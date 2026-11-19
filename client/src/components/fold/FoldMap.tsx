"use client";

import { useId, useMemo, useRef } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FoldLevel, TextFoldDocument } from "@/lib/schema";
import { foldMap } from "@/lib/fold-map";
import type { MapNode } from "@/lib/fold-map";
import type { FoldContext } from "@/lib/fold-view";
import { Surface, surfaceControl } from "@/components/canvas/Surface";
import type { SurfaceHandle } from "@/components/canvas/Surface";

// The folded reader's map: the document as a mind map, with argument links and
// cited findings drawn across it. OpenPaper's own; nothing is ported.
//
// The camera, the gestures and the keyboard are the shared Surface's; this file
// decides what is drawn. React renders only when the document, the level, the
// folding or the selection changes, never while panning or zooming.

export type MapSelection = { kind: "unit" | "finding"; ref: string } | null;

type FoldMapProps = {
    document: TextFoldDocument;
    level: FoldLevel;
    context: FoldContext;
    /** Draw cited findings as shared nodes. */
    findings: boolean;
    /** Folded sections; kept by the reader so they survive a switch to the text and back. */
    collapsed: ReadonlySet<string>;
    onCollapsed: (collapsed: Set<string>) => void;
    selected: MapSelection;
    onSelect: (selection: MapSelection) => void;
    className?: string;
};

const ATTRIBUTES = { "data-fold-map": "true" } as const;
// Arrow keys skip the title and sections with nothing to fold.
const navigable = (node: MapNode) => node.kind !== "root" && !(node.kind === "section" && !node.children);

const NODE_STYLE: Record<MapNode["kind"], string> = {
    root: "border-blue-600 bg-blue-600 text-sm font-semibold text-white dark:border-blue-500 dark:bg-blue-500",
    section: "border-blue-200 bg-blue-50 text-sm font-medium text-blue-950 hover:border-blue-400 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-100 dark:hover:border-blue-600",
    unit: "border-border bg-card text-xs leading-[1.35] text-card-foreground hover:border-blue-400 dark:hover:border-blue-600",
    finding: "border-emerald-300 bg-emerald-50 text-xs font-medium text-emerald-950 hover:border-emerald-500 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-100",
};
// One class string per kind and state, not one merge per node per render.
const nodeClasses = new Map<string, string>();
function nodeClass(kind: MapNode["kind"], selected: boolean) {
    const id = `${kind}:${selected}`;
    let value = nodeClasses.get(id);
    if (!value) {
        value = cn(
            "absolute flex items-center gap-1.5 overflow-hidden rounded-xl border px-3 text-left shadow-xs outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
            NODE_STYLE[kind],
            selected && "border-blue-500 ring-2 ring-blue-500/40",
        );
        nodeClasses.set(id, value);
    }
    return value;
}

export function FoldMap({ document: doc, level, context, findings, collapsed, onCollapsed, selected, onSelect, className }: FoldMapProps) {
    const marker = useId().replace(/[^a-zA-Z0-9_-]/g, "");
    const layout = useMemo(() => foldMap(doc, { level, collapsed, context, findings }), [doc, level, collapsed, context, findings]);
    const byKey = useMemo(() => new Map(layout.nodes.map(node => [node.key, node])), [layout]);

    const surface = useRef<SurfaceHandle>(null);
    const picked = selected ? byKey.get(`${selected.kind}:${selected.ref}`) : undefined;

    const toggle = (node: MapNode) => {
        // The folded or opened section stays where it was on screen.
        surface.current?.hold(node);
        const next = new Set(collapsed);
        if (!next.delete(node.ref)) next.add(node.ref);
        onCollapsed(next);
    };
    const sections = layout.nodes.filter(node => node.kind === "section" && node.children > 0);
    const allOpen = sections.every(node => !node.collapsed);
    // Every section, including ones folded inside a collapsed parent.
    const setAll = (open: boolean) => onCollapsed(new Set(open ? [] : doc.sections.map(section => section.id)));

    // Edges that touch the selection stand out; the rest stay quiet.
    const selectedKey = selected ? `${selected.kind}:${selected.ref}` : "";

    return (
        <Surface
            handle={surface}
            width={layout.width}
            height={layout.height}
            nodes={layout.nodes}
            navigable={navigable}
            revealed={picked}
            fitLabel="Fit map to panel"
            attributes={ATTRIBUTES}
            className={className}
            toolbar={sections.length > 0 && (
                <button type="button" className={cn(surfaceControl, "mr-auto px-2")} onClick={() => setAll(!allOpen)}>{allOpen ? "Collapse all" : "Expand all"}</button>
            )}
        >
            <svg aria-hidden width={layout.width} height={layout.height} className="pointer-events-none absolute inset-0">
                <defs>
                    <marker id={`${marker}-link`} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                        <path d="M0,0 L8,4 L0,8 z" className="fill-blue-500" />
                    </marker>
                </defs>
                {layout.edges.map(edge => {
                    const active = !!selectedKey && (edge.from === selectedKey || edge.to === selectedKey);
                    return (
                        <path
                            key={edge.key}
                            d={edge.path}
                            fill="none"
                            data-edge={edge.kind}
                            strokeWidth={active ? 2 : 1.5}
                            strokeDasharray={edge.kind === "link" ? "5 4" : undefined}
                            markerEnd={edge.kind === "link" ? `url(#${marker}-link)` : undefined}
                            className={
                                edge.kind === "tree" ? (active ? "stroke-blue-500" : "stroke-slate-300 dark:stroke-slate-600")
                                    : edge.kind === "link" ? "stroke-blue-500"
                                        : (active ? "stroke-emerald-600 dark:stroke-emerald-400" : "stroke-emerald-400/70 dark:stroke-emerald-600/70")
                            }
                        />
                    );
                })}
            </svg>
            {layout.edges.filter(edge => edge.kind === "link").map(edge => (
                <span
                    key={edge.key}
                    aria-hidden
                    className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 whitespace-nowrap rounded-full border border-blue-200 bg-background px-1.5 py-px text-[10px] font-medium text-blue-700 dark:border-blue-800 dark:text-blue-300"
                    style={{ left: edge.labelX, top: edge.labelY }}
                >
                    {edge.rel}
                </span>
            ))}
            {layout.nodes.map(node => {
                const isSelected = node.key === selectedKey;
                const style = { left: node.x, top: node.y, width: node.w, height: node.h };
                const base = nodeClass(node.kind, isSelected);
                if (node.kind === "root") {
                    return <div key={node.key} data-map-node="root" data-map-key={node.key} className={base} style={style}><span className="line-clamp-3 [overflow-wrap:anywhere]">{node.label}</span></div>;
                }
                if (node.kind === "section") {
                    const Chevron = node.collapsed ? ChevronRight : ChevronDown;
                    return (
                        <button
                            key={node.key}
                            type="button"
                            data-map-node="section"
                            data-map-key={node.key}
                            className={base}
                            style={style}
                            disabled={!node.children}
                            aria-expanded={node.children ? !node.collapsed : undefined}
                            aria-label={`${node.label}: ${node.children} ${node.children === 1 ? "item" : "items"}`}
                            onClick={() => toggle(node)}
                        >
                            <span className="line-clamp-2 min-w-0 flex-1 [overflow-wrap:anywhere]">{node.label}</span>
                            {node.children > 0 && (
                                <span className="flex shrink-0 items-center text-[11px] font-normal opacity-70">
                                    {node.collapsed && node.children}<Chevron aria-hidden className="h-3.5 w-3.5" />
                                </span>
                            )}
                        </button>
                    );
                }
                return (
                    <button
                        key={node.key}
                        type="button"
                        data-map-node={node.kind}
                        data-map-key={node.key}
                        className={base}
                        style={style}
                        aria-pressed={isSelected}
                        aria-label={node.kind === "finding" ? `Finding: ${node.label}` : `${node.name}: ${node.label}`}
                        onClick={() => onSelect(isSelected ? null : { kind: node.kind as "unit" | "finding", ref: node.ref })}
                    >
                        <span className={node.kind === "unit" ? "line-clamp-3 [overflow-wrap:anywhere]" : "line-clamp-2 [overflow-wrap:anywhere]"}>{node.label}</span>
                    </button>
                );
            })}
        </Surface>
    );
}
