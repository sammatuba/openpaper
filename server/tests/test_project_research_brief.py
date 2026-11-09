"""Textfold source fidelity and project persistence, permissions and stale folds."""
import copy
import os
import unittest

from pydantic import ValidationError
from app.schemas.textfold import TextFoldDocument


def document():
    return {
        "format": "textfold/doc", "version": 0, "id": "project-test", "title": "An uncertainty", "lang": "en",
        "levels": ["topic", "takeaway", "key", "brief", "full"], "written": ["topic", "takeaway", "key"],
        "provenance": {"ai_generated": True, "local": False, "model": "test-model", "upstream": "preserved"},
        "sections": [{"id": "S1", "title": "Evidence for", "depth": 1, "takeaway": "A tentative result", "topic": "Result",
                      "units": [{"id": "S1.p1", "kind": "paragraph", "full": "Observed a difference. A confound remains.",
                                 "sentences": ["Observed a difference.", "A confound remains."], "evidence": [0, 1],
                                 "brief": ["Observed a difference.", "A confound remains."],
                                 "key": "A result with a caveat", "takeaway": "A tentative result", "topic": "Result"}]}],
        "links": [{"from": "S1.p1", "to": "S1", "rel": "supports"}], "extension": {"keep": True},
    }


class TextFoldValidationTests(unittest.TestCase):
    def test_roundtrip_preserves_provenance_extensions_and_link_alias(self):
        self.assertEqual(TextFoldDocument.model_validate(document()).model_dump(by_alias=True), document())

    def test_rejects_unsupported_version_and_invalid_links_or_ids(self):
        changes = [lambda d: d.update(version=1), lambda d: d['links'][0].update(to='missing'),
                   lambda d: d['sections'][0]['units'][0].update(id='S1'),
                   lambda d: d.update(written=['full']), lambda d: d.update(levels=['topic'])]
        for change in changes:
            d = document()
            change(d)
            with self.assertRaises(ValidationError): TextFoldDocument.model_validate(d)

    def test_rejects_fabricated_quotes_bad_anchors_and_reordered_source(self):
        for update in [{"evidence": [-1]}, {"evidence": [99]}, {"evidence": [True]},
                       {"brief": ["Invented quotation"]}, {"evidence": [], "brief": []},
                       {"full": "Unrelated content"}, {"sentences": []},
                       {"full": "", "sentences": [], "evidence": [], "brief": []},
                       {"sentences": ["A confound remains.", "Observed a difference."]}]:
            d = document()
            d['sections'][0]['units'][0].update(update)
            with self.assertRaises(ValidationError): TextFoldDocument.model_validate(d)

    def test_rejects_oversized_extension_fields(self):
        d = document()
        d['extension'] = 'x' * 1_000_001
        with self.assertRaises(ValidationError): TextFoldDocument.model_validate(d)

    def test_unicode_uses_utf8_size_and_empty_sections_cannot_claim_results(self):
        d = document()
        d['extension'] = '文' * 200_000
        self.assertEqual(TextFoldDocument.model_validate(d).model_dump(by_alias=True), d)
        for version in (False, 0.0):
            d = document()
            d['version'] = version
            with self.assertRaises(ValidationError): TextFoldDocument.model_validate(d)
        d = document()
        d['sections'][0]['units'] = []
        with self.assertRaises(ValidationError): TextFoldDocument.model_validate(d)


@unittest.skipUnless(os.environ.get('OPENPAPER_ISOLATED_PG_TEST') == '1', 'requires isolated /tmp PostgreSQL')
class ProjectResearchBriefPostgresTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse the guarded socket-only fixture without inheriting its tests.
        from tests import test_mcp_postgres as fixture
        fixture.MCPPostgresTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        from tests import test_mcp_postgres as fixture
        fixture.MCPPostgresTests.tearDownClass.__func__(cls)

    async def test_api_roundtrip_permissions_and_source_invalidation(self):
        import httpx
        from fastapi import FastAPI
        from types import SimpleNamespace
        from unittest.mock import patch
        from uuid import uuid4
        from app.api.projects.projects_api import projects_router
        from app.auth.dependencies import get_required_user
        from app.database.database import get_db
        from app.database.models import ProjectRole, ProjectRoles

        owner, viewer, outsider = [uuid4() for _ in range(3)]
        with self.engine.begin() as conn:
            for uid in (owner, viewer, outsider):
                conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u,:e,'google',:e,true,false,true)"), {'u': uid, 'e': str(uid) + '@test.invalid'})
        app = FastAPI()
        app.include_router(projects_router, prefix='/api/projects')
        actor = SimpleNamespace(id=owner)
        app.dependency_overrides[get_required_user] = lambda: actor
        def db_session():
            with self.Session() as db: yield db
        app.dependency_overrides[get_db] = db_session
        with patch('app.api.projects.projects_api.can_user_create_project', return_value=(True, None)), patch('app.api.projects.projects_api.track_event'):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                payload = {'title': 'Research', 'description': 'Original source', 'research_brief': document()}
                created = await client.post('/api/projects', json=payload)
                self.assertEqual(created.status_code, 201, created.text)
                project_id = created.json()['id']
                path = '/api/projects/' + project_id
                self.assertEqual((await client.get(path)).json()['research_brief'], document())
                listed = (await client.get('/api/projects')).json()
                self.assertNotIn('research_brief', listed[0])
                self.assertEqual((await client.patch(path, json={'title': 'Renamed'})).json()['research_brief'], document())
                self.assertEqual((await client.patch(path, json={'description': 'Original source'})).json()['research_brief'], document())
                self.assertIsNone((await client.patch(path, json={'description': 'Changed source'})).json()['research_brief'])
                replacement = copy.deepcopy(document())
                replacement['title'] = 'Replacement'
                response = await client.patch(path, json={'description': 'Replacement source', 'research_brief': replacement})
                self.assertEqual(response.json()['research_brief'], replacement)
                bad = document()
                bad['sections'][0]['units'][0]['brief'] = ['Fabricated quote']
                self.assertEqual((await client.patch(path, json={'research_brief': bad})).status_code, 422)
                self.assertEqual((await client.get(path)).json()['research_brief'], replacement)
                with self.Session() as db:
                    db.add(ProjectRole(id=uuid4(), project_id=project_id, user_id=viewer, role=ProjectRoles.VIEWER))
                    db.commit()
                actor.id = viewer
                self.assertEqual((await client.get(path)).json()['research_brief'], replacement)
                self.assertEqual((await client.patch(path, json={'research_brief': None})).status_code, 404)
                actor.id = outsider
                self.assertEqual((await client.get(path)).status_code, 404)
                actor.id = owner
                self.assertIsNone((await client.patch(path, json={'research_brief': None})).json()['research_brief'])

    async def test_migration_upgrade_and_downgrade_preserve_description(self):
        import importlib.util
        from pathlib import Path
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        path = Path(__file__).resolve().parents[1] / 'migrations/versions/2026_11_08_1200_project_research_brief.py'
        spec = importlib.util.spec_from_file_location('brief_migration', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with self.engine.begin() as conn:
            # This fixture starts at the current ORM schema, so undo first.
            with Operations.context(MigrationContext.configure(conn)):
                migration.downgrade()
                migration.upgrade()
            columns = {row[0] for row in conn.execute(self.text("SELECT column_name FROM information_schema.columns WHERE table_schema=:schema AND table_name='project'"), {'schema': self.schema})}
            self.assertIn('description', columns)
            self.assertIn('research_brief', columns)
