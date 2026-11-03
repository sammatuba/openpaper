"""Durable Cloud Tasks outcome delivery and replay, without network access."""
import io
import json
import os
import unittest
from unittest import mock

import requests
from botocore.exceptions import ClientError
from fastapi import HTTPException

os.environ.setdefault("TASK_BACKEND", "cloudtasks")
from src import app, tasks


class MemoryStore:
    def __init__(self):
        self.objects = {}
        self.fail_write = False

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, Bucket, Key, Body, **kwargs):
        if self.fail_write:
            raise RuntimeError("storage down")
        if Key in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.objects[Key] = Body


class OutcomeDelivery(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        patch = mock.patch.object(tasks.s3_service, "s3_client", self.store)
        patch.start()
        self.addCleanup(patch.stop)
        bucket = mock.patch.object(tasks.s3_service, "bucket_name", "test-bucket")
        bucket.start()
        self.addCleanup(bucket.stop)

    def test_outage_and_recovery_replays_both_outcome_kinds(self):
        for kind in ("upload_and_process_file", "process_data_table"):
            for status in ("completed", "failed"):
                task_id = kind + status
                payload = {"task_id": task_id, "status": status, "result": None}
                with mock.patch.object(tasks, "post_webhook", side_effect=requests.ConnectionError("down")):
                    with self.assertRaises(tasks.OutcomeDeliveryError):
                        tasks.deliver_outcome(kind, task_id, "http://server/hook", payload)
                with mock.patch.object(tasks, "post_webhook") as post, mock.patch.object(app, "celery_app") as celery:
                    response = app.run_task(app.RunTaskRequest(task=kind, task_id=task_id, kwargs={"webhook_url": "http://server/hook"}), authorization=None, x_jobs_secret=None)
                    self.assertEqual(response["status"], "completed")
                    celery.tasks.get.return_value.apply.assert_not_called()
                    post.assert_called_once_with("http://server/hook", payload, delays=())

    def test_storage_failure_does_not_deliver(self):
        self.store.fail_write = True
        with mock.patch.object(tasks, "post_webhook") as post:
            with self.assertRaises(tasks.OutcomeDeliveryError):
                tasks.deliver_outcome("process_data_table", "id", "http://server/hook", {"status": "completed"})
            post.assert_not_called()

    def test_conflicting_outcome_does_not_replace_success(self):
        with mock.patch.object(tasks, "post_webhook") as post:
            tasks.deliver_outcome("process_data_table", "id", "http://server/hook", {"status": "completed"})
            tasks.deliver_outcome("process_data_table", "id", "http://server/hook", {"status": "failed"})
            self.assertEqual(post.call_args.args[1], {"status": "completed"})

    def test_gcs_generation_precondition_and_errors(self):
        with mock.patch.dict(os.environ, {"AWS_ENDPOINT_URL_S3": "https://storage.googleapis.com"}), \
             mock.patch("google.auth.default", return_value=(object(), None)), \
             mock.patch("google.auth.transport.requests.AuthorizedSession") as session:
            response = session.return_value.post.return_value
            response.status_code = 200
            self.assertTrue(tasks.put_outcome_once("process_data_table", "id", b"{}"))
            self.assertEqual(session.return_value.post.call_args.kwargs["params"]["ifGenerationMatch"], "0")
            response.status_code = 412
            self.assertFalse(tasks.put_outcome_once("process_data_table", "id", b"{}"))
            response.status_code = 503
            response.raise_for_status.side_effect = requests.HTTPError("unavailable")
            with self.assertRaises(requests.HTTPError):
                tasks.put_outcome_once("process_data_table", "id", b"{}")

    def test_failed_task_execution_is_not_acknowledged(self):
        for kind in ("upload_and_process_file", "process_data_table"):
            with mock.patch.object(app, "celery_app") as celery:
                celery.tasks.get.return_value.apply.return_value.failed.return_value = True
                with self.assertRaises(HTTPException) as error:
                    app.run_task(app.RunTaskRequest(task=kind, task_id="missing", kwargs={"webhook_url": "http://server/hook"}), authorization=None, x_jobs_secret=None)
                self.assertEqual(error.exception.status_code, 503)

    def test_default_celery_mode_does_not_read_checkpoint(self):
        with mock.patch.dict(os.environ, {"TASK_BACKEND": "celery"}), \
             mock.patch.object(app, "celery_app") as celery, \
             mock.patch.object(tasks, "load_outcome") as load:
            celery.tasks.get.return_value.apply.return_value.failed.return_value = False
            result = app.run_task(app.RunTaskRequest(task="process_data_table", task_id="id"), authorization=None, x_jobs_secret=None)
            self.assertEqual(result["status"], "completed")
            load.assert_not_called()
            celery.tasks.get.return_value.apply.assert_called_once()

    def test_replay_rejects_changed_target(self):
        with mock.patch.object(tasks, "post_webhook"):
            tasks.deliver_outcome("process_data_table", "id", "http://server/hook", {"status": "completed"})
        with mock.patch.object(tasks, "post_webhook") as post:
            with mock.patch.object(app, "celery_app"), self.assertRaises(HTTPException) as error:
                app.run_task(app.RunTaskRequest(task="process_data_table", task_id="id", kwargs={"webhook_url": "http://other/hook"}), authorization=None, x_jobs_secret=None)
            self.assertEqual(error.exception.status_code, 503)
            post.assert_not_called()
