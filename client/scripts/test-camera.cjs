// Camera arithmetic of the map, exercised on the real TS module.
const ts = require('typescript');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
require.extensions['.ts'] = (m, filename) => m._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename);
const { MIN_ZOOM, MAX_ZOOM, clampZoom, clampPan, zoomAt, fit, reveal, between, neighbour } = require(path.resolve(__dirname, '../src/lib/camera.ts'));

const near = (a, b, message) => assert.ok(Math.abs(a - b) < 1e-9, `${message || 'near'}: ${a} vs ${b}`);
const world = { width: 2000, height: 1200 }, view = { width: 800, height: 600 };
const worldAt = (camera, point) => ({ x: (point.x - camera.x) / camera.zoom, y: (point.y - camera.y) / camera.zoom });

// Zoom keeps the world point under the cursor where it is, in and out, from any camera.
for (const camera of [{ x: 0, y: 0, zoom: 1 }, { x: -340.5, y: 87.25, zoom: 0.6 }, { x: 120, y: -900, zoom: 1.7 }]) {
    for (const point of [{ x: 0, y: 0 }, { x: 400, y: 300 }, { x: 799, y: 12 }]) {
        for (const factor of [1.1, 1 / 1.1, 1.5, 0.4]) {
            const before = worldAt(camera, point), next = zoomAt(camera, point, camera.zoom * factor), after = worldAt(next, point);
            near(after.x, before.x, 'x under the cursor'); near(after.y, before.y, 'y under the cursor');
            near(next.zoom, clampZoom(camera.zoom * factor));
        }
    }
}
// Zoom stops at its limits, and still keeps the point fixed at the limit.
assert.equal(zoomAt({ x: 0, y: 0, zoom: 1 }, { x: 10, y: 10 }, 99).zoom, MAX_ZOOM);
assert.equal(zoomAt({ x: 0, y: 0, zoom: 1 }, { x: 10, y: 10 }, 0.0001).zoom, MIN_ZOOM);
assert.deepEqual(zoomAt({ x: 5, y: 7, zoom: MAX_ZOOM }, { x: 300, y: 200 }, 10), { x: 5, y: 7, zoom: MAX_ZOOM });

// Pan is free, but some of the world always stays in view.
const visible = camera => {
    const right = camera.x + world.width * camera.zoom, bottom = camera.y + world.height * camera.zoom;
    return Math.min(right, view.width) - Math.max(camera.x, 0) >= 64 - 1e-9 && Math.min(bottom, view.height) - Math.max(camera.y, 0) >= 64 - 1e-9;
};
for (const zoom of [MIN_ZOOM, 0.5, 1, MAX_ZOOM]) {
    for (const [x, y] of [[1e6, 1e6], [-1e6, -1e6], [1e6, -1e6], [0, 0], [-500, 200]]) assert.ok(visible(clampPan({ x, y, zoom }, world, view)), `visible at ${zoom} from ${x},${y}`);
}
assert.deepEqual(clampPan({ x: -300, y: -100, zoom: 1 }, world, view), { x: -300, y: -100, zoom: 1 }, 'a camera already in range is not moved');
// A world smaller than the keep margin stays wholly inside.
assert.deepEqual(clampPan({ x: 900, y: -50, zoom: 1 }, { width: 40, height: 30 }, view), { x: 760, y: 0, zoom: 1 });
// A viewport with no size yet moves nothing and divides by nothing.
assert.deepEqual(clampPan({ x: 12, y: 34, zoom: 1 }, world, { width: 0, height: 0 }), { x: 12, y: 34, zoom: 1 });
assert.deepEqual(fit(world, { width: 0, height: 0 }), { x: 0, y: 0, zoom: 1 });
assert.deepEqual(fit({ width: 0, height: 0 }, view), { x: 0, y: 0, zoom: 1 });

// Fit: readable first. A wide world starts at its top-left at 80%; a small one is centred at 100%.
assert.deepEqual(fit(world, view), { x: 0, y: 0, zoom: 0.8 });
assert.deepEqual(fit({ width: 900, height: 2000 }, view), { x: 0, y: 0, zoom: 800 / 900 });
assert.deepEqual(fit({ width: 400, height: 200 }, view), { x: 200, y: 200, zoom: 1 });
assert.deepEqual(fit({ width: 400, height: 2000 }, view), { x: 200, y: 0, zoom: 1 });

// Reveal: the smallest move; nothing when the box is already inside.
const still = { x: -100, y: -50, zoom: 1 };
assert.deepEqual(reveal(still, { x: 200, y: 200, w: 100, h: 50 }, view), still);
assert.deepEqual(reveal(still, { x: 1500, y: 200, w: 100, h: 50 }, view), { x: -824, y: -50, zoom: 1 }, 'right edge lands a margin inside');
assert.deepEqual(reveal(still, { x: 0, y: 0, w: 100, h: 50 }, view), { x: 24, y: 24, zoom: 1 }, 'left and top land a margin inside');
assert.deepEqual(reveal({ x: 0, y: 0, zoom: 2 }, { x: 600, y: 0, w: 100, h: 50 }, view), { x: -624, y: 24, zoom: 2 }, 'zoom is counted');
// A box wider than the viewport shows its start, without a margin it has no room for.
assert.deepEqual(reveal({ x: -500, y: 0, zoom: 1 }, { x: 100, y: 100, w: 1000, h: 50 }, view), { x: -100, y: 0, zoom: 1 });

// Tween ends are exact.
const a = { x: 0, y: 10, zoom: 1 }, b = { x: 100, y: -10, zoom: 2 };
assert.deepEqual(between(a, b, 0), a); assert.deepEqual(between(a, b, 1), b);
assert.deepEqual(between(a, b, 0.5), { x: 50, y: 0, zoom: 1.5 });

// Arrow keys: along a column, across to the nearest in the next column, and nowhere at an edge.
const box = (key, x, y) => ({ key, x, y, w: 100, h: 40 });
const boxes = [box('root', 0, 100), box('s1', 150, 40), box('s2', 150, 160), box('u1', 300, 0), box('u2', 300, 50), box('u3', 300, 160)];
const go = (key, direction) => neighbour(boxes, boxes.find(item => item.key === key), direction)?.key ?? null;
assert.equal(go('u1', 'down'), 'u2'); assert.equal(go('u2', 'down'), 'u3'); assert.equal(go('u3', 'up'), 'u2');
assert.equal(go('s1', 'right'), 'u2'); assert.equal(go('u3', 'left'), 's2'); assert.equal(go('s2', 'left'), 'root');
assert.equal(go('root', 'left'), null); assert.equal(go('u3', 'right'), null); assert.equal(go('u1', 'up'), null);
assert.equal(go('s1', 'down'), 's2');

console.log('camera: ok');
