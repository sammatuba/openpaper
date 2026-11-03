"""PDF replay against the dedicated socket-only test cluster, never a live DB."""
import asyncio
import getpass
import os
import unittest
from unittest.mock import patch
from uuid import uuid4


@unittest.skipUnless(os.environ.get("OPENPAPER_ISOLATED_PG_TEST") == "1", "requires isolated /tmp/openpaper-pg-transaction-test cluster")
class PdfWebhookPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        username = getpass.getuser()
        expected = f"postgresql://{username}@/postgres?host=/tmp&port=55439"
        if (os.getcwd() != "/tmp" or os.environ.get("PYTHON_DOTENV_DISABLED") != "1"
                or os.environ.get("DATABASE_URL") != expected):
            raise RuntimeError("Requires /tmp, disabled dotenv and the dedicated local database")
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import URL
        from sqlalchemy.orm import sessionmaker
        from app.api import webhook_api
        from app.database import models

        cls.api, cls.models, cls.text = webhook_api, models, staticmethod(text)
        url = URL.create("postgresql+psycopg2", username=username, database="postgres", query={"host": "/tmp", "port": "55439"})
        cls.admin = create_engine(url)
        with cls.admin.connect() as connection:
            if (connection.execute(text("SHOW data_directory")).scalar_one() != "/tmp/openpaper-pg-transaction-test"
                    or connection.execute(text("SHOW listen_addresses")).scalar_one()):
                raise RuntimeError("Refusing non-isolated PostgreSQL cluster")
        cls.schema = "pdf_webhook_test_" + uuid4().hex
        with cls.admin.begin() as connection:
            connection.execute(text("CREATE SCHEMA " + cls.schema))
        cls.engine = create_engine(url, connect_args={"options": "-csearch_path=" + cls.schema})
        try:
            with cls.engine.begin() as connection:
                for model in (models.User, models.PaperUploadJob, models.Paper, models.Highlight,
                              models.Annotation, models.Conversation, models.Message):
                    model.__table__.create(connection)
            cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.admin.begin() as connection:
            connection.execute(cls.text("DROP SCHEMA " + cls.schema + " CASCADE"))
        cls.admin.dispose()

    def test_crash_after_enrichment_then_replay(self):
        from fastapi import BackgroundTasks, HTTPException
        m, api = self.models, self.api
        user_id, job_id, paper_id = uuid4(), uuid4(), uuid4()
        with self.Session.begin() as session:
            session.add(m.User(id=user_id, email=f"{user_id}@example.com", name="User", auth_provider="test", provider_user_id=str(user_id)))
            session.add(m.PaperUploadJob(id=job_id, user_id=user_id, task_id="task", status=m.JobStatus.PENDING))
            session.flush()
            session.add(m.Paper(id=paper_id, user_id=user_id, upload_job_id=job_id, file_url="file", page_offset_map={"1": [0, 4]}))
        payload = api.PdfProcessingWebhookData(task_id="task", status="completed", result={
            "success": True, "job_id": str(job_id), "file_url": "file", "raw_content": "text",
            "page_offset_map": {"1": [0, 4]}, "metadata": {"title": "Paper", "summary": "Summary",
            "highlights": [{"text": "text", "type": "topic", "annotation": "Note"}]},
        })
        original_complete = api.paper_upload_job_crud.mark_as_completed
        def call():
            with self.Session() as session:
                return asyncio.run(api.handle_paper_processing_webhook(str(job_id), payload, BackgroundTasks(), session))
        def counts():
            with self.Session() as session:
                return (session.get(m.PaperUploadJob, job_id).status,
                        *(session.query(model).count() for model in (m.Highlight, m.Annotation, m.Conversation, m.Message)))
        with patch.object(api, "engine", self.engine), \
             patch.object(api.zotero_import_crud, "get_by_upload_job_id", return_value=None), \
             patch.object(api, "track_event"), \
             patch.object(api.paper_upload_job_crud, "mark_as_completed", side_effect=[RuntimeError("crash"), None]) as complete:
            with self.assertRaises(HTTPException):
                call()
            self.assertEqual(counts(), (m.JobStatus.PENDING, 0, 0, 0, 0))
            complete.side_effect = original_complete
            call()
            self.assertEqual(counts(), (m.JobStatus.COMPLETED, 1, 1, 1, 1))
            self.assertIn("already completed", call()["status"])
            self.assertEqual(counts(), (m.JobStatus.COMPLETED, 1, 1, 1, 1))
