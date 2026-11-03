"""Data-table webhook commits its result and status as one unit."""
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from app.api import webhook_api as api
from app.database.models import JobStatus


class TableWebhookOutcomes(unittest.TestCase):
    def setUp(self):
        self.job_id = str(uuid4())
        self.job = MagicMock(status=JobStatus.PENDING, column_plan=[], columns=[])
        self.db = MagicMock()
        self.db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = self.job
        self.complete = api.DataTableProcessingResultWebhookData(
            task_id="task", status="completed", result={"success": True, "columns": ["x"], "rows": []}
        )

    @patch.object(api.data_table_job_crud, "get_by_task_id", return_value=None)
    @patch.object(api.operations, "name_data_table", return_value="Table")
    def test_duplicate_and_late_failure_do_not_create_results(self, name, lookup):
        api.handle_data_table_processing_webhook(self.job_id, self.complete, self.db)
        self.assertEqual(self.job.status, JobStatus.COMPLETED)
        self.assertEqual(self.db.commit.call_count, 1)
        self.assertEqual(self.db.add.call_count, 1)
        api.handle_data_table_processing_webhook(self.job_id, self.complete, self.db)
        failure = api.DataTableProcessingResultWebhookData(task_id="task", status="failed", error="late")
        api.handle_data_table_processing_webhook(self.job_id, failure, self.db)
        self.assertEqual(self.db.add.call_count, 1)
        self.assertEqual(self.db.commit.call_count, 1)

    @patch.object(api.operations, "name_data_table", return_value="Table")
    def test_commit_failure_rolls_back_and_requests_retry(self, name):
        self.db.commit.side_effect = RuntimeError("database down")
        with self.assertRaises(HTTPException) as error:
            api.handle_data_table_processing_webhook(self.job_id, self.complete, self.db)
        self.assertEqual(error.exception.status_code, 500)
        self.db.rollback.assert_called_once()

    def test_wrong_task_is_not_acknowledged(self):
        self.db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None
        with self.assertRaises(HTTPException) as error:
            api.handle_data_table_processing_webhook(self.job_id, self.complete, self.db)
        self.assertEqual(error.exception.status_code, 404)

    def test_failure_without_result_is_accepted(self):
        failure = api.DataTableProcessingResultWebhookData(task_id="task", status="failed", error="failed")
        api.handle_data_table_processing_webhook(self.job_id, failure, self.db)
        self.assertEqual(self.job.status, JobStatus.FAILED)
        self.db.commit.assert_called_once()
