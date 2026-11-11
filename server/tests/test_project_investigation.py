import copy
import unittest
from uuid import uuid4
from pydantic import ValidationError
from app.schemas.investigation import InvestigationDocument

class InvestigationSchemaTests(unittest.TestCase):
    def test_empty_virtual_document(self):
        doc=InvestigationDocument()
        self.assertEqual(doc.case.question,'')
        self.assertEqual(doc.findings,[])

    def test_strict_version_and_unknown_fields(self):
        for change in ({'version':True},{'version':1.0},{'version':2},{'unexpected':'x'}):
            with self.assertRaises(ValidationError): InvestigationDocument.model_validate(change)

    def test_graph_duplicate_ids_and_dangling_relations(self):
        claim={'id':str(uuid4()),'statement':'Qualified result'}
        document={'claims':[claim]}
        InvestigationDocument.model_validate(document)
        for changes in ({'claims':[claim,claim]},{'relations':[{'id':str(uuid4()),'claim_id':claim['id'],'finding_id':str(uuid4()),'relation':'supports'}]}):
            with self.assertRaises(ValidationError): InvestigationDocument.model_validate(document|changes)

    def test_source_and_quote_references(self):
        finding={'id':str(uuid4()),'label':'Unbound','source':{'kind':'unbound'}}
        block={'id':str(uuid4()),'kind':'source_quote','finding_ids':[finding['id']]}
        document={'findings':[finding],'manuscript':{'sections':[{'id':str(uuid4()),'title':'Evidence','blocks':[block]}]}}
        InvestigationDocument.model_validate(document)
        for changes in ({'finding_ids':[]},{'finding_ids':[finding['id'],finding['id']]},{'claim_ids':[str(uuid4())]}):
            d=copy.deepcopy(document);d['manuscript']['sections'][0]['blocks'][0].update(changes)
            with self.assertRaises(ValidationError): InvestigationDocument.model_validate(d)

    def test_utf8_bound_and_field_bound(self):
        with self.assertRaises(ValidationError): InvestigationDocument.model_validate({'case':{'question':'x'*20001}})
        claims=[{'id':str(uuid4()),'statement':'s','reasoning':'文'*20000} for _ in range(34)]
        with self.assertRaises(ValidationError): InvestigationDocument.model_validate({'claims':claims})

    def test_portable_export_escapes_hostile_prose(self):
        from app.services.investigation_export import export_document
        document=InvestigationDocument().model_dump(mode='json')
        document['manuscript']['title']='<script>alert(1)</script>'
        document['manuscript']['sections']=[{'id':str(uuid4()),'title':'Draft','blocks':[{'id':str(uuid4()),'kind':'paragraph','text':'[click](javascript:alert(1)) <iframe src=x>','finding_ids':[],'provenance':{'kind':'human'}}]}]
        body={'document':document,'revision':1,'validation':{'findings':{},'blocks':{}}}
        output,media,extension=export_document(body,uuid4(),'markdown')
        self.assertNotIn('<script>',output)
        self.assertNotIn('<iframe',output)
        self.assertIn('[Uncited]',output)
        self.assertEqual(extension,'md')
        self.assertEqual(media,'text/markdown')

    def test_single_additive_migration_head(self):
        from pathlib import Path
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        config=Config();config.set_main_option('script_location',str(Path(__file__).resolve().parents[1]/'migrations'))
        script=ScriptDirectory.from_config(config)
        self.assertEqual(script.get_heads(),['project_investigation_01'])
        self.assertEqual(script.get_revision('project_investigation_01').down_revision,'project_research_brief_01')

    def test_all_dependency_edits_change_pins(self):
        from app.services.investigation import pins
        cid,fid=str(uuid4()),str(uuid4())
        document=InvestigationDocument.model_validate({'claims':[{'id':cid,'statement':'Conditional'}],'findings':[{'id':fid,'label':'A','source':{'kind':'unbound'}}],'relations':[{'id':str(uuid4()),'claim_id':cid,'finding_id':fid,'relation':'supports'}]}).model_dump(mode='json')
        block={'claim_ids':[cid],'finding_ids':[fid]};before=pins(document,block)
        for collection,key,value in [('claims','caveats','New limitation'),('claims','archived',True),('findings','our_interpretation','Different inference'),('findings','archived',True),('relations','relation','qualifies'),('relations','rationale','Setup differs')]:
            changed=copy.deepcopy(document);changed[collection][0][key]=value
            self.assertNotEqual(pins(changed,block),before)
        changed=copy.deepcopy(document);changed['findings'][0]['setup']['task']='Different task'
        self.assertNotEqual(pins(changed,block),before)
