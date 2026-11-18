// Level projection of the native folded reader, exercised on the real TS modules.
const ts = require('typescript');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
// Compile the real TS modules on require, including their relative imports.
require.extensions['.ts'] = (m, filename) => m._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename);
const load = relative => require(path.resolve(__dirname, relative));
const { investigationPreview } = load('../src/lib/investigation-preview.ts');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const Markdown = require('react-markdown').default;
const remarkGfm = require('remark-gfm').default;
const { foldMarkdown } = load('../src/lib/textfold.ts');
const { unitView, nextStep, isProse, linksFrom, provenanceLine, foldContext, withReferences, LEVEL_ORDER } = load('../src/lib/fold-view.ts');
const render = text => renderToStaticMarkup(React.createElement(Markdown, { remarkPlugins: [remarkGfm] }, text));

const doc = foldMarkdown('# Question\nDoes control compose?\n\n## Evidence\nA result was observed. A caveat remains. Another detail matters.\n\n```python\nx = 1\n```\n\n- one item. second sentence.\n\n| a | b |\n| - | - |\n| 1 | 2 |', 'Test', 'test');
const prose = doc.sections[1].units[0];
assert.deepEqual(LEVEL_ORDER, ['topic', 'takeaway', 'key', 'brief', 'full']);

// Each level shows its own text; Brief and Full are source wording.
assert.deepEqual(unitView(prose, 'topic'), { level: 'topic', source: false, markdown: prose.topic });
assert.deepEqual(unitView(prose, 'takeaway'), { level: 'takeaway', source: false, markdown: 'A result was observed.' });
assert.deepEqual(unitView(prose, 'key'), { level: 'key', source: false, markdown: 'A result was observed. A caveat remains.' });
assert.deepEqual(unitView(prose, 'brief'), { level: 'brief', source: true, markdown: prose.brief.join(' ') });
assert.deepEqual(unitView(prose, 'full'), { level: 'full', source: true, markdown: prose.full });

// An empty summary falls through to the next fuller level that has text.
const sparse = { ...prose, topic: '  ', takeaway: '' };
assert.equal(unitView(sparse, 'topic').level, 'key');
assert.equal(unitView({ ...sparse, key: '' }, 'topic').level, 'brief');
assert.equal(unitView({ ...sparse, key: '', brief: [], evidence: [] }, 'takeaway').level, 'full');
// Fields outside the format never reach the page as text.
assert.equal(unitView({ ...prose, key: { toString: () => 'x' } }, 'key').level, 'brief');

// Non-prose blocks show Full at Brief.
for (const unit of doc.sections[1].units.slice(1)) {
    assert.equal(isProse(unit), false, unit.full);
    assert.deepEqual(unitView(unit, 'brief'), { level: 'full', source: true, markdown: unit.full });
}
assert.equal(isProse(prose), true);
assert.equal(isProse({ full: 'A sentence with a - dash and 3. not a list.' }), true);
assert.equal(isProse({ full: '> quoted' }), false);
// A GFM table without outer pipes is still a table.
const bare = { ...prose, full: 'a | b\n- | -\n1 | 2', sentences: ['a | b'], evidence: [0], brief: ['a | b'] };
assert.equal(isProse(bare), false);
assert.deepEqual(unitView(bare, 'brief'), { level: 'full', source: true, markdown: bare.full });
assert.equal(isProse({ full: '    indented code' }), false);
assert.equal(isProse({ full: '<div>raw</div>' }), false);

// Opening a paragraph: summary → source sentences → full text; non-prose skips Brief.
assert.equal(nextStep(prose, 'topic'), 'brief');
assert.equal(nextStep(prose, 'key'), 'brief');
assert.equal(nextStep(prose, 'brief'), 'full');
assert.equal(nextStep(prose, 'full'), null);
assert.equal(nextStep(doc.sections[1].units[1], 'key'), 'full');

// Argument links resolve to readable targets; dangling links are ignored.
const linked = structuredClone(doc);
linked.links = [
    { from: 'S2.p1', to: 'S1.p1', rel: 'builds_on' },
    { from: 'S2.p1', to: 'S1', rel: 'supports' },
    { from: 'S2.p1', to: 'missing', rel: 'supports' },
    { from: 'missing', to: 'S1', rel: 'supports' },
];
const links = linksFrom(linked);
assert.deepEqual([...links.keys()], ['S2.p1']);
assert.deepEqual(links.get('S2.p1'), [
    { rel: 'builds on', to: 'S1.p1', title: linked.sections[0].units[0].topic },
    { rel: 'supports', to: 'S1', title: 'Question' },
]);
assert.equal(linksFrom({ ...doc, links: undefined }).size, 0);

// References and footnotes are resolved in document context, per paragraph.
const cited = foldMarkdown([
    'See [the paper][r] and [again][R].',
    '[r]: https://first.example "First"',
    '[r]: https://second.example\nA local duplicate does not win: [dup][r].',
    'A claim with a note.[^n] No definitions needed here: [plain] text.',
    '[^n]: The note cites [the paper][r].',
    '```\nunclosed [r] fence',
].join('\n\n'), 'Cited', 'cited');
const [uses, defines, duplicate, noted, note, fence] = cited.sections[0].units;
const context = foldContext(cited);
assert.deepEqual([...context.silent], [defines.id, note.id], 'definition-only paragraphs render no words');
assert.deepEqual([...context.definitions.keys()], ['r']);
assert.equal((render(withReferences(context, uses.full)).match(/href="https:\/\/first\.example" title="First"/g) || []).length, 2, 'both labels resolve, case-insensitively');
assert.match(render(withReferences(context, duplicate.full)), /href="https:\/\/first\.example"/, 'the first definition in the document wins');
assert.doesNotMatch(render(withReferences(context, duplicate.full)), /second\.example/);
const notedHtml = render(withReferences(context, noted.full));
assert.match(notedHtml, /The note cites <a href="https:\/\/first\.example"/, 'a footnote defined in another paragraph renders with its own citation');
assert.match(notedHtml, /\[plain\] text/);
const fenceHtml = render(withReferences(context, fence.full));
assert.match(fenceHtml, /<code>unclosed \[r\] fence\n?<\/code>/, 'an unclosed fence shows only its own text');
assert.doesNotMatch(fenceHtml, /first\.example/);
assert.equal(withReferences(context, 'No labels here.'), 'No labels here.');
assert.equal(withReferences(foldContext(doc), prose.full), prose.full);
// Labels match as written: entities, backslash escapes and escaped brackets.
const labels = foldMarkdown([
    'See [AT&T][at&t], [entity][a&amp;b], [star][a\\*b] and [bracket][a\\]b].',
    '[at&t]: https://att.example',
    '[a&amp;b]: https://entity.example',
    '[a\\*b]: https://star.example',
    '[a\\]b]: https://bracket.example',
].join('\n\n'), 'Labels', 'labels');
const labelHtml = render(withReferences(foldContext(labels), labels.sections[0].units[0].full));
for (const host of ['att', 'entity', 'star', 'bracket']) assert.match(labelHtml, new RegExp(`href="https://${host}\\.example"`), host);
assert.equal(labelHtml, render(labels.sections[0].units.map(unit => unit.full).join('\n\n')), 'same as rendering the whole document');

// A footnote label inside code is not a citation: the paragraph renders exactly as written.
const coded = foldMarkdown('Claim.[^n]\n\n[^n]: The note.\n\n    x = data[^n]\n    y = 2\n\nInline `[^n]` only.', 'Code', 'code');
const codedContext = foldContext(coded);
const [, , indented, inline] = coded.sections[0].units;
assert.equal(withReferences(codedContext, indented.full), indented.full);
assert.match(render(withReferences(codedContext, indented.full)), /<pre><code>x = data\[\^n\]\ny = 2\n?<\/code><\/pre>/);
assert.equal(withReferences(codedContext, inline.full), inline.full);
// A footnote cited before an unclosed fence would be swallowed by it, so it is not added.
assert.equal(withReferences(codedContext, 'Claim.[^n]\n\n```\nopen'), 'Claim.[^n]\n\n```\nopen');
// A footnote nested in a quotation is left to its own paragraph.
const nested = foldMarkdown('Cited.[^q]\n\n> [^q]: first line\n> second line', 'Nested', 'nested');
assert.equal(foldContext(nested).footnotes.size, 0);
assert.equal(withReferences(foldContext(nested), nested.sections[0].units[0].full), nested.sections[0].units[0].full);

// A definition whose label wraps inside a quotation is shared without the quote's line prefix.
const wrapped = foldMarkdown('See [Smith\nJones] here.\n\n> [Smith\n> Jones]: https://sj.example\n> quoted words', 'Wrapped', 'wrapped');
const wrappedHtml = render(withReferences(foldContext(wrapped), wrapped.sections[0].units[0].full));
assert.equal(wrappedHtml, '<p>See <a href="https://sj.example">Smith\nJones</a> here.</p>');

// Summaries taken from the source keep their citations too.
assert.match(render(withReferences(context, unitView(uses, 'takeaway').markdown)), /href="https:\/\/first\.example"/);

// Draft preview: attribution and findings are fields, never prose; a cited
// finding that no longer exists stays visible.
const investigation = {
    case: {}, findings: [{ id: 'f1', label: 'Signalled fixture', source: { kind: 'anchored', quote: 'Q.' } }, { id: 'f2', label: 'Heading quote', source: { kind: 'anchored', quote: '# Heading only' } }],
    manuscript: { sections: [{ id: 's', title: 'Intro', blocks: [
        { id: 'b1', kind: 'paragraph', text: 'Para one.', finding_ids: ['f1', 'gone'], provenance: { kind: 'assistant' }, dependency_pins: {} },
        { id: 'b2', kind: 'source_quote', text: '', finding_ids: ['f1'], provenance: { kind: 'human' }, dependency_pins: {} },
        { id: 'b3', kind: 'source_quote', text: '', finding_ids: ['f2'], provenance: { kind: 'human' }, dependency_pins: {} },
        { id: 'b4', kind: 'gap', text: '', finding_ids: ['f1'], provenance: { kind: 'human' }, dependency_pins: {} },
        { id: 'b5', kind: 'paragraph', text: '# Dose\nTake one daily.\n\nSecond paragraph.', finding_ids: ['f1'], provenance: { kind: 'human' }, dependency_pins: {} },
    ] }] },
};
const draft = investigationPreview(investigation, 'draft', 'p1');
const [first, quoted, heading, gap, dose, second] = draft.sections[0].units;
assert.equal(draft.sections[0].units.length, 6);
assert.equal(first.full, 'Para one.');
assert.equal(first.attribution, 'AI-authored prose — human review required');
assert.deepEqual(first.findings, [{ id: 'f1', label: 'Signalled fixture' }, { id: 'gone', label: 'unavailable (gone)' }]);
assert.equal(quoted.full, 'Q.');
assert.equal(quoted.attribution, 'Exact source quotation — captured version');
assert.equal(heading.full, '# Heading only', 'a quotation that is only a heading keeps its text');
assert.equal(heading.attribution, 'Exact source quotation — captured version');
assert.deepEqual([gap.full, gap.attribution, gap.findings], ['', 'Evidence gap', [{ id: 'f1', label: 'Signalled fixture' }]], 'an empty gap keeps its label and citation');
assert.equal(unitView(gap, 'topic').level, 'full');
assert.equal(dose.full, '# Dose\nTake one daily.', 'a heading inside a paragraph stays in its text');
assert.deepEqual([dose.attribution, dose.findings, second.attribution, second.findings], ['Human-authored prose', [], '', [{ id: 'f1', label: 'Signalled fixture' }]], 'a block is labelled once and cited once');
assert.equal(draft.sections.length, 1, 'block headings do not become manuscript sections');
assert.equal(draft.provenance.ai_generated, true);

// Origin of the summaries is always stated.
assert.match(provenanceLine(doc), /^Local excerpts · first sentences, no new assessment\. Full and Brief preserve source wording\.$/);
assert.match(provenanceLine({ ...doc, provenance: { ai_generated: true, local: false, model: 'm1' } }), /^AI-written summaries · m1\./);
assert.match(provenanceLine({ ...doc, provenance: { ai_generated: false, local: false } }), /^Provided reading levels\./);
console.log('Fold view: five levels, fall-through, non-prose, opening steps, document-context references and footnotes, links, draft blocks and provenance checks passed');
