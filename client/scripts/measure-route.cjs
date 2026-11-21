// Measures what opening a project costs on the local production build.
// 1. From the build manifest: the files of the project page entry and of the
//    project layout entry. Next's "First Load JS" for a page counts the page
//    entry and not the layouts above it, so the two are shown apart.
// 2. From the served document: every script the route's HTML loads, which is
//    not counting the polyfill a current browser skips. Does not vary by run.
//    This is what the document asks for, not a timing of when it can render.
// 3. In a browser, API mocked and answering after 400 ms: scripts requested and
//    project API requests made once the network has gone quiet. This includes
//    Next prefetching linked routes and code fetched ahead of need, so it is
//    the total, not what startup waits for.
// Usage: node scripts/measure-route.cjs
const { chromium } = require(process.env.OPENPAPER_PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');
const base = process.env.OPENPAPER_BROWSER_BASE || 'http://127.0.0.1:3011';

const ID = 'research-demo';
const project = { id: ID, title: 'Measured project', description: '# The question\nWhat does opening a project cost?', research_brief: null, role: 'admin' };
const investigation = { format: 'openpaper/investigation', version: 1, case: { question: '', why_it_matters: '', landscape: '', coverage_limits: '', provisional_answer: '', unresolved_tension: '', reconciliation: '', discriminating_experiment: '', update_criteria: '' }, claims: [], findings: [], relations: [], manuscript: { title: '', sections: [] } };
const kb = bytes => (bytes / 1024).toFixed(1);

function manifestEntries() {
    const next = process.env.OPENPAPER_NEXT_DIR || path.resolve(__dirname, '../.next');
    const pages = JSON.parse(fs.readFileSync(path.join(next, 'app-build-manifest.json'), 'utf8')).pages;
    const scripts = files => files.filter(file => file.endsWith('.js'));
    const size = files => scripts(files).reduce((total, file) => {
        const body = fs.readFileSync(path.join(next, file));
        return { raw: total.raw + body.length, gzip: total.gzip + zlib.gzipSync(body).length };
    }, { raw: 0, gzip: 0 });
    const route = '/(main)/(protected)/projects/[projectId]';
    const page = pages[`${route}/page`] ?? [], layout = pages[`${route}/layout`] ?? [];
    const only = layout.filter(file => !page.includes(file));
    const a = size(page), b = size(only);
    console.log(`page entry        : ${scripts(page).length} files, ${kb(a.raw)} KB raw, ${kb(a.gzip)} KB gzip`);
    console.log(`layout entry only : ${scripts(only).length} files not in the page entry, ${kb(b.raw)} KB raw, ${kb(b.gzip)} KB gzip`);
}

async function documentScripts() {
    const html = await (await fetch(`${base}/projects/${ID}`)).text();
    // Scripts marked noModule are for browsers without module support; a current browser skips them.
    const tags = [...html.matchAll(/<script\b[^>]*>/g)].map(match => match[0]).filter(tag => !/\bnomodule\b/i.test(tag));
    const urls = [...new Set(tags.map(tag => /\bsrc="([^"]+\.js)"/.exec(tag)?.[1]).filter(Boolean))];
    let raw = 0, gzip = 0;
    for (const url of urls) {
        const body = Buffer.from(await (await fetch(new URL(url, base))).arrayBuffer());
        raw += body.length;
        gzip += zlib.gzipSync(body).length;
    }
    console.log(`route document    : ${urls.length} scripts, ${kb(raw)} KB raw, ${kb(gzip)} KB gzip`);
}

(async () => {
    manifestEntries();
    await documentScripts();
    const browser = await chromium.launch({ headless: true, executablePath: process.env.OPENPAPER_CHROMIUM || undefined, args: ['--no-sandbox'] });
    try {
        const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
        const requested = [], sizes = new Map(), api = [], errors = [];
        const isScript = url => url.includes('/_next/static/') && url.endsWith('.js');
        const projectCalls = () => api.filter(item => item.startsWith('/api/projects/')).length;
        page.on('pageerror', error => errors.push(error.message));
        page.on('request', request => { if (isScript(request.url())) requested.push(request.url()); });
        page.on('response', async response => {
            if (!isScript(response.url())) return;
            const body = await response.body().catch(() => null);
            if (body) sizes.set(response.url(), { raw: body.length, gzip: zlib.gzipSync(body).length });
        });
        await page.route('**/api/**', async route => {
            const request = route.request(), pathname = new URL(request.url()).pathname;
            const headers = { 'access-control-allow-origin': base, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'content-type,if-match', 'access-control-expose-headers': 'ETag' };
            if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
            api.push(pathname);
            let body = [];
            if (pathname === '/api/auth/me') body = { success: true, user: { id: 'u', name: 'Researcher', email: 'local@example.org', is_active: true, is_blocked: false } };
            else if (pathname === '/api/subscription/usage') body = { limits: { knowledge_base_size: 100, paper_uploads: 100, chat_credits_weekly: 100, projects: 10, audio_overviews_weekly: 10, data_tables_weekly: 10 }, usage: { knowledge_base_size: 0, paper_uploads: 0, chat_credits_used: 0, projects: 1, audio_overviews_used: 0, data_tables_used: 0 } };
            else if (pathname === `/api/projects/${ID}`) body = project;
            else if (pathname === `/api/projects/papers/${ID}`) body = { papers: [] };
            else if (pathname === `/api/projects/${ID}/investigation`) { body = { document: investigation, validation: { findings: {}, blocks: {} } }; headers.ETag = `"investigation:${ID}:1"`; }
            else if (pathname.startsWith('/api/projects/audio/')) body = [];
            else if (pathname.endsWith('/jobs') || pathname.includes('/jobs/')) body = { jobs: [] };
            else if (pathname.includes('/artifacts/')) body = { artifacts: [] };
            else if (pathname.includes('/invitations/')) body = { invitations: [] };
            if (pathname.startsWith('/api/projects/')) await new Promise(resolve => setTimeout(resolve, 400));
            return route.fulfill({ status: 200, headers, contentType: 'application/json', body: JSON.stringify(body) }).catch(() => undefined);
        });
        await page.goto(`${base}/projects/${ID}`);
        await page.getByRole('link', { name: project.title, exact: true }).waitFor();
        await page.waitForTimeout(6000);
        await page.waitForLoadState('networkidle');
        const sum = urls => urls.reduce((total, url) => ({ raw: total.raw + (sizes.get(url)?.raw ?? 0), gzip: total.gzip + (sizes.get(url)?.gzip ?? 0) }), { raw: 0, gzip: 0 });
        const late = sum(requested);
        console.log(`network quiet     : ${requested.length} scripts requested, ${kb(late.raw)} KB raw, ${kb(late.gzip)} KB gzip, ${projectCalls()} project API requests`);
        if (errors.length) console.log(`page errors: ${errors.join('; ')}`);
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exit(1); });
