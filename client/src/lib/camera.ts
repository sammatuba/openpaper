// Camera arithmetic for a pan-and-zoom surface. A world point p is drawn at
// p * zoom + (x, y) inside the viewport. Pure: no DOM, no storage, no network.

export type Camera = { x: number; y: number; zoom: number };
export type Size = { width: number; height: number };
export type Point = { x: number; y: number };
export type Box = { x: number; y: number; w: number; h: number };
export type Direction = 'left' | 'right' | 'up' | 'down';

export const MIN_ZOOM = 0.2;
export const MAX_ZOOM = 2;
/** How much of the world always stays inside the viewport, in screen pixels. */
const KEEP = 64;

export const clampZoom = (zoom: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));

/** The world can be moved freely, but never out of sight. */
export function clampPan(camera: Camera, world: Size, view: Size): Camera {
    const axis = (offset: number, extent: number, size: number) => {
        if (!(size > 0)) return offset;
        const keep = Math.min(KEEP, size / 2, extent);
        return Math.min(size - keep, Math.max(keep - extent, offset));
    };
    return { zoom: camera.zoom, x: axis(camera.x, world.width * camera.zoom, view.width), y: axis(camera.y, world.height * camera.zoom, view.height) };
}

/** Zoom so that the world point under `point` (viewport coordinates) stays under it. */
export function zoomAt(camera: Camera, point: Point, zoom: number): Camera {
    const next = clampZoom(zoom), scale = next / camera.zoom;
    return { zoom: next, x: point.x - (point.x - camera.x) * scale, y: point.y - (point.y - camera.y) * scale };
}

/**
 * The opening view: fit the width, but never so small that text stops being readable.
 * A world smaller than the viewport is centred; a larger one starts at its top-left.
 */
export function fit(world: Size, view: Size): Camera {
    if (!(view.width > 0) || !(world.width > 0)) return { x: 0, y: 0, zoom: 1 };
    const zoom = clampZoom(Math.max(0.8, Math.min(1, view.width / world.width)));
    const start = (extent: number, size: number) => (extent < size ? (size - extent) / 2 : 0);
    return { zoom, x: start(world.width * zoom, view.width), y: start(world.height * zoom, view.height) };
}

/** The smallest move that brings a world box inside the viewport, with a margin. */
export function reveal(camera: Camera, box: Box, view: Size, margin = 24): Camera {
    const axis = (offset: number, start: number, length: number, size: number) => {
        const low = start * camera.zoom + offset, high = low + length * camera.zoom;
        const pad = Math.min(margin, Math.max(0, (size - length * camera.zoom) / 2));
        // A box larger than the viewport shows its start.
        if (low < pad || high - low > size - 2 * pad) return offset + pad - low;
        if (high > size - pad) return offset + size - pad - high;
        return offset;
    };
    return { zoom: camera.zoom, x: axis(camera.x, box.x, box.w, view.width), y: axis(camera.y, box.y, box.h, view.height) };
}

/** A point part of the way from one camera to another. */
export function between(from: Camera, to: Camera, t: number): Camera {
    const mix = (a: number, b: number) => a + (b - a) * t;
    return { x: mix(from.x, to.x), y: mix(from.y, to.y), zoom: mix(from.zoom, to.zoom) };
}

/** The nearest box in a direction, for arrow-key movement. Distance across the direction counts double. */
export function neighbour<T extends Box & { key: string }>(boxes: readonly T[], from: T, direction: Direction): T | null {
    const cx = from.x + from.w / 2, cy = from.y + from.h / 2;
    const horizontal = direction === 'left' || direction === 'right';
    const sign = direction === 'left' || direction === 'up' ? -1 : 1;
    let best: T | null = null, bestScore = Infinity;
    for (const box of boxes) {
        if (box.key === from.key) continue;
        const dx = box.x + box.w / 2 - cx, dy = box.y + box.h / 2 - cy;
        const along = (horizontal ? dx : dy) * sign, across = Math.abs(horizontal ? dy : dx);
        if (along < 1) continue;
        const score = along + across * 2;
        if (score < bestScore) { best = box; bestScore = score; }
    }
    return best;
}
