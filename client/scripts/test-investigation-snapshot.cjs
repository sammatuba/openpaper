// The kept copy of a saved investigation: whose it is and when it is dropped.
const ts = require('typescript');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
require.extensions['.ts'] = (m, filename) => m._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename);
const snapshot = require(path.resolve(__dirname, '../src/lib/investigation-snapshot.ts'));
const { askInvestigation: ask, answerIsCurrent, answerStands, subscribeInvestigationSnapshots, rememberInvestigation: remember, denyInvestigation: deny, recallInvestigation: recall, forgetInvestigation, forgetInvestigations, investigationSession, subscribeInvestigationSession } = snapshot;

const doc = name => ({ name });
const keep = (project, name) => remember(ask(project), doc(name));

// Kept per project, replaced by a later answer.
assert.equal(recall('a'), null);
keep('a', 'a1');
keep('b', 'b1');
assert.deepEqual(recall('a'), doc('a1'));
keep('a', 'a2');
assert.deepEqual(recall('a'), doc('a2'));
assert.deepEqual(recall('b'), doc('b1'));

// Of two requests for one project, the one that started later decides, for the copy and for whoever shows the answer.
{
    const first = ask('a'), second = ask('a');
    assert.equal(answerStands(first), true);
    assert.equal(remember(second, doc('newer')), true);
    assert.equal(answerStands(first), false, 'the older answer no longer stands');
    assert.equal(answerStands(second), true);
    assert.equal(remember(first, doc('older')), false, 'and is reported as not to be shown');
    assert.deepEqual(recall('a'), doc('newer'), 'an older answer does not replace a newer one');
}
// A refusal removes the copy, and an answer asked for before it does not bring it back.
{
    const slow = ask('a'), refused = ask('a');
    deny(refused);
    assert.equal(recall('a'), null);
    remember(slow, doc('restored'));
    assert.equal(recall('a'), null, 'a success that started before the refusal is not kept');
    assert.deepEqual(recall('b'), doc('b1'), 'other projects stay');
}
// A refusal that started before a later success does not remove it.
{
    const refused = ask('a'), later = ask('a');
    remember(later, doc('a3'));
    deny(refused);
    assert.deepEqual(recall('a'), doc('a3'));
}
// The project itself is denied: nothing already under way may bring its copy back, a later request may.
{
    const underWay = ask('a');
    forgetInvestigation('a');
    assert.equal(recall('a'), null);
    remember(underWay, doc('late'));
    assert.equal(recall('a'), null);
    keep('a', 'a4');
    assert.deepEqual(recall('a'), doc('a4'));
}

// A view drawing a kept copy is told when it is replaced or dropped, and only then.
{
    let told = 0;
    const stop = subscribeInvestigationSnapshots(() => { told += 1; });
    keep('watched', 'w1');
    assert.equal(told, 1);
    const old = ask('watched'), refusal = ask('watched');
    deny(refusal);
    assert.equal(told, 2, 'a refusal that drops the copy tells the view');
    assert.equal(recall('watched'), null);
    remember(old, doc('late'));
    deny(ask('watched'));
    assert.equal(told, 2, 'nothing changed, nothing told');
    keep('watched', 'w2');
    forgetInvestigation('watched');
    assert.equal(told, 4);
    forgetInvestigations();
    assert.equal(told, 5, 'sign-out tells the view');
    stop();
    keep('watched', 'w3');
    assert.equal(told, 5);
}

// Sign-out empties everything, tells whoever is listening, and answers asked for before it are not kept or current.
{
    let told = 0;
    const stop = subscribeInvestigationSession(() => { told += 1; });
    const before = investigationSession(), asked = ask('b'), refused = ask('a');
    assert.equal(answerIsCurrent(asked), true);
    forgetInvestigations();
    assert.equal(told, 1);
    assert.equal(investigationSession(), before + 1);
    assert.equal(answerIsCurrent(asked), false);
    assert.equal(recall('a'), null);
    assert.equal(recall('b'), null);
    remember(asked, doc('late'));
    assert.equal(recall('b'), null, 'a response from the earlier session does not reach the next user');
    keep('a', 'next user');
    deny(refused);
    assert.deepEqual(recall('a'), doc('next user'), 'a refusal from the earlier session does not remove the next user\'s copy');
    stop();
    forgetInvestigations();
    assert.equal(told, 1, 'a listener that left is not told');
}

// Only the most recently used few are kept.
for (let i = 0; i < 12; i++) keep(`p${i}`, `p${i}`);
assert.equal(recall('p0'), null);
assert.equal(recall('p3'), null);
assert.deepEqual(recall('p4'), doc('p4'));
assert.deepEqual(recall('p11'), doc('p11'));
keep('p4', 'p4 again');
keep('new', 'new');
assert.deepEqual(recall('p4'), doc('p4 again'), 'using a project again keeps it');
assert.equal(recall('p5'), null);

console.log('investigation snapshot: ok');
