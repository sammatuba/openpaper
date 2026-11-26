"use client";
import {createContext,useContext,useState,useRef,useEffect,useCallback,useSyncExternalStore,ReactNode} from 'react';
import {emptyInvestigation,validateInvestigation,Investigation,InvestigationState,investigationRequest,InvestigationHttpError} from '@/lib/investigation';
import {askInvestigation,answerStands,rememberInvestigation,denyInvestigation,forgetInvestigation,investigationSession,subscribeInvestigationSession} from '@/lib/investigation-snapshot';
import type {InvestigationTicket} from '@/lib/investigation-snapshot';
import {useProjectWorkspace} from './ProjectWorkspaceProvider';

type Context={document:Investigation;update:(fn:(draft:Investigation)=>void)=>void;save:(reviewed?:string[])=>Promise<void>;reload:()=>Promise<void>;dirty:boolean;status:string;validation:InvestigationState['validation'];loaded:boolean;revision:number;reviewProposal:(id:string)=>void};
const InvestigationContext=createContext<Context|null>(null);
export const useInvestigation=()=>{const context=useContext(InvestigationContext);if(!context)throw Error('Investigation provider missing');return context;};
// The server refused: whatever was kept for the project is no longer ours to show.
const refused=(error:unknown,asked:InvestigationTicket)=>{if(error instanceof InvestigationHttpError&&[401,403,404].includes(error.status))denyInvestigation(asked);};
// The document, loaded or edited, belongs to the user who was signed in when it was asked for.
// When that user signs out or changes, the provider starts again empty: nothing of theirs stays on screen.
export function InvestigationProvider({children}:{children:ReactNode}){
 const session=useSyncExternalStore(subscribeInvestigationSession,investigationSession,()=>0);
 return <InvestigationSession key={session}>{children}</InvestigationSession>;
}
function InvestigationSession({children}:{children:ReactNode}){
 const {projectId,project,projectDenied}=useProjectWorkspace();
 const edits=useRef(0);const reviewedProposals=useRef(new Set<string>());
 const [document,setDocument]=useState<Investigation>(emptyInvestigation);
 const [tag,setTag]=useState<string|null>(null);const [dirty,setDirty]=useState(false);const [loaded,setLoaded]=useState(false);
 const [status,setStatus]=useState('Loading');const [validation,setValidation]=useState<InvestigationState['validation']>({findings:{},blocks:{}});
 // One save at a time, and no reload while one is in flight, so a save's answer is never overtaken by a
 // reload and never lands on a later save's status. (A reload is the user's choice to replace what is on
 // screen; it can wait for the save it would otherwise race.)
 const saving=useRef(false);const saves=useRef(0);const loadedRef=useRef(false);
 // Block reviews asked for while a save was in flight, or sent with a save that failed: they go with the next save.
 const queuedReviews=useRef<string[]>([]);
 const reload=useCallback(async()=>{
  if(saving.current)throw new Error('A save is in progress.');
  const asked=askInvestigation(projectId),editsThen=edits.current,savesThen=saves.current;let answer;
  try{answer=await investigationRequest(`/api/projects/${projectId}/investigation`);}catch(error){refused(error,asked);throw error;}
  // An answer that a later request has overtaken, or that is another session's, is neither kept nor shown;
  // the reload is reported as not done, so the user is not left thinking the screen was replaced.
  if(!rememberInvestigation(asked,answer.body.document))throw new Error('Overtaken by a later request.');const {body,etag}=answer;
  // The user confirmed replacing what was on screen then. Anything edited or sent to be saved since is newer
  // work they have not agreed to lose: it stays, with its revision tag, and the reload is reported as not done.
  // A save attempted meanwhile counts even if it has already failed: its conflict is about the draft still on screen.
  if(edits.current!==editsThen||saves.current!==savesThen||saving.current)throw new Error('Edited or saved since the reload was asked for.');
  // The draft the reviews belonged to is being replaced.
  queuedReviews.current=[];
  loadedRef.current=true;setDocument(body.document);setValidation(body.validation);setTag(etag);setDirty(false);setLoaded(true);setStatus('Saved');
 },[projectId]);
 // Loads when the project opens, and again when access to a denied project returns before anything was loaded.
 // A loaded document is never reloaded from here: it may hold unsaved edits.
 useEffect(()=>{if(projectDenied||loadedRef.current)return;let active=true;setStatus('Loading');const asked=askInvestigation(projectId);investigationRequest(`/api/projects/${projectId}/investigation`).then(({body,etag})=>{if(active&&rememberInvestigation(asked,body.document)){loadedRef.current=true;setDocument(body.document);setValidation(body.validation);setTag(etag);setDirty(false);setLoaded(true);setStatus('Saved');}}).catch(error=>{refused(error,asked);if(active&&answerStands(asked))setStatus('Could not load investigation');});return()=>{active=false;};},[projectId,projectDenied]);
 useEffect(()=>{if(projectDenied)forgetInvestigation(projectId);},[projectDenied,projectId]);
 useEffect(()=>{const before=(event:BeforeUnloadEvent)=>{if(dirty){event.preventDefault();event.returnValue='';}};window.addEventListener('beforeunload',before);return()=>window.removeEventListener('beforeunload',before);},[dirty]);
 useEffect(()=>{
  if(!dirty)return;
  const leave=(event:MouseEvent)=>{
   const link=(event.target as Element).closest('a[href]') as HTMLAnchorElement|null;
   if(!link||link.target==='_blank'||link.download)return;
   const destination=new URL(link.href,window.location.href);
   if(destination.origin===location.origin&&(destination.pathname===`/projects/${projectId}`||destination.pathname.startsWith(`/projects/${projectId}/`)))return;
   if(!window.confirm('Leave this project and discard unsaved changes? Cancel to keep editing or download your draft.')){event.preventDefault();event.stopPropagation();}
  };
  const navigation=(window as unknown as {navigation?:EventTarget}).navigation;
  const navigate=(event:Event)=>{
   const destination=(event as Event&{destination?:{url:string}}).destination;
   if(!destination||!event.cancelable)return;
   const target=new URL(destination.url,location.href);
   if(target.origin===location.origin&&(target.pathname===`/projects/${projectId}`||target.pathname.startsWith(`/projects/${projectId}/`)))return;
   if(!window.confirm('Discard unsaved project changes? Cancel to keep editing or download your draft.'))event.preventDefault();
  };
  window.document.addEventListener('click',leave,true);navigation?.addEventListener('navigate',navigate);
  return()=>{window.document.removeEventListener('click',leave,true);navigation?.removeEventListener('navigate',navigate);};
 },[dirty,projectId]);
 const update=(fn:(draft:Investigation)=>void)=>{if(project?.role!=='admin'&&project?.role!=='editor')return;edits.current++;setDocument(previous=>{const draft=structuredClone(previous);fn(draft);return draft;});setDirty(true);setStatus(saving.current?'Saving':'Unsaved changes');};
 const save=async(reviewed:string[]=[])=>{
  if(!loaded||!tag)return;
  if(saving.current){queuedReviews.current.push(...reviewed);return;}
  saving.current=true;saves.current++;const savedEdit=edits.current;setStatus('Saving');const asked=askInvestigation(projectId);
  // What this request sends is its own list: reviews that arrive while it is in flight wait in the queue for the next one.
  // Only blocks still in the draft can be reviewed.
  const present=new Set(document.manuscript.sections.flatMap(section=>section.blocks.map(block=>block.id)));
  const sent=[...new Set([...queuedReviews.current,...reviewed])].filter(id=>present.has(id));queuedReviews.current=[];let done=false;
  try{validateInvestigation(document);const {body,etag}=await investigationRequest(`/api/projects/${projectId}/investigation`,{method:'PUT',headers:{'If-Match':tag},body:JSON.stringify({document,reviewed_block_ids:sent,reviewed_proposal_ids:[...reviewedProposals.current]})});done=true;if(!rememberInvestigation(asked,body.document)){setStatus('Save failed');return;}setTag(etag);setValidation(body.validation);if(edits.current===savedEdit){setDocument(body.document);setDirty(false);setStatus('Saved');reviewedProposals.current.clear();}else{setDirty(true);setStatus('Unsaved changes');}}
  catch(error){refused(error,asked);if(!answerStands(asked)){setStatus('Save failed');return;}if(error instanceof Error&&error.message.startsWith('Validation failed:')){setStatus(error.message);return;}setStatus(error instanceof InvestigationHttpError&&error.status===412?'Conflict':'Save failed');}
  // A review that arrived during a save that succeeded has not been sent: the document is not fully saved yet.
  finally{saving.current=false;if(!done){queuedReviews.current=[...new Set([...sent,...queuedReviews.current])];if(queuedReviews.current.length)setDirty(true);}if(done&&queuedReviews.current.length){setDirty(true);setStatus(now=>now==='Saved'?'Unsaved changes':now);}}
 };
 return <InvestigationContext.Provider value={{document,update,save,reload,dirty,status,validation,loaded,revision:Number(tag?.match(/:(\d+)(?:-[a-z]+)?"$/)?.[1]||0)/* a compressing proxy appends "-gzip" or "-zstd" to the tag */,reviewProposal:id=>reviewedProposals.current.add(id)}}>{children}</InvestigationContext.Provider>;
}
