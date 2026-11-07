"""Focused MCP project CRUD checks: access rules, validation, and replay safety."""
import uuid
import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.database.models import ProjectRoles
from app.mcp import project_tools as ops


class TestProjectTools(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.user = SimpleNamespace(id=uuid.uuid4())
        self.pid = str(uuid.uuid4())
        self.paper_id = str(uuid.uuid4())

    def test_input_validation(self):
        with self.assertRaises(ValueError):
            ops._title("  ")
        with self.assertRaises(ValueError):
            ops._description("x" * 10001)
        with self.assertRaises(ValueError):
            ops._uuid("not-a-uuid", "project_id")
        with self.assertRaises(ValueError):
            ops.list_project_papers(self.db, self.user, self.pid, "https://example.org", -1, 50)
        with self.assertRaises(ValueError):
            ops.list_project_papers(self.db, self.user, self.pid, "https://example.org", 0, 101)

    def test_create_replay_does_not_consume_quota(self):
        existing = SimpleNamespace(
            id=uuid.uuid4(), admin_id=self.user.id, title="MEOS SwarmLab", description="research"
        )
        request = SimpleNamespace(project_id=existing.id, payload_hash=hashlib.sha256(
            b'{"description":"research","title":"MEOS SwarmLab"}'
        ).hexdigest())
        self.db.query.return_value.filter.return_value.one_or_none.side_effect = [request, existing]
        with patch.object(ops, "can_user_create_project") as quota:
            result = ops.create_project(self.db, self.user, "MEOS SwarmLab",
                                        str(uuid.uuid4()), "research", "https://example.org")
            self.assertEqual(result["status"], "already_created")
            quota.assert_not_called()
            self.db.commit.assert_not_called()

    def test_create_replay_rejects_mutated_request(self):
        existing = SimpleNamespace(payload_hash="different-payload")
        self.db.query.return_value.filter.return_value.one_or_none.return_value = existing
        with self.assertRaisesRegex(ValueError, "Request ID already used"):
            ops.create_project(self.db, self.user, "MEOS SwarmLab",
                               str(uuid.uuid4()), None, "https://example.org")

    def test_create_quota_is_enforced(self):
        self.db.query.return_value.filter.return_value.one_or_none.return_value = None
        with patch.object(ops, "can_user_create_project", return_value=(False, "limit")):
            with self.assertRaises(PermissionError):
                ops.create_project(self.db, self.user, "MEOS SwarmLab",
                                   str(uuid.uuid4()), None, "https://example.org")
        self.db.commit.assert_not_called()

    def test_viewer_cannot_modify_project(self):
        role = SimpleNamespace(role=ProjectRoles.VIEWER)
        self.db.query.return_value.filter.return_value.one_or_none.return_value = role
        with self.assertRaises(PermissionError):
            ops.remove_paper_from_project(self.db, self.user, self.pid, self.paper_id)
        self.db.delete.assert_not_called()
        self.db.commit.assert_not_called()

    def test_non_member_cannot_list_papers(self):
        self.db.query.return_value.filter.return_value.one_or_none.return_value = None
        with self.assertRaisesRegex(ValueError, "not accessible"):
            ops.list_project_papers(self.db, self.user, self.pid, "https://example.org")
        self.db.commit.assert_not_called()

    def test_paper_is_not_removed_from_library(self):
        role = SimpleNamespace(role=ProjectRoles.EDITOR)
        project = SimpleNamespace(id=uuid.UUID(self.pid), updated_at=None)
        link = SimpleNamespace(paper_id=uuid.UUID(self.paper_id))
        # Return a role for the membership query, then a project row with lock,
        # then the project-paper association.
        first = MagicMock()
        first.filter.return_value.one_or_none.return_value = role
        second = MagicMock()
        second.filter.return_value.with_for_update.return_value.one_or_none.return_value = project
        third = MagicMock()
        third.filter.return_value.one_or_none.return_value = link
        self.db.query.side_effect = [first, second, third]
        result = ops.remove_paper_from_project(self.db, self.user, self.pid, self.paper_id)
        self.assertEqual(result["status"], "removed")
        self.db.delete.assert_called_once_with(link)
        self.db.commit.assert_called_once()

    def test_update_requires_admin(self):
        role = SimpleNamespace(role=ProjectRoles.EDITOR)
        self.db.query.return_value.filter.return_value.one_or_none.return_value = role
        with self.assertRaises(PermissionError):
            ops.update_project(self.db, self.user, self.pid, "https://example.org", title="Renamed")
        self.db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
