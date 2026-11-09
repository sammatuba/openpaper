import { z } from 'zod';
import { unified } from 'unified';
import remarkParse from 'remark-parse';
import { toMarkdown } from 'mdast-util-to-markdown';
import type { Definition, Nodes } from 'mdast';
import type { FoldLevel, Project, TextFoldDocument, TextFoldSection, TextFoldUnit } from './schema';

// Native reader of the public Textfold v0 format; no standalone server needed.
// https://github.com/chenxiachan/textfold/blob/main/docs/format.md
export const FOLD_LEVELS: FoldLevel[] = ['topic', 'takeaway', 'key', 'brief', 'full'];
const text = z.string().max(100_000);
const id = z.string().min(1).max(200);
const level = z.enum(['topic', 'takeaway', 'key', 'brief', 'full']);
const unit = z.object({
    id, kind: text.default('paragraph'), full: text,
    sentences: z.array(text).max(1000), evidence: z.array(z.number().int()).max(1000),
    brief: z.array(text).max(1000), key: text, takeaway: text, topic: text,
}).passthrough().superRefine((u, ctx) => {
    let cursor = 0;
    for (const sentence of u.sentences) {
        const at = u.full.indexOf(sentence, cursor);
        if (!sentence || at < 0) ctx.addIssue({ code: 'custom', message: 'Source sentences must occur verbatim and in order in Full.' });
        cursor = at + sentence.length;
    }
    if ((!u.sentences.length && u.full.trim()) ||
        ((u.key || u.takeaway || u.topic) && !u.evidence.length) ||
        u.evidence.some(i => i < 0 || i >= u.sentences.length) ||
        JSON.stringify(u.brief) !== JSON.stringify(u.evidence.map(i => u.sentences[i]))) {
        ctx.addIssue({ code: 'custom', message: 'Brief must quote its referenced source sentences; summaries need source anchors.' });
    }
});
const documentSchema = z.object({
    format: z.literal('textfold/doc'), version: z.literal(0), id, title: text, lang: text,
    levels: z.array(level), written: z.array(level),
    provenance: z.object({ ai_generated: z.boolean(), local: z.boolean(), model: text.nullish() }).passthrough(),
    sections: z.array(z.object({
        id, title: text, depth: z.number().int().min(1).max(6).default(1),
        takeaway: text, topic: text, units: z.array(unit).max(1000),
    }).passthrough().refine(s => !s.takeaway || s.units.some(u => u.evidence.length), 'Section takeaways need anchored source units.')).min(1).max(100),
    links: z.array(z.object({ from: id, to: id, rel: text }).passthrough()).max(2000).default([]),
}).passthrough().superRefine((doc, ctx) => {
    const ids = doc.sections.flatMap(s => [s.id, ...s.units.map(u => u.id)]);
    if (JSON.stringify(doc.levels) !== JSON.stringify(FOLD_LEVELS) ||
        doc.written.some(l => l === 'full' || l === 'brief') ||
        new Set(ids).size !== ids.length || doc.links.some(l => !ids.includes(l.from) || !ids.includes(l.to))) {
        ctx.addIssue({ code: 'custom', message: 'Check the five reading levels, unique IDs, and argument links. Full and Brief must be source text.' });
    }
});

export function parseTextFold(value: unknown): TextFoldDocument {
    const result = documentSchema.safeParse(value);
    if (!result.success) throw new Error(result.error.issues[0]?.message || 'Invalid Textfold document.');
    if (new TextEncoder().encode(JSON.stringify(result.data)).length > 1_000_000) throw new Error('The research brief must be under 1 MB.');
    return result.data as TextFoldDocument;
}

/** Export the same compact UTF-8 representation used by the import size bound. */
export function serializeTextFold(doc: TextFoldDocument): string {
    return JSON.stringify(parseTextFold(doc));
}

/** Read the saved levels when valid, with the original description as fallback. */
export function projectResearchBrief(project: Pick<Project, 'id' | 'title' | 'description' | 'research_brief'>) {
    if (project.research_brief) {
        try { return { document: parseTextFold(project.research_brief), invalid: false }; }
        catch { /* Old/incompatible imports must not hide the original brief. */ }
    }
    return { document: foldMarkdown(project.description || '', project.title, project.id), invalid: !!project.research_brief };
}

export function researchQuestion(doc: TextFoldDocument): string | null {
    const section = doc.sections.find(s => RESEARCH_FRAMEWORK[0].match.test(s.title));
    if (!section) return null;
    return section.title.includes('?') ? section.title.replace(/^Uncertainty\s*\d*\s*:\s*/i, '') : section.takeaway || null;
}

/** Explicit editor repair only. Never automatically rewrite valid source Markdown. */
export function normalizeProjectMarkdown(source: string): string {
    let fence: string | null = null;
    return source.replace(/\r\n/g, '\n').split('\n').map(line => {
        const marker = line.match(/^\s*(`{3,}|~{3,})/);
        if (marker) {
            if (!fence) fence = marker[1];
            else if (marker[1][0] === fence[0] && marker[1].length >= fence.length) fence = null;
        }
        if (fence || marker) return line;
        // Inline code can contain literal Markdown; never turn it into sections.
        const spans = /(`+).*?\1/g;
        let cursor = 0;
        let result = '';
        for (const match of line.matchAll(spans)) {
            result += line.slice(cursor, match.index).replace(/\s+(#{1,6})\s+(?=\S)/g, '\n\n$1 ') + match[0];
            cursor = match.index! + match[0].length;
        }
        return result + line.slice(cursor).replace(/\s+(#{1,6})\s+(?=\S)/g, '\n\n$1 ');
    }).join('\n');
}

/** Keep document-wide reference links working when individual paragraphs fold. */
export function markdownReferences(doc: TextFoldDocument): string {
    const source = doc.sections.flatMap(s => s.units.map(u => u.full)).join('\n\n');
    const definitions: Definition[] = [];
    // Use the same CommonMark parser as react-markdown: valid definitions may
    // wrap URLs/titles onto later lines or appear inside a container block.
    const collect = (node: Nodes) => {
        if (node.type === 'definition') {
            definitions.push(node);
        }
        if ('children' in node) node.children.forEach(collect);
    };
    collect(unified().use(remarkParse).parse(source));
    // Parsed values already have entities decoded. Escape literal ampersands
    // when writing them so the reader cannot decode an entity a second time.
    return toMarkdown({ type: 'root', children: definitions }, { unsafe: [{ character: '&' }] }).trim();
}

// A local fold is an excerpt, not a model's assessment. Intl handles URLs,
// abbreviations and non-English sentence boundaries better than punctuation splitting.
function sentences(source: string): string[] {
    const segmenter = new Intl.Segmenter(undefined, { granularity: 'sentence' });
    return Array.from(segmenter.segment(source), s => s.segment.trim()).filter(Boolean);
}

function makeUnit(full: string, unitId: string, topic: string): TextFoldUnit {
    const parts = sentences(full);
    const evidence = parts.slice(0, 2).map((_, i) => i);
    return { id: unitId, kind: 'paragraph', full, sentences: parts, evidence,
        brief: evidence.map(i => parts[i]), key: parts.slice(0, 2).join(' '),
        takeaway: parts[0] || '', topic: parts[0]?.split(/\s+/).slice(0,6).join(' ') || topic };
}

function markdownBlocks(content: string): string[] {
    const blocks: string[] = [];
    let lines: string[] = [];
    let fence: string | null = null;
    for (const line of content.split('\n')) {
        const marker = line.match(/^\s*(`{3,}|~{3,})/);
        if (marker) {
            if (!fence) fence = marker[1];
            else if (marker[1][0] === fence[0] && marker[1].length >= fence.length) fence = null;
        }
        if (!line.trim() && !fence) {
            if (lines.length) blocks.push(lines.join('\n'));
            lines = [];
        } else lines.push(line);
    }
    if (lines.length) blocks.push(lines.join('\n'));
    return blocks;
}

export function foldMarkdown(source: string, title: string, documentId: string): TextFoldDocument {
    const sections: TextFoldSection[] = [];
    let current: TextFoldSection | null = null;
    let body: string[] = [];
    let fence: string | null = null;
    const flush = () => {
        if (!current && !body.join('').trim()) return;
        if (!current) current = { id: `S${sections.length + 1}`, title: 'Project context', depth: 1, topic: 'Project context', takeaway: '', units: [] };
        const content = body.join('\n').trim();
        // Keep tables, fenced code, and list structures intact in Full.
        const blocks = content ? markdownBlocks(content) : [];
        current.units = blocks.map((b, i) => makeUnit(b, `${current!.id}.p${i + 1}`, current!.title));
        current.takeaway = current.units[0]?.takeaway || '';
        sections.push(current);
        body = [];
    };
    for (const line of source.replace(/\r\n/g, '\n').split('\n')) {
        const marker = line.match(/^\s*(`{3,}|~{3,})/);
        if (marker) {
            if (!fence) fence = marker[1];
            else if (marker[1][0] === fence[0] && marker[1].length >= fence.length) fence = null;
        }
        const heading = !fence && !marker && line.match(/^(#{1,6})\s+(.+?)\s*#*$/);
        if (heading) {
            flush();
            current = { id: `S${sections.length + 1}`, title: heading[2], depth: heading[1].length,
                topic: heading[2], takeaway: '', units: [] };
        } else body.push(line);
    }
    flush();
    if (!sections.length) sections.push({ id: 'S1', title: 'Project context', depth: 1, topic: 'Project context', takeaway: '', units: [] });
    return { format: 'textfold/doc', version: 0, id: documentId, title, lang: 'en',
        levels: [...FOLD_LEVELS], written: [],
        source: { kind: 'markdown', label: 'Project description' }, source_text: source,
        provenance: { made_with: 'OpenPaper native Textfold reader', ai_generated: false, local: true },
        sections, links: [] };
}

export function foldText(unit: TextFoldUnit, level: FoldLevel): string {
    return level === 'brief' ? unit.brief.join(' ') : unit[level];
}

export const RESEARCH_FRAMEWORK = [
    { key: 'question', title: 'The uncertainty', match: /question|uncertainty|research aim/i, prompt: 'What disputed question would this project resolve?' },
    { key: 'relevance', title: 'Why it matters', match: /why.*matter|relevance|significance|catastroph|risk pathway/i, prompt: 'Which AI safety risk or decision could the answer change? State the causal pathway and its assumptions.' },
    { key: 'landscape', title: 'Landscape & novelty', match: /landscape|novel|related work|contribution|prior work/i, prompt: 'What do the closest projects already establish? What specific uncertainty or matched comparison remains, and when were the sources checked?' },
    { key: 'for', title: 'Evidence for', match: /evidence\s+for|supporting evidence/i, prompt: 'Which results support the concern? Cite exact sources and distinguish results from interpretation.' },
    { key: 'against', title: 'Evidence against', match: /evidence\s+against|counter.?evidence|constraining|against.*weak/i, prompt: 'Which null results or boundary conditions constrain it? Missing evidence is not a negative result.' },
    { key: 'tension', title: 'Resolve the tension', match: /tension|reconcil|explanation|complication/i, prompt: 'Which differences in models, tasks, training, priming, or evaluations could explain the disagreement?' },
    { key: 'experiment', title: 'Discriminating experiment', match: /experiment|next step|method|test design/i, prompt: 'What matched experiment separates the explanations? Define controls, outcomes and failure cases.' },
    { key: 'update', title: 'What would change our mind', match: /update|abandon|falsif|change.*mind|decision criter/i, prompt: 'What result would update, redirect, or end this project?' },
] as const;

export const RESEARCH_TEMPLATE = `## The question
State one disputed uncertainty, then your current provisional answer and its limits.

## Why this matters
Explain the AI safety risk pathway, affected decision and assumptions.

## Landscape and novelty
Compare the closest existing work, with sources and a date checked. State the specific unresolved gap; mark novelty as provisional.

## Evidence for
Cite supporting results. Separate observed outcomes, author interpretation, alternative explanations and speculation. Name models, tasks, training and evaluation conditions.

## Evidence against
Cite counterevidence, null results and boundary conditions with comparable setup details. An empty section does not establish absence of counterevidence.

## Tension and possible reconciliation
Explain conflicting findings and candidate moderators. Say what remains unresolved.

## Discriminating experiment
Describe a matched comparison, baselines, controls, success measures and failure cases that distinguish the explanations.

## Update and abandonment criteria
State what outcomes would change your view, narrow the claim or end the project.

## Sources and limitations
Link primary sources and exact passages. Record the search date and coverage limits. This is a scoping brief unless a fuller review is documented.`;
