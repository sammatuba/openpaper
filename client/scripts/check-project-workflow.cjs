// Local production UI only: intercept every API request, including model streams.
const { chromium } = require(process.env.OPENPAPER_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const base = process.env.OPENPAPER_BROWSER_BASE || 'http://127.0.0.1:3011';

(async () => {
    const browser = await chromium.launch({headless:true,executablePath:process.env.OPENPAPER_CHROMIUM || undefined,args:['--no-sandbox']});
    try {
        for (const width of [1440,390]) {
            const page = await browser.newPage({viewport:{width,height:1100},colorScheme:width===1440?'dark':'light'});
            let role='admin',empty=false,limited=false,failStart=false;
            const writes=[],streams=[],errors=[];
            page.on('pageerror',error=>errors.push(error.message));
            const project={id:'research-demo',title:'Strategic evidence laundering',description:'# The question\nDo reciprocal incentives amplify source-dependent evidence?\n\n## Evidence for\nOne controlled study motivates a matched comparison.\n\n## Evidence against\nA negative result constrains the claim.',research_brief:null};
            const papers=[{id:'p1',title:'Source dependence study',authors:[],status:'read',created_at:'2026-11-08'},{id:'p2',title:'Incentive study',authors:[],status:'read',created_at:'2026-11-07'}];
            const conversations=[{id:'older',title:'Earlier synthesis',updated_at:'2026-11-07'},{id:'recent',title:'Latest evidence comparison',updated_at:'2026-11-08'}];
            await page.route('**/api/**',async route=>{
                const req=route.request(),path=new URL(req.url()).pathname;
                let body=[],status=200;
                const headers={'access-control-allow-origin':base,'access-control-allow-credentials':'true','access-control-allow-headers':'content-type','access-control-allow-methods':'GET,POST,PATCH,OPTIONS'};
                if(req.method()==='OPTIONS') return route.fulfill({status:204,headers});
                if(req.method()!=='GET') writes.push({path,body:req.postDataJSON()});
                if(path==='/api/auth/me') body={success:true,user:{id:'u',name:'Researcher',email:'local@example.org',is_active:true,is_blocked:false}};
                else if(path==='/api/subscription/usage') body={limits:{knowledge_base_size:100,paper_uploads:100,chat_credits_weekly:100},usage:{knowledge_base_size:0,paper_uploads:0,chat_credits_used:limited?100:0}};
                else if(path==='/api/projects/research-demo') body={...project,role};
                else if(path==='/api/projects/papers/research-demo') body={papers:empty?[]:papers};
                else if(path==='/api/projects/conversations/research-demo') {
                    if(req.method()==='POST') {
                        status=failStart?500:200;body=failStart?{message:'Synthetic failure'}:{id:'new-discussion'};
                        if(!failStart) conversations.unshift({id:'new-discussion',title:req.postDataJSON().title,updated_at:'2026-11-09'});
                    }
                    else body=conversations;
                } else if(path.startsWith('/api/projects/conversations/research-demo/')) body={messages:path.endsWith('/new-discussion')?[{role:'assistant',content:'Saved synthesis result.'}]:[],is_owner:role!=='viewer'};
                else if(path==='/api/projects/artifacts/research-demo') body={artifacts:[]};
                else if(path==='/api/projects/tables/jobs/research-demo') body={jobs:[]};
                else if(path==='/api/projects/invitations/research-demo/') body={invitations:[]};
                else if(path==='/api/message/chat/everything') {
                    streams.push(req.postDataJSON());
                    return route.fulfill({status:200,headers,contentType:'text/plain',body:JSON.stringify({type:'content',content:'Mock evidence comparison; verify its sources.'})+'END_OF_STREAM'});
                }
                return route.fulfill({status,headers,contentType:'application/json',body:JSON.stringify(body)});
            });
            const home=async()=>{await page.goto(`${base}/projects/research-demo`);await page.getByRole('heading',{name:project.title,exact:true}).waitFor();};
            const main=page.getByRole('main').last();
            const returnToWorkspace=async()=>{
                if(width<768) await page.getByRole('button',{name:'Open project navigation',exact:true}).click();
                await page.getByRole('link',{name:'Research workspace',exact:true}).click();
                await main.getByRole('heading',{name:'What do you want to work on?'}).waitFor();
                assert.equal(await page.getByRole('dialog').count(),0,'mobile navigation closes after navigation');
            };
            await home();
            await main.getByRole('heading',{name:'What do you want to work on?'}).waitFor();
            await page.screenshot({path:`/tmp/openpaper-workflow-${width}.png`,fullPage:true});
            assert.equal(await page.getByRole('heading',{name:'Artifacts',exact:true}).count(),0,'first visit leaves artifacts closed');
            assert.equal(await page.locator('#research-brief').evaluate(el=>el.open),false);
            assert.equal(await page.locator('iframe').count(),0,'closed brief does not initialize a hidden reader');
            assert.match(await main.innerText(),/Do reciprocal incentives amplify/);
            const resume=main.getByRole('link',{name:'Latest evidence comparison'});
            assert.equal(await resume.getAttribute('href'),'/projects/research-demo/conversations/recent');
            assert.equal(await main.locator('section').first().getByRole('link').first().innerText(),'Latest evidence comparison');
            await main.getByRole('button',{name:'Plan the next experiment',exact:false}).click();
            await main.locator('textarea').fill('Separate duplication from strategic coordination.');
            await main.getByRole('button',{name:'Resolve the tension',exact:false}).click();
            assert.equal((await main.locator('textarea').inputValue()).trim(),'Separate duplication from strategic coordination.');
            await main.getByText('Review discussion instructions',{exact:true}).click();
            assert.match(await main.locator('#research-session details').innerText(),/Missing evidence is not counterevidence/);
            assert.equal(writes.length,0,'choosing a task never writes or invokes a model');
            await main.getByRole('button',{name:'Add context',exact:true}).click();
            await main.getByRole('button',{name:'Source dependence study',exact:false}).click();
            failStart=true;
            await main.getByRole('button',{name:'Start synthesis',exact:true}).click();
            await main.getByRole('alert').waitFor();
            assert.equal((await main.locator('textarea').inputValue()).trim(),'Separate duplication from strategic coordination.');
            assert.equal(streams.length,0);
            failStart=false;
            await main.getByRole('button',{name:'Start synthesis',exact:true}).click();
            await page.waitForURL('**/projects/research-demo/conversations/new-discussion');
            await page.getByText('Mock evidence comparison; verify its sources.',{exact:false}).waitFor();
            assert.equal(streams.length,1);
            assert.match(streams[0].user_query,/Reconcile conflicting findings/);
            assert.match(streams[0].user_query,/Separate duplication from strategic coordination/);
            assert.match(streams[0].user_query,/Do reciprocal incentives amplify/);
            assert.deepEqual(streams[0].mentioned_paper_ids,['p1']);
            assert.equal(writes.filter(w=>w.path==='/api/projects/research-demo').length,0,'sessions do not overwrite the brief');

            // Workspace home is reachable from a conversation on desktop and mobile.
            await returnToWorkspace();
            await main.getByRole('link',{name:'Resolve the tension',exact:true}).waitFor({timeout:5000});
            assert.equal(await main.locator('section').first().getByRole('link').first().innerText(),'Resolve the tension','newly created discussion is immediately resumable without a reload');
            await main.getByRole('link',{name:'Resolve the tension',exact:true}).click();
            await page.waitForURL('**/projects/research-demo/conversations/new-discussion');
            await page.getByText('Saved synthesis result.',{exact:true}).waitFor();
            assert.equal(streams.length,1,'resuming loads saved messages without resubmitting the prompt');
            await returnToWorkspace();
            assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
            await main.getByRole('button',{name:'Ask my own question',exact:true}).click();
            assert.equal(await main.getByRole('button',{name:'Start discussion',exact:true}).isDisabled(),true);
            await main.locator('textarea').fill('What remains unknown?');
            assert.equal(await main.getByRole('button',{name:'Start discussion',exact:true}).isEnabled(),true);

            // The existing native brief remains accessible from the task workspace.
            await main.getByRole('button',{name:'Read or update the brief',exact:true}).click();
            await page.locator('[data-reader-ready="true"]').waitFor();
            await main.getByRole('button',{name:'Edit brief',exact:true}).waitFor();
            await home();
            role='viewer'; await home();
            await main.getByText(/You have view access/).waitFor();
            assert.equal(await main.locator('textarea').count(),0);
            await page.locator('#research-brief > summary').click();
            await page.locator('[data-reader-ready="true"]').waitFor();
            assert.equal(await main.getByRole('button',{name:'Edit brief',exact:true}).count(),0);
            role='editor'; await home();
            await main.getByRole('heading',{name:'What do you want to work on?'}).waitFor();
            await main.getByText(/Share conclusions with a project admin/).waitFor();
            // Imported Full text, rather than an older description or AI takeaway,
            // is the context for a guided discussion of the current working brief.
            const full='Does independent provenance change the decision?';
            project.research_brief={format:'textfold/doc',version:0,id:'imported',title:project.title,lang:'en',levels:['topic','takeaway','key','brief','full'],written:[],provenance:{ai_generated:false,local:true},sections:[{id:'s1',title:'The question',depth:1,takeaway:full,topic:'Provenance',units:[{id:'u1',kind:'paragraph',full,sentences:[full],evidence:[0],brief:[full],key:full,takeaway:full,topic:'Provenance'}]}],links:[]};
            await home();
            await main.getByText('Review discussion instructions',{exact:true}).click();
            const importedPrompt=await main.locator('#research-session details').innerText();
            assert.match(importedPrompt,/Does independent provenance change the decision/);
            assert.doesNotMatch(importedPrompt,/Do reciprocal incentives amplify/);
            project.research_brief=null;
            role='admin';limited=true;await home();
            await main.getByText(/Your chat credit limit has been reached/).waitFor();
            assert.equal(await main.getByRole('button',{name:'Start evidence comparison',exact:true}).isDisabled(),true);
            const before=writes.length;
            await main.locator('textarea').evaluate(el=>el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true})));
            assert.equal(writes.length,before,'Enter cannot bypass the credit limit');
            limited=false;empty=true;await home();
            await main.getByRole('heading',{name:'Start by adding your evidence'}).waitFor();
            assert.equal(await main.locator('textarea').count(),0);
            await main.getByRole('button',{name:'Add from library',exact:true}).click();
            await page.getByRole('dialog').waitFor();
            await page.keyboard.press('Escape');
            // A saved open preference is honored on desktop; mobile stays focused.
            await page.evaluate(()=>localStorage.setItem('project-artifacts-collapsed','false'));
            await home();
            if(width>=768) {
                await page.getByRole('heading',{name:'Artifacts',exact:true}).waitFor();
                await page.getByRole('button',{name:'Close artifacts',exact:true}).click();
                await home();
            }
            assert.equal(await page.getByRole('heading',{name:'Artifacts',exact:true}).count(),0);
            assert.deepEqual(errors,[]);
            console.log(`${width}px: default layout, guided synthesis, scope handoff, draft/retry, saved discussion navigation, brief/native reader, viewer/editor/credit/empty states passed`);
            await page.close();
        }
    } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
