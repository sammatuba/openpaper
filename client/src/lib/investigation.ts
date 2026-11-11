import {z} from 'zod';
const text=z.string().max(20000),label=z.string().max(500),id=z.uuid(),digest=z.string().regex(/^[0-9a-f]{64}$/);
const sourceSchema=z.discriminatedUnion('kind',[
 z.strictObject({kind:z.literal('anchored'),paper_id:id,start_line:z.number().int().positive(),end_line:z.number().int().positive(),quote:text.min(1),source_sha256:digest,quote_sha256:digest,title:text.optional(),authors:z.array(label).max(500).optional(),publish_date:label.nullable().optional(),doi:label.nullable().optional(),page_span:z.tuple([z.number().int().positive(),z.number().int().positive()]).nullable().optional()}).refine(s=>s.end_line>=s.start_line&&(!s.page_span||s.page_span[1]>=s.page_span[0]),'Reversed source location'),
 z.strictObject({kind:z.literal('redacted'),paper_id:id}),z.strictObject({kind:z.literal('unbound'),origin_locator:label.optional(),notes:text.optional()})
]);
const provenanceSchema=z.strictObject({kind:z.enum(['human','assembled','assistant','imported']),request_id:id.nullable().optional(),message_id:id.nullable().optional(),origin_label:label.nullable().optional(),original_ids:z.array(label).max(1000).optional(),edited:z.boolean().optional(),inserted_at:z.string().nullable().optional(),inserted_by:id.nullable().optional(),reviewed:z.boolean().optional()}).refine(p=>p.kind!=='assistant'||Boolean(p.request_id&&p.message_id),'Missing assistant identity');
const blockSchema=z.strictObject({id,kind:z.enum(['paragraph','source_quote','gap']),text:z.string().max(10000),claim_ids:z.array(id).max(100),finding_ids:z.array(id).max(500),provenance:provenanceSchema,quote_snapshot:sourceSchema.nullable().optional(),dependency_pins:z.record(z.string().max(100),digest).refine(p=>Object.keys(p).length<=1600)});
const investigationSchema=z.strictObject({
 format:z.literal('openpaper/investigation'),version:z.literal(1),
 case:z.strictObject({question:text,why_it_matters:text,landscape:text,coverage_limits:text,provisional_answer:text,unresolved_tension:text,reconciliation:text,discriminating_experiment:text,update_criteria:text,search_date:z.iso.date().nullable().optional()}),
 claims:z.array(z.strictObject({id,statement:z.string().max(2000),reasoning:text,caveats:text,archived:z.boolean()})).max(100),
 findings:z.array(z.strictObject({id,label,observed_result:text,author_interpretation:text,our_interpretation:text,setup:z.strictObject({model:text,task:text,training:text,intervention:text,evaluation:text,other:text}),limitations:text,source:sourceSchema,archived:z.boolean()})).max(500),
 relations:z.array(z.strictObject({id,claim_id:id,finding_id:id,relation:z.enum(['supports','challenges','qualifies']),rationale:text})).max(1000),
 manuscript:z.strictObject({title:label,sections:z.array(z.strictObject({id,title:label,blocks:z.array(blockSchema).max(1000)})).max(30)})
});
export function validateInvestigation(value:unknown){
 const parsed=investigationSchema.safeParse(value);
 if(!parsed.success)throw new Error('Validation failed: '+parsed.error.issues.map(issue=>issue.path.join('.')+': '+issue.message).slice(0,3).join('; '));
 const doc=parsed.data,blocks=doc.manuscript.sections.flatMap(s=>s.blocks),entities=[...doc.claims,...doc.findings,...doc.relations,...doc.manuscript.sections,...blocks];
 const claims=new Set(doc.claims.map(c=>c.id)),findings=new Set(doc.findings.map(f=>f.id)),triples=doc.relations.map(r=>[r.claim_id,r.finding_id,r.relation].join(':'));
 if(blocks.length>1000||new Set(entities.map(e=>e.id)).size!==entities.length||new Set(triples).size!==triples.length||doc.relations.some(r=>!claims.has(r.claim_id)||!findings.has(r.finding_id))||blocks.some(b=>b.claim_ids.some(id=>!claims.has(id))||b.finding_ids.some(id=>!findings.has(id))||new Set(b.claim_ids).size!==b.claim_ids.length||new Set(b.finding_ids).size!==b.finding_ids.length||(b.kind==='source_quote'&&b.finding_ids.length!==1)))throw new Error('Validation failed: duplicate or missing investigation references.');
 if(new TextEncoder().encode(JSON.stringify(doc)).length>2000000)throw new Error('Validation failed: investigation exceeds UTF-8 byte limit.');
}

export type Source = {kind:'anchored';paper_id:string;start_line:number;end_line:number;quote:string;source_sha256:string;quote_sha256:string;title?:string;authors?:string[];publish_date?:string|null;doi?:string|null;page_span?:[number,number]|null} | {kind:'unbound';origin_locator?:string;notes?:string} | {kind:'redacted';paper_id:string};
export type Claim = {id:string;statement:string;reasoning:string;caveats:string;archived:boolean};
export type Finding = {id:string;label:string;observed_result:string;author_interpretation:string;our_interpretation:string;setup:Record<'model'|'task'|'training'|'intervention'|'evaluation'|'other',string>;limitations:string;source:Source;archived:boolean};
export type Relation = {id:string;claim_id:string;finding_id:string;relation:'supports'|'challenges'|'qualifies';rationale:string};
export type Block = {id:string;kind:'paragraph'|'source_quote'|'gap';text:string;claim_ids:string[];finding_ids:string[];provenance:{edited?:boolean;kind:'human'|'assembled'|'assistant'|'imported';request_id?:string;message_id?:string};dependency_pins:Record<string,string>;quote_snapshot?:Source|null};
export type Section = {id:string;title:string;blocks:Block[]};
export type Investigation = {format:'openpaper/investigation';version:1;case:Record<'question'|'why_it_matters'|'landscape'|'coverage_limits'|'provisional_answer'|'unresolved_tension'|'reconciliation'|'discriminating_experiment'|'update_criteria',string>&{search_date?:string|null};claims:Claim[];findings:Finding[];relations:Relation[];manuscript:{title:string;sections:Section[]}};
export type InvestigationState = {document:Investigation;revision:number;validation:{findings:Record<string,string>;blocks:Record<string,string>}};
export const emptyInvestigation=():Investigation=>({format:'openpaper/investigation',version:1,case:{question:'',why_it_matters:'',landscape:'',coverage_limits:'',provisional_answer:'',unresolved_tension:'',reconciliation:'',discriminating_experiment:'',update_criteria:''},claims:[],findings:[],relations:[],manuscript:{title:'',sections:[]}});
export function downloadInvestigation(document:Investigation,saved:boolean){
 const portable=structuredClone(document);
 // Offline recovery retains authored work while captured source text requires a fresh access check.
 for(const finding of portable.findings){const source=finding.source;finding.source={kind:'unbound',origin_locator:source.kind==='unbound'?source.origin_locator:source.paper_id,notes:'Offline recovery: bind current project source lines before citing.'};}
 for(const section of portable.manuscript.sections)for(const block of section.blocks)block.quote_snapshot=null;
 const blob=new Blob([JSON.stringify({format:'openpaper/investigation-bundle',version:1,saved,exported_at:new Date().toISOString(),document:portable},null,2)],{type:'application/json'});
 const url=URL.createObjectURL(blob);const link=window.document.createElement('a');link.href=url;link.download=saved?'investigation-saved.json':'investigation-unsaved.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export class InvestigationHttpError extends Error { constructor(public status:number,message:string){super(message);} }
export async function investigationRequest(path:string,options:RequestInit={}){
 const response=await fetch(`${process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000'}${path}`,{credentials:'include',...options,headers:{'Content-Type':'application/json',...options.headers}});
 if(!response.ok)throw new InvestigationHttpError(response.status,`Request failed (${response.status}). Your unsaved work is preserved.`);
 const body=await response.json();
 if(/\/investigation$/.test(path)&&(!body?.document||body.document.format!=='openpaper/investigation'||body.document.version!==1||!body.document.case||!Array.isArray(body.document.claims)||!Array.isArray(body.document.findings)||!body.document.manuscript))throw new InvestigationHttpError(502,'Invalid investigation response. Local work is preserved.');
 return {body,etag:response.headers.get('ETag')};
}
