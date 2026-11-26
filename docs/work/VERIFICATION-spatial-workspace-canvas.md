# VERIFICATION: Spatial workspace, project canvas

Date: 2026-11-19. Intent: [INTENT-spatial-workspace-canvas.md](INTENT-spatial-workspace-canvas.md), with its amendment sections. Branch `feat/spatial-workspace`, on top of `a3b8c877`. Client only. Not deployed.

## What changed

- **The project home is the canvas** (`/projects/[id]`, "Canvas" in the destination bar): the question, the draft's sections, the claims, the findings and the papers as nodes, in four columns. Lines always drawn: question to claim; claim to finding, coloured and dashed by supports, challenges or qualifies; finding to the paper its passage is anchored in. Each claim shows how many findings support, challenge and qualify it. Archived claims and findings are not drawn.
- **Draft lines on selection.** A section's lines to the claims and findings it cites are drawn while the section, or one of those claims or findings, is selected; a section gets at most 100, and its detail says when it cites more.
- **Layout** is a pure function (`lib/project-canvas.ts`): claims and sections in document order, findings level with their claims, papers level with their findings, unlinked ones after. Nothing is stored or hand-placed.
- **One engine.** The camera, gestures, keyboard and zoom controls moved from `FoldMap.tsx` into `components/canvas/Surface.tsx`. The brief map and the canvas both run on it.
- **Detail.** Selecting a node opens its text under the map with its actions: Overview and evidence for a claim; Evidence and the source in the reader for a finding; the reader for a paper; Write for a section; Overview for the question. Linked items named in the detail are buttons that move the selection and bring the node into view. From the keyboard, opening a node moves focus into the detail; Escape returns to the node; Close returns focus to the node.
- **Remembered for the session, in memory:** camera and selection per project (numbers and ids only), and the last saved investigation per project so a return visit draws at once (`lib/investigation-snapshot.ts`; rules in the intent's amendments).
- **The investigation provider is scoped to the signed-in session.** It restarts empty at sign-out and on a change of user. This also closes a gap that predates this slice: before, an account change on an open project left the previous user's document in the provider.
- **Overview moved** to `/projects/[id]/overview`. `/projects/[id]?claim=…` redirects to it. The brief panel's page preview and the one in-app link to Overview follow.
- The workspace provider exposes `papersError`. The destination bar scrolls sideways when it does not fit, and its entries are slightly narrower below 640 px so all five fit at 390 px.

## Measured

`node scripts/measure-canvas.cjs`, headless Chromium 1234 at 1440×960, local production build, API mocked, CPU slowed 4×. "Show" is from the click on Canvas to the first painted frame with every node. First is the first time in the page (the route's code loads too); warm is leaving and coming back. Three runs for each fixture (the dense fixture was run three more times after the line cap; both sets are given where they differ). These runs predate the round 2 review fixes, which did not touch how nodes or lines are rendered; the measurement was not repeated after them.

| Canvas | Action | Result at 4× slowdown |
| --- | --- | --- |
| 72 nodes, 132 lines (12 claims, 40 findings, 15 papers, 4 sections) | Show, first | 226–311 ms |
| | Show, warm | 95–160 ms |
| | Select a claim; a section | 115–167 ms; 92–158 ms |
| | Zoom, 60 steps | 0 React commits; 0–1 frames over 33 ms |
| | Pan, wheel and drag | 0 React commits; 0–1 frames over 33 ms |
| 931 nodes, 1,600 lines (the format's maximum: 100 claims, 500 findings, 1,000 relations, 30 sections; 300 papers), each section citing 3 things | Show, first | 740, 787, 932 ms |
| | Show, warm | 490, 606, 796 ms |
| | Select a claim; a section | 202–368 ms; 170–241 ms |
| | Zoom, 60 steps | 0 React commits; 0, 1 and 9 frames over 33 ms |
| | Pan, wheel and drag | 0 React commits; 0–1 frames over 33 ms |
| The same 931 nodes, every section citing every claim and finding (18,000 citations) | Show, first | 833, 918, 1,389 ms; second set 1,209, 1,378, 1,394 ms |
| | Show, warm | 602, 620, 712 ms; second set 992, 1,033, 1,081 ms |
| | Select a claim (30 draft lines appear) | 231–302 ms |
| | Select a section (100 draft lines appear) | 278–301 ms |
| | Zoom, 60 steps | 0 React commits; 2–11 frames over 33 ms |
| | Pan, wheel and drag | 0 React commits; 0–2 frames over 33 ms |

Before the review, earlier code drew every draft line at once. Measured then on the sparse fixture only: show first 767–2,332 ms, warm 505–962 ms. Without the slowdown, that build showed the largest sparse canvas in 201–246 ms. The current build was not re-measured without slowdown.

Reading it:

- Layout is 4 to 13 ms for the largest canvas, dense or sparse (`test-project-canvas.cjs`). No Worker and no typed-array geometry were built.
- **The intent's 1 s line for showing the maximum canvas is not met at 4× slowdown**: the sparse maximum stays under it in these runs (740–932 ms first), the dense maximum does not (up to 1,394 ms). The dense and sparse fixtures draw the same nodes and lines when nothing is selected, so the difference between the two dense sets, and between dense and sparse, is partly run-to-run noise on this machine; I cannot separate the two with three runs each.
- `content-visibility: auto` on nodes was built and measured (two runs, sparse maximum): warm show 424 and 510 ms, but zooming went from 2–3 frames over 33 ms to 25 and 38, because nodes entering the view are laid out during the gesture. It was removed.
- Selecting a section that cites everything took 1,565–1,757 ms when all 600 lines were drawn. With the cap of 100 it is 278–301 ms.
- Nodes are memoised so a selection re-renders two nodes, not all of them.
- A real project reaches these sizes only with 100 claims and 500 findings.

### Weight (`node scripts/measure-route.cjs`, against `a3b8c877`)

| | `a3b8c877` | Now |
| --- | --- | --- |
| Scripts the home route's HTML asks for, polyfill excluded | 38, 1,120.5 KB raw, 356.2 KB gzip | 38, 1,112.9 KB raw, 354.1 KB gzip |
| Next "First Load JS" for the home page | 212 kB (Overview) | 173 kB (canvas); Overview at its new address 214 kB |
| All scripts requested once the network is quiet | 67, 2,133.9 KB raw, 667.6 KB gzip | 66, 2,098.9 KB raw, 655.6 KB gzip |
| All built chunks | 3,923.1 KB raw, 1,195.3 KB gzip | 3,931.8 KB raw, 1,198.3 KB gzip |

The home route's document asks for 7.7 KB raw (2.2 KB gzip) less than before, so the boundary is met on the final build. This figure moves with how the bundler splits shared code: two builds earlier in this work, with less code, measured 2.1 and 2.8 KB raw over. The build as a whole is 8 KB raw larger.

## Checks run on the final build

| Check | Result |
| --- | --- |
| `tsc --noEmit` | Pass |
| eslint on touched paths | 0 errors; 1 warning that predates this work (`ArtifactsPanel.tsx:320`) |
| `npm run test:textfold` (now includes `test-project-canvas.cjs`, `test-investigation-snapshot.cjs` and `test-investigation-provider.cjs`) | Pass |
| `next build` | Pass |
| `test:research-overview:browser`, 1440 and 390 | Pass; one step added (below) |
| `test:project-workflow:browser`, 1440 and 390 | Pass, unchanged |
| `test:investigation:browser` | Pass; two `goto` addresses changed (below) |
| `test:map-touch:browser` | Pass, unchanged |
| `test:flow:browser`, 1440, 390, reduced motion | Pass, unchanged |
| `test:canvas:browser`, 1440 and 390 | Pass |
| `git diff --check` | Clean |

`test:canvas:browser` (fixture: 10 claims, 12 findings, 2 papers, 6 sections, plus an archived claim and finding) asserts:

- the home page is the canvas with Canvas current in the bar; nodes by kind and lines by kind, archived items absent, no source line for a redacted finding, no draft lines until something is selected;
- a claim's accessible name carries its tally; selecting it shows its text, both links, four highlighted lines including the one draft line, and keeps it in view; a pointer press leaves focus on the node;
- a finding named in the detail takes the selection, is brought into view, and focus is on the detail; its source opens in the reader and closing the reader returns focus to the button;
- an unbound finding and a redacted finding whose paper is listed both say the source is not available and offer no reader; the paper does not list the redacted finding;
- a paper's detail opens the reader and focus returns;
- keyboard only: arrows walk the nodes; Enter opens a claim and focus is in the detail; Tab reaches the first linked finding; Enter selects it; Escape returns to the node with the detail open; Enter closes and reopens; Tab reaches Close; Enter closes and focus is on the node;
- after zooming and selecting a section, "Open in Write" shows the section on screen, and coming back restores zoom, selection and position within 2 px; the same with the selection panned out of view;
- "Open in Evidence" shows the tenth finding on screen; `?claim=` on the home address shows the tenth claim on screen in Overview;
- a return visit with a 1,500 ms API draws the kept copy in about 120 to 160 ms with no skeleton, then shows the server's changed claim text once it answers;
- a return visit whose investigation request fails keeps the kept copy and says so, for a populated and for an empty investigation;
- with unsaved edits on screen, a change of account announced from another tab removes the first user's text from the page before any request is answered, and the second user's investigation then appears;
- "Open in Write" followed from a kept copy while the investigation request is held: Write is on screen without the section, and shows it (the sixth, below the fold) once the request is answered;
- a 403 that arrives late, from a request an earlier visit started, removes a kept copy that is on screen: the canvas is replaced by the alert and none of its text remains, with no navigation;
- after the account switch the second user has neither the first user's selection nor their zoom;
- a project denied while its investigation is loading, then allowed again on the same page, asks for the investigation again and draws the canvas;
- (1440 only, it needs a 31 s wait) a denial learned by a card's prefetch on the project list removes the kept investigation: the next visit, with the investigation failing, shows the failure and no old copy; and the project itself is shown again once access returns;
- editing during a held save: the bar still says Saving, Save is disabled, one request carries the first edit, the later edit stays on screen as unsaved, and the next Save sends it;
- after a failed save, "Reload latest" confirmed with its request held, then an edit: when the answer arrives the edit is still on screen, the bar does not say Saved, and the reload is reported as failed;
- an empty project shows the prompt; papers alone are drawn; a failed paper list, investigation or project load on a first visit shows its alert and no map; no horizontal page overflow; no page errors.

The out-of-view pan assertion was checked against the bug it covers: with the fix disabled in `Surface.tsx` the check fails, with it restored it passes.

`test-project-canvas.cjs` asserts the layout rules, including exact centres (a finding level with its one claim, at the mean of two, a paper level with its finding, a crowded neighbour directly below), no overlap, bounds, order, lines only between drawn nodes, draft lines per selection and their cap, tallies, determinism, and both maximum fixtures under 250 ms. `test-investigation-snapshot.cjs` asserts the kept-copy rules in every ordering listed in the intent, that an overtaken answer is reported as not to be shown, and that a reader is told exactly when a copy changes.

`test-investigation-provider.cjs` (added after round 5, on the owner's go) drives the real provider, with React, the workspace hook and `fetch` replaced by stand-ins so each answer is released by hand. It asserts: load and failed load; two reloads answered in reverse order; reload then edit; reload then edit then save, with the 412 that follows leaving the edit, its tag and Conflict; reload on a dirty draft with a save retried and refused before the reload answers (round 5's blocking case), and that a reload asked for afterwards does replace the draft; reload refused and a second Save ignored during a save; an edit during a save keeps Saving and is sent by the next save; a block review made during a save is absent from that request, leaves the document unsaved, goes with the next save and is not sent twice; a failed save's review is retried once; a reload clears reviews of the discarded draft; a review of a removed block is not sent; a project denial during a save, and a refused save, leave the draft with Save failed and nothing kept; denial during the first load then access restored loads again, and a loaded draft is not reloaded; a denial recorded during the first load keeps its answer off screen; a change of user restarts the provider and the first user's answers are neither shown nor kept; a viewer cannot edit. Nine guards in the provider were removed one at a time by the author, and the harness fails for each; the round 6 reviewer removed 19 and found two it did not catch (a refused reload, and a refused first load, dropping the kept copy), which now have cases.

Screenshots of the canvas at 1440 and 390, with and without a detail, and of the empty prompt were looked at (`.meos/artifacts/project-canvas/`); those on disk now are from the final run.

## Journey changes

`check-investigation-workspace.cjs`: the two steps that opened the project home to reach Overview now open `/overview`. No assertion changed. `check-project-research-overview.cjs` gained a step: select the last paragraph on the brief map, visit the text, come back, and the paragraph is selected and in view. The touch check was not touched. All pass on the shared surface. The same journey now blocks the app's Google tag script (`www.googletagmanager.com`, loaded by the main layout from the real network): on the last day of this work the tag began arriving during the run and writing its own storage key (`_gcl_ls`), which failed the assertion that the reader stores nothing in two of three runs. The assertion is unchanged. That the signed-in app loads an advertising tag at all is the owner's to know; it predates this work.

## Found and fixed during verification

1. `test:flow:browser` failed after the home page became the canvas: a cached return visit showed a skeleton while the investigation loaded. Fixed with the kept copy; the flow check passes unchanged.
2. After the review fixes, one run of the canvas check failed: closing the reader resized the surface, which pulled the camera back to the selected node while the user had already moved focus to another. A resize now keeps the selection in view only if it was in view before.
3. The new list-denial check found a fault from the flow slice: a denial recorded by a card's prefetch stayed on screen after access returned, because the project came back unchanged and nothing re-rendered. The project hooks now subscribe to denials (`lib/reads.ts` announces them; unit tested).

## Independent review

`./meos review` (GPT reviewer through Codex, `gpt-6.2-astra`, read-only sandbox; it ran the unit tests, `tsc` and eslint, not the build or the browser checks).

| Round | Verdict | Findings | Outcome |
| --- | --- | --- | --- |
| 1, `.meos/reviews/20261119T074026Z.md` | rework | Blocking: an account change could leave the previous user's working document on screen; a denial could leave or restore a kept copy (reload and save not covered, older answers could undo it). Important: a redacted finding got a source line and "Open source"; the benchmark fixture was sparse (a dense draft gives 19,600 lines, not 1,690); returning to the canvas could undo a saved pan; no keyboard path from a node to its detail, and Close lost focus; a failed paper list read as an empty project. Minor: no stale notice on an empty kept copy; link checks did not prove the target was on screen and the return visit served identical data; layout tests checked order, not alignment | All addressed, with tests, as listed in the intent's second amendment. The dense case was fixed in the design (draft lines on selection, capped) and then measured |
| 2, `.meos/reviews/20261119T081853Z.md` | rework | Round 1 findings confirmed fixed, two partly. Blocking: a refusal could drop a kept copy while its text stayed on screen (the canvas read the copy without subscribing). Important: an older answer could replace the live document, tag and save state after a newer one; "Open in Write" from a kept copy lost its section; the pan fix stopped the brief map showing its selection on reopening. Minor: camera and selection carried across accounts; two relations to one claim pulled a finding off-centre | All addressed, with tests, as listed under "Round 2 added" in the intent |
| 3, `.meos/reviews/20261119T083354Z.md` | rework | Four of six round 2 findings confirmed fixed. Blocking: a project denial learned on the project list (prefetch) left the kept investigation in memory. Important: an overtaken save judged its ownership by the shared "Saving" label, so it could leave "Saved" or fail a newer save; a denial during the first load, then restored access, left the investigation loading for good. Minor: the Write check did not prove the section was absent when the link was followed | All addressed, as listed under "Round 3 added" in the intent. Tested by the author: the list denial (unit and browser), denial then access on one page (browser), the Write check. Not tested by the author, checked by the reviewer in memory in round 4: the refused reload and duplicate save during a save, and a save cut off by a denial. The save finding was removed at its cause (no reload during a save) |
| 4, `.meos/reviews/20261119T085618Z.md` | rework | Round 3 fixes confirmed by the reviewer's in-memory checks. Blocking: a reload started before an edit and a save could replace the edit when its answer came, so a following 412 left nothing to recover. Important: a paper-list refusal during the first load invalidated the investigation request and left the canvas loading; the one-save guard silently dropped a second Save, and a block review, made during a save. Minor: the round 3 row overstated test coverage | Partly fixed, as round 5 showed. Fixed and confirmed by the round 5 reviewer: reload then edit then save; editing during a save; the paper-list refusal. Not fixed by round 4's change: a save that started and failed while the reload was pending; and the review queue it added lost a review made during a save and kept reviews across a reload |

The reload and save faults in rounds 3 and 4 are in code that predates this slice, or in guards added during this review; the slice touched the provider to scope it to the session and to keep copies, and each round has followed that into the save path.
| 5, `.meos/reviews/20261119T090836Z.md` | rework | Blocking, and present at `a3b8c877` too: after "Reload latest" on a dirty draft, a Save retried and refused (412) before the reload answered let the reload replace the draft, leaving nothing to recover. Important, both from round 4's queue: a block review made during a save was never sent; reviews from a discarded draft were sent after a reload, which the server rejects. Minor: the round 4 row said "all addressed" | Changed after the verdict and **not reviewed**: the reload now gives way to any save attempted since it was asked for; each save sends its own review list, later ones wait, failed ones are retried, a reload clears them, and only blocks still in the draft are sent. The full check set passes. The orderings were then put under test in the provider harness |

**Rounds 1 to 5 (GPT reviewer) ended in rework; round 6 (Claude Opus 5.5) accepted with findings.** Five rounds ran. Rounds 1 and 2 were about the canvas and the kept copy. From round 3 on, the findings moved into how the investigation provider saves and reloads, where each fix was checked by the next round and each round found a further ordering. Until round 5 the provider had no test harness in this repository; the reviewer exercised it in memory with mocked hooks, the author through the browser. `test-investigation-provider.cjs` now holds those orderings.

Round 6 did not run: `./meos review` stopped after 61,698 tokens with "Your workspace is out of credits" (Codex), and saved an empty report (`.meos/reviews/20261119T100825Z.md`).

**Round 6, Claude Opus 5.5, fresh read-only reviewer agent (owner's choice; it shares a model family with the author): accept with findings, nothing blocking.** It was given the diff, the intent, this record and the five earlier reports. It ran the unit tests, `tsc` and eslint, not the build or the browser checks. It confirmed the three round 5 findings fixed, judged the harness's stand-in for React faithful for what is claimed, compared the provider with `a3b8c877` and found no ordering that loses a draft, shows one user's document to another, reports Saved for unsaved work or leaves the page stuck, and found no path that shows a kept copy to another user. Findings, all minor:

- A refused reload (and refused first load) dropping the kept copy had no test. Cases added.
- An overtaken reload returned silently. It now reports that it failed.
- A review-only save that failed left the document marked clean with its review waiting (the review was simply dropped at `a3b8c877`). The document now stays unsaved.
- One harness check was conditional and could pass without checking. Made unconditional.
- Errors in this record. Corrected.

These four changes were made after the verdict and are not reviewed; the unit tests and the full check set were run again after them.

Noted by the reviewer as a deliberate trade-off for the owner: signing in as another account in another tab now discards this tab's unsaved draft at once, with no chance to download it. That is what keeps one user's draft from being saved under another's account.

## Not verified

- Chromium only. No real device, GPU, trackpad, network or signed-in account; the API is mocked throughout.
- How the canvas reads on a real project. Whether four columns, the line styles, draft lines only on selection, and a 500-finding column are readable is for the owner's eye.
- The provider's orderings are tested with a stand-in for React, not React itself: the stand-in runs effects synchronously after each render and has no concurrent rendering. In a browser the checks cover the account switch, the failed reload, the late refusal, an edit during a save and an edit after a reload was asked for; the block-review orderings are covered by the harness only.
- A refused save or reload (401, 403, 404) dropping the kept copy is exercised in the harness, not in a browser.
- Sign-out (as opposed to an account switch) restarting the provider goes through the same session change; the browser check drives the switch only.
- Screen readers were not run. Keyboard behaviour is tested; the detail is a labelled, focusable complementary region.
- Viewer role on the canvas was not exercised in the browser check; the canvas has no editing.
- Frame figures are main-thread only, as in the camera slice. No measurement without CPU slowdown on the final build.

## Not in this slice

The brief's tree on the canvas, hand-placed positions, the jump palette, shared-element transitions from a node to its panel, editing on the canvas.

## Next

1. Owner: open a real project and say whether the canvas is the right home, and whether Overview being one click away is acceptable for a new project.
2. Owner decision still open from the flow slice: panel transition timing (160 ms against design.md's 200 to 300 ms).
3. Then, in the strategy's order: the jump palette, and decision B (hand-placed positions), which needs a server slice.
