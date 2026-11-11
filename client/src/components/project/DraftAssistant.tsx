"use client";
import {useRef,useState,useEffect} from 'react';
import {investigationRequest} from '@/lib/investigation';
import {fetchFromApi} from '@/lib/api';
import {useProjectWorkspace} from './ProjectWorkspaceProvider';
import {useInvestigation} from './InvestigationProvider';

type Proposal={text:string;finding_ids:string[];claim_ids:string[];request_id:string;message_id:string;section_id:string;stale:boolean;uncited:boolean};
export function DraftAssistant({sectionId,findingIds,claimIds}:{sectionId:string;findingIds:string[];claimIds:string[]}){
 const {projectId,papers,openPaper}=useProjectWorkspace();const {document,dirty,revision,update,reviewProposal}=useInvestigation();
 const [open,setOpen]=useState(false);const [models,setModels]=useState<string[]>([]);const [provider,setProvider]=useState('');const [instructions,setInstructions]=useState('');
 const [inspected,setInspected]=useState<string|null>(null);const [state,setState]=useState('');const [id,setId]=useState<string|null>(null);const [proposal,setProposal]=useState<Proposal|null>(null);const [reviewed,setReviewed]=useState(false);
 const abort=useRef<AbortController|null>(null);const generating=useRef(false);
 useEffect(()=>()=>abort.current?.abort(),[]);
 const url=`/api/projects/${projectId}/investigation/draft-requests`;
 const finding=document.findings.find(f=>f.id===inspected);
 const omitted=document.findings.filter(f=>!findingIds.includes(f.id)&&(!claimIds.length||document.relations.some(r=>r.finding_id===f.id&&claimIds.includes(r.claim_id))));
 const button='mr-2 rounded-md border px-3 py-2 text-sm disabled:opacity-50';
 async function show(){setOpen(true);try{const options=await fetchFromApi('/api/message/models');const names=Object.keys(options.models||{});setModels(names);setProvider(names.includes(options.default)?options.default:(names[0]||''));}catch{setState('Model options unavailable. Manual drafting remains available.');}}
 async function check(requestId=id){if(!requestId)return;try{const {body}=await investigationRequest(url+'/'+requestId);setState(body.error_code||body.state);if(body.proposal)setProposal(body.proposal);}catch{setState('Could not read status. Your input is preserved; try Check status.');}}
 async function generate(){
  if(generating.current)return;generating.current=true;setState('Generating');setProposal(null);setReviewed(false);const requestId=crypto.randomUUID();setId(requestId);
  abort.current=new AbortController();
  try{
   await investigationRequest(url,{method:'POST',signal:abort.current.signal,body:JSON.stringify({id:requestId,base_revision:revision,section_id:sectionId,claim_ids:claimIds,finding_ids:findingIds,instructions,provider})});
   const response=await fetch(`${process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000'}${url}/${requestId}/run`,{method:'POST',credentials:'include',signal:abort.current.signal});
   if(!response.ok||!response.body)throw Error('Generation did not start.');
   const reader=response.body.getReader();try{while(!(await reader.read()).done){/* Results are only accepted from the authorized status endpoint. */}}finally{reader.releaseLock();}
   await check(requestId);
  }catch{setState('Generation response interrupted. Check status before starting a new request.');}
  finally{generating.current=false;abort.current=null;}
 }
 function insert(){if(!proposal||((proposal.stale||dirty)&&!reviewed))return;
  const section=document.manuscript.sections.find(s=>s.id===proposal.section_id);if(!section){setState('Target section changed; proposal preserved.');return;}
  if(proposal.stale||dirty)reviewProposal(proposal.request_id);
  update(d=>{d.manuscript.sections.find(s=>s.id===proposal.section_id)!.blocks.push({id:crypto.randomUUID(),kind:'paragraph',text:proposal.text,claim_ids:proposal.claim_ids,finding_ids:proposal.finding_ids,provenance:{kind:'assistant',request_id:proposal.request_id,message_id:proposal.message_id},dependency_pins:{}});});setProposal(null);setState('Inserted into unsaved draft. Save investigation to persist.');
 }
 return <div className="space-y-2 rounded-md border p-3"><button className={button} onClick={()=>void show()}>Draft with assistant</button>{open&&<>
  <p className="text-sm">Only the {findingIds.length} selected findings will be sent. Other project evidence is omitted. Review your selection before generating. Manual drafting uses no model credits.</p>
  <details className="text-sm"><summary>Review selected context and omissions</summary><p>Target section: {document.manuscript.sections.find(s=>s.id===sectionId)?.title}</p><p>Saved case fields accompany these claims: {claimIds.map(id=>document.claims.find(c=>c.id===id)?.statement).join('; ')||'None selected'}.</p>{findingIds.map(id=>{const item=document.findings.find(f=>f.id===id);return item&&<article key={id}><h3>{item.label}</h3><p>Observed: {item.observed_result}</p><p>Setup: {Object.values(item.setup).filter(Boolean).join('; ')||'Not recorded'}</p><p>Limitations: {item.limitations||'Not recorded'}</p><blockquote className="whitespace-pre-wrap break-words">{item.source.kind==='anchored'?item.source.quote:'Source unavailable or unbound'}</blockquote></article>;})}<p>Omitted findings for this selection:</p><ul>{omitted.map(item=><li key={item.id}>{item.label} · {document.relations.filter(r=>r.finding_id===item.id&&(!claimIds.length||claimIds.includes(r.claim_id))).map(r=>r.relation).join(', ')||'No selected claim relation'}</li>)}</ul><p>Revise the claim/evidence selection above before Generate. No omitted evidence is sent.</p></details>
  <label className="block text-sm">Configured provider<select value={provider} onChange={event=>setProvider(event.target.value)}>{models.map(model=><option key={model}>{model}</option>)}</select></label>
  <label className="block text-sm">Drafting instructions<textarea className="w-full rounded border bg-background p-2" maxLength={2000} value={instructions} onChange={event=>setInstructions(event.target.value)}/></label>
  <button className={button} disabled={dirty||!provider||!findingIds.length||state==='Generating'} onClick={()=>void generate()}>Generate paragraph</button>
  {dirty&&<p>Save current edits before generating.</p>}
  <button className={button} disabled={!id} onClick={()=>void check()}>Check request status</button>
  <button className={button} disabled={state!=='Generating'} onClick={()=>abort.current?.abort()}>Cancel generation</button>
  <p role="status">{state}</p>
  {proposal&&<div className="space-y-2"><p>AI-authored proposal · {proposal.uncited?'Uncited prose':'Citations validated against selected findings; review factual accuracy.'}</p><textarea aria-label="Assistant proposal" className="w-full rounded border bg-background p-2" value={proposal.text} onChange={event=>setProposal({...proposal,text:event.target.value})}/>{proposal.finding_ids.map(fid=><button type="button" className={button} key={fid} onClick={()=>setInspected(fid)}>Inspect {document.findings.find(f=>f.id===fid)?.label||'Unavailable finding'}</button>)}{(proposal.stale||dirty)&&<label><input type="checkbox" checked={reviewed} onChange={event=>setReviewed(event.target.checked)}/> I reviewed this proposal against the current workspace and evidence.</label>}<button className={button} disabled={(proposal.stale||dirty)&&!reviewed} onClick={insert}>Insert assistant paragraph</button><button className={button} onClick={()=>{setProposal(null);setState('Proposal discarded. Manuscript unchanged.');}}>Discard proposal</button></div>}
  {finding&&<aside aria-label="Proposal source context"><h3>{finding.label}</h3><p>Current selected source context; verify the proposal against this evidence.</p><blockquote className="whitespace-pre-wrap break-words">{finding.source.kind==='anchored'?finding.source.quote:'Source unavailable or unbound.'}</blockquote><p>Limitations: {finding.limitations||'Not recorded'}</p>{finding.source.kind==='anchored'&&<button type="button" className={button} onClick={()=>{const source=finding.source;if(source.kind==='anchored'){const paper=papers.find(p=>p.id===source.paper_id);if(paper)openPaper(paper,source.quote);}}}>Open proposal PDF source</button>}<button type="button" className={button} onClick={()=>setInspected(null)}>Close source context</button></aside>}
 </>}</div>;
}
