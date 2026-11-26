// Local production UI only, API mocked. Checks the flow slice: workspace panels
// load on demand and recover from a failed load, project data is served from
// cache on a second visit, and a failed revalidation does not blank the page.
const { chromium } = require(process.env.OPENPAPER_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.OPENPAPER_BROWSER_BASE || 'http://127.0.0.1:3011';

const ID = 'research-demo';
const project = { id: ID, title: 'Strategic evidence laundering', description: '# The question\nDo reciprocal incentives amplify source-dependent evidence?', research_brief: null, role: 'admin', num_papers: 2, num_conversations: 0 };
const papers = [
    { id: 'p1', title: 'Source dependence study', authors: [], status: 'read', created_at: '2026-11-08' },
    { id: 'p2', title: 'Incentive study', authors: [], status: 'read', created_at: '2026-11-07' },
];
const investigation = { format: 'openpaper/investigation', version: 1, case: { question: '', why_it_matters: '', landscape: '', coverage_limits: '', provisional_answer: '', unresolved_tension: '', reconciliation: '', discriminating_experiment: '', update_criteria: '' }, claims: [], findings: [], relations: [], manuscript: { title: '', sections: [] } };
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
function fixturePdf() {
    const objects = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>', '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>', '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
    const content = 'BT /F1 14 Tf 30 740 Td (Synthetic fixture PDF for the flow check.) Tj ET';
    objects.push('<< /Length ' + content.length + ' >>\nstream\n' + content + '\nendstream');
    let pdf = '%PDF-1.4\n';
    const offsets = [0];
    for (let i = 0; i < objects.length; i++) { offsets.push(Buffer.byteLength(pdf)); pdf += (i + 1) + ' 0 obj\n' + objects[i] + '\nendobj\n'; }
    const offset = Buffer.byteLength(pdf);
    pdf += 'xref\n0 6\n0000000000 65535 f \n' + offsets.slice(1).map(n => String(n).padStart(10, '0') + ' 00000 n \n').join('') + 'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n' + offset + '\n%%EOF';
    return Buffer.from(pdf);
}

(async () => {
    const browser = await chromium.launch({ headless: true, executablePath: process.env.OPENPAPER_CHROMIUM || undefined, args: ['--no-sandbox'] });
    try {
        // The last run asks for reduced motion: same behaviour, no transition.
        for (const [width, reducedMotion] of [[1440, 'no-preference'], [390, 'no-preference'], [1440, 'reduce']]) {
            const context = await browser.newContext({ viewport: { width, height: 1000 }, reducedMotion });
            const page = await context.newPage();
            const errors = [];
            page.on('pageerror', error => errors.push(error.message));
            // Data saver on: the layout must not fetch panel code ahead of need, so loading on demand can be observed.
            await page.addInitScript(() => Object.defineProperty(Navigator.prototype, 'connection', { get: () => ({ saveData: true }) }));
            // Count view transitions and note whether the panel has its transition name while one runs.
            await page.addInitScript(() => {
                const start = Document.prototype.startViewTransition;
                window.flowTransitions = { started: 0, named: 0 };
                if (!start) return;
                Document.prototype.startViewTransition = function (update) {
                    window.flowTransitions.started++;
                    const transition = start.call(this, update);
                    transition.ready.then(() => {
                        if (document.getAnimations().some(animation => animation.effect?.pseudoElement?.includes('workspace-panel'))) window.flowTransitions.named++;
                    }, () => undefined);
                    return transition;
                };
            });

            const seen = [];
            const control = { delay: 0, projectStatus: 200, blockChunks: false, pending: 0 };
            const count = path => seen.filter(item => item === path).length;
            await page.route('**/_next/static/chunks/**', route => (control.blockChunks ? route.abort() : route.continue()));
            await page.route(`${base}/synthetic-fixture.pdf`, route => route.fulfill({ status: 200, contentType: 'application/pdf', body: fixturePdf() }));
            await page.route('**/api/**', async route => {
                const request = route.request(), path = new URL(request.url()).pathname;
                const headers = { 'access-control-allow-origin': base, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'content-type,if-match', 'access-control-allow-methods': 'GET,POST,PUT,PATCH,OPTIONS', 'access-control-expose-headers': 'ETag' };
                if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
                seen.push(path);
                let body = [], status = 200;
                if (path === '/api/auth/me') body = { success: true, user: { id: 'u', name: 'Researcher', email: 'local@example.org', is_active: true, is_blocked: false } };
                else if (path === '/api/subscription/usage') body = { limits: { knowledge_base_size: 100, paper_uploads: 100, chat_credits_weekly: 100, projects: 10 }, usage: { knowledge_base_size: 0, paper_uploads: 0, chat_credits_used: 0, projects: 1 } };
                else if (path === '/api/projects') body = [project];
                else if (path === `/api/projects/${ID}`) {
                    status = control.projectStatus;
                    body = status === 200 ? project : { message: status === 404 ? 'Project not found' : 'Synthetic failure' };
                }
                else if (path === `/api/projects/papers/${ID}`) body = { papers };
                else if (path.endsWith('/file-url')) body = { file_url: `${base}/synthetic-fixture.pdf` };
                else if (path === `/api/projects/${ID}/investigation`) { body = { document: investigation, validation: { findings: {}, blocks: {} } }; headers.ETag = `"investigation:${ID}:1"`; }
                else if (path === `/api/projects/artifacts/${ID}`) body = { artifacts: [] };
                else if (path === `/api/projects/tables/jobs/${ID}` || path === `/api/projects/charts/jobs/${ID}`) body = { jobs: [] };
                else if (path === `/api/projects/invitations/${ID}/`) body = { invitations: [] };
                else if (path === `/api/projects/papers/${ID}/pending-jobs`) body = { jobs: [] };
                if (control.delay && path.startsWith('/api/projects/')) {
                    control.pending++;
                    await pause(control.delay);
                    control.pending--;
                }
                return route.fulfill({ status, headers, contentType: 'application/json', body: JSON.stringify(body) }).catch(() => undefined);
            });
            // SWR revalidates every key when the browser comes back online; requests for a key are deduplicated for two seconds.
            const revalidate = async () => { await pause(2200); await page.evaluate(() => window.dispatchEvent(new Event('online'))); };
            const title = page.getByRole('link', { name: project.title, exact: true });
            const briefButton = page.getByRole('button', { name: 'Toggle research brief panel', exact: true });
            const artifactsButton = page.getByRole('button', { name: 'Toggle artifacts panel', exact: true });
            const failed = page.locator('[data-panel-notice="failed"]');
            // Each transition assertion covers one action: reset, act, then read.
            const resetTransitions = () => page.evaluate(() => { window.flowTransitions = { started: 0, named: 0 }; });
            const expectTransition = async what => {
                await pause(250);
                const seenNow = await page.evaluate(() => window.flowTransitions);
                if (reducedMotion === 'reduce') assert.equal(seenNow.started, 0, `reduced motion: ${what} without a transition`);
                else {
                    assert.ok(seenNow.started >= 1, `${what} ran in a view transition`);
                    assert.ok(seenNow.named >= 1, `${what} animated the panel under its own transition name`);
                }
            };

            // 1. A project opens without the panels' requests.
            const card = page.getByRole('link', { name: new RegExp(project.title) }).first();
            await page.goto(`${base}/projects`);
            await card.waitFor();
            // Slow enough that the click lands while the hover's prefetch is still in flight.
            control.delay = 300;
            // Hovering alone fetches the project; opening it then joins that request.
            await card.hover();
            for (let i = 0; i < 40 && count(`/api/projects/${ID}`) === 0; i++) await pause(5);
            assert.equal(count(`/api/projects/${ID}`), 1, 'hovering a card fetches its project before any click');
            await card.click();
            await page.waitForURL(`${base}/projects/${ID}`);
            await title.waitFor();
            await pause(600);
            control.delay = 0;
            assert.equal(count(`/api/projects/${ID}`), 1, 'hovering a card and opening it is one project request');
            assert.equal(count(`/api/projects/papers/${ID}`), 1, 'and one request for its papers');
            assert.equal(count(`/api/projects/artifacts/${ID}`), 0, 'closed artifacts panel makes no request');
            assert.equal(count(`/api/projects/audio/${ID}`), 0, 'closed artifacts panel does not fetch audio');
            assert.equal(await page.locator('.workspace-panel').count(), 0, 'no panel is mounted before it is asked for');

            // 2. Panel code that fails to load: a notice, the page still works, retry recovers.
            const destinations = page.getByRole('navigation',{name:'Project destinations'});
            await destinations.getByRole('link',{name:'Write',exact:true}).click();
            const pageLauncher = page.getByRole('button',{name:'Open folded preview',exact:true});
            await pageLauncher.waitFor();
            control.blockChunks = true;
            await pageLauncher.press('Enter');
            await failed.waitFor();
            assert.match(await failed.innerText(), /research brief could not be loaded/);
            assert.ok(await title.isVisible(), 'the workspace stays usable when a panel fails to load');
            await failed.getByRole('button', {name:'Dismiss'}).press('Enter');
            await failed.waitFor({state:'detached'});
            assert.ok(await pageLauncher.evaluate(button => document.activeElement === button), 'Failed reader dismissal restores the page launcher');
            await page.goBack();
            await page.waitForURL(`${base}/projects/${ID}`);
            await briefButton.press('Enter');
            await failed.waitFor();
            control.blockChunks = false;
            await resetTransitions();
            await failed.getByRole('button', { name: 'Try again' }).click();
            await page.locator('[data-brief-panel]').waitFor();
            await expectTransition('a panel whose code arrives after the click');
            assert.equal(await failed.count(), 0, 'the notice goes once the panel loads');
            await resetTransitions();
            await page.getByRole('button', { name: 'Back to workspace' }).click();
            await page.locator('[data-brief-panel]').waitFor({ state: 'detached' });
            await expectTransition('closing the brief');
            await resetTransitions();
            await briefButton.click();
            await page.locator('[data-brief-panel]').waitFor();
            await expectTransition('opening a loaded panel');
            await page.getByRole('button', { name: 'Back to workspace' }).click();
            await page.locator('[data-brief-panel]').waitFor({ state: 'detached' });

            // 3. Dismissing a failed load closes the request; asking again is a fresh attempt.
            control.blockChunks = true;
            await artifactsButton.click();
            await failed.waitFor();
            await failed.getByRole('button', { name: 'Dismiss' }).click();
            await failed.waitFor({ state: 'detached' });
            control.blockChunks = false;
            await artifactsButton.click();
            await page.getByRole('heading', { name: 'Artifacts', exact: true }).waitFor();
            await pause(300);
            assert.ok(count(`/api/projects/artifacts/${ID}`) >= 1, 'the artifacts panel fetches when first opened');
            await page.getByRole('button', { name: 'Close artifacts', exact: true }).click();
            await page.getByRole('heading', { name: 'Artifacts', exact: true }).waitFor({ state: 'hidden' });
            // Two toggles in one tick: the preference saved at the click already matches where the panel ends up.
            const savedAtClick = await page.evaluate(() => {
                const button = document.querySelector('[aria-label="Toggle artifacts panel"]');
                button.click();
                button.click();
                return localStorage.getItem('project-artifacts-collapsed');
            });
            assert.equal(savedAtClick, 'true', 'open then close saves "collapsed" before either change is applied');
            await pause(400);
            assert.ok(await page.getByRole('heading', { name: 'Artifacts', exact: true }).isHidden(), 'open then close leaves the panel closed');
            assert.equal(await page.evaluate(() => localStorage.getItem('project-artifacts-collapsed')), 'true');

            // 4. An open reader keeps its PDF pane when the paper list is fetched again.
            if (width >= 768) {
                await page.getByRole('complementary').getByText('Source dependence study', { exact: true }).click();
                const pane = page.locator('.workspace-panel .pdfViewer .page').first();
                await pane.locator('canvas').first().waitFor();
                await pane.evaluate(element => { element.dataset.flowMark = 'kept'; element.querySelector('canvas').dataset.flowMark = 'canvas'; });
                const before = count(`/api/projects/papers/${ID}`);
                await revalidate();
                for (let i = 0; i < 40 && count(`/api/projects/papers/${ID}`) === before; i++) await pause(50);
                assert.ok(count(`/api/projects/papers/${ID}`) > before, 'the paper list was fetched again');
                await pause(400);
                assert.equal(await page.locator('.pdfViewer .page[data-flow-mark="kept"]').count(), 1, 'the rendered PDF page was not remounted by the refetch');
                assert.equal(await page.locator('.pdfViewer canvas[data-flow-mark="canvas"]').count(), 1, 'the rendered canvas is the same element');
                assert.equal(count(`/api/projects/papers/${ID}/p1/file-url`), 1, 'the file URL was not requested again');
                await briefButton.click();
                await page.locator('[data-brief-panel]').waitFor();
                await page.setViewportSize({width:390,height:900});
                await page.getByRole('navigation',{name:'Project destinations'}).getByRole('link',{name:'Evidence',exact:true}).click();
                await page.getByRole('heading',{name:'Evidence',exact:true}).waitFor();
                assert.ok(await pane.isHidden(), 'Navigating to Evidence leaves the previously opened PDF out of the way');
                const evidenceLauncher = page.getByRole('button',{name:'Open folded preview',exact:true});
                await evidenceLauncher.click();
                await page.getByRole('button',{name:'Back to workspace',exact:true}).click();
                await page.locator('[data-brief-panel]').waitFor({state:'detached'});
                assert.ok(await pane.isHidden(), 'Back leaves a previously hidden PDF out of the way');
                assert.ok(await evidenceLauncher.evaluate(button => document.activeElement === button));
                await page.setViewportSize({width,height:900});
                await page.getByRole('complementary').getByText('Source dependence study',{exact:true}).click();
                await pane.waitFor();
                await page.goBack();
                await page.waitForURL(`${base}/projects/${ID}`);
                await resetTransitions();
                await page.getByRole('button', { name: 'Close Source dependence study', exact: true }).click();
                await page.locator(".pdfViewer").first().waitFor({ state: "detached" });
                await expectTransition('closing the last reader tab');
            }

            // 5. A second visit renders from cache while the API is slow.
            await page.goBack();
            await page.waitForURL(`${base}/projects`);
            await card.waitFor();
            control.delay = 1500;
            const started = Date.now();
            await card.click();
            await page.waitForURL(`${base}/projects/${ID}`);
            await title.waitFor();
            const elapsed = Date.now() - started;
            assert.ok(control.pending > 0, 'the project requests are still in flight when the name is shown');
            assert.ok(elapsed < 1200, `cached project shown in ${elapsed} ms, before the 1500 ms response`);
            assert.equal(await page.locator('[data-slot="skeleton"]').count(), 0, 'no project skeleton on a cached visit');
            await pause(1700);
            control.delay = 0;

            // 6. On Evidence, which has no project error handling of its own: a failed
            // revalidation keeps the page; a 404 replaces it; a network failure after
            // the 404 does not bring the cached project back; a success does.
            // First, a project that fails to load for an ordinary reason (not a denial)
            // keeps the workspace: Evidence and the navigation render as they always did.
            control.projectStatus = 500;
            await page.goto(`${base}/projects/${ID}/evidence`);
            await page.getByRole('main').last().getByRole('heading').first().waitFor();
            assert.equal(await page.locator('[data-project-error]').count(), 0, 'a first-load failure does not replace the workspace');
            assert.equal(await artifactsButton.count(), 1, 'the header keeps its controls on a first-load failure');
            assert.ok(await briefButton.isDisabled(), 'The reader needs a loaded project');
            assert.ok(await page.getByRole('button',{name:'Open folded preview',exact:true}).isDisabled());
            control.projectStatus = 200;
            await page.goto(`${base}/projects/${ID}/evidence`);
            await title.waitFor();
            const main = page.getByRole('main').last();
            await main.getByRole('heading').first().waitFor();
            const evidenceText = (await main.innerText()).trim();
            assert.ok(evidenceText.length > 40 && !evidenceText.includes('Project not found'), 'Evidence is on screen');
            // The artifacts panel is open and loaded, and the rail lists the papers, when access goes.
            if (!(await page.getByRole('heading', { name: 'Artifacts', exact: true }).isVisible())) await artifactsButton.click();
            await page.getByRole('heading', { name: 'Artifacts', exact: true }).waitFor();
            if (width >= 768) await page.getByRole('complementary').getByText('Source dependence study', { exact: true }).first().waitFor();
            control.projectStatus = 500;
            let before = count(`/api/projects/${ID}`);
            await revalidate();
            for (let i = 0; i < 40 && count(`/api/projects/${ID}`) === before; i++) await pause(50);
            assert.ok(count(`/api/projects/${ID}`) > before, 'the project was fetched again');
            await pause(400);
            assert.ok(await title.isVisible(), 'a failed revalidation leaves the project on screen');
            assert.equal(await page.getByText('Synthetic failure').count(), 0, 'a failed revalidation shows no error');
            control.projectStatus = 404;
            before = count(`/api/projects/${ID}`);
            await revalidate();
            const denial = page.locator('main [data-project-error]');
            await denial.waitFor({ timeout: 15000 });
            assert.match(await denial.innerText(), /Project not found/);
            assert.equal(await title.count(), 0, 'a project that is gone is not shown from cache');
            assert.equal(await main.getByRole('heading').count(), 0, 'the Evidence view is replaced, not left on screen');
            assert.ok(await denial.isVisible(), 'nothing covers the denial');
            assert.equal(await page.locator('.workspace-panel').count(), 0, 'the open artifacts panel is unmounted with what it had loaded');
            assert.equal(await page.getByRole('heading', { name: 'Artifacts', exact: true }).count(), 0, 'no artifacts panel after a denial');
            assert.equal(await page.getByText('Source dependence study', { exact: true }).count(), 0, 'the rail no longer lists the project papers');
            // Saving needs a role the user no longer has; downloading what is in memory does not.
            const exportsBefore = seen.filter(item => item.includes('/export')).length;
            await page.getByRole('button', { name: 'Export and import', exact: true }).click();
            const [download] = await Promise.all([
                page.waitForEvent('download'),
                page.getByRole('menuitem', { name: /Download (saved|unsaved) bundle/ }).click(),
            ]);
            const bundle = JSON.parse(fs.readFileSync(await download.path(), 'utf8'));
            assert.equal(bundle.format, 'openpaper/investigation-bundle', 'the bundle is written from memory after a denial');
            assert.equal(bundle.document.format, 'openpaper/investigation');
            assert.equal(seen.filter(item => item.includes('/export')).length, exportsBefore, 'the recovery download asks the server for nothing');
            for (const name of ['Open project navigation', 'Toggle research brief panel', 'Toggle artifacts panel']) {
                assert.equal(await page.getByRole('button', { name, exact: true }).count(), 0, `"${name}" is gone for a denied project`);
            }
            assert.equal(await page.locator('a[href="/projects"][data-slot="breadcrumb-link"]').isVisible(), true, 'the way back to the project list stays');
            control.projectStatus = 500;
            before = count(`/api/projects/${ID}`);
            await revalidate();
            for (let i = 0; i < 40 && count(`/api/projects/${ID}`) === before; i++) await pause(50);
            assert.ok(count(`/api/projects/${ID}`) > before, 'the project was fetched again after the denial');
            await pause(400);
            assert.equal(await denial.count(), 1, 'a network failure after a denial does not lift it');
            assert.equal(await title.count(), 0, 'the cached project stays hidden after a denial and a network failure');
            control.projectStatus = 200;
            await revalidate();
            await title.waitFor({ timeout: 15000 });
            assert.equal(await denial.count(), 0, 'a successful read lifts the denial');

            // 7. Signing out in another tab: this tab drops the user and the cached project.
            const other = await context.newPage();
            await other.goto(`${base}/favicon.ico`).catch(() => undefined);
            await other.evaluate(() => { const channel = new BroadcastChannel('openpaper-auth'); channel.postMessage('signed-out'); channel.close(); });
            await page.waitForURL(/\/login/, { timeout: 15000 });
            assert.equal(await title.count(), 0, 'the project is not shown after sign-out in another tab');
            await other.close();

            assert.deepEqual(errors, [], 'no page errors');
            console.log(`${width}px${reducedMotion === 'reduce' ? ' reduced motion' : ''}: on-demand panels, failed load and retry, ${width >= 768 ? 'reader kept across refetch, ' : ''}cached second visit in ${elapsed} ms, revalidation failure, denial on Evidence, denial then network failure, sign-out from another tab passed`);
            await context.close();
        }
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exit(1); });
