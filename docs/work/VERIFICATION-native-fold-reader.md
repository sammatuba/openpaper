# VERIFICATION: Native folded reader

Date: 2026-11-18. Intent: [INTENT-native-fold-reader.md](INTENT-native-fold-reader.md). Strategy: [STRATEGY-native-fold-reader.md](STRATEGY-native-fold-reader.md). Branch `feat/native-fold-reader`, from `feat/guided-shell` at `2574ea64`. Client only. Committed as `b5d8661f`, pushed and deployed; see Deployment.

## What changed

- New: `client/src/components/fold/FoldedReader.tsx` (the reader), `client/src/lib/fold-view.ts` (level logic), `client/scripts/test-fold-view.cjs`.
- `ProjectResearchOverview` (Discuss) and `FoldedPreview` (Overview, Evidence, Write) render `FoldedReader`.
- `investigation-preview.ts`: attribution and cited findings are fields of each paragraph, not injected Markdown.
- `textfold.ts`: adds `foldBlock` (one authored block to paragraphs, headings kept as text); validation rules unchanged. `markdownReferences` is no longer used by the app and is kept with its tests.
- `eslint.config.mjs`: `scripts/**/*.cjs` may use `require`. The `made_with` value of locally folded documents is now `OpenPaper`.
- Deleted: `client/public/vendor/textfold/`, `client/src/lib/textfold-native/`, `client/src/lib/textfold-upstream.tsx`, `client/src/components/textfold/`, the three vendor build and check scripts, the `.gitattributes` vendor line, the `test:textfold-native` script.
- Credit to TextFold (Xia Chen, Apache-2.0) in `README.md`, the brief editor's import help and `docs/PROJECT-RESEARCH-BRIEFS.md`. User guides updated. Superseded statements marked in the older strategy and handoff.

No server file, API, stored data or validation rule changed.

## Behaviour changes a user will notice

- The reader is part of the page and uses the app's type and colours. Default level is Takeaway (the embedded reader opened on its map).
- Keys 1–5 run Topic to Full (the embedded reader ran Full to Topic).
- Gone: word-morph animation, gesture zoom, map canvas, display settings, highlights and notes, "Export local reader annotations", the "Original brief and source anchors" disclosure (Full is the original text). Highlights already in a browser's storage are left there and nothing reads them.
- Write preview: attribution is a label above each paragraph; findings are named links. A cited finding that no longer exists shows as plain text "unavailable".
- Attribution and finding fields are shown only in OpenPaper-built previews. An imported brief carrying fields with those names keeps them for export but they are not rendered.

## Executed checks (WSL, Node 22, production build)

| Check | Result |
| --- | --- |
| `npm run test:textfold` (format tests, `test-fold-view.cjs`, investigation graph) | Pass |
| `tsc --noEmit` | Pass |
| `eslint` on `src/components/fold`, `src/components/project`, `src/lib`, project routes and the four touched scripts | 0 errors; 1 pre-existing warning in `ArtifactsPanel.tsx` |
| `npm run build` | Pass |
| Remnant search for `vendor/textfold`, `textfold-native`, `textfold-upstream`, `DR_I18N`, `NativeTextfold`, `TextFoldReader` in `client/src`, `client/public`, `client/scripts`, `.github`, `.gitattributes` | No match |
| Built chunks containing `native-surface` or `DR_I18N` | None |
| `npm run test:research-overview:browser` (1440, 390) | Pass |
| `npm run test:project-workflow:browser` (1440, 390) | Pass |
| `npm run test:investigation:browser` (1440, 390) | Pass |
| `git diff --check` | Pass |

Size, same machine, baseline built from `2574ea64`:

| Measure | Before | After |
| --- | --- | --- |
| `/projects/[projectId]/discuss` route / first load | 76.1 kB / 319 kB | 22.4 kB / 261 kB |
| `/projects/[projectId]` first load | 234 kB | 206 kB |
| `/draft`, `/evidence` first load | 196 kB, 192 kB | 168 kB, 164 kB |
| `.next/static` | 24,172 KB | 21,540 KB |
| `client/public` | 6,576 KB | 5,780 KB |
| Tracked lines | | 16,147 removed, about 700 added |

What the journeys assert about the reader:

- Discuss: no iframe; default level; one-sentence Takeaway; Full keeps a reference-style link's `href` and title; reference definitions are not shown as paragraphs; a paragraph opens to source sentences, then full text, then folds back while its neighbour stays folded; focus moves to the paragraph's remaining control when the one just used leaves the page, and number keys keep working afterwards; keys and arrow keys change level with focus in the reader; a digit typed in a dialog field does not; no `/api` request while folding; `localStorage` and `sessionStorage` keys equal the baseline taken before the reader mounted, also after reading an imported brief and reloading.
- Long brief (50 sections, 200 cited paragraphs, 50 reference definitions): all 200 paragraphs render and resolve their citation; a level change took between 65 and 215 ms across four runs at the two widths (click to second animation frame); reload to reader ready took 1.2 to 2.2 s.
- Imported brief with hostile content: raw `<img onerror>`, `<script>` and a `javascript:` link in a paragraph's source Markdown show as inert text at Full; every in-page argument link reaches an element, including one whose target is a definition-only paragraph; a unit id of `__proto__` still opens; non-string `findings` and `attribution` extension values do not crash and are not rendered; a section title containing template tokens renders literally; no `img`, `script` or `iframe` in the reader; injected handler never runs; Brief quotes the selected second sentence, not the first; a section-to-section argument link is rendered.
- Previews: open on Overview, Evidence and Write; Write shows AI, human and quotation attribution and the exact captured quote; opening and folding causes no request to the app other than the reader's code chunk and the destination bar's own prefetch of the open page; no new storage key; no editing control inside the preview; a finding link navigates to `/evidence?finding=` with unsaved prose intact; theme change keeps the preview mounted and its level; a viewer can open and fold a preview.

Screenshots inspected by eye: Discuss reader light 1440 and 390, dark 390 (`/tmp/openpaper-fold-*.png`); Write preview dark 1440 (`.meos/artifacts/investigation-workspace/draft-native-dark-1440.png`). Also captured, not inspected: Discuss dark 1440, Write preview light at both widths (`draft-fold-*.png`), Write preview dark 390. The Overview and Evidence previews are asserted but sit below the captured frame in their screenshots.

## Independent review

Round 1, Codex via `./meos review --base feat/guided-shell` (`.meos/reviews/20261118T131344Z.md`): **rework**, nine findings.

| Finding | Disposition |
| --- | --- |
| Blocking: a parser-valid brief with a non-string `findings` label crashed the reader | Fixed: entries are type-checked, and these fields render only in OpenPaper-built previews. Journey imports such a brief |
| A missing cited finding vanished from the draft preview | Fixed: kept as an unavailable citation in plain text. Unit test |
| GFM table without outer pipes treated as prose at Brief | Fixed: prose is decided by the renderer's own CommonMark and GFM grammar. Unit test |
| Section-origin argument links not rendered | Fixed. Journey |
| Finding links prefetched their route | Fixed: `prefetch={false}`. Journey watches all requests to the app |
| Pointer referenced a missing verification record | This document |
| Journeys skipped several acceptance items | Fixed: previews opened on all three views and as a viewer; storage baseline before mount; digit that would change the level; more screenshots |
| ESLint `no-require-imports` on the touched `.cjs` scripts | Fixed in round 2: the rule is off for `scripts/**/*.cjs`; the touched scripts lint clean |
| `INVESTIGATION-WORKSPACES.md` described removed controls | Fixed |

Round 2 (`.meos/reviews/20261118T134247Z.md`): **rework**, six findings.

| Finding | Disposition |
| --- | --- |
| Draft preview dropped heading text inside a block, and lost attribution and findings for a block with no text | Fixed: `foldBlock` keeps a block's headings as its text and always yields a paragraph; a block is labelled on its first paragraph and cited on its last. Unit tests for a heading-only quotation, an empty cited gap and a heading inside a paragraph |
| Appending all reference definitions to each paragraph could change shown source or a link's destination; cross-paragraph footnotes were lost | Fixed: `foldContext` collects definitions and footnotes once (first definition wins); `withReferences` places only the ones a paragraph uses before its text. Unit tests render duplicates, an unclosed fence and a footnote defined in another paragraph |
| Reparsing every definition per paragraph was slow | Fixed by the same change; measured above |
| An argument link could point at a paragraph the reader does not render | Fixed: such a link lands on the containing section. Journey checks every in-page link's target |
| Hostile-content journey did not put hostile Markdown in rendered source | Fixed |
| Touched-path lint | Fixed |

Round 3: Codex did not run (workspace out of credits, `.meos/reviews/20261118T135509Z.md`). A fresh agent with no authoring context reviewed the staged change instead and returned **rework** with ten findings. This is a stand-in, not parity with the Codex gate; it executed the unit script and its own rendering experiments, not the journeys.

| Finding | Disposition |
| --- | --- |
| A reference label containing `&` or an entity stopped resolving across paragraphs | Fixed: a definition keeps its label exactly as written in the source. Unit test compares the paragraph's rendering with the whole-document rendering |
| A label written with a backslash escape lost its definition | Fixed by the same change. Unit test |
| A paragraph of indented code containing `[^n]` rendered as nothing | Fixed: footnotes are placed after the text, and only when the parsed result both cites and defines them; otherwise the paragraph is rendered exactly as written. Unit tests for indented code, inline code and an unclosed fence |
| Focus was lost when "Show full text" or "Fold back" left the page | Fixed: focus moves to the paragraph's remaining control. Journey asserts the focused control and that number keys still work |
| A footnote defined inside a quotation was sliced with its quote prefixes | Changed: only top-level footnote definitions are shared across paragraphs. One nested in a quote or list is rendered where it is written and a citation of it from another paragraph shows as written. Unit test |
| A label containing an escaped bracket was not found | Fixed. Unit test |
| Duplicate `footnote-label` ids when several paragraphs have footnotes | Fixed: that id and the attribute pointing at it are not emitted; footnote anchors keep per-paragraph ids |
| An opened paragraph's state was keyed by position and could stick to a different paragraph after an edit | Fixed: keyed by the paragraph's own id in a Map |
| This record pointed at a missing round 3 section | This section |
| The older strategy linked to a deleted file | Fixed |

Re-review by the same stand-in agent after the fixes: **accept**. It re-ran its earlier failing inputs and 21 new ones against `withReferences` (resolved: the label, indented-code and bracket findings by execution; the focus and footnote-id findings by reading) and reported five minor findings.

| Minor finding | Disposition |
| --- | --- |
| A definition whose label wraps onto a second line inside a quotation was shared with the quote prefix in its label, adding foreign text above the citing paragraph | Fixed: a line break in a shared label is a space. Unit test |
| A label containing a backslash followed by a line break was not found | Fixed |
| This record understated the effect of the first item | Removed with the fix |
| A paragraph's own later definition of a footnote label wins over an earlier one elsewhere in the document | Accepted; listed below |
| Opened-paragraph state follows position for locally folded text, whose ids are positional | Accepted; the code comment now says so |

The last two fixes above were made after the re-review and have been checked only by the unit script and the journeys.

Known limits that remain:

- A footnote cited from a paragraph that also contains an unclosed fence or an unterminated HTML block after the citation is shown as written (`[^n]`).
- A footnote defined inside a quotation or list is not shared with other paragraphs: a citation of it elsewhere shows as written, and if the defining paragraph holds nothing else its text is not shown.
- With duplicate footnote labels, a paragraph that defines the label itself uses its own definition.
- After an edit that shifts paragraphs in a locally folded brief, an opened paragraph's state stays with the position.

## Deployment (2026-11-18, owner instruction)

Client container only. Cloud Build `5cc5ba38-abf9-4112-abc8-eafd556a2852` from `b5d8661f`, image `client@sha256:9c3106fc56f497bf01beb899dbafbc406aaa4e32660acce6f999db90c64755c1`. Staged without traffic as `openpaper-00020-dus`, smoke-checked, then moved to 100%; staging tag removed. Server and Caddy image digests are unchanged. No migration ran. Rollback: `gcloud run services update-traffic openpaper --region asia-southeast1 --to-revisions openpaper-00017-lax=100`.

Smoke on the staged URL and then on `papers.sammatuba.workers.dev` and the `run.app` host: `/api/health` 200, `/` 200, `/login` 200, `/projects` 200, `/projects/{id}/discuss` 200, `/vendor/textfold/reader.js` 404 (200 on the previous revision, so the new client is the one served), unauthenticated investigation 401, unauthenticated `POST /api/mcp` 401. The signed-in reader on real data was not exercised.

## Map and panel (2026-11-18, after owner feedback on the deployed reader)

Owner feedback: the deployed reader is text only, lacks the earlier mind-map and graph view, and sits at the bottom of Discuss. See the amendment in `STRATEGY-native-fold-reader.md`.

Changed: `lib/fold-map.ts` (layout), `components/fold/FoldMap.tsx` (map), `FoldedReader.tsx` (Map and Read views, detail pane, own scroll area), `components/project/BriefPanel.tsx` (right-slot panel), `ProjectWorkspaceProvider.tsx` (`brief` panel mode), `ProjectHeader.tsx` (Brief button), Discuss page (bottom section removed), `investigation/shared.tsx` (Open folded preview opens the panel). Removed `ProjectResearchOverview.tsx`. Client only.

Executed (WSL, Node 22, production build, Chromium at 1440 and 390 px):

- `tsc --noEmit`, `npm run lint`: no errors.
- `npm run test:textfold`: passes, including the new `scripts/test-fold-map.cjs` (tree layout, columns by depth, folding, argument links, shared findings, plain node text, hostile ids, 200-paragraph layout, no overlapping nodes).
- `test:research-overview:browser`: passes. Panel opens from the header and from Discuss, takes focus, closes on Escape and returns focus; map nodes do not overlap; fold, collapse all, zoom, fit; selecting a paragraph shows it under the map and Read in context scrolls to it; an imported brief draws both argument links and no finding nodes; 200 paragraphs open folded and expand in 54 to 196 ms.
- `test:project-workflow:browser`, `test:investigation:browser`: pass. Write preview draws cited findings as shared nodes with a link to Evidence; on a phone, following a finding closes the panel.
- Sizes: Discuss route 8.52 kB / 190 kB first load (the reader moved to the shared project layout).

Defect found by the new unit test and fixed: a map node showed raw `[text][label]` for a reference-style link; node text now resolves references as the text view does.

Independent review of `90aa2a07`: `./meos review --base 14ceceda` did not complete (Codex workspace out of credits, `.meos/reviews/20261118T150441Z.md`). A stand-in reviewer (a fresh agent given the diff and records, not the author's reasoning) returned **rework** with 10 findings; it found the layout and the handling of untrusted text sound. A Codex pass is owed.

| # | Severity | Finding | Outcome |
| --- | --- | --- | --- |
| 1 | important | Panel returned focus to its opener whenever it left the slot, including when Artifacts or a paper took it | Fixed: focus returns only on the panel's own Close and Escape; journey asserts it |
| 2 | important | Close paragraph, Close finding and Read in context dropped focus to the page | Fixed: closing returns to the map node, Read in context falls back to the reader; journey asserts the first |
| 3 | important | A large brief imported into an open map rendered unfolded; stale fold state after an in-place change | Fixed: fold state is in the reader and resets, with selection and opened paragraphs, when the document's structure changes; the map re-fits |
| 4 | minor | Selection followed position after an edit that shifts paragraphs | Fixed with 3 |
| 5 | minor | Folded sections were lost on Map to Read to Map | Fixed; journey asserts it. Zoom still re-fits |
| 6 | minor | The selected text was far away in tab order and announced in full | Fixed: selecting moves focus to the text; the live region is removed |
| 7 | minor | The full-screen overlay is not modal | Not changed: same as the existing reader and artifacts panels |
| 8 | minor | The panel squeezed the page at narrow desktop widths | Fixed: it is a full-screen sheet below 1024 px |
| 9 | minor | Relevance and Landscape cards removed without record; provenance line only in Read | Provenance line now also under the map; card removal recorded in the strategy amendment |
| 10 | minor | Loose timing bound; no unit case for a link under a twice-folded ancestor; stale file names in records | Journey checks added for 1, 2, 5; the rest not changed |

The fixes have not been re-reviewed.

Staging: Cloud Build `d549e5cb-daf0-4928-b805-2dc7ab6f9c58` from `a3be08ca`, image `client@sha256:2b314659a81690ee9c3921a50947af0cb69a3651510798f31a56cbf2b4c484e8`, revision `openpaper-00023-wov` at 0% under tag `fold`. Smoke on the staged URL: `/api/health`, `/`, `/login`, `/projects`, `/projects/{id}/discuss` 200; unauthenticated investigation and `POST /api/mcp` 401. 

Promotion: the owner moved traffic to `openpaper-00023-wov` (100%) on 2026-11-18; staging tag removed. Smoke on `papers.sammatuba.workers.dev` and the `run.app` host: `/api/health`, `/`, `/login`, `/projects`, `/projects/{id}/discuss` 200; `/vendor/textfold/reader.js` 404; unauthenticated investigation and `POST /api/mcp` 401. The signed-in panel and map on real data were not exercised. Rollback: `gcloud run services update-traffic openpaper --region asia-southeast1 --to-revisions openpaper-00020-dus=100`.

Not executed for this change: Firefox and Safari, signed-in real data, touch pinch zoom, a brief with many crossing argument links.

Known limits: node positions are computed, not draggable; the panel's level, view and selection reset when it is closed; the map is a list of buttons to assistive technology, with Read as the fully structured view.

## Not executed

- Firefox and Safari; only Chromium.
- Rendering cost beyond the 200-paragraph fixture (the format allows 100 sections of 1,000 units).
- Scroll anchoring when the level changes mid-document is implemented but not asserted by a journey.
- Signed-in use on real data: no operator session.
- Server suites: no server file changed.

## Observed, not part of this change

The local production build sends Google Analytics page views during browser journeys (seen as a `google-analytics.com/g/collect` request carrying the synthetic project URL). It predates this branch.
