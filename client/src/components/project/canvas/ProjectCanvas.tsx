"use client";

import Link from "next/link";
import { memo, useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import type { RefObject } from "react";
import { ArrowRight, BookOpen, FileText, Map as MapIcon, PenLine, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { DRAFT_LINE_LIMIT, canvasIsEmpty, canvasKey, draftEdges, projectCanvas } from "@/lib/project-canvas";
import type { CanvasEdge, CanvasEdgeKind, CanvasNode } from "@/lib/project-canvas";
import type { Camera } from "@/lib/camera";
import type { Investigation, Relation } from "@/lib/investigation";
import { investigationSession, recallInvestigation, subscribeInvestigationSnapshots } from "@/lib/investigation-snapshot";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Surface } from "@/components/canvas/Surface";
import type { SurfaceHandle } from "@/components/canvas/Surface";
import { useProjectWorkspace } from "@/components/project/ProjectWorkspaceProvider";
import { useInvestigation } from "@/components/project/InvestigationProvider";
import { EmptyState, RELATIONS, RELATION_KINDS, RelationTag, useCanEdit } from "@/components/project/investigation/shared";

// The project's home: the whole investigation on one surface. The canvas reads
// the document in memory and never writes it; reading and editing happen in the
// views and panels its nodes lead to.

// Where the camera was and what was selected, per project, for the signed-in session only: the next
// user of this tab starts with their own view. Numbers and ids: no research text is kept here.
type View = { camera?: Camera; selected: string | null };
const views = new Map<string, View>();
let viewsFor = -1;
function viewOf(session: number, projectId: string): View | undefined {
    return session === investigationSession() && session === viewsFor ? views.get(projectId) : undefined;
}
// A write from a session that has ended (a canvas unmounting after sign-out) is dropped.
function keepView(session: number, projectId: string, change: Partial<View>) {
    if (session !== investigationSession()) return;
    if (viewsFor !== session) { views.clear(); viewsFor = session; }
    views.set(projectId, { selected: null, ...views.get(projectId), ...change });
}

const ATTRIBUTES = { "data-project-canvas": "true" } as const;

const NODE_STYLE: Record<CanvasNode["kind"], string> = {
    question: "items-start border-blue-600 bg-blue-600 py-2.5 text-sm font-semibold leading-snug text-white dark:border-blue-500 dark:bg-blue-500",
    claim: "flex-col items-stretch justify-center gap-1 border-blue-200 bg-blue-50 text-xs font-medium leading-[1.35] text-blue-950 hover:border-blue-400 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-100 dark:hover:border-blue-600",
    finding: "border-emerald-300 bg-emerald-50 text-xs font-medium leading-[1.35] text-emerald-950 hover:border-emerald-500 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-100",
    paper: "border-border bg-card text-xs leading-[1.35] text-card-foreground hover:border-blue-400 dark:hover:border-blue-600",
    section: "border-dashed border-slate-300 bg-background text-xs font-medium text-foreground hover:border-blue-400 dark:border-slate-600 dark:hover:border-blue-600",
};
// One class string per kind and state, not one merge per node per render.
const nodeClasses = new Map<string, string>();
function nodeClass(kind: CanvasNode["kind"], selected: boolean) {
    const id = `${kind}:${selected}`;
    let value = nodeClasses.get(id);
    if (!value) {
        value = cn(
            // Every node is rendered, on screen or not. `content-visibility: auto` was measured and left out: it shortens
            // the first paint of a very large canvas but lays nodes out mid-zoom, which makes zooming stutter.
            "absolute flex items-center gap-1.5 overflow-hidden rounded-xl border px-3 text-left shadow-xs outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
            NODE_STYLE[kind],
            selected && "border-blue-500 ring-2 ring-blue-500/40",
        );
        nodeClasses.set(id, value);
    }
    return value;
}

// Relations keep the colours they have everywhere else; the dash repeats the meaning so colour is never the only cue.
const EDGE_STYLE: Record<CanvasEdgeKind, { quiet: string; active: string; dash?: string }> = {
    asks: { quiet: "stroke-slate-300 dark:stroke-slate-600", active: "stroke-blue-500" },
    supports: { quiet: "stroke-green-600/60 dark:stroke-green-500/60", active: "stroke-green-600 dark:stroke-green-400" },
    challenges: { quiet: "stroke-red-600/60 dark:stroke-red-500/60", active: "stroke-red-600 dark:stroke-red-400", dash: "7 4" },
    qualifies: { quiet: "stroke-yellow-600/70 dark:stroke-yellow-500/70", active: "stroke-yellow-600 dark:stroke-yellow-400", dash: "2 4" },
    source: { quiet: "stroke-slate-300 dark:stroke-slate-600", active: "stroke-emerald-600 dark:stroke-emerald-400" },
    drafts: { quiet: "stroke-slate-300/70 dark:stroke-slate-600/70", active: "stroke-blue-500", dash: "4 5" },
};

const plural = (count: number, one: string, many = `${one}s`) => `${count} ${count === 1 ? one : many}`;

function Tally({ tally }: { tally: Record<Relation["relation"], number> }) {
    const total = RELATION_KINDS.reduce((sum, kind) => sum + tally[kind], 0);
    if (!total) return <span className="text-[11px] font-normal opacity-70">No evidence linked</span>;
    return (
        <span className="flex items-center gap-2.5">
            {RELATION_KINDS.map(kind => {
                if (!tally[kind]) return null;
                const Icon = RELATIONS[kind].icon;
                return <span key={kind} className={cn("inline-flex items-center gap-0.5 text-[11px]", RELATIONS[kind].tone)}><Icon aria-hidden className="h-3 w-3" />{tally[kind]}</span>;
            })}
        </span>
    );
}

const tallyWords = (tally: Record<Relation["relation"], number>) => {
    const parts = RELATION_KINDS.filter(kind => tally[kind]).map(kind => `${tally[kind]} ${RELATIONS[kind].verb}`);
    return parts.length ? parts.join(", ") : "no evidence linked";
};

export function ProjectCanvas() {
    const { projectId, project, papers, isProjectLoading, isPapersLoading, papersError, projectError, openPaper, openAddPapers } = useProjectWorkspace();
    const { document: current, status, loaded } = useInvestigation();
    // On a return visit the last saved copy is drawn while the current one loads.
    // Subscribed, so a copy that is dropped (a refusal arriving late) leaves the screen without waiting for another render.
    const snapshot = useSyncExternalStore(subscribeInvestigationSnapshots, () => recallInvestigation(projectId), () => null);
    const kept = loaded ? null : snapshot;
    const [session] = useState(investigationSession);
    const doc = kept ?? current;
    const canEdit = useCanEdit();
    const base = `/projects/${projectId}`;

    const [selectedKey, setSelectedKey] = useState<string | null>(() => viewOf(session, projectId)?.selected ?? null);
    const layout = useMemo(() => projectCanvas(doc, papers), [doc, papers]);
    const byKey = useMemo(() => new Map(layout.nodes.map(node => [node.key, node])), [layout]);
    const drawable = (loaded || !!kept) && !(isPapersLoading && !papers.length);
    const selected = selectedKey && drawable ? byKey.get(selectedKey) : undefined;

    const surface = useRef<SurfaceHandle>(null);
    // Set when the selection was made from the keyboard or from the detail: focus then goes to the detail,
    // so its actions are the next thing reached, not the hundreds of nodes after the selected one.
    const toDetail = useRef(false);
    // A section's lines to what it cites are drawn only while one end is selected: a long draft cites
    // thousands of things, and drawn all at once the lines would bury the argument and slow the canvas.
    const drafts = useMemo(() => (selected ? draftEdges(layout, byKey, selected.key) : NO_EDGES), [layout, byKey, selected]);
    const select = useCallback((key: string | null, focusDetail = false) => {
        toDetail.current = focusDetail && key !== null;
        setSelectedKey(key);
        keepView(session, projectId, { selected: key });
    }, [projectId, session]);
    const focusNode = (key: string) => window.document.querySelector<HTMLElement>(`[data-project-canvas] [data-map-key="${CSS.escape(key)}"]`)?.focus({ preventScroll: true });
    // A selection whose node is gone (archived, removed) clears.
    useEffect(() => {
        if (drawable && selectedKey && !byKey.has(selectedKey)) {
            setSelectedKey(null);
            keepView(session, projectId, { selected: null });
        }
    }, [drawable, selectedKey, byKey, projectId, session]);

    // Moves the selection to a node named in the detail and brings it into view.
    const go = (key: string) => {
        const node = byKey.get(key);
        if (!node) return;
        select(key, true);
        surface.current?.show(node);
    };

    if (isProjectLoading && !project) return <div className="mx-auto w-full max-w-4xl space-y-4 p-6"><Skeleton className="h-8 w-2/3" /><Skeleton className="h-48 w-full" /></div>;
    if (projectError) return <div role="alert" className="p-4 text-destructive">{projectError.message}</div>;
    if (!project) return <div className="p-4">Project not found.</div>;
    if (!loaded && !kept && status !== "Loading") return <div role="alert" className="p-4 text-sm text-red-700 dark:text-red-400">{status}. Reload the page to try again.</div>;
    // No paper list and none cached: an empty list here would be a guess, and findings would lose their sources.
    if (papersError && !papers.length) return <div role="alert" className="p-4 text-sm text-red-700 dark:text-red-400">Could not load this project&apos;s papers. Reload the page to try again.</div>;
    if (!drawable) return <div className="space-y-4 p-6" data-canvas-loading="true"><Skeleton className="h-8 w-1/3" /><Skeleton className="h-64 w-full" /></div>;

    // The current copy could not be loaded; what is drawn is the last one saved.
    const stale = kept && status !== "Loading"
        ? <span role="status" data-canvas-stale="true" className="text-yellow-700 dark:text-yellow-400">Last saved copy; the current one could not be loaded</span>
        : null;
    const heading = <h1 className="sr-only">Canvas: {doc.case.question.trim() || "no question yet"}</h1>;

    if (canvasIsEmpty(doc, papers)) {
        return (
            <section aria-label="Project canvas" className="mx-auto w-full max-w-2xl px-4 py-10 sm:px-6">
                {heading}
                <EmptyState icon={MapIcon} title="Nothing to map yet">
                    <p>The canvas draws the question, the claims, the findings linked to them, the papers they come from and the draft. It fills in as you work.</p>
                    <div className="flex flex-wrap gap-2">
                        <Button asChild size="sm"><Link href={`${base}/overview`}>Start with the question<ArrowRight aria-hidden className="h-4 w-4" /></Link></Button>
                        {canEdit && <Button variant="outline" size="sm" onClick={() => openAddPapers()}>Add papers</Button>}
                    </div>
                </EmptyState>
                {stale && <p className="mt-3 text-xs">{stale}</p>}
            </section>
        );
    }

    const count = (kind: CanvasNode["kind"]) => layout.nodes.reduce((sum, node) => sum + (node.kind === kind ? 1 : 0), 0);

    return (
        <section aria-label="Project canvas" className="flex min-h-0 flex-1 flex-col">
            {heading}
            <Surface
                handle={surface}
                width={layout.width}
                height={layout.height}
                nodes={layout.nodes}
                revealed={selected}
                initial={viewOf(session, projectId)?.camera}
                onLeave={camera => keepView(session, projectId, { camera })}
                fitLabel="Fit canvas to view"
                attributes={ATTRIBUTES}
                className="min-h-0 flex-1"
                toolbar={<p className="mr-auto min-w-0 truncate px-1 text-xs text-muted-foreground">{plural(count("claim"), "claim")} · {plural(count("finding"), "finding")} · {plural(count("paper"), "paper")} · {plural(count("section"), "draft section")}{stale && <> · {stale}</>}</p>}
            >
                <CanvasEdges edges={layout.edges} drafts={drafts} width={layout.width} height={layout.height} selectedKey={selected?.key ?? ""} />
                {layout.nodes.map(node => <Node key={node.key} node={node} selected={node.key === selected?.key} onSelect={select} />)}
            </Surface>
            {selected && <Detail node={selected} doc={doc} cites={layout.cites.get(selected.key)?.size ?? 0} base={base} takeFocus={toDetail} toNode={() => focusNode(selected.key)} onClose={() => { focusNode(selected.key); select(null); }} go={go} openPaper={openPaper} />}
        </section>
    );
}

// Selecting changes two nodes; the rest keep what they rendered.
const Node = memo(function Node({ node, selected, onSelect }: { node: CanvasNode; selected: boolean; onSelect: (key: string | null, focusDetail?: boolean) => void }) {
    return (
        <button
            type="button"
            data-map-node={node.kind}
            data-map-key={node.key}
            className={nodeClass(node.kind, selected)}
            style={{ left: node.x, top: node.y, width: node.w, height: node.h }}
            aria-pressed={selected}
            aria-label={`${node.name}: ${node.label}${node.tally ? ` (${tallyWords(node.tally)})` : ""}`}
            // A click with no pointer behind it came from the keyboard (Enter or Space).
            onClick={event => onSelect(selected ? null : node.key, event.detail === 0)}
        >
            {node.kind === "paper" && <FileText aria-hidden className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
            {node.kind === "section" && <PenLine aria-hidden className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
            <span className={cn("[overflow-wrap:anywhere]", node.kind === "question" ? "line-clamp-4" : node.kind === "section" ? "line-clamp-1" : "line-clamp-2")}>{node.label}</span>
            {node.tally && <Tally tally={node.tally} />}
        </button>
    );
});

const NO_EDGES: CanvasEdge[] = [];

function CanvasEdges({ edges, drafts, width, height, selectedKey }: { edges: CanvasEdge[]; drafts: CanvasEdge[]; width: number; height: number; selectedKey: string }) {
    return (
        <svg aria-hidden width={width} height={height} className="pointer-events-none absolute inset-0">
            {[...edges, ...drafts].map(edge => {
                const active = !!selectedKey && (edge.from === selectedKey || edge.to === selectedKey);
                const style = EDGE_STYLE[edge.kind];
                return <path key={edge.key} d={edge.path} fill="none" data-edge={edge.kind} data-active={active || undefined} strokeWidth={active ? 2.25 : 1.5} strokeDasharray={style.dash} className={active ? style.active : style.quiet} />;
            })}
        </svg>
    );
}

const detailLink = "rounded-sm text-left text-sm leading-6 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-ring";

// What the selected node says, and where to read or edit it.
function Detail({ node, doc, cites, base, takeFocus, toNode, onClose, go, openPaper }: {
    node: CanvasNode;
    doc: Investigation;
    /** Sections only: how many shown claims and findings it cites. */
    cites: number;
    base: string;
    /** True when this selection should move focus into the detail. */
    takeFocus: RefObject<boolean>;
    /** Returns focus to the selected node, leaving the detail open. */
    toNode: () => void;
    onClose: () => void;
    go: (key: string) => void;
    openPaper: ReturnType<typeof useProjectWorkspace>["openPaper"];
}) {
    const { papers } = useProjectWorkspace();
    const region = useRef<HTMLElement>(null);
    useEffect(() => {
        if (!takeFocus.current) return;
        takeFocus.current = false;
        region.current?.focus({ preventScroll: true });
    }, [node.key, takeFocus]);
    const shown = (kind: "claim" | "finding", id: string) => (kind === "claim" ? doc.claims : doc.findings).some(item => item.id === id && !item.archived);

    let title = "", body: React.ReactNode = null, actions: React.ReactNode = null;
    if (node.kind === "question") {
        title = "Question";
        body = <>
            <p className="text-sm leading-6 [overflow-wrap:anywhere]">{doc.case.question.trim() || "No question yet."}</p>
            {doc.case.provisional_answer.trim() && <p className="text-sm leading-6 text-muted-foreground [overflow-wrap:anywhere]"><span className="font-medium text-foreground">Provisional answer. </span>{doc.case.provisional_answer}</p>}
        </>;
        actions = <Button asChild size="sm"><Link href={`${base}/overview`}>Open Overview<ArrowRight aria-hidden className="h-4 w-4" /></Link></Button>;
    } else if (node.kind === "claim") {
        const claim = doc.claims.find(item => item.id === node.ref);
        const relations = doc.relations.filter(relation => relation.claim_id === node.ref && shown("finding", relation.finding_id));
        title = node.name;
        body = <>
            <p className="text-sm leading-6 [overflow-wrap:anywhere]">{claim?.statement.trim() || "Untitled claim."}</p>
            {relations.length > 0 && (
                <ul className="space-y-1">
                    {relations.map(relation => (
                        <li key={relation.id} className="flex items-baseline gap-2">
                            <RelationTag relation={relation.relation} className="shrink-0" />
                            <button type="button" className={detailLink} onClick={() => go(canvasKey("finding", relation.finding_id))}>{doc.findings.find(finding => finding.id === relation.finding_id)?.label.trim() || "Untitled finding"}</button>
                        </li>
                    ))}
                </ul>
            )}
        </>;
        actions = <>
            <Button asChild size="sm"><Link href={`${base}/overview?claim=${node.ref}`}>Open in Overview<ArrowRight aria-hidden className="h-4 w-4" /></Link></Button>
            <Button asChild variant="outline" size="sm"><Link href={`${base}/evidence?claim=${node.ref}`}>View its evidence</Link></Button>
        </>;
    } else if (node.kind === "finding") {
        const finding = doc.findings.find(item => item.id === node.ref);
        const relations = doc.relations.filter(relation => relation.finding_id === node.ref && shown("claim", relation.claim_id));
        const source = finding?.source;
        // Only a source with its passage leads to a paper; a redacted one names a paper but has nothing to open.
        const paper = source?.kind === "anchored" ? papers.find(item => item.id === source.paper_id) : undefined;
        title = "Finding";
        body = <>
            <p className="text-sm font-medium leading-6 [overflow-wrap:anywhere]">{finding?.label.trim() || "Untitled finding"}</p>
            {finding?.observed_result.trim() && <p className="text-sm leading-6 text-muted-foreground [overflow-wrap:anywhere]">{finding.observed_result}</p>}
            {relations.length > 0 && (
                <ul className="space-y-1">
                    {relations.map(relation => (
                        <li key={relation.id} className="flex items-baseline gap-2">
                            <RelationTag relation={relation.relation} className="shrink-0" />
                            <button type="button" className={detailLink} onClick={() => go(canvasKey("claim", relation.claim_id))}>{doc.claims.find(claim => claim.id === relation.claim_id)?.statement.trim() || "Untitled claim"}</button>
                        </li>
                    ))}
                </ul>
            )}
            <p className="text-xs leading-5 text-muted-foreground">
                {paper
                    ? <>Source: <button type="button" className="rounded-sm underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-ring" onClick={() => go(canvasKey("paper", paper.id))}>{paper.title || "Untitled paper"}</button></>
                    : "Source not available in this project."}
            </p>
        </>;
        actions = <>
            <Button asChild size="sm"><Link href={`${base}/evidence?finding=${node.ref}`}>Open in Evidence<ArrowRight aria-hidden className="h-4 w-4" /></Link></Button>
            {paper && <Button variant="outline" size="sm" onClick={() => openPaper(paper, source?.kind === "anchored" ? source.quote : null)}><BookOpen aria-hidden className="h-4 w-4" />Open source</Button>}
        </>;
    } else if (node.kind === "paper") {
        const paper = papers.find(item => item.id === node.ref);
        const drawn = doc.findings.filter(finding => !finding.archived && finding.source.kind === "anchored" && finding.source.paper_id === node.ref);
        title = "Paper";
        body = <>
            <p className="text-sm font-medium leading-6 [overflow-wrap:anywhere]">{paper?.title || "Untitled paper"}</p>
            {!!paper?.authors?.length && <p className="text-xs leading-5 text-muted-foreground [overflow-wrap:anywhere]">{paper.authors.slice(0, 6).join(", ")}{paper.authors.length > 6 ? " and others" : ""}</p>}
            {drawn.length > 0
                ? <ul className="space-y-1">{drawn.map(finding => <li key={finding.id}><button type="button" className={detailLink} onClick={() => go(canvasKey("finding", finding.id))}>{finding.label.trim() || "Untitled finding"}</button></li>)}</ul>
                : <p className="text-xs leading-5 text-muted-foreground">No findings captured from this paper yet.</p>}
        </>;
        actions = paper ? <Button size="sm" onClick={() => openPaper(paper)}><BookOpen aria-hidden className="h-4 w-4" />Open in reader</Button> : null;
    } else {
        const section = doc.manuscript.sections.find(item => item.id === node.ref);
        const blocks = section?.blocks ?? [];
        const cited = new Set(blocks.flatMap(block => block.finding_ids));
        title = node.name;
        body = <>
            <p className="text-sm font-medium leading-6 [overflow-wrap:anywhere]">{section?.title.trim() || "Untitled section"}</p>
            <p className="text-xs leading-5 text-muted-foreground">{plural(blocks.filter(block => block.kind !== "gap").length, "paragraph")}, citing {plural(cited.size, "finding")}{blocks.some(block => block.kind === "gap") ? `; ${plural(blocks.filter(block => block.kind === "gap").length, "evidence gap")}` : ""}.</p>
            {cites > DRAFT_LINE_LIMIT && <p className="text-xs leading-5 text-muted-foreground" data-canvas-capped="true">Lines are drawn to the first {DRAFT_LINE_LIMIT} of the {cites} claims and findings it cites.</p>}
        </>;
        actions = <Button asChild size="sm"><Link href={`${base}/draft#section-${node.ref}`}>Open in Write<ArrowRight aria-hidden className="h-4 w-4" /></Link></Button>;
    }

    return (
        <aside
            ref={region}
            tabIndex={-1}
            aria-label={`Selected: ${title}. Escape returns to the map.`}
            data-canvas-detail={node.kind}
            onKeyDown={event => { if (event.key === "Escape" && !event.defaultPrevented) { event.preventDefault(); toNode(); } }}
            className="max-h-[45%] shrink-0 overflow-y-auto border-t bg-background px-4 py-3 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:px-5"
        >
            <div className="mx-auto flex max-w-4xl items-start gap-3">
                <div className="min-w-0 flex-1 space-y-2">
                    <h2 className="text-xs font-medium text-muted-foreground">{title}</h2>
                    {body}
                    {actions && <div className="flex flex-wrap gap-2 pt-1">{actions}</div>}
                </div>
                <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" aria-label="Close detail" onClick={onClose}><X className="h-4 w-4" /></Button>
            </div>
        </aside>
    );
}
