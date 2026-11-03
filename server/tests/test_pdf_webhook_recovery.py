"""PDF outcome retries preserve the paper through receiver failures."""
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine, text
from app.api import webhook_api as api
from app.database.models import JobStatus
from app.schemas.responses import AIHighlight


class PdfWebhookRecovery(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.job_id = str(uuid4())
        self.user = MagicMock(id=uuid4(), email="user@example.com", name="User", is_admin=False)
        self.user.name = "User"
        self.job = MagicMock(id=self.job_id, user=self.user, status=JobStatus.PENDING,
                             created_at=datetime.now(timezone.utc))
        self.paper = MagicMock(id=uuid4())
        self.db = MagicMock()
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        self.engine_patch = patch.object(api, "engine", self.engine)
        self.engine_patch.start()
        self.addCleanup(self.engine_patch.stop)
        self.data = api.PdfProcessingWebhookData(task_id="task", status="completed", result={
            "success": True, "job_id": self.job_id, "file_url": "https://private/file",
            "raw_content": "text", "metadata": {"title": "Paper"},
        })
        self.patches = [
            patch.object(api.paper_upload_job_crud, "get_by", return_value=self.job),
            patch.object(api.zotero_import_crud, "get_by_upload_job_id", return_value=None),
            patch.object(api.paper_crud, "get_by_upload_job_id", return_value=self.paper),
            patch.object(api.paper_crud, "update", return_value=self.paper),
            patch.object(api.paper_upload_job_crud, "mark_as_completed", return_value=self.job),
            patch.object(api, "handle_failed_upload"),
            patch.object(api, "AdvisoryLock"),
            patch.object(api, "track_event"),
        ]
        self.mocks = [p.start() for p in self.patches]
        self.mocks[6].return_value.acquire.return_value = True
        for p in self.patches:
            self.addCleanup(p.stop)

    async def call(self):
        return await api.handle_paper_processing_webhook(self.job_id, self.data, BackgroundTasks(), self.db)

    async def test_paper_write_failure_retries_without_deleting_paper(self):
        self.mocks[3].side_effect = [None, self.paper]
        with self.assertRaises(HTTPException) as error:
            await self.call()
        self.assertEqual(error.exception.status_code, 500)
        self.mocks[4].assert_not_called()
        self.mocks[5].assert_not_called()
        self.db.rollback.assert_called_once()
        await self.call()
        self.mocks[4].assert_called_once()
        self.mocks[5].assert_not_called()

    async def test_status_write_failure_retries(self):
        self.mocks[4].side_effect = [None, self.job]
        with patch.object(api.paper_tag_crud, "apply_keyword_tags") as tags:
            self.data.result.metadata.keywords = ["keyword"]
            with self.assertRaises(HTTPException):
                await self.call()
            tags.assert_called_once()
            self.mocks[5].assert_not_called()
            await self.call()
            self.assertEqual(tags.call_count, 2)

    async def test_failed_outcome_retries_when_failure_status_write_fails(self):
        self.patches[5].stop()  # Exercise the real failed-upload handler.
        self.data = api.PdfProcessingWebhookData(task_id="task", status="failed", result=None, error="worker failed")
        self.mocks[2].return_value = None
        with patch.object(api.paper_upload_job_crud, "get", return_value=self.job), \
             patch.object(api.paper_upload_job_crud, "mark_as_failed", side_effect=[None, self.job]) as mark_failed:
            with self.assertRaises(HTTPException) as error:
                await self.call()
            self.assertEqual(error.exception.status_code, 500)
            self.db.rollback.assert_called_once()
            result = await self.call()
            self.assertEqual(result["status"], "webhook processed")
            self.assertEqual(mark_failed.call_count, 2)

    async def test_failed_outcome_retries_if_paper_cleanup_fails(self):
        self.patches[5].stop()
        self.data = api.PdfProcessingWebhookData(task_id="task", status="failed", result=None, error="worker failed")
        with patch.object(api.paper_upload_job_crud, "get", return_value=self.job), \
             patch.object(api.project_paper_crud, "get_projects_by_paper_id", return_value=[]), \
             patch.object(api.paper_crud, "remove", side_effect=[None, self.paper]), \
             patch.object(api.paper_upload_job_crud, "mark_as_failed", return_value=self.job) as mark_failed:
            with self.assertRaises(HTTPException) as error:
                await self.call()
            self.assertEqual(error.exception.status_code, 500)
            mark_failed.assert_not_called()
            result = await self.call()
            self.assertEqual(result["status"], "webhook processed")
            mark_failed.assert_called_once()

    async def test_crash_rolls_back_enrichment_and_replay_does_not_duplicate(self):
        with self.engine.begin() as conn:
            conn.execute(text("CREATE TABLE enrichment (kind TEXT)"))
        self.data.result.metadata.highlights = [AIHighlight(text="text", type="topic", annotation="note")]
        self.data.result.metadata.summary = "summary"
        def highlights(db, **kwargs):
            db.execute(text("INSERT INTO enrichment VALUES ('highlight')"))
            db.commit()
        def conversation(db, **kwargs):
            db.execute(text("INSERT INTO enrichment VALUES ('conversation')"))
            db.commit()
            return MagicMock(id=uuid4())
        def message(db, **kwargs):
            db.execute(text("INSERT INTO enrichment VALUES ('message')"))
            db.commit()
            return True
        self.mocks[4].side_effect = [RuntimeError("crash before completion"), self.job]
        with patch.object(api.paper_crud, "create_ai_annotations", side_effect=highlights), \
             patch.object(api.conversation_crud, "create", side_effect=conversation), \
             patch.object(api.message_crud, "create", side_effect=message):
            with self.assertRaises(HTTPException):
                await self.call()
            with self.engine.connect() as conn:
                self.assertEqual(conn.execute(text("SELECT count(*) FROM enrichment")).scalar(), 0)
            await self.call()
            with self.engine.connect() as conn:
                self.assertEqual(conn.execute(text("SELECT kind FROM enrichment ORDER BY kind")).scalars().all(),
                                 ["conversation", "highlight", "message"])
            self.job.status = JobStatus.COMPLETED
            await self.call()
            with self.engine.connect() as conn:
                self.assertEqual(conn.execute(text("SELECT count(*) FROM enrichment")).scalar(), 3)

    async def test_telemetry_failure_does_not_lose_completed_outcome(self):
        self.mocks[7].side_effect = RuntimeError("telemetry down")
        result = await self.call()
        self.assertEqual(result["status"], "webhook processed")
        self.mocks[4].assert_called_once()
        self.mocks[5].assert_not_called()
