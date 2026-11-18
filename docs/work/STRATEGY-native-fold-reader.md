# STRATEGY: Native folded reader (replace the embedded Textfold engine)

Date: 2026-11-18. Owner direction: recreate folded reading inside OpenPaper instead of embedding Textfold, credit the upstream project, and be decisive about the internal implementation.

## Decision

OpenPaper stops shipping and adapting the upstream Textfold reader. Folded reading becomes an ordinary OpenPaper React component that renders a `textfold/doc` v0 document directly with the app's own Markdown renderer, tokens and controls.

- **Removed:** `client/public/vendor/textfold/`, `client/src/lib/textfold-native/` (the generated 805 KB engine), `client/src/lib/textfold-upstream.tsx` (the adapter to upstream's internal token format), `TextFoldReader.tsx` (iframe host), `NativeTextfold.tsx` (shadow-root host), `build-textfold-native.cjs`, `check-textfold-native.cjs`, `check-textfold-vendor.cjs`.
- **Kept unchanged:** the `textfold/doc` v0 data format as OpenPaper's stored and interchange format: `client/src/lib/textfold.ts` (parse, serialize, `foldMarkdown`), `server/app/schemas/textfold.py`, saved `research_brief` values, JSON import and export. No migration.
- **One reader, two call sites:** the Discuss working brief (`ProjectResearchOverview`) and the folded previews on Overview, Evidence and Write (`FoldedPreview`) use the same component.
- **No port.** No upstream JavaScript, CSS, markup or translation strings are copied or adapted. The new reader is written from the format and from our own product requirements.

This supersedes invariant 8 of `STRATEGY-ai-native-research-platform.md` ("the existing native Textfold engine ... is retained ... not ... an imitation"), criterion C11 as worded there, and the instruction in `HANDOFF-investigation-workspace.md` not to replace the engine. What survives from those is the product promise, restated below, not the engine.

## Why the embed worked against us

| Cost | Evidence in the tree |
| --- | --- |
| Two different embeddings of one reader | Iframe with a document assembled from a fetched template on Discuss; shadow root for the previews |
| The "native" engine is a rewritten foreign program | `build-textfold-native.cjs` turns upstream's page script into a function with about 40 text replacements and a syntax-tree pass (`document.body` → `scope.surface`, `setTimeout` → `scope.delay`, every `.then` wrapped). Any upstream change can break it without a type error |
| It cannot follow `client/design.md` | Its own top bar, zoom footer, fonts, colours and settings panel; the shadow root and iframe block the app's tokens, so we restyle with `!important` hide lists and a hand-copied palette |
| Weight | 805 KB engine, of which about 350 KB is translations for a product surface we hide; plus 760 KB of vendored assets served from `public/` |
| Security surface | The iframe needs `allow-scripts allow-same-origin` with inline scripts; the shadow host needs sanitising of upstream-shaped HTML strings |
| Research text in browser storage | The engine keeps notes and highlights in `localStorage`. Review round 1 of the guided shell treated research text in browser storage as a defect elsewhere |
| A lossy adapter | Our document is converted to upstream word tokens and realigned; when Markdown crosses a sentence boundary the adapter gives up and shows the full paragraph with a warning |
| Tests bound to upstream internals | Journeys click `#zoombar button[data-l="2"]` and read `.u[data-u="op-u-0-0"] .tx .hl` |
| It taxes every later slice | Each guided-shell slice has to carry two-instance isolation, 20-remount cleanup, keyboard isolation and theme regressions for code we do not own |

## What the native reader is

The product promise that stays:

1. Five levels: Topic, Takeaway, Key, Brief, Full.
2. Full and Brief are source wording. Brief shows the quoted source sentences; Full renders the unit's Markdown, with document-wide reference links working.
3. Topic, Takeaway and Key are labelled by origin: local excerpt, provided, or AI-written with the model name.
4. A summary can always be opened to the source sentences it rests on.
5. Folding, navigation and export make no request and no model call.
6. In the draft preview each paragraph shows its attribution (human, AI-authored needing review, imported, exact quotation, gap) and its finding links, which go to Evidence.

Decisions on shape:

- A level control for the whole document (a labelled five-option group; keys 1–5 only while focus is inside the reader) and a per-paragraph control to open one paragraph further without changing the rest.
- At Topic the reader is an outline: section titles with their topic lines, which replaces the upstream map view. Argument links in the document are listed on the paragraph they start from as in-page links.
- Attribution and finding links are rendered from `unit.provenance` and `unit.finding_ids` as real labels and Next links, not as sentences injected into the folded Markdown and intercepted clicks.
- A unit that is not prose (table, fenced code, list) shows Full at Brief. This replaces the alignment warning.
- Level changes re-render. A short opacity transition that respects reduced motion is the whole animation budget.
- Plain DOM in the page: no iframe, no shadow root, no `dangerouslySetInnerHTML`, no `localStorage`.

Deliberately dropped: word-morph animation, pinch and gesture zoom, the map canvas, the typography and settings panel, upstream's translations, browser-local notes and highlights, and "Export local reader annotations". Existing local highlights in a browser are not migrated; the keys are left in place and nothing reads them. Shared annotation belongs to the platform's comment model, not a reader-private store.

## Licence and credit

Upstream is **Apache-2.0** (Xia Chen, `chenxiachan/textfold`), not MIT. Consequences:

- Because nothing is ported, the vendored `LICENSE` and `NOTICE` leave with the vendored code and no Apache redistribution duty remains. Implementing a published data format carries no licence obligation.
- Credit is given anyway, in `README.md` and in the reader's export help text: the folded reading levels and the `textfold/doc` format originate from TextFold by Xia Chen, with a link.
- Rule for the implementer: if any upstream file is opened for reference, no text is copied from it. If that rule is ever broken, Apache-2.0 section 4 applies again (licence text, NOTICE, statement of changes) and the files must say so.

## Material unknowns

| Unknown | Default taken | What would change it |
| --- | --- | --- |
| Whether the word-morph animation is part of what the owner values | Dropped | Owner says the morph is the point. Then it is built as our own small layout animation in a later slice, still not a port |
| Whether anyone relies on browser-local highlights | Dropped without migration | Owner has highlights to keep. Then export them from the deployed build before this ships |
| Whether the argument map is used | ~~Replaced by the Topic outline and listed links~~ Reversed on 2026-11-18, see the amendment below | A project with many `links` proves the list unreadable |
| UI name | "Folded reading" in the interface; "Textfold" only for the file format in import and export | Owner prefers another name |
| Rendering cost on long briefs (format allows 100 sections of 1000 units) | Render all, measure on the 50-section fixture | Measured slowness; then collapse sections by default |

## Amendment, 2026-11-18: map and panel (owner feedback after deployment)

The owner used the deployed reader and rejected it: text only, without the earlier mind-map and graph view, and placed at the bottom of Discuss where it is hard to reach. Two defaults above are reversed. The decision to implement internally and not embed stands.

- **Map.** The reader has a map view of OpenPaper's own, and it is the view that opens first. Title, sections and paragraphs are a left-to-right tree; argument links (`links`) are dashed, labelled arrows across it; in investigation previews the findings paragraphs cite are shared nodes, which makes the Write preview a graph and not only a tree. Layout is a pure function (`client/src/lib/fold-map.ts`), rendered as HTML buttons over an SVG edge layer (`client/src/components/fold/FoldMap.tsx`). No graph library is added and nothing is ported from TextFold.
- **Panel.** The reader is no longer mounted in page content. It lives in the workspace's right slot (`client/src/components/project/BriefPanel.tsx`), opened by Brief in the project header on every project route, by the question card on Discuss and by Open folded preview on Overview, Evidence and Write. `ProjectResearchOverview.tsx` is removed; Edit brief, the invalid-levels notice, the empty state and the open-questions list moved into the panel.
- **Still dropped:** word-morph animation, gesture zoom beyond Ctrl+wheel, display settings, browser-local highlights.
- **What would change this:** the owner finds the map layout wrong for real briefs (then adjust the layout function, which is isolated), or wants free-form node positions (then positions need storage, which the reader does not have today).

## Next

Intent: [INTENT-native-fold-reader.md](INTENT-native-fold-reader.md). One slice, client only, on a branch from `feat/guided-shell`. Both hosts are replaced and the vendored code deleted in the same change so two readers never coexist.
