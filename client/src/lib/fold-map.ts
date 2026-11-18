import type { FoldLevel, TextFoldDocument } from './schema';
import { plainText, unitView, withReferences } from './fold-view';
import type { FoldContext } from './fold-view';

// Layout of the folded reader's map: the document as a left-to-right mind map
// (title, sections, paragraphs) with argument links and cited findings drawn
// across it as graph edges. Pure geometry: no DOM, no storage, no network.

export type MapNodeKind = 'root' | 'section' | 'unit' | 'finding';

export type MapNode = {
    /** Unique in the map; `ref` is the document id it stands for. */
    key: string;
    ref: string;
    kind: MapNodeKind;
    label: string;
    /** Paragraph position and section title, for accessible names. */
    name: string;
    column: number;
    x: number;
    y: number;
    w: number;
    h: number;
    /** Sections only: paragraphs and subsections under it, and whether they are hidden. */
    children: number;
    collapsed: boolean;
};

export type MapEdge = {
    key: string;
    kind: 'tree' | 'link' | 'cites';
    from: string;
    to: string;
    /** Relation name on argument links. */
    rel: string;
    path: string;
    labelX: number;
    labelY: number;
};

export type FoldMapLayout = { nodes: MapNode[]; edges: MapEdge[]; width: number; height: number };

export type MapFinding = { id: string; label: string };

type Options = {
    level: FoldLevel;
    collapsed: ReadonlySet<string>;
    /** Document-wide references; paragraphs that only define them are not on the map. */
    context: FoldContext;
    /** Draw the findings each paragraph cites (documents OpenPaper built itself). */
    findings: boolean;
};

const SIZE: Record<MapNodeKind, { w: number; h: number }> = {
    root: { w: 160, h: 76 },
    section: { w: 176, h: 54 },
    unit: { w: 236, h: 70 },
    finding: { w: 190, h: 46 },
};
const COLUMN_GAP = 44;
const ROW_GAP = 12;
const PAD = 20;

type Tree = { node: MapNode; children: Tree[] };

function findingsOf(unit: { [key: string]: unknown }): MapFinding[] {
    return Array.isArray(unit.findings)
        ? unit.findings.filter((item): item is MapFinding => !!item && typeof item === 'object' && typeof item.id === 'string' && typeof item.label === 'string')
        : [];
}

export function foldMap(doc: TextFoldDocument, options: Options): FoldMapLayout {
    const make = (kind: MapNodeKind, ref: string, label: string, name: string, column: number): MapNode =>
        ({ key: `${kind}:${ref}`, ref, kind, label, name, column, x: 0, y: 0, ...SIZE[kind], children: 0, collapsed: false });

    const root: Tree = { node: make('root', doc.id, doc.title.trim() || 'Untitled', 'Document', 0), children: [] };
    // Where a document id is drawn: itself, or the nearest shown ancestor when folded away.
    const shownAs = new Map<string, string>();
    const cites: { unit: string; finding: MapFinding }[] = [];
    const stack: { depth: number; tree: Tree; hidden: boolean }[] = [];
    const textLevel: FoldLevel = options.level === 'topic' ? 'topic' : 'takeaway';

    for (const section of doc.sections) {
        while (stack.length && stack[stack.length - 1].depth >= section.depth) stack.pop();
        const parent = stack[stack.length - 1];
        const hidden = !!parent && (parent.hidden || parent.tree.node.collapsed);
        const column = (parent ? parent.tree.node.column : 0) + 1;
        const tree: Tree = { node: make('section', section.id, section.title.trim() || 'Untitled section', section.title, column), children: [] };
        tree.node.collapsed = options.collapsed.has(section.id);
        const units = section.units.filter(unit => !options.context.silent.has(unit.id));
        tree.node.children = units.length;
        if (parent) parent.tree.node.children += 1;
        const anchor = hidden ? shownAs.get(parent!.tree.node.ref)! : tree.node.key;
        shownAs.set(section.id, anchor);
        if (!hidden) (parent ? parent.tree : root).children.push(tree);
        section.units.forEach(unit => shownAs.set(unit.id, anchor));
        units.forEach((unit, index) => {
            if (hidden || tree.node.collapsed) return;
            const text = plainText(withReferences(options.context, unitView(unit, textLevel).markdown)) || 'No text.';
            const node = make('unit', unit.id, text.length > 220 ? `${text.slice(0, 217).trimEnd()}…` : text, `paragraph ${index + 1} of ${section.title}`, column + 1);
            tree.children.push({ node, children: [] });
            shownAs.set(unit.id, node.key);
            if (options.findings) for (const finding of findingsOf(unit)) cites.push({ unit: node.key, finding });
        });
        stack.push({ depth: section.depth, tree, hidden });
    }

    // Columns are as wide as their widest node.
    const all: MapNode[] = [];
    const collect = (tree: Tree) => { all.push(tree.node); tree.children.forEach(collect); };
    collect(root);
    const findingColumn = Math.max(...all.map(node => node.column)) + 1;
    const findingNodes = new Map<string, MapNode>();
    for (const { finding } of cites) {
        if (!findingNodes.has(finding.id)) findingNodes.set(finding.id, make('finding', finding.id, finding.label.trim() || 'Untitled finding', 'Finding', findingColumn));
    }
    const widths: number[] = [];
    for (const node of [...all, ...findingNodes.values()]) widths[node.column] = Math.max(widths[node.column] || 0, node.w);
    const lefts: number[] = [];
    widths.reduce((left, width, column) => { lefts[column] = left; return left + width + COLUMN_GAP; }, PAD);

    // Leaves stack downwards; a parent sits at the middle of its children.
    let cursor = PAD;
    const place = (tree: Tree) => {
        const node = tree.node;
        node.x = lefts[node.column];
        if (!tree.children.length) {
            node.y = cursor;
        } else {
            const start = cursor;
            tree.children.forEach(place);
            const first = tree.children[0].node, last = tree.children[tree.children.length - 1].node;
            node.y = Math.max(start, (first.y + last.y + last.h) / 2 - node.h / 2);
        }
        cursor = Math.max(cursor, node.y + node.h + ROW_GAP);
    };
    place(root);

    // A finding sits level with the paragraphs that cite it, without overlapping its neighbours.
    const byKey = new Map(all.map(node => [node.key, node]));
    const wanted = [...findingNodes.values()].map(node => {
        const citing = cites.filter(cite => cite.finding.id === node.ref).map(cite => byKey.get(cite.unit)!);
        return { node, y: citing.reduce((sum, unit) => sum + unit.y + unit.h / 2, 0) / citing.length - node.h / 2 };
    }).sort((a, b) => a.y - b.y);
    let floor = PAD;
    for (const item of wanted) {
        item.node.x = lefts[findingColumn];
        item.node.y = Math.max(floor, item.y);
        floor = item.node.y + item.node.h + ROW_GAP;
        byKey.set(item.node.key, item.node);
        all.push(item.node);
    }

    const edges: MapEdge[] = [];
    const across = (kind: MapEdge['kind'], from: MapNode, to: MapNode, rel: string, index: number) => {
        const x1 = from.x + from.w, y1 = from.y + from.h / 2;
        let path: string, labelX: number, labelY: number;
        if (to.x > from.x) {
            const x2 = to.x, y2 = to.y + to.h / 2, bend = (x2 - x1) / 2;
            path = `M${x1},${y1} C${x1 + bend},${y1} ${x2 - bend},${y2} ${x2},${y2}`;
            labelX = (x1 + x2) / 2; labelY = (y1 + y2) / 2;
        } else if (to.x < from.x) {
            // Back towards the title: leave from the left edge and arrive on the right edge.
            const sx = from.x, x2 = to.x + to.w, y2 = to.y + to.h / 2, bend = (sx - x2) / 2;
            path = `M${sx},${y1} C${sx - bend},${y1} ${x2 + bend},${y2} ${x2},${y2}`;
            labelX = (sx + x2) / 2; labelY = (y1 + y2) / 2;
        } else {
            // Same column: bow out to the right, wider for longer spans.
            const x2 = to.x + to.w, y2 = to.y + to.h / 2, bow = Math.min(COLUMN_GAP - 12, 22 + Math.abs(y2 - y1) / 12);
            path = `M${x1},${y1} C${x1 + bow * 1.6},${y1} ${x2 + bow * 1.6},${y2} ${x2},${y2}`;
            labelX = Math.max(x1, x2) + bow * 1.2; labelY = (y1 + y2) / 2;
        }
        edges.push({ key: `${kind}:${from.key}>${to.key}:${index}`, kind, from: from.key, to: to.key, rel, path, labelX, labelY });
    };
    const branches = (tree: Tree) => tree.children.forEach((child, index) => { across('tree', tree.node, child.node, '', index); branches(child); });
    branches(root);
    (doc.links || []).forEach((link, index) => {
        const from = byKey.get(shownAs.get(link.from) || ''), to = byKey.get(shownAs.get(link.to) || '');
        if (from && to && from !== to) across('link', from, to, link.rel.replaceAll('_', ' '), index);
    });
    const drawn = new Set<string>();
    cites.forEach((cite, index) => {
        const id = `${cite.unit}>${cite.finding.id}`;
        if (drawn.has(id)) return;
        drawn.add(id);
        across('cites', byKey.get(cite.unit)!, findingNodes.get(cite.finding.id)!, '', index);
    });

    return {
        nodes: all,
        edges,
        width: Math.max(...all.map(node => node.x + node.w)) + PAD + (edges.some(edge => edge.kind === 'link') ? COLUMN_GAP : 0),
        height: Math.max(...all.map(node => node.y + node.h)) + PAD,
    };
}

/** Large documents open with their sections folded. */
export function initiallyCollapsed(doc: TextFoldDocument): Set<string> {
    const units = doc.sections.reduce((count, section) => count + section.units.length, 0);
    return new Set(units > 40 ? doc.sections.map(section => section.id) : []);
}
