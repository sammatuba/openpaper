"""MCP note transactions on the dedicated socket-only test PostgreSQL cluster."""
import getpass
import os
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4


@unittest.skipUnless(os.environ.get("OPENPAPER_ISOLATED_PG_TEST") == "1", "requires isolated /tmp PostgreSQL")
class MCPPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import URL
        from sqlalchemy.orm import sessionmaker
        from app.database.models import Paper, PaperNote, User
        from app.mcp.notes import append_note
        if os.getcwd() != "/tmp" or os.environ.get("PYTHON_DOTENV_DISABLED") != "1" or os.environ.get("DATABASE_URL") != f"postgresql://{getpass.getuser()}@/postgres?host=/tmp&port=55439":
            raise RuntimeError("Refusing non-isolated database")
        cls.text, cls.PaperNote, cls.append = staticmethod(text), PaperNote, staticmethod(append_note)
        url = URL.create("postgresql+psycopg2", username=getpass.getuser(), database="postgres", query={"host": "/tmp", "port": "55439"})
        cls.admin = create_engine(url)
        with cls.admin.connect() as conn:
            if conn.execute(text("SHOW data_directory")).scalar_one() != "/tmp/openpaper-pg-transaction-test" or conn.execute(text("SHOW listen_addresses")).scalar_one():
                raise RuntimeError("Not isolated PostgreSQL")
        cls.schema = "mcp_test_" + uuid4().hex
        with cls.admin.begin() as conn:
            conn.execute(text("CREATE SCHEMA " + cls.schema))
        cls.engine = create_engine(url, connect_args={"options": "-csearch_path=" + cls.schema})
        try:
            with cls.engine.begin() as conn:
                User.__table__.create(conn)
                from app.database.models import PaperUploadJob
                PaperUploadJob.__table__.create(conn)
                Paper.__table__.create(conn)
                PaperNote.__table__.create(conn)
                from app.database.models import Project, ProjectRole, ProjectPaper, Highlight, Annotation, PaperPassage, Subscription, MCPPaperImportRequest, ResearchProject
                for model in (Project, ProjectRole, ProjectPaper, Highlight, Annotation, PaperPassage, Subscription, MCPPaperImportRequest, ResearchProject):
                    model.__table__.create(conn)
                conn.execute(text("CREATE TABLE mcp_note_requests (user_id uuid NOT NULL, request_id uuid NOT NULL, paper_id uuid NOT NULL, content_hash text NOT NULL, PRIMARY KEY(user_id, request_id))"))
            cls.Session = sessionmaker(bind=cls.engine)
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.admin.begin() as conn:
            conn.execute(cls.text("DROP SCHEMA " + cls.schema + " CASCADE"))
        cls.admin.dispose()

    def test_concurrent_dedup_and_isolation(self):
        user, other, paper, request = uuid4(), uuid4(), uuid4(), uuid4()
        with self.engine.begin() as conn:
            conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:a, :a_email, 'google','a',true,false,true), (:b, :b_email, 'google','b',true,false,true)"), {"a": user, "b": other, "a_email":str(user)+"@test", "b_email":str(other)+"@test"})
            conn.execute(self.text("INSERT INTO papers (id, user_id, file_url, status) VALUES (:p, :u, 'x', 'reading')"), {"p": paper, "u": user})
        def call(req, content="saved"):
            with self.Session() as session:
                return self.append(session, user, str(paper), str(req), content)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: call(request), range(4)))
        self.assertEqual(sorted(r["status"] for r in results), ["already_applied"] * 3 + ["appended"])
        with self.Session() as session:
            self.assertEqual(session.query(self.PaperNote).filter_by(paper_id=paper).one().content, "saved")
            with self.assertRaises(ValueError):
                self.append(session, other, str(paper), str(uuid4()), "stolen")
        with self.assertRaises(ValueError):
            call(request, "changed")
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: call(uuid4(), "more"), range(4)))
        with self.Session() as session:
            self.assertEqual(session.query(self.PaperNote).filter_by(paper_id=paper).one().content.count("more"), 4)

    def test_research_evidence_project_privacy_and_fresh_note_context(self):
        from types import SimpleNamespace
        from app.database.models import ProjectRole, PaperPassage, Paper
        from app.mcp.research import ResearchReader
        owner, member, outsider, paper, project, empty = [uuid4() for _ in range(6)]
        with self.engine.begin() as conn:
            for uid in (owner, member, outsider):
                conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u,:e,'google',:e,true,false,true)"), {"u":uid,"e":str(uid)+"@test"})
            conn.execute(self.text("INSERT INTO papers (id,user_id,file_url,status,title,raw_content) VALUES (:p,:u,'x','reading','Unrelated metadata','Collective reasoning loses distributed evidence.')"), {"p":paper,"u":owner})
            conn.execute(self.text("INSERT INTO project (id,admin_id,title,description) VALUES (:p,:u,'Research question','Open question: information loss'), (:empty,:u,'Empty','')"), {"p":project,"u":owner,"empty":empty})
            conn.execute(self.text("INSERT INTO project_role (id,project_id,user_id,role) VALUES (:id,:p,:u,'viewer')"), {"id":uuid4(),"p":project,"u":member})
            conn.execute(self.text("INSERT INTO project_paper (id,project_id,paper_id) VALUES (:id,:p,:paper)"), {"id":uuid4(),"p":project,"paper":paper})
            conn.execute(self.text("INSERT INTO paper_passages (paper_id,start_line,end_line,content,ts_vector) VALUES (:p,1,1,:t,to_tsvector('english',:t))"), {"p":paper,"t":"Collective reasoning loses distributed evidence."})
            for uid, content in [(owner,"OWNER PRIVATE NOTE"),(member,"MEMBER PRIVATE NOTE")]:
                # Notes are unique per paper, so only the owner's note is stored.
                if uid == owner:
                    conn.execute(self.text("INSERT INTO paper_notes (id,paper_id,user_id,content) VALUES (:id,:p,:u,:t)"), {"id":uuid4(),"p":paper,"u":uid,"t":content})
                hid=uuid4()
                conn.execute(self.text("INSERT INTO highlights (id,paper_id,user_id,raw_text,role,page_number) VALUES (:id,:p,:u,:t,'user',1)"), {"id":hid,"p":paper,"u":uid,"t":content})
                conn.execute(self.text("INSERT INTO annotations (id,paper_id,user_id,highlight_id,content,role) VALUES (:id,:p,:u,:h,:t,'user')"), {"id":uuid4(),"p":paper,"u":uid,"h":hid,"t":content})
        def reader(db, uid): return ResearchReader(db, SimpleNamespace(id=uid), "https://papers.test")
        with self.Session() as db:
            r=reader(db,owner)
            hit=r.evidence("distributed")["results"][0]
            self.assertEqual(r.fetch(hit["id"])["text"],"Collective reasoning loses distributed evidence.")
            self.assertEqual(r.fetch(hit["id"])["metadata"]["start_line"],1)
            indexed=db.query(PaperPassage).filter_by(paper_id=paper).one()
            indexed.end_line=999
            db.flush()
            with self.assertRaises(ValueError): r.fetch(hit["id"])
            indexed.end_line=1
            db.flush()
            huge=SimpleNamespace(id=paper,title="x",authors=["a"*1000000],abstract="",user_id=owner)
            self.assertEqual(len(r.metadata(huge)["authors"][0]),300)
            self.assertEqual(r.evidence("distributed",str(empty))["results"],[])
            self.assertEqual(r.evidence("nonexistent")["results"],[])
            self.assertIn("OWNER PRIVATE NOTE",str(r.context(str(project))))
            member_reader=reader(db,member)
            self.assertEqual(member_reader.evidence("distributed")["results"],[])
            shared=member_reader.evidence("distributed",str(project))["results"][0]
            self.assertEqual(shared["id"],hit["id"])
            self.assertEqual(shared["url"],f"https://papers.test/projects/{project}")
            self.assertEqual(member_reader.fetch(hit["id"])["url"],shared["url"])
            from app.database.crud.projects.project_paper_crud import project_paper_crud
            # The linked project lists the cited paper through the browser's API.
            self.assertEqual(project_paper_crud.get_project_paper_ids_by_project_id(db,project_id=project,user=SimpleNamespace(id=member)),[paper])
            ctx=member_reader.context(str(project))
            self.assertNotIn("OWNER PRIVATE NOTE",str(ctx))
            self.assertIn("MEMBER PRIVATE NOTE",str(ctx))
            self.assertEqual(ctx["papers"][0]["note"]["content"],None)
            with self.assertRaises(ValueError): reader(db,outsider).fetch(hit["id"])
            with self.assertRaises(ValueError): reader(db,outsider).context(str(project))
            with self.assertRaises(ValueError): self.append(db,member,str(paper),str(uuid4()),"forbidden")
            db.rollback()
        request=uuid4()
        with self.Session() as db:
            self.append(db,owner,str(paper),str(request),"Selected insight")
        with self.Session() as db:
            self.assertEqual(self.append(db,owner,str(paper),str(request),"Selected insight")["status"],"already_applied")
        with self.Session() as db:
            context=reader(db,owner).context(str(project))
            note=context["papers"][0]["note"]
            self.assertEqual(note["content"].count("Selected insight"),1)
            self.assertTrue(note["etag"])
            first=reader(db,owner).note(str(paper),limit=5)
            rest=reader(db,owner).note(str(paper),offset=first["next_offset"])
            self.assertEqual(first["content"]+rest["content"],note["content"])
            self.assertEqual(first["etag"],rest["etag"])
            second_paper=uuid4()
            db.execute(self.text("INSERT INTO papers (id,user_id,file_url,status) VALUES (:p,:u,'x','reading')"),{"p":second_paper,"u":owner})
            db.execute(self.text("INSERT INTO project_paper (id,project_id,paper_id) VALUES (:id,:p,:paper)"),{"id":uuid4(),"p":project,"paper":second_paper})
            db.flush()
            page1=reader(db,owner).context(str(project),limit=1)
            page2=reader(db,owner).context(str(project),offset=page1["next_offset"],limit=1)
            self.assertEqual({p["id"] for p in page1["papers"]+page2["papers"]},{str(paper),str(second_paper)})
            self.assertIsNone(page2["next_offset"])
            db.query(ProjectRole).filter_by(project_id=project,user_id=member).delete()
            db.commit()
        with self.Session() as db:
            with self.assertRaises(ValueError): reader(db,member).fetch(hit["id"])
            with self.assertRaises(ValueError): reader(db,member).evidence("distributed",str(project))
            passage=db.query(PaperPassage).filter_by(paper_id=paper).one()
            source=db.query(Paper).filter_by(id=paper).one()
            source.raw_content="Changed raw text, index untouched"
            db.flush()
            with self.assertRaises(ValueError): reader(db,owner).fetch(hit["id"])
            from app.mcp.research import passage_id
            source.raw_content=passage.content="x"*20001
            db.flush()
            with self.assertRaisesRegex(ValueError,"exceeds 20000"): reader(db,owner).fetch(passage_id(passage))
            passage.content="Revised source text"
            db.commit()
            with self.assertRaises(ValueError): reader(db,owner).fetch(hit["id"])
            for query,limit in [("",20),("x"*201,20),("valid",31)]:
                with self.assertRaises(ValueError): reader(db,owner).evidence(query,limit=limit)

    def test_upload_content_dedup_race_permissions_and_status(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import patch, AsyncMock
        from app.mcp.uploads import import_pdf, upload_status
        from app.database.models import PaperUploadJob, Paper
        from app.api import paper_upload_api
        owner,other,project=[uuid4() for _ in range(3)]
        with self.engine.begin() as conn:
            for uid in (owner,other):
                conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u,:e,'google',:e,true,false,true)"),{"u":uid,"e":str(uid)+"@test"})
            conn.execute(self.text("INSERT INTO project (id,admin_id,title) VALUES (:p,:u,'Upload test')"),{"p":project,"u":owner})
            conn.execute(self.text("INSERT INTO project_role (id,project_id,user_id,role) VALUES (:id,:p,:u,'viewer')"),{"id":uuid4(),"p":project,"u":other})
        calls=[]
        async def dispatch(data,filename,job,user,db,project,**options):
            self.assertTrue(options['preserve_on_dispatch_error'])
            calls.append(str(job.id))
            job.status='running';job.task_id='test-task';db.commit()
        def call():
            with self.Session() as db:
                return asyncio.run(import_pdf(db,SimpleNamespace(id=owner),'https://papers.test','https://files.test/file.pdf'))
        with patch('app.mcp.uploads.download_pdf',return_value=b'fixture'),patch('app.mcp.uploads.validate_pdf_content',new=AsyncMock(return_value=(True,''))),patch.object(paper_upload_api,'check_subscription_limits',new=AsyncMock(return_value=None)),patch.object(paper_upload_api,'upload_raw_file_microservice',side_effect=dispatch):
            with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(lambda _:call(),range(3)))
            self.assertEqual(len(calls),1)
            self.assertEqual(len({r['job_id'] for r in results}),1)
            self.assertEqual(sum(not r['reused'] for r in results),1)
            with self.Session() as db:
                with self.assertRaisesRegex(ValueError,'editor'):asyncio.run(import_pdf(db,SimpleNamespace(id=other),'https://papers.test','https://files.test/file.pdf',str(project)))
                with self.assertRaises(ValueError):upload_status(db,SimpleNamespace(id=other),results[0]['job_id'],'https://papers.test')
                job=db.query(PaperUploadJob).filter_by(id=UUID(results[0]['job_id'])).one()
                job.status='failed';db.commit()
            failed=call()
            self.assertEqual(failed['status'],'failed');self.assertEqual(len(calls),1)
            with self.Session() as db:
                job=db.query(PaperUploadJob).filter_by(id=UUID(results[0]['job_id'])).one()
                job.status='completed';db.add(Paper(id=uuid4(),user_id=owner,file_url='x',upload_job_id=job.id));db.commit()
                ready=upload_status(db,SimpleNamespace(id=owner),str(job.id),'https://papers.test')
                self.assertTrue(ready['completed']);self.assertTrue(ready['paper_url'])
        with patch('app.mcp.uploads.download_pdf',return_value=b'bad'),patch('app.mcp.uploads.validate_pdf_content',new=AsyncMock(return_value=(False,'Not a PDF'))):
            with self.Session() as db:
                before=db.query(PaperUploadJob).count()
                with self.assertRaisesRegex(ValueError,'Not a PDF'):asyncio.run(import_pdf(db,SimpleNamespace(id=owner),'https://papers.test','https://files.test/bad'))
                self.assertEqual(db.query(PaperUploadJob).count(),before)
        interrupted=AsyncMock(side_effect=asyncio.CancelledError())
        with patch('app.mcp.uploads.download_pdf',return_value=b'interrupted'),patch('app.mcp.uploads.validate_pdf_content',new=AsyncMock(return_value=(True,''))),patch.object(paper_upload_api,'check_subscription_limits',new=AsyncMock(return_value=None)),patch.object(paper_upload_api,'upload_raw_file_microservice',new=interrupted):
            with self.Session() as db:
                with self.assertRaises(asyncio.CancelledError):asyncio.run(import_pdf(db,SimpleNamespace(id=owner),'https://papers.test','https://files.test/file.pdf'))
            with self.Session() as db:
                recovered=asyncio.run(import_pdf(db,SimpleNamespace(id=owner),'https://papers.test','https://files.test/file.pdf'))
                self.assertTrue(recovered['reused']);self.assertEqual(recovered['status'],'pending')
                self.assertEqual(interrupted.await_count,1)
        with patch('app.mcp.uploads.download_pdf',return_value=b'different'),patch('app.mcp.uploads.validate_pdf_content',new=AsyncMock(return_value=(True,''))),patch.object(paper_upload_api,'check_subscription_limits',new=AsyncMock(return_value='Upload limit')):
            with self.Session() as db:
                with self.assertRaisesRegex(ValueError,'Upload limit'):asyncio.run(import_pdf(db,SimpleNamespace(id=owner),'https://papers.test','https://files.test/other'))

    def test_encrypted_store_survives_new_instances(self):
        import asyncio
        import asyncpg
        from cryptography.fernet import Fernet
        from key_value.aio.stores.postgresql import PostgreSQLStore
        from key_value.aio.wrappers.encryption.fernet import FernetEncryptionWrapper
        table = "mcp_store_" + uuid4().hex
        with self.engine.begin() as conn:
            conn.execute(self.text("CREATE TABLE " + table + " (collection text NOT NULL, key text NOT NULL, value jsonb NOT NULL, ttl double precision, created_at timestamptz, expires_at timestamptz, PRIMARY KEY(collection, key))"))
        async def check():
            pool = await asyncpg.create_pool(user=getpass.getuser(), database="postgres", host="/tmp", port=55439,
                server_settings={"search_path": self.schema})
            key = Fernet.generate_key()
            try:
                a = FernetEncryptionWrapper(PostgreSQLStore(pool=pool, table_name=table, auto_create=False), fernet=Fernet(key))
                await a.put(key="client", collection="oauth", value={"token": "sensitive-value"})
                b = FernetEncryptionWrapper(PostgreSQLStore(pool=pool, table_name=table, auto_create=False), fernet=Fernet(key))
                self.assertEqual(await b.get(key="client", collection="oauth"), {"token": "sensitive-value"})
                async with pool.acquire() as conn:
                    raw = await conn.fetchval("SELECT value::text FROM " + table)
                    self.assertNotIn("sensitive-value", raw)
            finally:
                await pool.close()
        asyncio.run(check())

    def test_stale_browser_put_is_rejected(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import patch
        from fastapi import HTTPException
        from app.api import paper_api
        from app.mcp.notes import note_etag
        user, paper = uuid4(), uuid4()
        with self.engine.begin() as conn:
            conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u, :email, 'google','u',true,false,true)"), {"u": user, "email":str(user)+"@test"})
            conn.execute(self.text("INSERT INTO papers (id, user_id, file_url, status) VALUES (:p, :u, 'x', 'reading')"), {"p": paper, "u": user})
        with self.Session() as session:
            self.append(session, user, str(paper), str(uuid4()), "original")
        old = note_etag("original")
        with self.Session() as session:
            self.append(session, user, str(paper), str(uuid4()), "new append")
        async def put(if_match):
            with self.Session() as session:
                return await paper_api.update_paper_note(str(paper), paper_api.UpdatePaperNoteSchema(content="old editor"), if_match, session, SimpleNamespace(id=user))
        with patch.dict(os.environ, {"MCP_ENABLED": "true"}), patch.object(paper_api.paper_crud, "get", return_value=object()):
            for tag, code in [(None, 428), (old, 412)]:
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(put(tag))
                self.assertEqual(caught.exception.status_code, code)
        with self.Session() as session:
            self.assertEqual(session.query(self.PaperNote).filter_by(paper_id=paper).one().content, "original\n\nnew append")

    def test_mcp_tool_identity_and_access_isolation(self):
        import asyncio
        import httpx
        from unittest.mock import patch
        from fastmcp.server.auth.auth import AccessToken
        from fastmcp.server.auth.providers.google import GoogleProvider
        from app.mcp import server
        owner, other, blocked, inactive, disallowed, paper = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
        emails = {"owner": str(owner)+"@test", "other": str(other)+"@test", "blocked": str(blocked)+"@test", "inactive": str(inactive)+"@test", "disallowed": str(disallowed)+"@test"}
        with self.engine.begin() as conn:
            for name, uid in [("owner", owner), ("other", other), ("blocked", blocked), ("inactive", inactive), ("disallowed", disallowed)]:
                conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:id,:email,'google',:provider,:active,:blocked,true)"), {"id":uid,"email":emails[name],"provider":name,"blocked":name == "blocked", "active":name != "inactive"})
            conn.execute(self.text("INSERT INTO papers (id,user_id,file_url,status,title,raw_content) VALUES (:p,:u,'x','reading','Private title','Collective reasoning evidence')"), {"p":paper,"u":owner})
            conn.execute(self.text("INSERT INTO paper_passages (paper_id,start_line,end_line,content,ts_vector) VALUES (:p,1,1,'Collective reasoning evidence',to_tsvector('english','Collective reasoning evidence'))"), {"p":paper})
        async def verify(_self, token):
            name = token if token in emails else "owner"
            claims = {"email": emails[name], "email_verified": token != "unverified", "aud": "wrong" if token == "wrong-audience" else "test-client"}
            return AccessToken(token=token, client_id="test", scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"], claims=claims)
        async def check():
            settings = {"CLIENT_DOMAIN":"https://papers.example.workers.dev", "GOOGLE_CLIENT_ID":"test-client", "GOOGLE_CLIENT_SECRET":"test-secret", "MCP_JWT_SIGNING_KEY":"testing-signing-key-with-32-characters", "MCP_STORAGE_ENCRYPTION_KEY":"MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=", "ALLOWED_EMAILS": ",".join(email for name, email in emails.items() if name != "disallowed")}
            with patch.dict(os.environ, settings), patch.object(GoogleProvider, "verify_token", verify), patch.object(server, "SessionLocal", self.Session):
                app = server.create_mcp_app()
                async with app.lifespan(app):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=settings["CLIENT_DOMAIN"]) as client:
                        async def call(token):
                            return await client.post("/api/mcp", headers={"accept":"application/json, text/event-stream", "authorization":"Bearer " + token, "mcp-protocol-version":"2025-03-26"}, json={"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_paper","arguments":{"paper_id":str(paper)}}})
                        self.assertIn("Private title", (await call("owner")).text)
                        async def rpc(name, arguments):
                            result = await client.post("/api/mcp", headers={"accept":"application/json, text/event-stream", "authorization":"Bearer owner", "mcp-protocol-version":"2025-03-26"}, json={"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":name,"arguments":arguments}})
                            self.assertEqual(result.status_code,200)
                            import json
                            payload = result.json() if result.headers.get("content-type","").startswith("application/json") else json.loads(next(line[6:] for line in result.text.splitlines() if line.startswith("data: ")))
                            self.assertFalse(payload["result"].get("isError"),payload)
                            return payload["result"]["structuredContent"]
                        search_result=await rpc("search",{"query":"unmatched"})
                        self.assertEqual(search_result,{"results":[]})
                        hits=await rpc("search",{"query":"collective"})
                        self.assertEqual(len(hits["results"]),1)
                        fetched=await rpc("fetch",{"id":hits["results"][0]["id"]})
                        self.assertEqual(fetched["text"],"Collective reasoning evidence")
                        self.assertTrue(fetched["url"])
                        self.assertEqual(fetched["metadata"]["start_line"],1)
                        req=str(uuid4())
                        first=await rpc("append_paper_note",{"paper_id":str(paper),"request_id":req,"content":"Chosen synthesis"})
                        second=await rpc("append_paper_note",{"paper_id":str(paper),"request_id":req,"content":"Chosen synthesis"})
                        self.assertEqual(second["status"],"already_applied")
                        note=await rpc("get_paper_note",{"paper_id":str(paper)})
                        self.assertEqual(note["content"],"Chosen synthesis")
                        self.assertEqual(first["etag"],note["etag"])
                        from app.api import paper_upload_api
                        from unittest.mock import AsyncMock
                        from pathlib import Path
                        pdf=(Path(__file__).resolve().parents[1]/'evals/seed_data/publicusegeneralhealthchatbots.pdf').read_bytes()
                        with patch('app.mcp.uploads.download_pdf',return_value=pdf) as download,patch.object(paper_upload_api,'check_subscription_limits',new=AsyncMock(return_value=None)),patch.object(paper_upload_api,'track_event'),patch.object(paper_upload_api.jobs_client,'submit_pdf_processing_job_with_upload',new=AsyncMock(return_value='processing-task')) as dispatch:
                            imported=await rpc('upload_paper_file',{'file':{'download_url':'https://file.test/first.pdf','file_id':'file-first'}})
                            attached=await rpc('upload_paper_file',{'file':{'download_url':'https://file.test/signed.pdf','file_id':'file-test'}})
                            self.assertEqual(imported['job_id'],attached['job_id'])
                            self.assertTrue(attached['reused']);self.assertEqual(dispatch.await_count,1)
                            polled=await rpc('get_paper_upload_status',{'job_id':imported['job_id']})
                            self.assertFalse(polled['completed']);self.assertEqual(polled['status'],'running')
                            self.assertEqual(dispatch.await_args.kwargs['pdf_bytes'],pdf)
                            self.assertEqual(dispatch.await_args.kwargs['user'].id,owner)
                            download.return_value=pdf+b'\n% attachment variant\n'
                            standalone=await rpc('upload_paper_file',{'file':{'download_url':'https://file.test/second.pdf','file_id':'file-second','mime_type':'application/pdf','file_name':'second.pdf'}})
                            self.assertNotEqual(standalone['job_id'],imported['job_id'])
                            self.assertEqual(standalone['status'],'running')
                            self.assertEqual(dispatch.await_count,2)
                            download.assert_called_with('https://file.test/second.pdf')
                            self.assertEqual(dispatch.await_args.kwargs['user'].id,owner)
                            self.assertEqual(dispatch.await_args.kwargs['pdf_bytes'],download.return_value)


                        for token in ["other", "blocked", "inactive", "disallowed", "unverified", "wrong-audience"]:
                            response = await call(token)
                            self.assertNotIn("Private title", response.text, token)
                            self.assertIn('"isError":true', response.text.replace(" ", ""), token)
        asyncio.run(check())

    def test_migration_upgrade_and_downgrade(self):
        import importlib.util
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy import create_engine
        schema = "mcp_migration_" + uuid4().hex
        with self.admin.begin() as conn:
            conn.execute(self.text("CREATE SCHEMA " + schema))
        engine = create_engine(self.admin.url, connect_args={"options":"-csearch_path=" + schema})
        try:
            path = Path(__file__).resolve().parents[1] / "migrations/versions/2026_11_03_1200_mcp_note_requests.py"
            spec = importlib.util.spec_from_file_location("mcp_migration_test", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with engine.begin() as conn:
                conn.execute(self.text("CREATE TABLE users (id uuid PRIMARY KEY)"))
                conn.execute(self.text("CREATE TABLE papers (id uuid PRIMARY KEY)"))
                with Operations.context(MigrationContext.configure(conn)):
                    module.upgrade()
                    self.assertEqual(conn.execute(self.text("SELECT to_regclass('mcp_oauth_store') IS NOT NULL")).scalar_one(), True)
                    module.downgrade()
                    self.assertEqual(conn.execute(self.text("SELECT to_regclass('mcp_oauth_store') IS NULL")).scalar_one(), True)
        finally:
            engine.dispose()
            with self.admin.begin() as conn:
                conn.execute(self.text("DROP SCHEMA " + schema + " CASCADE"))
