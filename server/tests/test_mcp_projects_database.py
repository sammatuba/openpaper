"""Exercise MCP project operations against a real SQLAlchemy session.

The test schema uses only the mapped columns accessed by these operations.
It avoids PostgreSQL-only types and never opens a network connection.
"""
import importlib.util
import sys
import unittest
import uuid
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from sqlalchemy import Column, DateTime, JSON, String, Uuid, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class ProjectRoles(str, Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class Project(Base):
    __tablename__ = "project"
    id = Column(Uuid(as_uuid=True), primary_key=True)
    admin_id = Column(Uuid(as_uuid=True), nullable=False)
    title = Column(String)
    description = Column(String)
    updated_at = Column(DateTime(timezone=True), default=func.now())


class ProjectRole(Base):
    __tablename__ = "project_role"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid(as_uuid=True), nullable=False)
    user_id = Column(Uuid(as_uuid=True), nullable=False)
    role = Column(String, nullable=False)


class Paper(Base):
    __tablename__ = "paper"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), nullable=False)
    title = Column(String)
    authors = Column(JSON)
    abstract = Column(String)
    created_at = Column(DateTime(timezone=True), default=func.now())


class ProjectPaper(Base):
    __tablename__ = "project_paper"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid(as_uuid=True), nullable=False)
    paper_id = Column(Uuid(as_uuid=True), nullable=False)


class MCPProjectRequest(Base):
    __tablename__ = "mcp_project_requests"
    user_id = Column(Uuid(as_uuid=True), primary_key=True)
    request_id = Column(Uuid(as_uuid=True), primary_key=True)
    project_id = Column(Uuid(as_uuid=True), nullable=False)
    payload_hash = Column(String(64), nullable=False)


quotas = {"project": True, "papers": True}


def mock_project_quota(db, user):
    return quotas["project"], "Project quota exceeded"


def mock_paper_quota(db, user, project_id, paper_count):
    return quotas["papers"], "Paper quota exceeded"


def load_service():
    models = ModuleType("app.database.models")
    for name in ("Paper", "Project", "ProjectPaper", "ProjectRole", "ProjectRoles", "MCPProjectRequest"):
        setattr(models, name, globals()[name])
    limits = ModuleType("app.helpers.subscription_limits")
    limits.can_user_create_project = mock_project_quota
    limits.can_user_add_papers_to_project = mock_paper_quota
    admissions = ModuleType("app.helpers.project_admission")
    admissions.lock_project_admissions = lambda db, user: None
    stub_modules = {
        "app": ModuleType("app"),
        "app.database": ModuleType("app.database"),
        "app.database.models": models,
        "app.helpers": ModuleType("app.helpers"),
        "app.helpers.subscription_limits": limits,
        "app.helpers.project_admission": admissions,
    }
    with patch.dict(sys.modules, stub_modules):
        path = Path(__file__).resolve().parents[1] / "app" / "mcp" / "project_tools.py"
        spec = importlib.util.spec_from_file_location("mcp_project_tools_under_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


service = load_service()
ORIGIN = "https://papers.example.test"


class TestMCPProjectsDatabase(unittest.TestCase):
    def setUp(self):
        quotas.update({"project": True, "papers": True})
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.admin = SimpleNamespace(id=uuid.uuid4())
        self.editor = SimpleNamespace(id=uuid.uuid4())
        self.viewer = SimpleNamespace(id=uuid.uuid4())
        self.outsider = SimpleNamespace(id=uuid.uuid4())

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def make_project(self):
        result = service.create_project(
            self.db, self.admin, "Paper Review", str(uuid.uuid4()), "original", ORIGIN
        )
        pid = uuid.UUID(result["id"])
        self.db.add(ProjectRole(project_id=pid, user_id=self.editor.id, role=ProjectRoles.EDITOR))
        self.db.add(ProjectRole(project_id=pid, user_id=self.viewer.id, role=ProjectRoles.VIEWER))
        self.db.commit()
        return pid

    def make_paper(self, user):
        paper = Paper(
            user_id=user.id, title="Example", authors=["Author"], abstract="Synthetic evidence"
        )
        self.db.add(paper)
        self.db.commit()
        return paper.id

    def test_create_is_atomic_and_idempotent(self):
        request_id = str(uuid.uuid4())
        first = service.create_project(self.db, self.admin, "New", request_id, "Description", ORIGIN)
        second = service.create_project(self.db, self.admin, "New", request_id, "Description", ORIGIN)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["status"], "created")
        self.assertEqual(second["status"], "already_created")
        self.assertEqual(self.db.query(Project).count(), 1)
        role = self.db.query(ProjectRole).one()
        self.assertEqual(role.user_id, self.admin.id)
        self.assertEqual(role.role, ProjectRoles.ADMIN)
        with self.assertRaisesRegex(ValueError, "Request ID already used"):
            service.create_project(self.db, self.admin, "Different", request_id, "Description", ORIGIN)

    def test_creation_validates_quota_and_arguments(self):
        with self.assertRaises(ValueError):
            service.create_project(self.db, self.admin, "  ", str(uuid.uuid4()), None, ORIGIN)
        with self.assertRaises(ValueError):
            service.create_project(self.db, self.admin, "Test", "not-uuid", None, ORIGIN)
        quotas["project"] = False
        with self.assertRaises(PermissionError):
            service.create_project(self.db, self.admin, "Test", str(uuid.uuid4()), None, ORIGIN)
        self.assertEqual(self.db.query(Project).count(), 0)

    def test_replay_survives_rename_and_rejects_deleted_project(self):
        request_id = str(uuid.uuid4())
        first = service.create_project(self.db, self.admin, "Original", request_id, None, ORIGIN)
        service.update_project(self.db, self.admin, first["id"], ORIGIN, title="Renamed", description="New")
        quotas["project"] = False
        replay = service.create_project(self.db, self.admin, "Original", request_id, None, ORIGIN)
        self.assertEqual(replay["id"], first["id"])
        self.assertEqual(replay["title"], "Renamed")
        self.db.query(ProjectRole).delete()
        self.db.query(Project).delete()
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "was deleted"):
            service.create_project(self.db, self.admin, "Original", request_id, None, ORIGIN)
        self.assertEqual(self.db.query(MCPProjectRequest).count(), 1)
        self.assertEqual(self.db.query(Project).count(), 0)

    def test_admin_can_update_and_others_cannot(self):
        pid = self.make_project()
        result = service.update_project(self.db, self.admin, str(pid), ORIGIN,
                                        title="Renamed", clear_description=True)
        self.assertEqual(result["title"], "Renamed")
        self.assertIsNone(result["description"])
        for user in (self.editor, self.viewer):
            with self.assertRaises(PermissionError):
                service.update_project(self.db, user, str(pid), ORIGIN, title="No")
        with self.assertRaises(ValueError):
            service.update_project(self.db, self.outsider, str(pid), ORIGIN, title="No")

    def test_editor_add_remove_and_paper_ownership(self):
        pid = self.make_project()
        paper_id = self.make_paper(self.editor)
        first = service.add_paper_to_project(self.db, self.editor, str(pid), str(paper_id))
        second = service.add_paper_to_project(self.db, self.editor, str(pid), str(paper_id))
        self.assertEqual(first["status"], "added")
        self.assertEqual(second["status"], "already_present")
        self.assertEqual(self.db.query(ProjectPaper).count(), 1)
        with self.assertRaises(ValueError):
            service.add_paper_to_project(self.db, self.admin, str(pid), str(paper_id))
        with self.assertRaises(PermissionError):
            service.remove_paper_from_project(self.db, self.viewer, str(pid), str(paper_id))
        self.assertEqual(
            service.remove_paper_from_project(self.db, self.editor, str(pid), str(paper_id))["status"],
            "removed",
        )
        self.assertEqual(
            service.remove_paper_from_project(self.db, self.editor, str(pid), str(paper_id))["status"],
            "not_present",
        )
        self.assertEqual(self.db.query(Paper).count(), 1)  # Unlink never deletes the source.

    def test_paper_quota_and_viewer_restrictions(self):
        pid = self.make_project()
        paper_id = self.make_paper(self.editor)
        quotas["papers"] = False
        with self.assertRaises(PermissionError):
            service.add_paper_to_project(self.db, self.editor, str(pid), str(paper_id))
        quotas["papers"] = True
        with self.assertRaises(PermissionError):
            service.add_paper_to_project(self.db, self.viewer, str(pid), str(paper_id))
        self.assertEqual(self.db.query(ProjectPaper).count(), 0)

    def test_paginated_project_list_is_members_only(self):
        pid = self.make_project()
        p1 = self.make_paper(self.admin)
        p2 = self.make_paper(self.admin)
        service.add_paper_to_project(self.db, self.admin, str(pid), str(p1))
        service.add_paper_to_project(self.db, self.admin, str(pid), str(p2))
        first = service.list_project_papers(self.db, self.viewer, str(pid), ORIGIN, limit=1)
        self.assertEqual(len(first["papers"]), 1)
        self.assertEqual(first["next_offset"], 1)
        self.assertFalse(first["papers"][0]["is_owner"])
        second = service.list_project_papers(
            self.db, self.viewer, str(pid), ORIGIN, offset=1, limit=1
        )
        self.assertEqual(len(second["papers"]), 1)
        self.assertIsNone(second["next_offset"])
        with self.assertRaises(ValueError):
            service.list_project_papers(self.db, self.outsider, str(pid), ORIGIN)
        with self.assertRaises(ValueError):
            service.list_project_papers(self.db, self.viewer, str(pid), ORIGIN, limit=101)


if __name__ == "__main__":
    unittest.main()
