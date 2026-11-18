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
        await page.goto(`${base}/projects/research-demo/discuss`);
        await page.getByRole('heading', {name:project.title,exact:true}).waitFor().catch(async error => {
            console.error('Initial browser state:', page.url(), await page.locator('body').innerText(), {errors,reads});
            throw error;
        });
        // The brief lives in the workspace's right panel, opened from the project header.
        const panel = page.locator('[data-brief-panel]');
        const openPanel = async () => {
            if (!await panel.count()) await page.getByRole('button', {name:'Toggle research brief panel',exact:true}).click();
            await panel.waitFor();
        };
        const closePanel = async () => {
            if (await panel.count()) await page.getByRole('button', {name:'Close research brief panel',exact:true}).click();
            await panel.waitFor({state:'detached'});
        };
        const readerReady = async (view = 'read') => {
            await openPanel();
            await page.locator('[data-reader-ready="true"]').waitFor().catch(async error => {
                console.error('Reader state', errors, await page.locator('body').innerText());
                throw error;
            });
            if (await page.locator('[data-reader-ready]').getAttribute('data-view') !== view) await page.locator(`[data-view-option="${view}"]`).click();
        };
        const storageKeys = () => page.evaluate(() => Object.keys(localStorage).sort().join(',') + '|' + Object.keys(sessionStorage).sort().join(','));
        const storedBefore = await storageKeys();
        assert.equal(await page.locator('[data-reader-ready]').count(), 0, 'storage baseline is taken before the reader mounts');
        assert.equal(await page.locator('#research-brief').count(), 0, 'the brief is no longer a section at the bottom of Discuss');
        await page.getByRole('button', {name:'Read or update the brief',exact:true}).click();
        await panel.waitFor();
        assert.equal(await page.evaluate(() => document.activeElement?.hasAttribute('data-brief-panel')), true, 'opening the panel moves focus into it');
        await page.keyboard.press('Escape');
        await panel.waitFor({state:'detached'});
        assert.equal(await page.evaluate(() => document.activeElement?.textContent), 'Read or update the brief', 'closing returns focus to the control that opened the panel');
        await readerReady('map');
        const reader = page.getByRole('region', {name:'Folded research brief',exact:true});
        // The map: title, sections and paragraphs as a branching tree.
        const map = reader.locator('[data-fold-map]');
        assert.equal(await reader.getAttribute('data-view'), 'map', 'the brief opens as a map');
        assert.equal(await map.locator('[data-map-node="root"]').innerText(), project.title);
        const sectionNodes = map.locator('[data-map-node="section"]');
        const unitNodes = map.locator('[data-map-node="unit"]');
        const sectionCount = await sectionNodes.count(), unitCount = await unitNodes.count();
        assert.ok(sectionCount >= 3 && unitCount >= sectionCount, `map has ${sectionCount} sections and ${unitCount} paragraphs`);
        assert.equal(await map.locator('path[data-edge="tree"]').count(), sectionCount + unitCount, 'every node hangs from its parent');
        const boxes = await map.locator('[data-map-node]').evaluateAll(nodes => nodes.map(node => { const r = node.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; }));
        assert.equal(boxes.some((a, i) => boxes.some((b, j) => i < j && a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3])), false, 'no two map nodes overlap');
        await page.screenshot({path:`/tmp/openpaper-map-${width}.png`});
        const firstSection = sectionNodes.first();
        const hidden = Number((await firstSection.getAttribute('aria-label')).match(/: (\d+) item/)[1]);
        await firstSection.click();
        assert.equal(await firstSection.getAttribute('aria-expanded'), 'false');
        assert.equal(await unitNodes.count(), unitCount - hidden, 'a section folds its paragraphs away');
        await firstSection.click();
        assert.equal(await unitNodes.count(), unitCount);
        await reader.getByRole('button', {name:'Collapse all',exact:true}).click();
        assert.equal(await unitNodes.count(), 0);
        await reader.getByRole('button', {name:'Expand all',exact:true}).click();
        assert.equal(await unitNodes.count(), unitCount);
        const zoomBefore = Number(await map.getAttribute('data-zoom'));
        await reader.getByRole('button', {name:'Zoom in',exact:true}).click();
        assert.ok(Number(await map.getAttribute('data-zoom')) > zoomBefore);
        await reader.getByRole('button', {name:'Fit map to panel',exact:true}).click();
        const detail = reader.locator('[data-map-detail]');
        assert.equal(await detail.getAttribute('data-map-detail'), 'none');
        const evidenceNode = map.getByRole('button', {name:/^paragraph 1 of .*: A controlled study observed boundary crossings/});
        await evidenceNode.click();
        assert.equal(await evidenceNode.getAttribute('aria-pressed'), 'true');
        assert.equal(await detail.getAttribute('data-map-detail'), 'unit');
        assert.match(await detail.innerText(), /A controlled study observed boundary crossings through inter-agent content\./);
        await detail.getByRole('button', {name:/^Show source sentences/}).click();
        await detail.getByRole('button', {name:/^Fold back/}).waitFor();
        await detail.getByRole('button', {name:/^Fold back/}).click();
        await page.screenshot({path:`/tmp/openpaper-map-detail-${width}.png`});
        await detail.getByRole('button', {name:'Read in context',exact:true}).click();
        assert.equal(await reader.getAttribute('data-view'), 'read', 'a paragraph on the map opens in the text');
        assert.equal(await reader.locator('[data-fold-unit="2-0"]').evaluate(element => { const r = element.getBoundingClientRect(), box = element.closest('.overflow-y-auto').getBoundingClientRect(); return r.top >= box.top - 1 && r.top < box.bottom; }), true, 'the paragraph is brought into view');
        const levelButton = name => reader.getByRole('radio', {name,exact:true});
        const unit = at => reader.locator(`[data-fold-unit="${at}"]`);
        assert.equal(await page.locator('iframe').count(), 0, 'the reader is part of the page');
        assert.equal(await reader.getAttribute('data-level'), 'takeaway');
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        assert.equal(writes.length, 0);
        await page.screenshot({path:`/tmp/openpaper-research-${width}.png`,fullPage:true});
        await reader.evaluate(element => element.scrollIntoView({block:'start'}));
        await page.screenshot({path:`/tmp/openpaper-fold-${width}.png`});
        await page.evaluate(() => document.documentElement.classList.add('dark'));
        await page.waitForTimeout(300);
        await page.screenshot({path:`/tmp/openpaper-fold-dark-${width}.png`});
        await page.evaluate(() => document.documentElement.classList.remove('dark'));
        const requestsBefore = reads.length;
        const evidence = unit('2-0');
        assert.match(await evidence.innerText(), /^A controlled study observed boundary crossings through inter-agent content\.\s/);
        assert.doesNotMatch(await evidence.innerText(), /production exploit/, 'Takeaway is one sentence');
        await levelButton('Full').click();
        assert.equal(await reader.getAttribute('data-level'), 'full');
        const citation = evidence.getByRole('link', {name:'Primary source',exact:true});
        await citation.waitFor();
        assert.equal(await citation.getAttribute('href'), 'https://example.org/source?q=&copy;');
        assert.equal(await citation.getAttribute('title'), 'Literal &amp;');
        assert.equal(await reader.getByText('[primary]:').count(), 0, 'reference definitions are link targets, not paragraphs');
        await levelButton('Key').click();
        assert.equal(await evidence.getAttribute('data-shown'), 'key');
        await evidence.getByRole('button', {name:/^Show source sentences/}).click();
        assert.equal(await evidence.getAttribute('data-shown'), 'brief', 'one paragraph opens to its source sentences');
        assert.equal(await unit('1-0').getAttribute('data-shown'), 'key', 'other paragraphs stay folded');
        await evidence.getByRole('button', {name:/^Show full text/}).click();
        assert.equal(await evidence.getAttribute('data-shown'), 'full');
        const focused = () => page.evaluate(() => document.activeElement?.textContent || '');
        assert.equal(await focused(), 'Fold back', 'focus moves to the remaining control when Show full text leaves');
        await page.keyboard.press('Enter');
        assert.equal(await evidence.getAttribute('data-shown'), 'key');
        assert.equal(await focused(), 'Show source sentences', 'focus returns to the paragraph control after folding back');
        await page.keyboard.press('2');
        assert.equal(await reader.getAttribute('data-level'), 'takeaway', 'number keys still work after a paragraph control was used');
        await levelButton('Takeaway').focus();
        await page.keyboard.press('5');
        assert.equal(await reader.getAttribute('data-level'), 'full', 'number keys change level inside the reader');
        await levelButton('Full').focus();
        await page.keyboard.press('ArrowLeft');
        assert.equal(await reader.getAttribute('data-level'), 'brief');
        await levelButton('Topic').click();
        assert.equal(await unit('2-0').getAttribute('data-shown'), 'topic');
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        assert.equal(reads.length, requestsBefore, 'folding makes no request');
        assert.equal(await storageKeys(), storedBefore, 'the reader stores nothing in the browser');
        const downloadPromise = page.waitForEvent('download');
        await page.getByRole('button', {name:'Export Textfold',exact:true}).click();
        const download = await downloadPromise;
        const doc = JSON.parse(await fs.readFile(await download.path(), 'utf8'));
        assert.equal(doc.source_text, fixture);
        assert.equal(doc.provenance.ai_generated, false);
        await closePanel();
        await page.getByRole('button', {name:'Assess relevance & novelty',exact:false}).click();
        await page.getByText('Review discussion instructions', {exact:true}).click();
        assert.match(await page.locator('#research-session details').innerText(), /do not assert novelty from missing papers/);
        assert.equal(writes.length, 0);
        await readerReady();
        await page.getByRole('button', {name:'Edit brief',exact:true}).click();
        const dialog = page.getByRole('dialog');
        await page.getByLabel('Project title', {exact:true}).press('3');
        assert.equal(await page.locator("[data-reader-ready]").getAttribute("data-level"), 'takeaway', 'typing a digit in a field elsewhere does not fold the brief');
        await page.getByLabel('Project title', {exact:true}).fill('Draft survives failure');
        failSave = true;
        await dialog.getByRole('button', {name:'Save brief',exact:true}).click();
        await dialog.getByRole('alert').getByText(/draft is still here/).waitFor();
        assert.equal(await page.getByLabel('Project title', {exact:true}).inputValue(), 'Draft survives failure');
        failSave = false;
        const ai = structuredClone(doc);
        ai.provenance = {ai_generated:true,local:false,model:'fixture-model'};
        ai.written = ['topic','takeaway','key'];
        ai.links = [{from:ai.sections[0].id,to:ai.sections[1].id,rel:'supports'},{from:ai.sections[1].units[0].id,to:ai.sections.at(-1).units.at(-1).id,rel:'ref'}];
        assert.match(ai.sections.at(-1).units.at(-1).full, /^\[primary\]:/, 'the second link targets a definition-only paragraph');
        const hostile = 'Raw <img src=x onerror="window.__openpaperInjected=1"> and <script>window.__openpaperInjected=1</script> markup with a [bad](javascript:window.__openpaperInjected=1) link.';
        ai.sections[0].title += ' {{SCRIPTS}} $&';
        Object.assign(ai.sections[0].units[0], {id:'__proto__',findings:[{id:{},label:{a:1}},null,'x',{id:'f',label:'Not shown'}],attribution:{a:1},role:'"><img src=x onerror=window.__openpaperInjected=1>',key:'Short.',takeaway:'The evidence for the evidence is a much longer independent takeaway.',topic:'The evidence for the evidence'});
        ai.sections[0].units.push({id:'exact-quote',kind:'paragraph',full:'A [source](https://a.example). a [source](https://b.example).',sentences:['A [source](https://a.example).','a [source](https://b.example).'],evidence:[1],brief:['a [source](https://b.example).'],key:'The second source is selected.',takeaway:'The second source is selected.',topic:'second source'});
        ai.sections[0].units.push({id:'hostile',kind:'paragraph',full:hostile,sentences:[hostile],evidence:[0],brief:[hostile],key:'Hostile markup stays inert.',takeaway:'Hostile markup stays inert.',topic:'Hostile markup'});
        await page.getByLabel('Import Textfold JSON file', {exact:true}).setInputFiles({name:'fold.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(ai))});
        await dialog.getByText(/AI-written summaries/).waitFor();
        await dialog.getByRole('button', {name:'Save brief',exact:true}).click();
        await page.getByRole('heading', {name:'Draft survives failure',exact:true}).waitFor();
        await page.getByText(/AI-written summaries · fixture-model/).waitFor();
        await readerReady();
        const imported = page.getByRole('region', {name:'Folded research brief',exact:true});
        const importedLevel = name => imported.getByRole('radio', {name,exact:true});
        const importedUnit = at => imported.locator(`[data-fold-unit="${at}"]`);
        await imported.getByRole('heading', {name:/\{\{SCRIPTS\}\} \$&$/}).waitFor();
        await imported.getByRole('link', {name:'supports → Why this matters',exact:true}).waitFor();
        assert.equal(await imported.getByText(/Not shown/).count(), 0, 'extension fields of an imported brief are kept, not rendered');
        // Argument links are drawn across the map as labelled arrows.
        await readerReady('map');
        const importedMap = imported.locator('[data-fold-map]');
        assert.equal(await importedMap.locator('path[data-edge="link"]').count(), 2, 'both argument links are drawn, the one to a definition-only paragraph ending on its section');
        assert.match(await importedMap.innerText(), /supports/);
        assert.equal(await importedMap.getByText(/Not shown/).count(), 0, 'an imported brief gets no finding nodes');
        assert.equal(await importedMap.locator('[data-map-node="finding"]').count(), 0);
        assert.match(await importedMap.innerText(), /Hostile markup stays inert\./);
        await page.screenshot({path:`/tmp/openpaper-map-links-${width}.png`});
        await readerReady();
        await importedLevel('Key').click();
        assert.match(await importedUnit('0-0').innerText(),/^Short\./);
        await importedUnit('0-0').getByRole('button', {name:/^Show source sentences/}).click();
        assert.equal(await importedUnit('0-0').getAttribute('data-shown'),'brief','a paragraph with a hostile id still opens');
        assert.equal(await importedUnit('0-1').getAttribute('data-shown'),'key');
        await importedLevel('Takeaway').click();
        assert.match(await importedUnit('0-0').innerText(),/^The evidence for the evidence is a much longer independent takeaway\./);
        await importedLevel('Brief').click();
        assert.equal(await importedUnit('0-1').locator('a').first().getAttribute('href'),'https://b.example');
        assert.match(await importedUnit('0-1').innerText(),/^a source\./,'Brief quotes the selected source sentence, not the first');
        await importedLevel('Topic').click();
        assert.match(await importedUnit('0-0').innerText(),/^The evidence for the evidence/);
        const inPage = imported.locator('a[href^="#"]');
        assert.equal(await inPage.count(), 2);
        assert.deepEqual(await inPage.evaluateAll(links => links.filter(link => !document.getElementById(link.getAttribute('href').slice(1))).map(link => link.textContent)), [], 'every argument link reaches an element, including one to a definition-only paragraph');
        await importedLevel('Full').click();
        assert.match(await importedUnit('0-2').innerText(), /markup with a bad link\./, 'hostile source Markdown is shown as inert text');
        assert.equal(await imported.locator('a[href^="javascript" i]').count(), 0);
        assert.equal(await page.evaluate(() => window.__openpaperInjected),undefined);
        assert.equal(await imported.locator('img,script,iframe').count(),0);
        // A long, citation-heavy brief: 50 sections, 200 cited paragraphs, 50 definitions.
        const savedBrief = project.research_brief;
        project.research_brief = {...savedBrief,id:'large',links:[],sections:Array.from({length:50},(_,i) => {
            const definition = `[r${i}]: https://example.org/${i}`;
            return {id:`L${i}`,title:`Section ${i}`,depth:1,topic:`Section ${i}`,takeaway:`Result ${i}.0 was observed.`,units:[
                ...Array.from({length:4},(_,j) => { const first = `Result ${i}.${j} was observed in [the paper][r${i}].`; return {id:`L${i}.${j}`,kind:'paragraph',full:`${first} A caveat remains.`,sentences:[first,'A caveat remains.'],evidence:[0],brief:[first],key:first,takeaway:first,topic:`Result ${i}.${j}`}; }),
                {id:`L${i}.r`,kind:'paragraph',full:definition,sentences:[definition],evidence:[0],brief:[definition],key:'',takeaway:'',topic:''}]};
        })};
        const opened = Date.now();
        await page.reload(); await readerReady();
        const openMs = Date.now() - opened;
        const large = page.locator('[data-reader-ready]');
        assert.equal(await large.locator('[data-fold-unit]').count(), 200);
        await readerReady('map');
        assert.equal(await large.locator('[data-map-node="section"]').count(), 50);
        assert.equal(await large.locator('[data-map-node="unit"]').count(), 0, 'a large brief opens with its sections folded');
        const expandMs = await page.evaluate(async () => {
            const start = performance.now();
            [...document.querySelectorAll('[data-fold-map] button')].find(button => button.textContent === 'Expand all').click();
            await new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)));
            return performance.now() - start;
        });
        assert.equal(await large.locator('[data-map-node="unit"]').count(), 200);
        assert.ok(expandMs < 1500, `expanding a 200-paragraph map took ${Math.round(expandMs)} ms`);
        await readerReady();
        const foldMs = await page.evaluate(async () => {
            const start = performance.now();
            document.querySelector('[data-reader-ready] [role=radio][data-level="full"]').click();
            await new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)));
            return performance.now() - start;
        });
        assert.equal(await large.getAttribute('data-level'), 'full');
        assert.equal(await large.locator('[data-fold-unit="49-3"] a').getAttribute('href'), 'https://example.org/49');
        assert.ok(foldMs < 1500, `folding 200 cited paragraphs took ${Math.round(foldMs)} ms`);
        console.log(`${width}px: 200 cited paragraphs: page reload to reader ${openMs} ms, level change ${Math.round(foldMs)} ms, map expand ${Math.round(expandMs)} ms`);
        project.research_brief = savedBrief;
        await page.reload(); await readerReady();
        assert.equal(await storageKeys(), storedBefore, 'reading an imported brief stores nothing in the browser');
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
        await page.getByRole('heading', {name:'Start by adding your evidence'}).waitFor();
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        assert.deepEqual(errors, []);
        console.log(`${width}px: brief panel, map (fold, zoom, select, argument links), native folded reader levels, paragraph opening, keyboard, citations, no requests or storage, export, import/save, draft retention, invalidation and access checks passed`);
        await page.close();
    }
    await browser.close();
})().catch(e => {console.error(e);process.exit(1)});
