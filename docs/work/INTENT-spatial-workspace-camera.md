# INTENT: Spatial workspace, slices 0 and 1 (baseline, camera engine)

Date: 2026-11-19. Strategy: [STRATEGY-spatial-workspace.md](STRATEGY-spatial-workspace.md), approved by the owner as recommended on 2026-11-19 (decision A: canvas as the project home; B and C keep the recorded defaults). Branch: `feat/spatial-workspace` from `feat/native-fold-reader`. Client only.

## Outcome

1. **Baseline.** Numbers exist for the map before any change: where the shipped JavaScript comes from, and what a pan and a zoom cost on a 250-node and a 2,000-node map.
2. **Camera.** Panning and zooming the brief map does no React work. Zoom follows the cursor, pinch works, and the map can be moved with wheel, drag and the keyboard. The same measurement is repeated and recorded beside the baseline. (Amended during implementation: a drag pans from anywhere, nodes included, so Space+drag was not needed and is not built.)

## Scope

Add:

- `client/scripts/measure-bundle.cjs`: attributes built chunks to packages from the production source maps. Prints a table; no dependency.
- `client/scripts/measure-map.cjs`: opens the brief map on a local production build with a mocked API (the existing journey pattern), generates documents of a given size, drives zoom and pan, and reports frame times, long tasks and React commits during the gesture.
- `client/src/lib/camera.ts`: pure camera arithmetic (zoom about a point, clamp, fit, bring a box into view). No DOM.
- `client/scripts/test-camera.cjs` for it, joined to `test:textfold`.
- `docs/work/VERIFICATION-spatial-workspace.md`: the baseline and after numbers, and what was run.

Change:

- `client/src/components/fold/FoldMap.tsx`: camera held in a ref and written to one transformed layer per animation frame; the percentage readout and `data-zoom` update without re-rendering nodes.

## Decided by measurement, not in advance

The strategy named three further techniques. Each is built only if the camera alone misses the target on the 2,000-node map, and the verification record says which were needed:

- skipping off-screen rendering (preferred form: `content-visibility`, which keeps every node in the DOM, in tab order and in the accessibility tree; unmounting is the fallback);
- drawing edges on a `<canvas>` instead of SVG paths;
- title-only and rectangle levels of detail.

## Boundaries

- No change to `lib/fold-map.ts` layout output, to the document format, to any API or to the server.
- No new runtime dependency.
- Every node stays a real button or link with its accessible name. Nothing reachable by keyboard today becomes unreachable.
- No storage: the camera position is not persisted.
- Selectors the journeys use stay valid (`data-fold-map`, `data-zoom`, `data-map-node`, `path[data-edge]`, the control names) unless a measured need removes SVG edges, in which case the journeys change in the same commit.
- Not in this slice: the canvas as project home, SWR, view transitions, on-demand loading, a layout Worker.

## Failure cases to handle

- Panel resized or opened at zero width: no division by zero; fit runs when a size exists.
- Map smaller than the viewport: centred when it opens and on fit. (Amended during implementation: it can then be moved freely, like a larger map, because locking it in the centre would break zoom-to-cursor.)
- Any map: pan is clamped so some of the map always remains visible.
- Ctrl+wheel must not zoom the browser page; a plain wheel over the map must not trap the page when the map cannot move further.
- Document or level change while zoomed: the camera is kept if the layout still fits it, refitted otherwise.
- Reduced motion: no animated camera moves.
- Touch: one finger pans, two fingers pinch; a tap on a node still activates it.
- Pointer released outside the map, or the gesture cancelled: the drag ends.

## Observable checks

| Check | How |
| --- | --- |
| Camera arithmetic: zoom keeps the point under the cursor fixed; clamps hold; fit and bring-into-view are correct | `node scripts/test-camera.cjs` |
| Layout unchanged | `node scripts/test-fold-map.cjs` passes untouched |
| Types, lint, build | `tsc --noEmit`, eslint on touched paths, `npm run build` |
| No React commit during a gesture | `measure-map.cjs` reports zero commits while zooming and panning |
| Frame cost | `measure-map.cjs` before and after at 250 and 2,000 nodes; after is recorded against the strategy target |
| Zoom to cursor | Journey: the node under the pointer is under the pointer after Ctrl+wheel, within 2 px |
| Keyboard | Journey: Tab to a node outside the viewport brings it into view; plus, minus and 0 zoom and fit while focus is in the map |
| Existing journeys | `test:research-overview:browser`, `test:investigation:browser`, `test:project-workflow:browser` pass at both widths |
| Bundle | Project layout chunk no larger than the 2026-11-18 build beyond the camera module itself; figure recorded |

## Not authorised by this intent

Push, pull request, deploy.
