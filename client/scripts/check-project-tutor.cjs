// Local production UI only, API mocked. Checks tutor mode in a project
// conversation: a study session is started from the Discuss page, its turns
// are asked for with style=tutor and without the reader's open papers as
// scope, the session state that arrives in the stream draws the study path
// and the skill map without ever appearing in the message, a reload restores
// both, and a conversation that is another member's offers no tutor at all.
const { chromium } = require(process.env.OPENPAPER_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const base = process.env.OPENPAPER_BROWSER_BASE || 'http://127.0.0.1:3011';

const PROJECT = 'study-demo';
const SESSION = 'study-1';
const THEIRS = 'theirs-1';
const END = 'END_OF_STREAM';

const papers = [
    { id: 'p1', title: 'Model organisms', authors: [], status: 'read', created_at: '2026-11-08' },
    { id: 'p2', title: 'Narrow is hard', authors: [], status: 'read', created_at: '2026-11-07' },
];
const names = [
    'Explain why a rank-1 adapter is not one feature',
    'Design a held-out test of generalization',
    'Reconcile the two stability results',
];
const subskill = (name, level) => ({ name, level, passes: 0, unprompted: false, last_checked: 0, notes: '' });
const unit = (title, unitPapers, status) => ({ title, papers: unitPapers, status });
const units = ['What was observed', 'Why broad is easier than narrow', 'What is still open'];
const diagnostic = {
    topic: 'Emergent misalignment', phase: 'diagnostic', target_level: 4, difficulty: 'normal', focus: null,
    diagnostic_asked: 1, subskills: names.map(name => subskill(name, 0)),
    path: [unit(units[0], ['p1'], 'todo'), unit(units[1], ['p1', 'p2'], 'todo'), unit(units[2], [], 'todo')],
    misconceptions: [], covered: [], fetch: ['Model organisms: the held-out evaluation'], turn: 1,
};
// Levels 4, 1 and 2 of a possible 15: 47% overall, one subskill at the target.
const teaching = {
    ...diagnostic, phase: 'teaching', focus: names[1], diagnostic_asked: 4, turn: 2,
    subskills: [subskill(names[0], 4), subskill(names[1], 1), subskill(names[2], 2)],
    path: [unit(units[0], ['p1'], 'done'), unit(units[1], ['p1', 'p2'], 'current'), unit(units[2], [], 'todo')],
    misconceptions: ['treats rank as a count of concepts'],
};

const investigation = { format: 'openpaper/investigation', version: 1, case: { question: '', why_it_matters: '', landscape: '', coverage_limits: '', provisional_answer: '', unresolved_tension: '', reconciliation: '', discriminating_experiment: '', update_criteria: '' }, claims: [], findings: [], relations: [], manuscript: { title: '', sections: [] } };

const FIRST_QUESTION ='Here is the path. A few questions first: what changed outside the training domain?';
const PLACED = 'That places you. We start with the second unit: why would the broad solution be easier to find?';
const ORDINARY = 'An ordinary answer about the project papers.';

(async () => {
    const browser = await chromium.launch({ headless: true, executablePath: process.env.OPENPAPER_CHROMIUM || undefined, args: ['--no-sandbox'] });
    try {
        for (const width of [1440, 390]) {
            const page = await browser.newPage({ viewport: { width, height: 1000 }, colorScheme: width === 1440 ? 'light' : 'dark' });
            const errors = [];
            page.on('pageerror', error => errors.push(error.message));

            const sent = [];
            const control = { fail: false };
            const created = [];
            const saved = { messages: [], tutorState: null };
            const conversations = [{ id: THEIRS, title: 'Evidence comparison', is_owner: false, owner_name: 'Colleague', updated_at: '2026-11-08' }];
            await page.route('**/api/**', async route => {
                const req = route.request(), url = new URL(req.url()), path = url.pathname;
                const headers = { 'access-control-allow-origin': base, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'content-type,if-match', 'access-control-allow-methods': 'GET,POST,PUT,PATCH,OPTIONS', 'access-control-expose-headers': 'ETag' };
                if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
                let body = [];
                if (path === '/api/auth/me') body = { success: true, user: { id: 'u', name: 'Learner', email: 'local@example.org', is_active: true, is_blocked: false } };
                else if (path === '/api/subscription/usage') body = { limits: { knowledge_base_size: 100, paper_uploads: 100, chat_credits_weekly: 100, projects: 10 }, usage: { knowledge_base_size: 0, paper_uploads: 0, chat_credits_used: 0, projects: 1 } };
                else if (path === `/api/projects/${PROJECT}`) body = { id: PROJECT, title: 'Emergent misalignment study', description: 'Two papers on emergent misalignment.', research_brief: null, role: 'admin' };
                else if (path === `/api/projects/papers/${PROJECT}`) body = { papers };
                else if (path.endsWith('/file-url')) body = { file_url: `${base}/synthetic-fixture.pdf` };
                else if (path === `/api/projects/${PROJECT}/investigation`) { body = { document: investigation, validation: { findings: {}, blocks: {} } }; headers.ETag = `"investigation:${PROJECT}:1"`; }
                else if (path === `/api/projects/conversations/${PROJECT}`) {
                    if (req.method() === 'POST') {
                        created.push(req.postDataJSON());
                        conversations.unshift({ id: SESSION, title: req.postDataJSON().title, is_owner: true, owner_name: 'Learner', updated_at: '2026-11-09' });
                        body = { id: SESSION, title: req.postDataJSON().title, messages: [] };
                    } else body = conversations;
                } else if (path === `/api/projects/conversations/${PROJECT}/${SESSION}`) {
                    body = { id: SESSION, title: 'Study session', is_owner: true, messages: saved.messages, tutor_state: saved.tutorState };
                } else if (path === `/api/projects/conversations/${PROJECT}/${THEIRS}`) {
                    // What another member is sent: the ordinary turns, and no session.
                    body = { id: THEIRS, title: 'Evidence comparison', is_owner: false, messages: [{ id: 't1', role: 'user', content: 'Compare the evidence.' }, { id: 't2', role: 'assistant', content: 'A colleague was answered here.' }], tutor_state: null };
                } else if (path === `/api/projects/artifacts/${PROJECT}`) body = { artifacts: [] };
                else if (path === `/api/projects/tables/jobs/${PROJECT}` || path === `/api/projects/charts/jobs/${PROJECT}`) body = { jobs: [] };
                else if (path === `/api/projects/invitations/${PROJECT}/`) body = { invitations: [] };
                else if (path === `/api/projects/papers/${PROJECT}/pending-jobs`) body = { jobs: [] };
                else if (path === '/api/message/chat/everything') {
                    const request = req.postDataJSON();
                    sent.push(request);
                    if (control.fail) return route.fulfill({ status: 200, headers, contentType: 'text/plain', body: JSON.stringify({ type: 'error', content: 'Synthetic failure' }) + END });
                    const events = [{ type: 'status', content: 'View File - Model organisms' }];
                    let reply = ORDINARY;
                    if (request.style === 'tutor') {
                        const starting = request.user_query.startsWith('Teach me');
                        reply = starting ? FIRST_QUESTION : PLACED;
                        saved.tutorState = starting ? diagnostic : teaching;
                    }
                    // In two pieces, as a model streams it.
                    events.push({ type: 'content', content: reply.slice(0, 20) }, { type: 'content', content: reply.slice(20) });
                    events.push({ type: 'trace', content: { status_messages: ['View File - Model organisms'], tool_calls: [] } });
                    if (request.style === 'tutor') events.push({ type: 'tutor_state', content: saved.tutorState });
                    saved.messages.push({ id: `m${saved.messages.length}`, role: 'user', content: request.user_query }, { id: `m${saved.messages.length + 1}`, role: 'assistant', content: reply });
                    return route.fulfill({ status: 200, headers, contentType: 'text/plain', body: events.map(event => JSON.stringify(event) + END).join('') });
                }
                return route.fulfill({ status: 200, headers, contentType: 'application/json', body: JSON.stringify(body) });
            });

            const main = page.getByRole('main').last();
            const input = page.locator('form textarea');
            const toggle = page.getByRole('button', { name: 'Tutor', exact: true });
            const panel = page.getByRole('region', { name: 'Tutoring session', exact: true });
            const path = panel.getByRole('list', { name: 'Study path', exact: true });
            const map = panel.getByRole('list', { name: 'Skill map', exact: true });
            const turns = count => page.waitForFunction(n => document.querySelectorAll('[data-message-index]').length >= n, count);
            const say = async text => { await input.fill(text); await input.press('Enter'); };

            // The Discuss page offers a study session beside the research tasks.
            await page.goto(`${base}/projects/${PROJECT}/discuss`);
            const study = main.locator('section[aria-labelledby="study-heading"]');
            await study.getByRole('heading', { name: 'Study these papers', exact: true }).waitFor();
            assert.match(await study.innerText(), /Only you see a study session/);
            assert.equal(sent.length, 0, 'nothing is sent until a session is started');

            // Starting one creates a discussion and sends its first turn to the tutor.
            await study.getByRole('button', { name: 'Start a study session' }).click();
            await page.waitForURL(`**/projects/${PROJECT}/conversations/${SESSION}`);
            await page.getByText(FIRST_QUESTION, { exact: true }).waitFor();
            assert.deepEqual(created, [{ title: 'Study session' }]);
            assert.equal(sent.length, 1);
            assert.equal(sent[0].style, 'tutor');
            assert.equal(sent[0].user_query, 'Teach me this project.');
            assert.equal(sent[0].project_id, PROJECT);
            assert.equal(sent[0].conversation_id, SESSION);
            assert.equal('mentioned_paper_ids' in sent[0], false);

            // The switch is on, remembered for this conversation, and the panel shows the path.
            assert.equal(await toggle.getAttribute('aria-pressed'), 'true');
            assert.equal(await page.evaluate(id => localStorage.getItem(`openpaper:tutor-mode:conversation:${id}`), SESSION), 'true');
            await panel.getByText('Placing your level', { exact: true }).waitFor();
            assert.match(await panel.innerText(), /Emergent misalignment/);
            assert.equal(await path.getByRole('listitem').count(), units.length);
            assert.match(await panel.innerText(), /0 of 3 done/);
            assert.equal(await path.locator('[aria-current="step"]').count(), 0, 'no unit is current during the diagnostic');
            // A unit names the papers it draws on, by title.
            assert.deepEqual(await path.getByRole('listitem').nth(1).getByRole('button').allInnerTexts(), ['Model organisms', 'Narrow is hard']);
            assert.equal(await path.getByRole('listitem').nth(2).getByRole('button').count(), 0);
            // The map names what is covered but claims no levels yet.
            assert.equal(await map.getByRole('listitem').count(), names.length);
            assert.equal(await panel.getByRole('progressbar').count(), 0, 'no levels are shown before placement');
            await panel.getByRole('button', { name: "I don't know", exact: true }).waitFor();
            assert.equal(await panel.getByRole('button', { name: 'Next unit', exact: true }).count(), 0);
            assert.equal(await input.getAttribute('placeholder'), 'Answer the tutor, or ask to be taught these papers.');
            // A tutor turn covers the whole project, so there is nothing to scope.
            assert.equal(await page.getByRole('button', { name: 'Add context', exact: true }).count(), 0);
            assert.doesNotMatch(await page.locator('body').innerText(), /TUTOR-STATE|diagnostic_asked|the held-out evaluation/, 'the state is never shown as text');

            // Opening a paper from the path puts it in the reader beside the chat...
            await path.getByRole('listitem').nth(1).getByRole('button', { name: 'Narrow is hard', exact: true }).click();
            const closeReader = page.getByRole('button', { name: 'Close reader', exact: true });
            await closeReader.waitFor();
            if (width < 768) await closeReader.click();

            // ...and the next tutor turn is still about the whole project.
            await say('Answers changed on prompts the fine-tuning never touched.');
            await page.getByText(PLACED, { exact: true }).waitFor();
            assert.equal(sent[1].style, 'tutor');
            assert.equal('mentioned_paper_ids' in sent[1], false, 'an open paper does not narrow a tutor turn');

            // Placed: the path moves on, and levels, focus and the target mark appear.
            await panel.getByText('47% overall', { exact: true }).waitFor();
            assert.match(await panel.innerText(), /1 of 3 done/);
            const steps = path.getByRole('listitem');
            assert.equal(await steps.nth(0).getByLabel('Done').count(), 1);
            assert.equal(await steps.nth(1).getAttribute('aria-current'), 'step');
            assert.match(await steps.nth(1).innerText(), /Current unit/);
            assert.equal(await path.locator('[aria-current="step"]').count(), 1);
            const bars = panel.getByRole('progressbar');
            assert.deepEqual(await bars.evaluateAll(nodes => nodes.map(node => node.getAttribute('aria-valuenow'))), ['4', '1', '2']);
            assert.equal(await panel.getByLabel('Target reached').count(), 1, 'only the subskill at the target is marked');
            assert.match(await map.getByRole('listitem').nth(1).innerText(), /Current focus/);
            // The mocked reply lands inside the panel transition that sending
            // starts; let it finish, so the picture is of the page at rest.
            await page.evaluate(() => Promise.all(document.getAnimations()
                // A spinner never finishes; only what has an end is waited for.
                .filter(animation => Number.isFinite(animation.effect?.getComputedTiming().endTime))
                .map(animation => animation.finished.catch(() => { }))));
            await page.screenshot({ path: `/tmp/openpaper-project-tutor-${width}.png` });

            // A command chip is sent on its own, and leaves a half-typed answer alone.
            await input.fill('Because the general solution');
            await panel.getByRole('button', { name: 'Next unit', exact: true }).click();
            await turns(6);
            assert.equal(sent.length, 3);
            assert.equal(sent[2].user_query, 'next');
            assert.equal(sent[2].style, 'tutor');
            assert.equal(await input.inputValue(), 'Because the general solution', 'the draft survives a command');

            // A command that fails is what Retry sends again, not the draft beside it.
            control.fail = true;
            await panel.getByRole('button', { name: 'Show progress', exact: true }).click();
            const retry = page.getByRole('button', { name: 'Retry', exact: true });
            await retry.waitFor();
            assert.equal(sent[3].user_query, 'show progress');
            assert.equal(await input.inputValue(), 'Because the general solution', 'the draft survives a failed command');
            control.fail = false;
            await retry.click();
            await turns(8);
            assert.equal(sent.length, 5);
            assert.equal(sent[4].user_query, 'show progress', 'retry sends the command again');
            assert.equal(sent[4].style, 'tutor');
            assert.equal(await input.inputValue(), 'Because the general solution', 'the draft survives the retry');
            assert.equal(await retry.count(), 0);
            await input.fill('');

            // The tutor's notes on the learner are never on the page, and cannot be exported.
            assert.equal(await panel.getByRole('button', { name: /save state|resume/i }).count(), 0);
            assert.doesNotMatch(await page.locator('body').innerText(), /treats rank as a count/, 'the notes stay out of the page');

            // The panel folds away and back.
            const header = panel.getByRole('button', { name: /Emergent misalignment/ });
            await header.click();
            assert.equal(await header.getAttribute('aria-expanded'), 'false');
            assert.equal(await bars.count(), 0);
            await header.click();
            assert.equal(await bars.count(), names.length);

            // A reload keeps the switch (this browser) and the session (the server).
            await page.goto(`${base}/projects/${PROJECT}/conversations/${SESSION}`);
            await page.getByText(PLACED, { exact: true }).first().waitFor();
            assert.equal(await toggle.getAttribute('aria-pressed'), 'true');
            await panel.getByText('47% overall', { exact: true }).waitFor();
            assert.match(await panel.innerText(), /1 of 3 done/);
            assert.equal(sent.length, 5, 'reading a conversation back sends nothing');

            // Off: the next question is ordinary, scoped as before, and the session is kept.
            await toggle.click();
            assert.equal(await panel.count(), 0);
            assert.equal(await input.getAttribute('placeholder'), 'Ask a follow-up');
            await page.getByRole('button', { name: 'Add context', exact: true }).waitFor();
            await say('One ordinary question.');
            await page.getByText(ORDINARY, { exact: true }).waitFor();
            assert.equal('style' in sent[5], false, 'an ordinary question carries no style');
            await toggle.click();
            await panel.getByText('47% overall', { exact: true }).waitFor();

            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'no horizontal overflow');

            // Another member's conversation: read only, and no tutor to switch on.
            await page.goto(`${base}/projects/${PROJECT}/conversations/${THEIRS}`);
            await page.getByText('A colleague was answered here.', { exact: true }).waitFor();
            assert.equal(await toggle.count(), 0, 'tutor mode is offered only in a conversation of your own');
            assert.equal(await panel.count(), 0);
            assert.equal(await input.isDisabled(), true);

            assert.deepEqual(errors, []);
            await page.close();
            console.log(`project tutor: ${width}px ok`);
        }
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exit(1); });
