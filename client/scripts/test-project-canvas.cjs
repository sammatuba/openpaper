// Layout of the project canvas, exercised on the real TS module.
const ts = require('typescript');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
require.extensions['.ts'] = (m, filename) => m._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename);
const { projectCanvas, draftEdges, canvasIsEmpty, canvasKey } = require(path.resolve(__dirname, '../src/lib/project-canvas.ts'));

const overlaps = nodes => nodes.some((a, i) => nodes.some((b, j) => i < j && a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h));
const inside = layout => layout.nodes.every(node => node.x >= 0 && node.y >= 0 && node.x + node.w <= layout.width && node.y + node.h <= layout.height);
const of = (layout, kind) => layout.nodes.filter(node => node.kind === kind);
const node = (layout, kind, ref) => layout.nodes.find(item => item.key === canvasKey(kind, ref));
const edge = (layout, kind, from, to) => layout.edges.filter(item => item.kind === kind && item.from === from && item.to === to);
const centre = item => item.y + item.h / 2;
const drafts = (layout, key) => draftEdges(layout, new Map(layout.nodes.map(item => [item.key, item])), key).map(item => `${item.from}>${item.to}`).sort();

const empty = () => ({ format: 'openpaper/investigation', version: 1, case: { question: '', why_it_matters: '', landscape: '', coverage_limits: '', provisional_answer: '', unresolved_tension: '', reconciliation: '', discriminating_experiment: '', update_criteria: '' }, claims: [], findings: [], relations: [], manuscript: { title: '', sections: [] } });
const claim = (id, statement, archived = false) => ({ id, statement, reasoning: '', caveats: '', archived });
const finding = (id, label, source, archived = false) => ({ id, label, observed_result: '', author_interpretation: '', our_interpretation: '', setup: { model: '', task: '', training: '', intervention: '', evaluation: '', other: '' }, limitations: '', source, archived });
const anchored = paper => ({ kind: 'anchored', paper_id: paper, start_line: 1, end_line: 2, quote: 'q', source_sha256: 'a'.repeat(64), quote_sha256: 'b'.repeat(64) });
const relation = (id, claim_id, finding_id, kind) => ({ id, claim_id, finding_id, relation: kind, rationale: '' });
const block = (id, claim_ids, finding_ids) => ({ id, kind: 'paragraph', text: 't', claim_ids, finding_ids, provenance: { kind: 'human' }, dependency_pins: {} });

// Nothing recorded: the view shows a prompt, and the layout is still a valid one-node map.
assert.equal(canvasIsEmpty(empty(), []), true);
assert.equal(canvasIsEmpty(empty(), [{ id: 'p', title: 'P' }]), false);
assert.equal(canvasIsEmpty({ ...empty(), claims: [claim('c', 'x', true)] }, []), true, 'an archived claim is not something to draw');
{
    const layout = projectCanvas(empty(), []);
    assert.equal(layout.nodes.length, 1);
    assert.equal(layout.nodes[0].label, 'No question yet');
    assert.ok(inside(layout));
}

const doc = empty();
doc.case.question = '  Does   control compose?\n';
doc.claims = [claim('c1', 'It composes'), claim('c2', 'It does not'), claim('c3', 'Archived', true), claim('c4', '')];
doc.findings = [
    finding('f1', 'Late finding for c2', anchored('p2')),
    finding('f2', 'Finding for c1', anchored('p1')),
    finding('f3', 'Unlinked', { kind: 'unbound' }),
    finding('f4', 'Archived', anchored('p1'), true),
    finding('f5', 'Paper gone', anchored('missing')),
    finding('f6', 'Redacted', { kind: 'redacted', paper_id: 'p1' }),
];
doc.relations = [
    relation('r1', 'c2', 'f1', 'challenges'),
    relation('r2', 'c1', 'f2', 'supports'),
    relation('r3', 'c1', 'f2', 'qualifies'),
    relation('r4', 'c3', 'f2', 'supports'),
    relation('r5', 'c1', 'f4', 'supports'),
    relation('r6', 'c1', 'f5', 'supports'),
];
doc.manuscript.sections = [
    { id: 's1', title: 'Introduction', blocks: [block('b1', ['c1', 'c3'], ['f2', 'f4']), block('b2', ['c1'], ['f2'])] },
    { id: 's2', title: '', blocks: [] },
];
const papers = [{ id: 'p1', title: 'First paper' }, { id: 'p2', title: 'Second paper' }, { id: 'p3', title: null }];
const layout = projectCanvas(doc, papers);

// One node per shown thing; archived claims and findings are not drawn.
assert.equal(of(layout, 'question').length, 1);
assert.equal(of(layout, 'question')[0].label, 'Does control compose?', 'whitespace is collapsed');
assert.deepEqual(of(layout, 'claim').map(item => item.ref), ['c1', 'c2', 'c4']);
assert.deepEqual(of(layout, 'finding').map(item => item.ref).sort(), ['f1', 'f2', 'f3', 'f5', 'f6']);
assert.deepEqual(of(layout, 'paper').map(item => item.ref), ['p1', 'p2', 'p3']);
assert.deepEqual(of(layout, 'section').map(item => item.ref), ['s1', 's2']);
assert.equal(node(layout, 'claim', 'c4').label, 'Untitled claim');
assert.equal(node(layout, 'paper', 'p3').label, 'Untitled paper');
assert.equal(node(layout, 'section', 's2').label, 'Untitled section');
assert.equal(node(layout, 'claim', 'c2').name, 'Claim 2');
assert.equal(new Set(layout.nodes.map(item => item.key)).size, layout.nodes.length);
assert.equal(new Set(layout.edges.map(item => item.key)).size, layout.edges.length);

// Geometry: nothing overlaps, everything is inside, columns run left to right.
assert.equal(overlaps(layout.nodes), false);
assert.ok(inside(layout));
const column = kind => of(layout, kind)[0].x;
assert.ok(column('question') === column('section') && column('question') < column('claim') && column('claim') < column('finding') && column('finding') < column('paper'));

// Claims and sections keep document order; the sections sit under the question.
assert.ok(node(layout, 'claim', 'c1').y < node(layout, 'claim', 'c2').y && node(layout, 'claim', 'c2').y < node(layout, 'claim', 'c4').y);
assert.ok(of(layout, 'question')[0].y + of(layout, 'question')[0].h < node(layout, 'section', 's1').y && node(layout, 'section', 's1').y < node(layout, 'section', 's2').y);

// A finding sits by its claim, whatever its place in the document; unlinked findings follow the linked ones.
assert.ok(centre(node(layout, 'finding', 'f2')) < centre(node(layout, 'finding', 'f1')), 'f2 bears on the first claim, so it comes first');
for (const linked of ['f1', 'f2', 'f5']) for (const loose of ['f3', 'f6']) assert.ok(node(layout, 'finding', linked).y < node(layout, 'finding', loose).y);
assert.ok(node(layout, 'finding', 'f3').y < node(layout, 'finding', 'f6').y, 'unlinked findings keep document order');
// A paper sits by its findings; one nothing was drawn from comes last.
assert.ok(node(layout, 'paper', 'p1').y < node(layout, 'paper', 'p2').y && node(layout, 'paper', 'p2').y < node(layout, 'paper', 'p3').y);

// Edges only join drawn nodes.
const keys = new Set(layout.nodes.map(item => item.key));
assert.ok(layout.edges.every(item => keys.has(item.from) && keys.has(item.to)));
assert.equal(layout.edges.filter(item => item.kind === 'asks').length, 3, 'the question leads to each shown claim');
assert.equal(edge(layout, 'supports', 'claim:c1', 'finding:f2').length, 1);
assert.equal(edge(layout, 'qualifies', 'claim:c1', 'finding:f2').length, 1);
assert.notEqual(edge(layout, 'supports', 'claim:c1', 'finding:f2')[0].path, edge(layout, 'qualifies', 'claim:c1', 'finding:f2')[0].path, 'two relations between the same pair are drawn apart');
assert.equal(edge(layout, 'challenges', 'claim:c2', 'finding:f1').length, 1);
assert.equal(layout.edges.filter(item => ['supports', 'challenges', 'qualifies'].includes(item.kind)).length, 4, 'relations to archived claims and findings are left out');
assert.deepEqual(layout.edges.filter(item => item.kind === 'source').map(item => `${item.from}>${item.to}`).sort(), ['finding:f1>paper:p2', 'finding:f2>paper:p1'], 'a finding whose paper is not in the project, or whose source is redacted, has no source edge');
// A section's lines to what it cites are built for a selection, not drawn with the rest.
assert.equal(layout.edges.filter(item => item.kind === 'drafts').length, 0);
assert.deepEqual(drafts(layout, 'section:s1'), ['section:s1>claim:c1', 'section:s1>finding:f2'], 'a section cites each claim and finding once, and only shown ones');
assert.deepEqual(drafts(layout, 'section:s2'), []);
assert.deepEqual(drafts(layout, 'claim:c1'), ['section:s1>claim:c1'], 'a cited claim shows the sections that cite it');
assert.deepEqual(drafts(layout, 'finding:f2'), ['section:s1>finding:f2']);
assert.deepEqual(drafts(layout, 'claim:c2'), []);
assert.deepEqual(drafts(layout, 'paper:p1'), []);
assert.deepEqual(drafts(layout, 'nothing'), []);

// Level means level: a node linked to one thing has its centre, one linked to several has their mean.
{
    const level = empty();
    level.claims = [claim('c1', 'a'), claim('c2', 'b'), claim('c3', 'c'), claim('c4', 'd'), claim('c5', 'e')];
    level.findings = [finding('one', 'One claim', anchored('p1')), finding('two', 'Two claims', anchored('p2')), finding('free', 'Unlinked', { kind: 'unbound' })];
    level.relations = [relation('r1', 'c2', 'one', 'supports'), relation('r2', 'c3', 'two', 'supports'), relation('r3', 'c5', 'two', 'challenges')];
    const map = projectCanvas(level, [{ id: 'p2', title: 'P2' }, { id: 'p1', title: 'P1' }, { id: 'p3', title: 'P3' }]);
    assert.equal(centre(node(map, 'finding', 'one')), centre(node(map, 'claim', 'c2')), 'a finding sits level with its one claim');
    assert.equal(centre(node(map, 'finding', 'two')), (centre(node(map, 'claim', 'c3')) + centre(node(map, 'claim', 'c5'))) / 2, 'a finding sits at the mean of its claims');
    assert.equal(centre(node(map, 'finding', 'two')), centre(node(map, 'claim', 'c4')));
    assert.equal(centre(node(map, 'paper', 'p1')), centre(node(map, 'finding', 'one')), 'a paper sits level with its one finding, whatever its place in the list');
    assert.equal(centre(node(map, 'paper', 'p2')), centre(node(map, 'finding', 'two')));
    assert.ok(node(map, 'finding', 'free').y > node(map, 'finding', 'two').y && node(map, 'paper', 'p3').y > node(map, 'paper', 'p2').y, 'unlinked nodes follow');
    // A finding that bears on one claim in two ways and on another in one sits midway between the two claims.
    {
        const twice = empty();
        twice.claims = [claim('c1', 'a'), claim('c2', 'b'), claim('c3', 'c')];
        twice.findings = [finding('f', 'Both', { kind: 'unbound' })];
        twice.relations = [relation('r1', 'c1', 'f', 'supports'), relation('r2', 'c1', 'f', 'qualifies'), relation('r3', 'c3', 'f', 'supports')];
        const placed = projectCanvas(twice, []);
        assert.equal(centre(node(placed, 'finding', 'f')), centre(node(placed, 'claim', 'c2')), 'each claim counts once for placement');
        assert.deepEqual(node(placed, 'claim', 'c1').tally, { supports: 1, challenges: 0, qualifies: 1 }, 'and every relation still counts in the tally');
        assert.equal(placed.edges.filter(item => item.to === 'finding:f' && item.from === 'claim:c1').length, 2);
    }
    // Two findings wanting the same place: the first keeps it, the second goes directly below.
    level.findings.push(finding('also', 'Also c2', { kind: 'unbound' }));
    level.relations.push(relation('r4', 'c2', 'also', 'qualifies'));
    const crowded = projectCanvas(level, []);
    assert.equal(centre(node(crowded, 'finding', 'one')), centre(node(crowded, 'claim', 'c2')));
    assert.equal(node(crowded, 'finding', 'also').y, node(crowded, 'finding', 'one').y + node(crowded, 'finding', 'one').h + 12);
    assert.equal(overlaps(crowded.nodes), false);
}

// A draft that cites everything: the layout stays quick, and the lines are the view's to ration.
{
    const dense = empty();
    dense.claims = Array.from({ length: 100 }, (_, i) => claim(`c${i}`, `Claim ${i}`));
    dense.findings = Array.from({ length: 500 }, (_, i) => finding(`f${i}`, `Finding ${i}`, anchored(`p${i % 300}`)));
    dense.relations = Array.from({ length: 1000 }, (_, i) => relation(`r${i}`, `c${(i * 7) % 100}`, `f${i % 500}`, i < 500 ? 'supports' : 'challenges'));
    dense.manuscript.sections = Array.from({ length: 30 }, (_, i) => ({ id: `s${i}`, title: `Section ${i}`, blocks: [block(`b${i}`, dense.claims.map(item => item.id), dense.findings.map(item => item.id))] }));
    const started = performance.now();
    const result = projectCanvas(dense, Array.from({ length: 300 }, (_, i) => ({ id: `p${i}`, title: `Paper ${i}` })));
    const took = performance.now() - started;
    assert.equal(result.edges.length, 100 + 1000 + 500, 'the lines always drawn do not grow with the draft');
    assert.equal([...result.cites.values()].reduce((sum, cited) => sum + cited.size, 0), 30 * 600);
    assert.equal(drafts(result, 'section:s0').length, 100, 'a section gets lines to the first hundred things it cites');
    assert.equal(drafts(result, 'section:s0')[0], 'section:s0>claim:c0');
    assert.equal(drafts(result, 'claim:c0').length, 30);
    assert.ok(took < 250, `layout of the densest canvas took ${took.toFixed(1)} ms`);
    console.log(`project canvas: densest layout ${result.nodes.length} nodes, ${result.edges.length} edges, 18000 citations in ${took.toFixed(1)} ms`);
}

// A claim counts the shown findings that bear on it.
assert.deepEqual(node(layout, 'claim', 'c1').tally, { supports: 2, challenges: 0, qualifies: 1 });
assert.deepEqual(node(layout, 'claim', 'c2').tally, { supports: 0, challenges: 1, qualifies: 0 });
assert.equal(node(layout, 'finding', 'f1').tally, null);

// Long text is cut for the node; the document is not changed.
{
    const long = empty();
    long.claims = [claim('c', 'word '.repeat(100))];
    const before = JSON.stringify(long);
    const label = node(projectCanvas(long, []), 'claim', 'c').label;
    assert.ok(label.length <= 200 && label.endsWith('…'));
    assert.equal(JSON.stringify(long), before);
}

// The same input always gives the same map.
assert.deepEqual(projectCanvas(doc, papers), layout);

// The format's maximum, with 300 papers: still no overlap, and quick.
{
    const big = empty();
    big.case.question = 'Q';
    big.claims = Array.from({ length: 100 }, (_, i) => claim(`c${i}`, `Claim ${i}`));
    big.findings = Array.from({ length: 500 }, (_, i) => finding(`f${i}`, `Finding ${i}`, anchored(`p${i % 300}`)));
    big.relations = Array.from({ length: 1000 }, (_, i) => relation(`r${i}`, `c${(i * 7) % 100}`, `f${i % 500}`, i < 500 ? 'supports' : 'challenges'));
    big.manuscript.sections = Array.from({ length: 30 }, (_, i) => ({ id: `s${i}`, title: `Section ${i}`, blocks: [block(`b${i}`, [`c${i}`], [`f${i}`, `f${i + 30}`])] }));
    const many = Array.from({ length: 300 }, (_, i) => ({ id: `p${i}`, title: `Paper ${i}` }));
    const started = performance.now();
    const result = projectCanvas(big, many);
    const took = performance.now() - started;
    assert.equal(result.nodes.length, 1 + 30 + 100 + 500 + 300);
    assert.ok(inside(result));
    for (const kind of ['claim', 'finding', 'paper', 'section']) assert.equal(overlaps(of(result, kind)), false);
    assert.ok(took < 250, `layout of the largest canvas took ${took.toFixed(1)} ms`);
    console.log(`project canvas: largest layout ${result.nodes.length} nodes, ${result.edges.length} edges in ${took.toFixed(1)} ms`);
}

console.log('project canvas layout: ok');
