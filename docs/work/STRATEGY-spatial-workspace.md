# STRATEGY: Spatial workspace (canvas feel, smoother flow, performance)

Date: 2026-11-19. Owner question: how to give the interface an infinite-canvas feel, make the flow smoother and get maximum performance, with light libraries and modern efficient technology, zero-copy data in particular.

Status: **approved by the owner as recommended, 2026-11-19.** Decision A is taken: the canvas becomes the project home. B and C keep the defaults recorded below (no hand-placed positions; desktop first, pinch supported). Slices 0 and 1 are implemented on `feat/spatial-workspace`; see [INTENT-spatial-workspace-camera.md](INTENT-spatial-workspace-camera.md) and [VERIFICATION-spatial-workspace.md](VERIFICATION-spatial-workspace.md).

Corrections from slice 0 and 1, which the text below predates:

- The two large shared chunks are pdf.js and KaTeX, not app code. The project layout chunk (167 KB, 45 modules) is where loading on demand pays.
- The camera alone met the pan and zoom target at 2,000 nodes. Culling, canvas edges and levels of detail were not needed and were not built; all nodes stay in the DOM.
- A saved brief is capped at 1 MB, so a real brief map holds a few hundred paragraphs. The 2,000-node case belongs to the project canvas.
- Mounting 2,000 nodes ("expand all") is still slow and is the first thing the project canvas intent must settle.

## Where the interface is today

- The project workspace is a fixed shell: header, left rail, route content, and one right slot shared by the reader, the brief and the artifacts (`projects/[projectId]/layout.tsx`). Overview, Evidence, Write and Discuss are separate routes inside it.
- The only spatial surface is the brief map (`components/fold/FoldMap.tsx`, 213 lines, layout in `lib/fold-map.ts`). It is a scroll container holding a scaled wrapper.
- Zoom is React state. Every Ctrl+wheel tick re-renders every node and edge and resizes the wrapper, which forces layout. There is no culling: all nodes are mounted whatever the viewport shows. Zoom is not anchored to the cursor, and there is no pinch.
- `next/dynamic` is used once in `src` (the PDF viewer). SWR is used by two hooks; project and investigation data are fetched in provider effects.
- Build of 2026-11-18, uncompressed: project layout chunk 168 KB; the two largest shared chunks are 392 KB and 264 KB and have not been attributed to packages.

No runtime measurement exists (frame times, interaction latency, transferred bytes). Every performance claim below is a design argument until slice 0 produces numbers.

## Assumptions challenged

**"Infinite canvas" for everything.** A research workspace is mostly long text: PDFs, a draft, a discussion. Putting those on a free pan-and-zoom board makes them worse to read, breaks find-in-page and screen-reader order, and turns each editor into a floating window to manage. What the owner rejected on 2026-11-18 was a text-only brief with no map, which points at wanting one spatial overview, not a whiteboard. The decision below takes that reading.

**"Zero-copy" as a goal.** It is a technique that pays where large buffers cross a boundary. OpenPaper's API responses are small JSON; the large bytes are PDFs, which already go from storage to the browser on a presigned URL without passing through the server. Applied to the wrong place (a binary wire format for small records) it adds decoder weight and removes nothing measurable.

**"Maximum performance" means a faster renderer.** The map's cost is React re-rendering during gestures and mounting off-screen nodes, not DOM being slow. A GPU renderer would fix a problem we do not have and cost text quality, selection, links and accessibility.

## Decision

### 1. One canvas per project, documents stay documents

The project gets a single spatial surface as its home: the brief tree, findings, papers, claims and draft sections as nodes, with the existing argument and citation edges. Reading and writing stay in docked panels that open from a node and return to it. Layout stays a deterministic pure function; nodes are not hand-placed.

Not chosen:

| Option | Why not |
| --- | --- |
| Map stays a view inside the Brief panel, only made smoother | Does not change how the workspace feels; kept as slice 1 because it proves the engine |
| Free-form whiteboard with user-placed nodes | Needs position storage, conflict rules for collaborators, and a server slice; revisit after the canvas is in use |

### 2. Own camera engine, no canvas library

- Camera (`x`, `y`, `zoom`) lives in a ref and a small external store, not component state. A gesture writes one CSS `transform` on one layer per animation frame. React does not commit during pan or zoom.
- Input: wheel and two-finger scroll pan; Ctrl/Cmd+wheel and pinch zoom toward the cursor; drag on background and Space+drag pan; arrow keys move between nodes and bring the focused node into view; fit and reset stay as buttons.
- Culling: only nodes intersecting the viewport plus a margin are mounted. Edges are drawn on one `<canvas>` under the nodes instead of one SVG path element each.
- Level of detail: at low zoom a node shows its title only; below that, nodes are drawn as rectangles on the edge canvas and DOM nodes are unmounted. This is what lets the surface feel unbounded.
- Nodes stay real HTML buttons and links, so focus, accessible names and text selection keep working.

Libraries considered and declined: tldraw (large, and its licence terms need checking for a hosted product), React Flow (DOM-based and sound, but we already own the layout and the previous record ruled out a graph library), d3-zoom (small, but the camera is about 150 lines of pointer handling). No runtime dependency is added for the canvas.

### 3. Zero-copy where bytes are large

Adopt:

- **Scene geometry in typed arrays.** Node boxes as one `Float32Array` (x, y, w, h per node). Culling and hit testing read it without allocating.
- **Layout in a Worker, result transferred.** `postMessage` with a transfer list moves the buffer instead of cloning it. Only worth it once slice 0 shows layout over a frame on large briefs.
- **PDF bytes by range.** Confirm the viewer requests page ranges from storage and does not download whole files before first paint.
- **Images decoded off the main thread** (`createImageBitmap` / `img.decode()`) for paper thumbnails on the canvas.

Decline:

| Technique | Reason |
| --- | --- |
| Arrow, FlatBuffers or protobuf for API responses | Payloads are small JSON; the decoder outweighs the saving, and `lib/schema.ts` stays the one hand-written type source |
| `SharedArrayBuffer` | Needs cross-origin isolation headers, which put Google sign-in, Stripe, PostHog and storage-hosted PDFs at risk; transfer covers our case |
| WebGL, WebGPU or a WASM renderer | Text-heavy nodes; loses accessibility and selection for a bottleneck we have not measured |

### 4. Flow

- **No skeleton on destination switches.** Project and investigation data move to SWR (already the sanctioned escape hatch in `client/design.md` §6): cached render first, revalidate after, prefetch on pointer intent.
- **Optimistic writes** for the small edits (reorder, attribute, link), with rollback and the existing error states.
- **Native View Transitions** for panel open and close and for node-to-panel, as progressive enhancement, off under reduced motion. This replaces the "short opacity transition is the whole animation budget" rule in `STRATEGY-native-fold-reader.md`.
- **Jump anywhere.** `cmdk` is already installed: a palette that searches nodes and moves the camera there.
- **Panels keep their state** when closed and reopened (scroll position, level, selection).

### 5. Weight

- Attribute the 392 KB and 264 KB shared chunks before choosing what to split.
- Likely candidates to load on demand: `react-syntax-highlighter`, KaTeX, Stripe, `canvas-confetti`, PostHog after first paint.
- Rule: the project route ships no more JavaScript after this work than before it.

## Targets (to be confirmed or corrected by slice 0)

| Measure | Target |
| --- | --- |
| Pan and zoom on a 2,000-node map, mid-range laptop | Display refresh rate, no React commit during the gesture |
| Destination switch with cached data | Under 100 ms to content |
| Project route JavaScript | Not above the 2026-11-18 build |

## Order

0. **Baseline.** Bundle attribution; performance trace of the map on the 50-section fixture and on a generated 2,000-node document. Numbers recorded in a verification record.
1. **Camera engine in the existing map.** Client only, no data change, inside the Brief panel. Proves decision 2.
2. **Flow.** SWR for project data, view transitions, on-demand loading. Independent of the canvas; can run alongside slice 1.
3. **Canvas as project home.** Depends on owner decision A.
4. **Pinned positions.** Only if owner decision B says so; needs a server slice.

## Material unknowns

| Unknown | Default taken | What would change it |
| --- | --- | --- |
| Whether "canvas feel" means one spatial home or a whiteboard | Spatial home, deterministic layout | Owner wants to arrange nodes by hand |
| Real node counts on real projects | Design for 2,000 | Slice 0 shows a few hundred at most; then drop level-of-detail drawing and the Worker |
| Whether layout is ever slow enough for a Worker | Not built until measured | Layout over one frame on the large fixture |
| Whether the PDF viewer already uses range requests | Unverified | It does; then nothing to do there |
| What is in the two largest shared chunks | Unattributed | Attribution shows they are framework code that cannot be split |
| Touch and tablet as a first-class target | Pinch supported, desktop first | Owner uses a tablet for this |
| View Transitions support in the owner's browsers | Progressive enhancement | None; unsupported browsers get an instant switch |

## Owner decisions

- **A.** Canvas as the project home (recommended), or only a smoother map in the Brief panel?
- **B.** Should node positions ever be hand-placed and saved?
- **C.** Is tablet or touch use a priority?

Slices 0, 1 and 2 do not depend on these answers.
