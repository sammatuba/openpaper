// Production shell with mutable synthetic server state; real DB security is tested separately.
const {chromium}=require(process.env.OPENPAPER_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const {createHash}=require('node:crypto');
const base=process.env.OPENPAPER_BROWSER_BASE||'http://127.0.0.1:3011';
const fixture=require('../../docs/work/investigation-workspace-fixture.json');
const projectId=fixture.project.id,paperId=fixture.sources[0].id;
function fixturePdf(){const text='Synthetic fixture PDF. Exact quotation is available in extracted text.';const objects=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>','<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>','<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];const content='BT /F1 14 Tf 30 740 Td ('+text+') Tj ET';objects.push('<< /Length '+content.length+' >>\nstream\n'+content+'\nendstream');let pdf='%PDF-1.4\n',offsets=[0];for(let i=0;i<objects.length;i++){offsets.push(Buffer.byteLength(pdf));pdf+=(i+1)+' 0 obj\n'+objects[i]+'\nendobj\n';}const offset=Buffer.byteLength(pdf);pdf+='xref\n0 6\n0000000000 65535 f \n'+offsets.slice(1).map(n=>String(n).padStart(10,'0')+' 00000 n \n').join('')+'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+offset+'\n%%EOF';return Buffer.from(pdf);}
const sha=text=>createHash('sha256').update(text).digest('hex');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.OPENPAPER_CHROMIUM,args:['--no-sandbox']});
 try{for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:960},reducedMotion:width===390?'reduce':'no-preference'});const errors=[],unexpected=[];let saved=null,revision=0,forceConflict=false,providerCalls=0,sourceChanged=false,failSave=false,puts=0,failInspect=false,failProject=false;const requests=new Map();
  const blank=()=>({format:'openpaper/investigation',version:1,case:{question:'',why_it_matters:'',landscape:'',coverage_limits:'',provisional_answer:'',unresolved_tension:'',reconciliation:'',discriminating_experiment:'',update_criteria:''},claims:[],findings:[],relations:[],manuscript:{title:'',sections:[]}});
  page.setDefaultTimeout(10000);
  const legacyUnit={id:'legacy-u',kind:'paragraph',full:'Imported synthesis remains provisional.',sentences:['Imported synthesis remains provisional.'],evidence:[0],brief:['Imported synthesis remains provisional.'],key:'Imported synthesis',takeaway:'Imported synthesis',topic:'Synthesis'};
  const project={id:projectId,title:fixture.project.title,description:null,research_brief:{format:'textfold/doc',version:0,id:'legacy-only',title:'Imported question',lang:'en',levels:['topic','takeaway','key','brief','full'],written:[],provenance:{ai_generated:false,local:false},sections:[{id:'legacy-q',title:'The question',depth:1,takeaway:'A legacy research question?',topic:'Question',units:[{...legacyUnit,id:'legacy-question',full:'A legacy research question?',sentences:['A legacy research question?'],brief:['A legacy research question?'],key:'A legacy research question?',takeaway:'A legacy research question?',topic:'Question'}]},{id:'legacy-a',title:'Provisional answer',depth:1,takeaway:'Provisional',topic:'Answer',units:[legacyUnit]}],links:[]},role:'admin'};
  await page.route('**/synthetic-fixture.pdf',route=>route.fulfill({status:200,contentType:'application/pdf',body:fixturePdf()}));
  page.on('pageerror',e=>errors.push(e.message));await page.addInitScript(()=>{localStorage.setItem('project-artifacts-collapsed','true');localStorage.setItem('project-rail-collapsed','true');});
  await page.route('**/api/**',async route=>{
   const request=route.request(),url=new URL(request.url()),p=url.pathname;
   let body=[],status=200;const headers={'access-control-allow-origin':base,'access-control-allow-credentials':'true','access-control-allow-headers':'content-type,if-match','access-control-allow-methods':'GET,PUT,OPTIONS','access-control-expose-headers':'ETag'};
   if(request.method()==='OPTIONS')return route.fulfill({status:204,headers});
   if(p==='/api/auth/me')body={success:true,user:{id:'synthetic-user',name:'Researcher',email:'test@example.invalid',is_active:true,is_blocked:false}};
   else if(p==='/api/subscription/usage')body={limits:{knowledge_base_size:100,paper_uploads:100,chat_credits_weekly:100},usage:{knowledge_base_size:0,paper_uploads:0,chat_credits_used:0}};
   else if(p==='/api/message/models')body={models:{gemini:'Fake provider'},default:'gemini'};
   else if(p===`/api/projects/${projectId}/investigation/draft-requests`&&request.method()==='POST'){
    const input=JSON.parse(request.postData());
    if(input.base_revision!==revision){status=412;body={detail:'Stale workspace'};}
    else{if(!requests.has(input.id))requests.set(input.id,{id:input.id,state:'pending',input,proposal:null});body=requests.get(input.id);}
   }
   else if(p.startsWith(`/api/projects/${projectId}/investigation/draft-requests/`)){
    const id=p.split('/')[6],record=requests.get(id);
    if(!record){status=404;body={detail:'Unknown request'};}
    else if(p.endsWith('/run')){
     if(record.state!=='pending'){status=409;body={detail:'Already claimed'};}
     else{providerCalls++;record.state='completed';record.proposal={text:'AI-proposed qualified synthesis.',finding_ids:record.input.finding_ids,claim_ids:record.input.claim_ids,request_id:id,message_id:'a54d8000-2200-4400-8800-000000000001',section_id:record.input.section_id,stale:record.input.base_revision!==revision,uncited:false};return route.fulfill({status:200,headers,contentType:'text/event-stream',body:JSON.stringify({type:'complete'})+'END_OF_STREAM'});}
    }else body=record;
   }
   else if(p===`/api/projects/${projectId}/investigation`){
    if(request.method()==='PUT'){puts++;
     if(failSave){status=500;body={detail:'Synthetic failure'};}
     else if(forceConflict||request.headers()['if-match']!==`"investigation:${projectId}:${revision}"`){status=412;body={detail:'Synthetic conflict'};}
     else{saved=JSON.parse(request.postData()).document;revision++;for(const section of saved.manuscript.sections)for(const block of section.blocks)if(block.kind==='source_quote'&&!block.quote_snapshot)block.quote_snapshot=structuredClone(saved.findings.find(f=>f.id===block.finding_ids[0]).source);}
    }
    if(status===200)body={document:saved||blank(),revision,validation:{findings:Object.fromEntries((saved?.findings||[]).map(f=>[f.id,sourceChanged&&f.source.paper_id===paperId?'source_changed':'current'])),blocks:Object.fromEntries((saved?.manuscript.sections||[]).flatMap(s=>s.blocks).map(b=>[b.id,sourceChanged?'review_needed':'current']))}};
    headers.ETag=`"investigation:${projectId}:${revision}"`;
   }
   else if(p===`/api/projects/${projectId}/investigation/sources/search`)body={coverage:'Indexed passages only; sources without an index remain inspectable by line.',results:[{paper_id:paperId,start_line:2,end_line:2,excerpt:'Search excerpt, deliberately not the quotation.',title:fixture.sources[0].title}]};
   else if(failInspect&&p.startsWith(`/api/projects/${projectId}/investigation/sources/`)){status=404;body={detail:'Extracted text unavailable'};}
   else if(p.startsWith(`/api/projects/${projectId}/investigation/sources/`)){const source=fixture.sources.find(source=>p.endsWith('/'+source.id));if(!source)throw Error('Unknown source');body={start_line:2,end_line:2,text:source.quote,source_sha256:sha(source.raw_content),quote_sha256:sha(source.quote)};}
   else if(p.startsWith(`/api/projects/papers/${projectId}/`)&&p.endsWith('/file-url'))body={file_url:base+'/synthetic-fixture.pdf'};
   else if(p===`/api/projects/${projectId}`){if(failProject){status=500;body={detail:'Synthetic project failure'};}else body=project;}
   else if(p===`/api/projects/papers/${projectId}`)body={papers:fixture.sources.map(source=>({id:source.id,title:source.title,authors:[],status:'read',is_owner:true}))};
   else if(p===`/api/projects/conversations/${projectId}`||p==='/api/conversation/everything')body=[];
   else if(p===`/api/projects/invitations/${projectId}/`)body={invitations:[]};
   else if(p===`/api/projects/tables/jobs/${projectId}`)body={jobs:[]};
   else if(p===`/api/projects/artifacts/${projectId}`)body={artifacts:[]};
   else if(['/api/paper/active','/api/projects'].includes(p)||p===`/api/projects/${projectId}/collaborators`||p===`/api/projects/audio/${projectId}`||p===`/api/projects/audio/jobs/${projectId}`)body=[];
   else if(p==='/api/referral/balance')body={balance:0};
   else if([`/api/projects/charts/jobs/${projectId}`,`/api/projects/papers/${projectId}/pending-jobs`].includes(p))body={jobs:[]};
   else{unexpected.push(request.method()+' '+p);status=500;body={detail:'Unexpected test request'};}
   return route.fulfill({status,headers,contentType:'application/json',body:JSON.stringify(body)});
  });
  await page.goto(`${base}/projects/${projectId}/overview`);
  const workspace=page.getByRole('region',{name:'Investigation workspace'});
  const nav=page.getByRole('navigation',{name:'Project destinations'});
  const noOverflow=async label=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,label+' has no horizontal page overflow at '+width);
  const evidenceGroup=()=>workspace.getByRole('group',{name:'Evidence for the next paragraph'}).first();
  // The per-section add panel is collapsed once the manuscript has content.
  const pick=async labels=>{if(!(await evidenceGroup().isVisible().catch(()=>false)))await workspace.getByRole('button',{name:'Add to section',exact:true}).first().click();await evidenceGroup().waitFor();for(const finding of saved.findings)await evidenceGroup().getByRole('checkbox',{name:finding.label,exact:true}).setChecked(labels.includes(finding.label));};
  await page.getByRole('button',{name:'Save investigation',exact:true}).waitFor().catch(async error=>{console.error('Load diagnostic',width,page.url(),await page.locator('body').innerText(),errors,unexpected);await page.screenshot({path:'/tmp/investigation-load.png',fullPage:true});throw error;});
  assert.equal(await nav.getByRole('link',{name:'Overview',exact:true}).getAttribute('aria-current'),'page');
  assert.match(await workspace.getByRole('heading',{name:/^Next: /}).innerText(),/state the question/i,'Guide starts at the question');
  assert.equal(await page.getByRole('heading',{name:'What do you want to work on?'}).count(),0,'Discussion starter is not stacked under the case');
  await workspace.getByRole('button',{name:'Start from existing brief (unsaved)',exact:true}).click();
  assert.equal(await workspace.getByLabel('Question',{exact:true}).inputValue(),'A legacy research question?');assert.equal(await workspace.getByLabel('Provisional answer',{exact:true}).inputValue(),'Imported synthesis remains provisional.');assert.equal(revision,0);assert.equal(saved,null);
  await workspace.getByLabel('Question',{exact:true}).fill('Does signaling affect agreement?');
  await workspace.getByRole('button',{name:'Add claim',exact:true}).click();
  await workspace.getByLabel('Claim statement').fill(fixture.claim.statement);
  assert.equal(puts,0);await page.keyboard.press('Control+s');
  await page.locator('[role=status]').filter({hasText:/^Saved$/}).first().waitFor();
  assert.equal(puts,1,'Shortcut saves a changed investigation once');
  assert.equal(await page.getByRole('button',{name:'Save investigation',exact:true}).isDisabled(),true);await page.keyboard.press('Control+s');await page.waitForTimeout(400);
  assert.equal(puts,1,'Shortcut does not write an unchanged investigation');assert.equal(revision,1);
  assert.equal(await page.getByRole('heading',{level:1,name:'Does signaling affect agreement?',exact:true}).count(),1,'Page heading is the research question');
  assert.equal(saved.case.question,'Does signaling affect agreement?');const claimId=saved.claims[0].id;
  assert.match(await workspace.getByRole('heading',{name:/^Next: /}).innerText(),/capture a finding/i,'Guide advances to evidence capture');
  await noOverflow('Overview');
  await page.waitForTimeout(400);await page.screenshot({path:path.resolve(__dirname,`../../.meos/artifacts/investigation-workspace/case-${width}.png`),fullPage:true});
  await nav.getByRole('link',{name:'Evidence',exact:true}).click();
  for(const [index,item] of fixture.findings.entries()){
   const addFinding=workspace.getByRole('button',{name:'Add finding',exact:true});await addFinding.waitFor();if(await addFinding.getAttribute('aria-expanded')!=='true')await addFinding.click();
   if(index===0){
    await workspace.getByLabel("Search the project's sources").fill('agreement');await workspace.getByRole('button',{name:'Search',exact:true}).click();
    await workspace.getByText('Indexed passages only',{exact:false}).waitFor();
    failInspect=true;await workspace.getByRole('button',{name:'Use these lines'}).first().click();await workspace.getByRole('alert').first().waitFor();
    assert.equal(await workspace.getByRole('button',{name:'Attach as finding'}).count(),0,'A failed inspection offers nothing to attach');
    failInspect=false;await workspace.getByRole('button',{name:'Use these lines'}).first().click();
   }else{
    await workspace.getByLabel('Project source').selectOption(item.paper_id);
    await workspace.getByLabel('Start line',{exact:true}).fill('2');
    await workspace.getByRole('button',{name:'Inspect source lines'}).click();
   }
   await workspace.getByRole('button',{name:'Attach as finding'}).click();
   await workspace.getByLabel('Label',{exact:true}).nth(index).fill(item.label);
   await workspace.getByLabel('Observed result',{exact:true}).nth(index).fill(fixture.sources[index].quote);
   await workspace.getByLabel('Author interpretation',{exact:true}).nth(index).fill('Authors describe the synthetic observation.');
   await workspace.getByLabel('Our interpretation',{exact:true}).nth(index).fill('Setup differences require a matched comparison.');
   await workspace.getByLabel('Limitations',{exact:true}).nth(index).fill('Synthetic task family only.');
   await workspace.getByLabel('Setup: intervention',{exact:true}).nth(index).fill(item.setup.intervention);
   await workspace.getByLabel('Setup: task',{exact:true}).nth(index).fill(item.setup.task);
   await workspace.getByLabel('Relate to claim').nth(index).selectOption(claimId);
   const article=workspace.locator('article').nth(index);
   await article.getByLabel('Relationship type').last().selectOption(item.relation_to_claim);
   await article.getByLabel('Select for comparison').check();
  }
  await workspace.getByLabel('Candidate reconciliation (our interpretation)').fill(fixture.reconciliation);
  await page.getByRole('button',{name:'Save investigation',exact:true}).click();
  await page.locator('[role=status]').filter({hasText:/^Saved$/}).first().waitFor();
  assert.equal(saved.findings[0].source.quote,fixture.sources[0].quote,'Search capture stores the inspected lines, not the search excerpt');assert.equal(saved.findings[0].source.quote_sha256,sha(fixture.sources[0].quote));assert.equal(saved.findings[0].source.source_sha256,sha(fixture.sources[0].raw_content));assert.equal(saved.findings[1].source.quote,fixture.sources[1].quote);
  assert.deepEqual(saved.relations.map(r=>r.relation),['supports','qualifies']);
  const comparison=workspace.getByText('Selected comparison',{exact:true}).locator('..');
  assert.match(await comparison.innerText(),/Task family A/);assert.match(await comparison.innerText(),/Task family B/);assert.match(await comparison.innerText(),/80%/);assert.match(await comparison.innerText(),/51%/);
  const artifacts=path.resolve(__dirname,'../../.meos/artifacts/investigation-workspace');fs.mkdirSync(artifacts,{recursive:true});await noOverflow('Evidence');await comparison.scrollIntoViewIfNeeded();await page.waitForTimeout(400);await page.screenshot({path:path.join(artifacts,`evidence-comparison-${width}.png`),fullPage:true});
  await nav.getByRole('link',{name:'Write',exact:true}).click();
  await workspace.getByRole('button',{name:'Create draft',exact:true}).click();
  await pick(saved.findings.map(f=>f.label));
  await workspace.getByRole('button',{name:'Insert editable paragraph'}).first().click();
  await workspace.getByLabel('Paragraph proposal',{exact:true}).fill(fixture.expected_paragraph);
  await workspace.getByRole('button',{name:'Insert paragraph',exact:true}).click();
  await page.getByRole('button',{name:'Save investigation',exact:true}).click();
  await page.locator('[role=status]').filter({hasText:/^Saved$/}).first().waitFor();
  assert.equal(saved.manuscript.sections[0].blocks[0].text,fixture.expected_paragraph);
  await pick([saved.findings[0].label]);
  await workspace.getByRole('button',{name:'Prepare source quote',exact:true}).first().click();await workspace.getByRole('button',{name:'Cancel insertion',exact:true}).click();assert.equal(saved.manuscript.sections[0].blocks.length,1);
  await workspace.getByRole('button',{name:'Prepare source quote',exact:true}).first().click();await workspace.getByRole('button',{name:'Insert paragraph',exact:true}).click();await page.getByRole('button',{name:'Save investigation',exact:true}).click();await page.locator('[role=status]').filter({hasText:/^Saved$/}).first().waitFor();
  assert.equal(saved.manuscript.sections[0].blocks[1].quote_snapshot.quote,fixture.sources[0].quote);
  await page.reload();
  await workspace.getByLabel('Paragraph',{exact:true}).first().waitFor().catch(async error=>{await page.screenshot({path:`/tmp/investigation-reload-${width}.png`,fullPage:true});console.error('Reload diagnostic',width,await workspace.count(),await workspace.getByLabel('Paragraph',{exact:true}).first().count(),JSON.stringify(saved),await page.locator('body').innerText(),errors,unexpected);throw error;});
  assert.equal(await workspace.getByLabel('Paragraph',{exact:true}).first().inputValue(),fixture.expected_paragraph);
  await pick(saved.findings.map(f=>f.label));
  for(const item of saved.findings){
   await workspace.locator('article[id^="block-"]').getByRole('link',{name:item.label,exact:true}).first().click();
   await page.waitForURL(url=>url.pathname.endsWith('/evidence')&&url.searchParams.get('finding')===item.id);assert.equal(new URL(page.url()).searchParams.get('finding'),item.id);
   const article=workspace.locator('#finding-'+item.id);
   assert.equal(await article.locator('blockquote').innerText(),item.source.quote);
   await article.getByRole('button',{name:'Open PDF source',exact:true}).click();
   await page.locator('.page[data-page-number="1"] canvas').first().waitFor({timeout:20000});
   await page.getByRole('button',{name:'Close reader',exact:true}).click();
   // The close is applied inside a view transition, a frame after the click.
   await article.getByRole('button',{name:'Open PDF source',exact:true}).evaluate(el=>new Promise(done=>{const until=performance.now()+1000;const look=()=>el===document.activeElement||performance.now()>until?done():requestAnimationFrame(look);look();}));
   assert.equal(await article.getByRole('button',{name:'Open PDF source',exact:true}).evaluate(el=>el===document.activeElement),true,'Reader close restores focus');
   await nav.getByRole('link',{name:'Write',exact:true}).click();
   const cited=saved.manuscript.sections[0].blocks.find(b=>b.finding_ids.includes(item.id)).id;await page.waitForURL(url=>url.pathname.endsWith('/draft')&&url.searchParams.get('block')===cited);
   await workspace.locator('#block-'+cited).waitFor();assert.equal(await workspace.locator('#block-'+cited).evaluate(el=>{const r=el.getBoundingClientRect();return r.bottom>0&&r.top<innerHeight;}),true,'Citing paragraph is in view after returning to Write');
   assert.equal(await workspace.getByLabel('Paragraph',{exact:true}).first().inputValue(),fixture.expected_paragraph);
  }
  await pick(saved.findings.map(f=>f.label));
  await pick([saved.findings[0].label]);
  await workspace.getByRole('button',{name:'Draft with assistant',exact:true}).first().click();await workspace.getByText('Review selected context and omissions',{exact:true}).click();assert.match(await workspace.locator('details').filter({hasText:'Review selected context and omissions'}).first().innerText(),/Near-control agreement/);
  assert.equal(providerCalls,0,'Opening assistant review invokes no provider');
  await workspace.getByRole('button',{name:'Generate paragraph',exact:true}).first().click();
  await workspace.getByLabel('Assistant proposal').waitFor();
  assert.equal(providerCalls,1);assert.equal(saved.manuscript.sections[0].blocks.length,2);await workspace.getByRole('button',{name:'Inspect '+saved.findings[0].label,exact:true}).click();assert.equal(await workspace.getByLabel('Proposal source context',{exact:true}).locator('blockquote').innerText(),fixture.sources[0].quote);await workspace.getByRole('button',{name:'Open proposal PDF source',exact:true}).click();await page.locator('.page[data-page-number="1"] canvas').first().waitFor();await page.getByRole('button',{name:'Close reader',exact:true}).click();assert.equal(await workspace.getByLabel('Assistant proposal').inputValue(),'AI-proposed qualified synthesis.');await workspace.getByRole('button',{name:'Close source context',exact:true}).click();await page.waitForTimeout(400);await page.screenshot({path:path.join(artifacts,`assistant-review-${width}.png`),fullPage:true});
  await workspace.getByRole('button',{name:'Discard proposal',exact:true}).click();
  assert.equal(saved.manuscript.sections[0].blocks.length,2);
  await workspace.getByRole('button',{name:'Generate paragraph',exact:true}).first().click();
  await workspace.getByLabel('Assistant proposal').waitFor();assert.equal(providerCalls,2);
  await workspace.getByRole('button',{name:'Insert assistant paragraph',exact:true}).click();
  await page.getByRole('button',{name:'Save investigation',exact:true}).click();
  await page.locator('[role=status]').filter({hasText:/^Saved$/}).first().waitFor();
  assert.equal(saved.manuscript.sections[0].blocks.at(-1).provenance.kind,'assistant');
  forceConflict=true;await workspace.getByLabel('Paragraph',{exact:true}).first().fill('Unsaved paragraph survives a conflict.');
  await page.getByRole('button',{name:'Save investigation',exact:true}).click();
  await page.locator('[role=status]').filter({hasText:/^Conflict$/}).waitFor();
  assert.equal(await workspace.getByLabel('Paragraph',{exact:true}).first().inputValue(),'Unsaved paragraph survives a conflict.');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.waitForTimeout(400);await page.screenshot({path:path.join(artifacts,`draft-conflict-${width}.png`),fullPage:true});
  await page.getByRole('button',{name:'Reload latest',exact:true}).click();await page.getByRole('button',{name:'Keep editing',exact:true}).click();
  assert.equal(await workspace.getByLabel('Paragraph',{exact:true}).first().inputValue(),'Unsaved paragraph survives a conflict.');
  forceConflict=false;failSave=true;await page.getByRole('button',{name:'Save investigation',exact:true}).click();await page.locator('[role=status]').filter({hasText:/^Save failed$/}).waitFor();
  assert.equal(await workspace.getByLabel('Paragraph',{exact:true}).first().inputValue(),'Unsaved paragraph survives a conflict.');failSave=false;
  await page.evaluate(()=>{const a=document.createElement('a');a.href='/projects';a.id='leave-project-test';a.textContent='Leave project test';document.body.append(a);});
  page.once('dialog',dialog=>dialog.dismiss());await page.locator('#leave-project-test').click();assert.match(page.url(),new RegExp('/projects/'+projectId+'/draft'));
  // The preview opens in the workspace's right panel (a full-screen sheet on a phone), as a map first.
  const openPreview=async()=>{if(!await page.locator('[data-brief-panel="page"]').count())await workspace.getByRole('button',{name:'Open folded preview',exact:true}).click();const region=page.getByRole('region',{name:'Folded document preview',exact:true});await region.waitFor();if(await region.getAttribute('data-view')!=='read')await region.locator('[data-view-option="read"]').click();return region;};
  const closePreview=async()=>{if(await page.locator('[data-brief-panel]').count())await page.getByRole('button',{name:'Close research brief panel',exact:true}).click();await page.locator('[data-brief-panel]').waitFor({state:'detached'});};
  const storedKeys=()=>page.evaluate(()=>Object.keys(localStorage).filter(key=>key!=='darkMode').sort().join(',')+'|'+Object.keys(sessionStorage).sort().join(','));
  const storedBefore=await storedKeys();
  // Every request to the app counts except the reader's own code chunk and the destination
  // bar's prefetch of the page already open (its Write link, outside the reader). The
  // app-wide analytics beacon batches earlier page views on its own timer and is not the reader's.
  const requested=[];const watch=request=>{const url=new URL(request.url());if(url.origin===new URL(base).origin&&!url.pathname.startsWith('/_next/static/')&&!(url.pathname===new URL(page.url()).pathname&&url.searchParams.has('_rsc')))requested.push(request.method()+' '+request.url());};page.on('request',watch);
  const preview=await openPreview();
  assert.equal(await page.locator('iframe').count(),0,'The folded preview is part of the page');
  const mount=await preview.elementHandle();await preview.scrollIntoViewIfNeeded();
  await preview.getByRole('radio',{name:'Topic',exact:true}).click();
  await preview.getByRole('radio',{name:'Full',exact:true}).click();
  await preview.getByRole('link',{name:'Finding: '+saved.findings[0].label,exact:true}).first().waitFor();await page.waitForTimeout(600);
  page.off('request',watch);assert.deepEqual(requested,[],'Opening and folding the preview makes no request');
  assert.equal(await preview.locator('input,textarea,[contenteditable]').count(),0,'The preview has no editing control');
  // On the map, cited findings are shared nodes joined to the paragraphs that cite them.
  await preview.locator('[data-view-option="map"]').click();
  assert.ok(await preview.locator('[data-map-node="unit"]').count()>=2,'Draft paragraphs are on the map');
  assert.ok(await preview.locator('[data-map-node="finding"]').count()>=1,'Cited findings are on the map');
  assert.ok(await preview.locator('path[data-edge="cites"]').count()>=1,'Paragraphs are joined to the findings they cite');
  // The map does not scroll: focus brings a node into view, as Tab does for a reader.
  const finding=preview.getByRole('button',{name:'Finding: '+saved.findings[0].label,exact:true});await finding.focus();await finding.click();
  await preview.getByRole('link',{name:'Open in Evidence',exact:true}).waitFor();
  await page.waitForTimeout(300);await page.screenshot({path:path.join(artifacts,`draft-map-${width}.png`)});
  await preview.locator('[data-view-option="read"]').click();
  await page.waitForTimeout(400);await page.screenshot({path:path.join(artifacts,`draft-fold-${width}.png`),fullPage:true});
  await page.evaluate(()=>{localStorage.setItem('darkMode','dark');document.documentElement.classList.add('dark');});
  await page.waitForFunction(()=>document.documentElement.classList.contains('dark'));
  assert.equal(await workspace.getByLabel('Paragraph',{exact:true}).first().inputValue(),'Unsaved paragraph survives a conflict.');
  assert.equal(await mount.evaluate(el=>el.isConnected),true,'Theme change preserves the preview');
  assert.equal(await preview.getAttribute('data-level'),'full','Theme change keeps the reading level');
  assert.equal(await storedKeys(),storedBefore,'The preview stores nothing in the browser');
  assert.equal(providerCalls,2,'Folding, theme changes and saves cause no model calls');
  const nativeText=await preview.innerText();
  assert.match(nativeText,/AI-authored prose/,'Preview labels assistant authorship');
  assert.match(nativeText,/Human-authored prose/,'Preview labels manual prose');
  assert.match(nativeText,/Exact source quotation — captured version/,'Preview labels captured quotation');
  assert.ok(nativeText.includes(fixture.sources[0].quote),'Quotation preserves exact captured wording');
  await preview.scrollIntoViewIfNeeded();await page.waitForTimeout(400);await page.screenshot({path:path.join(artifacts,`draft-native-dark-${width}.png`),fullPage:true});
  const nativeFinding=preview.getByRole('link',{name:'Finding: '+saved.findings[0].label,exact:true}).first();
  await nativeFinding.click();
  await page.waitForURL(url=>url.pathname.endsWith('/evidence')&&url.searchParams.get('finding')===saved.findings[0].id);
  assert.equal(await workspace.locator('#finding-'+saved.findings[0].id).locator('blockquote').innerText(),fixture.sources[0].quote);
  if(width<768)assert.equal(await page.locator('[data-brief-panel]').count(),0,'On a phone, following a finding closes the sheet so the evidence is visible');
  await nav.getByRole('link',{name:'Write',exact:true}).click();
  assert.equal(await workspace.getByLabel('Paragraph',{exact:true}).first().inputValue(),'Unsaved paragraph survives a conflict.','Native source navigation retains unsaved prose');
  await page.getByRole('button',{name:'Save investigation',exact:true}).click();await page.locator('[role=status]').filter({hasText:/^Saved$/}).first().waitFor();
  await nav.getByRole('link',{name:'Overview',exact:true}).click();await workspace.getByLabel('Claim statement').first().waitFor();
  assert.equal(await workspace.getByRole('heading',{name:/^Next: /}).count(),0,'Guide disappears once every step has happened');
  assert.match(await workspace.locator('#claim-'+saved.claims[0].id).innerText(),/Supports 1[\s\S]*Qualifies 1/,'Claim shows linked evidence counts');
  await noOverflow('Populated overview');
  for(const theme of ['dark','light']){
   await page.evaluate(theme=>{localStorage.setItem('darkMode',theme);document.documentElement.classList.toggle('dark',theme==='dark');},theme);const suffix=theme==='dark'?'-dark':'';
   await nav.getByRole('link',{name:'Overview',exact:true}).click();await workspace.getByLabel('Claim statement').first().waitFor();{const region=await openPreview();assert.match(await region.innerText(),/provisional answer/i,'Overview preview shows the case');}await page.waitForTimeout(400);await page.screenshot({path:path.join(artifacts,`overview${suffix}-${width}.png`),fullPage:true});await closePreview();
   await nav.getByRole('link',{name:'Evidence',exact:true}).click();await workspace.getByRole('heading',{name:'Evidence',exact:true}).waitFor();{const region=await openPreview();await region.getByRole('heading',{name:saved.findings[0].label,exact:true}).waitFor();}await page.waitForTimeout(400);await page.screenshot({path:path.join(artifacts,`evidence${suffix}-${width}.png`),fullPage:true});await closePreview();
   await nav.getByRole('link',{name:'Write',exact:true}).click();await workspace.getByLabel('Paragraph',{exact:true}).first().waitFor();await noOverflow('Write');await page.waitForTimeout(400);await page.screenshot({path:path.join(artifacts,`write${suffix}-${width}.png`),fullPage:true});
  }
  sourceChanged=true;await page.reload();await workspace.getByText('Evidence changed — review needed',{exact:false}).first().waitFor();assert.equal(await workspace.getByLabel('Paragraph',{exact:true}).first().inputValue(),'Unsaved paragraph survives a conflict.');await page.waitForTimeout(400);await page.screenshot({path:path.join(artifacts,`draft-source-changed-${width}.png`),fullPage:true});
  project.role='viewer';await page.goto(`${base}/projects/${projectId}/evidence`);await workspace.getByRole('heading',{name:'Evidence',exact:true}).waitFor();if(!(await workspace.getByLabel('Observed result',{exact:true}).first().isVisible().catch(()=>false)))await workspace.locator('article[id^="finding-"]').first().locator('button[aria-expanded]').first().click();assert.equal(await workspace.getByLabel('Observed result',{exact:true}).first().getAttribute('readonly'),'');assert.equal(await page.getByRole('button',{name:'Save investigation',exact:true}).count(),0,'Viewers are not offered Save');{const region=await openPreview();await region.getByRole('radio',{name:'Full',exact:true}).click();assert.equal(await region.getAttribute('data-level'),'full','Viewers can fold the preview');assert.equal(await region.locator('input,textarea,[contenteditable]').count(),0);await closePreview();}await workspace.getByLabel('Select for comparison').first().check();await workspace.getByText('Selected comparison',{exact:true}).waitFor();await workspace.getByRole('button',{name:'Open PDF source',exact:true}).first().click();await page.locator('.page[data-page-number="1"] canvas').first().waitFor();await page.getByRole('button',{name:'Close reader',exact:true}).click();assert.equal(await workspace.getByRole('button',{name:'Open PDF source',exact:true}).first().isEnabled(),true);
  project.role='admin';failProject=true;await page.goto(`${base}/projects/${projectId}/overview`);await page.getByRole('main').getByRole('alert').filter({hasText:/./}).first().waitFor();assert.equal(await page.getByLabel('Question',{exact:true}).count(),0,'A failed project request does not render a read-only case');failProject=false;
  assert.deepEqual(errors,[]);assert.deepEqual(unexpected,[]);await page.close();
 }console.log('Production desktop/mobile manual/assistant insertion-discard, reload/conflict, folded previews on Overview, Evidence and Write without requests or storage, AI/human/quotation attribution, finding link with unsaved prose, viewer preview and PDF, brief-only initialization and theme preservation passed.');}
 finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
