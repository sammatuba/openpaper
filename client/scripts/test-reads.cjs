// Rules for cached reads of a signed-in user's data, exercised on the real TS module.
const ts = require('typescript');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
require.extensions['.ts'] = (m, filename) => m._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename)
const { createReads, isGone } = require(path.resolve(__dirname, '../src/lib/reads.ts'));

const http = (status, message = `HTTP ${status}`) => Object.assign(new Error(message), { status });
const same = body => body;
// A request function whose responses the test settles by hand, in any order.
function manual() {
    const calls = [];
    const request = url => new Promise((resolve, reject) => calls.push({ url, resolve, reject }));
    return { calls, request };
}
const failure = promise => promise.then(() => null, error => error);

(async () => {
    assert.ok(isGone(http(401)) && isGone(http(403)) && isGone(http(404)));
    assert.ok(!isGone(http(500)) && !isGone(new Error('offline')) && !isGone(undefined));

    // Denied, then a network failure: the denial stands. A later success lifts it.
    {
        const { calls, request } = manual();
        const reads = createReads(request);
        const first = reads.read('/p', same); calls[0].resolve({ title: 'kept' });
        assert.deepEqual(await first, { title: 'kept' });
        assert.equal(reads.denied('/p'), null);
        const second = failure(reads.read('/p', same)); calls[1].reject(http(403, 'No access'));
        assert.equal((await second).message, 'No access');
        assert.equal(reads.denied('/p').message, 'No access');
        const third = failure(reads.read('/p', same)); calls[2].reject(http(503));
        await third;
        assert.equal(reads.denied('/p').message, 'No access', 'a network failure after a denial does not lift it');
        const fourth = reads.read('/p', same); calls[3].resolve({ title: 'back' });
        await fourth;
        assert.equal(reads.denied('/p'), null, 'a successful read lifts the denial');
        assert.equal(reads.denied('/other'), null, 'a denial belongs to one resource');
    }

    // A plain failure is not a denial.
    {
        const { calls, request } = manual();
        const reads = createReads(request);
        const read = failure(reads.read('/p', same)); calls[0].reject(http(500));
        await read;
        assert.equal(reads.denied('/p'), null);
    }

    // Sign-out while a prefetch is in flight: its response is not written.
    {
        const { calls, request } = manual();
        const reads = createReads(request);
        const written = [];
        const prefetch = reads.prefetch('/p', same, (url, data) => written.push([url, data]));
        reads.end();
        calls[0].resolve({ title: 'previous user' });
        await prefetch;
        assert.deepEqual(written, [], 'a response that arrives after sign-out is dropped');
        // The same holds for an ordinary read: it rejects instead of returning the old user's data.
        const read = failure(reads.read('/p', same));
        reads.end();
        calls[1].resolve({ title: 'previous user' });
        assert.match((await read).message, /session ended/);
        // And a denial from before sign-out does not carry over.
        const denied = failure(reads.read('/q', same)); calls[2].reject(http(404));
        await denied;
        assert.ok(reads.denied('/q'));
        reads.end();
        assert.equal(reads.denied('/q'), null);
    }

    // A read that begins while a prefetch is in flight joins it: one request, the
    // reader gets the result, and the prefetch does not also write to the cache.
    {
        const { calls, request } = manual();
        const reads = createReads(request);
        const written = [];
        const prefetch = reads.prefetch('/p', same, (url, data) => written.push(data));
        const read = reads.read('/p', same);
        const again = reads.prefetch('/p', same, (url, data) => written.push(data));
        assert.equal(calls.length, 1, 'hover then open is one request');
        calls[0].resolve({ title: 'shared' });
        assert.deepEqual(await read, { title: 'shared' });
        await prefetch; await again;
        assert.deepEqual(written, [], 'a joined prefetch leaves the cache to the reader');
        // Once it has settled, the next read is a fresh request.
        const later = reads.read('/p', same);
        assert.equal(calls.length, 2);
        calls[1].resolve({ title: 'fresh' });
        assert.deepEqual(await later, { title: 'fresh' });
    }

    // A joined prefetch that fails: the reader sees the error, and a denial is recorded once.
    {
        const { calls, request } = manual();
        const reads = createReads(request);
        const written = [];
        const prefetch = reads.prefetch('/p', same, (url, data) => written.push(data));
        const read = failure(reads.read('/p', same));
        calls[0].reject(http(403, 'No access'));
        assert.equal((await read).message, 'No access');
        await prefetch;
        assert.deepEqual(written, []);
        assert.equal(reads.denied('/p').message, 'No access');
    }

    // A prefetch nobody joined: writes once on success, nothing on failure.
    {
        const { calls, request } = manual();
        const reads = createReads(request);
        const written = [];
        const write = (url, data) => written.push(data.title);
        const alone = reads.prefetch('/p', same, write);
        calls[0].resolve({ title: 'prefetched' });
        await alone;
        assert.deepEqual(written, ['prefetched']);
        const failing = reads.prefetch('/p', same, write);
        calls[1].reject(http(500));
        await failing;
        assert.deepEqual(written, ['prefetched'], 'a failed prefetch writes nothing');
        assert.equal(reads.denied('/p'), null);
    }

    // A read already in flight when the prefetch starts is the older one: the
    // prefetch may write, and the older response does not undo a newer denial or success.
    {
        const { calls, request } = manual();
        const reads = createReads(request);
        const written = [];
        const older = reads.read('/p', same);
        const prefetch = reads.prefetch('/p', same, (url, data) => written.push(data.title));
        assert.equal(calls.length, 2, 'a prefetch does not join a read; only the reverse');
        calls[1].resolve({ title: 'newer' });
        await prefetch;
        assert.deepEqual(written, ['newer']);
        calls[0].reject(http(404));
        await failure(older);
        assert.equal(reads.denied('/p'), null, 'an older denial does not override a newer success');
    }

    // After sign-out a read does not join a prefetch from the previous session.
    {
        const { calls, request } = manual();
        const reads = createReads(request);
        const written = [];
        const prefetch = reads.prefetch('/p', same, (url, data) => written.push(data));
        reads.end();
        const read = reads.read('/p', same);
        assert.equal(calls.length, 2, 'the new session makes its own request');
        calls[0].resolve({ title: 'previous user' });
        calls[1].resolve({ title: 'current user' });
        assert.deepEqual(await read, { title: 'current user' });
        await prefetch;
        assert.deepEqual(written, []);
    }

    // A newer success wins over an older denial that arrives late, and the reverse.
    {
        const { calls, request } = manual();
        const reads = createReads(request);
        const older = reads.read('/p', same);
        const newer = failure(reads.read('/p', same));
        calls[1].reject(http(403));
        await newer;
        calls[0].resolve({ title: 'stale' });
        await older;
        assert.ok(reads.denied('/p'), 'an older success does not lift a newer denial');
    }

    // The pick function shapes the body; a body it cannot read is an error, not data.
    {
        const reads = createReads(async () => null);
        assert.deepEqual(await reads.read('/list', body => body || []), []);
        assert.ok(await failure(reads.read('/p', body => body.papers)));
    }

    console.log('reads: ok');
})().catch(error => { console.error(error); process.exit(1); });
