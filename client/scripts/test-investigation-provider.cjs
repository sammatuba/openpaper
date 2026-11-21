// The investigation provider's load, save and reload orderings, driven through the real component.
// React is replaced by a small stand-in that runs function components with hooks (state, refs,
// callbacks, effects, an external store, context), so every answer can be released by hand in any
// order. The workspace hook and fetch are stand-ins too; the provider, the investigation library
// and the kept-copy module are the real ones.
const ts = require('typescript');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');

const src = path.resolve(__dirname, '../src');
const compile = (m, filename) => m._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText, filename);
require.extensions['.ts'] = compile;
require.extensions['.tsx'] = compile;

// ---- a stand-in for React: enough to run the provider and observe what it provides
let rendering = null, stale = false;
const same = (a, b) => !!a && !!b && a.length === b.length && a.every((item, index) => Object.is(item, b[index]));
const hook = make => { const instance = rendering, index = instance.at++; if (!(index in instance.hooks)) instance.hooks[index] = make(); return instance.hooks[index]; };
const React = {
    createContext: initial => { const context = { value: initial }; context.Provider = { provides: context }; return context; },
    useContext: context => context.value,
    useState: initial => {
        const cell = hook(() => ({ value: typeof initial === 'function' ? initial() : initial }));
        return [cell.value, next => { const value = typeof next === 'function' ? next(cell.value) : next; if (!Object.is(value, cell.value)) { cell.value = value; stale = true; } }];
    },
    useRef: initial => hook(() => ({ current: initial })),
    useCallback: (fn, deps) => { const cell = hook(() => ({ fn, deps })); if (!same(cell.deps, deps)) { cell.fn = fn; cell.deps = deps; } return cell.fn; },
    useEffect: (fn, deps) => { const instance = rendering, cell = hook(() => ({ deps: null, cleanup: null })); if (!same(cell.deps, deps)) { cell.deps = deps; instance.effects.push(() => { cell.cleanup?.(); cell.cleanup = fn() || null; }); instance.cleanups.add(cell); } },
    useSyncExternalStore: (subscribe, get) => { const instance = rendering; hook(() => { const stop = subscribe(() => { stale = true; }); instance.cleanups.add({ cleanup: stop }); return {}; }); return get(); },
};
const runtime = { jsx: (type, props, key) => ({ type, props, key }), jsxs: (type, props, key) => ({ type, props, key }), Fragment: 'fragment' };

// ---- stand-ins for the workspace and the network
const workspace = { projectId: 'p', project: { role: 'admin' }, projectDenied: false };
const load = Module._load;
Module._load = function (request, ...rest) {
    if (request === 'react') return React;
    if (request === 'react/jsx-runtime') return runtime;
    if (request.endsWith('/ProjectWorkspaceProvider')) return { useProjectWorkspace: () => workspace };
    return load.call(this, request.startsWith('@/') ? path.join(src, request.slice(2)) : request, ...rest);
};
// The provider listens for the page being left; nothing here leaves it.
const quiet = { addEventListener() {}, removeEventListener() {} };
global.window = { ...quiet, document: quiet, location: { href: 'http://localhost/projects/p' } };
let calls = [];
global.fetch = (url, options = {}) => new Promise(resolve => calls.push({
    method: options.method || 'GET', sent: options.body ? JSON.parse(options.body) : null, tag: options.headers?.['If-Match'] ?? null,
    answer: (status, document, revision = 1) => resolve({ ok: status >= 200 && status < 300, status, headers: { get: () => `"investigation:p:${revision}"` }, json: async () => ({ document, validation: { findings: {}, blocks: {} } }) }),
}));

const { InvestigationProvider } = require(path.join(src, 'components/project/InvestigationProvider.tsx'));
const { emptyInvestigation } = require(path.join(src, 'lib/investigation.ts'));
const snapshot = require(path.join(src, 'lib/investigation-snapshot.ts'));

// ---- a renderer for that stand-in: one provider, its keyed child, and the value it provides
let instances = new Map(), provided = null;
function unmount(instance) { for (const cell of instance.cleanups) cell.cleanup?.(); }
function renderElement(element, slot) {
    if (!element || typeof element !== 'object') return;
    if (element.type?.provides) { element.type.provides.value = provided = element.props.value; return; }
    if (typeof element.type !== 'function') return;
    let instance = instances.get(slot);
    if (instance && (instance.type !== element.type || instance.key !== element.key)) { unmount(instance); instance = undefined; }
    if (!instance) { instance = { type: element.type, key: element.key, hooks: [], cleanups: new Set(), effects: [], at: 0 }; instances.set(slot, instance); }
    instance.at = 0;
    rendering = instance;
    const child = element.type(element.props);
    rendering = null;
    renderElement(child, `${slot}/0`);
}
function flush() {
    for (let pass = 0; pass < 50; pass++) {
        stale = false;
        renderElement({ type: InvestigationProvider, props: { children: null }, key: null }, 'root');
        for (const instance of instances.values()) for (const effect of instance.effects.splice(0)) effect();
        if (!stale) return;
    }
    throw new Error('The provider did not settle');
}
// Lets promise callbacks run, then renders whatever they changed.
async function settle() { for (let i = 0; i < 6; i++) { await new Promise(resolve => setImmediate(resolve)); flush(); } }
async function mount() {
    for (const instance of instances.values()) unmount(instance);
    instances = new Map(); provided = null; calls = [];
    Object.assign(workspace, { projectId: 'p', project: { role: 'admin' }, projectDenied: false });
    snapshot.forgetInvestigations();
    flush();
    await settle();
}
const failure = promise => promise.then(() => null, error => error);

// ---- documents
const uuid = n => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const B1 = uuid(1), B2 = uuid(2);
const block = id => ({ id, kind: 'paragraph', text: 'Text.', claim_ids: [], finding_ids: [], provenance: { kind: 'human' }, dependency_pins: {} });
const doc = (question, blocks = [B1, B2]) => { const d = emptyInvestigation(); d.case.question = question; d.manuscript.sections = blocks.length ? [{ id: uuid(9), title: 'S', blocks: blocks.map(block) }] : []; return d; };
const edit = question => { provided.update(draft => { draft.case.question = question; }); flush(); };
const shown = () => ({ question: provided.document.case.question, status: provided.status, dirty: provided.dirty, revision: provided.revision, loaded: provided.loaded });
// Mounts and answers the first load.
async function opened(question = 'server 1') {
    await mount();
    assert.equal(calls.length, 1);
    calls[0].answer(200, doc(question), 1);
    await settle();
    assert.deepEqual(shown(), { question, status: 'Saved', dirty: false, revision: 1, loaded: true });
}

// A promise left waiting on an answer nobody gives ends the script quietly; that must not read as a pass.
let finished = false;
process.on('exit', code => { if (!finished && code === 0) { console.error('investigation provider: ended before every case ran (something is waiting on an answer that was never given)'); process.exitCode = 1; } });

(async () => {
    // 1. Loading.
    await mount();
    assert.deepEqual(shown(), { question: '', status: 'Loading', dirty: false, revision: 0, loaded: false });
    calls[0].answer(500, null);
    await settle();
    assert.equal(provided.status, 'Could not load investigation');
    assert.equal(provided.loaded, false);
    await opened();
    assert.deepEqual(snapshot.recallInvestigation('p').case.question, 'server 1', 'the loaded document is kept for a return visit');

    // 2. Two reloads answered in reverse order: the later-started one decides everything that is shown.
    {
        await opened();
        const first = failure(provided.reload()), second = provided.reload();
        calls[2].answer(200, doc('server 3'), 3);
        await second; await settle();
        calls[1].answer(200, doc('server 2'), 2);
        assert.ok(await first, 'the overtaken reload is reported as not done');
        await settle();
        assert.deepEqual(shown(), { question: 'server 3', status: 'Saved', dirty: false, revision: 3, loaded: true });
        assert.equal(snapshot.recallInvestigation('p').case.question, 'server 3');
    }

    // 3. Reload asked for, then an edit and a save; the reload answers first. The edit survives, and the conflict that follows can be recovered from.
    {
        await opened();
        const reload = failure(provided.reload());
        edit('my edit');
        const save = provided.save();
        flush();
        calls[1].answer(200, doc('server 2'), 2);
        assert.ok(await reload, 'the reload is reported as not done');
        await settle();
        assert.equal(provided.document.case.question, 'my edit');
        assert.equal(provided.status, 'Saving');
        assert.equal(calls[2].tag, '"investigation:p:1"');
        calls[2].answer(412, null);
        await save; await settle();
        assert.deepEqual(shown(), { question: 'my edit', status: 'Conflict', dirty: true, revision: 1, loaded: true });
    }

    // The same with an edit alone and no save: the edit is still not the reload's to replace.
    {
        await opened();
        const reload = failure(provided.reload());
        edit('typed while the reload was on its way');
        calls[1].answer(200, doc('server 2'), 2);
        assert.ok(await reload);
        await settle();
        assert.deepEqual(shown(), { question: 'typed while the reload was on its way', status: 'Unsaved changes', dirty: true, revision: 1, loaded: true });
        assert.equal(snapshot.recallInvestigation('p').case.question, 'server 2', 'the answer is still the last saved copy');
    }

    // 4. Reload asked for on a dirty draft, then a save retried and refused before the reload answers: the draft is still there.
    {
        await opened();
        edit('my draft');
        const reload = failure(provided.reload());
        const save = provided.save();
        flush();
        calls[2].answer(412, null);
        await save; await settle();
        assert.equal(provided.status, 'Conflict');
        calls[1].answer(200, doc('other writer'), 2);
        assert.ok(await reload, 'a reload overtaken by a save attempt, finished or not, is not applied');
        await settle();
        assert.deepEqual(shown(), { question: 'my draft', status: 'Conflict', dirty: true, revision: 1, loaded: true });
        // A reload asked for now, with nothing after it, does replace the draft.
        const again = provided.reload();
        calls[3].answer(200, doc('other writer'), 2);
        await again; await settle();
        assert.deepEqual(shown(), { question: 'other writer', status: 'Saved', dirty: false, revision: 2, loaded: true });
    }

    // 5. A reload asked for during a save is refused; a second Save during a save sends nothing.
    {
        await opened();
        edit('one');
        const save = provided.save();
        flush();
        const refusedReload = failure(provided.reload());
        await provided.save();
        flush();
        assert.equal(calls.length, 2, 'one PUT, no GET');
        assert.ok(await refusedReload);
        // An edit during the save keeps the status at Saving; once answered, the later edit is unsaved and the next Save sends it.
        edit('two');
        assert.equal(provided.status, 'Saving');
        calls[1].answer(200, doc('one'), 2);
        await save; await settle();
        assert.deepEqual(shown(), { question: 'two', status: 'Unsaved changes', dirty: true, revision: 2, loaded: true });
        const next = provided.save();
        flush();
        assert.equal(calls[2].sent.document.case.question, 'two');
        assert.equal(calls[2].tag, '"investigation:p:2"');
        calls[2].answer(200, doc('two'), 3);
        await next; await settle();
        assert.deepEqual(shown(), { question: 'two', status: 'Saved', dirty: false, revision: 3, loaded: true });
    }

    // 6. A block review asked for during a save is not in that request, leaves the document unsaved, and goes with the next save.
    {
        await opened();
        edit('one');
        const save = provided.save();
        flush();
        await provided.save([B1]);
        assert.deepEqual(calls[1].sent.reviewed_block_ids, []);
        calls[1].answer(200, doc('one'), 2);
        await save; await settle();
        assert.equal(provided.status, 'Unsaved changes', 'a review still to be sent means the document is not fully saved');
        assert.equal(provided.dirty, true);
        const next = provided.save();
        flush();
        assert.deepEqual(calls[2].sent.reviewed_block_ids, [B1]);
        calls[2].answer(200, doc('one'), 3);
        await next; await settle();
        assert.equal(provided.status, 'Saved');
        const plain = provided.save();
        flush();
        assert.deepEqual(calls[3].sent.reviewed_block_ids, [], 'a sent review is not sent again');
        calls[3].answer(200, doc('one'), 4);
        await plain; await settle();
    }

    // 7. A review whose save fails is sent again with the retry, once.
    {
        await opened();
        const save = provided.save([B1]);
        flush();
        assert.deepEqual(calls[1].sent.reviewed_block_ids, [B1]);
        calls[1].answer(500, null);
        await save; await settle();
        assert.equal(provided.status, 'Save failed');
        assert.equal(provided.dirty, true, 'a review still waiting to be sent keeps the document unsaved');
        const retry = provided.save();
        flush();
        assert.deepEqual(calls[2].sent.reviewed_block_ids, [B1]);
        calls[2].answer(200, doc('server 1'), 2);
        await retry; await settle();
        assert.equal(provided.status, 'Saved');
        edit('later');
        const later = provided.save([B2]);
        flush();
        assert.deepEqual(calls[3].sent.reviewed_block_ids, [B2], 'the earlier review is not repeated');
        calls[3].answer(200, doc('later'), 3);
        await later; await settle();
    }

    // 8. A review refused with a conflict, then a reload that replaces the draft: the review is gone with the draft.
    {
        await opened();
        const save = provided.save([B1, B2]);
        flush();
        calls[1].answer(412, null);
        await save; await settle();
        assert.equal(provided.status, 'Conflict');
        const reload = provided.reload();
        // The latest version still has both blocks, so only clearing the queue keeps the old reviews from being sent.
        calls[2].answer(200, doc('other writer'), 2);
        await reload; await settle();
        edit('after the reload');
        const next = provided.save();
        flush();
        assert.deepEqual(calls[3].sent.reviewed_block_ids, [], 'reviews of a discarded draft are not sent');
        calls[3].answer(200, doc('after the reload'), 3);
        await next; await settle();
        assert.equal(provided.status, 'Saved');
    }
    // A review of a block that an edit has since removed is not sent either.
    {
        await opened();
        const save = provided.save([B1]);
        flush();
        calls[1].answer(500, null);
        await save; await settle();
        provided.update(draft => { draft.manuscript.sections[0].blocks = draft.manuscript.sections[0].blocks.filter(item => item.id !== B1); });
        flush();
        const retry = provided.save();
        flush();
        assert.deepEqual(calls[2].sent.reviewed_block_ids, []);
        calls[2].answer(200, doc('server 1', [B2]), 2);
        await retry; await settle();
    }

    // 9. The project is denied while a save is in flight: the answer is not applied, the save is reported failed, the draft stays, nothing is kept.
    {
        await opened();
        edit('mine');
        const save = provided.save();
        flush();
        workspace.projectDenied = true;
        flush();
        assert.equal(snapshot.recallInvestigation('p'), null);
        calls[1].answer(200, doc('mine'), 2);
        await save; await settle();
        assert.deepEqual(shown(), { question: 'mine', status: 'Save failed', dirty: true, revision: 1, loaded: true });
        assert.equal(snapshot.recallInvestigation('p'), null, 'a save answered after the denial does not bring the copy back');
    }
    // A save the server refuses outright drops the kept copy and keeps the draft.
    {
        await opened();
        edit('mine');
        const save = provided.save();
        flush();
        calls[1].answer(403, null);
        await save; await settle();
        assert.deepEqual(shown(), { question: 'mine', status: 'Save failed', dirty: true, revision: 1, loaded: true });
        assert.equal(snapshot.recallInvestigation('p'), null);
    }

    // A reload the server refuses drops the kept copy, is reported, and leaves the draft as it was.
    {
        await opened();
        edit('mine');
        const reload = failure(provided.reload());
        calls[1].answer(403, null);
        assert.ok(await reload);
        await settle();
        assert.equal(snapshot.recallInvestigation('p'), null);
        assert.deepEqual(shown(), { question: 'mine', status: 'Unsaved changes', dirty: true, revision: 1, loaded: true });
    }
    // So does a first load that is refused.
    {
        await mount();
        snapshot.rememberInvestigation(snapshot.askInvestigation('q'), doc('another project'));
        calls[0].answer(404, null);
        await settle();
        assert.equal(provided.status, 'Could not load investigation');
        assert.equal(snapshot.recallInvestigation('p'), null);
        assert.equal(snapshot.recallInvestigation('q').case.question, 'another project');
    }

    // 10. Denied during the first load, then allowed again on the same mount: asked again, and loaded. The first answer is not used.
    {
        await mount();
        workspace.projectDenied = true;
        flush();
        calls[0].answer(200, doc('asked before the denial'), 1);
        await settle();
        assert.equal(provided.loaded, false);
        workspace.projectDenied = false;
        flush();
        assert.equal(calls.length, 2, 'the investigation is asked for again');
        calls[1].answer(200, doc('asked after'), 1);
        await settle();
        assert.deepEqual(shown(), { question: 'asked after', status: 'Saved', dirty: false, revision: 1, loaded: true });
        // A loaded document with edits is not reloaded when a denial comes and goes.
        edit('unsaved');
        workspace.projectDenied = true; flush();
        workspace.projectDenied = false; flush();
        await settle();
        assert.equal(calls.length, 2);
        assert.equal(provided.document.case.question, 'unsaved');
    }

    // The project's denial is recorded (by any request) while the first load is on its way: that load's answer is not shown.
    {
        await mount();
        snapshot.forgetInvestigation('p');
        calls[0].answer(200, doc('asked before the denial'), 1);
        await settle();
        assert.equal(provided.loaded, false);
        assert.equal(provided.document.case.question, '');
        assert.equal(snapshot.recallInvestigation('p'), null);
    }

    // 11. Another user signs in: the provider starts again empty, and answers asked for by the first user are not shown or kept.
    {
        await opened();
        edit('first user, unsaved');
        const save = provided.save();
        flush();
        const reloadCalls = calls.length;
        snapshot.forgetInvestigations();
        flush();
        assert.deepEqual(shown(), { question: '', status: 'Loading', dirty: false, revision: 0, loaded: false });
        assert.equal(calls.length, reloadCalls + 1, 'the second user\'s investigation is asked for');
        calls[1].answer(200, doc('first user, saved'), 2);
        await save; await settle();
        assert.equal(provided.document.case.question, '');
        assert.equal(snapshot.recallInvestigation('p'), null);
        calls[2].answer(200, doc('second user'), 7);
        await settle();
        assert.deepEqual(shown(), { question: 'second user', status: 'Saved', dirty: false, revision: 7, loaded: true });
    }

    // 12. A viewer cannot edit.
    {
        await opened();
        workspace.project = { role: 'viewer' };
        flush();
        edit('not allowed');
        assert.deepEqual(shown(), { question: 'server 1', status: 'Saved', dirty: false, revision: 1, loaded: true });
    }

    finished = true;
    console.log('investigation provider: ok');
})().catch(error => { console.error(error); process.exit(1); });
