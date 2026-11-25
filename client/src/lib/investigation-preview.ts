import {foldBlock,makeUnit,foldMarkdown,projectResearchBrief,researchQuestion} from './textfold';
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
 if(view==='evidence'){
  const preview=foldMarkdown('',title,id);
  preview.sections=doc.findings.map(finding=>{
   const fields=[
    ['observed_result','Observed result',finding.observed_result],
    ['author_interpretation','Author interpretation',finding.author_interpretation],
    ['our_interpretation','Our interpretation',finding.our_interpretation],
    ['limitations','Limitations',finding.limitations],
   ];
   if(finding.source.kind==='anchored')fields.push(['source','Captured quotation',finding.source.quote]);
   const label=finding.label||'Untitled finding';
   return {id:finding.id,title:label,depth:1,topic:label,takeaway:'',
    units:fields.map(([key,attribution,value])=>({...makeUnit(value, finding.id+':'+key),attribution,finding_ids:[finding.id]}))};
  });
  return preview;
 }
 if(view==='case')return foldMarkdown(Object.entries(doc.case).filter(([key])=>key!=='search_date').map(([key,value])=>`## ${key.replaceAll('_',' ')}\n${value||'No entry yet.'}`).join('\n\n'),title,id);
 const result=foldMarkdown('',title,id);result.sections=[];
 result.provenance.ai_generated=doc.manuscript.sections.some(s=>s.blocks.some(b=>b.provenance.kind==='assistant'));
 result.provenance.model=result.provenance.ai_generated?'Mixed authorship; see each paragraph attribution':null;
 for(const section of doc.manuscript.sections){
  const units=section.blocks.flatMap(block=>{
   const attribution=block.kind==='source_quote'?'Exact source quotation — captured version':block.provenance.kind==='assistant'?'AI-authored prose — human review required':block.provenance.kind==='imported'?'Imported prose — unverified origin':block.kind==='gap'?'Evidence gap':'Human-authored prose';
   // Attribution and findings travel as fields of the paragraph, never as prose.
   // A cited finding that no longer exists stays visible as an unavailable citation.
   const findings=block.finding_ids.map(fid=>{const finding=doc.findings.find(f=>f.id===fid);return {id:fid,label:finding?finding.label||'Untitled finding':'unavailable ('+fid+')'};});
   // A block's own headings are its text, not manuscript sections; an empty block still shows what it cites.
   const paragraphs=foldBlock(block.kind==='source_quote'?quotation(doc,block):block.text,block.id);
   return paragraphs.map((unit,index)=>({...unit,provenance:{...block.provenance},finding_ids:block.finding_ids,attribution:index===0?attribution:'',findings:index===paragraphs.length-1?findings:[]}));
  });
  result.sections.push({id:section.id,title:section.title,depth:1,takeaway:section.title,topic:section.title,units});
 }
 return result;
}
