"use client";

import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef } from "react";
import type { FocusEvent as ReactFocusEvent, KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent } from "react";
import { ChevronDown, ChevronRight, Maximize, Minus, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FoldLevel, TextFoldDocument } from "@/lib/schema";
import { foldMap } from "@/lib/fold-map";
import type { MapNode } from "@/lib/fold-map";
import type { FoldContext } from "@/lib/fold-view";
import { MAX_ZOOM, MIN_ZOOM, between, clampPan, fit, neighbour, reveal, zoomAt } from "@/lib/camera";
import type { Camera, Direction, Point, Size } from "@/lib/camera";

// The folded reader's map: the document as a mind map, with argument links and
// cited findings drawn across it. OpenPaper's own; nothing is ported.
//
// The map is a surface under a camera. Moving the camera writes one transform on
// one layer; React renders only when the document, the level, the folding or the
// selection changes, never while panning or zooming.

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

const BUTTON_STEP = 1.2;
const GLIDE_MS = 160;
/** A press that moves less than this is a click, not a drag. */
const DRAG_SLOP = 4;
const ARROWS: Record<string, Direction> = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" };

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

const control = "inline-flex h-7 min-w-7 items-center justify-center rounded-md px-1.5 text-xs text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40";

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function FoldMap({ document: doc, level, context, findings, collapsed, onCollapsed, selected, onSelect, className }: FoldMapProps) {
    const marker = useId().replace(/[^a-zA-Z0-9_-]/g, "");
    const layout = useMemo(() => foldMap(doc, { level, collapsed, context, findings }), [doc, level, collapsed, context, findings]);
    const byKey = useMemo(() => new Map(layout.nodes.map(node => [node.key, node])), [layout]);

    const root = useRef<HTMLDivElement>(null);
    const viewport = useRef<HTMLDivElement>(null);
    const backdrop = useRef<HTMLDivElement>(null);
    const layer = useRef<HTMLDivElement>(null);
    const readout = useRef<HTMLSpanElement>(null);
    const zoomOutButton = useRef<HTMLButtonElement>(null);
    const zoomInButton = useRef<HTMLButtonElement>(null);

    const camera = useRef<Camera>({ x: 0, y: 0, zoom: 1 });
    const world = useRef<Size>({ width: layout.width, height: layout.height });
    const view = useRef<Size>({ width: 0, height: 0 });
    const fitted = useRef(false);
    const frame = useRef(0);
    const glide = useRef(0);
    const settle = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

    // The one write a camera move makes.
    const paint = useCallback(() => {
        frame.current = 0;
        const { x, y, zoom } = camera.current;
        if (layer.current) layer.current.style.transform = `translate3d(${Math.round(x)}px, ${Math.round(y)}px, 0) scale(${zoom})`;
    }, []);
    // Controls and the `data-zoom` readout follow the zoom the camera is heading for.
    const announce = useCallback((zoom: number) => {
        const percent = Math.round(zoom * 100);
        if (root.current) root.current.dataset.zoom = String(percent / 100);
        if (readout.current && readout.current.textContent !== `${percent}%`) readout.current.textContent = `${percent}%`;
        if (zoomOutButton.current) zoomOutButton.current.disabled = zoom <= MIN_ZOOM;
        if (zoomInButton.current) zoomInButton.current.disabled = zoom >= MAX_ZOOM;
    }, []);
    // While the camera is moving the layer is kept on the compositor; once it rests the
    // hint is dropped so text is drawn sharp at the new scale.
    const moving = useCallback(() => {
        if (layer.current && !layer.current.style.willChange) layer.current.style.willChange = "transform";
        clearTimeout(settle.current);
        settle.current = setTimeout(() => { if (layer.current) layer.current.style.willChange = ""; }, 200);
    }, []);
    const move = useCallback((next: Camera, how: "frame" | "now" | "glide" = "frame") => {
        const target = clampPan(next, world.current, view.current);
        cancelAnimationFrame(glide.current);
        glide.current = 0;
        announce(target.zoom);
        if (how === "glide" && !reducedMotion()) {
            const from = camera.current, started = performance.now();
            moving();
            const step = (now: number) => {
                const t = Math.min(1, (now - started) / GLIDE_MS);
                camera.current = t < 1 ? between(from, target, 1 - (1 - t) ** 3) : target;
                paint();
                glide.current = t < 1 ? requestAnimationFrame(step) : 0;
            };
            glide.current = requestAnimationFrame(step);
            return target;
        }
        camera.current = target;
        if (how === "frame") { moving(); if (!frame.current) frame.current = requestAnimationFrame(paint); }
        else { cancelAnimationFrame(frame.current); paint(); }
        return target;
    }, [announce, moving, paint]);

    // A folded or opened section stays where it was on screen; the rest of the map moves around it.
    const anchor = useRef<{ key: string; x: number; y: number } | null>(null);
    useLayoutEffect(() => {
        world.current = { width: layout.width, height: layout.height };
        if (!fitted.current) return;
        let next = camera.current;
        const held = anchor.current && byKey.get(anchor.current.key);
        if (held && anchor.current) next = { ...next, x: anchor.current.x - held.x * next.zoom, y: anchor.current.y - held.y * next.zoom };
        anchor.current = null;
        move(next, "now");
    }, [layout, byKey, move]);

    const picked = useRef<MapNode | undefined>(undefined);
    useLayoutEffect(() => { picked.current = selected ? byKey.get(`${selected.kind}:${selected.ref}`) : undefined; }, [selected, byKey]);

    // The first size the viewport has decides the opening view; later sizes only keep the map in sight.
    useLayoutEffect(() => {
        const box = viewport.current;
        if (!box) return;
        const measure = () => {
            view.current = { width: box.clientWidth, height: box.clientHeight };
            if (!view.current.width || !view.current.height) return;
            const first = !fitted.current;
            fitted.current = true;
            if (first) move(fit(world.current, view.current), "now");
            // Opening a paragraph's text under the map makes the map shorter; the paragraph stays in view.
            else if (picked.current) move(reveal(camera.current, picked.current, view.current), "glide");
            else move(camera.current, "now");
        };
        announce(camera.current.zoom);
        measure();
        const observer = new ResizeObserver(measure);
        observer.observe(box);
        return () => observer.disconnect();
    }, [announce, move]);
    useEffect(() => () => { cancelAnimationFrame(frame.current); cancelAnimationFrame(glide.current); clearTimeout(settle.current); }, []);

    const centre = (): Point => ({ x: view.current.width / 2, y: view.current.height / 2 });
    const zoomBy = (factor: number) => move(zoomAt(camera.current, centre(), camera.current.zoom * factor), "glide");
    const fitMap = () => move(fit(world.current, view.current), "glide");

    // Ctrl/Cmd + wheel and trackpad pinch zoom about the pointer; a plain wheel pans.
    useEffect(() => {
        const box = viewport.current;
        if (!box) return;
        const onWheel = (event: WheelEvent) => {
            const rect = box.getBoundingClientRect();
            const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? rect.height : 1;
            const dx = event.deltaX * unit, dy = event.deltaY * unit;
            const before = camera.current;
            if (event.ctrlKey || event.metaKey) {
                event.preventDefault();
                // A pinch arrives as many small steps, a wheel as a few large ones.
                const rate = Math.abs(dy) < 50 ? 0.01 : 0.001;
                move(zoomAt(before, { x: event.clientX - rect.left, y: event.clientY - rect.top }, before.zoom * Math.exp(-dy * rate)));
                return;
            }
            const sideways = event.shiftKey && !dx;
            const target = clampPan({ ...before, x: before.x - (sideways ? dy : dx), y: before.y - (sideways ? 0 : dy) }, world.current, view.current);
            // At the edge the wheel is left to whatever is behind the map.
            if (target.x === before.x && target.y === before.y) return;
            event.preventDefault();
            move(target);
        };
        box.addEventListener("wheel", onWheel, { passive: false });
        return () => box.removeEventListener("wheel", onWheel);
    }, [move]);

    // One pointer drags the map from anywhere, nodes included; two pinch it.
    const pointers = useRef(new Map<number, Point>());
    const drag = useRef<{ start: Point; moved: boolean } | null>(null);
    const swallowClick = useRef(false);
    const capture = (id: number) => { try { backdrop.current?.setPointerCapture(id); } catch { /* the pointer is already gone */ } };
    const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
        if (event.pointerType === "mouse" && event.button !== 0) return;
        const point = { x: event.clientX, y: event.clientY };
        pointers.current.set(event.pointerId, point);
        if (pointers.current.size === 1) {
            drag.current = { start: point, moved: false };
            // A press on the background can only be a drag, so it holds the pointer at once
            // and its release is seen wherever it happens.
            if (event.target === backdrop.current) capture(event.pointerId);
        } else if (drag.current) {
            drag.current.moved = true;
            for (const id of pointers.current.keys()) capture(id);
        }
    };
    const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
        const previous = pointers.current.get(event.pointerId), state = drag.current;
        if (!previous || !state) return;
        // A mouse press on a node is not held until it has moved; if it was released
        // outside the map in that time, the release never arrived here.
        if (event.pointerType === "mouse" && !event.buttons) { release(event.pointerId); return; }
        const point = { x: event.clientX, y: event.clientY };
        if (!state.moved) {
            if (Math.hypot(point.x - state.start.x, point.y - state.start.y) < DRAG_SLOP) return;
            state.moved = true;
            // The backdrop holds the pointer and shows the grabbing cursor: it has no
            // descendants, so the cursor change restyles one element and not every node.
            capture(event.pointerId);
            if (backdrop.current) backdrop.current.dataset.dragging = "true";
        }
        pointers.current.set(event.pointerId, point);
        const now = camera.current;
        if (pointers.current.size === 1) {
            move({ ...now, x: now.x + point.x - previous.x, y: now.y + point.y - previous.y });
            return;
        }
        const other = [...pointers.current].find(([id]) => id !== event.pointerId)?.[1];
        const rect = viewport.current?.getBoundingClientRect();
        if (!other || !rect) return;
        const was = { x: (previous.x + other.x) / 2, y: (previous.y + other.y) / 2 }, is = { x: (point.x + other.x) / 2, y: (point.y + other.y) / 2 };
        const spread = Math.hypot(previous.x - other.x, previous.y - other.y) || 1;
        const zoomed = zoomAt(now, { x: was.x - rect.left, y: was.y - rect.top }, now.zoom * Math.hypot(point.x - other.x, point.y - other.y) / spread);
        move({ ...zoomed, x: zoomed.x + is.x - was.x, y: zoomed.y + is.y - was.y });
    };
    const onPointerEnd = (event: ReactPointerEvent<HTMLDivElement>) => release(event.pointerId, true);
    function release(id: number, clicked = false) {
        if (!pointers.current.delete(id) || pointers.current.size) return;
        if (clicked && drag.current?.moved) {
            // The click that ends a drag must not also press the node it started on.
            swallowClick.current = true;
            setTimeout(() => { swallowClick.current = false; }, 0);
        }
        drag.current = null;
        if (backdrop.current) delete backdrop.current.dataset.dragging;
    }
    const onClickCapture = (event: ReactMouseEvent<HTMLDivElement>) => {
        if (!swallowClick.current) return;
        swallowClick.current = false;
        event.preventDefault();
        event.stopPropagation();
    };

    // Nothing here scrolls, so the camera brings a node into view when focus reaches it by
    // keyboard or from code. A press on the node itself does not: it is already under the pointer.
    const nodeOf = (target: EventTarget) => {
        const element = (target as HTMLElement).closest?.<HTMLElement>("[data-map-key]");
        return element ? byKey.get(element.dataset.mapKey || "") : undefined;
    };
    const onFocus = (event: ReactFocusEvent<HTMLDivElement>) => {
        const node = nodeOf(event.target);
        if (node && !pointers.current.size) move(reveal(camera.current, node, view.current), "glide");
    };
    const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
        if (event.ctrlKey || event.metaKey || event.altKey) return;
        const direction = ARROWS[event.key], from = direction && nodeOf(event.target);
        if (from) {
            // Arrow keys walk the map by position: along a column, or across to the nearest neighbour.
            event.preventDefault();
            const next = neighbour(layout.nodes.filter(node => node.kind !== "root" && !(node.kind === "section" && !node.children)), from, direction);
            if (next) layer.current?.querySelector<HTMLElement>(`[data-map-key="${CSS.escape(next.key)}"]`)?.focus({ preventScroll: true });
        } else if (event.key === "+" || event.key === "=") { event.preventDefault(); zoomBy(BUTTON_STEP); }
        else if (event.key === "-") { event.preventDefault(); zoomBy(1 / BUTTON_STEP); }
        else if (event.key === "0") { event.preventDefault(); fitMap(); }
    };

    const toggle = (node: MapNode) => {
        anchor.current = { key: node.key, x: node.x * camera.current.zoom + camera.current.x, y: node.y * camera.current.zoom + camera.current.y };
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
        <div ref={root} className={cn("flex min-h-0 flex-col", className)} data-fold-map="true">
            <div role="group" aria-label="Map controls" className="flex shrink-0 items-center justify-end gap-0.5 border-b px-2 py-1">
                {sections.length > 0 && (
                    <button type="button" className={cn(control, "mr-auto px-2")} onClick={() => setAll(!allOpen)}>{allOpen ? "Collapse all" : "Expand all"}</button>
                )}
                {/* The zoom controls' state and the readout are written by the camera, not by React. */}
                <button ref={zoomOutButton} type="button" className={control} aria-label="Zoom out" onClick={() => zoomBy(1 / BUTTON_STEP)}><Minus aria-hidden className="h-3.5 w-3.5" /></button>
                <span ref={readout} className="w-9 text-center text-[11px] tabular-nums text-muted-foreground" />
                <button ref={zoomInButton} type="button" className={control} aria-label="Zoom in" onClick={() => zoomBy(BUTTON_STEP)}><Plus aria-hidden className="h-3.5 w-3.5" /></button>
                <button type="button" className={control} aria-label="Fit map to panel" onClick={fitMap}><Maximize aria-hidden className="h-3.5 w-3.5" /></button>
            </div>
            {/* `overflow-clip`, not hidden: a clipped box cannot be scrolled by focus, so the camera is the only thing that moves the map. */}
            <div
                ref={viewport}
                data-map-viewport="true"
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={onPointerEnd}
                onPointerCancel={onPointerEnd}
                onClickCapture={onClickCapture}
                onFocus={onFocus}
                onKeyDown={onKeyDown}
                className="relative min-h-0 w-full flex-1 touch-none select-none overflow-clip"
            >
                <div ref={backdrop} aria-hidden className="absolute inset-0 cursor-grab bg-muted/30 data-[dragging]:cursor-grabbing" />
                <div ref={layer} className="absolute left-0 top-0 origin-top-left" style={{ width: layout.width, height: layout.height }}>
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
                </div>
            </div>
        </div>
    );
}
