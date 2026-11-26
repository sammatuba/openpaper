// Local production UI only, API mocked. Checks the project canvas: the home page
// draws the investigation, a selected node shows its text and leads to the view
// or panel that reads it, the camera and selection survive leaving and coming
// back, and the states with nothing to draw are handled.
const { chromium } = require(process.env.OPENPAPER_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.OPENPAPER_BROWSER_BASE || 'http://127.0.0.1:3011';

const ID = 'research-demo';
const uuid = n => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const C1 = uuid(1), C2 = uuid(2), C3 = uuid(3), F1 = uuid(11), F2 = uuid(12), F3 = uuid(13), F4 = uuid(14), F5 = uuid(15), S1 = uuid(21), B1 = uuid(31), T = Array.from({ length: 5 }, (_, i) => uuid(300 + i)), P1 = uuid(41), P2 = uuid(42);
const project = { id: ID, title: 'Strategic evidence laundering', description: '# The question\nDo reciprocal incentives amplify source-dependent evidence?', research_brief: null, role: 'admin', num_papers: 2, num_conversations: 0 };
const papers = [
    { id: P1, title: 'Source dependence study', authors: ['A. Author', 'B. Writer'], status: 'read', created_at: '2026-11-08' },
    { id: P2, title: 'Incentive study', authors: [], status: 'read', created_at: '2026-11-07' },
];
// Enough further claims and findings that the ones the links below name are off screen in Overview and Evidence.
const MORE = 8, K = Array.from({ length: MORE }, (_, i) => uuid(100 + i)), G = Array.from({ length: MORE }, (_, i) => uuid(200 + i));
const emptyCase = { question: '', why_it_matters: '', landscape: '', coverage_limits: '', provisional_answer: '', unresolved_tension: '', reconciliation: '', discriminating_experiment: '', update_criteria: '' };
const anchored = paper => ({ kind: 'anchored', paper_id: paper, start_line: 1, end_line: 2, quote: 'Synthetic fixture', source_sha256: 'a'.repeat(64), quote_sha256: 'b'.repeat(64) });
const finding = (id, label, source, archived = false) => ({ id, label, observed_result: `${label} was observed.`, author_interpretation: '', our_interpretation: '', setup: { model: '', task: '', training: '', intervention: '', evaluation: '', other: '' }, limitations: '', source, archived });
const full = {
    format: 'openpaper/investigation', version: 1,
    case: { ...emptyCase, question: 'Do reciprocal incentives amplify source-dependent evidence?', provisional_answer: 'Probably, in repeated settings.' },
    claims: [
        { id: C1, statement: 'Reciprocity amplifies dependent evidence', reasoning: '', caveats: '', archived: false },
        ...K.map((id, i) => ({ id, statement: `A further claim, number ${i + 1}`, reasoning: '', caveats: '', archived: false })),
        { id: C2, statement: 'The effect vanishes with disclosure', reasoning: '', caveats: '', archived: false },
        { id: C3, statement: 'An archived claim', reasoning: '', caveats: '', archived: true },
    ],
    findings: [
        finding(F1, 'Amplification in repeated games', anchored(P1)),
        ...G.map((id, i) => finding(id, `A further observation, number ${i + 1}`, { kind: 'unbound' })),
        finding(F2, 'Disclosure removes the effect', anchored(P2)),
        finding(F3, 'An unbound observation', { kind: 'unbound' }),
        finding(F4, 'An archived finding', anchored(P1), true),
        finding(F5, 'A redacted source', { kind: 'redacted', paper_id: P1 }),
    ],
    relations: [
        { id: uuid(51), claim_id: C1, finding_id: F1, relation: 'supports', rationale: '' },
        { id: uuid(52), claim_id: C1, finding_id: F2, relation: 'challenges', rationale: '' },
        { id: uuid(53), claim_id: C2, finding_id: F2, relation: 'supports', rationale: '' },
        { id: uuid(54), claim_id: C3, finding_id: F1, relation: 'supports', rationale: '' },
    ],
    // Five sections of three paragraphs come first, so the section the canvas links to is below the fold in Write.
    manuscript: { title: 'Draft', sections: [...T.map((id, i) => ({ id, title: `Earlier section ${i + 1}`, blocks: [0, 1, 2].map(n => ({ id: uuid(400 + i * 3 + n), kind: 'paragraph', text: `Paragraph ${n + 1} of an earlier section. `.repeat(6), claim_ids: [], finding_ids: [], provenance: { kind: 'human' }, dependency_pins: {} })) })), { id: S1, title: 'Introduction', blocks: [{ id: B1, kind: 'paragraph', text: 'Reciprocity matters.', claim_ids: [C1], finding_ids: [F1], provenance: { kind: 'human' }, dependency_pins: {} }] }] },
};
const empty = { format: 'openpaper/investigation', version: 1, case: emptyCase, claims: [], findings: [], relations: [], manuscript: { title: '', sections: [] } };
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
function fixturePdf() {
    const objects = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>', '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>', '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
    const content = 'BT /F1 14 Tf 30 740 Td (Synthetic fixture PDF for the canvas check.) Tj ET';
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
    const shots = path.resolve(__dirname, '../../.meos/artifacts/project-canvas');
    fs.mkdirSync(shots, { recursive: true });
    try {
        for (const width of [1440, 390]) {
            const context = await browser.newContext({ viewport: { width, height: 900 } });
            const page = await context.newPage();
            const errors = [];
            page.on('pageerror', error => errors.push(error.message));
            await page.addInitScript(() => localStorage.setItem('project-artifacts-collapsed', 'true'));

            const control = { delay: 0, pending: 0, investigation: full, investigationStatus: 200, investigationScript: [], projectLog: [], puts: [], putDelay: 0, putStatus: 200, papers, papersStatus: 200, projectStatus: 200, user: 'u' };
            await page.route(`${base}/synthetic-fixture.pdf`, route => route.fulfill({ status: 200, contentType: 'application/pdf', body: fixturePdf() }));
            await page.route('**/api/**', async route => {
                const request = route.request(), url = new URL(request.url()).pathname;
                const headers = { 'access-control-allow-origin': base, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'content-type,if-match', 'access-control-allow-methods': 'GET,POST,PUT,PATCH,OPTIONS', 'access-control-expose-headers': 'ETag' };
                if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
                let body = [], status = 200;
                if (url === '/api/auth/me') body = { success: true, user: { id: control.user, name: 'Researcher', email: 'local@example.org', is_active: true, is_blocked: false } };
                else if (url === '/api/subscription/usage') body = { limits: { knowledge_base_size: 100, paper_uploads: 100, chat_credits_weekly: 100, projects: 10 }, usage: { knowledge_base_size: 0, paper_uploads: 0, chat_credits_used: 0, projects: 1 } };
                else if (url === '/api/projects') body = [project];
                else if (url === `/api/projects/${ID}`) { status = control.projectStatus; control.projectLog.push(status); body = status === 200 ? project : { message: 'Synthetic failure' }; }
                else if (url === `/api/projects/papers/${ID}`) { status = control.papersStatus; body = status === 200 ? { papers: control.papers } : { message: 'Synthetic failure' }; }
                else if (url.endsWith('/file-url')) body = { file_url: `${base}/synthetic-fixture.pdf` };
                else if (url === `/api/projects/${ID}/investigation` && request.method() === 'PUT') {
                    const sent = JSON.parse(request.postData());
                    control.puts.push(sent.document.case.question);
                    if (control.putDelay) await pause(control.putDelay);
                    status = control.putStatus;
                    if (status === 200) control.investigation = sent.document;
                    body = status === 200 ? { document: sent.document, validation: { findings: {}, blocks: {} } } : { detail: 'Synthetic failure' };
                    headers.ETag = `"investigation:${ID}:${control.puts.length + 1}"`;
                }
                else if (url === `/api/projects/${ID}/investigation`) {
                    // A scripted answer (status and delay) takes the place of the usual one, one request at a time.
                    const scripted = control.investigationScript.shift();
                    status = scripted ? scripted.status : control.investigationStatus;
                    if (scripted?.delay) await pause(scripted.delay);
                    body = status === 200 ? { document: control.investigation, validation: { findings: {}, blocks: {} } } : { detail: 'Synthetic failure' };
                    headers.ETag = `"investigation:${ID}:1"`;
                }
                else if (url === `/api/projects/artifacts/${ID}`) body = { artifacts: [] };
                else if (url === `/api/projects/tables/jobs/${ID}` || url === `/api/projects/charts/jobs/${ID}` || url === `/api/projects/papers/${ID}/pending-jobs`) body = { jobs: [] };
                else if (url === `/api/projects/invitations/${ID}/`) body = { invitations: [] };
                if (control.delay && url.startsWith('/api/projects/')) { control.pending++; await pause(control.delay); control.pending--; }
                return route.fulfill({ status, headers, contentType: 'application/json', body: JSON.stringify(body) }).catch(() => undefined);
            });

            const home = `${base}/projects/${ID}`;
            const canvas = page.locator('[data-project-canvas]');
            const node = (kind, ref) => canvas.locator(`[data-map-key="${kind}:${ref}"]`);
            const detail = page.locator('[data-canvas-detail]');
            const nav = page.getByRole('navigation', { name: 'Project destinations' });
            const noOverflow = async label => assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${label}: no horizontal page overflow at ${width}`);
            // A node is inside the canvas viewport, whole.
            const inView = async locator => {
                const box = await locator.boundingBox(), frame = await canvas.locator('[data-map-viewport]').boundingBox();
                return !!box && box.x >= frame.x - 1 && box.y >= frame.y - 1 && box.x + box.width <= frame.x + frame.width + 1 && box.y + box.height <= frame.y + frame.height + 1;
            };
            // Focus brings a node into view the way Tab does; then it can be pressed.
            const press = async locator => { await locator.focus(); await pause(250); await locator.click(); };
            const focused = async locator => {
                for (let i = 0; i < 20; i++) { if (await locator.evaluate(element => element === document.activeElement)) return true; await pause(50); }
                return false;
            };

            // An element is inside the window, so a link that names it has really landed on it.
            const onScreen = async locator => {
                for (let i = 0; i < 20; i++) {
                    const box = await locator.boundingBox();
                    if (box && box.y >= 0 && box.y < page.viewportSize().height - 40) return true;
                    await pause(50);
                }
                return false;
            };
            const active = () => page.evaluate(() => (document.activeElement?.getAttribute('aria-label') || document.activeElement?.textContent || '').trim());
            const ALL = { question: 1, claim: 2 + MORE, finding: 4 + MORE, paper: 2, section: 1 + T.length };

            // 1. The home page is the canvas, drawn from the investigation and the papers.
            await page.goto(home);
            await canvas.waitFor();
            assert.equal(await nav.getByRole('link', { name: 'Canvas', exact: true }).getAttribute('aria-current'), 'page');
            assert.equal(await nav.getByRole('link', { name: 'Overview', exact: true }).getAttribute('href'), `/projects/${ID}/overview`);
            assert.equal(await page.getByRole('heading', { level: 1 }).textContent(), `Canvas: ${full.case.question}`);
            const kinds = async () => Object.fromEntries(await Promise.all(['question', 'claim', 'finding', 'paper', 'section'].map(async kind => [kind, await canvas.locator(`[data-map-node="${kind}"]`).count()])));
            assert.deepEqual(await kinds(), ALL, 'archived claims and findings are not drawn');
            const edges = async () => Object.fromEntries(await Promise.all(['asks', 'supports', 'challenges', 'qualifies', 'source', 'drafts'].map(async kind => [kind, await canvas.locator(`path[data-edge="${kind}"]`).count()])));
            assert.deepEqual(await edges(), { asks: 2 + MORE, supports: 2, challenges: 1, qualifies: 0, source: 2, drafts: 0 }, 'a redacted source is not drawn as one; draft lines wait for a selection');
            assert.equal(await node('claim', C1).getAttribute('aria-label'), 'Claim 1: Reciprocity amplifies dependent evidence (1 supports, 1 challenges)');
            assert.equal(await detail.count(), 0, 'nothing is selected to begin with');
            await noOverflow('Canvas');
            await page.screenshot({ path: path.join(shots, `canvas-${width}.png`) });

            // 2. Selecting a claim shows what it says and where its evidence is; its edges stand out.
            await press(node('claim', C1));
            await page.locator('[data-canvas-detail="claim"]').waitFor();
            assert.equal(await node('claim', C1).getAttribute('aria-pressed'), 'true');
            assert.ok((await detail.textContent()).includes('Reciprocity amplifies dependent evidence'));
            assert.equal(await detail.getByRole('link', { name: 'View its evidence', exact: true }).getAttribute('href'), `/projects/${ID}/evidence?claim=${C1}`);
            assert.equal(await detail.getByRole('link', { name: 'Open in Overview' }).getAttribute('href'), `/projects/${ID}/overview?claim=${C1}`);
            assert.equal(await canvas.locator('path[data-active]').count(), 4, 'the question, two findings and the section touch the selected claim');
            assert.equal((await edges()).drafts, 1, 'the section that cites the claim is joined to it while it is selected');
            assert.ok(await inView(node('claim', C1)), 'the selected claim stays in view when its detail opens');
            assert.ok(await focused(node('claim', C1)), 'a pointer press leaves focus on the node');
            await noOverflow('Canvas with a detail');
            await page.screenshot({ path: path.join(shots, `canvas-claim-${width}.png`) });

            // 3. A finding named in the detail becomes the selection and is brought into view; focus stays in the detail.
            await detail.getByRole('button', { name: 'Amplification in repeated games', exact: true }).click();
            await page.locator('[data-canvas-detail="finding"]').waitFor();
            assert.ok(await focused(detail), 'focus is on the detail, not lost with the button that was pressed');
            await pause(300);
            assert.ok(await inView(node('finding', F1)), 'the finding is in view');
            assert.equal(await node('finding', F1).getAttribute('aria-pressed'), 'true');
            assert.ok((await detail.textContent()).includes('Source: Source dependence study'));

            // 4. Its source opens in the docked reader; closing the reader returns to where it was opened.
            const openSource = detail.getByRole('button', { name: 'Open source', exact: true });
            await openSource.click();
            await page.locator('.page[data-page-number="1"] canvas').first().waitFor();
            await page.getByRole('button', { name: 'Close reader', exact: true }).click();
            assert.ok(await focused(openSource), 'closing the reader returns focus to the button that opened it');
            assert.equal(await node('finding', F1).getAttribute('aria-pressed'), 'true', 'the selection is kept across the reader');

            // A finding with no passage to open (unbound, or redacted with its paper still listed) says so and offers no reader.
            for (const id of [F3, F5]) {
                await press(node('finding', id));
                await page.locator('[data-canvas-detail="finding"]').getByText('Source not available in this project.').waitFor();
                assert.equal(await detail.getByRole('button', { name: 'Open source', exact: true }).count(), 0);
            }

            // 5. A paper opens in the reader from its detail, and lists only findings with a passage in it.
            await press(node('paper', P1));
            await page.locator('[data-canvas-detail="paper"]').waitFor();
            assert.ok((await detail.textContent()).includes('Amplification in repeated games'), 'the paper lists the findings drawn from it');
            assert.ok(!(await detail.textContent()).includes('A redacted source'), 'a redacted finding is not listed under its paper');
            await press(node('paper', P2));
            await detail.getByText('Disclosure removes the effect').waitFor();
            const openPaper = detail.getByRole('button', { name: 'Open in reader', exact: true });
            await openPaper.click();
            await page.locator('.page[data-page-number="1"] canvas').first().waitFor();
            await page.getByRole('button', { name: 'Close reader', exact: true }).click();
            assert.ok(await focused(openPaper));
            await detail.getByRole('button', { name: 'Close detail', exact: true }).click();
            await detail.waitFor({ state: 'detached' });

            // 6. Keyboard only: walk to a node, open it, use an action in its detail, come back, close.
            await node('question', 'question').focus();
            await page.keyboard.press('ArrowRight');
            assert.ok(await focused(node('claim', C1)), 'ArrowRight from the question reaches the first claim');
            await page.keyboard.press('ArrowDown');
            assert.ok(await focused(node('claim', K[0])), 'ArrowDown moves along the column');
            await page.keyboard.press('ArrowUp');
            assert.ok(await focused(node('claim', C1)));
            await page.keyboard.press('Enter');
            await page.locator('[data-canvas-detail="claim"]').waitFor();
            assert.ok(await focused(detail), 'opening a node from the keyboard moves focus into its detail');
            await page.keyboard.press('Tab');
            assert.equal(await active(), 'Amplification in repeated games', 'the first Tab reaches the detail, not the next node');
            await page.keyboard.press('Enter');
            await page.locator('[data-canvas-detail="finding"]').waitFor();
            assert.ok(await focused(detail));
            await page.keyboard.press('Escape');
            assert.ok(await focused(node('finding', F1)), 'Escape returns to the selected node');
            assert.equal(await detail.count(), 1, 'Escape leaves the detail open');
            await page.keyboard.press('Enter');
            await detail.waitFor({ state: 'detached' });
            await page.keyboard.press('Enter');
            await page.locator('[data-canvas-detail="finding"]').waitFor();
            for (let i = 0; i < 12 && await active() !== 'Close detail'; i++) await page.keyboard.press('Tab');
            assert.equal(await active(), 'Close detail', 'Close is reached by Tab from the detail');
            await page.keyboard.press('Enter');
            await detail.waitFor({ state: 'detached' });
            assert.ok(await focused(node('finding', F1)), 'closing the detail returns focus to its node');

            // 7. Leaving for Write and coming back restores the camera and the selection.
            await canvas.getByRole('button', { name: 'Zoom in', exact: true }).click();
            await pause(300);
            await canvas.getByRole('button', { name: 'Zoom in', exact: true }).click();
            await pause(300);
            const zoom = await canvas.getAttribute('data-zoom');
            await press(node('section', S1));
            await page.locator('[data-canvas-detail="section"]').waitFor();
            assert.ok((await detail.textContent()).includes('1 paragraph, citing 1 finding.'));
            assert.equal((await edges()).drafts, 2, 'a selected section is joined to what it cites');
            const before = await node('section', S1).boundingBox();
            await detail.getByRole('link', { name: 'Open in Write' }).click();
            await page.waitForURL(`${home}/draft#section-${S1}`);
            assert.ok(await onScreen(page.locator(`#section-${S1}`)), 'Write shows the section');
            await nav.getByRole('link', { name: 'Canvas', exact: true }).click();
            await page.waitForURL(home);
            await canvas.waitFor();
            await pause(400);
            assert.equal(await canvas.getAttribute('data-zoom'), zoom, 'the zoom is restored');
            assert.equal(await node('section', S1).getAttribute('aria-pressed'), 'true', 'the selection is restored');
            const after = await node('section', S1).boundingBox();
            assert.ok(Math.abs(after.x - before.x) < 2 && Math.abs(after.y - before.y) < 2, 'the camera is where it was left');

            // The same with the selection panned out of sight: coming back must not pull the camera to it.
            const frame = await canvas.locator('[data-map-viewport]').boundingBox();
            await page.mouse.move(frame.x + frame.width / 2, frame.y + frame.height / 2);
            await page.mouse.wheel(3000, 0);
            await pause(300);
            assert.equal(await inView(node('section', S1)), false, 'the selected section is panned out of view');
            const away = await node('section', S1).boundingBox();
            await nav.getByRole('link', { name: 'Evidence', exact: true }).click();
            await page.waitForURL(`${home}/evidence`);
            await nav.getByRole('link', { name: 'Canvas', exact: true }).click();
            await page.waitForURL(home);
            await canvas.waitFor();
            await pause(600);
            const back = await node('section', S1).boundingBox();
            assert.ok(Math.abs(back.x - away.x) < 2 && Math.abs(back.y - away.y) < 2, `a pan away from the selection is kept (${Math.round(away.x)} then ${Math.round(back.x)})`);
            assert.equal(await node('section', S1).getAttribute('aria-pressed'), 'true');
            await canvas.getByRole('button', { name: 'Fit canvas to view', exact: true }).click();
            await pause(300);

            // 8. A finding opens in Evidence, on that finding (the tenth, below the fold without the link).
            await press(node('finding', F2));
            await detail.getByRole('link', { name: 'Open in Evidence' }).click();
            await page.waitForURL(`${home}/evidence?finding=${F2}`);
            assert.ok(await onScreen(page.locator(`#finding-${F2}`)), 'Evidence shows the finding');

            // 9. A link saved to a claim on the old home address lands on it in Overview (the tenth claim).
            await page.goto(`${home}?claim=${C2}`);
            await page.waitForURL(`${home}/overview?claim=${C2}`);
            assert.ok(await onScreen(page.locator(`#claim-${C2}`)), 'Overview shows the claim');
            assert.equal(await nav.getByRole('link', { name: 'Overview', exact: true }).getAttribute('aria-current'), 'page');
            await noOverflow('Overview');

            // 10. A return visit draws the canvas from what was kept, before the server answers, then takes the answer.
            // A full page load empties the memory, so the project is opened once from the list first.
            await page.goto(`${base}/projects`);
            const card = page.getByRole('link', { name: new RegExp(project.title) }).first();
            await card.click();
            await node('claim', C1).waitFor();
            await page.goBack();
            await page.waitForURL(`${base}/projects`);
            await card.waitFor();
            const revised = { ...full, claims: full.claims.map(claim => (claim.id === C1 ? { ...claim, statement: 'Reciprocity amplifies dependent evidence, revised' } : claim)) };
            control.investigation = revised;
            control.delay = 1500;
            const started = Date.now();
            await card.click();
            await node('claim', C1).waitFor();
            const elapsed = Date.now() - started;
            assert.ok(control.pending > 0, 'the project requests are still in flight when the canvas is drawn');
            assert.ok(elapsed < 1200, `canvas drawn from memory in ${elapsed} ms, before the 1500 ms response`);
            assert.equal(await page.locator('[data-slot="skeleton"]').count(), 0, 'no skeleton on a return visit');
            assert.ok(!(await node('claim', C1).getAttribute('aria-label')).includes('revised'), 'what is drawn first is the kept copy');
            await pause(1700);
            control.delay = 0;
            assert.ok((await node('claim', C1).getAttribute('aria-label')).includes('revised'), 'the kept copy is replaced by the server\'s answer');
            assert.deepEqual(await kinds(), ALL);

            // A return visit whose investigation cannot be loaded keeps the last saved copy on screen and says so.
            await page.goBack();
            await page.waitForURL(`${base}/projects`);
            await card.waitFor();
            control.investigationStatus = 500;
            await card.click();
            await canvas.locator('[data-canvas-stale]').waitFor();
            assert.ok((await canvas.locator('[data-canvas-stale]').textContent()).includes('Last saved copy'));
            assert.ok((await node('claim', C1).getAttribute('aria-label')).includes('revised'));
            control.investigationStatus = 200;
            control.investigation = full;

            // "Open in Write" from the kept copy, before the investigation has loaded: Write has no sections
            // yet when the link is followed, and still lands on the section once they exist.
            await page.goBack();
            await page.waitForURL(`${base}/projects`);
            await card.waitFor();
            control.investigationScript = [{ status: 200, delay: 3000 }];
            await card.click();
            await press(node('section', S1));
            await detail.getByRole('link', { name: 'Open in Write' }).click();
            await page.waitForURL(`${home}/draft#section-${S1}`);
            await page.getByRole('status').filter({ hasText: 'Loading' }).first().waitFor();
            assert.equal(await page.locator(`#section-${S1}`).count(), 0, 'Write is on screen without the section: the investigation has not been answered');
            assert.equal(control.investigationScript.length, 0);
            await page.locator(`#section-${S1}`).waitFor();
            assert.ok(await onScreen(page.locator(`#section-${S1}`)), 'Write shows the section opened from a kept copy, once it exists');
            await nav.getByRole('link', { name: 'Canvas', exact: true }).click();
            await canvas.waitFor();
            await detail.getByRole('button', { name: 'Close detail', exact: true }).click();

            // A refusal that arrives late, from a request an earlier visit started, withdraws a kept copy that is on screen.
            // (Back through Write and the canvas to the list, without a page load: that would empty the memory.)
            for (let i = 0; i < 4 && page.url() !== `${base}/projects`; i++) { await page.goBack(); await pause(300); }
            await page.waitForURL(`${base}/projects`);
            await card.waitFor();
            control.investigationScript = [{ status: 403, delay: 2500 }, { status: 500 }];
            await card.click();
            await node('claim', C1).waitFor();
            await page.goBack();
            await page.waitForURL(`${base}/projects`);
            await card.waitFor();
            await card.click();
            await canvas.locator('[data-canvas-stale]').waitFor();
            assert.equal(control.investigationScript.length, 0, 'both scripted answers were asked for');
            await page.getByRole('main').getByRole('alert').filter({ hasText: 'Could not load investigation' }).first().waitFor({ timeout: 6000 });
            assert.equal(await canvas.count(), 0, 'the kept copy left the screen when the refusal arrived, with no navigation');
            assert.ok(!(await page.locator('body').innerText()).includes('Reciprocity amplifies'), 'none of its text remains');

            // The project is denied while its investigation is still loading, then access returns on the same page:
            // the investigation is asked for again and the canvas appears.
            control.investigationScript = [{ status: 200, delay: 2500 }];
            control.projectStatus = 404;
            await page.goto(home);
            await page.locator('[data-project-error]').waitFor();
            await pause(2800);
            control.projectStatus = 200;
            for (let i = 0; i < 4 && await page.locator('[data-project-error]').count(); i++) {
                await pause(2200);
                await page.evaluate(() => window.dispatchEvent(new Event('online')));
                await pause(600);
            }
            await canvas.waitFor({ timeout: 10000 });
            assert.deepEqual(await kinds(), ALL, 'the canvas is drawn after access returns');

            // The denial is learned on the project list, by a card's prefetch, with no workspace open: the kept
            // investigation goes with it, so a later visit whose investigation fails has no old copy to fall back on.
            // (A card is prefetched at most every 30 seconds, hence the wait. Once is enough.)
            if (width === 1440) {
                await page.goto(`${base}/projects`);
                await card.click();
                await node('claim', C1).waitFor();
                await page.goBack();
                await page.waitForURL(`${base}/projects`);
                await card.waitFor();
                await page.mouse.move(2, 2);
                await pause(31000);
                control.projectLog.length = 0;
                control.projectStatus = 403;
                await card.hover();
                await pause(800);
                control.projectStatus = 200;
                control.investigationStatus = 500;
                await card.click();
                await page.getByRole('main').getByRole('alert').filter({ hasText: 'Could not load investigation' }).first().waitFor({ timeout: 15000 }).catch(async error => {
                    console.error('On screen instead:', { projectRequests: control.projectLog.join(','), canvas: await canvas.count(), stale: await page.locator('[data-canvas-stale]').count(), denied: await page.locator('[data-project-error]').count(), url: page.url(), main: (await page.getByRole('main').last().innerText()).slice(0, 300) });
                    throw error;
                });
                assert.equal(await canvas.count(), 0, 'no kept copy is drawn after the project was denied on the list');
                assert.equal(await page.locator('[data-canvas-stale]').count(), 0);
                control.investigationStatus = 200;
            }

            // Editing while a save is in flight: the bar keeps saying Saving and offers no second Save until the
            // first has been answered; the later edit is then unsaved, and the next Save sends it.
            control.investigation = full;
            await page.goto(`${home}/overview`);
            const field = page.getByLabel('Question', { exact: true });
            const saveButton = page.getByRole('button', { name: 'Save investigation', exact: true });
            const state = page.getByRole('main').getByRole('status').first();
            await state.filter({ hasText: 'Saved' }).waitFor();
            control.putDelay = 2000;
            await field.fill('First edit');
            await saveButton.click();
            await state.filter({ hasText: 'Saving' }).waitFor();
            await field.fill('Second edit, made during the save');
            await pause(300);
            assert.equal((await state.textContent()).trim(), 'Saving', 'the bar still says Saving after an edit during the save');
            assert.equal(await saveButton.isDisabled(), true, 'Save is not offered while a save is in flight');
            await state.filter({ hasText: 'Unsaved changes' }).waitFor({ timeout: 6000 });
            assert.deepEqual(control.puts, ['First edit'], 'one request, with the first edit');
            assert.equal(await field.inputValue(), 'Second edit, made during the save', 'the later edit is still on screen');
            control.putDelay = 0;
            await saveButton.click();
            await state.filter({ hasText: 'Saved' }).waitFor();
            assert.deepEqual(control.puts, ['First edit', 'Second edit, made during the save']);

            // A reload that was asked for before an edit does not replace the edit when its answer arrives.
            control.putStatus = 500;
            await field.fill('Edit that fails to save');
            await saveButton.click();
            await page.getByRole('button', { name: 'Reload latest', exact: true }).click();
            control.investigationScript = [{ status: 200, delay: 2000 }];
            await page.getByRole('button', { name: 'Replace with latest', exact: true }).click();
            await pause(300);
            await field.fill('Written after the reload was asked for');
            await pause(2500);
            assert.equal(control.investigationScript.length, 0, 'the reload was asked for');
            assert.equal(await field.inputValue(), 'Written after the reload was asked for', 'the reload\'s answer did not replace the newer edit');
            assert.notEqual((await state.textContent()).trim(), 'Saved', 'and the work is not reported as saved');
            await page.getByText('Reload failed. Your work is preserved.').first().waitFor();
            control.putStatus = 200;
            control.puts.length = 0;
            control.investigation = full;

            // 11. Another account signs in (in another tab) while this one has unsaved edits on the same project:
            // the first user's document leaves the screen before any answer arrives, and the second user's replaces it.
            await page.goto(`${home}/overview`);
            const question = page.getByLabel('Question', { exact: true });
            await question.waitFor();
            await page.getByRole('status').filter({ hasText: 'Saved' }).first().waitFor();
            const unsaved = 'Unsaved question of the first user';
            await question.fill(unsaved);
            await nav.getByRole('link', { name: 'Canvas', exact: true }).click();
            await canvas.waitFor();
            assert.equal(await page.getByRole('heading', { level: 1 }).textContent(), `Canvas: ${unsaved}`, 'the canvas draws unsaved edits');
            // The first user leaves a zoomed camera and a selection behind.
            const fitted = await canvas.getAttribute('data-zoom');
            await canvas.getByRole('button', { name: 'Zoom in', exact: true }).click();
            await pause(300);
            assert.notEqual(await canvas.getAttribute('data-zoom'), fitted);
            await press(node('claim', C2));
            await page.locator('[data-canvas-detail="claim"]').waitFor();
            control.user = 'v';
            control.investigation = { ...full, case: { ...full.case, question: 'Question of the second user' } };
            control.delay = 1200;
            const other = await context.newPage();
            await other.goto(`${base}/favicon.ico`).catch(() => undefined);
            const switched = Date.now();
            await other.evaluate(() => { const channel = new BroadcastChannel('openpaper-auth'); channel.postMessage({ user: 'v' }); channel.close(); });
            await page.waitForFunction(words => !document.body.innerText.includes(words) && !(document.querySelector('h1')?.textContent || '').includes(words), unsaved, { timeout: 1000 });
            assert.ok(Date.now() - switched < 1200, 'the first user\'s unsaved document left the screen before any request was answered');
            await pause(1400);
            control.delay = 0;
            for (let i = 0; i < 4 && !(await page.getByRole('heading', { level: 1 }).textContent().catch(() => '')).includes('second user'); i++) {
                await pause(2200);
                await page.evaluate(() => window.dispatchEvent(new Event('online')));
                await pause(600);
            }
            assert.equal(await page.getByRole('heading', { level: 1 }).textContent(), 'Canvas: Question of the second user');
            assert.ok(!(await page.locator('body').innerText()).includes(unsaved));
            assert.equal(await detail.count(), 0, 'the second user does not inherit the first user\'s selection');
            assert.equal(await canvas.getAttribute('data-zoom'), fitted, 'nor their camera');
            await other.close();
            control.user = 'u';
            control.investigation = full;

            // 12. Nothing recorded: a prompt, not an empty map.
            control.investigation = empty;
            control.papers = [];
            await page.goto(home);
            await page.getByRole('heading', { name: 'Nothing to map yet', exact: true }).waitFor();
            assert.equal(await canvas.count(), 0);
            assert.equal(await page.getByRole('link', { name: 'Start with the question' }).getAttribute('href'), `/projects/${ID}/overview`);
            assert.equal(await page.locator('[data-canvas-stale]').count(), 0);
            await page.screenshot({ path: path.join(shots, `canvas-empty-${width}.png`) });

            // An empty kept copy that cannot be refreshed says so too.
            await page.goto(`${base}/projects`);
            await card.click();
            await page.getByRole('heading', { name: 'Nothing to map yet', exact: true }).waitFor();
            await page.goBack();
            await page.waitForURL(`${base}/projects`);
            await card.waitFor();
            control.investigationStatus = 500;
            await card.click();
            await page.getByRole('heading', { name: 'Nothing to map yet', exact: true }).waitFor();
            await page.locator('[data-canvas-stale]').waitFor();
            control.investigationStatus = 200;

            // Papers alone are worth drawing.
            control.papers = papers;
            await page.goto(home);
            await canvas.waitFor();
            assert.deepEqual(await kinds(), { question: 1, claim: 0, finding: 0, paper: 2, section: 0 });

            // 13. The paper list fails on a first visit: said so, not drawn as a project without papers.
            control.investigation = full;
            control.papersStatus = 500;
            await page.goto(home);
            await page.getByRole('main').getByRole('alert').filter({ hasText: 'Could not load this project\'s papers' }).first().waitFor();
            assert.equal(await canvas.count(), 0);
            assert.equal(await page.getByRole('heading', { name: 'Nothing to map yet', exact: true }).count(), 0);
            control.papersStatus = 200;

            // 14. The investigation fails to load on a first visit: the message, and no map of papers alone.
            control.investigationStatus = 500;
            await page.goto(home);
            await page.getByRole('main').getByRole('alert').filter({ hasText: 'Could not load investigation' }).first().waitFor();
            assert.equal(await canvas.count(), 0);
            control.investigationStatus = 200;

            // 15. The project fails to load: the alert, as on the other views.
            control.projectStatus = 500;
            await page.goto(home);
            await page.getByRole('main').getByRole('alert').filter({ hasText: /./ }).first().waitFor();
            assert.equal(await canvas.count(), 0);
            control.projectStatus = 200;

            assert.deepEqual(errors, [], 'no page errors');
            console.log(`${width}px: nodes and edges, details, reader and back, keyboard-only open/act/close, camera kept (selection in and out of view), links land on screen, old claim link, return visit in ${elapsed} ms then revised, kept copy on failed reload, Write from a kept copy, late refusal, denial then access on one page, denial learned on the list, edit during a save, edit after a reload was asked for, account switch, empty, papers only, failed loads passed`);
            await context.close();
        }
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exit(1); });
