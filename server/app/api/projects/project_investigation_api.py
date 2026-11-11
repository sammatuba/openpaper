"""Conditional atomic investigation API; reads never create rows."""
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.auth.dependencies import get_required_user
from app.database.database import get_db
from app.database.models import Paper, ProjectPaper
from app.schemas.user import CurrentUser
from app.schemas.investigation import SaveInvestigation,CreateDraftRequest
from app.services import investigation as service

class BoundedInvestigationRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def bounded(request):
            if request.method in ('POST','PUT') and len(await request.body())>2_010_000:
                raise HTTPException(413,'Investigation request exceeds byte limit')
            try:return await original(request)
            except RequestValidationError as error:
                if any('UTF-8 byte limit' in str(item.get('ctx',{})) for item in error.errors()):
                    raise HTTPException(413,'Investigation exceeds UTF-8 byte limit') from error
                raise
        return bounded

investigation_router=APIRouter(prefix="/{project_id}/investigation",route_class=BoundedInvestigationRoute)


def response(project_id,row,document,db):
    body=service.representation(db,project_id,row,document)
    return JSONResponse(body,headers={'ETag':service.etag(project_id,body['revision']),'Cache-Control':'private, no-store'})


@investigation_router.get("")
def get_investigation(project_id:UUID,db:Session=Depends(get_db),actor:CurrentUser=Depends(get_required_user)):
    service.access(db,project_id,actor.id)
    row,document=service.read_document(db,project_id)
    return response(project_id,row,document,db)


@investigation_router.put("")
def put_investigation(project_id:UUID,request:SaveInvestigation,if_match:str|None=Header(None),db:Session=Depends(get_db),actor:CurrentUser=Depends(get_required_user)):
    row,document=service.save(db,project_id,actor.id,request,if_match)
    return response(project_id,row,document,db)


@investigation_router.get("/sources/search")
def search_sources(project_id:UUID,q:str=Query(...,min_length=1,max_length=200),limit:int=Query(10,ge=1,le=30),db:Session=Depends(get_db),actor:CurrentUser=Depends(get_required_user)):
    from app.database.models import PaperPassage
    from sqlalchemy import func
    service.access(db,project_id,actor.id)
    rows=(db.query(PaperPassage.paper_id,PaperPassage.start_line,PaperPassage.end_line,PaperPassage.content,Paper.title)
        .join(ProjectPaper,ProjectPaper.paper_id==PaperPassage.paper_id)
        .join(Paper,Paper.id==PaperPassage.paper_id)
        .filter(ProjectPaper.project_id==project_id,PaperPassage.ts_vector.op('@@')(func.websearch_to_tsquery('english',q)))
        .order_by(PaperPassage.paper_id,PaperPassage.start_line).limit(limit).all())
    return JSONResponse({'coverage':'Indexed passages only; sources without an index remain inspectable by line.','results':[{'paper_id':str(row.paper_id),'start_line':row.start_line,'end_line':row.end_line,'excerpt':row.content[:20000],'title':row.title} for row in rows]},headers={'Cache-Control':'private, no-store'})


@investigation_router.get("/sources/{paper_id}")
def get_source(project_id:UUID,paper_id:UUID,start_line:int=Query(1,ge=1),line_count:int=Query(50,ge=1,le=200),db:Session=Depends(get_db),actor:CurrentUser=Depends(get_required_user)):
    service.access(db,project_id,actor.id)
    associated=db.query(ProjectPaper).filter(ProjectPaper.project_id==project_id,ProjectPaper.paper_id==paper_id).first()
    if not associated: raise HTTPException(404,'Source not found')
    paper=db.query(Paper.id,Paper.title,Paper.authors,Paper.publish_date,Paper.doi,Paper.raw_content).filter(Paper.id==paper_id).first()
    if not paper or not paper.raw_content: raise HTTPException(404,'Extracted text unavailable')
    lines=paper.raw_content.split('\n')
    if start_line>len(lines): raise HTTPException(422,'Source range exceeds text')
    selected=lines[start_line-1:start_line-1+line_count]
    text='\n'.join(selected)
    if len(text)>20000: raise HTTPException(413,'Request a smaller source range')
    return JSONResponse({'paper_id':str(paper_id),'title':paper.title,'authors':paper.authors or [],'publish_date':paper.publish_date,'doi':paper.doi,'start_line':start_line,'end_line':start_line+len(selected)-1,'text':text,'source_sha256':service.text_hash(paper.raw_content),'quote_sha256':service.text_hash(text),'page_span':None,'total_lines':len(lines)},headers={'Cache-Control':'private, no-store'})


@investigation_router.get("/export")
def export_investigation(project_id:UUID,format:str=Query('bundle',pattern='^(bundle|markdown|bibtex)$'),db:Session=Depends(get_db),actor:CurrentUser=Depends(get_required_user)):
    from app.services.investigation_export import export_document
    from fastapi.responses import Response
    service.access(db,project_id,actor.id)
    row,document=service.read_document(db,project_id)
    body=service.representation(db,project_id,row,document)
    content,media,extension=export_document(body,project_id,format)
    return Response(content,media_type=media,headers={'Cache-Control':'private, no-store','Content-Disposition':f'attachment; filename="investigation.{extension}"'})


@investigation_router.post("/draft-requests")
def create_draft_request(project_id:UUID,request:CreateDraftRequest,db:Session=Depends(get_db),actor:CurrentUser=Depends(get_required_user)):
    from app.services import investigation_drafting as drafts
    row=drafts.create(db,project_id,actor,request)
    return JSONResponse(drafts.status(db,project_id,actor,row.id),headers={'Cache-Control':'private, no-store'})


@investigation_router.get("/draft-requests/{request_id}")
def get_draft_request(project_id:UUID,request_id:UUID,db:Session=Depends(get_db),actor:CurrentUser=Depends(get_required_user)):
    from app.services import investigation_drafting as drafts
    return JSONResponse(drafts.status(db,project_id,actor,request_id),headers={'Cache-Control':'private, no-store'})


@investigation_router.post("/draft-requests/{request_id}/run")
async def run_draft_request(project_id:UUID,request_id:UUID,db:Session=Depends(get_db),actor:CurrentUser=Depends(get_required_user)):
    from app.services import investigation_drafting as drafts
    from app.api.message_api import _with_keepalive,_KeepAlive,KEEPALIVE_INTERVAL_SECONDS,END_DELIMITER
    from fastapi.responses import StreamingResponse
    stream=await drafts.run(db,project_id,actor,request_id)
    async def output():
        async for chunk in _with_keepalive(stream,KEEPALIVE_INTERVAL_SECONDS):
            yield END_DELIMITER if isinstance(chunk,_KeepAlive) else chunk
    return StreamingResponse(output(),media_type='text/event-stream',headers={'Cache-Control':'private, no-store'})


@investigation_router.post("/import/preview")
def preview_import(project_id:UUID,bundle:dict,db:Session=Depends(get_db),actor:CurrentUser=Depends(get_required_user)):
    import json
    from uuid import uuid4
    from pydantic import ValidationError
    from app.schemas.investigation import InvestigationDocument
    service.access(db,project_id,actor.id,write=True)
    if len(json.dumps(bundle,ensure_ascii=False).encode())>2_000_000:raise HTTPException(413,'Import exceeds byte limit')
    if bundle.get('format')!='openpaper/investigation-bundle' or type(bundle.get('version')) is not int or bundle['version']!=1:raise HTTPException(422,'Unsupported bundle')
    try: document=InvestigationDocument.model_validate(bundle['document']).model_dump(mode='json')
    except (KeyError,ValidationError) as error:raise HTTPException(422,'Invalid investigation bundle') from error
    entities=[*document['claims'],*document['findings'],*document['relations'],*document['manuscript']['sections'],*[b for s in document['manuscript']['sections'] for b in s['blocks']]]
    mapping={entity['id']:str(uuid4()) for entity in entities}
    for entity in entities:entity['id']=mapping[entity['id']]
    for finding in document['findings']:
        source=finding['source'];locator=source.get('paper_id',source.get('origin_locator',''))
        finding['source']={'kind':'unbound','origin_locator':locator,'notes':'Imported locator; explicitly bind current project source lines before citing.'}
    for relation in document['relations']:
        relation['claim_id']=mapping[relation['claim_id']];relation['finding_id']=mapping[relation['finding_id']]
    for section in document['manuscript']['sections']:
        for block in section['blocks']:
            block['claim_ids']=[mapping[i] for i in block['claim_ids']];block['finding_ids']=[mapping[i] for i in block['finding_ids']]
            block['provenance']={'kind':'imported','origin_label':'Investigation bundle','original_ids':[next(old for old,new in mapping.items() if new==block['id'])]}
            block['dependency_pins']={}
            block['quote_snapshot']=None
            if block['kind']=='source_quote':block['text']=''
    return JSONResponse({'document':document,'saved':False,'warnings':['All sources require explicit project-source binding. Imported citations and dependency pins are unverified.']},headers={'Cache-Control':'private, no-store'})
