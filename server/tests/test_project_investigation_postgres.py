"""Actual conditional HTTP persistence on the guarded disposable cluster."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import UUID, uuid4

@unittest.skipUnless(os.environ.get('OPENPAPER_ISOLATED_PG_TEST')=='1','requires isolated PostgreSQL')
class InvestigationPostgresTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_mcp_postgres import MCPPostgresTests
        MCPPostgresTests.setUpClass.__func__(cls)
        from sqlalchemy import event
        @event.listens_for(cls.engine, "connect")
        def utf8(connection, record): connection.set_client_encoding("UTF8")
        import json
        cls.engine.dialect._json_serializer=lambda value:json.dumps(value,ensure_ascii=False)
        cls.engine.dispose()
        from app.database.models import ProjectInvestigation
        with cls.engine.begin() as conn: ProjectInvestigation.__table__.create(conn)

    @classmethod
    def tearDownClass(cls):
        from tests.test_mcp_postgres import MCPPostgresTests
        MCPPostgresTests.tearDownClass.__func__(cls)

    def seed(self):
        owner,viewer,outsider,project,paper=[uuid4() for _ in range(5)]
        with self.engine.begin() as conn:
            for uid in (owner,viewer,outsider):
                conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u,:e,'google',:e,true,false,true)"),{'u':uid,'e':str(uid)+'@test.invalid'})
            conn.execute(self.text("INSERT INTO project (id,admin_id,title,description) VALUES (:p,:u,'Synthetic investigation','Keep legacy description')"),{'p':project,'u':owner})
            conn.execute(self.text("INSERT INTO project_role (id,project_id,user_id,role) VALUES (:id,:p,:u,'viewer')"),{'id':uuid4(),'p':project,'u':viewer})
            conn.execute(self.text("INSERT INTO papers (id,user_id,file_url,status,title,raw_content) VALUES (:p,:u,'x','reading','Synthetic A',:text)"),{'p':paper,'u':owner,'text':'Title\nExact result α.\nLimitations.'})
            conn.execute(self.text("INSERT INTO project_paper (id,project_id,paper_id) VALUES (:id,:p,:paper)"),{'id':uuid4(),'p':project,'paper':paper})
        return owner,viewer,outsider,project,paper

    async def test_http_virtual_save_etag_roles_anchor_redaction(self):
        import httpx
        from fastapi import FastAPI
        from app.api.projects.project_investigation_api import investigation_router
        from app.auth.dependencies import get_required_user
        from app.database.database import get_db
        from app.database.models import ProjectInvestigation
        owner,viewer,outsider,project,paper=self.seed()
        actor=SimpleNamespace(id=owner)
        app=FastAPI();app.include_router(investigation_router,prefix='/api/projects')
        app.dependency_overrides[get_required_user]=lambda:actor
        def sessions():
            with self.Session() as db: yield db
        app.dependency_overrides[get_db]=sessions
        url=f'/api/projects/{project}/investigation'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            first=await client.get(url);self.assertEqual(first.status_code,200,first.text)
            tag=first.headers['etag'];document=first.json()['document']
            with self.Session() as db: self.assertIsNone(db.get(ProjectInvestigation,project))
            self.assertEqual((await client.put(url,json={'document':document})).status_code,428)
            source=(await client.get(url+f'/sources/{paper}?start_line=2&line_count=1')).json()
            fid=str(uuid4())
            document['findings']=[{'id':fid,'label':'Observed result','source':{'kind':'anchored','paper_id':str(paper),'start_line':2,'end_line':2,'quote':source['text'],'source_sha256':source['source_sha256'],'quote_sha256':source['quote_sha256']}}]
            saved=await client.put(url,json={'document':document},headers={'If-Match':tag})
            self.assertEqual(saved.status_code,200,saved.text)
            self.assertEqual((await client.put(url,json={'document':document},headers={'If-Match':tag})).status_code,412)
            tag=saved.headers['etag'];document=saved.json()['document']
            # Persist a manual cited paragraph, then change its source.
            document['manuscript']['sections']=[{'id':str(uuid4()),'title':'Evidence','blocks':[{'id':str(uuid4()),'kind':'paragraph','text':'A qualified authored paragraph.','finding_ids':[fid]}]}]
            paragraph=await client.put(url,json={'document':document},headers={'If-Match':tag})
            self.assertEqual(paragraph.status_code,200,paragraph.text)
            tag=paragraph.headers['etag'];document=paragraph.json()['document'];block=document['manuscript']['sections'][0]['blocks'][0]
            self.assertEqual(paragraph.json()['validation']['blocks'][block['id']],'current')
            old_pins=block['dependency_pins']
            with self.engine.begin() as conn:
                conn.execute(self.text('UPDATE papers SET raw_content=:text WHERE id=:p'),{'p':paper,'text':'Title\nChanged result.\nLimitations.'})
            changed=await client.get(url)
            self.assertEqual(changed.json()['validation']['findings'][fid],'source_changed')
            self.assertEqual(changed.json()['validation']['blocks'][block['id']],'review_needed')
            self.assertEqual(changed.json()['document']['manuscript']['sections'][0]['blocks'][0]['text'],'A qualified authored paragraph.')
            ordinary=await client.put(url,json={'document':document},headers={'If-Match':tag})
            self.assertEqual(ordinary.status_code,200,ordinary.text)
            self.assertEqual(ordinary.json()['document']['manuscript']['sections'][0]['blocks'][0]['dependency_pins'],old_pins)
            tag=ordinary.headers['etag']
            reviewed=await client.put(url,json={'document':document,'reviewed_block_ids':[block['id']]},headers={'If-Match':tag})
            self.assertEqual(reviewed.status_code,409,reviewed.text)
            actor.id=viewer
            self.assertEqual((await client.get(url)).status_code,200)
            self.assertEqual((await client.put(url,json={'document':document},headers={'If-Match':tag})).status_code,403)
            actor.id=outsider;self.assertEqual((await client.get(url)).status_code,404)
            actor.id=owner
            with self.engine.begin() as conn:
                conn.execute(self.text('DELETE FROM project_paper WHERE project_id=:p'),{'p':project})
            read=await client.get(url);self.assertEqual(read.json()['document']['findings'][0]['source']['kind'],'redacted')
            self.assertNotIn('Exact result',read.text)
            again=await client.put(url,json={'document':read.json()['document']},headers={'If-Match':tag})
            self.assertEqual(again.status_code,200,again.text)
            with self.Session() as db:
                self.assertEqual(db.get(ProjectInvestigation,project).document['findings'][0]['source']['quote'],'Exact result α.')

    async def test_concurrent_first_save_has_one_winner(self):
        from fastapi import HTTPException
        from app.services.investigation import save,etag
        from app.schemas.investigation import SaveInvestigation,InvestigationDocument
        owner,_,_,project,_=self.seed()
        def write(_):
            with self.Session() as db:
                try: save(db,project,owner,SaveInvestigation(document=InvestigationDocument()),etag(project,0));return 200
                except HTTPException as error:return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool: outcomes=list(pool.map(write,range(2)))
        self.assertEqual(sorted(outcomes),[200,412])

    async def test_concurrent_update_and_failed_commit_are_atomic(self):
        from unittest.mock import patch
        from fastapi import HTTPException
        from app.services import investigation as service
        from app.schemas.investigation import SaveInvestigation,InvestigationDocument
        owner,_,_,project,_=self.seed()
        request=SaveInvestigation(document=InvestigationDocument())
        with self.Session() as db:service.save(db,project,owner,request,service.etag(project,0))
        def write(index):
            with self.Session() as db:
                update=request.model_copy(deep=True);update.document.case.question=str(index)
                try:service.save(db,project,owner,update,service.etag(project,1));return 200
                except HTTPException as error:return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(write,range(2)))
        self.assertEqual(sorted(outcomes),[200,412])
        with self.Session() as db:
            row,before=service.read_document(db,project)
            with patch.object(db,'commit',side_effect=RuntimeError('Synthetic commit failure')):
                with self.assertRaises(RuntimeError):service.save(db,project,owner,request,service.etag(project,2))
            row,after=service.read_document(db,project)
            self.assertEqual(row.revision,2);self.assertEqual(before,after)

    async def test_anchor_forgery_unicode_crlf_and_revoked_http_access(self):
        import copy
        import httpx
        from fastapi import FastAPI
        from app.api.projects.project_investigation_api import investigation_router
        from app.auth.dependencies import get_required_user
        from app.database.database import get_db
        from app.services.investigation import text_hash
        owner,editor,outsider,project,paper=self.seed();actor=SimpleNamespace(id=owner)
        raw='Unicode 😀\r\nExact café 文.\r\n';quote='Exact café 文.\r'
        with self.engine.begin() as conn:conn.execute(self.text('UPDATE papers SET raw_content=:raw WHERE id=:p'),{'raw':raw,'p':paper})
        app=FastAPI();app.include_router(investigation_router,prefix='/api/projects')
        app.dependency_overrides[get_required_user]=lambda:actor
        def sessions():
            with self.Session() as db:yield db
        app.dependency_overrides[get_db]=sessions
        url=f'/api/projects/{project}/investigation'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            initial=await client.get(url);document=initial.json()['document'];tag=initial.headers['etag']
            read=await client.get(url+f'/sources/{paper}?start_line=2&line_count=1')
            self.assertEqual(read.json()['text'],quote);self.assertEqual(read.json()['source_sha256'],text_hash(raw))
            self.assertEqual((await client.get(url+f'/sources/{uuid4()}')).status_code,404)
            document['findings']=[{'id':str(uuid4()),'label':'Unicode quotation','source':{'kind':'anchored','paper_id':str(paper),'start_line':2,'end_line':2,'quote':quote,'quote_sha256':text_hash(quote),'source_sha256':text_hash(raw)}}]
            for key,value,expected in [('quote','Fabricated',422),('quote_sha256','0'*64,422),('source_sha256','0'*64,409),('paper_id',str(uuid4()),422)]:
                invalid=copy.deepcopy(document);invalid['findings'][0]['source'][key]=value
                response=await client.put(url,json={'document':invalid},headers={'If-Match':tag})
                self.assertEqual(response.status_code,expected,response.text)
                self.assertEqual((await client.get(url)).json()['revision'],0)
            self.assertEqual((await client.put(url,json={'document':document},headers={'If-Match':'bad'})).status_code,400)
            saved=await client.put(url,json={'document':document},headers={'If-Match':tag})
            self.assertEqual(saved.status_code,200,saved.text);tag=saved.headers['etag']
            actor.id=editor
            for role in ('admin','editor'):
                with self.engine.begin() as conn:conn.execute(self.text('UPDATE project_role SET role=:role WHERE project_id=:p AND user_id=:u'),{'role':role,'p':project,'u':editor})
                response=await client.put(url,json={'document':saved.json()['document']},headers={'If-Match':tag})
                self.assertEqual(response.status_code,200,response.text);tag=response.headers['etag']
            with self.engine.begin() as conn:conn.execute(self.text('DELETE FROM project_role WHERE project_id=:p AND user_id=:u'),{'p':project,'u':editor})
            for path in (url,url+'/export',url+f'/sources/{paper}'):
                response=await client.get(path);self.assertEqual(response.status_code,404);self.assertNotIn(quote,response.text)
            self.assertEqual((await client.put(url,json={'document':document},headers={'If-Match':tag})).status_code,404)
            app.dependency_overrides.pop(get_required_user)
            self.assertEqual((await client.get(url)).status_code,401)

    async def test_additive_migration_upgrade_downgrade_upgrade(self):
        import importlib.util
        from pathlib import Path
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        owner,_,_,project,_=self.seed()
        spec=importlib.util.spec_from_file_location('investigation_migration',Path(__file__).resolve().parents[1]/'migrations/versions/2026_11_11_0100_project_investigation.py')
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        with self.engine.begin() as conn:
            conn.execute(self.text('CREATE TABLE conversations (id uuid PRIMARY KEY)'))
            conn.execute(self.text('CREATE TABLE messages (id uuid PRIMARY KEY)'))
            conn.execute(self.text('DROP TABLE project_investigations'))
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade();migration.downgrade();migration.upgrade()
            self.assertEqual(conn.execute(self.text('SELECT description FROM project WHERE id=:p'),{'p':project}).scalar_one(),'Keep legacy description')
            self.assertEqual(conn.execute(self.text("SELECT count(*) FROM information_schema.tables WHERE table_schema=:s AND table_name IN ('project_investigations','project_draft_requests')"),{'s':self.schema}).scalar_one(),2)
            conn.execute(self.text('DROP TABLE project_draft_requests'))
            conn.execute(self.text('DROP TABLE conversations'))
            conn.execute(self.text('DROP TABLE messages'))

    async def test_long_source_quote_remains_roundtrippable(self):
        from app.services import investigation as service
        from app.schemas.investigation import InvestigationDocument,SaveInvestigation
        owner,_,_,project,paper=self.seed();quote='q'*10001
        with self.engine.begin() as conn:conn.execute(self.text('UPDATE papers SET raw_content=:text WHERE id=:p'),{'text':quote,'p':paper})
        fid=str(uuid4())
        document=InvestigationDocument.model_validate({'findings':[{'id':fid,'label':'Long exact quotation','source':{'kind':'anchored','paper_id':str(paper),'start_line':1,'end_line':1,'quote':quote,'quote_sha256':service.text_hash(quote),'source_sha256':service.text_hash(quote)}}],'manuscript':{'sections':[{'id':str(uuid4()),'title':'Quoted source','blocks':[{'id':str(uuid4()),'kind':'source_quote','finding_ids':[fid]}]}]}})
        with self.Session() as db:
            row,document=service.save(db,project,owner,SaveInvestigation(document=document),service.etag(project,0))
            view=service.representation(db,project,row,document)
            self.assertEqual(view['document']['manuscript']['sections'][0]['blocks'][0]['text'],'')
            self.assertEqual(view['document']['findings'][0]['source']['quote'],quote)
            service.save(db,project,owner,SaveInvestigation.model_validate({'document':view['document']}),service.etag(project,1))

    async def test_rebinding_preserves_quotation_snapshot_until_explicit_review(self):
        from app.services import investigation as service
        from app.services.investigation_export import export_document
        from app.schemas.investigation import InvestigationDocument,SaveInvestigation
        owner,_,_,project,paper=self.seed();fid,bid=str(uuid4()),str(uuid4())
        original='Exact result α.';replacement='Replacement source wording.'
        document=InvestigationDocument.model_validate({'findings':[{'id':fid,'label':'Quoted result','source':{'kind':'anchored','paper_id':str(paper),'start_line':2,'end_line':2,'quote':original,'quote_sha256':service.text_hash(original),'source_sha256':service.text_hash('Title\n'+original+'\nLimitations.')}}],'manuscript':{'sections':[{'id':str(uuid4()),'title':'Source quotations','blocks':[{'id':bid,'kind':'source_quote','finding_ids':[fid]}]}]}})
        with self.Session() as db:
            row,document=service.save(db,project,owner,SaveInvestigation(document=document),service.etag(project,0))
            self.assertEqual(document['manuscript']['sections'][0]['blocks'][0]['quote_snapshot']['quote'],original)
            raw='Title\n'+replacement+'\nLimitations.'
            with self.engine.begin() as conn:conn.execute(self.text('UPDATE papers SET raw_content=:raw WHERE id=:p'),{'raw':raw,'p':paper})
            document['findings'][0]['source'].update(quote=replacement,quote_sha256=service.text_hash(replacement),source_sha256=service.text_hash(raw))
            # Client snapshot tampering is ignored; canonical insertion capture wins.
            document['manuscript']['sections'][0]['blocks'][0]['quote_snapshot']['quote']='Forged replacement'
            row,document=service.save(db,project,owner,SaveInvestigation.model_validate({'document':document}),service.etag(project,1))
            view=service.representation(db,project,row,document)
            self.assertEqual(view['document']['manuscript']['sections'][0]['blocks'][0]['quote_snapshot']['quote'],original)
            self.assertEqual(view['validation']['blocks'][bid],'review_needed')
            exported,_,_=export_document(view,project,'markdown')
            self.assertIn(original,exported);self.assertNotIn(replacement,exported)
            row,document=service.save(db,project,owner,SaveInvestigation.model_validate({'document':view['document'],'reviewed_block_ids':[bid]}),service.etag(project,2))
            view=service.representation(db,project,row,document)
            self.assertEqual(view['document']['manuscript']['sections'][0]['blocks'][0]['quote_snapshot']['quote'],replacement)
            self.assertEqual(view['validation']['blocks'][bid],'current')
            with self.engine.begin() as conn:conn.execute(self.text('DELETE FROM project_paper WHERE project_id=:p'),{'p':project})
            _,document=service.read_document(db,project);view=service.representation(db,project,row,document)
            self.assertNotIn(replacement,str(view));self.assertNotIn(original,str(view))
            self.assertEqual(view['document']['manuscript']['sections'][0]['blocks'][0]['quote_snapshot']['kind'],'redacted')
            row,document=service.save(db,project,owner,SaveInvestigation.model_validate({'document':view['document']}),service.etag(project,3))
            self.assertEqual(document['manuscript']['sections'][0]['blocks'][0]['quote_snapshot']['quote'],replacement)

    async def test_canonical_two_source_fixture_journey_and_exports(self):
        import json
        import httpx
        from pathlib import Path
        from fastapi import FastAPI
        from app.api.projects.project_investigation_api import investigation_router
        from app.auth.dependencies import get_required_user
        from app.database.database import get_db
        from app.services.investigation import text_hash
        fixture=json.loads((Path(__file__).resolve().parents[2]/'docs/work/investigation-workspace-fixture.json').read_text())
        owner=fixture['actors']['owner'];project=fixture['project']['id'];actor=SimpleNamespace(id=UUID(owner))
        with self.engine.begin() as conn:
            for uid in fixture['actors'].values():conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u,:e,'google',:e,true,false,true)"),{'u':uid,'e':uid+'@test.invalid'})
            conn.execute(self.text("INSERT INTO project (id,admin_id,title,description) VALUES (:p,:u,:title,'Preserve fixture legacy brief')"),{'p':project,'u':owner,'title':fixture['project']['title']})
            for source in fixture['sources']:
                conn.execute(self.text("INSERT INTO papers (id,user_id,file_url,status,title,raw_content) VALUES (:p,:u,'x','reading',:title,:text)"),{'p':source['id'],'u':owner,'title':source['title'],'text':source['raw_content']})
                conn.execute(self.text('INSERT INTO project_paper (id,project_id,paper_id) VALUES (:id,:p,:paper)'),{'id':uuid4(),'p':project,'paper':source['id']})
        app=FastAPI();app.include_router(investigation_router,prefix='/api/projects')
        app.dependency_overrides[get_required_user]=lambda:actor
        def sessions():
            with self.Session() as db:yield db
        app.dependency_overrides[get_db]=sessions
        url=f'/api/projects/{project}/investigation'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            initial=await client.get(url);document=initial.json()['document']
            document['case'].update(question='Does signaling affect agreement?',reconciliation=fixture['reconciliation'],discriminating_experiment=fixture['discriminating_experiment'])
            document['claims']=[fixture['claim']]
            document['findings']=[];document['relations']=[]
            for item in fixture['findings']:
                source=next(s for s in fixture['sources'] if s['id']==item['paper_id'])
                read=await client.get(url+f"/sources/{source['id']}?start_line=2&line_count=1")
                self.assertEqual(read.json()['text'],source['quote'])
                document['findings'].append({'id':item['id'],'label':item['label'],'setup':item['setup'],'source':{'kind':'anchored','paper_id':source['id'],'start_line':2,'end_line':2,'quote':source['quote'],'quote_sha256':text_hash(source['quote']),'source_sha256':text_hash(source['raw_content'])}})
                document['relations'].append({'id':str(uuid4()),'claim_id':fixture['claim']['id'],'finding_id':item['id'],'relation':item['relation_to_claim']})
            block_id=str(uuid4())
            document['manuscript']['sections']=[{'id':str(uuid4()),'title':'Evidence and reconciliation','blocks':[{'id':block_id,'kind':'paragraph','text':fixture['expected_paragraph'],'claim_ids':[fixture['claim']['id']],'finding_ids':[f['id'] for f in fixture['findings']]}]}]
            saved=await client.put(url,json={'document':document},headers={'If-Match':initial.headers['etag']})
            self.assertEqual(saved.status_code,200,saved.text)
            reloaded=await client.get(url)
            self.assertEqual(reloaded.json()['document']['manuscript']['sections'][0]['blocks'][0]['text'],fixture['expected_paragraph'])
            self.assertEqual(reloaded.json()['validation']['blocks'][block_id],'current')
            source_a,source_b=fixture['sources']
            with self.engine.begin() as conn:
                conn.execute(self.text('UPDATE papers SET raw_content=:text WHERE id=:p'),{'text':source_a['replacement_raw_content'],'p':source_a['id']})
                conn.execute(self.text('DELETE FROM project_paper WHERE project_id=:p AND paper_id=:paper'),{'p':project,'paper':source_b['id']})
            changed=await client.get(url);body=changed.json()
            self.assertEqual(body['validation']['findings'][fixture['findings'][0]['id']],'source_changed')
            self.assertEqual(body['validation']['findings'][fixture['findings'][1]['id']],'unavailable')
            self.assertEqual(body['validation']['blocks'][block_id],'review_needed')
            self.assertEqual(body['document']['manuscript']['sections'][0]['blocks'][0]['text'],fixture['expected_paragraph'])
            self.assertEqual(body['document']['findings'][0]['source']['quote'],source_a['quote'])
            self.assertNotIn(source_b['quote'],changed.text)
            for format in ('bundle','markdown','bibtex'):
                exported=await client.get(url+'/export?format='+format)
                self.assertEqual(exported.status_code,200,exported.text)
                self.assertNotIn(source_b['quote'],exported.text)
                self.assertIn('no-store',exported.headers['cache-control'])
            bundle=(await client.get(url+'/export?format=bundle')).json()
            imported=await client.post(url+'/import/preview',json=bundle)
            self.assertEqual(imported.status_code,200,imported.text)
            preview=imported.json()['document']
            self.assertTrue(all(f['source']['kind']=='unbound' for f in preview['findings']))
            self.assertNotEqual(preview['claims'][0]['id'],fixture['claim']['id'])
            self.assertEqual(preview['manuscript']['sections'][0]['blocks'][0]['provenance']['kind'],'imported')
