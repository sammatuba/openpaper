"""Fake-provider request identity and bounded proposal validation."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from app.services.investigation_drafting import proposal

class ProposalTests(unittest.TestCase):
    def test_known_markers_and_uncited_prose(self):
        fid=str(uuid4());result=proposal('Qualified result [[finding:'+fid+']]',[fid])
        self.assertEqual(result['finding_ids'],[fid])
        self.assertTrue(proposal('[1] https://example.org',[])['uncited'])

    def test_invalid_empty_and_oversize_output(self):
        for text in ('','   ','x'*10001,'Invented [[finding:'+str(uuid4())+']]'):
            with self.assertRaises(ValueError):proposal(text,[])

@unittest.skipUnless(os.environ.get('OPENPAPER_ISOLATED_PG_TEST')=='1','requires isolated PostgreSQL')
class DraftRequestPostgresTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_project_investigation_postgres import InvestigationPostgresTests
        InvestigationPostgresTests.setUpClass.__func__(cls)
        from app.database.models import Conversation,Message,ProjectDraftRequest
        with cls.engine.begin() as conn:
            for model in (Conversation,Message,ProjectDraftRequest):model.__table__.create(conn)

    @classmethod
    def tearDownClass(cls):
        from tests.test_project_investigation_postgres import InvestigationPostgresTests
        InvestigationPostgresTests.tearDownClass.__func__(cls)

    def seed(self):
        from tests.test_project_investigation_postgres import InvestigationPostgresTests
        return InvestigationPostgresTests.seed(self)

    async def test_create_replay_run_and_saved_message_accounting(self):
        from app.services import investigation as workspace
        from app.services import investigation_drafting as drafts
        from app.schemas.investigation import InvestigationDocument,SaveInvestigation,CreateDraftRequest
        from app.llm.provider import LLMProvider,StreamChunk
        from app.database.models import Message,ProjectDraftRequest
        from fastapi import HTTPException
        owner,_,_,project,paper=self.seed();actor=SimpleNamespace(id=owner)
        fid,section=str(uuid4()),str(uuid4())
        document=InvestigationDocument.model_validate({'findings':[{'id':fid,'label':'Synthetic result','source':{'kind':'anchored','paper_id':str(paper),'start_line':2,'end_line':2,'quote':'Exact result α.','source_sha256':workspace.text_hash('Title\nExact result α.\nLimitations.'),'quote_sha256':workspace.text_hash('Exact result α.')}}],'manuscript':{'sections':[{'id':section,'title':'Evidence'}]}})
        with self.Session() as db:workspace.save(db,project,owner,SaveInvestigation(document=document),workspace.etag(project,0))
        request=CreateDraftRequest(id=uuid4(),base_revision=1,section_id=section,finding_ids=[fid],provider='gemini')
        class Fake:
            calls=0
            def get_chat_model_options(self):return {LLMProvider.GEMINI:'fake'}
            async def _stream(self,*args,**kwargs):
                self.calls+=1
                assert kwargs['single_attempt'] is True
                yield StreamChunk('Qualified synthetic result [[finding:'+fid+']]',model='fake',provider=LLMProvider.GEMINI)
        fake=Fake()
        with patch.object(drafts,'client',return_value=fake),patch.object(drafts,'quota'):
            with self.Session() as db:
                first=drafts.create(db,project,actor,request);self.assertEqual(first.state,'pending')
                second=drafts.create(db,project,actor,request);self.assertEqual(first.id,second.id)
                self.assertEqual(fake.calls,0)
                changed=request.model_copy(update={'instructions':'Different payload'})
                with self.assertRaises(HTTPException) as error:drafts.create(db,project,actor,changed)
                self.assertEqual(error.exception.status_code,409)
                stream=await drafts.run(db,project,actor,request.id)
                chunks=[chunk async for chunk in stream]
                self.assertTrue(any('complete' in chunk for chunk in chunks));self.assertEqual(fake.calls,1)
                read=drafts.status(db,project,actor,request.id);self.assertEqual(read['state'],'completed')
                self.assertEqual(read['proposal']['finding_ids'],[fid])
                with self.assertRaises(HTTPException) as error:await drafts.run(db,project,actor,request.id)
                self.assertEqual(error.exception.status_code,409);self.assertEqual(fake.calls,1)
                self.assertEqual(db.query(Message).filter(Message.conversation_id==first.conversation_id).count(),2)
                # Submitted evidence edits require explicit proposal acknowledgment even at the original revision.
                _,saved_document=workspace.read_document(db,project)
                saved_document['findings'][0]['our_interpretation']='A new qualification submitted alongside insertion.'
                saved_document['manuscript']['sections'][0]['blocks']=[{'id':str(uuid4()),'kind':'paragraph','text':read['proposal']['text'],'finding_ids':[fid],'provenance':{'kind':'assistant','request_id':str(request.id),'message_id':read['proposal']['message_id']}}]
                update=SaveInvestigation.model_validate({'document':saved_document})
                with self.assertRaises(HTTPException) as error:workspace.save(db,project,owner,update,workspace.etag(project,1))
                self.assertEqual(error.exception.status_code,409)
                acknowledged=SaveInvestigation.model_validate({'document':saved_document,'reviewed_proposal_ids':[str(request.id)]})
                workspace.save(db,project,owner,acknowledged,workspace.etag(project,1))
                # Deleting the result never releases the request identity.
                message_id=db.get(ProjectDraftRequest,request.id).message_id;db.execute(self.text('DELETE FROM messages WHERE id=:id'),{'id':message_id});db.commit()
                read=drafts.status(db,project,actor,request.id)
                self.assertIsNone(read['proposal']);self.assertEqual(fake.calls,1)
                # A second editor can preserve and edit an already accepted AI block after result deletion.
                with self.engine.begin() as conn:
                    editor=uuid4()
                    conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u,:e,'google',:e,true,false,true)"),{'u':editor,'e':str(editor)+'@test.invalid'})
                    conn.execute(self.text("INSERT INTO project_role (id,project_id,user_id,role) VALUES (:id,:p,:u,'editor')"),{'id':uuid4(),'p':project,'u':editor})
                _,latest=workspace.read_document(db,project)
                latest['case']['coverage_limits']='Collaborative edit retains AI provenance.'
                latest['manuscript']['sections'][0]['blocks'][0]['text']+=' Human qualification.'
                workspace.save(db,project,editor,SaveInvestigation.model_validate({'document':latest}),workspace.etag(project,2))
                _,latest=workspace.read_document(db,project)
                self.assertTrue(latest['manuscript']['sections'][0]['blocks'][0]['provenance']['edited'])


    def prepare_request(self):
        from app.services import investigation as workspace
        from app.schemas.investigation import InvestigationDocument,SaveInvestigation,CreateDraftRequest
        owner,viewer,outsider,project,paper=self.seed();fid,section=str(uuid4()),str(uuid4())
        document=InvestigationDocument.model_validate({'findings':[{'id':fid,'label':'Synthetic result','source':{'kind':'anchored','paper_id':str(paper),'start_line':2,'end_line':2,'quote':'Exact result α.','source_sha256':workspace.text_hash('Title\nExact result α.\nLimitations.'),'quote_sha256':workspace.text_hash('Exact result α.')}}],'manuscript':{'sections':[{'id':section,'title':'Evidence'}]}})
        with self.Session() as db:workspace.save(db,project,owner,SaveInvestigation(document=document),workspace.etag(project,0))
        request=CreateDraftRequest(id=uuid4(),base_revision=1,section_id=section,finding_ids=[fid],provider='gemini')
        return owner,viewer,project,paper,request

    async def test_failures_timeout_cancel_and_replay_preserve_manuscript(self):
        import asyncio
        from app.services import investigation_drafting as drafts
        from app.llm.provider import LLMProvider,StreamChunk
        from app.database.models import ProjectDraftRequest,ProjectInvestigation
        from fastapi import HTTPException
        owner,_,project,_,base_request=self.prepare_request();actor=SimpleNamespace(id=owner)
        for scenario in ('empty','invented','error','timeout','cancel'):
            with self.subTest(scenario=scenario):
                class Fake:
                    calls=0
                    def get_chat_model_options(self):return {LLMProvider.GEMINI:'fake'}
                    async def _stream(self,*args,**kwargs):
                        self.calls+=1
                        if scenario=='error':raise RuntimeError('Synthetic provider failure')
                        if scenario=='timeout':await asyncio.sleep(1)
                        if scenario=='invented':yield StreamChunk('Invented [[finding:'+str(uuid4())+']]',model='fake',provider=LLMProvider.GEMINI)
                        if scenario=='cancel':
                            yield StreamChunk('Partial content',model='fake',provider=LLMProvider.GEMINI)
                            await asyncio.sleep(1)
                        if False:yield None
                fake=Fake();request=base_request.model_copy(update={'id':uuid4()})
                with patch.object(drafts,'client',return_value=fake),patch.object(drafts,'quota'),patch.object(drafts,'DEADLINE_SECONDS',0.02):
                    with self.Session() as db:
                        drafts.create(db,project,actor,request)
                        stream=await drafts.run(db,project,actor,request.id)
                        if scenario=='cancel':await anext(stream);await stream.aclose()
                        else:chunks=[chunk async for chunk in stream];self.assertTrue(any('error' in chunk for chunk in chunks))
                        row=db.get(ProjectDraftRequest,request.id);self.assertIn(row.state,('failed','uncertain'))
                        self.assertEqual(fake.calls,1)
                        self.assertEqual(db.get(ProjectInvestigation,project).document['manuscript']['sections'][0]['blocks'],[])
                        with self.assertRaises(HTTPException):await drafts.run(db,project,actor,request.id)
                        self.assertEqual(fake.calls,1)

    async def test_duplicate_claim_quota_and_revocation(self):
        from app.services import investigation_drafting as drafts
        from app.llm.provider import LLMProvider
        from app.database.models import ProjectDraftRequest,Conversation
        from fastapi import HTTPException
        owner,editor,project,_,request=self.prepare_request();actor=SimpleNamespace(id=editor)
        with self.engine.begin() as conn:conn.execute(self.text("UPDATE project_role SET role='editor' WHERE project_id=:p AND user_id=:u"),{'p':project,'u':editor})
        fake=SimpleNamespace(get_chat_model_options=lambda:{LLMProvider.GEMINI:'fake'})
        with patch.object(drafts,'client',return_value=fake),patch.object(drafts,'quota',side_effect=HTTPException(429,'No credits')):
            with self.Session() as db:
                with self.assertRaises(HTTPException) as error:drafts.create(db,project,actor,request)
                self.assertEqual(error.exception.status_code,429)
                self.assertIsNone(db.get(ProjectDraftRequest,request.id))
                self.assertEqual(db.query(Conversation).filter(Conversation.conversable_id==project).count(),0)
        with patch.object(drafts,'client',return_value=fake),patch.object(drafts,'quota'):
            with self.Session() as db:
                drafts.create(db,project,actor,request)
                claimed=await drafts.run(db,project,actor,request.id)
                with self.assertRaises(HTTPException) as error:await drafts.run(db,project,actor,request.id)
                self.assertEqual(error.exception.status_code,409)
                # An unconsumed claimed stream stays durable; it is never reset to pending.
                await claimed.aclose()
                with self.engine.begin() as conn:conn.execute(self.text('DELETE FROM project_role WHERE project_id=:p AND user_id=:u'),{'p':project,'u':editor})
                with self.assertRaises(HTTPException) as error:drafts.status(db,project,actor,request.id)
                self.assertEqual(error.exception.status_code,404)

    async def test_concurrent_identity_and_revocation_during_stream(self):
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        from fastapi import HTTPException
        from app.services import investigation_drafting as drafts
        from app.llm.provider import LLMProvider,StreamChunk
        from app.database.models import Message,ProjectDraftRequest
        owner,editor,project,_,request=self.prepare_request();actor=SimpleNamespace(id=editor)
        with self.engine.begin() as conn:conn.execute(self.text("UPDATE project_role SET role='editor' WHERE project_id=:p AND user_id=:u"),{'p':project,'u':editor})
        class Fake:
            calls=0
            def get_chat_model_options(self):return {LLMProvider.GEMINI:'fake'}
            async def _stream(self,*args,**kwargs):
                self.calls+=1
                yield StreamChunk('Qualified synthetic result.',model='fake',provider=LLMProvider.GEMINI)
        fake=Fake()
        with patch.object(drafts,'client',return_value=fake),patch.object(drafts,'quota'):
            def create(_):
                with self.Session() as db:return drafts.create(db,project,actor,request).id
            with ThreadPoolExecutor(max_workers=2) as pool:created=list(pool.map(create,range(2)))
            self.assertEqual(created,[request.id,request.id]);self.assertEqual(fake.calls,0)
            with self.Session() as db:
                stream=await drafts.run(db,project,actor,request.id)
                first=await anext(stream);self.assertIn('content',first)
                with self.engine.begin() as conn:conn.execute(self.text('DELETE FROM project_role WHERE project_id=:p AND user_id=:u'),{'p':project,'u':editor})
                remainder=[chunk async for chunk in stream]
                self.assertFalse(any('"type": "complete"' in chunk for chunk in remainder));self.assertEqual(fake.calls,1)
                row=db.get(ProjectDraftRequest,request.id);self.assertEqual(row.state,'failed');self.assertIsNone(row.message_id)
                self.assertEqual(db.query(Message).filter(Message.conversation_id==row.conversation_id,Message.role=='assistant').count(),0)
                with self.assertRaises(HTTPException):drafts.status(db,project,actor,request.id)


class SingleAttemptProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_does_not_resample_an_empty_answer(self):
        from tests.test_empty_answer_stream import EmptyGeminiStreamTest,chunk
        from google.genai.types import FinishReason
        from app.llm.utils import EmptyStreamError
        provider,attempts=EmptyGeminiStreamTest.make_provider(self,lambda n:[chunk(None,FinishReason.MAX_TOKENS)])
        with self.assertRaises(EmptyStreamError):
            _=[item async for item in provider.send_message_stream(model='fake',message='q',history=[],system_prompt='s',single_attempt=True)]
        self.assertEqual(attempts['n'],1)

    async def test_openai_disables_sdk_and_stream_retries(self):
        from app.llm.provider import OpenAIProvider
        from app.llm.utils import EmptyStreamError
        calls=[];sdk_options=[]
        async def create(**kwargs):
            calls.append(kwargs)
            async def empty():
                if False:yield None
            return empty()
        fake=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        fake.with_options=lambda **options:(sdk_options.append(options) or fake)
        provider=OpenAIProvider.__new__(OpenAIProvider);provider._async_client=fake
        with patch.object(provider,'_prepare_openai_messages',return_value=[]):
            with self.assertRaises(EmptyStreamError):
                _=[item async for item in provider.send_message_stream(model='fake',message='q',history=[],system_prompt='s',single_attempt=True)]
        self.assertEqual(len(calls),1);self.assertEqual(sdk_options,[{'max_retries':0}])
        self.assertNotIn('single_attempt',calls[0])

    async def test_anthropic_disables_sdk_and_stream_retries(self):
        from app.llm.provider import AnthropicProvider
        from app.llm.utils import EmptyStreamError
        calls=[];sdk_options=[]
        class Empty:
            async def __aenter__(self):return self
            async def __aexit__(self,*args):return False
            @property
            def text_stream(self):
                async def empty():
                    if False:yield None
                return empty()
            async def get_final_message(self):return SimpleNamespace(usage=None)
        def stream(**kwargs):calls.append(kwargs);return Empty()
        fake=SimpleNamespace(messages=SimpleNamespace(stream=stream));fake.with_options=lambda **options:(sdk_options.append(options) or fake)
        provider=AnthropicProvider.__new__(AnthropicProvider);provider._async_client=fake
        with patch.object(provider,'_prepare_anthropic_messages',return_value=[]):
            with self.assertRaises(EmptyStreamError):
                _=[item async for item in provider.send_message_stream(model='fake',message='q',history=[],system_prompt='s',single_attempt=True)]
        self.assertEqual(len(calls),1);self.assertEqual(sdk_options,[{'max_retries':0}]);self.assertNotIn('single_attempt',calls[0])
