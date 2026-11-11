import {foldMarkdown,projectResearchBrief,researchQuestion} from './textfold';
import type {Project} from './schema';
import type {Investigation,Block} from './investigation';

export function legacyCase(project:Pick<Project,'id'|'title'|'description'|'research_brief'>){
 const brief=projectResearchBrief(project).document;
 const full=(section:typeof brief.sections[number])=>section.units.map(u=>u.full).join('\n\n');
 const context=brief.sections.map(s=>'## '+s.title+'\n'+full(s)).join('\n\n');
 const answer=brief.sections.find(s=>/provisional|answer|synthesi|conclusion/i.test(s.title));
 return {question:(researchQuestion(brief)||'').slice(0,20000),landscape:context.slice(0,20000),provisional_answer:answer?full(answer).slice(0,20000):'',excerpted:context.length>20000};
}
export function quotation(doc:Investigation,block:Block){
 const source=block.quote_snapshot;
 if(source)return source.kind==='anchored'?source.quote:'Source unavailable or unbound.';
 // An unsaved new quotation is a preview; persisted blocks carry server snapshots.
 if(!Object.keys(block.dependency_pins).length){const selected=doc.findings.find(f=>f.id===block.finding_ids[0])?.source;return selected?.kind==='anchored'?selected.quote:'Source unavailable or unbound.';}
 return 'Source unavailable or unbound.';
}
export function investigationPreview(doc:Investigation,view:'case'|'evidence'|'draft',projectId:string){
 const title='Investigation '+view,id=projectId+':'+view;
 if(view!=='draft')return foldMarkdown(view==='evidence'?doc.findings.map(f=>`## ${f.label}\nObserved result: ${f.observed_result}\n\nAuthor interpretation: ${f.author_interpretation}\n\nOur interpretation: ${f.our_interpretation}\n\nLimitations: ${f.limitations}\n\nExact source quotation: ${f.source.kind==='anchored'?f.source.quote:'Unavailable or unbound.'}`).join('\n\n'):Object.entries(doc.case).filter(([key])=>key!=='search_date').map(([key,value])=>`## ${key.replaceAll('_',' ')}\n${value||'No entry yet.'}`).join('\n\n'),title,id);
 const result=foldMarkdown('',title,id);result.sections=[];
 result.provenance.ai_generated=doc.manuscript.sections.some(s=>s.blocks.some(b=>b.provenance.kind==='assistant'));
 result.provenance.model=result.provenance.ai_generated?'Mixed authorship; see each paragraph attribution':null;
 for(const section of doc.manuscript.sections){
  const units=section.blocks.flatMap(block=>{
   const attribution=block.kind==='source_quote'?'Exact source quotation — captured version':block.provenance.kind==='assistant'?'AI-authored prose — human review required':block.provenance.kind==='imported'?'Imported prose — unverified origin':block.kind==='gap'?'Evidence gap':'Human-authored prose';
   const links=block.finding_ids.map(fid=>`[Finding ${fid}](/projects/${projectId}/evidence?finding=${fid})`).join(' ');
   const fragment=foldMarkdown(`${attribution}.\n\n${block.kind==='source_quote'?quotation(doc,block):block.text}\n\n${links}`,section.title,block.id);
   return fragment.sections.flatMap(s=>s.units).map((unit,index)=>({...unit,id:block.id+':'+index,provenance:{...block.provenance},finding_ids:block.finding_ids}));
  });
  result.sections.push({id:section.id,title:section.title,depth:1,takeaway:section.title,topic:section.title,units});
 }
 return result;
}
