"""Project-local source validation and atomic investigation persistence."""
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import UUID
from types import SimpleNamespace
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session
from app.database.models import Paper, Project, ProjectRole, ProjectPaper, ProjectInvestigation, ProjectDraftRequest, Message, ResearchProject
from app.schemas.investigation import InvestigationDocument


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",", ":")).encode()).hexdigest()


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def access(db, project_id, actor_id, *, write=False, lock=False):
    query=db.query(Project).filter(Project.id==project_id)
    if lock: query=query.with_for_update()
    project=query.first()
    if not project: raise HTTPException(404,"Project not found")
    roles=db.query(ProjectRole).filter(ProjectRole.project_id==project_id,ProjectRole.user_id==actor_id)
    if lock: roles=roles.with_for_update()
    role=roles.first()
    if project.admin_id != actor_id and role is None: raise HTTPException(404,"Project not found")
    if write and project.admin_id != actor_id and role.role not in ("admin","editor"):
        raise HTTPException(403,"Editing requires an editor role")
    return project


def sources(db, project_id, document, *, lock=False):
    ids={UUID(f['source']['paper_id']) for f in document['findings'] if f['source']['kind'] in ('anchored','redacted')}
    ids.update(UUID(b['quote_snapshot']['paper_id']) for s in document['manuscript']['sections'] for b in s['blocks'] if b.get('quote_snapshot'))
    if not ids: return {}
    associations=db.query(ProjectPaper).filter(ProjectPaper.project_id==project_id,ProjectPaper.paper_id.in_(ids))
    if lock: associations=associations.with_for_update()
    allowed={row.paper_id for row in associations.all()}
    if not allowed: return {}
    query=db.query(Paper.id,Paper.raw_content,Paper.title,Paper.authors,Paper.publish_date,Paper.doi).filter(Paper.id.in_(allowed))
    if lock: query=query.with_for_update()
    # Retain bounded quotations/metadata; release each full extracted paper before
    # fetching the next one instead of accumulating every raw_content in memory.
    result={}
    for row in query.yield_per(1):
        pid=str(row.id);quotations={}
        if lock and row.raw_content:
            lines=row.raw_content.split('\n')
            for finding in document['findings']:
                source=finding['source']
                if source['kind']=='anchored' and source['paper_id']==pid and source['end_line']<=len(lines):
                    if source['end_line']-source['start_line']>20000:continue
                    selected=lines[source['start_line']-1:source['end_line']]
                    if sum(map(len,selected))+len(selected)-1<=20000:
                        quotations[finding['id']]='\n'.join(selected)
        result[pid]=SimpleNamespace(id=row.id,title=row.title,authors=row.authors,publish_date=row.publish_date,doi=row.doi,
            source_sha256=text_hash(row.raw_content) if row.raw_content else None,quotations=quotations)
    return result


def pins(document, block):
    claim_ids=set(block['claim_ids']); finding_ids=set(block['finding_ids'])
    result={}
    for claim in document['claims']:
        if claim['id'] in claim_ids: result['claim:'+claim['id']]=digest(claim)
    for finding in document['findings']:
        if finding['id'] in finding_ids:
            result['finding:'+finding['id']]=digest({k:v for k,v in finding.items() if k!='label'})
    for relation in document['relations']:
        if relation['claim_id'] in claim_ids or relation['finding_id'] in finding_ids:
            result['relation:'+relation['id']]=digest(relation)
    return result


def read_document(db, project_id):
    row=db.get(ProjectInvestigation,project_id)
    document=copy.deepcopy(row.document) if row else InvestigationDocument().model_dump(mode='json')
    return row,document


def representation(db, project_id, row, document):
    available=sources(db,project_id,document)
    validation={'findings':{},'blocks':{}}
    hashes={pid:p.source_sha256 for pid,p in available.items() if p.source_sha256}
    for finding in document['findings']:
        source=finding['source'];kind=source['kind']
        status='unbound'
        if kind=='anchored':
            status='current' if hashes.get(source['paper_id'])==source['source_sha256'] else ('source_changed' if source['paper_id'] in hashes else 'unavailable')
        validation['findings'][finding['id']]=status
    for section in document['manuscript']['sections']:
        for block in section['blocks']:
            stale=block['dependency_pins']!=pins(document,block)
            unavailable=any(validation['findings'][fid]=='unavailable' for fid in block['finding_ids'])
            changed=any(validation['findings'][fid]!='current' for fid in block['finding_ids'])
            archived=any(x['archived'] for x in document['claims'] if x['id'] in block['claim_ids']) or any(x['archived'] for x in document['findings'] if x['id'] in block['finding_ids'])
            validation['blocks'][block['id']]='review_needed' if stale or changed or archived or (block['provenance']['kind']=='imported' and not block['provenance'].get('reviewed')) else 'current'
            if block['kind']=='source_quote':
                block['text']=''  # quotation display is derived from the access-checked finding
                snapshot=block.get('quote_snapshot')
                if snapshot and snapshot['paper_id'] not in hashes:
                    block['quote_snapshot']={'kind':'redacted','paper_id':snapshot['paper_id']}
                if snapshot and (snapshot['kind']!='anchored' or hashes.get(snapshot['paper_id'])!=snapshot.get('source_sha256')):
                    validation['blocks'][block['id']]='review_needed'
    for finding in document['findings']:
        if validation['findings'][finding['id']]=='unavailable':
            finding['source']={'kind':'redacted','paper_id':finding['source']['paper_id']}
    return {'document':document,'revision':row.revision if row else 0,'validation':validation}


def etag(project_id, revision):
    return f'"investigation:{project_id}:{revision}"'


def save(db:Session, project_id, actor_id, request, if_match):
    try:
        access(db,project_id,actor_id,write=True,lock=True)
        # One authoritative write path: after research-core conversion the v1 document is
        # retained read-only history and legacy writes are refused (strategy 10.6).
        root=db.query(ResearchProject).filter(ResearchProject.project_id==project_id).with_for_update().first()
        if root and root.storage_generation=='v2':
            raise HTTPException(409,'Research storage is converted; legacy investigation writes are refused')
        row,old=read_document(db,project_id)
        current=etag(project_id,row.revision if row else 0)
        if if_match is None: raise HTTPException(428,'If-Match is required')
        if not re.fullmatch(r'"investigation:[0-9a-fA-F-]{36}:[0-9]+"',if_match): raise HTTPException(400,'Malformed If-Match')
        try: UUID(if_match.split(':')[1])
        except ValueError as error:raise HTTPException(400,'Malformed If-Match') from error
        if if_match!=current: raise HTTPException(412,'Investigation changed',headers={'ETag':current})
        document=request.document.model_dump(mode='json')
        old_findings={f['id']:f for f in old['findings']}
        old_blocks={b['id']:b for s in old['manuscript']['sections'] for b in s['blocks']}
        # Never trust a client/import quotation snapshot as a source grant.
        reviewed={str(i) for i in request.reviewed_block_ids}
        for section in document['manuscript']['sections']:
            for block in section['blocks']:
                previous=old_blocks.get(block['id'])
                if block['kind']=='source_quote':
                    finding=next(f for f in document['findings'] if f['id']==block['finding_ids'][0])
                    block['quote_snapshot']=copy.deepcopy(previous.get('quote_snapshot')) if previous and block['id'] not in reviewed else None
                else:block['quote_snapshot']=None
        for finding in document['findings']:
            if finding['source']['kind']=='redacted':
                previous=old_findings.get(finding['id'])
                if not previous or previous['source'].get('paper_id')!=finding['source']['paper_id']:
                    raise HTTPException(422,'Invalid redacted source')
                finding['source']=copy.deepcopy(previous['source'])
        available=sources(db,project_id,document,lock=True)
        hashes={pid:p.source_sha256 for pid,p in available.items() if p.source_sha256}
        for finding in document['findings']:
            source=finding['source']; previous=old_findings.get(finding['id'])
            if source['kind']!='anchored': continue
            if previous and source==previous['source']: continue
            paper=available.get(source['paper_id'])
            if not paper or not paper.source_sha256: raise HTTPException(422,'Source is unavailable in this project')
            if hashes[source['paper_id']]!=source['source_sha256']: raise HTTPException(409,'Source changed')
            quote=paper.quotations.get(finding['id'])
            if quote is None:raise HTTPException(422,'Source range exceeds text')
            if quote!=source['quote'] or text_hash(quote)!=source['quote_sha256']: raise HTTPException(422,'Quotation does not match exact source lines')
            source.update(title=paper.title or '',authors=paper.authors or [],doi=paper.doi,page_span=None,publish_date=paper.publish_date)
        blocks=[b for s in document['manuscript']['sections'] for b in s['blocks']]
        if not reviewed<={b['id'] for b in blocks}: raise HTTPException(422,'Unknown reviewed block')
        for block in blocks:
            previous=old_blocks.get(block['id'])
            if block['kind']=='source_quote':
                block['text']=''
                if not previous or block['id'] in reviewed:
                    source=next(f for f in document['findings'] if f['id']==block['finding_ids'][0])['source']
                    block['quote_snapshot']=copy.deepcopy(source) if source['kind']=='anchored' else None
            for key,value in {'inserted_at':datetime.now(timezone.utc).isoformat(),'inserted_by':str(actor_id)}.items():
                block['provenance'][key]=previous['provenance'].get(key) if previous else value
            if previous and previous['provenance']['kind']=='imported':
                block['provenance']['kind']='imported'
                block['provenance']['origin_label']=previous['provenance'].get('origin_label')
                block['provenance']['original_ids']=previous['provenance'].get('original_ids',[])
            if block['provenance']['kind']=='imported':
                block['provenance']['reviewed']=bool(previous and previous['provenance'].get('reviewed'))
                block['provenance']['request_id']=None;block['provenance']['message_id']=None
            preserved_assistant=previous and previous['provenance']['kind']=='assistant'
            if preserved_assistant:
                if any(block['provenance'].get(key)!=previous['provenance'].get(key) for key in ('kind','request_id','message_id')):
                    raise HTTPException(422,'Cannot erase or replace assistant provenance')
                if not set(block['finding_ids'])<=set(previous['finding_ids']) or not set(block['claim_ids'])<=set(previous['claim_ids']):
                    raise HTTPException(422,'Retained assistant references require their original validated selection')
                block['provenance']=copy.deepcopy(previous['provenance'])
                block['provenance']['edited']=bool(previous['provenance'].get('edited')) or block['text']!=previous['text']
            elif block['provenance']['kind']=='assistant':
                provenance=block['provenance']
                request_row=db.get(ProjectDraftRequest,UUID(provenance['request_id']))
                message=db.get(Message,UUID(provenance['message_id']))
                if (not request_row or request_row.project_id!=project_id or request_row.requester_id!=actor_id
                    or request_row.state!='completed' or str(request_row.message_id)!=provenance['message_id']
                    or not message or message.conversation_id!=request_row.conversation_id):
                    raise HTTPException(422,'Invalid assistant provenance')
                if not set(block['finding_ids'])<=set((message.references or {}).get('investigation',{}).get('finding_ids',[])):
                    raise HTTPException(422,'Assistant citations were not validated')
                if not set(block['claim_ids'])<=set(request_row.snapshot['payload']['claim_ids']):
                    raise HTTPException(422,'Assistant claim selection is invalid')
                from app.services.investigation_drafting import chosen_context
                payload=request_row.snapshot['payload']
                submitted_context=chosen_context(db,project_id,document,payload['claim_ids'],payload['finding_ids'])
                stale=row.revision!=request_row.base_revision or digest(submitted_context)!=request_row.snapshot['context_digest']
                if stale and provenance['request_id'] not in {str(i) for i in request.reviewed_proposal_ids}:
                    raise HTTPException(409,'Proposal requires explicit review against submitted workspace and evidence')
                if not any(s['id']==str(request_row.section_id) and block in s['blocks'] for s in document['manuscript']['sections']):
                    raise HTTPException(409,'Proposal target section changed')
                provenance['edited']=block['text']!=message.content
            if previous and block['id'] not in reviewed:
                block['dependency_pins']=previous['dependency_pins']
            elif not previous and block['provenance']['kind']=='imported' and block['id'] not in reviewed:
                block['dependency_pins']={}
            else:
                if any(claim['archived'] for claim in document['claims'] if claim['id'] in block['claim_ids']):raise HTTPException(409,'Archived claim requires current review')
                for fid in block['finding_ids']:
                    finding=next(f for f in document['findings'] if f['id']==fid)
                    source=finding['source']
                    if finding['archived'] or source['kind']!='anchored' or hashes.get(source['paper_id'])!=source['source_sha256']:
                        raise HTTPException(409,'Review requires current accessible evidence')
                block['dependency_pins']=pins(document,block)
                if block['provenance']['kind']=='imported' and block['id'] in reviewed:block['provenance']['reviewed']=True
        try:InvestigationDocument.model_validate(document)
        except ValidationError as error:
            if len(json.dumps(document,ensure_ascii=False,separators=(',',':')).encode())>2_000_000:raise HTTPException(413,'Canonical investigation exceeds byte limit') from error
            raise HTTPException(422,'Canonical source metadata violates document bounds') from error
        if row is None:
            row=ProjectInvestigation(project_id=project_id,schema_version=1,revision=1,document=document,updated_by=actor_id)
            db.add(row)
        else:
            row.document=document;row.revision+=1;row.updated_by=actor_id
        db.commit()
        return row,document
    except Exception:
        db.rollback()
        raise
