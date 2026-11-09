// Exercise the real TS module using the already installed TypeScript compiler.
const ts = require('typescript');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const Module = require('node:module');
const path = require('node:path');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const Markdown = require('react-markdown').default;
const filename = path.resolve(__dirname, '../src/lib/textfold.ts');
const m = new Module(filename, module);
m.filename = filename;
m.paths = Module._nodeModulePaths(path.dirname(filename));
m._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename);
const { foldMarkdown, parseTextFold, serializeTextFold, normalizeProjectMarkdown, foldText, markdownReferences } = m.exports;
const source = '# The question\nDoes control compose?\n\n## Evidence for\nA result was observed. A caveat remains. Another detail matters.\n\n## Evidence against\nA matched run found no effect.\n\n## Experiment\n```python\n# not a section\n\nx = 1\n```\n\n[Source](https://example.org/paper)';
const doc = foldMarkdown(source, 'Research', 'project-1');
assert.equal(doc.sections.length, 4);
assert.equal(doc.source_text, source);
assert.equal(doc.provenance.ai_generated, false);
assert.equal(doc.provenance.local, true);
assert.deepEqual(parseTextFold(doc), doc);
const u = doc.sections[1].units[0];
assert.equal(foldText(u, 'takeaway'), 'A result was observed.');
assert.equal(foldText(u, 'key'), 'A result was observed. A caveat remains.');
assert.equal(foldText(u, 'brief'), 'A result was observed. A caveat remains.');
assert.equal(foldText(u, 'full'), 'A result was observed. A caveat remains. Another detail matters.');
assert.equal(doc.sections[3].units[0].full, '```python\n# not a section\n\nx = 1\n```');
assert.match(doc.sections[3].units[1].full, /https:\/\/example.org\/paper/);
assert.equal(normalizeProjectMarkdown('Intro ## Evidence for\nA finding. ## Evidence against\nA null result.'), 'Intro\n\n## Evidence for\nA finding.\n\n## Evidence against\nA null result.');
assert.equal(foldMarkdown('', 'Empty', 'empty').sections.length, 1);
assert.equal(foldMarkdown('## Evidence\nUse `x ## y` as the literal control.', 'Test', 'test').sections.length, 1);
assert.equal(foldMarkdown('## Evidence\nA [label ## with hashes](https://example.org) stays intact.', 'Test', 'test').sections.length, 1);
assert.equal(foldMarkdown('## Evidence\n````\n```\nx ## y\n```\n````', 'Test', 'test').sections.length, 1);
const render = text => renderToStaticMarkup(React.createElement(Markdown, {children:text}));
const primaryLink = html => html.match(/<a [^>]+>primary<\/a>/)?.[0];
for (const definition of ['[paper]: https://example.org/source', '[paper]:\nhttps://example.org/source', '> [paper]: https://example.org/source', '[paper]:\n  https://example.org/source\n  "A source title"', '[paper]: https://example.org/?q=&amp;copy; "Literal &amp;amp;"']) {
    const source = `Finding [primary][paper].\n\n${definition}`;
    const refs = markdownReferences(foldMarkdown(source, 'Test', 'test'));
    assert.ok(primaryLink(render(source)), 'fixture should render a primary citation');
    assert.equal(primaryLink(render(`Finding [primary][paper].\n\n${refs}`)), primaryLink(render(source)), 'fold must preserve actual URL and title');
}
assert.equal(markdownReferences(foldMarkdown('~~~\n[not-a-ref]: fake\n~~~', 'Test', 'test')), '');
for (const edit of [d => d.version = 1, d => d.sections[0].id = d.sections[1].id,
    d => d.sections[1].units[0].brief = ['Invented quote'], d => d.sections[1].units[0].evidence = [-1],
    d => d.sections[1].units[0].sentences = ['Not in source'], d => d.links = [{from:'bad',to:'S1',rel:'supports'}]]) {
    const d = structuredClone(doc); edit(d); assert.throws(() => parseTextFold(d));
}
const unsupported = structuredClone(doc);
Object.assign(unsupported.sections[1].units[0], {full:'',sentences:[],evidence:[],brief:[]});
assert.throws(() => parseTextFold(unsupported));
assert.doesNotThrow(() => parseTextFold({...doc, extra:'文'.repeat(200_000)}));
const large = foldMarkdown(`## Evidence\n${'A'.repeat(139)}.`, 'Test', 'test');
large.sections[0].units = Array.from({length:1000}, (_,i) => ({...large.sections[0].units[0],id:`u${i}`}));
assert.ok(Buffer.byteLength(JSON.stringify(large,null,2)) > 1_000_000, 'fixture must reproduce pretty-export overflow');
const exported = serializeTextFold(large);
assert.ok(Buffer.byteLength(exported) <= 1_000_000);
assert.deepEqual(parseTextFold(JSON.parse(exported)), large);
const ai = structuredClone(doc);
ai.written = ['topic', 'takeaway', 'key']; ai.provenance = {ai_generated:true, local:false, model:'test', extension:'retained'};
ai.extra = {keep:true}; ai.links = [{from:'S2.p1', to:'S3.p1', rel:'qualifies'}];
assert.deepEqual(parseTextFold(JSON.parse(JSON.stringify(ai))), ai);
assert.throws(() => parseTextFold({...doc, extra:'x'.repeat(1_000_001)}));
console.log('Textfold: parser, five levels, source fidelity, fences, flattened headings, provenance, roundtrip and rejection checks passed');
