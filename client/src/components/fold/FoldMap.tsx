"use client";

import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { ChevronDown, ChevronRight, Maximize, Minus, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FoldLevel, TextFoldDocument } from "@/lib/schema";
import { foldMap } from "@/lib/fold-map";
import type { MapNode } from "@/lib/fold-map";
import type { FoldContext } from "@/lib/fold-view";

// The folded reader's map: the document as a mind map, with argument links and
// cited findings drawn across it. OpenPaper's own; nothing is ported.

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

const MIN_ZOOM = 0.35;
const MAX_ZOOM = 1.6;
const clamp = (zoom: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(zoom * 100) / 100));

const NODE_STYLE: Record<MapNode["kind"], string> = {
    root: "border-blue-600 bg-blue-600 text-sm font-semibold text-white dark:border-blue-500 dark:bg-blue-500",
    section: "border-blue-200 bg-blue-50 text-sm font-medium text-blue-950 hover:border-blue-400 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-100 dark:hover:border-blue-600",
    unit: "border-border bg-card text-xs leading-[1.35] text-card-foreground hover:border-blue-400 dark:hover:border-blue-600",
    finding: "border-emerald-300 bg-emerald-50 text-xs font-medium text-emerald-950 hover:border-emerald-500 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-100",
};

const control = "inline-flex h-7 min-w-7 items-center justify-center rounded-md px-1.5 text-xs text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40";

export function FoldMap({ document: doc, level, context, findings, collapsed, onCollapsed, selected, onSelect, className }: FoldMapProps) {
    const [zoom, setZoom] = useState(1);
    const scroller = useRef<HTMLDivElement>(null);
    const marker = useId().replace(/[^a-zA-Z0-9_-]/g, "");
    const layout = useMemo(() => foldMap(doc, { level, collapsed, context, findings }), [doc, level, collapsed, context, findings]);

    const fit = useCallback(() => {
        const box = scroller.current;
        if (!box || !box.clientWidth) return;
        // Fit the width, but never so small that the text stops being readable.
        setZoom(clamp(Math.max(0.8, Math.min(1, box.clientWidth / layout.width))));
        box.scrollTo({ left: 0, top: 0 });
    }, [layout.width]);
    const fitted = useRef(false);
    useLayoutEffect(() => { if (!fitted.current) { fitted.current = true; fit(); } }, [fit]);

    // Ctrl/Cmd + wheel zooms; a plain wheel scrolls the map.
    useEffect(() => {
        const box = scroller.current;
        if (!box) return;
        const onWheel = (event: WheelEvent) => {
            if (!event.ctrlKey && !event.metaKey) return;
            event.preventDefault();
            setZoom(current => clamp(current * (event.deltaY < 0 ? 1.1 : 1 / 1.1)));
        };
        box.addEventListener("wheel", onWheel, { passive: false });
        return () => box.removeEventListener("wheel", onWheel);
    }, []);

    // Drag the background to pan.
    const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
    const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
        if (event.button !== 0 || (event.target as HTMLElement).closest("button")) return;
        const box = event.currentTarget;
        drag.current = { x: event.clientX, y: event.clientY, left: box.scrollLeft, top: box.scrollTop };
        box.setPointerCapture(event.pointerId);
    };
    const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
        if (!drag.current) return;
        event.currentTarget.scrollLeft = drag.current.left - (event.clientX - drag.current.x);
        event.currentTarget.scrollTop = drag.current.top - (event.clientY - drag.current.y);
    };
    const endDrag = () => { drag.current = null; };

    const toggle = (id: string) => {
        const next = new Set(collapsed);
        if (!next.delete(id)) next.add(id);
        onCollapsed(next);
    };
    const sections = layout.nodes.filter(node => node.kind === "section" && node.children > 0);
    const allOpen = sections.every(node => !node.collapsed);
    // Every section, including ones folded inside a collapsed parent.
    const setAll = (open: boolean) => onCollapsed(new Set(open ? [] : doc.sections.map(section => section.id)));

    // Edges that touch the selection stand out; the rest stay quiet.
    const selectedKey = selected ? `${selected.kind}:${selected.ref}` : "";

    return (
        <div className={cn("flex min-h-0 flex-col", className)} data-fold-map="true" data-zoom={zoom}>
            <div role="group" aria-label="Map controls" className="flex shrink-0 items-center justify-end gap-0.5 border-b px-2 py-1">
                {sections.length > 0 && (
                    <button type="button" className={cn(control, "mr-auto px-2")} onClick={() => setAll(!allOpen)}>{allOpen ? "Collapse all" : "Expand all"}</button>
                )}
                <button type="button" className={control} aria-label="Zoom out" disabled={zoom <= MIN_ZOOM} onClick={() => setZoom(current => clamp(current - 0.15))}><Minus aria-hidden className="h-3.5 w-3.5" /></button>
                <span className="w-9 text-center text-[11px] tabular-nums text-muted-foreground">{Math.round(zoom * 100)}%</span>
                <button type="button" className={control} aria-label="Zoom in" disabled={zoom >= MAX_ZOOM} onClick={() => setZoom(current => clamp(current + 0.15))}><Plus aria-hidden className="h-3.5 w-3.5" /></button>
                <button type="button" className={control} aria-label="Fit map to panel" onClick={fit}><Maximize aria-hidden className="h-3.5 w-3.5" /></button>
            </div>
            <div
                ref={scroller}
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={endDrag}
                onPointerCancel={endDrag}
                className="flex min-h-0 w-full flex-1 cursor-grab touch-pan-x touch-pan-y overflow-auto bg-muted/30 active:cursor-grabbing"
            >
                {/* Auto margins centre a map smaller than the panel and still let a larger one scroll from its start. */}
                <div className="m-auto shrink-0" style={{ width: layout.width * zoom, height: layout.height * zoom }}>
                    <div className="relative origin-top-left" style={{ width: layout.width, height: layout.height, transform: `scale(${zoom})` }}>
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
                                        className={cn(
                                            edge.kind === "tree" && (active ? "stroke-blue-500" : "stroke-slate-300 dark:stroke-slate-600"),
                                            edge.kind === "link" && "stroke-blue-500",
                                            edge.kind === "cites" && (active ? "stroke-emerald-600 dark:stroke-emerald-400" : "stroke-emerald-400/70 dark:stroke-emerald-600/70"),
                                        )}
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
                            const base = cn(
                                "absolute flex items-center gap-1.5 overflow-hidden rounded-xl border px-3 text-left shadow-xs outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                                NODE_STYLE[node.kind],
                                isSelected && "border-blue-500 ring-2 ring-blue-500/40",
                            );
                            if (node.kind === "root") {
                                return <div key={node.key} data-map-node="root" className={base} style={style}><span className="line-clamp-3 [overflow-wrap:anywhere]">{node.label}</span></div>;
                            }
                            if (node.kind === "section") {
                                const Chevron = node.collapsed ? ChevronRight : ChevronDown;
                                return (
                                    <button
                                        key={node.key}
                                        type="button"
                                        data-map-node="section"
                                        className={base}
                                        style={style}
                                        disabled={!node.children}
                                        aria-expanded={node.children ? !node.collapsed : undefined}
                                        aria-label={`${node.label}: ${node.children} ${node.children === 1 ? "item" : "items"}`}
                                        onClick={() => toggle(node.ref)}
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
                                    className={base}
                                    style={style}
                                    aria-pressed={isSelected}
                                    aria-label={node.kind === "finding" ? `Finding: ${node.label}` : `${node.name}: ${node.label}`}
                                    onClick={() => onSelect(isSelected ? null : { kind: node.kind as "unit" | "finding", ref: node.ref })}
                                >
                                    <span className={cn("[overflow-wrap:anywhere]", node.kind === "unit" ? "line-clamp-3" : "line-clamp-2")}>{node.label}</span>
                                </button>
                            );
                        })}
                    </div>
                </div>
            </div>
        </div>
    );
}
