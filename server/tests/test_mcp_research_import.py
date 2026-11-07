"""MCP import ledger: authenticated role checks, canonical duplicate and job tracking."""
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.mcp import research_import


class TestImportLedger(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = MagicMock()
        self.user = SimpleNamespace(id=uuid.uuid4())
        self.pid = str(uuid.uuid4())
        self.rid = str(uuid.uuid4())
        self.url = "https://arxiv.org/abs/2512.16856"

    async def test_invalid_uuid_rejected_before_database_or_download(self):
        with patch.object(research_import, "fetch_research_pdf", new_callable=AsyncMock) as fetch:
            with self.assertRaises(ValueError):
                await research_import.import_paper_from_url(
                    self.db, self.user, "not-a-uuid", self.rid, self.url
                )
            fetch.assert_not_awaited()

    async def test_replay_cannot_change_original_source(self):
        source = "arxiv:2512.16856"
        previous = SimpleNamespace(
            user_id=self.user.id, request_id=uuid.UUID(self.rid),
            project_id=uuid.UUID(self.pid), source_key=source,
            source_url="https://arxiv.org/pdf/2512.16856.pdf",
            upload_job_id=None, paper_id=None, status="submitted", error_message=None,
        )
        self.db.query.return_value.filter.return_value.with_for_update.return_value.one_or_none.return_value = SimpleNamespace()
        self.db.query.return_value.filter.return_value.one_or_none.return_value = previous
        with patch.object(research_import, "_require_editor"), \
             patch.object(research_import, "fetch_research_pdf", new_callable=AsyncMock) as fetch:
            with self.assertRaisesRegex(ValueError, "different import"):
                await research_import.import_paper_from_url(
                    self.db, self.user, self.pid, self.rid, self.url
                )
            fetch.assert_not_awaited()

    async def test_no_permission_rejected_before_fetch(self):
        with patch.object(research_import, "_require_editor", side_effect=PermissionError), \
             patch.object(research_import, "fetch_research_pdf", new_callable=AsyncMock) as fetch:
            with self.assertRaises(PermissionError):
                await research_import.import_paper_from_url(
                    self.db, self.user, self.pid, self.rid, self.url
                )
            fetch.assert_not_awaited()

    async def test_source_duplicate_does_not_enqueue(self):
        previous = SimpleNamespace(
            user_id=self.user.id, request_id=uuid.uuid4(),
            project_id=uuid.UUID(self.pid), source_key="arxiv:2512.16856",
            source_url=self.url, upload_job_id=None, paper_id=None,
            status="reserved", error_message=None,
        )
        first = MagicMock()
        first.filter.return_value.with_for_update.return_value.one_or_none.return_value = SimpleNamespace()
        second = MagicMock()
        second.filter.return_value.one_or_none.return_value = None
        third = MagicMock()
        third.filter.return_value.one_or_none.return_value = previous
        self.db.query.side_effect = [first, second, third]
        with patch.object(research_import, "_require_editor"), \
             patch.object(research_import, "fetch_research_pdf", new_callable=AsyncMock) as fetch, \
             patch.object(research_import.jobs_client, "submit_pdf_processing_job_with_upload", new_callable=AsyncMock) as submit:
            result = await research_import.import_paper_from_url(
                self.db, self.user, self.pid, self.rid, self.url
            )
            self.assertEqual(result["status"], "already_requested")
            fetch.assert_not_awaited()
            submit.assert_not_awaited()

    def test_unowned_status_never_exposed(self):
        self.db.query.return_value.filter.return_value.one_or_none.return_value = None
        with self.assertRaisesRegex(ValueError, "not found"):
            research_import.get_import_status(self.db, self.user, self.rid)


if __name__ == "__main__":
    unittest.main()
