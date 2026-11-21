# VERIFICATION: Spatial workspace, slices 0 and 1

Date: 2026-11-19. Intent: [INTENT-spatial-workspace-camera.md](INTENT-spatial-workspace-camera.md). Branch: `feat/spatial-workspace` from `feat/native-fold-reader` at `593be74f`. Client only. Not committed, not pushed, not deployed.

## What changed

- `client/src/lib/camera.ts` (new): pure camera arithmetic.
- `client/src/components/fold/FoldMap.tsx`: the map is a surface under a camera. A move writes one `transform` on one layer; React does not render during pan or zoom.
- `client/scripts/`: `test-camera.cjs`, `measure-bundle.cjs`, `measure-map.cjs`, `check-map-touch.cjs` (new); two journeys adjusted (below).
- `client/package.json`: `test-camera` joins `test:textfold`; `test:map-touch:browser`, `measure:bundle`, `measure:map` added.

Behaviour a reader will notice:

- Ctrl/Cmd+wheel and trackpad pinch zoom about the pointer. Range is 20% to 200% (was 35% to 160%).
- A drag pans from anywhere, nodes included; a drag that starts on a node does not press it.
- Touch: one finger pans, two pinch, a tap presses.
- Keyboard, with focus on a node: arrow keys move to the nearest node in that direction; `+`, `-` and `0` zoom and fit.
- Focus reaching a node by keyboard or from code brings it into view.
- Folding or opening a section keeps that section where it was on screen.
- A selected paragraph stays in view when its text opens under the map.
- The map no longer scrolls and has no scrollbars.

## Slice 0: baseline

### Bundle (`node scripts/measure-bundle.cjs`, production build of `593be74f`)

107 chunks with source maps: 3,883.6 KB raw, 1,177.9 KB gzip.

| Package | Raw KB |
| --- | --- |
| App code (`src/`) | 1,194.6 |
| Next client runtime | 589.9 |
| pdfjs-dist | 526.6 |
| KaTeX | 259.2 |
| react-dom (two copies: framework chunk and Next's compiled copy) | 174.2 + 172.8 |
| posthog-js | 169.8 |
| zod | 97.1 |
| react-syntax-highlighter | 35.5 |

The two large shared chunks the strategy left unattributed are pdf.js (389 KB) and KaTeX (262 KB). The project layout chunk is 166.7 KB raw, 47.2 KB gzip, all app code: 45 modules, including the artifacts panel, chart composer, add-papers sheet and audio cards, which load with every project route whether or not they are opened.

### Map (`node scripts/measure-map.cjs 50x4,100x19 4`)

Headless Chromium 1234 at 1440×960 on the local production build, API mocked, CPU slowed 4×. Each gesture is 60 input steps. Three runs each; the table gives the range. "Script" is main-thread script time over the whole gesture.

| Map | Gesture | | React commits | Script ms | Frames over 33 ms | Longest frame ms | Long tasks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 251 nodes | Zoom | before | 59–60 | 339–997 | 0–24 | 17–100 | 0–11 |
| | | after | 0 | 71–81 | 0 | 17–33 | 0 |
| | Pan, wheel | before | 0 | 60–123 | 0–3 | 17–50 | 0–1 |
| | | after | 0 | 66–91 | 0 | 17 | 0 |
| | Pan, drag | before | 0 | 46–55 | 1 | 50–133 | 1 |
| | | after | 0 | 63–82 | 0 | 17 | 0 |
| 2,001 nodes | Zoom | before | 60 | 1,161–1,297 | 9–18 | 50–83 | 0–1 |
| | | after | 0 | 76–85 | 0–1 | 33 | 0 |
| | Pan, wheel | before | 0 | 52–63 | 0 | 17 | 0 |
| | | after | 0 | 55–79 | 0 | 17 | 0 |
| | Pan, drag | before | 0 | 47–59 | 2 | 417–450 | 2 |
| | | after | 0 | 71–79 | 0 | 17 | 0 |

Findings:

- Zoom was one React commit per wheel step. It is now none.
- Wheel pan was already smooth (native scrolling) and stays smooth as a transform.
- Every drag started with a freeze of about 430 ms on the large map: the grab cursor changed on the scroll container and, because `cursor` inherits, restyled every node (800–852 ms of style work at 4× slowdown). The cursor now lives on an empty backdrop element; the freeze is gone.
- "Expand all" on 2,001 nodes took 1.5–5.2 s before and 1.2–3.9 s after at 4× slowdown. The ranges overlap; no improvement is claimed. This is the cost of mounting 2,000 nodes and is the open item for the project canvas.

### Other findings from the baseline

- A saved brief is capped at 1 MB (`parseTextFold`). With real paragraph text, each stored about four times across the levels, that is a few hundred paragraphs. A 2,000-node brief map is reachable only with very short text; the 2,000-node target matters for the project canvas (papers, findings, claims), not for the brief map.
- `next/dynamic` is used once in `src`. The project layout chunk is the place where loading on demand will pay.

## Slice 1: decisions made by measurement

| Technique from the strategy | Built | Reason |
| --- | --- | --- |
| Camera outside React, one transform | Yes | Zoom commits 60 → 0 |
| Skip off-screen rendering (`content-visibility` or unmounting) | No | Pan and zoom meet the target with all 2,001 nodes mounted |
| Edges on a `<canvas>` | No | Same; SVG paths stay, so the journeys' edge selectors are unchanged |
| Title-only and rectangle levels of detail | No | Same |
| Layout in a Worker | No | Out of scope; layout was not isolated from mounting in this measurement |

All nodes stay in the DOM, in tab order and in the accessibility tree.

## Checks run on the final build

| Check | Result |
| --- | --- |
| `npx tsc --noEmit` | Pass |
| `npx eslint` on `FoldMap.tsx`, `camera.ts` and the four new scripts | Pass |
| `npm run test:textfold` (now includes `test-camera.cjs`; `test-fold-map.cjs` untouched) | Pass |
| `npm run build` | Pass |
| `npm run test:research-overview:browser`, 1440 and 390 | Pass |
| `npm run test:investigation:browser`, both widths | Pass |
| `npm run test:project-workflow:browser`, 1440 and 390 | Pass |
| `npm run test:map-touch:browser` (390×844 touch context) | Pass: one-finger pan from a node without pressing it, pinch out and in, page not zoomed or scrolled, tap presses |
| `node scripts/measure-map.cjs 50x4,100x19 4` | Zero React commits during zoom and both pans, at both sizes |
| `git diff --check` | Clean |

New assertions in the research-overview journey, both widths: fit returns to the opening zoom; after Ctrl+wheel the point under the pointer is within 2 px of where it was and the page itself is not zoomed; a drag that starts on a node moves the map and does not select the node; a press released outside the map does not leave the map following the pointer; a focused off-screen node is brought into view with no container scrolled; arrow keys move between nodes; `+`, `-`, `0` zoom and fit.

Screenshots from the journeys were looked at for 1440 (map) and 390 (map with a paragraph open).

## Journey changes

The old map scrolled, so a test could click a node outside the visible area and the browser scrolled to it. The new map does not scroll. Three steps in `check-project-research-overview.cjs` and one in `check-investigation-workspace.cjs` now focus the node before clicking it, which brings it into view the way Tab does. No selector changed.

## A defect found and fixed during the work

The first version left a drag half-open when the mouse was pressed on a node and released outside the map before moving 4 px; the map then followed the pointer on hover. Found by the new drag assertion. Fixed two ways: a press on the background holds the pointer at once, and a mouse move with no button down ends any open drag. The journey covers it.

## Bundle after

Project layout chunk: 172.6 KB raw, 49.1 KB gzip (before: 166.7 and 47.2). The increase, 5.9 KB raw and 1.9 KB gzip, is the camera module and the larger map component. Total: 3,889.6 KB raw, 1,179.9 KB gzip. The strategy's rule that the project route ends no heavier than it started is not yet met; the flow slice is expected to recover far more than this by loading the layout's panels on demand.

## Not verified

- Frame times are main-thread only. Raster and compositor cost is not measured, and nothing was measured on a real GPU, a real phone or a real trackpad. Pinch on a trackpad arrives as Ctrl+wheel and is covered by that path; a physical pinch was not tried.
- Only Chromium. Firefox and Safari were not run.
- Text sharpness after zooming was looked at in screenshots at 82% and 93%, not at every scale.
- Screen-reader behaviour was not tested with a screen reader; the accessible names and roles are unchanged.
- Three pre-existing files under `client/scripts/` fail eslint (`generate-blog-metadata.js`, `test-investigation.cjs`, `test-textfold.cjs`). Not touched.
- Not signed in to the deployed product; nothing deployed.

## Next

1. Owner: review and say whether to commit, push and open a pull request for `feat/spatial-workspace`.
2. Flow slice (strategy order 2): load the project layout's panels on demand, move project data to SWR, view transitions. Needs its own intent.
3. Project canvas (strategy order 3, owner decision A taken): its intent must settle the mount cost of large maps first, since "expand all" at 2,000 nodes is the one number this slice did not move.
