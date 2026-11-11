"use client";
import {createContext,useContext,useState,useRef,useEffect,useCallback,ReactNode} from 'react';
import {emptyInvestigation,validateInvestigation,Investigation,InvestigationState,investigationRequest,InvestigationHttpError} from '@/lib/investigation';
import {useProjectWorkspace} from './ProjectWorkspaceProvider';

type Context={document:Investigation;update:(fn:(draft:Investigation)=>void)=>void;save:(reviewed?:string[])=>Promise<void>;reload:()=>Promise<void>;dirty:boolean;status:string;validation:InvestigationState['validation'];loaded:boolean;revision:number;reviewProposal:(id:string)=>void};
const InvestigationContext=createContext<Context|null>(null);
export const useInvestigation=()=>{const context=useContext(InvestigationContext);if(!context)throw Error('Investigation provider missing');return context;};
export function InvestigationProvider({children}:{children:ReactNode}){
 const {projectId,project}=useProjectWorkspace();
 const edits=useRef(0);const reviewedProposals=useRef(new Set<string>());
 const [document,setDocument]=useState<Investigation>(emptyInvestigation);
 const [tag,setTag]=useState<string|null>(null);const [dirty,setDirty]=useState(false);const [loaded,setLoaded]=useState(false);
 const [status,setStatus]=useState('Loading');const [validation,setValidation]=useState<InvestigationState['validation']>({findings:{},blocks:{}});
 const reload=useCallback(async()=>{
  const {body,etag}=await investigationRequest(`/api/projects/${projectId}/investigation`);
  setDocument(body.document);setValidation(body.validation);setTag(etag);setDirty(false);setLoaded(true);setStatus('Saved');
 },[projectId]);
 useEffect(()=>{let active=true;investigationRequest(`/api/projects/${projectId}/investigation`).then(({body,etag})=>{if(active){setDocument(body.document);setValidation(body.validation);setTag(etag);setDirty(false);setLoaded(true);setStatus('Saved');}}).catch(()=>{if(active)setStatus('Could not load investigation');});return()=>{active=false;};},[projectId]);
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
 const update=(fn:(draft:Investigation)=>void)=>{if(project?.role!=='admin'&&project?.role!=='editor')return;edits.current++;setDocument(previous=>{const draft=structuredClone(previous);fn(draft);return draft;});setDirty(true);setStatus('Unsaved changes');};
 const save=async(reviewed:string[]=[])=>{
  if(!loaded||!tag||status==='Saving')return;const savedEdit=edits.current;setStatus('Saving');
  try{validateInvestigation(document);const {body,etag}=await investigationRequest(`/api/projects/${projectId}/investigation`,{method:'PUT',headers:{'If-Match':tag},body:JSON.stringify({document,reviewed_block_ids:reviewed,reviewed_proposal_ids:[...reviewedProposals.current]})});setTag(etag);setValidation(body.validation);if(edits.current===savedEdit){setDocument(body.document);setDirty(false);setStatus('Saved');reviewedProposals.current.clear();}else{setDirty(true);setStatus('Unsaved changes');}}
  catch(error){if(error instanceof Error&&error.message.startsWith('Validation failed:')){setStatus(error.message);return;}setStatus(error instanceof InvestigationHttpError&&error.status===412?'Conflict':'Save failed');}
 };
 return <InvestigationContext.Provider value={{document,update,save,reload,dirty,status,validation,loaded,revision:Number(tag?.split(':').at(-1)?.replace('"','')||0),reviewProposal:id=>reviewedProposals.current.add(id)}}>{children}</InvestigationContext.Provider>;
}
