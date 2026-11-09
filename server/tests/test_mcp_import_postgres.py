"""Importer acceptance on guarded PostgreSQL; cloud boundaries are substituted."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import httpx
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.google import GoogleProvider
from sqlalchemy import create_engine
from app.database.models import MCPPaperImportRequest, Paper, PaperUploadJob, ProjectPaper, ProjectRole
from app.helpers import pdf_jobs
from app.mcp import research_import, server
from tests import test_mcp_project_postgres as projects

@unittest.skipUnless(os.environ.get("OPENPAPER_ISOLATED_PG_TEST") == "1", "requires isolated /tmp PostgreSQL")
class ImportPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        projects.ProjectPostgresTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        projects.ProjectPostgresTests.tearDownClass.__func__(cls)

    user = projects.ProjectPostgresTests.user
    create = projects.ProjectPostgresTests.create
    setUp = projects.ProjectPostgresTests.setUp

    def fixture(self):
        user = self.user()
        return user, self.create(user)["id"]

    def invoke(self, user, pid, rid, url="https://arxiv.org/abs/2512.16856"):
        with self.Session() as db:
            return asyncio.run(research_import.import_paper_from_url(db,user,pid,rid,url))

    def test_real_pipeline_replay_and_completed_readback(self):
        user, pid = self.fixture()
        rid = str(uuid4())
        with patch.object(research_import,"fetch_research_pdf",new_callable=AsyncMock,return_value=b"fixture") as fetch, patch.object(pdf_jobs.s3_service,"upload_file",new_callable=AsyncMock,return_value=("test/key","https://storage.test/key")), patch.object(pdf_jobs.jobs_client,"submit_pdf_processing_job",return_value="task") as dispatch, patch.object(pdf_jobs,"track_event"):
            first = self.invoke(user,pid,rid)
            self.assertEqual(first["status"],"submitted")
            self.assertEqual(self.invoke(user,pid,rid)["upload_job_id"], first["upload_job_id"])
            self.assertEqual(self.invoke(user,pid,str(uuid4()))["status"],"already_requested")
            self.assertEqual((fetch.await_count,dispatch.call_count),(1,1))
        with self.Session() as db:
            job = db.get(PaperUploadJob,UUID(first["upload_job_id"]))
            job.status = "completed"
            paper = db.query(Paper).filter_by(upload_job_id=job.id).one()
            paper.raw_content, paper.title = "Synthetic extracted evidence", "Fixture paper"
            db.commit()
            status = research_import.get_import_status(db,user,rid)
            self.assertEqual(status["processing_status"],"completed")
            self.assertEqual(status["paper_id"], str(paper.id))
            self.assertEqual(db.query(ProjectPaper).filter_by(project_id=UUID(pid)).count(),1)
        with self.assertRaisesRegex(ValueError,"different import"):
            self.invoke(user,pid,rid,"https://arxiv.org/abs/2502.14143")
        with self.Session() as db, self.assertRaises(ValueError):
            research_import.get_import_status(db,self.user(),rid)

    def test_attachment_admission_counts_url_import_reservations(self):
        from app.mcp import uploads
        user, pid = self.fixture()
        with self.Session() as db:
            db.add(MCPPaperImportRequest(user_id=user.id, request_id=uuid4(),
                   project_id=UUID(pid), source_key='arxiv:2512.16856',
                   source_url='https://arxiv.org/abs/2512.16856', status='reserved'))
            db.commit()
        with patch.object(uploads, 'download_pdf', return_value=b'fixture'), \
             patch.object(uploads, 'validate_pdf_content', new_callable=AsyncMock, return_value=(True, None)), \
             patch.object(research_import, 'get_plan_limits', return_value={research_import.PAPER_UPLOAD_KEY: 1}), \
             patch('app.api.paper_upload_api.upload_raw_file_microservice', new_callable=AsyncMock) as submit:
            with self.Session() as db, self.assertRaisesRegex(PermissionError, 'outstanding imports'):
                asyncio.run(uploads.import_pdf(db, user, 'https://test.invalid', 'https://files.example/file.pdf', pid))
            submit.assert_not_awaited()
        with self.Session() as db:
            self.assertEqual(db.query(PaperUploadJob).filter_by(user_id=user.id).count(), 0)

    def test_attachment_rechecks_permission_after_download(self):
        from app.mcp import uploads
        user, pid = self.fixture()
        def download(_):
            with self.Session() as db:
                db.query(ProjectRole).filter_by(user_id=user.id, project_id=UUID(pid)).update({'role': 'viewer'})
                db.commit()
            return b'fixture'
        with patch.object(uploads, 'download_pdf', side_effect=download), \
             patch.object(uploads, 'validate_pdf_content', new_callable=AsyncMock, return_value=(True, None)), \
             patch('app.api.paper_upload_api.upload_raw_file_microservice', new_callable=AsyncMock) as submit:
            with self.Session() as db, self.assertRaisesRegex(ValueError, 'editor access'):
                asyncio.run(uploads.import_pdf(db, user, 'https://test.invalid', 'https://files.example/file.pdf', pid))
            submit.assert_not_awaited()

    def test_attachment_ambiguous_dispatch_preserves_resources_and_no_retry(self):
        from app.mcp import uploads
        user, pid = self.fixture()
        with patch.object(uploads, 'download_pdf', return_value=b'fixture'), \
             patch.object(uploads, 'validate_pdf_content', new_callable=AsyncMock, return_value=(True, None)), \
             patch.object(pdf_jobs.s3_service, 'upload_file', new_callable=AsyncMock, return_value=('test/key', 'https://storage.test/key')), \
             patch.object(pdf_jobs.s3_service, 'delete_file') as delete, \
             patch.object(pdf_jobs.jobs_client, 'submit_pdf_processing_job', side_effect=TimeoutError('uncertain dispatch')) as dispatch, \
             patch('app.api.paper_upload_api.track_event'):
            with self.Session() as db, self.assertRaisesRegex(RuntimeError, 'requires reconciliation'):
                asyncio.run(uploads.import_pdf(db, user, 'https://test.invalid', 'https://files.example/file.pdf', pid))
            with self.Session() as db:
                replay = asyncio.run(uploads.import_pdf(db, user, 'https://test.invalid', 'https://files.example/file.pdf', pid))
                self.assertTrue(replay['reused'])
                self.assertEqual(replay['status'], 'running')
                self.assertEqual(db.query(Paper).filter_by(user_id=user.id).count(), 1)
                self.assertEqual(db.query(ProjectPaper).filter_by(project_id=UUID(pid)).count(), 1)
            dispatch.assert_called_once()
            delete.assert_not_called()

    def test_pre_dispatch_storage_failure_releases_capacity_for_both_imports(self):
        from app.mcp import uploads
        user, pid = self.fixture()
        with patch.object(uploads, 'download_pdf', return_value=b'fixture'), \
             patch.object(uploads, 'validate_pdf_content', new_callable=AsyncMock, return_value=(True, None)), \
             patch.object(research_import, 'fetch_research_pdf', new_callable=AsyncMock, return_value=b'fixture'), \
             patch.object(pdf_jobs.s3_service, 'upload_file', new_callable=AsyncMock, side_effect=RuntimeError('storage unavailable')):
            with self.Session() as db:
                attachment = asyncio.run(uploads.import_pdf(db, user, 'https://test.invalid', 'https://files.example/file.pdf', pid))
                self.assertEqual(attachment['status'], 'failed')
            result = self.invoke(user, pid, str(uuid4()))
            self.assertEqual(result['status'], 'failed')
            with self.Session() as db:
                self.assertEqual(db.query(Paper).filter_by(user_id=user.id).count(), 0)
                with patch.object(research_import, 'get_plan_limits', return_value={research_import.PAPER_UPLOAD_KEY: 1}):
                    research_import._check_upload_capacity(db, user)

    def test_ambiguous_dispatch_preserves_resources_and_no_retry(self):
        user,pid = self.fixture()
        rid = str(uuid4())
        with patch.object(research_import,"fetch_research_pdf",new_callable=AsyncMock,return_value=b"fixture"), patch.object(pdf_jobs.s3_service,"upload_file",new_callable=AsyncMock,return_value=("test/key","https://storage.test/key")), patch.object(pdf_jobs.s3_service,"delete_file") as delete, patch.object(pdf_jobs.jobs_client,"submit_pdf_processing_job",side_effect=TimeoutError("sensitive diagnostics")) as dispatch, patch.object(pdf_jobs,"track_event"):
            first = self.invoke(user,pid,rid)
            self.assertEqual(first["status"],"needs_reconciliation")
            self.assertNotIn("sensitive",json.dumps(first))
            self.assertEqual(self.invoke(user,pid,rid)["status"],"needs_reconciliation")
            dispatch.assert_called_once()
            delete.assert_not_called()
        with self.Session() as db:
            self.assertEqual(db.query(Paper).filter_by(user_id=user.id).count(),1)
            self.assertEqual(db.query(ProjectPaper).filter_by(project_id=UUID(pid)).count(),1)

    def test_failure_and_revocation_during_download_never_dispatch(self):
        for revoke in (False,True):
            user,pid = self.fixture()
            async def download(_):
                if revoke:
                    with self.Session() as db:
                        db.query(ProjectRole).filter_by(user_id=user.id,project_id=UUID(pid)).update({"role":"viewer"})
                        db.commit()
                    return b"fixture"
                raise ValueError("bad PDF")
            rid = str(uuid4())
            with patch.object(research_import,"fetch_research_pdf",side_effect=download) as fetch, patch.object(pdf_jobs.jobs_client,"submit_pdf_processing_job_with_upload",new_callable=AsyncMock) as submit:
                first = self.invoke(user,pid,rid)
                self.assertEqual(first["status"],"failed")
                if not revoke: self.assertEqual(self.invoke(user,pid,rid)["status"],"failed")
                self.assertEqual(fetch.await_count,1)
                submit.assert_not_awaited()
            with self.Session() as db:
                self.assertEqual(db.query(PaperUploadJob).filter_by(user_id=user.id).count(),0)
                if revoke:
                    with self.assertRaises(PermissionError): research_import.get_import_status(db,user,rid)

    def test_concurrent_canonical_sources_start_one_job(self):
        user,pid = self.fixture()
        async def submit(**kwargs): return "task"
        with patch.object(research_import,"fetch_research_pdf",new_callable=AsyncMock,return_value=b"fixture") as fetch, patch.object(pdf_jobs.jobs_client,"submit_pdf_processing_job_with_upload",side_effect=submit) as dispatch:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _:self.invoke(user,pid,str(uuid4())),range(4)))
            self.assertEqual(sum(r["status"] == "submitted" for r in results),1)
            self.assertEqual((fetch.await_count,dispatch.await_count),(1,1))
        with self.Session() as db:
            self.assertEqual(db.query(MCPPaperImportRequest).filter_by(user_id=user.id).count(),1)
            self.assertEqual(db.query(PaperUploadJob).filter_by(user_id=user.id).count(),1)

    def seed_completed(self,user,count):
        with self.Session() as db:
            db.add_all(Paper(user_id=user.id,file_url="x",status="reading") for _ in range(count))
            db.commit()

    def test_distinct_sources_across_projects_compete_for_last_user_slot(self):
        user,pid=self.fixture()
        other_pid=self.create(user)["id"]
        self.seed_completed(user,9)
        def call(i):
            try:
                return self.invoke(user, pid if i%2 else other_pid, str(uuid4()), f"https://arxiv.org/abs/2512.1685{i}")["status"]
            except PermissionError:
                return "denied"
        with patch.object(research_import,"fetch_research_pdf",new_callable=AsyncMock,return_value=b"fixture") as fetch, patch.object(pdf_jobs.jobs_client,"submit_pdf_processing_job_with_upload",new_callable=AsyncMock,return_value="task") as dispatch:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(call,range(4)))
            self.assertEqual(sorted(results),["denied"]*3+["submitted"])
            self.assertEqual((fetch.await_count,dispatch.await_count),(1,1))
        with self.Session() as db:
            self.assertEqual(db.query(MCPPaperImportRequest).filter_by(user_id=user.id).count(),1)

    def test_reserved_pending_and_ambiguous_capacity_and_completion(self):
        for kind in ("reserved","pending","needs_reconciliation","completed"):
            with self.subTest(kind=kind):
                user,pid=self.fixture()
                self.seed_completed(user,9)
                with self.Session() as db:
                    job=None
                    if kind != "reserved":
                        job=PaperUploadJob(user_id=user.id,status="failed" if kind == "needs_reconciliation" else kind)
                        db.add(job);db.flush()
                    if kind in ("reserved","needs_reconciliation"):
                        db.add(MCPPaperImportRequest(user_id=user.id,request_id=uuid4(),project_id=UUID(pid),source_key="prior",source_url="prior",status=kind,upload_job_id=job.id if job else None))
                    if kind == "completed":
                        db.add(Paper(user_id=user.id,file_url="x",status="reading",upload_job_id=job.id))
                    db.commit()
                with patch.object(research_import,"fetch_research_pdf",new_callable=AsyncMock) as fetch, self.assertRaisesRegex(PermissionError,"outstanding"):
                    self.invoke(user,pid,str(uuid4()))
                fetch.assert_not_awaited()

    def test_confirmed_failure_releases_capacity_but_preserves_request_replay(self):
        from app.database.crud.paper_upload_crud import paper_upload_job_crud
        for state in ("submitted","submitting","needs_reconciliation"):
            with self.subTest(ledger_status=state):
                user,pid=self.fixture()
                self.seed_completed(user,9)
                rid=str(uuid4())
                with self.Session() as db:
                    job=PaperUploadJob(user_id=user.id,status="running")
                    db.add(job);db.flush()
                    db.add(MCPPaperImportRequest(user_id=user.id,request_id=UUID(rid),project_id=UUID(pid),source_key="arxiv:2512.16857",source_url="https://arxiv.org/abs/2512.16857",status=state,upload_job_id=job.id))
                    db.commit()
                    paper_upload_job_crud.mark_as_failed(db,job_id=str(job.id),user=user,error_message="Confirmed processing failure")
                with patch.object(research_import,"fetch_research_pdf",new_callable=AsyncMock,return_value=b"fixture") as fetch, patch.object(pdf_jobs.jobs_client,"submit_pdf_processing_job_with_upload",new_callable=AsyncMock,return_value="task") as dispatch:
                    self.assertEqual(self.invoke(user,pid,str(uuid4()))["status"],"submitted")
                    failed=self.invoke(user,pid,rid,"https://arxiv.org/abs/2512.16857")
                    self.assertEqual(failed["processing_status"],"failed")
                    self.assertTrue(failed["replay"])
                    self.assertEqual((fetch.await_count,dispatch.await_count),(1,1))

    def test_owned_arxiv_identity_is_exact_and_version_aware(self):
        user,pid = self.fixture()
        with self.Session() as db:
            wrong = Paper(user_id=user.id,file_url="x",doi="10.9999/otherarxiv.2512.16856",status="reading")
            right = Paper(user_id=user.id,file_url="x",doi="https://doi.org/10.48550/arXiv.2512.16856v2",status="reading")
            db.add_all([wrong,right]); db.commit()
            self.assertEqual(research_import._owned_arxiv_match(db,user,"arxiv:2512.16856").id,right.id)
            self.assertIsNone(research_import._owned_arxiv_match(db,user,"arxiv:2512.16856v1"))
            expected = str(right.id)
        with patch.object(research_import,"fetch_research_pdf",new_callable=AsyncMock) as fetch:
            result = self.invoke(user,pid,str(uuid4()))
            self.assertEqual((result["status"],result["paper_id"]),("linked_existing",expected))
            fetch.assert_not_awaited()

    def test_migration_upgrade_uniqueness_and_downgrade(self):
        schema="import_migration_"+uuid4().hex
        with self.admin.begin() as conn: conn.execute(self.text("CREATE SCHEMA "+schema))
        engine=create_engine(self.admin.url,connect_args={"options":"-csearch_path="+schema})
        try:
            path=Path(__file__).resolve().parents[1]/"migrations/versions/2026_11_07_1800_mcp_research_import.py"
            spec=importlib.util.spec_from_file_location("import_migration",path)
            migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
            with engine.begin() as conn:
                conn.execute(self.text("CREATE TABLE users (id uuid PRIMARY KEY)"))
                conn.execute(self.text("CREATE TABLE project (id uuid PRIMARY KEY)"))
                with Operations.context(MigrationContext.configure(conn)):
                    migration.upgrade()
                    columns=set(conn.execute(self.text("SELECT column_name FROM information_schema.columns WHERE table_schema=:s AND table_name='mcp_paper_import_requests'"),{"s":schema}).scalars())
                    self.assertEqual(columns,set(MCPPaperImportRequest.__table__.columns.keys()))
                    from sqlalchemy import inspect
                    unique=inspect(conn).get_unique_constraints("mcp_paper_import_requests")
                    self.assertIn(["user_id","project_id","source_key"],[u["column_names"] for u in unique])
                    migration.downgrade()
                    self.assertIsNone(conn.execute(self.text("SELECT to_regclass('mcp_paper_import_requests')")).scalar_one())
        finally:
            engine.dispose()
            with self.admin.begin() as conn: conn.execute(self.text("DROP SCHEMA "+schema+" CASCADE"))

    def test_import_and_status_over_authenticated_mcp(self):
        user,pid=self.fixture()
        rid=str(uuid4())
        async def verify(_self,token):
            return AccessToken(token=token,client_id="test",scopes=["openid","https://www.googleapis.com/auth/userinfo.email"],claims={"email":user.email,"email_verified":True,"aud":"test-client"})
        async def exercise():
            with patch.object(GoogleProvider,"verify_token",verify), patch.object(server,"SessionLocal",self.Session), patch.object(research_import,"fetch_research_pdf",new_callable=AsyncMock,return_value=b"fixture"), patch.object(pdf_jobs.jobs_client,"submit_pdf_processing_job_with_upload",new_callable=AsyncMock,return_value="task"):
                app=server.create_mcp_app()
                async with app.lifespan(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=os.environ["CLIENT_DOMAIN"]) as client:
                    async def rpc(method,params,auth=True):
                        headers={"accept":"application/json, text/event-stream","mcp-protocol-version":"2025-03-26"}
                        if auth: headers["authorization"]="Bearer synthetic"
                        response=await client.post("/api/mcp",headers=headers,json={"jsonrpc":"2.0","id":1,"method":method,"params":params})
                        if not auth: return response
                        self.assertEqual(response.status_code,200)
                        return json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith("data: ")))["result"]
                    self.assertEqual((await rpc("tools/list",{},False)).status_code,401)
                    registry=await rpc("tools/list",{})
                    tools={t["name"]:t for t in registry["tools"]}
                    self.assertEqual(set(tools["import_paper_from_url"]["inputSchema"]["required"]),{"project_id","request_id","url"})
                    self.assertFalse(tools["import_paper_from_url"]["annotations"]["readOnlyHint"])
                    self.assertTrue(tools["get_paper_import_status"]["annotations"]["readOnlyHint"])
                    async def call(name,args):
                        result=await rpc("tools/call",{"name":name,"arguments":args})
                        self.assertFalse(result.get("isError"),result)
                        return json.loads(result["content"][0]["text"])
                    imported=await call("import_paper_from_url",{"project_id":pid,"request_id":rid,"url":"https://arxiv.org/abs/2512.16856"})
                    status=await call("get_paper_import_status",{"request_id":rid})
                    self.assertEqual(status["upload_job_id"],imported["upload_job_id"])
        asyncio.run(exercise())
