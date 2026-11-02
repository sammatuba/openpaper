"""POST /tasks/run executes a registered task in-process (TASK_BACKEND=cloudtasks)."""

import os
import unittest
from unittest import mock

os.environ.setdefault("TASK_BACKEND", "cloudtasks")

from fastapi.testclient import TestClient  # noqa: E402

from src import app as jobs_api  # noqa: E402
from src.celery_app import celery_app  # noqa: E402


SEEN = []


@celery_app.task(bind=True, name="test_echo")
def echo(self, value: str):
    # update_state must work without Redis (memory backend in cloudtasks mode).
    self.update_state(state="PROGRESS", meta={"status": "echoing"})
    SEEN.append((self.request.id, value))
    return {"task_id": self.request.id, "value": value}


@celery_app.task(bind=True, name="test_boom")
def boom(self):
    raise RuntimeError("boom")


class RunTask(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(jobs_api.app)
        patcher = mock.patch.object(
            jobs_api, "RUNNABLE_TASKS", jobs_api.RUNNABLE_TASKS | {"test_echo", "test_boom"}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_runs_the_task_with_the_given_id(self):
        with mock.patch.dict(os.environ, {"JOBS_INTERNAL_SECRET": ""}):
            response = self.client.post(
                "/tasks/run", json={"task": "test_echo", "task_id": "id-1", "kwargs": {"value": "hi"}}
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"task_id": "id-1", "status": "completed"})
        # The task ran under the id the server stored, so its webhook matches the job row.
        self.assertIn(("id-1", "hi"), SEEN)

    def test_a_failing_task_is_reported_not_retried(self):
        with mock.patch.dict(os.environ, {"JOBS_INTERNAL_SECRET": ""}):
            response = self.client.post("/tasks/run", json={"task": "test_boom", "task_id": "id-2"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "failed")
        self.assertIn("boom", response.json()["error"])

    def test_unknown_task_is_404(self):
        with mock.patch.dict(os.environ, {"JOBS_INTERNAL_SECRET": ""}):
            response = self.client.post("/tasks/run", json={"task": "nope", "task_id": "x"})
        self.assertEqual(response.status_code, 404)

    def test_shared_secret_is_enforced_when_set(self):
        with mock.patch.dict(os.environ, {"JOBS_INTERNAL_SECRET": "s"}):
            denied = self.client.post("/tasks/run", json={"task": "test_echo", "task_id": "x", "kwargs": {"value": "v"}})
            allowed = self.client.post(
                "/tasks/run",
                json={"task": "test_echo", "task_id": "y", "kwargs": {"value": "v"}},
                headers={"Authorization": "Bearer s"},
            )
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(allowed.status_code, 200)


if __name__ == "__main__":
    unittest.main()
