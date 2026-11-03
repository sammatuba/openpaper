"""Real transaction checks against the dedicated, socket-only local test cluster.

Opt in explicitly; see the invocation in the module-level skip message. Never
connect to a configured application database or reuse its schema.
"""
import os
import getpass
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4


@unittest.skipUnless(os.environ.get("OPENPAPER_ISOLATED_PG_TEST") == "1", "requires isolated /tmp/openpaper-pg-transaction-test cluster")
class TableWebhookPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        username = getpass.getuser()
        expected_url = f"postgresql://{username}@/postgres?host=/tmp&port=55439"
        if (os.getcwd() != "/tmp" or os.environ.get("PYTHON_DOTENV_DISABLED") != "1"
                or os.environ.get("DATABASE_URL") != expected_url):
            raise RuntimeError("Run from /tmp with dotenv disabled and the dedicated local DATABASE_URL")
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import URL
        from sqlalchemy.orm import sessionmaker
        from app.api import webhook_api
        from app.database.models import DataTableExtractionJob, DataTableExtractionResult, DataTableRow

        cls.api = webhook_api
        cls.Job = DataTableExtractionJob
        cls.Result = DataTableExtractionResult
        cls.Row = DataTableRow
        cls.text = staticmethod(text)
        url = URL.create("postgresql+psycopg2", username=username, database="postgres", query={"host": "/tmp", "port": "55439"})
        cls.admin = create_engine(url)
        with cls.admin.connect() as connection:
            directory = connection.execute(text("SHOW data_directory")).scalar_one()
            listening = connection.execute(text("SHOW listen_addresses")).scalar_one()
            if directory != "/tmp/openpaper-pg-transaction-test" or listening:
                raise RuntimeError("Refusing to test against a non-isolated PostgreSQL cluster")
        cls.schema = "webhook_test_" + uuid4().hex
        with cls.admin.begin() as connection:
            connection.execute(text("CREATE SCHEMA " + cls.schema))
        cls.engine = create_engine(url, connect_args={"options": "-csearch_path=" + cls.schema})
        try:
            with cls.engine.begin() as connection:
                # Minimal unrelated parents. The exercised job/result/row tables
                # are the real application SQLAlchemy tables and constraints.
                for table in ("users", "project", "papers"):
                    connection.execute(text("CREATE TABLE " + table + " (id uuid PRIMARY KEY)"))
                for table in (cls.Job.__table__, cls.Result.__table__, cls.Row.__table__):
                    table.create(connection)
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

    def setUp(self):
        self.job_id, self.user_id, self.paper_id = uuid4(), uuid4(), uuid4()
        with self.engine.begin() as connection:
            connection.execute(self.text("INSERT INTO users (id) VALUES (:id)"), {"id": self.user_id})
            connection.execute(self.text("INSERT INTO papers (id) VALUES (:id)"), {"id": self.paper_id})
        with self.Session.begin() as session:
            session.add(self.Job(id=self.job_id, user_id=self.user_id, task_id="task", status="pending", columns=["x"], column_plan=[]))
        self.patches = [patch.object(self.api.paper_crud, "get", return_value=SimpleNamespace(title="Paper")), patch.object(self.api.data_table_job_crud, "get_by_task_id", return_value=None)]
        for p in self.patches: p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])

    def payload(self, paper_id=None, task_id="task"):
        return self.api.DataTableProcessingResultWebhookData(task_id=task_id, status="completed", result={"success": True, "columns": ["x"], "rows": [{"paper_id": str(paper_id or self.paper_id), "values": {"x": {"value": "answer"}}}]})

    def call(self, payload):
        with self.Session() as session:
            return self.api.handle_data_table_processing_webhook(str(self.job_id), payload, session)

    def state(self):
        with self.Session() as session:
            job = session.get(self.Job, self.job_id)
            results = session.query(self.Result).filter_by(job_id=self.job_id).all()
            rows = session.query(self.Row).join(self.Result).filter(self.Result.job_id == self.job_id).all()
            return job.status, len(results), len(rows), [r.values for r in rows]

    def test_concurrent_duplicates_and_late_failure(self):
        entered, release, second_started, second_done = (threading.Event() for _ in range(4))
        second_pid = []
        def title(**kwargs):
            entered.set()
            if not release.wait(10): raise TimeoutError("first transaction not released")
            return "Table"
        def second():
            with self.Session() as session:
                second_pid.append(session.execute(self.text("SELECT pg_backend_pid()")).scalar_one())
                second_started.set()
                try: return self.api.handle_data_table_processing_webhook(str(self.job_id), self.payload(), session)
                finally: second_done.set()
        with patch.object(self.api.operations, "name_data_table", side_effect=title):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(self.call, self.payload())
                try:
                    self.assertTrue(entered.wait(5))
                    later = pool.submit(second)
                    self.assertTrue(second_started.wait(5))
                    deadline = time.monotonic() + 5
                    waiting = False
                    while time.monotonic() < deadline:
                        with self.admin.connect() as connection:
                            waiting = connection.execute(self.text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {"pid": second_pid[0]}).scalar_one_or_none()
                        if waiting or second_done.is_set(): break
                        time.sleep(0.02)
                    self.assertTrue(waiting, "PostgreSQL must report the second delivery waiting on a lock")
                finally:
                    release.set()
                first.result(timeout=10)
                self.assertIn("already completed", later.result(timeout=10)["status"])
        failure = self.api.DataTableProcessingResultWebhookData(task_id="task", status="failed", error="late")
        self.assertIn("already completed", self.call(failure)["status"])
        status, results, rows, values = self.state()
        self.assertEqual((status, results, rows), ("completed", 1, 1))
        self.assertEqual(values[0]["x"]["value"], "answer")

    def test_constraint_failure_rolls_back_result_rows_and_job(self):
        from fastapi import HTTPException
        with patch.object(self.api.operations, "name_data_table", return_value="Table"):
            with self.assertRaises(HTTPException) as caught:
                self.call(self.payload(paper_id=uuid4()))
        self.assertEqual(caught.exception.status_code, 500)
        self.assertEqual(self.state()[:3], ("pending", 0, 0))

    def test_wrong_task_does_not_change_job(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as caught:
            self.call(self.payload(task_id="other"))
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(self.state()[:3], ("pending", 0, 0))
