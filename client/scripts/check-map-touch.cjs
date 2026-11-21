// The map under touch, on a phone-sized touch context: one finger pans, two pinch, a tap presses.
// Run against a local production build; all API calls are mocked.
// OPENPAPER_PLAYWRIGHT_MODULE and OPENPAPER_CHROMIUM optionally name local installs.
const { chromium } = require(process.env.OPENPAPER_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const base = process.env.OPENPAPER_BROWSER_BASE || 'http://127.0.0.1:3011';
const unit = (i, j) => { const first = `Result ${i}.${j} held.`; return { id: `S${i}.${j}`, kind: 'paragraph', full: first, sentences: [first], evidence: [0], brief: [first], key: first, takeaway: first, topic: `R ${i}.${j}` }; };
const brief = { format: 'textfold/doc', version: 0, id: 'd', title: 'Touch', lang: 'en', levels: ['topic', 'takeaway', 'key', 'brief', 'full'], written: [], provenance: { ai_generated: false, local: true }, links: [],
    sections: Array.from({ length: 6 }, (_, i) => ({ id: `S${i}`, title: `Section ${i}`, depth: 1, topic: `Section ${i}`, takeaway: 'Result held.', units: Array.from({ length: 4 }, (_, j) => unit(i, j)) })) };
(async () => {
    const browser = await chromium.launch({ headless: true, executablePath: process.env.OPENPAPER_CHROMIUM || undefined, args: ['--no-sandbox'] });
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
    const page = await context.newPage();
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    const project = { id: 'measure', title: 'Touch project', description: 'x', research_brief: brief, role: 'admin', created_at: '', updated_at: '' };
    await page.route('**/api/**', route => {
        const url = new URL(route.request().url());
        const headers = { 'access-control-allow-origin': base, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'content-type', 'access-control-allow-methods': 'GET,POST,PATCH,OPTIONS' };
        if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
        let body = [];
        if (url.pathname === '/api/auth/me') body = { success: true, user: { id: 'u', name: 'R', email: 't@example.org', is_active: true, is_blocked: false } };
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
    const map = page.locator('[data-fold-map]');
    await map.waitFor();
    await page.waitForTimeout(500);
    const cdp = await context.newCDPSession(page);
    const touch = (type, points) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: points.map(([x, y], id) => ({ x, y, id })) });
    const zoom = async () => Number(await map.getAttribute('data-zoom'));
    const section = map.locator('[data-map-node="section"]').first();
    const box = await map.locator('[data-map-viewport]').boundingBox();
    const cx = box.x + box.width / 2, cy = box.y + box.height / 2;

    // One finger pans, starting on a node, and does not press it.
    const start = await section.boundingBox();
    const fx = start.x + 20, fy = start.y + 20;
    const expanded = await section.getAttribute('aria-expanded');
    await touch('touchStart', [[fx, fy]]);
    for (let i = 1; i <= 8; i += 1) { await touch('touchMove', [[fx - i * 5, fy + i * 10]]); await page.waitForTimeout(16); }
    await touch('touchEnd', []);
    await page.waitForTimeout(300);
    const panned = await section.boundingBox();
    assert.ok(Math.abs(panned.x - start.x + 40) < 8 && Math.abs(panned.y - start.y - 80) < 8, `one finger pans: ${JSON.stringify([start, panned])}`);
    assert.equal(await section.getAttribute('aria-expanded'), expanded, 'a pan does not press the node it started on');
    assert.equal(await page.evaluate(() => window.scrollY + document.scrollingElement.scrollTop), 0, 'the page did not scroll');

    // Two fingers pinch about their midpoint.
    const before = await zoom();
    await touch('touchStart', [[cx - 30, cy], [cx + 30, cy]]);
    for (let i = 1; i <= 8; i += 1) { await touch('touchMove', [[cx - 30 - i * 6, cy], [cx + 30 + i * 6, cy]]); await page.waitForTimeout(16); }
    await touch('touchEnd', []);
    await page.waitForTimeout(300);
    const pinched = await zoom();
    assert.ok(pinched > before * 1.5, `pinch out zooms in: ${before} to ${pinched}`);
    assert.equal(await page.evaluate(() => window.visualViewport.scale), 1, 'the page itself is not zoomed');
    await touch('touchStart', [[cx - 80, cy], [cx + 80, cy]]);
    for (let i = 1; i <= 8; i += 1) { await touch('touchMove', [[cx - 80 + i * 6, cy], [cx + 80 - i * 6, cy]]); await page.waitForTimeout(16); }
    await touch('touchEnd', []);
    await page.waitForTimeout(300);
    assert.ok(await zoom() < pinched, 'pinch in zooms out');

    // A tap still activates a node.
    await map.getByRole('button', { name: 'Fit map to panel', exact: true }).tap();
    await page.waitForTimeout(300);
    const target = await section.boundingBox();
    await page.touchscreen.tap(target.x + 20, target.y + 20);
    await page.waitForTimeout(200);
    assert.notEqual(await section.getAttribute('aria-expanded'), expanded, 'a tap presses the node');
    assert.deepEqual(errors, []);
    console.log('touch: one-finger pan, pinch in and out, tap passed');
    await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
