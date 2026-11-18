// Layout of the folded reader's map, exercised on the real TS modules.
const ts = require('typescript');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
require.extensions['.ts'] = (m, filename) => m._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename);
const load = relative => require(path.resolve(__dirname, relative));
const { foldMarkdown } = load('../src/lib/textfold.ts');
const { foldContext, plainText } = load('../src/lib/fold-view.ts');
const { foldMap, initiallyCollapsed } = load('../src/lib/fold-map.ts');

const overlaps = nodes => nodes.some((a, i) => nodes.some((b, j) => i < j && a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h));
const inside = layout => layout.nodes.every(node => node.x >= 0 && node.y >= 0 && node.x + node.w <= layout.width && node.y + node.h <= layout.height);
const of = (layout, kind) => layout.nodes.filter(node => node.kind === kind);
const options = (doc, extra = {}) => ({ level: 'takeaway', collapsed: new Set(), context: foldContext(doc), findings: false, ...extra });

// Markdown becomes words only: no syntax, no markup, no reference definitions.
assert.equal(plainText('A **bold** [link](https://x.example) and `code`.\n\n[r]: https://y.example'), 'A bold link and code.');
assert.equal(plainText('<img src=x onerror=alert(1)> ![chart](c.png) text'), 'chart text');

const doc = foldMarkdown('# Question\nDoes control compose? It may not.\n\n## Evidence\nA result was observed in [the paper][p]. A caveat remains.\n\nA second result.\n\n### Detail\nNested paragraph.\n\n## Limits\nCoverage is partial.\n\n[p]: https://example.org', 'Test brief', 'test');
const layout = foldMap(doc, options(doc));

// One root, every section, every paragraph that has words; each hangs from its parent.
assert.equal(of(layout, 'root').length, 1);
assert.equal(of(layout, 'root')[0].label, 'Test brief');
assert.equal(of(layout, 'section').length, doc.sections.length);
const worded = doc.sections.flatMap(section => section.units).filter(unit => !foldContext(doc).silent.has(unit.id));
assert.equal(of(layout, 'unit').length, worded.length, 'a paragraph that only defines references is not on the map');
assert.equal(layout.edges.filter(edge => edge.kind === 'tree').length, layout.nodes.length - 1);
assert.equal(overlaps(layout.nodes), false);
assert.equal(inside(layout), true);
assert.equal(of(layout, 'unit').some(node => /\[|\]|\*|https:/.test(node.label)), false, 'node text is plain');

// Depth becomes columns: a subsection sits to the right of its parent section.
const section = title => layout.nodes.find(node => node.kind === 'section' && node.label === title);
assert.ok(section('Detail').x > section('Evidence').x && section('Evidence').x > section('Question').x);
assert.ok(layout.edges.some(edge => edge.kind === 'tree' && edge.from === section('Evidence').key && edge.to === section('Detail').key));
// A parent sits within the vertical span of its children.
const kids = layout.edges.filter(edge => edge.from === section('Evidence').key).map(edge => layout.nodes.find(node => node.key === edge.to));
assert.ok(section('Evidence').y >= Math.min(...kids.map(node => node.y)) && section('Evidence').y <= Math.max(...kids.map(node => node.y)));

// Topic shows the short label; fuller levels show the takeaway.
const evidenceUnit = doc.sections.find(item => item.title === 'Evidence').units[0];
assert.equal(of(foldMap(doc, options(doc, { level: 'full' })), 'unit').find(node => node.ref === evidenceUnit.id).label, 'A result was observed in the paper.');
assert.equal(of(foldMap(doc, options(doc, { level: 'topic' })), 'unit').find(node => node.ref === evidenceUnit.id).label, plainText(evidenceUnit.topic));

// Folding a section removes its paragraphs and its subsections, and keeps its own node.
const evidenceId = doc.sections.find(item => item.title === 'Evidence').id;
const folded = foldMap(doc, options(doc, { collapsed: new Set([evidenceId]) }));
assert.equal(folded.nodes.some(node => node.label === 'Detail'), false);
assert.equal(folded.nodes.find(node => node.ref === evidenceId).collapsed, true);
assert.equal(folded.nodes.find(node => node.ref === evidenceId).children, 3, 'two paragraphs and one subsection');
assert.ok(folded.height < layout.height);
assert.equal(overlaps(folded.nodes), false);

// Argument links are edges of their own; unknown ends are dropped, folded ends land on the nearest shown section.
const limitsUnit = doc.sections.find(item => item.title === 'Limits').units[0];
const linked = { ...doc, links: [
    { from: evidenceUnit.id, to: limitsUnit.id, rel: 'qualified_by' },
    { from: doc.sections[0].id, to: evidenceId, rel: 'supports' },
    { from: evidenceUnit.id, to: 'missing', rel: 'supports' },
    { from: evidenceUnit.id, to: evidenceUnit.id, rel: 'self' },
] };
const withLinks = foldMap(linked, options(linked));
const linkEdges = withLinks.edges.filter(edge => edge.kind === 'link');
assert.deepEqual(linkEdges.map(edge => edge.rel), ['qualified by', 'supports']);
assert.equal(linkEdges[0].from, `unit:${evidenceUnit.id}`);
assert.equal(linkEdges.every(edge => /^M[-\d.]+,[-\d.]+ C/.test(edge.path) && !/NaN/.test(edge.path)), true);
assert.equal(inside(withLinks), true);
const linkFolded = foldMap(linked, options(linked, { collapsed: new Set([evidenceId]) })).edges.filter(edge => edge.kind === 'link');
assert.equal(linkFolded[0].from, `section:${evidenceId}`, 'a link from a folded paragraph starts at its section');
assert.equal(linkFolded.length, 2);
const sibling = { ...doc, links: [{ from: evidenceUnit.id, to: doc.sections.find(item => item.title === 'Evidence').units[1].id, rel: 'supports' }] };
assert.equal(foldMap(sibling, options(sibling)).edges.filter(edge => edge.kind === 'link').length, 1, 'a link between two paragraphs of one section bows around them');
assert.equal(foldMap(sibling, options(sibling, { collapsed: new Set([evidenceId]) })).edges.filter(edge => edge.kind === 'link').length, 0, 'a link whose two ends fold into the same node is not drawn');

// Findings are shared nodes: two paragraphs citing one finding meet at one node.
const cited = structuredClone(doc);
const [first, second] = cited.sections.find(item => item.title === 'Evidence').units;
first.findings = [{ id: 'f1', label: 'Finding one' }, { id: 'f2', label: 'Finding two' }, null, { id: {}, label: 'bad' }];
second.findings = [{ id: 'f1', label: 'Finding one' }];
const graph = foldMap(cited, options(cited, { findings: true }));
assert.deepEqual(of(graph, 'finding').map(node => node.label).sort(), ['Finding one', 'Finding two']);
assert.equal(graph.edges.filter(edge => edge.kind === 'cites').length, 3);
assert.equal(graph.edges.filter(edge => edge.kind === 'cites' && edge.to === 'finding:f1').length, 2, 'a shared finding has two parents');
assert.ok(of(graph, 'finding').every(node => node.x > Math.max(...of(graph, 'unit').map(unit => unit.x))), 'findings sit in their own column');
assert.equal(overlaps(graph.nodes), false);
assert.equal(inside(graph), true);
assert.equal(of(foldMap(cited, options(cited)), 'finding').length, 0, 'findings are drawn only when asked for');
assert.equal(of(foldMap(cited, options(cited, { findings: true, collapsed: new Set(cited.sections.map(item => item.id)) })), 'finding').length, 0, 'folded paragraphs take their findings with them');

// Degenerate documents still lay out.
const empty = foldMap({ ...doc, title: ' ', sections: [] }, options(doc));
assert.equal(empty.nodes.length, 1);
assert.equal(empty.nodes[0].label, 'Untitled');
assert.ok(empty.width > 0 && empty.height > 0);
const hostileIds = { ...doc, sections: [{ ...doc.sections[0], id: '__proto__', units: [{ ...doc.sections[0].units[0], id: 'constructor' }] }], links: [{ from: 'constructor', to: '__proto__', rel: 'x' }] };
assert.equal(foldMap(hostileIds, options(hostileIds)).edges.filter(edge => edge.kind === 'link').length, 1);

// Large documents open folded and lay out quickly.
const large = { ...doc, links: [], sections: Array.from({ length: 50 }, (_, i) => ({ id: `s${i}`, title: `Section ${i}`, depth: 1, topic: '', takeaway: '', units: Array.from({ length: 4 }, (_, j) => ({ ...evidenceUnit, id: `s${i}.${j}` })) })) };
assert.equal(initiallyCollapsed(large).size, 50);
assert.equal(initiallyCollapsed(doc).size, 0);
const started = Date.now();
const big = foldMap(large, options(large));
assert.equal(of(big, 'unit').length, 200);
assert.equal(overlaps(big.nodes), false);
assert.ok(Date.now() - started < 2000);
console.log('Fold map: tree layout, columns by depth, folding, argument links, shared findings, plain node text, degenerate and large documents passed');
