import type { Investigation, Relation } from './investigation';

// Layout of the project canvas: the whole investigation on one surface.
// Columns run left to right: the question and the draft's sections, the claims,
// the findings, the papers. Pure geometry: no DOM, no storage, no network, and
// nothing hand-placed. The same document and papers always give the same map.

export type CanvasKind = 'question' | 'section' | 'claim' | 'finding' | 'paper';

export type CanvasNode = {
    /** Unique on the canvas; `ref` is the id of what it stands for. */
    key: string;
    ref: string;
    kind: CanvasKind;
    label: string;
    /** What kind of thing it is and where it sits, for accessible names. */
    name: string;
    column: number;
    x: number;
    y: number;
    w: number;
    h: number;
    /** Claims only: how many shown findings support, challenge and qualify it. */
    tally: Record<Relation['relation'], number> | null;
};

export type CanvasEdgeKind = 'asks' | Relation['relation'] | 'source' | 'drafts';

export type CanvasEdge = { key: string; kind: CanvasEdgeKind; from: string; to: string; path: string };

export type CanvasLayout = {
    nodes: CanvasNode[];
    /** Every line that is always drawn. A section's lines to what it cites are not here: see `draftEdges`. */
    edges: CanvasEdge[];
    /** Per draft section (by node key), the keys of the claims and findings its paragraphs cite. */
    cites: Map<string, ReadonlySet<string>>;
    width: number;
    height: number;
};

export type CanvasPaper = { id: string; title?: string | null };

const SIZE: Record<CanvasKind, { w: number; h: number }> = {
    question: { w: 240, h: 104 },
    section: { w: 240, h: 48 },
    claim: { w: 260, h: 84 },
    finding: { w: 240, h: 60 },
    paper: { w: 230, h: 54 },
};
const COLUMN: Record<CanvasKind, number> = { question: 0, section: 0, claim: 1, finding: 2, paper: 3 };
const COLUMN_GAP = 84;
const ROW_GAP = 12;
const GROUP_GAP = 36;
const PAD = 24;
const LABEL_LIMIT = 200;

export const canvasKey = (kind: CanvasKind, ref: string) => `${kind}:${ref}`;

const middle = (node: CanvasNode) => node.y + node.h / 2;
// Always drawn from the left node's right edge to the right node's left edge.
function curve(kind: CanvasEdgeKind, from: CanvasNode, to: CanvasNode, shift = 0): CanvasEdge {
    const x1 = from.x + from.w, y1 = middle(from) + shift, x2 = to.x, y2 = middle(to) + shift, bend = (x2 - x1) / 2;
    return { key: `${kind}:${from.key}>${to.key}`, kind, from: from.key, to: to.key, path: `M${x1},${y1} C${x1 + bend},${y1} ${x2 - bend},${y2} ${x2},${y2}` };
}

/**
 * The lines between draft sections and what they cite that touch one node: all of a section's,
 * or, for a claim or finding, one from each section that cites it. A long draft cites thousands
 * of things, so these are built for the selection and not for the whole canvas, and a section
 * gets lines to at most `DRAFT_LINE_LIMIT` of what it cites, in the order its paragraphs cite them.
 */
export const DRAFT_LINE_LIMIT = 100;
export function draftEdges(layout: CanvasLayout, byKey: ReadonlyMap<string, CanvasNode>, key: string): CanvasEdge[] {
    const edges: CanvasEdge[] = [];
    const own = layout.cites.get(key), self = byKey.get(key);
    if (!self) return edges;
    if (own) {
        for (const cited of own) {
            if (edges.length >= DRAFT_LINE_LIMIT) break;
            const to = byKey.get(cited);
            if (to) edges.push(curve('drafts', self, to));
        }
        return edges;
    }
    for (const [section, cited] of layout.cites) {
        const from = byKey.get(section);
        if (from && cited.has(key)) edges.push(curve('drafts', from, self));
    }
    return edges;
}

/** True when there is nothing to draw: no question, claims, findings, sections or papers. */
export function canvasIsEmpty(doc: Investigation, papers: readonly CanvasPaper[]) {
    return !doc.case.question.trim() && !papers.length && !doc.manuscript.sections.length
        && !doc.claims.some(claim => !claim.archived) && !doc.findings.some(finding => !finding.archived);
}

export function projectCanvas(doc: Investigation, papers: readonly CanvasPaper[]): CanvasLayout {
    const nodes: CanvasNode[] = [];
    const byKey = new Map<string, CanvasNode>();
    const lefts: number[] = [];
    [SIZE.question.w, SIZE.claim.w, SIZE.finding.w, SIZE.paper.w].reduce((left, width, column) => { lefts[column] = left; return left + width + COLUMN_GAP; }, PAD);
    const make = (kind: CanvasKind, ref: string, text: string, fallback: string, name: string): CanvasNode => {
        const words = text.trim().replace(/\s+/g, ' ') || fallback;
        const node: CanvasNode = {
            key: canvasKey(kind, ref), ref, kind, name, column: COLUMN[kind], x: lefts[COLUMN[kind]], y: 0, ...SIZE[kind], tally: null,
            label: words.length > LABEL_LIMIT ? `${words.slice(0, LABEL_LIMIT - 1).trimEnd()}…` : words,
        };
        nodes.push(node);
        byKey.set(node.key, node);
        return node;
    };
    const centre = middle;
    const stack = (column: CanvasNode[], from: number) => column.reduce((y, node) => { node.y = y; return y + node.h + ROW_GAP; }, from);
    // Each node sits level with what it is linked to in the column before, without overlapping its neighbours.
    // Nodes with no link follow the linked ones, in their own order.
    const settle = (column: CanvasNode[], linked: (node: CanvasNode) => CanvasNode[]) => {
        const wanted = column.map((node, index) => {
            const others = linked(node);
            return { node, index, y: others.length ? others.reduce((sum, other) => sum + centre(other), 0) / others.length - node.h / 2 : Infinity };
        }).sort((a, b) => (a.y === b.y ? a.index - b.index : a.y < b.y ? -1 : 1));
        let floor = PAD;
        for (const item of wanted) {
            item.node.y = item.y === Infinity ? floor : Math.max(floor, item.y);
            floor = item.node.y + item.node.h + ROW_GAP;
        }
    };

    // Column 0: the question, then the draft's sections under it.
    const question = make('question', 'question', doc.case.question, 'No question yet', 'Question');
    question.y = PAD;
    const sections = doc.manuscript.sections.map((section, index) => make('section', section.id, section.title, 'Untitled section', `Draft section ${index + 1}`));
    stack(sections, question.y + question.h + GROUP_GAP);

    // Column 1: claims, in the order they are argued.
    const claims = doc.claims.filter(claim => !claim.archived).map((claim, index) => {
        const node = make('claim', claim.id, claim.statement, 'Untitled claim', `Claim ${index + 1}`);
        node.tally = { supports: 0, challenges: 0, qualifies: 0 };
        return node;
    });
    stack(claims, PAD);

    // Column 2: findings, level with the claims they bear on.
    const findings = doc.findings.filter(finding => !finding.archived).map(finding => make('finding', finding.id, finding.label, 'Untitled finding', 'Finding'));
    const relations = doc.relations
        .map(relation => ({ relation, claim: byKey.get(canvasKey('claim', relation.claim_id)), finding: byKey.get(canvasKey('finding', relation.finding_id)) }))
        .filter((item): item is { relation: Relation; claim: CanvasNode; finding: CanvasNode } => !!item.claim && !!item.finding);
    const claimsOf = new Map<CanvasNode, Set<CanvasNode>>();
    for (const { relation, claim, finding } of relations) {
        claim.tally![relation.relation] += 1;
        claimsOf.set(finding, (claimsOf.get(finding) || new Set<CanvasNode>()).add(claim));
    }
    settle(findings, finding => [...(claimsOf.get(finding) || [])]);

    // Column 3: papers, level with the findings drawn from them.
    const paperNodes = papers.map(paper => make('paper', paper.id, paper.title || '', 'Untitled paper', 'Paper'));
    const sources: { finding: CanvasNode; paper: CanvasNode }[] = [];
    const findingsOf = new Map<CanvasNode, CanvasNode[]>();
    for (const finding of doc.findings) {
        const from = byKey.get(canvasKey('finding', finding.id));
        // A redacted source names a paper but gives no passage to open, so it is not drawn as a source.
        const paper = finding.source.kind === 'anchored' ? byKey.get(canvasKey('paper', finding.source.paper_id)) : undefined;
        if (!from || finding.archived || !paper) continue;
        sources.push({ finding: from, paper });
        findingsOf.set(paper, [...(findingsOf.get(paper) || []), from]);
    }
    settle(paperNodes, paper => findingsOf.get(paper) || []);

    const edges: CanvasEdge[] = [];
    const seen = new Set<string>();
    const across = (kind: CanvasEdgeKind, from: CanvasNode, to: CanvasNode, shift = 0) => {
        const edge = curve(kind, from, to, shift);
        if (seen.has(edge.key)) return;
        seen.add(edge.key);
        edges.push(edge);
    };
    for (const claim of claims) across('asks', question, claim);
    // A finding can bear on one claim in more than one way; the lines are kept apart.
    const SHIFT: Record<Relation['relation'], number> = { supports: 0, challenges: 6, qualifies: -6 };
    const pairs = new Map<string, number>();
    for (const { claim, finding } of relations) pairs.set(`${claim.key}>${finding.key}`, (pairs.get(`${claim.key}>${finding.key}`) || 0) + 1);
    for (const { relation, claim, finding } of relations) across(relation.relation, claim, finding, pairs.get(`${claim.key}>${finding.key}`)! > 1 ? SHIFT[relation.relation] : 0);
    for (const { finding, paper } of sources) across('source', finding, paper);
    const cites = new Map<string, Set<string>>();
    doc.manuscript.sections.forEach((section, index) => {
        const cited = new Set<string>();
        for (const block of section.blocks) {
            for (const id of block.claim_ids) { const key = canvasKey('claim', id); if (byKey.has(key)) cited.add(key); }
            for (const id of block.finding_ids) { const key = canvasKey('finding', id); if (byKey.has(key)) cited.add(key); }
        }
        cites.set(sections[index].key, cited);
    });

    return {
        nodes,
        edges,
        cites,
        // The papers column is kept only when there are papers to put in it, and so on leftwards.
        width: Math.max(...nodes.map(node => node.x + node.w)) + PAD,
        height: Math.max(...nodes.map(node => node.y + node.h)) + PAD,
    };
}
