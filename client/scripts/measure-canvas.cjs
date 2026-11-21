// Cost of the project canvas on a local production build with a mocked API:
// showing it (from a click on Canvas to the first painted frame), selecting a
// node, and moving around it.
// Usage: node scripts/measure-canvas.cjs [sizes] [cpu slowdown, default 4]
//   sizes are claims x findings x papers, default 12x40x15,100x500x300,100x500x300xdense.
//   The second is the investigation format's maximum, with 300 papers; "dense" makes
//   every draft section cite every claim and every finding (18,000 citation lines).
// Prints one JSON line per size and action.
const { chromium } = require(process.env.OPENPAPER_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const base = process.env.OPENPAPER_BROWSER_BASE || 'http://127.0.0.1:3011';
const sizes = (process.argv[2] || '12x40x15,100x500x300,100x500x300xdense').split(',').map(size => { const parts = size.split('x'); return [...parts.slice(0, 3).map(Number), parts[3] === 'dense']; });
const slowdown = Number(process.argv[3]) || 4;
const TICKS = 60;
const ID = 'measure';

const uuid = (group, n) => `00000000-0000-4000-8${String(group).padStart(3, '0')}-${String(n).padStart(12, '0')}`;
function investigation(claims, findings, papers, dense) {
    const relations = Math.min(1000, findings * 2), sections = Math.min(30, Math.max(1, Math.round(claims / 3)));
    return {
        format: 'openpaper/investigation', version: 1,
        case: { question: 'What does drawing the whole investigation cost?', why_it_matters: '', landscape: '', coverage_limits: '', provisional_answer: '', unresolved_tension: '', reconciliation: '', discriminating_experiment: '', update_criteria: '' },
        claims: Array.from({ length: claims }, (_, i) => ({ id: uuid(1, i), statement: `Claim ${i}: the measured effect holds under condition ${i} and replicates across the settings tried.`, reasoning: '', caveats: '', archived: false })),
        findings: Array.from({ length: findings }, (_, i) => ({
            id: uuid(2, i), label: `Finding ${i}: result held on replication in setting ${i % 17}`, observed_result: 'Observed.', author_interpretation: '', our_interpretation: '',
            setup: { model: '', task: '', training: '', intervention: '', evaluation: '', other: '' }, limitations: '',
            source: { kind: 'anchored', paper_id: uuid(4, i % papers), start_line: 1, end_line: 2, quote: 'q', source_sha256: 'a'.repeat(64), quote_sha256: 'b'.repeat(64) }, archived: false,
        })),
        relations: Array.from({ length: relations }, (_, i) => ({ id: uuid(3, i), claim_id: uuid(1, (i * 7) % claims), finding_id: uuid(2, i % findings), relation: ['supports', 'challenges', 'qualifies'][Math.floor(i / findings) + (i % 5 === 0 ? 1 : 0)] || 'supports', rationale: '' })),
        manuscript: {
            title: 'Draft',
            sections: Array.from({ length: sections }, (_, i) => ({ id: uuid(5, i), title: `Section ${i}`, blocks: [{ id: uuid(6, i), kind: 'paragraph', text: 'Text.', claim_ids: dense ? Array.from({ length: claims }, (_, n) => uuid(1, n)) : [uuid(1, i % claims)], finding_ids: dense ? Array.from({ length: findings }, (_, n) => uuid(2, n)) : [uuid(2, i % findings), uuid(2, (i + sections) % findings)], provenance: { kind: 'human' }, dependency_pins: {} }] })),
        },
    };
}

const summary = frames => {
    const sorted = [...frames].sort((a, b) => a - b);
    const at = q => sorted.length ? Math.round(sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))] * 10) / 10 : 0;
    return { frames: sorted.length, p50: at(0.5), p95: at(0.95), max: at(1), over33: sorted.filter(ms => ms > 33.4).length };
};

(async () => {
    const browser = await chromium.launch({ headless: true, executablePath: process.env.OPENPAPER_CHROMIUM || undefined, args: ['--no-sandbox'] });
    for (const [claims, findings, papers, dense] of sizes) {
        const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.addInitScript(() => {
            localStorage.setItem('project-artifacts-collapsed', 'true');
            localStorage.setItem('project-rail-collapsed', 'true');
            // React reports every commit to a devtools hook when one exists, in production builds too.
            window.__commits = 0;
            window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
                supportsFiber: true, isDisabled: false, renderers: new Map(), checkDCE() {}, inject() { return 1; },
                onCommitFiberRoot() { window.__commits += 1; }, onPostCommitFiberRoot() {}, onCommitFiberUnmount() {},
            };
        });
        const project = { id: ID, title: 'Measured project', description: 'Measured.', research_brief: null, role: 'admin', created_at: '', updated_at: '' };
        const doc = investigation(claims, findings, papers, dense);
        const paperList = Array.from({ length: papers }, (_, i) => ({ id: uuid(4, i), title: `Paper ${i}: a study of replication in setting ${i}`, authors: [], status: 'read', created_at: '2026-11-08' }));
        await page.route('**/api/**', async route => {
            const req = route.request(), url = new URL(req.url());
            const headers = { 'access-control-allow-origin': base, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'content-type,if-match', 'access-control-allow-methods': 'GET,POST,PUT,PATCH,OPTIONS', 'access-control-expose-headers': 'ETag' };
            if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
            let body = [];
            if (url.pathname === '/api/auth/me') body = { success: true, user: { id: 'u', name: 'Researcher', email: 'test@example.org', is_active: true, is_blocked: false } };
            else if (url.pathname === '/api/subscription/usage') body = { limits: { knowledge_base_size: 100, paper_uploads: 100, chat_credits_weekly: 100 }, usage: { knowledge_base_size: 0, paper_uploads: 0, chat_credits_used: 0 } };
            else if (url.pathname === `/api/projects/${ID}`) body = project;
            else if (url.pathname === `/api/projects/papers/${ID}`) body = { papers: paperList };
            else if (url.pathname === `/api/projects/${ID}/investigation`) { body = { document: doc, validation: { findings: {}, blocks: {} } }; headers.ETag = `"investigation:${ID}:1"`; }
            else if (url.pathname === `/api/projects/invitations/${ID}/`) body = { invitations: [] };
            else if (url.pathname.includes('/jobs')) body = { jobs: [] };
            else if (url.pathname === `/api/projects/artifacts/${ID}`) body = { artifacts: [] };
            return route.fulfill({ status: 200, headers, contentType: 'application/json', body: JSON.stringify(body) });
        });
        // Start on a light route with the investigation loaded, so the click measures the canvas and nothing else.
        await page.goto(`${base}/projects/${ID}/discuss`);
        await page.getByRole('status').filter({ hasText: 'Saved' }).first().waitFor();
        const canvas = page.locator('[data-project-canvas]');
        const expected = 1 + claims + findings + papers + doc.manuscript.sections.length;

        const cdp = await page.context().newCDPSession(page);
        await cdp.send('Performance.enable');
        await cdp.send('Emulation.setCPUThrottlingRate', { rate: slowdown });
        const metrics = async () => Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map(item => [item.name, item.value]));

        const measure = async (action, drive) => {
            await page.evaluate(() => {
                const rec = window.__rec = { frames: [], long: 0, longest: 0, commits: window.__commits, last: performance.now(), on: true };
                const tick = now => { if (!rec.on) return; rec.frames.push(now - rec.last); rec.last = now; requestAnimationFrame(tick); };
                requestAnimationFrame(tick);
                rec.observer = new PerformanceObserver(list => { for (const entry of list.getEntries()) { rec.long += 1; rec.longest = Math.max(rec.longest, entry.duration); } });
                rec.observer.observe({ entryTypes: ['longtask'] });
            });
            const before = await metrics();
            const shownMs = await drive();
            await page.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))));
            const after = await metrics();
            const rec = await page.evaluate(() => { const rec = window.__rec; rec.on = false; rec.observer.disconnect(); return { frames: rec.frames.slice(1), long: rec.long, longest: Math.round(rec.longest), commits: window.__commits - rec.commits }; });
            const ms = name => Math.round((after[name] - before[name]) * 1000);
            console.log(JSON.stringify({
                size: `${claims}x${findings}x${papers}${dense ? ' dense' : ''}`, slowdown, action, edges: await canvas.locator('path[data-edge]').count(), ...(shownMs == null ? {} : { shownMs }), domNodes: await canvas.locator('[data-map-node]').count(),
                ...summary(rec.frames), longTasks: rec.long, longestTaskMs: rec.longest, reactCommits: rec.commits,
                scriptMs: ms('ScriptDuration'), layoutMs: ms('LayoutDuration'), styleMs: ms('RecalcStyleDuration'), taskMs: ms('TaskDuration'),
            }));
        };

        // From the click on Canvas to the first frame painted with every node in the document.
        const show = () => measure('show canvas', () => page.evaluate(count => new Promise(done => {
            const started = performance.now();
            const check = () => {
                if (document.querySelectorAll('[data-project-canvas] [data-map-node]').length !== count) return requestAnimationFrame(check);
                requestAnimationFrame(() => requestAnimationFrame(() => done(Math.round(performance.now() - started))));
            };
            document.querySelector('nav[aria-label="Project destinations"] a').click();
            requestAnimationFrame(check);
        }), expected));
        await show();
        assert.equal(await canvas.locator('[data-map-node]').count(), expected, 'every node is on the canvas');
        // Leave and come back: the route's code is loaded now, so this is the mount alone.
        await page.getByRole('navigation', { name: 'Project destinations' }).getByRole('link', { name: 'Discuss', exact: true }).click();
        await canvas.waitFor({ state: 'detached' });
        await page.waitForTimeout(500);
        await show();

        const viewport = canvas.locator('[data-map-viewport]');
        const box = await viewport.boundingBox();
        const centre = { x: box.x + box.width / 2, y: box.y + box.height / 2 };

        await measure('select a claim', async () => {
            const started = Date.now();
            await canvas.locator('[data-map-node="claim"]').first().click();
            await page.locator('[data-canvas-detail="claim"]').waitFor();
            return Date.now() - started;
        });
        await page.getByRole('button', { name: 'Close detail', exact: true }).click();
        // A section is the node with the most lines to draw once selected.
        await measure('select a section', async () => {
            const started = Date.now();
            await canvas.locator('[data-map-node="section"]').first().click();
            await page.locator('[data-canvas-detail="section"]').waitFor();
            return Date.now() - started;
        });
        await page.getByRole('button', { name: 'Close detail', exact: true }).click();
        await measure('zoom (ctrl+wheel)', async () => {
            await page.mouse.move(centre.x, centre.y);
            await page.keyboard.down('Control');
            for (let i = 0; i < TICKS; i += 1) { await page.mouse.wheel(0, Math.floor(i / 12) % 2 ? -100 : 100); await page.waitForTimeout(16); }
            await page.keyboard.up('Control');
        });
        await canvas.getByRole('button', { name: 'Fit canvas to view', exact: true }).click();
        await measure('pan (wheel)', async () => {
            await page.mouse.move(centre.x, centre.y);
            for (let i = 0; i < TICKS; i += 1) { await page.mouse.wheel(Math.floor(i / 30) % 2 ? -30 : 30, Math.floor(i / 30) % 2 ? -90 : 90); await page.waitForTimeout(16); }
        });
        await canvas.getByRole('button', { name: 'Fit canvas to view', exact: true }).click();
        await measure('pan (drag)', async () => {
            // The canvas's padding is background at its top-left corner.
            await page.mouse.move(box.x + 6, box.y + 6);
            await page.mouse.down();
            for (let i = 1; i <= TICKS; i += 1) { await page.mouse.move(box.x + 6 + i * 2, box.y + 6 + i * 6); await page.waitForTimeout(16); }
            await page.mouse.up();
        });
        assert.deepEqual(errors, [], 'no page errors');
        await page.close();
    }
    await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
