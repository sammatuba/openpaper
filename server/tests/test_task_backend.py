"""TASK_BACKEND selects where async work goes: the Celery broker by default,
Cloud Tasks pushes when set to cloudtasks. These check the switch and the
Cloud Tasks payload without touching the network."""

import base64
import json
import os
import unittest
from datetime import datetime, timezone
from unittest import mock

from app.helpers.task_backend import (
    CloudTasksBackend,
    get_task_backend_name,
    uses_cloud_tasks,
)

CLOUD_TASKS_ENV = {
    "TASK_BACKEND": "cloudtasks",
    "CLOUD_TASKS_PROJECT": "proj",
    "CLOUD_TASKS_LOCATION": "asia-southeast1",
    "CLOUD_TASKS_QUEUE": "openpaper-jobs",
    "CLOUD_TASKS_TARGET_URL": "https://jobs.example.run.app/tasks/run",
    "CLOUD_TASKS_SERVICE_ACCOUNT": "tasks@proj.iam.gserviceaccount.com",
    "JOBS_INTERNAL_SECRET": "s3cret",
}


class BackendSelection(unittest.TestCase):
    def test_default_is_celery(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TASK_BACKEND", None)
            self.assertEqual(get_task_backend_name(), "celery")
            self.assertFalse(uses_cloud_tasks())

    def test_cloudtasks_is_case_insensitive(self):
        with mock.patch.dict(os.environ, {"TASK_BACKEND": " CloudTasks "}):
            self.assertTrue(uses_cloud_tasks())

    def test_missing_config_names_every_missing_variable(self):
        env = {"TASK_BACKEND": "cloudtasks", "CLOUD_TASKS_PROJECT": "proj"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError) as ctx:
                CloudTasksBackend()
        message = str(ctx.exception)
        for name in ("CLOUD_TASKS_LOCATION", "CLOUD_TASKS_QUEUE", "CLOUD_TASKS_TARGET_URL"):
            self.assertIn(name, message)
        self.assertNotIn("CLOUD_TASKS_PROJECT", message)


class CloudTasksPayload(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, CLOUD_TASKS_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.backend = CloudTasksBackend()

    def test_task_carries_name_id_and_kwargs_to_the_runner(self):
        task = self.backend.build_task(
            "upload_and_process_file",
            {"s3_object_key": "k", "webhook_url": "https://app/api/webhooks/paper-processing/j"},
            task_id="abc-123",
        )
        self.assertEqual(
            task["name"],
            "projects/proj/locations/asia-southeast1/queues/openpaper-jobs/tasks/abc-123",
        )
        http = task["httpRequest"]
        self.assertEqual(http["httpMethod"], "POST")
        self.assertEqual(http["url"], CLOUD_TASKS_ENV["CLOUD_TASKS_TARGET_URL"])
        self.assertEqual(http["headers"]["X-Jobs-Secret"], "s3cret")
        self.assertNotIn("Authorization", http["headers"])
        self.assertEqual(
            http["oidcToken"], {"serviceAccountEmail": CLOUD_TASKS_ENV["CLOUD_TASKS_SERVICE_ACCOUNT"]}
        )
        body = json.loads(base64.b64decode(http["body"]))
        self.assertEqual(body["task"], "upload_and_process_file")
        self.assertEqual(body["task_id"], "abc-123")
        self.assertEqual(body["kwargs"]["s3_object_key"], "k")
        self.assertEqual(task["dispatchDeadline"], "1800s")
        self.assertNotIn("scheduleTime", task)

    def test_eta_becomes_a_utc_schedule_time(self):
        eta = datetime(2026, 11, 3, 1, 2, 3, 456000, tzinfo=timezone.utc)
        task = self.backend.build_task("delayed_referral_settlement_callback", {}, eta=eta)
        self.assertEqual(task["scheduleTime"], "2026-11-03T01:02:03.456Z")

    def test_generated_ids_are_unique_and_url_safe(self):
        ids = {self.backend.build_task("t", {})["name"].rsplit("/", 1)[1] for _ in range(5)}
        self.assertEqual(len(ids), 5)
        for task_id in ids:
            self.assertRegex(task_id, r"^[A-Za-z0-9_-]+$")

    def test_status_is_pending_and_points_at_the_webhook(self):
        status = self.backend.task_status("abc")
        self.assertEqual(status["status"], "pending")
        self.assertEqual(status["task_id"], "abc")

    def test_send_posts_to_the_queue_and_returns_the_id(self):
        session = mock.Mock()
        session.post.return_value = mock.Mock(status_code=200, text="")
        with mock.patch.object(self.backend, "_session", return_value=session):
            task_id = self.backend.send_task("process_data_table", {"data_table": {}})
        url = session.post.call_args.args[0]
        self.assertTrue(url.endswith("/queues/openpaper-jobs/tasks"))
        sent = session.post.call_args.kwargs["json"]["task"]
        self.assertTrue(sent["name"].endswith(f"/tasks/{task_id}"))

    def test_send_raises_on_a_refused_task(self):
        session = mock.Mock()
        session.post.return_value = mock.Mock(status_code=403, text="denied")
        with mock.patch.object(self.backend, "_session", return_value=session):
            with self.assertRaises(RuntimeError):
                self.backend.send_task("process_data_table", {})


class JobsClientRouting(unittest.TestCase):
    """JobsClient hands work to Cloud Tasks only when TASK_BACKEND says so."""

    def test_pdf_job_goes_to_cloud_tasks_with_the_webhook_url(self):
        env = dict(CLOUD_TASKS_ENV, WEBHOOK_BASE_URL="https://app.example")
        with mock.patch.dict(os.environ, env):
            from app.helpers.pdf_jobs import JobsClient

            client = JobsClient()
            with mock.patch.object(client.cloud_tasks, "send_task", return_value="tid") as send:
                self.assertEqual(client.submit_pdf_processing_job("key.pdf", "job-1"), "tid")
        name, kwargs = send.call_args.args
        self.assertEqual(name, "upload_and_process_file")
        self.assertEqual(kwargs["s3_object_key"], "key.pdf")
        self.assertEqual(
            kwargs["webhook_url"], "https://app.example/api/webhooks/paper-processing/job-1"
        )
        self.assertFalse(kwargs["skip_metadata_extraction"])

    def test_status_and_cancel_do_not_call_the_celery_api(self):
        with mock.patch.dict(os.environ, CLOUD_TASKS_ENV):
            from app.helpers.pdf_jobs import JobsClient

            client = JobsClient()
            with mock.patch("app.helpers.pdf_jobs.requests") as requests_mod:
                self.assertEqual(client.check_celery_task_status("t")["status"], "pending")
                with mock.patch.object(client.cloud_tasks, "cancel_task", return_value={"status": "cancelled"}):
                    self.assertEqual(client.cancel_celery_task("t")["status"], "cancelled")
            requests_mod.get.assert_not_called()
            requests_mod.delete.assert_not_called()

    def test_default_backend_has_no_cloud_tasks_client(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TASK_BACKEND", None)
            from app.helpers.pdf_jobs import JobsClient

            self.assertIsNone(JobsClient().cloud_tasks)


if __name__ == "__main__":
    unittest.main()
