"""MCP note transactions on the dedicated socket-only test PostgreSQL cluster."""
import getpass
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4


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
                conn.execute(text("CREATE TABLE paper_upload_jobs (id uuid PRIMARY KEY)"))
                Paper.__table__.create(conn)
                PaperNote.__table__.create(conn)
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
            conn.execute(self.text("INSERT INTO papers (id,user_id,file_url,status,title) VALUES (:p,:u,'x','reading','Private title')"), {"p":paper,"u":owner})
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
            path = "/home/sammatuba/projects/ps/openpaper/server/migrations/versions/2026_11_03_1200_mcp_note_requests.py"
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
