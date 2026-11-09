"""Maintenance batching and dry-run guarantees without app startup or real DBs."""
import argparse
from contextlib import contextmanager
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import UUID

from app.scripts import backfill_paper_passages as maintenance


class Result:
    def __init__(self, value=None, rows=None, rowcount=0):
        self.value, self.rows, self.rowcount = value, rows or [], rowcount

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value

    def fetchall(self):
        return self.rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, papers=(), missing_vectors=(), read_only=False):
        self.papers = dict(papers)
        self.indexed = set()
        self.vectors = set(missing_vectors)
        self.statements = []
        self.paper_cursors = []
        self.vector_cursors = []
        self.commits = self.rollbacks = self.savepoints = 0
        self.closed = False
        self.read_only = read_only
        self.fail_insert = None
        self.on_paper_scan = None

    @contextmanager
    def begin_nested(self):
        if self.read_only:
            raise AssertionError("savepoint in dry run")
        self.savepoints += 1
        yield

    def execute(self, statement, parameters=None):
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        if self.read_only and not sql.startswith("SELECT "):
            raise AssertionError("mutation in dry run: " + sql)
        eligible = sorted((key, content) for key, content in self.papers.items()
                          if key not in self.indexed and content is not None)
        if sql.startswith("SELECT COUNT(*) FROM papers"):
            return Result(value=len(eligible))
        if sql.startswith("SELECT p.id FROM papers"):
            return Result(value=eligible[-1][0] if eligible else None)
        if sql.startswith("SELECT COUNT(*) FROM paper_passages"):
            return Result(value=len(self.vectors))
        if sql.startswith("SELECT p.id, p.raw_content"):
            self.paper_cursors.append(parameters["after_id"])
            if self.on_paper_scan:
                self.on_paper_scan(self)
            after = parameters["after_id"]
            return Result(rows=[(key, value) for key, value in eligible
                                if (after is None or key > after) and key <= parameters["upper_id"]]
                          [:parameters["limit"]])
        if sql.startswith("INSERT INTO paper_passages"):
            if self.fail_insert:
                raise self.fail_insert
            self.indexed.update(row["paper_id"] for row in parameters)
            return Result(rowcount=len(parameters))
        if sql.startswith("SELECT COALESCE(MAX(id)"):
            return Result(value=max(self.vectors, default=0))
        if sql.startswith("SELECT id FROM paper_passages"):
            self.vector_cursors.append(parameters["after_id"])
            return Result(rows=sorted(key for key in self.vectors
                                     if parameters["after_id"] < key <= parameters["upper_id"])
                          [:parameters["limit"]])
        if sql.startswith("UPDATE paper_passages"):
            changed = {key for key in self.vectors
                       if parameters["after_id"] < key <= parameters["last_id"]}
            self.vectors -= changed
            return Result(rowcount=len(changed))
        raise AssertionError("Unexpected SQL: " + sql)

    def commit(self):
        if self.read_only:
            raise AssertionError("commit in dry run")
        self.commits += 1

    def rollback(self):
        if self.read_only:
            raise AssertionError("explicit rollback in dry run")
        self.rollbacks += 1

    def close(self):
        self.closed = True


def passage(content):
    return [{"start_line": 1, "end_line": 1, "content": content}]


class PassageBackfillTests(TestCase):
    def run_backfill(self, db, *, dry_run=False, builder=passage, batch_size=2):
        return maintenance.backfill(batch_size, dry_run,
                                    session_factory=lambda: db, build_passages=builder)

    def test_dry_run_is_select_only_with_multiple_batches_and_zero_uuid(self):
        db = FakeSession([(UUID(int=i), f"paper {i}") for i in range(5)],
                         missing_vectors=(1, 2, 3), read_only=True)
        report = self.run_backfill(db, dry_run=True)
        self.assertEqual(report["papers_found"], 5)
        self.assertEqual(report["papers_scanned"], 5)
        self.assertEqual(report["papers_planned"], 5)
        self.assertEqual(report["existing_missing_vectors"], 3)
        self.assertEqual(db.paper_cursors, [None, UUID(int=1), UUID(int=3), UUID(int=4)])
        self.assertEqual((db.commits, db.rollbacks, db.savepoints), (0, 0, 0))
        self.assertTrue(db.closed)

    def test_empty_dry_run_reports_missing_vectors_without_writes(self):
        db = FakeSession(missing_vectors=(4, 8), read_only=True)
        report = self.run_backfill(db, dry_run=True)
        self.assertEqual(report["papers_scanned"], 0)
        self.assertEqual(report["existing_missing_vectors"], 2)
        self.assertTrue(all(sql.startswith("SELECT ") for sql in db.statements))
        self.assertEqual(db.commits, 0)

    def test_empty_and_unbuildable_papers_do_not_repeat(self):
        db = FakeSession([(UUID(int=1), "  "), (UUID(int=2), "bad"),
                          (UUID(int=3), "none"), (UUID(int=4), "good")])
        def build(content):
            if content == "bad":
                raise ValueError("cannot build")
            return [] if content == "none" else passage(content)
        with self.assertLogs(maintenance.logger, "ERROR"):
            report = self.run_backfill(db, builder=build, batch_size=1)
        self.assertEqual((report["papers_scanned"], report["papers_skipped"],
                          report["paper_errors"], report["papers_indexed"]), (4, 2, 1, 1))
        self.assertEqual(db.indexed, {UUID(int=4)})
        self.assertEqual(db.commits, 1)
        self.assertFalse(any("ALTER TABLE" in sql for sql in db.statements))

    def test_normal_backfill_repairs_existing_vectors_in_bounded_batches(self):
        db = FakeSession([(UUID(int=1), "one"), (UUID(int=2), "two")],
                         missing_vectors=(1, 2, 3, 4, 5))
        report = self.run_backfill(db)
        self.assertEqual(report["papers_indexed"], 2)
        self.assertEqual(report["vectors_updated"], 5)
        self.assertEqual(db.vector_cursors, [0, 2, 4])
        self.assertEqual(db.vectors, set())
        self.assertFalse(any("TRIGGER" in sql for sql in db.statements))

    def test_insert_failure_rolls_back_and_closes_without_trigger_changes(self):
        db = FakeSession([(UUID(int=1), "one")])
        db.fail_insert = RuntimeError("storage unavailable")
        with self.assertRaisesRegex(RuntimeError, "storage unavailable"):
            self.run_backfill(db)
        self.assertEqual((db.commits, db.rollbacks), (0, 1))
        self.assertTrue(db.closed)
        self.assertFalse(any("TRIGGER" in sql for sql in db.statements))

    def test_keyboard_interrupt_closes_read_only_session(self):
        db = FakeSession([(UUID(int=1), "one")], read_only=True)
        db.on_paper_scan = lambda _: (_ for _ in ()).throw(KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            self.run_backfill(db, dry_run=True)
        self.assertEqual((db.commits, db.rollbacks), (0, 0))
        self.assertTrue(db.closed)

    def test_scan_has_fixed_upper_bound_during_new_imports(self):
        db = FakeSession([(UUID(int=1), "one")], read_only=True)
        db.on_paper_scan = lambda session: session.papers.update({UUID(int=99): "later"})
        report = self.run_backfill(db, dry_run=True, batch_size=1)
        self.assertEqual(report["papers_scanned"], 1)

    def test_batch_size_rejected_before_opening_session(self):
        factory = Mock()
        for size in (0, -1, True, 1.5, "3"):
            with self.subTest(size=size), self.assertRaises(ValueError):
                maintenance.backfill(size, session_factory=factory, build_passages=passage)
        factory.assert_not_called()
        for value in ("0", "-2", "nope"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                maintenance.positive_batch_size(value)
        self.assertEqual(maintenance.positive_batch_size("3"), 3)

    def test_cli_rejects_invalid_size_without_initializing_backfill(self):
        with patch.object(maintenance, "backfill") as run:
            with self.assertRaises(SystemExit) as error:
                maintenance.main(["--batch-size", "0", "--dry-run"])
        self.assertEqual(error.exception.code, 2)
        run.assert_not_called()
