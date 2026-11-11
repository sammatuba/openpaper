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
  const page=await browser.newPage({viewport:{width,height:960},reducedMotion:width===390?'reduce':'no-preference'});const errors=[],unexpected=[];let saved=null,revision=0,forceConflict=false,providerCalls=0,sourceChanged=false,failSave=false;const requests=new Map();
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
    if(request.method()==='PUT'){
     if(failSave){status=500;body={detail:'Synthetic failure'};}
     else if(forceConflict||request.headers()['if-match']!==`"investigation:${projectId}:${revision}"`){status=412;body={detail:'Synthetic conflict'};}
     else{saved=JSON.parse(request.postData()).document;revision++;for(const section of saved.manuscript.sections)for(const block of section.blocks)if(block.kind==='source_quote'&&!block.quote_snapshot)block.quote_snapshot=structuredClone(saved.findings.find(f=>f.id===block.finding_ids[0]).source);}
    }
    if(status===200)body={document:saved||blank(),revision,validation:{findings:Object.fromEntries((saved?.findings||[]).map(f=>[f.id,sourceChanged&&f.source.paper_id===paperId?'source_changed':'current'])),blocks:Object.fromEntries((saved?.manuscript.sections||[]).flatMap(s=>s.blocks).map(b=>[b.id,sourceChanged?'review_needed':'current']))}};
    headers.ETag=`"investigation:${projectId}:${revision}"`;
   }
   else if(p.startsWith(`/api/projects/${projectId}/investigation/sources/`)){const source=fixture.sources.find(source=>p.endsWith('/'+source.id));if(!source)throw Error('Unknown source');body={start_line:2,end_line:2,text:source.quote,source_sha256:sha(source.raw_content),quote_sha256:sha(source.quote)};}
   else if(p.startsWith(`/api/projects/papers/${projectId}/`)&&p.endsWith('/file-url'))body={file_url:base+'/synthetic-fixture.pdf'};
   else if(p===`/api/projects/${projectId}`)body=project;
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
  await page.goto(`${base}/projects/${projectId}`);
  const workspace=page.getByRole('region',{name:'Investigation workspace'});
  await workspace.getByRole('button',{name:'Save investigation',exact:true}).waitFor().catch(async error=>{console.error('Load diagnostic',width,page.url(),await page.locator('body').innerText(),errors,unexpected);await page.screenshot({path:'/tmp/investigation-load.png',fullPage:true});throw error;});
  await workspace.getByRole('button',{name:'Start from existing brief (unsaved)',exact:true}).click();
  assert.equal(await workspace.getByLabel('question',{exact:true}).inputValue(),'A legacy research question?');assert.equal(await workspace.getByLabel('provisional answer',{exact:true}).inputValue(),'Imported synthesis remains provisional.');assert.equal(revision,0);assert.equal(saved,null);
  await workspace.getByLabel('question',{exact:true}).fill('Does signaling affect agreement?');
  await workspace.getByRole('button',{name:'Add claim',exact:true}).click();
  await workspace.getByLabel('Claim statement').fill(fixture.claim.statement);
  await workspace.getByRole('button',{name:'Save investigation',exact:true}).click();
  await workspace.getByRole('status').filter({hasText:'Saved'}).first().waitFor();
  assert.equal(saved.case.question,'Does signaling affect agreement?');const claimId=saved.claims[0].id;
  await page.screenshot({path:path.resolve(__dirname,`../../.meos/artifacts/investigation-workspace/case-${width}.png`),fullPage:true});
  await workspace.getByRole('link',{name:'Evidence',exact:true}).click();
  for(const [index,item] of fixture.findings.entries()){
   await workspace.getByLabel('Project source').selectOption(item.paper_id);
   await workspace.getByLabel('Start line',{exact:true}).fill('2');
   await workspace.getByRole('button',{name:'Inspect source lines'}).click();
   await workspace.getByRole('button',{name:'Attach as finding'}).click();
   await workspace.getByLabel('label',{exact:true}).nth(index).fill(item.label);
   await workspace.getByLabel('observed result',{exact:true}).nth(index).fill(fixture.sources[index].quote);
   await workspace.getByLabel('author interpretation',{exact:true}).nth(index).fill('Authors describe the synthetic observation.');
   await workspace.getByLabel('our interpretation',{exact:true}).nth(index).fill('Setup differences require a matched comparison.');
   await workspace.getByLabel('limitations',{exact:true}).nth(index).fill('Synthetic task family only.');
   await workspace.getByLabel('Setup: intervention',{exact:true}).nth(index).fill(item.setup.intervention);
   await workspace.getByLabel('Setup: task',{exact:true}).nth(index).fill(item.setup.task);
   await workspace.getByLabel('Relate to claim').nth(index).selectOption(claimId);
   const article=workspace.locator('article').nth(index);
   await article.locator('select').last().selectOption(item.relation_to_claim);
   await article.getByLabel('Select for comparison').check();
  }
  await workspace.getByLabel('Candidate reconciliation (our interpretation)').fill(fixture.reconciliation);
  await workspace.getByRole('button',{name:'Save investigation',exact:true}).click();
  await workspace.getByRole('status').filter({hasText:'Saved'}).first().waitFor();
  assert.equal(saved.findings[0].source.quote,fixture.sources[0].quote);assert.equal(saved.findings[1].source.quote,fixture.sources[1].quote);
  assert.deepEqual(saved.relations.map(r=>r.relation),['supports','qualifies']);
  const comparison=workspace.getByText('Selected comparison',{exact:true}).locator('..');
  assert.match(await comparison.innerText(),/Task family A/);assert.match(await comparison.innerText(),/Task family B/);assert.match(await comparison.innerText(),/80%/);assert.match(await comparison.innerText(),/51%/);
  const artifacts=path.resolve(__dirname,'../../.meos/artifacts/investigation-workspace');fs.mkdirSync(artifacts,{recursive:true});await comparison.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,`evidence-comparison-${width}.png`),fullPage:true});
  await workspace.getByRole('link',{name:'Draft',exact:true}).click();
  await workspace.getByRole('button',{name:'Create draft',exact:true}).click();
  await workspace.getByLabel('Evidence for the next paragraph').first().selectOption(saved.findings.map(f=>f.id));
  await workspace.getByRole('button',{name:'Insert editable paragraph'}).first().click();
  await workspace.getByLabel('Paragraph proposal',{exact:true}).fill(fixture.expected_paragraph);
  await workspace.getByRole('button',{name:'Insert paragraph',exact:true}).click();
  await workspace.getByRole('button',{name:'Save investigation',exact:true}).click();
  await workspace.getByRole('status').filter({hasText:'Saved'}).first().waitFor();
  assert.equal(saved.manuscript.sections[0].blocks[0].text,fixture.expected_paragraph);
  await workspace.getByLabel('Evidence for the next paragraph').first().selectOption(saved.findings[0].id);
  await workspace.getByRole('button',{name:'Prepare source quote',exact:true}).first().click();await workspace.getByRole('button',{name:'Cancel insertion',exact:true}).click();assert.equal(saved.manuscript.sections[0].blocks.length,1);
  await workspace.getByRole('button',{name:'Prepare source quote',exact:true}).first().click();await workspace.getByRole('button',{name:'Insert paragraph',exact:true}).click();await workspace.getByRole('button',{name:'Save investigation',exact:true}).click();await workspace.getByRole('status').filter({hasText:'Saved'}).first().waitFor();
  assert.equal(saved.manuscript.sections[0].blocks[1].quote_snapshot.quote,fixture.sources[0].quote);
  await page.reload();
  await workspace.getByLabel('Paragraph',{exact:true}).first().waitFor().catch(async error=>{await page.screenshot({path:`/tmp/investigation-reload-${width}.png`,fullPage:true});console.error('Reload diagnostic',width,await workspace.count(),await workspace.getByLabel('Paragraph',{exact:true}).first().count(),JSON.stringify(saved),await page.locator('body').innerText(),errors,unexpected);throw error;});
  assert.equal(await workspace.getByLabel('Paragraph',{exact:true}).first().inputValue(),fixture.expected_paragraph);
  await workspace.getByLabel('Evidence for the next paragraph').first().selectOption(saved.findings.map(f=>f.id));
  for(const item of saved.findings){
   await workspace.getByRole('link',{name:item.label,exact:true}).first().click();
   await page.waitForURL(url=>url.pathname.endsWith('/evidence')&&url.searchParams.get('finding')===item.id);assert.equal(new URL(page.url()).searchParams.get('finding'),item.id);
   const article=workspace.locator('#finding-'+item.id);
   assert.equal(await article.locator('blockquote').innerText(),item.source.quote);
   await article.getByRole('button',{name:'Open PDF source',exact:true}).click();
   await page.locator('.page[data-page-number="1"] canvas').first().waitFor({timeout:20000});
   await page.getByRole('button',{name:'Close reader',exact:true}).click();
   assert.equal(await article.getByRole('button',{name:'Open PDF source',exact:true}).evaluate(el=>el===document.activeElement),true,'Reader close restores focus');
   await workspace.getByRole('link',{name:'Draft',exact:true}).click();
   assert.equal(await workspace.getByLabel('Paragraph',{exact:true}).first().inputValue(),fixture.expected_paragraph);
  }
  await workspace.getByLabel('Evidence for the next paragraph').first().selectOption(saved.findings.map(f=>f.id));
  await workspace.getByLabel('Evidence for the next paragraph').first().selectOption(saved.findings[0].id);
  await workspace.getByRole('button',{name:'Draft with assistant',exact:true}).first().click();await workspace.getByText('Review selected context and omissions',{exact:true}).click();assert.match(await workspace.locator('details').first().innerText(),/Near-control agreement/);
  assert.equal(providerCalls,0,'Opening assistant review invokes no provider');
  await workspace.getByRole('button',{name:'Generate paragraph',exact:true}).first().click();
  await workspace.getByLabel('Assistant proposal').waitFor();
  assert.equal(providerCalls,1);assert.equal(saved.manuscript.sections[0].blocks.length,2);await workspace.getByRole('button',{name:'Inspect '+saved.findings[0].label,exact:true}).click();assert.equal(await workspace.getByLabel('Proposal source context',{exact:true}).locator('blockquote').innerText(),fixture.sources[0].quote);await workspace.getByRole('button',{name:'Open proposal PDF source',exact:true}).click();await page.locator('.page[data-page-number="1"] canvas').first().waitFor();await page.getByRole('button',{name:'Close reader',exact:true}).click();assert.equal(await workspace.getByLabel('Assistant proposal').inputValue(),'AI-proposed qualified synthesis.');await workspace.getByRole('button',{name:'Close source context',exact:true}).click();await page.screenshot({path:path.join(artifacts,`assistant-review-${width}.png`),fullPage:true});
  await workspace.getByRole('button',{name:'Discard proposal',exact:true}).click();
  assert.equal(saved.manuscript.sections[0].blocks.length,2);
  await workspace.getByRole('button',{name:'Generate paragraph',exact:true}).first().click();
  await workspace.getByLabel('Assistant proposal').waitFor();assert.equal(providerCalls,2);
  await workspace.getByRole('button',{name:'Insert assistant paragraph',exact:true}).click();
  await workspace.getByRole('button',{name:'Save investigation',exact:true}).click();
  await workspace.getByRole('status').filter({hasText:'Saved'}).first().waitFor();
  assert.equal(saved.manuscript.sections[0].blocks.at(-1).provenance.kind,'assistant');
  forceConflict=true;await workspace.getByLabel('Paragraph',{exact:true}).first().fill('Unsaved paragraph survives a conflict.');
  await workspace.getByRole('button',{name:'Save investigation',exact:true}).click();
  await workspace.getByRole('status').filter({hasText:'Conflict'}).waitFor();
  assert.equal(await workspace.getByLabel('Paragraph',{exact:true}).first().inputValue(),'Unsaved paragraph survives a conflict.');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(artifacts,`draft-conflict-${width}.png`),fullPage:true});
  page.once('dialog',dialog=>dialog.dismiss());await workspace.getByRole('button',{name:'Reload latest',exact:true}).click();
  assert.equal(await workspace.getByLabel('Paragraph',{exact:true}).first().inputValue(),'Unsaved paragraph survives a conflict.');
  forceConflict=false;failSave=true;await workspace.getByRole('button',{name:'Save investigation',exact:true}).click();await workspace.getByRole('status').filter({hasText:'Save failed'}).waitFor();
  assert.equal(await workspace.getByLabel('Paragraph',{exact:true}).first().inputValue(),'Unsaved paragraph survives a conflict.');failSave=false;
  await page.evaluate(()=>{const a=document.createElement('a');a.href='/projects';a.id='leave-project-test';a.textContent='Leave project test';document.body.append(a);});
  page.once('dialog',dialog=>dialog.dismiss());await page.locator('#leave-project-test').click();assert.match(page.url(),new RegExp('/projects/'+projectId+'/draft'));
  await workspace.getByRole('button',{name:'Open folded preview',exact:true}).click();
  await workspace.locator('.native-surface').waitFor();
  assert.equal(await page.locator('iframe').count(),0,'New draft preview is native');
  const mount=await workspace.locator('.native-surface').elementHandle();await workspace.getByLabel('Folded document preview',{exact:true}).scrollIntoViewIfNeeded();
  await page.evaluate(()=>{localStorage.setItem('darkMode','dark');document.documentElement.classList.add('dark');});
  await page.waitForFunction(()=>document.querySelector('[aria-label="Folded document preview"] div.relative')?.firstElementChild?.shadowRoot?.querySelector('.native-surface')?.dataset.theme==='dark');
  assert.equal(await workspace.getByLabel('Paragraph',{exact:true}).first().inputValue(),'Unsaved paragraph survives a conflict.');
  assert.equal(await mount.evaluate(el=>el.isConnected),true,'Theme change preserves the native mount');
  assert.equal(providerCalls,2,'Folding, theme changes and saves cause no model calls');
  const nativeText=await workspace.locator('.native-surface .doc').innerText();
  assert.match(nativeText,/AI-authored prose/,'Native preview labels assistant authorship');
  assert.match(nativeText,/Human-authored prose/,'Native preview labels manual prose');
  assert.match(nativeText,/Exact source quotation — captured version/,'Native preview labels captured quotation');
  assert.ok(nativeText.includes(fixture.sources[0].quote),'Native quotation preserves exact captured wording');
  await workspace.getByLabel('Folded document preview',{exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,`draft-native-dark-${width}.png`),fullPage:true});
  const nativeFinding=workspace.locator('.native-surface').getByRole('link',{name:'Finding '+saved.findings[0].id,exact:true}).first();
  await nativeFinding.click();
  await page.waitForURL(url=>url.pathname.endsWith('/evidence')&&url.searchParams.get('finding')===saved.findings[0].id);
  assert.equal(await workspace.locator('#finding-'+saved.findings[0].id).locator('blockquote').innerText(),fixture.sources[0].quote);
  await workspace.getByRole('link',{name:'Draft',exact:true}).click();
  assert.equal(await workspace.getByLabel('Paragraph',{exact:true}).first().inputValue(),'Unsaved paragraph survives a conflict.','Native source navigation retains unsaved prose');
  await workspace.getByRole('button',{name:'Save investigation',exact:true}).click();await workspace.getByRole('status').filter({hasText:'Saved'}).first().waitFor();sourceChanged=true;await page.reload();await workspace.getByText('Evidence changed — review needed',{exact:false}).first().waitFor();assert.equal(await workspace.getByLabel('Paragraph',{exact:true}).first().inputValue(),'Unsaved paragraph survives a conflict.');await page.screenshot({path:path.join(artifacts,`draft-source-changed-${width}.png`),fullPage:true});
  project.role='viewer';await page.goto(`${base}/projects/${projectId}/evidence`);await workspace.getByRole('heading',{name:'Evidence',exact:true}).waitFor();assert.equal(await workspace.getByLabel('observed result',{exact:true}).first().getAttribute('readonly'),'');assert.equal(await workspace.getByRole('button',{name:'Save investigation',exact:true}).isDisabled(),true);await workspace.getByLabel('Select for comparison').first().check();await workspace.getByText('Selected comparison',{exact:true}).waitFor();await workspace.getByRole('button',{name:'Open PDF source',exact:true}).first().click();await page.locator('.page[data-page-number="1"] canvas').first().waitFor();await page.getByRole('button',{name:'Close reader',exact:true}).click();assert.equal(await workspace.getByRole('button',{name:'Open PDF source',exact:true}).first().isEnabled(),true);
  assert.deepEqual(errors,[]);assert.deepEqual(unexpected,[]);await page.close();
 }console.log('Production desktop/mobile manual/assistant insertion-discard, reload/conflict, native AI/human/quotation attribution, native finding callback with unsaved prose, viewer PDF, brief-only initialization and theme preservation passed.');}
 finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
