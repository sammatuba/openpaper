"""Private thumbnails: durable storage URLs become authorized signed read URLs."""
import os
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.helpers.s3 import S3Service

BASE = "https://storage.googleapis.com/test-papers"
PREVIEW = BASE + "/uploads/preview.png"


def storage():
    service = S3Service.__new__(S3Service)
    service.bucket_name = "test-papers"
    service.cloudflare_bucket_name = "storage.googleapis.com/test-papers"
    service.s3_client = boto3.client(
        "s3", endpoint_url="https://storage.googleapis.com",
        aws_access_key_id="test-access", aws_secret_access_key="test-secret",
        region_name="auto", config=Config(signature_version="s3v4"),
    )
    return service


class PreviewSigningTests(unittest.TestCase):
    def setUp(self):
        self.service = storage()

    def test_private_preview_has_a_valid_signature_for_its_object(self):
        signed = self.service.get_preview_url(PREVIEW)
        self.assertEqual(urlsplit(signed).path, "/test-papers/uploads/preview.png")
        query = parse_qs(urlsplit(signed).query)
        self.assertIn("X-Amz-Signature", query)
        self.assertEqual(query["X-Amz-Expires"], ["86400"])

    def test_expired_signatures_are_replaced_and_keys_decoded_once(self):
        signer = MagicMock(return_value="fresh-url")
        self.service.generate_presigned_url = signer
        self.assertEqual(self.service.get_preview_url(
            BASE + "/uploads/a%20b%2520.png?X-Amz-Signature=expired#page"
        ), "fresh-url")
        signer.assert_called_once_with("uploads/a b%20.png")

    def test_other_hosts_and_buckets_never_receive_our_signature(self):
        self.service.generate_presigned_url = MagicMock()
        for url in ("https://cdn.example/preview.png",
                    "https://storage.googleapis.com/other-bucket/preview.png",
                    "https://storage.googleapis.com/test-papers-extra/preview.png",
                    "https://storage.googleapis.com.evil.example/test-papers/preview.png",
                    "https://storage.googleapis.com@evil.example/test-papers/preview.png"):
            self.assertEqual(self.service.get_preview_url(url), url)
        self.service.generate_presigned_url.assert_not_called()

    def test_missing_preview_and_empty_key_need_no_signing(self):
        self.service.generate_presigned_url = MagicMock()
        self.assertIsNone(self.service.get_preview_url(None))
        self.assertEqual(self.service.get_preview_url(""), "")
        self.assertIsNone(self.service.get_preview_url(BASE + "/"))
        self.service.generate_presigned_url.assert_not_called()

    def test_legacy_cdn_storage_path_is_signed_too(self):
        self.service.cloudflare_bucket_name = "assets.example"
        self.service.generate_presigned_url = MagicMock(return_value="signed")
        self.assertEqual(self.service.get_preview_url("https://assets.example/uploads/p.png"), "signed")
        self.service.generate_presigned_url.assert_called_once_with("uploads/p.png")

    def test_signing_failure_returns_no_broken_private_link(self):
        self.service.s3_client = MagicMock()
        self.service.s3_client.generate_presigned_url.side_effect = ClientError(
            {"Error": {"Code": "SigningFailed", "Message": "test failure"}}, "GetObject"
        )
        self.assertIsNone(self.service.get_preview_url(PREVIEW))


@unittest.skipUnless(os.environ.get("OPENPAPER_ISOLATED_PG_TEST") == "1",
                     "requires isolated /tmp PostgreSQL")
class PreviewPostgresTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_mcp_postgres as fixture
        fixture.MCPPostgresTests.setUpClass.__func__(cls)
        from app.database.models import PaperTag, PaperTagAssociation, PaperImage, ZoteroImportedItem
        with cls.engine.begin() as conn:
            for model in (PaperTag, PaperTagAssociation, PaperImage, ZoteroImportedItem):
                model.__table__.create(conn)

    @classmethod
    def tearDownClass(cls):
        from tests import test_mcp_postgres as fixture
        fixture.MCPPostgresTests.tearDownClass.__func__(cls)

    async def test_responses_sign_only_accessible_papers_without_changing_storage(self):
        import httpx
        from fastapi import FastAPI
        from sqlalchemy import inspect
        from app.api import paper_api, search_api
        from app.api.projects import project_papers_api
        from app.auth.dependencies import get_current_user, get_required_user
        from app.database.database import get_db
        from app.database.models import Paper
        from app.database.crud.projects.project_paper_crud import project_paper_crud

        owner, viewer, outsider, project, paper_id = [uuid4() for _ in range(5)]
        with self.engine.begin() as conn:
            for uid in (owner, viewer, outsider):
                conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u,:e,'google',:e,true,false,true)"),
                             {"u": uid, "e": str(uid) + "@example.com"})
            conn.execute(self.text("INSERT INTO project (id,admin_id,title) VALUES (:p,:u,'Preview test')"), {"p": project, "u": owner})
            for uid, role in ((owner, "admin"), (viewer, "viewer")):
                conn.execute(self.text("INSERT INTO project_role (id,project_id,user_id,role) VALUES (:id,:p,:u,:r)"),
                             {"id": uuid4(), "p": project, "u": uid, "r": role})
        with self.Session() as db:
            db.add(Paper(id=paper_id, user_id=owner, title="Preview research",
                         raw_content="Preview research finding.", summary="", file_url="stored-pdf",
                         s3_object_key="uploads/paper.pdf", preview_url=PREVIEW))
            db.commit()
            db.execute(self.text("INSERT INTO project_paper (id,project_id,paper_id) VALUES (:id,:p,:paper)"),
                       {"id": uuid4(), "p": project, "paper": paper_id})
            db.commit()

        actor = SimpleNamespace(id=owner)
        with self.Session() as db:
            row = project_paper_crud.get_papers_metadata_by_project_id(db, project_id=project, user=actor)[0]
            self.assertNotIn("preview_url", inspect(row).unloaded)
            self.assertIn("raw_content", inspect(row).unloaded)
            self.assertIn("summary", inspect(row).unloaded)
            db.expunge(row)
            self.assertEqual(row.preview_url, PREVIEW)  # no lazy query for the preview

        app = FastAPI()
        app.include_router(paper_api.paper_router, prefix="/api/paper")
        app.include_router(project_papers_api.project_papers_router, prefix="/api/project-papers")
        app.include_router(search_api.search_router, prefix="/api/search")
        app.dependency_overrides[get_required_user] = lambda: actor
        app.dependency_overrides[get_current_user] = lambda: actor
        def session():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db] = session
        service = storage()
        # Only storage/network and unrelated metadata/analytics are replaced.
        # Paper access, membership, deferred loading and search use PostgreSQL.
        with ExitStack() as stack:
            for module in (paper_api, project_papers_api, search_api):
                stack.enter_context(patch.object(module, "s3_service", service))
                stack.enter_context(patch.object(module, "track_event"))
            stack.enter_context(patch.object(service, "get_cached_presigned_url", return_value="signed-pdf"))
            stack.enter_context(patch.object(paper_api, "hydrate_paper_metadata", side_effect=lambda **kw: kw["paper"]))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                for path in ("/api/paper/all", "/api/paper/active", "/api/paper/relevant",
                             f"/api/project-papers/{project}", "/api/search/?q=preview"):
                    response = await client.get(path)
                    self.assertEqual(response.status_code, 200, response.text)
                    preview = response.json()["papers"][0]["preview_url"]
                    self.assertIn("X-Amz-Signature=", preview)
                response = await client.get(f"/api/paper?id={paper_id}")
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn("X-Amz-Signature=", response.json()["preview_url"])
                actor.id = viewer
                response = await client.get(f"/api/project-papers/{project}")
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn("X-Amz-Signature=", response.json()["papers"][0]["preview_url"])
                self.assertEqual((await client.get(f"/api/paper?id={paper_id}")).status_code, 404)
                actor.id = outsider
                self.assertEqual((await client.get(f"/api/project-papers/{project}")).json()["papers"], [])
                self.assertEqual((await client.get("/api/paper/all")).json()["papers"], [])
                self.assertEqual((await client.get("/api/search/?q=preview")).json()["papers"], [])
                self.assertEqual((await client.get(f"/api/paper?id={paper_id}")).status_code, 404)
                share_id = str(uuid4())
                with self.Session() as db:
                    shared = db.get(Paper, paper_id)
                    shared.is_public = True
                    shared.share_id = share_id
                    db.commit()
                app.dependency_overrides[get_current_user] = lambda: None
                stack.enter_context(patch.object(service, "get_cached_presigned_url_by_owner", return_value="shared-pdf"))
                response = await client.get(f"/api/paper/share?id={share_id}")
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn("X-Amz-Signature=", response.json()["paper"]["preview_url"])
                with self.Session() as db:
                    db.get(Paper, paper_id).is_public = False
                    db.commit()
                with patch.object(service, "get_preview_url", wraps=service.get_preview_url) as sign:
                    self.assertEqual((await client.get(f"/api/paper/share?id={share_id}")).status_code, 404)
                    sign.assert_not_called()
        with self.Session() as db:
            self.assertEqual(db.get(Paper, paper_id).preview_url, PREVIEW)
