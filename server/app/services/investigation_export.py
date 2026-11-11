"""Pure exports of already redacted, access-checked investigation views."""
import json
import re
from datetime import datetime,timezone


def markdown(text):
    # Escape raw HTML and Markdown control characters rather than executing imports.
    text=text.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    return re.sub(r'([\\`*{}\[\]()#!_|])',r'\\\1',text)


def bibtex(text):
    replacements={'\\':r'\textbackslash{}','{':r'\{','}':r'\}','%':r'\%','&':r'\&','#':r'\#','_':r'\_','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}
    return ''.join(replacements.get(c,c) for c in str(text)).replace('\n',' ')


def export_document(body,project_id,format):
    document=body['document'];validation=body['validation']
    if format=='bundle':
        result={'format':'openpaper/investigation-bundle','version':1,'project_id':str(project_id),'saved':True,'revision':body['revision'],'exported_at':datetime.now(timezone.utc).isoformat(),'document':document,'validation':validation}
        return json.dumps(result,ensure_ascii=False,indent=2),'application/json','json'
    findings={f['id']:f for f in document['findings']}
    references={}
    for finding in document['findings']:
        source=finding['source']
        if source['kind']=='anchored': references.setdefault(source['paper_id'],source)
    for section in document['manuscript']['sections']:
        for block in section['blocks']:
            source=block.get('quote_snapshot')
            if source and source['kind']=='anchored':references.setdefault(source['paper_id'],source)
    if format=='bibtex':
        entries=[]
        if any(f['source']['kind']!='anchored' for f in document['findings']):entries.append('% Unavailable or unbound references omitted; verify manuscript citations.')
        for pid,source in sorted(references.items()):
            fields=[]
            raw_date=source.get('publish_date') or ''
            year=raw_date[:4] if re.match(r'^\d{4}(?:-|$)',raw_date) else ''
            for key,value in [('title',source.get('title')),('author',' and '.join(source.get('authors') or [])),('doi',source.get('doi')),('year',year)]:
                if value: fields.append('  '+key+' = {'+bibtex(value)+'}')
            warnings=[]
            if not source.get('title') or not source.get('publish_date'):warnings.append('Some bibliographic fields are unavailable; verify before publication')
            if any(validation['findings'].get(f['id'])!='current' for f in document['findings'] if f['source'].get('paper_id')==pid):warnings.append('Historical or changed evidence; source review required')
            if any(b.get('quote_snapshot',{}).get('paper_id')==pid and validation['blocks'].get(b['id'])=='review_needed' for s in document['manuscript']['sections'] for b in s['blocks'] if b.get('quote_snapshot')):warnings.append('Captured quotation requires evidence review')
            if warnings:fields.append('  note = {'+bibtex('; '.join(warnings))+'}')
            entries.append('@misc{paper_'+pid.replace('-','')+',\n'+',\n'.join(fields)+'\n}')
        return '\n\n'.join(entries),'application/x-bibtex','bib'
    output=['# '+markdown(document['manuscript']['title'] or 'Investigation draft'),'']
    used=set()
    for section in document['manuscript']['sections']:
        output+=['## '+markdown(section['title']),'']
        for block in section['blocks']:
            used.update(block['finding_ids'])
            text=markdown(block['text'])
            if block['kind']=='source_quote':
                source=block.get('quote_snapshot')
                text=markdown(source['quote']) if source and source['kind']=='anchored' else '[Source unavailable or unbound]'
                if source and source['kind']=='anchored':
                    text+=f" [Captured quotation: paper_{source['paper_id'].replace('-','')}, extracted lines {source['start_line']}–{source['end_line']}, source version {source['source_sha256'][:12]}]"
            citations=' '.join('[^finding-'+fid+']' for fid in block['finding_ids'])
            output+=[text+(' '+citations if citations else ' [Uncited]'),'']
            if block['provenance']['kind']=='assistant':output+=['[AI-authored prose; human review required]','']
            if validation['blocks'].get(block['id'])=='review_needed':output+=['[Evidence changed or unavailable — review needed]','']
    output+=['## Sources and limitations','',markdown(document['case']['coverage_limits']),'']
    for fid in sorted(used):
        finding=findings[fid];source=finding['source'];status=validation['findings'].get(fid,'unavailable')
        if source['kind']!='anchored':description='Source unavailable or unbound'
        else:description=markdown(source.get('title') or 'Untitled source')+f"; extracted lines {source['start_line']}–{source['end_line']}; paper_{source['paper_id'].replace('-','')}; PDF page not mapped"
        output += [f'[^finding-{fid}]: {description}. [Source context](/projects/{project_id}/evidence?finding={fid}). Status: {status}. Limitations: '+markdown(finding['limitations'])]
    return '\n'.join(output),'text/markdown','md'
