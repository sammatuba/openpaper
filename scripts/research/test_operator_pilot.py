import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import operator_pilot as pilot


class Field:
    def __eq__(self, other):
        return other


class User:
    email = Field()


class AppSession:
    token = Field()

    def __init__(self, **fields):
        self.__dict__.update(fields)


class FakeQuery:
    def __init__(self, db, model):
        self.db, self.model, self.value = db, model, None

    def filter(self, value):
        self.value = value
        return self

    def one_or_none(self):
        return self.db.owner

    def delete(self, **kwargs):
        self.db.deleted.append(self.value)
        return 1


class FakeDB:
    def __init__(self, owner, deleted):
        self.owner, self.deleted, self.added = owner, deleted, []

    def query(self, model):
        return FakeQuery(self, model)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass

    def close(self):
        pass


class Pilot(unittest.TestCase):
    def setUp(self):
        self.owner = SimpleNamespace(email=pilot.OWNER, id="owner", is_active=True, is_email_verified=True, is_blocked=False)
        self.deleted, self.databases = [], []
        self.entry = {"id": "a", "status": "ready", "upload_url": "https://example.test/paper.pdf", "identities": [], "kind": "dossier", "note_status": "pending"}
        self.manifest = {"entries": [self.entry]}
        self.source = Path(tempfile.gettempdir())

    def factory(self):
        db = FakeDB(self.owner, self.deleted)
        self.databases.append(db)
        return db

    def run_pilot(self):
        return pilot.run_pilot(self.manifest, ["a"], Path("unused"), self.source, self.factory, User, AppSession)

    def test_revokes_after_success_and_expiry_is_bounded(self):
        with mock.patch.object(pilot.corpus, "step"):
            self.run_pilot()
        record = self.databases[0].added[0]
        self.assertEqual(self.deleted, [record.token])
        self.assertEqual(record.user_agent, pilot.AGENT)
        seconds = (record.expires_at - pilot.datetime.now(pilot.timezone.utc)).total_seconds()
        self.assertGreater(seconds, 0)
        self.assertLessEqual(seconds, 1800)

    def test_revokes_when_upload_raises(self):
        with mock.patch.object(pilot.corpus, "step", side_effect=RuntimeError("upload failed")), self.assertRaises(RuntimeError):
            self.run_pilot()
        self.assertEqual(self.deleted, [self.databases[0].added[0].token])

    def test_revokes_after_ambiguous_session_commit_failure(self):
        first = self.factory()
        first.commit = mock.Mock(side_effect=RuntimeError("ambiguous commit"))
        with mock.patch.object(pilot.corpus, "step") as step, self.assertRaises(RuntimeError):
            pilot.run_pilot(self.manifest, ["a"], Path("unused"), self.source,
                            mock.Mock(side_effect=[first, self.factory()]), User, AppSession)
        step.assert_not_called()
        self.assertEqual(self.deleted, [first.added[0].token])

    def test_owner_must_be_exact_active_verified_unblocked(self):
        for field, value in (("email", "other@example.com"), ("is_active", False), ("is_email_verified", False), ("is_blocked", True)):
            with self.subTest(field=field):
                original = getattr(self.owner, field)
                setattr(self.owner, field, value)
                with self.assertRaises(ValueError):
                    self.run_pilot()
                setattr(self.owner, field, original)
        self.assertFalse(any(db.added for db in self.databases))
        self.assertEqual(self.deleted, [])

    def test_more_than_three_or_unready_rejected_before_session(self):
        with self.assertRaises(ValueError):
            pilot.run_pilot(self.manifest, ["a", "b", "c", "d"], Path("unused"), self.source, self.factory, User, AppSession)
        self.entry["status"] = "uncertain"
        with self.assertRaises(ValueError):
            self.run_pilot()
        self.assertEqual(self.databases, [])

    def test_cli_requires_explicit_run_flag(self):
        with mock.patch("sys.argv", ["operator_pilot.py", "--id", "a"]), self.assertRaises(SystemExit):
            pilot.main()


if __name__ == "__main__":
    unittest.main()
