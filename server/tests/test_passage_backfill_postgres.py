"""Passage maintenance against the explicitly isolated local PostgreSQL cluster."""
import getpass
import importlib.util
import os
from pathlib import Path
import unittest
from uuid import UUID, uuid4


@unittest.skipUnless(os.environ.get("OPENPAPER_ISOLATED_PG_TEST") == "1", "requires isolated /tmp PostgreSQL")
class PassageBackfillPostgresTests(unittest.TestCase):
    def setUp(self):
        username = getpass.getuser()
        expected = f"postgresql://{username}@/postgres?host=/tmp&port=55439"
        if (os.getcwd() != "/tmp" or os.environ.get("PYTHON_DOTENV_DISABLED") != "1"
                or os.environ.get("DATABASE_URL") != expected):
            raise RuntimeError("Requires /tmp, disabled dotenv and the dedicated local database")
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import URL
        from sqlalchemy.orm import sessionmaker
        from app.scripts.backfill_paper_passages import backfill

        self.text, self.backfill = text, backfill
        url = URL.create("postgresql+psycopg2", username=username, database="postgres",
                         query={"host": "/tmp", "port": "55439"})
        self.admin = create_engine(url)
        with self.admin.connect() as conn:
            if (conn.execute(text("SHOW data_directory")).scalar_one() != "/tmp/openpaper-pg-transaction-test"
                    or conn.execute(text("SHOW listen_addresses")).scalar_one()):
                raise RuntimeError("Refusing non-isolated PostgreSQL cluster")
        self.schema = "passage_maintenance_" + uuid4().hex
        with self.admin.begin() as conn:
            conn.execute(text("CREATE SCHEMA " + self.schema))
        self.addCleanup(self.cleanup_database)
        self.engine = create_engine(url, connect_args={"options": "-csearch_path=" + self.schema})
        self.readonly = create_engine(url, connect_args={
            "options": "-csearch_path=" + self.schema + " -cdefault_transaction_read_only=on"})
        self.Session = sessionmaker(bind=self.engine)
        with self.engine.begin() as conn:
            conn.execute(text("CREATE TABLE papers (id uuid PRIMARY KEY, raw_content text)"))
            conn.execute(text("INSERT INTO papers (id, raw_content) VALUES (:id, :content)"),
                         [{"id": UUID(int=i), "content": value}
                          for i, value in enumerate(("zero", "one", "", "legacy"))])
            # Run the real passage migration so normal insert/vector behavior is
            # exercised against its actual trigger and constraints.
            from alembic.migration import MigrationContext
            from alembic.operations import Operations
            path = Path(__file__).resolve().parents[1] / "migrations/versions/2026_03_18_1200_add_paper_passages_table.py"
            spec = importlib.util.spec_from_file_location("passages_migration", path)
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
            # A legacy missing-vector row is created before this fixture's
            # transaction ends; re-enable its real trigger before maintenance.
            conn.execute(text("ALTER TABLE paper_passages DISABLE TRIGGER paper_passages_tsvectorupdate"))
            conn.execute(text("INSERT INTO paper_passages (paper_id,start_line,end_line,content) "
                              "VALUES (:paper,1,1,'legacy')"), {"paper": UUID(int=3)})
            conn.execute(text("ALTER TABLE paper_passages ENABLE TRIGGER paper_passages_tsvectorupdate"))

    def cleanup_database(self):
        for name in ("engine", "readonly"):
            if hasattr(self, name):
                getattr(self, name).dispose()
        with self.admin.begin() as conn:
            conn.execute(self.text("DROP SCHEMA " + self.schema + " CASCADE"))
        self.admin.dispose()

    def state(self):
        with self.engine.connect() as conn:
            return (
                conn.execute(self.text("SELECT COUNT(*) FROM paper_passages")).scalar_one(),
                conn.execute(self.text("SELECT COUNT(*) FROM paper_passages WHERE ts_vector IS NULL")).scalar_one(),
                conn.execute(self.text("SELECT tgenabled FROM pg_trigger WHERE tgrelid = 'paper_passages'::regclass "
                                       "AND tgname = 'paper_passages_tsvectorupdate'")).scalar_one(),
            )

    @staticmethod
    def build(content):
        return [{"start_line": 1, "end_line": 1, "content": content}]

    def test_read_only_session_can_complete_finite_dry_run(self):
        from sqlalchemy.orm import Session, sessionmaker
        class ReadOnlySession(Session):
            def commit(self):
                raise AssertionError("dry run committed")

            def begin_nested(self):
                raise AssertionError("dry run created a savepoint")

        before = self.state()
        report = self.backfill(1, True,
                               session_factory=sessionmaker(bind=self.readonly, class_=ReadOnlySession),
                               build_passages=self.build)
        self.assertEqual((report["papers_found"], report["papers_scanned"], report["papers_planned"],
                          report["papers_skipped"], report["existing_missing_vectors"]), (3, 3, 2, 1, 1))
        self.assertEqual(self.state(), before)

    def test_normal_backfill_preserves_trigger_and_searches_new_and_legacy_text(self):
        report = self.backfill(1, session_factory=self.Session, build_passages=self.build)
        self.assertEqual((report["papers_indexed"], report["papers_skipped"], report["vectors_updated"]), (2, 1, 1))
        self.assertEqual(self.state(), (3, 0, "O"))
        with self.engine.connect() as conn:
            found = conn.execute(self.text("SELECT paper_id FROM paper_passages "
                                           "WHERE ts_vector @@ plainto_tsquery('english', 'legacy')")).scalars().all()
        self.assertEqual(found, [UUID(int=3)])
        again = self.backfill(1, session_factory=self.Session, build_passages=self.build)
        self.assertEqual((again["papers_scanned"], again["papers_indexed"], again["vectors_updated"]), (1, 0, 0))
        self.assertEqual(self.state(), (3, 0, "O"))

    def test_concurrent_delete_does_not_lose_other_papers_or_change_trigger(self):
        def build(content):
            if content == "zero":
                with self.engine.begin() as conn:
                    conn.execute(self.text("DELETE FROM papers WHERE id = :id"), {"id": UUID(int=0)})
            return self.build(content)

        report = self.backfill(3, session_factory=self.Session, build_passages=build)
        self.assertEqual((report["papers_indexed"], report["papers_skipped"]), (1, 2))
        self.assertEqual(self.state(), (2, 0, "O"))

    def test_failure_rolls_back_batch_and_preserves_trigger(self):
        def invalid(content):
            if content == "one":
                return [{"start_line": None, "end_line": 1, "content": content}]
            return self.build(content)

        from sqlalchemy.exc import IntegrityError
        before = self.state()
        with self.assertRaises(IntegrityError):
            self.backfill(3, session_factory=self.Session, build_passages=invalid)
        self.assertEqual(self.state(), before)
