"""
Where asynchronous work is sent.

TASK_BACKEND selects it:

- ``celery`` (default, upstream): tasks go to the Celery broker and the jobs
  worker consumes them. Nothing in this module is used.
- ``cloudtasks``: tasks are HTTP-pushed by Google Cloud Tasks to the jobs
  service's ``POST /tasks/run``, which executes the Celery task in-process.
  No broker, no result backend, no always-on worker. Completion and failure
  still arrive on the server by webhook, exactly as with Celery; the only
  difference is that status polling cannot see intermediate progress.

The Cloud Tasks REST API is called directly with the ambient Google
credentials (google-auth ships with google-genai), so no extra dependency.
"""

import base64
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CLOUD_TASKS_API = "https://cloudtasks.googleapis.com/v2"
# Cloud Tasks caps an HTTP dispatch at 30 minutes; the jobs service request
# timeout is set to match in deploy/.
DISPATCH_DEADLINE = "1800s"


def get_task_backend_name() -> str:
    return (os.getenv("TASK_BACKEND") or "celery").strip().lower()


def uses_cloud_tasks() -> bool:
    return get_task_backend_name() == "cloudtasks"


class CloudTasksBackend:
    """Enqueue work on a Cloud Tasks queue that pushes to the jobs service."""

    def __init__(
        self,
        project: Optional[str] = None,
        location: Optional[str] = None,
        queue: Optional[str] = None,
        target_url: Optional[str] = None,
        service_account: Optional[str] = None,
        internal_secret: Optional[str] = None,
    ) -> None:
        self.project = project or os.getenv("CLOUD_TASKS_PROJECT", "")
        self.location = location or os.getenv("CLOUD_TASKS_LOCATION", "")
        self.queue = queue or os.getenv("CLOUD_TASKS_QUEUE", "")
        self.target_url = target_url or os.getenv("CLOUD_TASKS_TARGET_URL", "")
        # Cloud Tasks mints an OIDC token for this account; the jobs service
        # is deployed without public invokers and Cloud Run IAM checks it.
        self.service_account = service_account or os.getenv(
            "CLOUD_TASKS_SERVICE_ACCOUNT", ""
        )
        # Defense in depth: the runner also checks this shared secret.
        self.internal_secret = internal_secret or os.getenv("JOBS_INTERNAL_SECRET", "")

        missing = [
            name
            for name, value in (
                ("CLOUD_TASKS_PROJECT", self.project),
                ("CLOUD_TASKS_LOCATION", self.location),
                ("CLOUD_TASKS_QUEUE", self.queue),
                ("CLOUD_TASKS_TARGET_URL", self.target_url),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "TASK_BACKEND=cloudtasks needs " + ", ".join(missing) + " to be set"
            )

    @property
    def parent(self) -> str:
        return (
            f"projects/{self.project}/locations/{self.location}/queues/{self.queue}"
        )

    def _session(self):  # pragma: no cover - exercised against real GCP only
        from google.auth import default
        from google.auth.transport.requests import AuthorizedSession

        credentials, _ = default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return AuthorizedSession(credentials)

    def build_task(
        self,
        task_name: str,
        kwargs: Dict[str, Any],
        *,
        task_id: Optional[str] = None,
        eta: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """The Cloud Tasks task resource for one job. Split out so the
        payload can be checked without network access."""
        task_id = task_id or str(uuid.uuid4())
        body = {"task": task_name, "task_id": task_id, "kwargs": kwargs}
        headers = {"Content-Type": "application/json"}
        if self.internal_secret:
            # Not Authorization: Cloud Tasks overwrites that header with the
            # OIDC token, and Cloud Run's front end consumes it.
            headers["X-Jobs-Secret"] = self.internal_secret

        http_request: Dict[str, Any] = {
            "httpMethod": "POST",
            "url": self.target_url,
            "headers": headers,
            "body": base64.b64encode(json.dumps(body).encode()).decode(),
        }
        if self.service_account:
            http_request["oidcToken"] = {"serviceAccountEmail": self.service_account}

        task: Dict[str, Any] = {
            # Naming the task with our id makes the enqueue idempotent and
            # lets the webhook match on the same id the job row stores.
            "name": f"{self.parent}/tasks/{task_id}",
            "httpRequest": http_request,
            "dispatchDeadline": DISPATCH_DEADLINE,
        }
        if eta is not None:
            if eta.tzinfo is None:
                eta = eta.replace(tzinfo=timezone.utc)
            task["scheduleTime"] = (
                eta.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            )
        return task

    def send_task(
        self,
        task_name: str,
        kwargs: Dict[str, Any],
        *,
        eta: Optional[datetime] = None,
    ) -> str:
        task = self.build_task(task_name, kwargs, eta=eta)
        task_id = task["name"].rsplit("/", 1)[1]
        response = self._session().post(
            f"{CLOUD_TASKS_API}/{self.parent}/tasks", json={"task": task}, timeout=15
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Cloud Tasks refused {task_name}: {response.status_code} {response.text}"
            )
        logger.info(f"Enqueued {task_name} on Cloud Tasks as {task_id}")
        return task_id

    def task_status(self, task_id: str) -> Dict[str, Any]:
        """Cloud Tasks has no task state the server can read; completion and
        failure come by webhook. Report pending so callers keep waiting."""
        return {
            "task_id": task_id,
            "status": "pending",
            "meta": {"message": "Cloud Tasks backend: progress is reported by webhook"},
        }

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        response = self._session().delete(
            f"{CLOUD_TASKS_API}/{self.parent}/tasks/{task_id}", timeout=15
        )
        if response.status_code not in (200, 204, 404):
            raise RuntimeError(
                f"Cloud Tasks could not cancel {task_id}: {response.status_code} {response.text}"
            )
        return {
            "task_id": task_id,
            "status": "cancelled",
            "message": "Task removed from the queue (a running task finishes)",
        }
