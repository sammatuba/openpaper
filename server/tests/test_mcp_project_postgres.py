"""Real models, quota gates and MCP transport on guarded disposable PostgreSQL.

Google verification is synthetic; credentials and production data are never used.
"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BrokenBarrierError
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock
from uuid import uuid4, UUID

import httpx
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.google import GoogleProvider
from sqlalchemy import event, create_engine
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.database.models import (
    Annotation, Highlight, MCPProjectRequest, Paper, PaperNote, Project,
    ProjectPaper, ProjectRole, ProjectRoleInvitation, Subscription,
)
from app.helpers import subscription_limits as limits
from app.mcp import server, project_tools
from tests import test_mcp_postgres as baseline


@unittest.skipUnless(os.environ.get("OPENPAPER_ISOLATED_PG_TEST") == "1", "requires isolated /tmp PostgreSQL")
class ProjectPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        baseline.MCPPostgresTests.setUpClass.__func__(cls)
        try:
            with cls.engine.begin() as conn:
                for model in (Project, ProjectRole, ProjectPaper, MCPProjectRequest,
                              ProjectRoleInvitation, Subscription, Highlight, Annotation):
                    model.__table__.create(conn, checkfirst=True)
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        baseline.MCPPostgresTests.tearDownClass.__func__(cls)

    def setUp(self):
        environment = patch.dict(os.environ, {"SELF_HOSTED_PLAN":"basic", "ALLOWED_EMAILS":""})
        environment.start()
        self.addCleanup(environment.stop)

    def user(self):
        uid = uuid4()
        with self.engine.begin() as conn:
            conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:id,:email,'google',:provider,true,false,true)"),
                         dict(id=uid, email=str(uid)+"@test", provider=str(uid)))
        return SimpleNamespace(id=uid, email=str(uid)+"@test")

    def create(self, user, request=None, title="Test", description=None):
        with self.Session() as db:
            return project_tools.create_project(db, user, title, request or str(uuid4()), description, "https://papers.example.workers.dev")

    def paper_fixture(self, count=0):
        user = self.user()
        pid = UUID(self.create(user)["id"])
        papers = [uuid4() for _ in range(count + 2)]
        with self.Session() as db:
            db.add_all(Paper(id=p, user_id=user.id, file_url="x", status="reading") for p in papers)
            db.flush()
            db.add_all(ProjectPaper(project_id=pid, paper_id=p) for p in papers[:count])
            db.commit()
        return user, pid, papers[-2:]

    def test_mcp_description_update_invalidates_stale_brief(self):
        from tests.test_project_research_brief import document
        user = self.user()
        pid = UUID(self.create(user, description='Original')['id'])
        with self.Session() as db:
            row = db.get(Project, pid)
            row.research_brief = document()
            db.commit()
            project_tools.update_project(db, user, str(pid), 'https://example.test', title='Renamed')
            self.assertEqual(db.get(Project, pid).research_brief, document())
            project_tools.update_project(db, user, str(pid), 'https://example.test', description='Changed')
            self.assertIsNone(db.get(Project, pid).research_brief)

    def test_browser_mcp_paper_races_and_duplicate_replay(self):
        from app.api.projects import project_papers_api as api
        for same_paper in (False, True):
            with self.subTest(same_paper=same_paper):
                user, pid, papers = self.paper_fixture(count=49)  # Basic cap is 50.
                start, counted = Barrier(2), Barrier(2)
                actual_quota = limits.can_user_add_papers_to_project
                def quota(*args, **kwargs):
                    result = actual_quota(*args, **kwargs)
                    if result[0]:
                        try:
                            counted.wait(timeout=0.3)
                        except BrokenBarrierError:
                            pass
                    return result
                def call(kind):
                    start.wait(timeout=10)
                    with self.Session() as db:
                        if kind == "browser":
                            paper = papers[0] if same_paper else papers[1]
                            response = asyncio.run(api.add_paper_to_project(str(pid), api.AddPaperToProjectRequest(paper_ids=[str(paper)]), db, user))
                            self.assertIn(response.status_code, (201,403))
                            return response.status_code
                        try:
                            project_tools.add_paper_to_project(db, user, str(pid), str(papers[0]))
                            return 201
                        except PermissionError:
                            return 403
                with patch.object(limits,"can_user_add_papers_to_project",quota), patch.object(project_tools,"can_user_add_papers_to_project",quota), patch.object(api,"can_user_add_papers_to_project",quota):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        results = list(pool.map(call,("mcp","browser")))
                self.assertEqual(sorted(results), [201,201] if same_paper else [201,403])
                with self.Session() as db:
                    self.assertEqual(db.query(ProjectPaper).filter_by(project_id=pid).count(),50)
                    linked = db.query(ProjectPaper).filter_by(project_id=pid).filter(ProjectPaper.paper_id.in_(papers)).one()
                    # Duplicate input and retries consume no slots at the cap.
                    request = api.AddPaperToProjectRequest(paper_ids=[str(linked.paper_id)] * 2)
                    self.assertEqual(asyncio.run(api.add_paper_to_project(str(pid),request,db,user)).status_code,201)

    def test_browser_batch_quota_and_caller_transaction(self):
        from app.api.projects import project_papers_api as api
        from app.database.crud.projects.project_paper_crud import project_paper_crud, ProjectPaperCreate
        user, pid, papers = self.paper_fixture(count=49)
        with self.Session() as db:
            request = api.AddPaperToProjectRequest(paper_ids=[str(p) for p in papers])
            self.assertEqual(asyncio.run(api.add_paper_to_project(str(pid),request,db,user)).status_code,403)
        with self.Session() as db:
            self.assertIsNotNone(project_paper_crud.create(db,obj_in=ProjectPaperCreate(paper_id=papers[0]),user=user,project_id=pid,auto_commit=False))
            db.rollback()
        with self.Session() as db:
            self.assertEqual(db.query(ProjectPaper).filter_by(project_id=pid).count(),49)
        # A failure later in a batch must roll back the earlier successful item.
        user, pid, papers = self.paper_fixture()
        with self.Session() as db:
            request = api.AddPaperToProjectRequest(paper_ids=[str(papers[0]),str(uuid4())])
            self.assertEqual(asyncio.run(api.add_paper_to_project(str(pid),request,db,user)).status_code,400)
        with self.Session() as db:
            self.assertEqual(db.query(ProjectPaper).filter_by(project_id=pid).count(),0)
            self.assertEqual(db.query(Paper).filter(Paper.id.in_(papers)).count(),2)

    def test_replay_after_edits_deletion_quota_and_cross_user_uuid(self):
        user, request = self.user(), str(uuid4())
        first = self.create(user, request, " Original ")
        with self.Session() as db:
            project_tools.update_project(db, user, first["id"], "https://example.test", title="Renamed", description="New")
        self.create(user)  # Exhaust the basic quota; replay must still work.
        replay = self.create(user, request, "Original")
        self.assertEqual((replay["id"], replay["title"], replay["status"]), (first["id"], "Renamed", "already_created"))
        with self.assertRaisesRegex(ValueError, "Request ID already used"):
            self.create(user, request, "Different")
        self.assertNotEqual(self.create(self.user(), request, "Original")["id"], first["id"])
        with self.engine.begin() as conn:
            conn.execute(self.text("DELETE FROM project WHERE id=:id"), {"id":first["id"]})
        with self.assertRaisesRegex(ValueError, "was deleted"):
            self.create(user, request, "Original")
        with self.Session() as db:
            self.assertEqual(db.query(MCPProjectRequest).filter_by(user_id=user.id).count(), 2)

    def test_concurrent_same_request_creates_one_project(self):
        user, request, start = self.user(), str(uuid4()), Barrier(4)
        def call(_):
            start.wait(timeout=10)
            return self.create(user, request)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(call, range(4)))
        self.assertEqual(len({r["id"] for r in results}), 1)
        self.assertEqual(sorted(r["status"] for r in results), ["already_created"] * 3 + ["created"])
        with self.Session() as db:
            for model, field in ((Project,"admin_id"), (ProjectRole,"user_id"), (MCPProjectRequest,"user_id")):
                self.assertEqual(db.query(model).filter_by(**{field:user.id}).count(), 1)

    def test_competing_admissions_respect_last_slot(self):
        from app.database.crud.projects.project_crud import project_crud, ProjectCreate
        from app.database.crud.projects.project_role_invitation_crud import project_role_invitation_crud
        for mode in ("mcp", "browser", "invitation"):
            with self.subTest(mode=mode):
                user, invitation_id = self.user(), str(uuid4())
                self.create(user)
                if mode == "invitation":
                    owner = self.user()
                    pid = self.create(owner)["id"]
                    with self.Session() as db:
                        db.add(ProjectRoleInvitation(id=UUID(invitation_id), project_id=UUID(pid), email=user.email, invited_by=owner.id, role="viewer"))
                        db.commit()
                start, counted = Barrier(2), Barrier(2)
                actual_quota = limits.can_user_create_project
                def quota(db, actor):
                    result = actual_quota(db, actor)
                    if result[0]:
                        # Without serialization both counts pass before inserts.
                        # With the lock only the first reaches this rendezvous.
                        try:
                            counted.wait(timeout=0.3)
                        except BrokenBarrierError:
                            pass
                    return result
                def call(kind):
                    start.wait(timeout=10)
                    try:
                        with self.Session() as db:
                            if kind == "browser":
                                self.assertIsNotNone(project_crud.create(db, obj_in=ProjectCreate(title="Browser"), user=user))
                            elif kind == "invitation":
                                self.assertIsNotNone(project_role_invitation_crud.accept_invitation(db, invitation_id=invitation_id, user=user))
                            else:
                                project_tools.create_project(db, user, "MCP", str(uuid4()), None, "https://example.test")
                        return "admitted"
                    except PermissionError:
                        return "denied"
                with patch.object(limits, "can_user_create_project", quota), patch.object(project_tools, "can_user_create_project", quota):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        results = list(pool.map(call, ("mcp", mode)))
                self.assertEqual(sorted(results), ["admitted", "denied"])
                with self.Session() as db:
                    self.assertEqual(db.query(ProjectRole).filter_by(user_id=user.id).count(), 2)

    def test_failed_creation_rolls_back_project_membership_and_request(self):
        from app.database.crud.projects.project_crud import project_crud, ProjectCreate
        user, request = self.user(), str(uuid4())
        def fail_membership(_mapper, _connection, _target):
            raise RuntimeError("synthetic membership failure")
        event.listen(ProjectRole, "before_insert", fail_membership)
        try:
            with self.Session() as db:
                with self.assertRaisesRegex(RuntimeError, "synthetic"):
                    project_tools.create_project(db, user, "Test", request, None, "https://example.test")
                db.rollback()
            with self.Session() as db:
                self.assertIsNone(project_crud.create(db, obj_in=ProjectCreate(title="Test"), user=user))
        finally:
            event.remove(ProjectRole, "before_insert", fail_membership)
        with self.Session() as db:
            for model, field in ((Project,"admin_id"), (ProjectRole,"user_id"), (MCPProjectRequest,"user_id")):
                self.assertEqual(db.query(model).filter_by(**{field:user.id}).count(), 0)
        self.assertEqual(self.create(user, request)["status"], "created")

    def test_quota_query_failure_is_not_treated_as_capacity(self):
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.scalar.side_effect = RuntimeError("count failed")
        with self.assertRaisesRegex(RuntimeError, "count failed"):
            limits.can_user_create_project(db, self.user())

    def test_migration_matches_mapping(self):
        schema = "project_migration_" + uuid4().hex
        with self.admin.begin() as conn:
            conn.execute(self.text("CREATE SCHEMA " + schema))
        engine = create_engine(self.admin.url, connect_args={"options":"-csearch_path=" + schema})
        try:
            path = Path(__file__).resolve().parents[1] / "migrations/versions/2026_11_07_1200_mcp_project_requests.py"
            spec = importlib.util.spec_from_file_location("project_request_migration", path)
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            with engine.begin() as conn:
                conn.execute(self.text("CREATE TABLE users (id uuid PRIMARY KEY)"))
                conn.execute(self.text("CREATE TABLE project_paper (id uuid PRIMARY KEY, project_id uuid NOT NULL, paper_id uuid NOT NULL)"))
                pid, paper = uuid4(), uuid4()
                conn.execute(self.text("INSERT INTO project_paper (id,project_id,paper_id) VALUES (:a,:pid,:paper),(:b,:pid,:paper)"), {"a":uuid4(),"b":uuid4(),"pid":pid,"paper":paper})
                with Operations.context(MigrationContext.configure(conn)):
                    migration.upgrade()
                    self.assertEqual(conn.execute(self.text("SELECT count(*) FROM project_paper")).scalar_one(),1)
                    # A future insert cannot reintroduce identical associations.
                    with conn.begin_nested() as savepoint:
                        from sqlalchemy.exc import IntegrityError
                        with self.assertRaises(IntegrityError):
                            conn.execute(self.text("INSERT INTO project_paper (id,project_id,paper_id) VALUES (:id,:pid,:paper)"), {"id":uuid4(),"pid":pid,"paper":paper})
                        savepoint.rollback()
                    columns = set(conn.execute(self.text("SELECT column_name FROM information_schema.columns WHERE table_schema=:s AND table_name='mcp_project_requests'"), {"s":schema}).scalars())
                    self.assertEqual(columns, set(MCPProjectRequest.__table__.columns.keys()))
                    migration.downgrade()
                    self.assertIsNone(conn.execute(self.text("SELECT to_regclass('mcp_project_requests')")).scalar_one())
        finally:
            engine.dispose()
            with self.admin.begin() as conn:
                conn.execute(self.text("DROP SCHEMA " + schema + " CASCADE"))

    def test_project_roles_over_mcp(self):
        actors = {name:self.user() for name in ("admin","editor","viewer","outsider","blocked","inactive","disallowed")}
        with self.engine.begin() as conn:
            conn.execute(self.text("UPDATE users SET is_blocked=true WHERE id=:id"), {"id":actors["blocked"].id})
            conn.execute(self.text("UPDATE users SET is_active=false WHERE id=:id"), {"id":actors["inactive"].id})
        paper, note = uuid4(), uuid4()
        with self.engine.begin() as conn:
            conn.execute(self.text("INSERT INTO papers (id,user_id,file_url,status,title) VALUES (:p,:u,'x','reading','Synthetic evidence')"), {"p":paper,"u":actors["editor"].id})
            conn.execute(self.text("INSERT INTO paper_notes (id,paper_id,user_id,content) VALUES (:n,:p,:u,'Preserve note')"), {"n":note,"p":paper,"u":actors["editor"].id})
        highlight, annotation = uuid4(), uuid4()
        with self.Session() as db:
            db.add(Highlight(id=highlight,paper_id=paper,user_id=actors["editor"].id,raw_text="Synthetic evidence"))
            db.flush()
            db.add(Annotation(id=annotation,highlight_id=highlight,paper_id=paper,user_id=actors["editor"].id,content="Preserve annotation"))
            db.commit()
        async def verify(_self, token):
            if token == "invalid":
                return None
            actor = actors.get(token, actors["admin"])
            return AccessToken(token=token, client_id="test", scopes=["openid","https://www.googleapis.com/auth/userinfo.email"],
                               claims={"email":actor.email,"email_verified":token != "unverified","aud":"wrong" if token == "wrong-audience" else "test-client"})
        async def exercise():
            settings = {"CLIENT_DOMAIN":"https://papers.example.workers.dev","GOOGLE_CLIENT_ID":"test-client","GOOGLE_CLIENT_SECRET":"test-secret",
                        "MCP_JWT_SIGNING_KEY":"testing-signing-key-with-32-characters","MCP_STORAGE_ENCRYPTION_KEY":"MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
                        "ALLOWED_EMAILS":",".join(a.email for n,a in actors.items() if n != "disallowed")}
            with patch.dict(os.environ,settings), patch.object(GoogleProvider,"verify_token",verify), patch.object(server,"SessionLocal",self.Session):
                app = server.create_mcp_app()
                async with app.lifespan(app):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=settings["CLIENT_DOMAIN"]) as client:
                        async def rpc(actor, method, params):
                            headers = {"accept":"application/json, text/event-stream","mcp-protocol-version":"2025-03-26"}
                            if actor is not None:
                                headers["authorization"] = "Bearer " + actor
                            return await client.post("/api/mcp", headers=headers, json={"jsonrpc":"2.0","id":1,"method":method,"params":params})
                        def result(response):
                            self.assertEqual(response.status_code,200)
                            return json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith("data: ")))["result"]
                        async def call(actor, name, args):
                            return result(await rpc(actor,"tools/call",{"name":name,"arguments":args}))
                        def value(reply):
                            return json.loads(reply["content"][0]["text"])
                        for actor in (None,"invalid"):
                            self.assertEqual((await rpc(actor,"tools/list",{})).status_code,401)
                        tools = result(await rpc("admin","tools/list",{}))["tools"]
                        self.assertTrue(next(t for t in tools if t["name"] == "remove_paper_from_project")["annotations"]["destructiveHint"])
                        self.assertTrue(next(t for t in tools if t["name"] == "update_project")["annotations"]["destructiveHint"])
                        request = {"title":"Transport test","request_id":str(uuid4())}
                        for token in ("blocked","inactive","disallowed","unverified","wrong-audience"):
                            self.assertTrue((await call(token,"create_project",request)).get("isError"),token)
                        first = value(await call("admin","create_project",request))
                        replay = value(await call("admin","create_project",request))
                        self.assertEqual((replay["id"],replay["status"]),(first["id"],"already_created"))
                        pid = UUID(first["id"])
                        with self.Session() as db:
                            for name in ("editor","viewer"):
                                db.add(ProjectRole(project_id=pid,user_id=actors[name].id,role=name))
                            db.commit()
                        args = {"project_id":str(pid),"paper_id":str(paper)}
                        for name in ("admin","viewer","outsider"):
                            self.assertTrue((await call(name,"add_paper_to_project",args)).get("isError"))
                        self.assertEqual(value(await call("editor","add_paper_to_project",args))["status"],"added")
                        self.assertEqual(value(await call("editor","add_paper_to_project",args))["status"],"already_present")
                        self.assertFalse((await call("viewer","list_project_papers",{"project_id":str(pid)})).get("isError",False))
                        self.assertTrue((await call("outsider","list_project_papers",{"project_id":str(pid)})).get("isError"))
                        for name in ("editor","viewer","outsider"):
                            self.assertTrue((await call(name,"update_project",{"project_id":str(pid),"title":"No"})).get("isError"))
                        self.assertFalse((await call("admin","update_project",{"project_id":str(pid),"title":"Yes"})).get("isError",False))
                        self.assertEqual(value(await call("admin","create_project",request))["title"],"Yes")
                        cleared = value(await call("admin","update_project",{"project_id":str(pid),"description":"Temporary"}))
                        self.assertEqual(cleared["description"],"Temporary")
                        cleared = value(await call("admin","update_project",{"project_id":str(pid),"clear_description":True}))
                        self.assertIsNone(cleared["description"])
                        for name in ("viewer","outsider"):
                            self.assertTrue((await call(name,"remove_paper_from_project",args)).get("isError"))
                        self.assertEqual(value(await call("editor","remove_paper_from_project",args))["status"],"removed")
                        self.assertEqual(value(await call("editor","remove_paper_from_project",args))["status"],"not_present")
        asyncio.run(exercise())
        with self.Session() as db:
            self.assertIsNotNone(db.get(Paper,paper))
            self.assertEqual(db.get(PaperNote,note).content,"Preserve note")
            self.assertEqual(db.get(Annotation,annotation).content,"Preserve annotation")
