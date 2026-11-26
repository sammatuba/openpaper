import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';
import { toMarkdown } from 'mdast-util-to-markdown';
import type { Nodes } from 'mdast';
import type { FoldLevel, TextFoldDocument, TextFoldUnit } from './schema';

// What the folded reader shows for a paragraph at a reading level. No DOM, no
// storage, no network. The reading levels and the textfold/doc format
// originate from TextFold by Xia Chen (https://github.com/chenxiachan/textfold).
export const LEVEL_ORDER: FoldLevel[] = ['topic', 'takeaway', 'key', 'brief', 'full'];
export const LEVEL_LABELS: Record<FoldLevel, string> = {
    topic: 'Topic', takeaway: 'Takeaway', key: 'Key', brief: 'Brief', full: 'Full',
};

export type UnitView = {
    /** The level actually shown; fuller than requested when the requested level has no text. */
    level: FoldLevel;
    /** True when the text is source wording (Brief and Full). */
    source: boolean;
    /** Markdown to render. */
    markdown: string;
};

// The same CommonMark + GFM grammar the reader renders with, so a block is
// prose exactly when it renders as paragraphs.
const grammar = unified().use(remarkParse).use(remarkGfm);
const proseCache = new WeakMap<object, boolean>();

/** Tables, code, lists, quotes, headings and raw HTML do not fold by sentence. */
export function isProse(unit: Pick<TextFoldUnit, 'full'>): boolean {
    let prose = proseCache.get(unit);
    if (prose === undefined) {
        prose = grammar.parse(unit.full).children.every(node => node.type === 'paragraph' || node.type === 'definition');
        proseCache.set(unit, prose);
    }
    return prose;
}

export function unitView(unit: TextFoldUnit, requested: FoldLevel): UnitView {
    for (const level of LEVEL_ORDER.slice(LEVEL_ORDER.indexOf(requested))) {
        if (level === 'full') break;
        if (level === 'brief') {
            if (isProse(unit) && unit.brief.some(sentence => sentence.trim())) return { level, source: true, markdown: unit.brief.join(' ') };
            continue;
        }
        const text = typeof unit[level] === 'string' ? unit[level].trim() : '';
        if (text) return { level, source: false, markdown: text };
    }
    return { level: 'full', source: true, markdown: unit.full };
}

/** The next fuller level that changes what is shown, or null at Full. */
export function nextStep(unit: TextFoldUnit, shown: FoldLevel): FoldLevel | null {
    if (shown === 'full') return null;
    const brief = unitView(unit, 'brief');
    return shown !== 'brief' && brief.level === 'brief' ? 'brief' : 'full';
}

/** The words of a piece of Markdown, for places that show text only (map nodes, names). */
export function plainText(markdown: string): string {
    const words: string[] = [];
    const walk = (node: Nodes) => {
        if (node.type === 'definition' || node.type === 'footnoteDefinition' || node.type === 'footnoteReference' || node.type === 'html') return;
        if (node.type === 'text' || node.type === 'inlineCode' || node.type === 'code') words.push(node.value);
        else if (node.type === 'image' || node.type === 'imageReference') words.push(node.alt || 'image');
        else if (node.type === 'break') words.push(' ');
        else if ('children' in node) { node.children.forEach(walk); if (node.type !== 'root' && !('value' in node) && /^(paragraph|heading|listItem|tableCell|tableRow|blockquote)$/.test(node.type)) words.push(' '); }
    };
    walk(grammar.parse(markdown));
    return words.join('').replace(/\s+/g, ' ').trim();
}

// Paragraphs render one at a time, but link references and footnotes are
// defined once for the whole document. The context holds each definition as
// Markdown, first definition winning as in CommonMark, so a paragraph can be
// rendered with exactly the definitions it uses.
export type FoldContext = {
    literal: boolean;
    definitions: Map<string, string>;
    footnotes: Map<string, string>;
    /** Paragraphs that only define references or footnotes and so render no words. */
    silent: Set<string>;
};

// Labels match on their source text (escapes and entities included), with
// whitespace collapsed and case folded, as the parser's own identifiers do.
const identifier = (label: string) => label.replace(/[\t\n\r ]+/g, ' ').trim().toLowerCase().toUpperCase().toLowerCase();
const LABEL = /\[((?:\\[\s\S]|[^\[\]\\])+)\]/g;

export function foldContext(doc: TextFoldDocument, literal = false): FoldContext {
    const context: FoldContext = { literal, definitions: new Map(), footnotes: new Map(), silent: new Set() };
    if (literal) return context;
    const wordless = (node: Nodes): boolean => node.type === 'definition' || node.type === 'footnoteDefinition' ||
        ((node.type === 'root' || node.type === 'blockquote') && node.children.every(wordless));
    for (const section of doc.sections) for (const unit of section.units) {
        const collect = (node: Nodes, top: boolean) => {
            if (node.type === 'definition' && !context.definitions.has(node.identifier)) {
                // The label is kept exactly as written so the paragraph's own label still matches it.
                // Destination and title are parsed values: escape ampersands so entities are not decoded twice.
                const rest = toMarkdown({ type: 'root', children: [{ ...node, label: 'x', identifier: 'x' }] }, { unsafe: [{ character: '&' }] }).trim().slice('[x]'.length);
                // The parsed label is decoded, so take the label from the source text itself.
                const written = node.position ? /^\[((?:\\[\s\S]|[^\[\]\\])+)\]/.exec(unit.full.slice(node.position.start.offset, node.position.end.offset)) : null;
                // A label wrapped inside a quotation carries the quote's line prefix; a line break in a label is a space.
                const label = written ? written[1].replace(/(?<!\\)\n[ \t>]*/g, ' ') : node.label ?? node.identifier;
                context.definitions.set(node.identifier, `[${label}]${rest}`);
            } else if (node.type === 'footnoteDefinition' && top && !context.footnotes.has(node.identifier) && node.position) {
                // Source text of a top-level footnote. One nested in a quote or list keeps
                // its container's line prefixes and is left to its own paragraph.
                context.footnotes.set(node.identifier, unit.full.slice(node.position.start.offset, node.position.end.offset));
            }
            if ('children' in node) node.children.forEach(child => collect(child, node.type === 'root'));
        };
        const tree = grammar.parse(unit.full);
        collect(tree, false);
        if (tree.children.length > 0 && wordless(tree)) context.silent.add(unit.id);
    }
    return context;
}

/**
 * The Markdown to render for a paragraph: the link definitions it uses, its
 * text, then the footnotes it cites. Link definitions go first, where nothing
 * in the paragraph (an unclosed fence, a local duplicate) can swallow or
 * override them, and where they cannot change how the text itself parses.
 * Footnotes go last and only when the parsed result really cites and defines
 * them; otherwise the paragraph is left exactly as written.
 */
export function withReferences(context: FoldContext, markdown: string): string {
    if (!context.definitions.size && !context.footnotes.size) return markdown;
    const definitions: string[] = [];
    const notes: [string, string][] = [];
    const seen = new Set<string>();
    const scan = (text: string) => {
        for (const match of text.matchAll(LABEL)) {
            const note = match[1].startsWith('^');
            const id = identifier(note ? match[1].slice(1) : match[1]);
            const key = (note ? '^' : '') + id;
            if (seen.has(key)) continue;
            seen.add(key);
            const definition = note ? context.footnotes.get(id) : context.definitions.get(id);
            if (!definition) continue;
            if (note) { notes.push([id, definition]); scan(definition); } else definitions.push(definition);
        }
    };
    scan(markdown);
    const text = definitions.length ? `${definitions.join('\n\n')}\n\n${markdown}` : markdown;
    if (!notes.length) return text;
    const candidate = `${text}\n\n${notes.map(note => note[1]).join('\n\n')}`;
    const cited = new Set<string>(), defined = new Set<string>();
    const walk = (node: Nodes) => {
        if (node.type === 'footnoteReference') cited.add(node.identifier);
        if (node.type === 'footnoteDefinition') defined.add(node.identifier);
        if ('children' in node) node.children.forEach(walk);
    };
    walk(grammar.parse(candidate));
    const kept = notes.filter(([id]) => cited.has(id) && defined.has(id));
    return kept.length ? `${text}\n\n${kept.map(note => note[1]).join('\n\n')}` : text;
}

export type FoldLink = { rel: string; to: string; title: string };

/** Argument links by the paragraph or section they start from, with a readable target. */
export function linksFrom(doc: TextFoldDocument): Map<string, FoldLink[]> {
    const titles = new Map<string, string>();
    for (const section of doc.sections) {
        titles.set(section.id, section.title);
        for (const unit of section.units) titles.set(unit.id, unit.topic.trim() || unit.takeaway.trim() || section.title);
    }
    const result = new Map<string, FoldLink[]>();
    for (const link of doc.links || []) {
        const title = titles.get(link.to);
        if (!title || !titles.has(link.from)) continue;
        if (!result.has(link.from)) result.set(link.from, []);
        result.get(link.from)!.push({ rel: link.rel.replaceAll('_', ' '), to: link.to, title });
    }
    return result;
}

export function provenanceLine(doc: TextFoldDocument): string {
    const origin = doc.provenance.local ? 'Local excerpts · first sentences, no new assessment'
        : doc.provenance.ai_generated ? `AI-written summaries${doc.provenance.model ? ` · ${doc.provenance.model}` : ''}`
            : 'Provided reading levels';
    return `${origin}. Full and Brief preserve source wording.`;
}
