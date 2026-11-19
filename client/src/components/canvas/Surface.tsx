"use client";

import { useCallback, useEffect, useImperativeHandle, useLayoutEffect, useMemo, useRef } from "react";
import type { FocusEvent as ReactFocusEvent, KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent, ReactNode, Ref } from "react";
import { Maximize, Minus, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { MAX_ZOOM, MIN_ZOOM, between, clampPan, fit, neighbour, reveal, zoomAt } from "@/lib/camera";
import type { Box, Camera, Direction, Point, Size } from "@/lib/camera";

// A surface under a camera, shared by the brief map and the project canvas.
// Moving the camera writes one transform on one layer; React renders only when
// what is drawn changes, never while panning or zooming.
//
// Whatever is drawn goes in as children, positioned in world coordinates. An
// element that stands for a node carries `data-map-key` with the node's key, so
// focus and the arrow keys can find it.

export type SurfaceNode = Box & { key: string };
export type SurfaceHandle = {
    /** Keep this node where it is on screen across the next change of layout. */
    hold: (node: SurfaceNode) => void;
    /** Bring this node into view. */
    show: (node: SurfaceNode) => void;
};

type SurfaceProps<T extends SurfaceNode> = {
    width: number;
    height: number;
    nodes: readonly T[];
    /** Nodes the arrow keys move between; all of them when not given. */
    navigable?: (node: T) => boolean;
    /** Kept in view when the surface is resized (a selection whose detail opens beside it). */
    revealed?: T;
    /** Where to open instead of the fitted view, and where to report the camera on leaving. */
    initial?: Camera;
    onLeave?: (camera: Camera) => void;
    /** Controls shown before the zoom buttons. */
    toolbar?: ReactNode;
    fitLabel: string;
    handle?: Ref<SurfaceHandle>;
    /** Attributes for the root element, which also carries `data-zoom`. */
    attributes?: Record<`data-${string}`, string>;
    className?: string;
    children: ReactNode;
};

const BUTTON_STEP = 1.2;
const GLIDE_MS = 160;
/** A press that moves less than this is a click, not a drag. */
const DRAG_SLOP = 4;
const ARROWS: Record<string, Direction> = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" };

export const surfaceControl = "inline-flex h-7 min-w-7 items-center justify-center rounded-md px-1.5 text-xs text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40";

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function Surface<T extends SurfaceNode>({ width, height, nodes, navigable, revealed, initial, onLeave, toolbar, fitLabel, handle, attributes, className, children }: SurfaceProps<T>) {
    const byKey = useMemo(() => new Map(nodes.map(node => [node.key, node])), [nodes]);

    const root = useRef<HTMLDivElement>(null);
    const viewport = useRef<HTMLDivElement>(null);
    const backdrop = useRef<HTMLDivElement>(null);
    const layer = useRef<HTMLDivElement>(null);
    const readout = useRef<HTMLSpanElement>(null);
    const zoomOutButton = useRef<HTMLButtonElement>(null);
    const zoomInButton = useRef<HTMLButtonElement>(null);

    const camera = useRef<Camera>({ x: 0, y: 0, zoom: 1 });
    /** Where the camera is heading; the same as `camera` unless it is gliding. */
    const aim = useRef<Camera>(camera.current);
    const world = useRef<Size>({ width, height });
    const view = useRef<Size>({ width: 0, height: 0 });
    const fitted = useRef(false);
    const frame = useRef(0);
    const glide = useRef(0);
    const settle = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
    const opening = useRef(initial);
    const leave = useRef(onLeave);
    useEffect(() => { leave.current = onLeave; }, [onLeave]);

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
        aim.current = target;
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

    // A held node stays where it was on screen; the rest of the surface moves around it.
    const anchor = useRef<{ key: string; x: number; y: number } | null>(null);
    useImperativeHandle(handle, () => ({
        hold: node => { anchor.current = { key: node.key, x: node.x * camera.current.zoom + camera.current.x, y: node.y * camera.current.zoom + camera.current.y }; },
        show: node => { move(reveal(camera.current, node, view.current), "glide"); },
    }), [move]);
    useLayoutEffect(() => {
        world.current = { width, height };
        if (!fitted.current) return;
        let next = camera.current;
        const held = anchor.current && byKey.get(anchor.current.key);
        if (held && anchor.current) next = { ...next, x: anchor.current.x - held.x * next.zoom, y: anchor.current.y - held.y * next.zoom };
        anchor.current = null;
        move(next, "now");
    }, [width, height, byKey, move]);

    const picked = useRef<T | undefined>(undefined);
    useLayoutEffect(() => { picked.current = revealed; }, [revealed]);

    // The first size the viewport has decides the opening view; later sizes only keep the surface in sight.
    useLayoutEffect(() => {
        const box = viewport.current;
        if (!box) return;
        const measure = () => {
            const size = { width: box.clientWidth, height: box.clientHeight };
            // The observer also reports the size it starts with. That is not a resize, and must not move a camera that was just restored.
            const old = view.current;
            const same = size.width === old.width && size.height === old.height;
            // Whether the picked node was wholly in view before this resize (or is about to be, mid-glide).
            const node = picked.current, heading = aim.current;
            const seen = !!node && old.width > 0 && old.height > 0 && (() => { const there = reveal(heading, node, old, 0); return there.x === heading.x && there.y === heading.y; })();
            view.current = size;
            if (!size.width || !size.height) return;
            const first = !fitted.current;
            fitted.current = true;
            if (first) {
                // A saved camera is restored as it was left. Otherwise the fitted view opens on the selection, if there is one.
                const start = opening.current ?? fit(world.current, size);
                move(opening.current || !node ? start : reveal(clampPan(start, world.current, size), node, size), "now");
            }
            else if (same) return;
            // Opening a node's detail beside the surface makes it smaller; the node stays in view.
            // A picked node the user has since moved away from is left where it is.
            else if (node && seen) move(reveal(heading, node, size), "glide");
            else move(heading, "now");
        };
        announce(camera.current.zoom);
        measure();
        const observer = new ResizeObserver(measure);
        observer.observe(box);
        return () => observer.disconnect();
    }, [announce, move]);
    useEffect(() => () => {
        cancelAnimationFrame(frame.current);
        cancelAnimationFrame(glide.current);
        clearTimeout(settle.current);
        if (fitted.current) leave.current?.(camera.current);
    }, []);

    const centre = (): Point => ({ x: view.current.width / 2, y: view.current.height / 2 });
    const zoomBy = (factor: number) => move(zoomAt(camera.current, centre(), camera.current.zoom * factor), "glide");
    const fitAll = () => move(fit(world.current, view.current), "glide");

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
            // At the edge the wheel is left to whatever is behind the surface.
            if (target.x === before.x && target.y === before.y) return;
            event.preventDefault();
            move(target);
        };
        box.addEventListener("wheel", onWheel, { passive: false });
        return () => box.removeEventListener("wheel", onWheel);
    }, [move]);

    // One pointer drags the surface from anywhere, nodes included; two pinch it.
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
        // outside the surface in that time, the release never arrived here.
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
            // Arrow keys walk the surface by position: along a column, or across to the nearest neighbour.
            event.preventDefault();
            const next = neighbour(navigable ? nodes.filter(navigable) : nodes, from, direction);
            if (next) layer.current?.querySelector<HTMLElement>(`[data-map-key="${CSS.escape(next.key)}"]`)?.focus({ preventScroll: true });
        } else if (event.key === "+" || event.key === "=") { event.preventDefault(); zoomBy(BUTTON_STEP); }
        else if (event.key === "-") { event.preventDefault(); zoomBy(1 / BUTTON_STEP); }
        else if (event.key === "0") { event.preventDefault(); fitAll(); }
    };

    return (
        <div ref={root} className={cn("flex min-h-0 flex-col", className)} {...attributes}>
            <div role="group" aria-label="Map controls" className="flex shrink-0 items-center justify-end gap-0.5 border-b px-2 py-1">
                {toolbar}
                {/* The zoom controls' state and the readout are written by the camera, not by React. */}
                <button ref={zoomOutButton} type="button" className={cn(surfaceControl, !toolbar && "ml-auto")} aria-label="Zoom out" onClick={() => zoomBy(1 / BUTTON_STEP)}><Minus aria-hidden className="h-3.5 w-3.5" /></button>
                <span ref={readout} className="w-9 text-center text-[11px] tabular-nums text-muted-foreground" />
                <button ref={zoomInButton} type="button" className={surfaceControl} aria-label="Zoom in" onClick={() => zoomBy(BUTTON_STEP)}><Plus aria-hidden className="h-3.5 w-3.5" /></button>
                <button type="button" className={surfaceControl} aria-label={fitLabel} onClick={fitAll}><Maximize aria-hidden className="h-3.5 w-3.5" /></button>
            </div>
            {/* `overflow-clip`, not hidden: a clipped box cannot be scrolled by focus, so the camera is the only thing that moves the surface. */}
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
                <div ref={layer} className="absolute left-0 top-0 origin-top-left" style={{ width, height }}>
                    {children}
                </div>
            </div>
        </div>
    );
}
