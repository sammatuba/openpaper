// Local production UI only, API mocked. Checks tutor mode in the paper chat:
// the switch is remembered per paper, a tutor turn is asked for with
// style=tutor and an ordinary one is not, the session state that arrives in
// the stream draws the skill map without ever appearing in the message, and a
// reload restores the map from the conversation.
const { chromium } = require(process.env.OPENPAPER_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const base = process.env.OPENPAPER_BROWSER_BASE || 'http://127.0.0.1:3011';

const PAPER = 'p1';
const CONVERSATION = 'c1';
const END = 'END_OF_STREAM';

const names = [
    'Explain why attention replaces recurrence',
    'Derive scaled dot-product attention',
    'Read the ablation table',
];
const subskill = (name, level) => ({ name, level, passes: 0, unprompted: false, last_checked: 0, notes: '' });
const diagnostic = {
    topic: 'Attention study', phase: 'diagnostic', target_level: 4, difficulty: 'normal', focus: null,
    diagnostic_asked: 1, subskills: names.map(name => subskill(name, 0)), misconceptions: [], covered: [], turn: 1,
};
// Levels 4, 1 and 2 of a possible 15: 47% overall, one subskill at the target.
const teaching = {
    ...diagnostic, phase: 'teaching', focus: names[1], diagnostic_asked: 4, turn: 2,
    subskills: [subskill(names[0], 4), subskill(names[1], 1), subskill(names[2], 2)],
    misconceptions: ['treats path length and depth as the same thing'],
};

const FIRST_QUESTION = 'A few questions first, to see what you know. What problem does the paper set out to solve?';
const PLACED = 'That places you. We start with the derivation: what does the scaling factor prevent?';
const ORDINARY = 'An ordinary answer about the paper.';

(async () => {
    const browser = await chromium.launch({ headless: true, executablePath: process.env.OPENPAPER_CHROMIUM || undefined, args: ['--no-sandbox'] });
    try {
        for (const width of [1440, 390]) {
            const page = await browser.newPage({ viewport: { width, height: 1000 }, colorScheme: width === 1440 ? 'light' : 'dark' });
            const errors = [];
            page.on('pageerror', error => errors.push(error.message));

            const sent = [];
            const saved = { messages: [], tutorState: null };
            await page.route('**/api/**', async route => {
                const req = route.request(), url = new URL(req.url()), path = url.pathname;
                const headers = { 'access-control-allow-origin': base, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'content-type', 'access-control-allow-methods': 'GET,POST,PATCH,OPTIONS' };
                if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
                let body = [];
                if (path === '/api/auth/me') body = { success: true, user: { id: 'u', name: 'Learner', email: 'local@example.org', is_active: true, is_blocked: false } };
                else if (path === '/api/subscription/usage') body = { plan: 'researcher', limits: { knowledge_base_size: 100, paper_uploads: 100, chat_credits_weekly: 100 }, usage: { knowledge_base_size: 0, paper_uploads: 0, chat_credits_used: 0, chat_credits_remaining: 100 } };
                else if (path === '/api/paper') body = { id: PAPER, title: 'Attention study', authors: ['A. Author'], abstract: 'A synthetic paper.', keywords: [], institutions: [], tags: [], status: 'reading', is_public: false, summary: null, summary_citations: [] };
                else if (path === '/api/paper/conversation') body = { id: CONVERSATION };
                else if (path === `/api/conversation/${CONVERSATION}`) {
                    const firstPage = (url.searchParams.get('page') || '1') === '1';
                    body = { id: CONVERSATION, title: null, messages: firstPage ? saved.messages : [], tutor_state: saved.tutorState };
                } else if (path === '/api/message/models') body = { models: {}, default: '' };
                else if (path === '/api/message/chat/paper') {
                    const request = req.postDataJSON();
                    sent.push(request);
                    const events = [];
                    let reply = ORDINARY;
                    if (request.style === 'tutor') {
                        const starting = request.user_query.startsWith('Teach me');
                        reply = starting ? FIRST_QUESTION : PLACED;
                        saved.tutorState = starting ? diagnostic : teaching;
                    }
                    // In two pieces, as a model streams it.
                    events.push({ type: 'content', content: reply.slice(0, 20) }, { type: 'content', content: reply.slice(20) });
                    if (request.style === 'tutor') events.push({ type: 'tutor_state', content: saved.tutorState });
                    saved.messages.push({ id: `m${saved.messages.length}`, role: 'user', content: request.user_query }, { id: `m${saved.messages.length + 1}`, role: 'assistant', content: reply });
                    return route.fulfill({ status: 200, headers, contentType: 'text/plain', body: events.map(event => JSON.stringify(event) + END).join('') });
                }
                return route.fulfill({ status: 200, headers, contentType: 'application/json', body: JSON.stringify(body) });
            });

            const open = async () => {
                await page.goto(`${base}/paper/${PAPER}?rsf=chat`);
                if (width < 768) await page.getByRole('button', { name: 'Tools', exact: true }).click();
                await page.locator('form textarea').waitFor();
            };
            const input = page.locator('form textarea');
            const toggle = page.getByRole('button', { name: 'Tutor', exact: true });
            const panel = page.getByRole('region', { name: 'Tutoring session', exact: true });
            const starter = page.getByRole('button', { name: 'What methodology did the authors use?', exact: true });
            const say = async text => { await input.fill(text); await input.press('Enter'); };

            await open();

            // Off by default: the chat is the one that was there before.
            assert.equal(await toggle.getAttribute('aria-pressed'), 'false');
            assert.equal(await panel.count(), 0, 'no tutoring panel until the mode is on');
            assert.equal(await input.getAttribute('placeholder'), 'Ask something about this paper.');
            await starter.waitFor();

            // On: the panel explains itself, and answer-seeking starters step aside.
            await toggle.click();
            assert.equal(await toggle.getAttribute('aria-pressed'), 'true');
            await panel.waitFor();
            assert.match(await panel.innerText(), /Not started/);
            assert.match(await panel.innerText(), /teaches this paper by asking/);
            assert.equal(await starter.count(), 0, 'starter questions are hidden in tutor mode');
            assert.equal(await input.getAttribute('placeholder'), 'Answer the tutor, or ask to be taught this paper.');
            assert.equal(await page.evaluate(id => localStorage.getItem(`openpaper:tutor-mode:${id}`), PAPER), 'true');
            assert.equal(sent.length, 0, 'switching the mode sends nothing');

            // And off again, for an ordinary question.
            await toggle.click();
            assert.equal(await panel.count(), 0);
            await starter.waitFor();
            await say('What is this paper about?');
            await page.getByText(ORDINARY, { exact: true }).waitFor();
            assert.equal(sent.length, 1);
            assert.equal('style' in sent[0], false, 'an ordinary question carries no style');

            // Start a session from the panel.
            await toggle.click();
            await panel.getByRole('button', { name: 'Teach me this paper', exact: true }).click();
            await page.getByText(FIRST_QUESTION, { exact: true }).waitFor();
            assert.equal(sent.length, 2);
            assert.equal(sent[1].style, 'tutor');
            assert.equal(sent[1].user_query, 'Teach me this paper.');
            assert.equal(sent[1].conversation_id, CONVERSATION);

            // During the diagnostic the map names what is covered but claims no levels.
            await panel.getByText('Placing your level', { exact: true }).waitFor();
            assert.match(await panel.innerText(), /Attention study/);
            assert.equal(await panel.getByRole('listitem').count(), names.length);
            assert.equal(await panel.getByRole('progressbar').count(), 0, 'no levels are shown before placement');
            assert.equal(await panel.getByRole('button', { name: 'Teach me this paper', exact: true }).count(), 0);
            // Nothing is taught during the diagnostic, so there is no answer to ask for.
            await panel.getByRole('button', { name: "I don't know", exact: true }).waitFor();
            assert.equal(await panel.getByRole('button', { name: 'Just tell me', exact: true }).count(), 0);
            assert.doesNotMatch(await page.locator('body').innerText(), /TUTOR-STATE|diagnostic_asked/, 'the state is never shown as text');

            // An answer places the learner: levels, overall, focus and the target mark.
            await say('It removes recurrence so every position can attend to every other.');
            await page.getByText(PLACED, { exact: true }).waitFor();
            assert.equal(sent[2].style, 'tutor');
            await panel.getByText('47% overall', { exact: true }).waitFor();
            const bars = panel.getByRole('progressbar');
            assert.equal(await bars.count(), names.length);
            assert.deepEqual(await bars.evaluateAll(nodes => nodes.map(node => node.getAttribute('aria-valuenow'))), ['4', '1', '2']);
            assert.equal(await panel.getByLabel('Target reached').count(), 1, 'only the subskill at the target is marked');
            assert.match(await panel.getByRole('listitem').nth(1).innerText(), /Current focus/);
            assert.doesNotMatch(await panel.getByRole('listitem').nth(0).innerText(), /Current focus/);
            await page.screenshot({ path: `/tmp/openpaper-tutor-${width}.png` });

            // A command chip is sent on its own, and leaves a half-typed answer alone.
            await panel.getByRole('button', { name: 'Just tell me', exact: true }).waitFor();
            await input.fill('It keeps the dot products from');
            await panel.getByRole('button', { name: 'Show progress', exact: true }).click();
            await page.waitForFunction(count => document.querySelectorAll('[data-message-index]').length >= count, 8);
            assert.equal(sent.length, 4);
            assert.equal(sent[3].user_query, 'show progress');
            assert.equal(sent[3].style, 'tutor');
            assert.equal(await input.inputValue(), 'It keeps the dot products from', 'the draft survives a command');
            await input.fill('');

            // The session resumes by itself, so there is no way to export it: an
            // export would be the tutor's notes on the learner, one paste from a
            // chat that a shared paper shows. The notes are never on the page.
            assert.equal(await panel.getByRole('button', { name: /save state|resume/i }).count(), 0);
            assert.doesNotMatch(await page.locator('body').innerText(), /treats path length/, 'the notes stay out of the page');

            // The map folds away and back.
            const header = panel.getByRole('button', { name: /Attention study/ });
            await header.click();
            assert.equal(await header.getAttribute('aria-expanded'), 'false');
            assert.equal(await bars.count(), 0);
            await header.click();
            assert.equal(await bars.count(), names.length);

            // A reload keeps the switch (this browser) and the session (the server).
            await open();
            assert.equal(await toggle.getAttribute('aria-pressed'), 'true');
            await panel.getByText('47% overall', { exact: true }).waitFor();
            assert.equal(await bars.count(), names.length);

            // Off: the next question is ordinary again, and the session is kept for later.
            await toggle.click();
            assert.equal(await panel.count(), 0);
            await say('One more ordinary question.');
            await page.waitForFunction(count => document.querySelectorAll('[data-message-index]').length >= count, 10);
            assert.equal('style' in sent[4], false);
            await toggle.click();
            await panel.getByText('47% overall', { exact: true }).waitFor();

            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'no horizontal overflow');
            assert.deepEqual(errors, []);
            await page.close();
            console.log(`tutor mode: ${width}px ok`);
        }
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exit(1); });
