// Cost of moving around the brief map, on a local production build with a mocked API.
// Usage: node scripts/measure-map.cjs [sizes, default 50x4,100x19] [cpu slowdown, default 4]
//   sizes are sections x paragraphs per section. Prints one JSON line per size and gesture.
// OPENPAPER_PLAYWRIGHT_MODULE and OPENPAPER_CHROMIUM optionally name local installs.
const { chromium } = require(process.env.OPENPAPER_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const base = process.env.OPENPAPER_BROWSER_BASE || 'http://127.0.0.1:3011';
const sizes = (process.argv[2] || '50x4,100x19').split(',').map(size => size.split('x').map(Number));
const slowdown = Number(process.argv[3]) || 4;
const TICKS = 60;

const brief = (sections, units) => ({
    format: 'textfold/doc', version: 0, id: `measure-${sections}x${units}`, title: 'Measured brief', lang: 'en',
    levels: ['topic', 'takeaway', 'key', 'brief', 'full'], written: [], provenance: { ai_generated: false, local: true }, links: [],
    sections: Array.from({ length: sections }, (_, i) => ({
        id: `S${i}`, title: `Section ${i}`, depth: 1, topic: `Section ${i}`, takeaway: `Result ${i}.0 was observed.`,
        units: Array.from({ length: units }, (_, j) => {
            const first = `Result ${i}.${j} held on replication.`;
            return { id: `S${i}.${j}`, kind: 'paragraph', full: `${first} A caveat remains.`, sentences: [first, 'A caveat remains.'], evidence: [0], brief: [first], key: first, takeaway: first, topic: `Result ${i}.${j}` };
        }),
    })),
});

const summary = frames => {
    const sorted = [...frames].sort((a, b) => a - b);
    const at = q => sorted.length ? Math.round(sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))] * 10) / 10 : 0;
    return { frames: sorted.length, p50: at(0.5), p95: at(0.95), max: at(1), over33: sorted.filter(ms => ms > 33.4).length };
};

(async () => {
    const browser = await chromium.launch({ headless: true, executablePath: process.env.OPENPAPER_CHROMIUM || undefined, args: ['--no-sandbox'] });
    for (const [sections, units] of sizes) {
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
        const project = { id: 'measure', title: 'Measured project', description: 'Measured.', research_brief: brief(sections, units), role: 'admin', created_at: '', updated_at: '' };
        await page.route('**/api/**', async route => {
            const req = route.request(), url = new URL(req.url());
            const headers = { 'access-control-allow-origin': base, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'content-type', 'access-control-allow-methods': 'GET,POST,PATCH,OPTIONS' };
            if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
            let body = [];
            if (url.pathname === '/api/auth/me') body = { success: true, user: { id: 'u', name: 'Researcher', email: 'test@example.org', is_active: true, is_blocked: false } };
            else if (url.pathname === '/api/subscription/usage') body = { limits: { knowledge_base_size: 100, paper_uploads: 100, chat_credits_weekly: 100 }, usage: { knowledge_base_size: 0, paper_uploads: 0, chat_credits_used: 0 } };
            else if (url.pathname === '/api/projects/measure') body = project;
            else if (url.pathname === '/api/projects/papers/measure') body = { papers: [] };
            else if (url.pathname === '/api/projects/invitations/measure/') body = { invitations: [] };
            else if (url.pathname === '/api/projects/tables/jobs/measure') body = { jobs: [] };
            else if (url.pathname === '/api/projects/artifacts/measure') body = { artifacts: [] };
            return route.fulfill({ status: 200, headers, contentType: 'application/json', body: JSON.stringify(body) });
        });
        await page.goto(`${base}/projects/measure/discuss`);
        await page.getByRole('button', { name: 'Toggle research brief panel', exact: true }).click();
        await page.locator('[data-reader-ready="true"]').waitFor();
        if (await page.locator('[data-reader-ready]').getAttribute('data-view') !== 'map') await page.locator('[data-view-option="map"]').click();
        const map = page.locator('[data-fold-map]');
        await map.waitFor();

        const cdp = await page.context().newCDPSession(page);
        await cdp.send('Performance.enable');
        await cdp.send('Emulation.setCPUThrottlingRate', { rate: slowdown });
        const metrics = async () => Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map(item => [item.name, item.value]));

        const measure = async (gesture, drive) => {
            await page.evaluate(() => {
                const rec = window.__rec = { frames: [], long: 0, commits: window.__commits, last: performance.now(), on: true };
                const tick = now => { if (!rec.on) return; rec.frames.push(now - rec.last); rec.last = now; requestAnimationFrame(tick); };
                requestAnimationFrame(tick);
                rec.observer = new PerformanceObserver(list => { rec.long += list.getEntries().length; });
                rec.observer.observe({ entryTypes: ['longtask'] });
            });
            const before = await metrics();
            await drive();
            await page.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))));
            const after = await metrics();
            const rec = await page.evaluate(() => { const rec = window.__rec; rec.on = false; rec.observer.disconnect(); return { frames: rec.frames.slice(1), long: rec.long, commits: window.__commits - rec.commits }; });
            const ms = name => Math.round((after[name] - before[name]) * 1000);
            console.log(JSON.stringify({
                size: `${sections}x${units}`, slowdown, gesture, domNodes: await map.locator('[data-map-node]').count(),
                ...summary(rec.frames), longTasks: rec.long, reactCommits: rec.commits,
                scriptMs: ms('ScriptDuration'), layoutMs: ms('LayoutDuration'), styleMs: ms('RecalcStyleDuration'), taskMs: ms('TaskDuration'),
            }));
        };

        // Open every section, the heaviest state the map has.
        await measure('expand all', async () => {
            const expand = map.getByRole('button', { name: 'Expand all', exact: true });
            if (await expand.count()) await expand.click();
            await page.waitForFunction(count => document.querySelectorAll('[data-map-node="unit"]').length === count, sections * units, { timeout: 120000 }).catch(async error => {
                console.error('Map state:', await map.locator('[data-map-node="section"]').count(), 'sections,', await map.locator('[data-map-node="unit"]').count(), 'paragraphs;', (await page.locator('[data-brief-panel]').innerText()).slice(0, 300), errors);
                throw error;
            });
        });
        assert.equal(await map.locator('[data-map-node="unit"]').count(), sections * units, 'every paragraph is on the map');

        const viewport = map.locator(':scope > div').nth(1);
        const box = await viewport.boundingBox();
        const centre = { x: box.x + box.width / 2, y: box.y + box.height / 2 };

        await measure('zoom (ctrl+wheel)', async () => {
            await page.mouse.move(centre.x, centre.y);
            await page.keyboard.down('Control');
            for (let i = 0; i < TICKS; i += 1) { await page.mouse.wheel(0, Math.floor(i / 12) % 2 ? -100 : 100); await page.waitForTimeout(16); }
            await page.keyboard.up('Control');
        });
        await map.getByRole('button', { name: 'Fit map to panel', exact: true }).click();
        await measure('pan (wheel)', async () => {
            await page.mouse.move(centre.x, centre.y);
            for (let i = 0; i < TICKS; i += 1) { await page.mouse.wheel(Math.floor(i / 30) % 2 ? -30 : 30, Math.floor(i / 30) % 2 ? -90 : 90); await page.waitForTimeout(16); }
        });
        await map.getByRole('button', { name: 'Fit map to panel', exact: true }).click();
        await measure('pan (drag)', async () => {
            // The map's padding is background at its top-left corner.
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
