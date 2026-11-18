# INTENT: Native folded reader

Date: 2026-11-18. Strategy: [STRATEGY-native-fold-reader.md](STRATEGY-native-fold-reader.md). Branch: `feat/native-fold-reader` from `feat/guided-shell`. Client only.

## Outcome

Folded reading on Discuss, Overview, Evidence and Write is rendered by one OpenPaper component from a `textfold/doc` v0 document. The upstream Textfold reader, its generated copy, its adapter and its build and check scripts are gone from the repository and from the shipped bundle.

## Scope

Add:

- `client/src/lib/fold-view.ts`: pure functions. For a unit and a level, what to show (text, whether it is source wording, the supporting sentences); which units are non-prose; resolved argument links.
- `client/src/components/fold/FoldedReader.tsx`: the reader. Props: `document`, optional `question`, optional `onOpenFinding`. Level group, per-paragraph open and close, outline at Topic, provenance line, per-paragraph attribution and finding links, "Export Textfold" (existing `serializeTextFold`).
- `client/scripts/test-fold-view.cjs` for the pure functions.

Change:

- `ProjectResearchOverview.tsx` and `investigation/shared.tsx` (`FoldedPreview`) use `FoldedReader`.
- `investigation-preview.ts`: attribution and finding links travel as unit fields, not as injected Markdown sentences.
- `package.json` scripts and `.github/workflows/test.yml`: the vendor and generated-engine checks leave `test:textfold`; `test:textfold-native` is removed; the fold-view test joins.
- The three browser journeys: selectors move from upstream internals and the iframe to roles and labels of the new reader.
- `README.md`: credit to TextFold (Xia Chen, Apache-2.0) for the reading levels and the format.
- `EditProjectDialog.tsx`: wording only where it says the reader is Textfold's.

Delete: `client/public/vendor/textfold/`, `client/src/lib/textfold-native/`, `client/src/lib/textfold-upstream.tsx`, `client/src/components/textfold/`, `client/scripts/build-textfold-native.cjs`, `check-textfold-native.cjs`, `check-textfold-vendor.cjs`, and the `.gitattributes` line for the vendor patch.

## Boundaries

- No change to `client/src/lib/textfold.ts` validation rules, `server/app/schemas/textfold.py`, the stored `research_brief`, or any API.
- No upstream code, CSS, markup or strings copied.
- No iframe, shadow root, `dangerouslySetInnerHTML`, `localStorage` or `sessionStorage` in the reader.
- No network request and no model call from the reader.
- Follows `client/design.md`: tokens, type and whitespace before borders, no nested bordered boxes.
- Not in this slice: morph animation, annotations, a map canvas.

## Failure cases to handle

- Saved brief that fails validation: the existing fallback to the project description still applies and the alert still shows.
- Unit with empty Topic, Takeaway or Key: falls through to the next fuller level that has text, and says which level is shown.
- Non-prose unit at Brief: shows Full.
- Empty document or section with no units: an empty state, not a blank region.
- Link text containing raw HTML or a `javascript:` URL in source Markdown: rendered inert by the Markdown renderer.
- Finding link to a finding that no longer exists: shown as plain text.
- Viewer role: reader works; nothing in it mutates.

## Observable checks

| Check | How |
| --- | --- |
| Level projection is correct for all five levels, fall-through, non-prose and links | `node scripts/test-fold-view.cjs` |
| Types, lint, build | `tsc --noEmit`, eslint on touched paths, `npm run build` |
| No remnant of the embed | `grep -ri "vendor/textfold\|textfold-native\|textfold-upstream\|DR_I18N" client/src client/public client/scripts` returns nothing; no `iframe` under `components/fold` |
| Bundle | After build, no chunk contains `native-surface`; record the size change of the project routes |
| Discuss brief | Research-overview journey: each level shows the expected text for the imported fixture; Brief equals the quoted sentences; Full keeps the reference link `href`; export writes `textfold/doc`; no request during level changes |
| Previews | Investigation journey: previews open on Overview, Evidence and Write; draft paragraphs show attribution labels; a finding link navigates to `/evidence?finding=`; theme change keeps the level; viewer read-only |
| Keyboard | Keys 1–5 change level only with focus in the reader; typing in a field elsewhere on the page does not |
| Storage | After opening and using a reader, `localStorage` has no new key |
| Layout | Screenshots at 1440 and 390, light and dark, for Discuss and one preview; no horizontal overflow |
| Existing journeys | `test:investigation:browser`, `test:project-workflow:browser`, `test:research-overview:browser` pass at both widths |

## Not authorised by this intent

Push, pull request, deploy. Supersession notes in the older strategy and handoff documents are edited as part of the change; their history is not rewritten.
