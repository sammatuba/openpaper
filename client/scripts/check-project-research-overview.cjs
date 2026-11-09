// Run against a local production build; all API calls are mocked, no model calls.
// OPENPAPER_PLAYWRIGHT_MODULE and OPENPAPER_CHROMIUM optionally name local installs.
const { chromium } = require(process.env.OPENPAPER_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const base = process.env.OPENPAPER_BROWSER_BASE || 'http://127.0.0.1:3011';
const fixture = `# The question
Does component-level AI control remain safe when agents and tools compose?

## Why this matters
Privileged access may allow locally permitted actions to combine into an unauthorized outcome. Catastrophic harm requires additional scale, capability, persistence and failed containment; a toy workflow does not establish these.

## Evidence for concern
A controlled study observed boundary crossings through inter-agent content. This motivates testing composition but does not demonstrate a production exploit. [Primary source][primary].

## Evidence against or constraining the concern
Well-designed monitoring protocols improve safety over simple baselines. The result depends on tasks and assumptions and is not a universal defense.

## Tension and possible reconciliation
Are failures ordinary permissions bugs or failures requiring interaction? Task difficulty, visibility and action budgets may explain different findings.

## Discriminating experiment
Randomize isolated versus interacting execution with matched computation and a fixed global invariant. Measure executed forbidden actions, legitimate-task success and false blocks.

## Update and abandonment criteria
If violations disappear under correctly enforced end-to-end authorization, shift toward policy expressiveness and utility costs.

## Sources and limitations
This is a scoping dossier; novelty and comprehensive coverage have not been assessed.

[primary]:
https://example.org/source?q=&amp;copy; "Literal &amp;amp;"`;

(async () => {
    const browser = await chromium.launch({ headless: true, executablePath: process.env.OPENPAPER_CHROMIUM || undefined, args: ['--no-sandbox'] });
    for (const width of [1440, 390]) {
        const page = await browser.newPage({ viewport: { width, height: 960 }, reducedMotion: width === 1440 ? 'no-preference' : 'reduce', acceptDownloads: true });
        const errors = [], writes = [], reads = [];
        let failSave = false, empty = false, role = 'admin';
        let project = { id: 'research-demo', title: 'Compositional AI control across trust boundaries', description: fixture, research_brief: null, role, created_at: '', updated_at: '' };
        page.on('pageerror', e => errors.push(e.stack || e.message));
        await page.addInitScript(() => { localStorage.setItem('project-artifacts-collapsed', 'true'); localStorage.setItem('project-rail-collapsed', 'true'); });
        await page.route('**/api/**', async route => {
            const req = route.request(), url = new URL(req.url());
            reads.push(`${req.method()} ${url.pathname}`);
            let body = [], status = 200;
            const headers = { 'access-control-allow-origin': base, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'content-type', 'access-control-allow-methods': 'GET,POST,PATCH,OPTIONS' };
            if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
            if (url.pathname === '/api/auth/me') body = { success: true, user: {id:'u',name:'Researcher',email:'test@example.org',is_active:true,is_blocked:false} };
            else if (url.pathname === '/api/subscription/usage') body = { limits:{knowledge_base_size:100,paper_uploads:100,chat_credits_weekly:100}, usage:{knowledge_base_size:0,paper_uploads:0,chat_credits_used:0} };
            else if (url.pathname === '/api/projects/research-demo') {
                if (req.method() === 'PATCH') {
                    const update = JSON.parse(req.postData()); writes.push(update);
                    if (failSave) { status = 500; body = {message:'Synthetic save failure'}; }
                    else { project = {...project,...update}; body = {...project,role}; }
                } else body = {...project,role};
            } else if (url.pathname === '/api/projects/papers/research-demo') body = {papers:empty ? [] : [{id:'paper-1',title:'Control study',authors:[],status:'read'}]};
            else if (url.pathname === '/api/projects/conversations/research-demo') body = [];
            else if (url.pathname === '/api/conversation/everything') body = [];
            else if (url.pathname === '/api/projects/invitations/research-demo/') body = {invitations:[]};
            else if (url.pathname === '/api/projects/tables/jobs/research-demo') body = {jobs:[]};
            else if (url.pathname === '/api/projects/artifacts/research-demo') body = {artifacts:[]};
            return route.fulfill({status,headers,contentType:'application/json',body:JSON.stringify(body)});
        });
        await page.goto(`${base}/projects/research-demo`);
        await page.getByRole('heading', {name:project.title,exact:true}).waitFor().catch(async error => {
            console.error('Initial browser state:', page.url(), await page.locator('body').innerText(), {errors,reads});
            throw error;
        });
        const readerReady = async () => {
            if (!await page.locator('#research-brief').evaluate(el => el.open)) await page.locator('#research-brief > summary').click();
            return page.locator('[data-reader-ready="true"]').waitFor().catch(async error => {
                console.error('Native reader state', errors, await page.locator('body').innerText());
                throw error;
            });
        };
        await readerReady();
        const native = page.frameLocator('iframe[title="Textfold research reader"]');
        const engine = page.frames().find(f => f !== page.mainFrame());
        const settled = async (target, level) => target.waitForFunction(expected => { const r=window.__reader; return r.level===expected && Math.abs(r.pos-expected)<0.001 && !document.documentElement.classList.contains('morphing') && !r.staged; },level);
        const rest = async level => settled(engine,level);
        await rest(0);
        assert.equal(await engine.evaluate(() => JSON.parse(document.getElementById('paper-data').textContent).openpaper.commit), '92ad625ab6887bf0060374c1fd86a558513baed2');
        assert.equal(await engine.evaluate(() => typeof window.__reader.scrubTo), 'function');
        await native.locator('.mmap:not([hidden])').waitFor();
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        assert.equal(writes.length, 0);
        await page.screenshot({path:`/tmp/openpaper-research-${width}.png`,fullPage:true});
        await page.locator('iframe').evaluate(element => element.scrollIntoView({block:'start'}));
        await page.screenshot({path:`/tmp/openpaper-textfold-${width}.png`});
        await native.locator('#zoombar button[data-l="4"]').click().catch(async error => {
            console.error('Native geometry',await engine.evaluate(() => ({width:innerWidth,height:innerHeight,button:document.querySelector('#zoombar button').getBoundingClientRect().toJSON(),footer:document.querySelector('.zoom').getBoundingClientRect().toJSON(),html:document.documentElement.scrollWidth})),await page.locator('iframe').boundingBox());
            throw error;
        });
        await rest(4);
        const evidence = native.locator('.u[data-u="op-u-2-0"]');
        const citation = evidence.getByRole('link', {name:'Primary source',exact:true});
        await citation.waitFor();
        assert.equal(await citation.getAttribute('href'), 'https://example.org/source?q=&copy;');
        assert.equal(await citation.getAttribute('title'), 'Literal &amp;');
        assert.ok(await evidence.locator('[data-id]').count() > 3, 'upstream word identities are present');
        await native.locator('#zoombar button[data-l="2"]').click();
        await rest(2);
        await evidence.click();
        await rest(2);
        assert.equal(await evidence.getAttribute('data-l'), '4', 'native local unfolding');
        assert.equal(await native.locator('#doc').getAttribute('data-level'), '2', 'other paragraphs stay folded');
        await native.locator('#zoombar button[data-l="3"]').focus();
        await page.keyboard.press('1');
        await rest(4);
        assert.equal(await native.locator('#doc').getAttribute('data-level'), '4');
        await native.locator('#zoombar button[data-l="0"]').click();
        await rest(0);
        if (width === 1440) {
            await engine.evaluate(() => window.__reader.scrubTo(2.5));
            await engine.waitForFunction(() => window.__reader.pos > 2 && window.__reader.pos < 3);
            assert.equal(await engine.evaluate(() => window.__reader.pos > 2 && window.__reader.pos < 3),true);
            await engine.evaluate(() => window.__reader.letGo());
            await engine.waitForFunction(() => Math.abs(window.__reader.pos-Math.round(window.__reader.pos))<0.001 && !document.documentElement.classList.contains('morphing') && !window.__reader.staged);
        }
        const downloadPromise = page.waitForEvent('download');
        await page.getByRole('button', {name:'Export Textfold',exact:true}).click();
        const download = await downloadPromise;
        const doc = JSON.parse(await fs.readFile(await download.path(), 'utf8'));
        assert.equal(doc.source_text, fixture);
        assert.equal(doc.provenance.ai_generated, false);
        await page.getByRole('button', {name:'Assess relevance & novelty',exact:false}).click();
        await page.getByText('Review discussion instructions', {exact:true}).click();
        assert.match(await page.locator('#research-session details').innerText(), /do not assert novelty from missing papers/);
        assert.equal(writes.length, 0);
        await page.getByRole('button', {name:'Edit brief',exact:true}).click();
        const dialog = page.getByRole('dialog');
        await page.getByLabel('Project title', {exact:true}).fill('Draft survives failure');
        failSave = true;
        await dialog.getByRole('button', {name:'Save brief',exact:true}).click();
        await dialog.getByRole('alert').getByText(/draft is still here/).waitFor();
        assert.equal(await page.getByLabel('Project title', {exact:true}).inputValue(), 'Draft survives failure');
        failSave = false;
        const ai = structuredClone(doc);
        ai.provenance = {ai_generated:true,local:false,model:'fixture-model'};
        ai.written = ['topic','takeaway','key'];
        ai.sections[0].title += ' {{SCRIPTS}} $&';
        Object.assign(ai.sections[0].units[0], {id:'__proto__',role:'"><img src=x onerror=window.__openpaperInjected=1>',key:'Short.',takeaway:'The evidence for the evidence is a much longer independent takeaway.',topic:'The evidence for the evidence'});
        ai.sections[0].units.push({id:'exact-quote',kind:'paragraph',full:'A [source](https://a.example). a [source](https://b.example).',sentences:['A [source](https://a.example).','a [source](https://b.example).'],evidence:[1],brief:['a [source](https://b.example).'],key:'The second source is selected.',takeaway:'The second source is selected.',topic:'second source'});
        await page.getByLabel('Import Textfold JSON file', {exact:true}).setInputFiles({name:'fold.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(ai))});
        await dialog.getByText(/AI-written summaries/).waitFor();
        await dialog.getByRole('button', {name:'Save brief',exact:true}).click();
        await page.getByRole('heading', {name:'Draft survives failure',exact:true}).waitFor();
        await page.getByText(/AI-written summaries · fixture-model/).waitFor();
        await readerReady();
        const importedNative = page.frameLocator('iframe[title="Textfold research reader"]');
        const importedFrame = page.frames().find(f => f !== page.mainFrame());
        await page.locator('iframe').evaluate(element => element.scrollIntoView({block:'start'}));
        await settled(importedFrame,0);
        await importedNative.locator('#zoombar button[data-l="2"]').click();
        await settled(importedFrame,2);
        assert.match(await importedNative.locator('.u[data-u="op-u-0-0"]').innerText(),/Short\./);
        await importedNative.locator('#zoombar button[data-l="1"]').click();
        await settled(importedFrame,1);
        assert.match(await importedNative.locator('.u[data-u="op-u-0-0"]').innerText(),/The evidence for the evidence/);
        await importedNative.locator('#zoombar button[data-l="3"]').click();
        await settled(importedFrame,3);
        assert.equal(await importedNative.locator('.u[data-u="op-u-0-1"] a').getAttribute('href'),'https://b.example');
        assert.match(await importedNative.locator('.u[data-u="op-u-0-1"]').textContent(),/^a source\./);
        await importedNative.locator('#zoombar button[data-l="0"]').click();
        await settled(importedFrame,0);
        assert.match((await importedNative.locator('.u[data-u="op-u-0-0"]').textContent()).replace(/\s+/g,' '),/The evidence for the evidence/);
        assert.equal(await importedFrame.evaluate(() => window.__openpaperInjected),undefined);
        assert.equal(await importedFrame.evaluate(() => JSON.parse(document.getElementById('paper-data').textContent).units['op-u-0-0'].lad.role),'context');
        await importedNative.locator('#zoombar button[data-l="1"]').click();
        await settled(importedFrame,1);
        await importedFrame.evaluate(() => {
            const text = document.querySelector('.u[data-u="op-u-0-0"] .tx');
            const range = document.createRange(); range.selectNodeContents(text);
            const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
            document.dispatchEvent(new Event('selectionchange'));
            text.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));
        });
        await importedNative.locator('.selbar [data-act="hl"]:not([data-s])').click();
        const savedNotes = await importedFrame.evaluate(() => { const data=JSON.parse(document.getElementById('paper-data').textContent); return JSON.parse(localStorage.getItem(`dr-notes:${data.meta.id}:${data.saved}`)); });
        assert.equal(savedNotes[0].anchor.shown.exact,ai.sections[0].units[0].takeaway);
        await page.reload(); await readerReady();
        const restored = page.frameLocator('iframe[title="Textfold research reader"]');
        const restoredFrame = page.frames().find(f => f !== page.mainFrame());
        await page.locator('iframe').evaluate(element => element.scrollIntoView({block:'start'}));
        await settled(restoredFrame,0);
        await restored.locator('#zoombar button[data-l="1"]').click();
        await settled(restoredFrame,1);
        assert.ok(await restored.locator('.u[data-u="op-u-0-0"] .hl').count() > 0,'Takeaway highlight restores');
        await restored.locator('#zoombar button[data-l="2"]').click();
        await settled(restoredFrame,2);
        assert.equal(await restored.locator('.u[data-u="op-u-0-0"] .tx .hl').count(),0,'Takeaway mark must not label unrelated Key words');
        await restoredFrame.evaluate(() => { window.showSaveFilePicker = undefined; });
        await restored.locator('.savebtn').click();
        await restored.locator('.svdlg input[name="what"][value="marks"]').check();
        await restored.locator('.svdlg input[name="fmt"][value="json"]').check();
        const notesDownloadPromise = page.waitForEvent('download');
        await restored.locator('.svdlg button[type="submit"]').click();
        const notesDownload = await notesDownloadPromise.catch(async error => {
            console.error('Native save state',await restored.locator('.svdlg').innerText(),await restoredFrame.evaluate(() => ({picker:typeof window.showSaveFilePicker,selection:document.querySelector('.svdlg form') && Object.fromEntries(new FormData(document.querySelector('.svdlg form')))})),errors);
            throw error;
        });
        const exportedNotes = JSON.parse(await fs.readFile(await notesDownload.path(),'utf8'));
        assert.equal(exportedNotes.notes[0].anchor.shown.exact,ai.sections[0].units[0].takeaway);
        assert.equal(writes.at(-1).research_brief.format, 'textfold/doc');
        await page.getByRole('button', {name:'Edit brief',exact:true}).click();
        await page.getByLabel('Research brief · Markdown', {exact:true}).fill(`${fixture}\n\nNew source context.`);
        await dialog.getByText(/replaced by local excerpts/).waitFor();
        await dialog.getByRole('button', {name:'Save brief',exact:true}).click();
        await page.getByText(/Local excerpts · first sentences/).waitFor();
        assert.equal(writes.at(-1).research_brief, null);
        role = 'viewer';
        await page.reload();
        await readerReady();
        assert.equal(await page.getByRole('button', {name:'Edit brief',exact:true}).count(), 0);
        role = 'admin'; empty = true;
        await page.reload();
        await readerReady();
        await page.getByRole('heading', {name:'Start by adding your evidence'}).waitFor();
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        assert.deepEqual(errors, []);
        console.log(`${width}px: UPSTREAM engine/map, stable word IDs, native local unfolding, keyboard, citations, export, import/save, draft retention, invalidation and access checks passed`);
        await page.close();
    }
    await browser.close();
})().catch(e => {console.error(e);process.exit(1)});
