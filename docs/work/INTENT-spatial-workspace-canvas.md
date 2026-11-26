# INTENT: Spatial workspace, project canvas

Date: 2026-11-19. Slice 3 of [STRATEGY-spatial-workspace.md](STRATEGY-spatial-workspace.md); owner decision A (canvas as the project home) was taken on 2026-11-19. Client only. Branch `feat/spatial-workspace`.

## Outcome

Opening a project lands on one map of the whole investigation: the question, the claims, the findings linked to them, the papers the findings come from, and the draft's sections. It moves with the same camera as the brief map. Selecting a node shows what it says and offers the place to read or edit it; a paper opens in the docked reader. The case editor that was the home page is one click away as Overview.

## Scope

1. **Layout** (`lib/project-canvas.ts`, pure, tested). Columns left to right: question and draft sections; claims; findings; papers. Edges: question to claim; claim to finding, named supports, challenges or qualifies; finding to its paper; section to the claims and findings its paragraphs cite. Claims and sections keep document order. Findings sit level with the claims they are linked to, papers level with their findings. Archived claims and findings are left out. Nothing is hand-placed or stored.
2. **Shared surface** (`components/canvas/Surface.tsx`). The camera, pointer, wheel, pinch, keyboard and zoom controls move out of `FoldMap.tsx` unchanged in behaviour, so the brief map and the canvas run on one engine.
3. **Canvas view** at `/projects/[id]`, named Canvas in the destination bar. A selected node shows its text under the map with its actions: a claim opens in Overview or its evidence; a finding opens in Evidence or opens its source in the reader; a paper opens in the reader; a section opens in Write; the question opens Overview. The camera and the selection are remembered for the session, per project, in memory.
4. **Overview** moves to `/projects/[id]/overview`. `/projects/[id]?claim=…` goes on to it, so links saved earlier still land on the claim.
5. **Mount cost, settled by measurement first.** The investigation format caps a project at 100 claims, 500 findings, 1,000 relations and 30 sections, so the canvas is bounded near 630 nodes plus papers, not the 2,000 the strategy designed for. `measure-canvas.cjs` times the first paint of the canvas at a typical size and at the format's maximum with 300 papers, CPU slowed 4×. If the maximum takes over 1 s to show, off-screen nodes skip rendering with `content-visibility` (they stay in the DOM, the tab order and the accessibility tree); unmounting is not used.

## Not in this slice

- The brief's own tree as canvas nodes; the brief keeps its map in the Brief panel.
- Hand-placed positions (decision B), the jump palette, node-to-panel shared-element transitions, optimistic writes, editing on the canvas.
- Typed-array geometry and a layout Worker: only if the measurement shows layout over one frame.
- No server, API, schema or dependency change.

## Boundaries

- The brief map behaves as before: its journeys and the touch check pass with no assertion changed.
- Every node is a real button with an accessible name; arrow keys, `+`, `-`, `0` and focus-into-view work as on the brief map.
- The canvas reads the investigation document in memory, unsaved edits included, and never writes it.
- Overview, Evidence, Write and Discuss are unchanged apart from Overview's address and links to it.
- The project home ships no more JavaScript in its document than it does at `a3b8c877`, or the difference is recorded with its cause.

## Failure cases

| Case | Behaviour |
| --- | --- |
| Nothing recorded yet (no question, claims, findings, sections or papers) | No empty map: a short prompt with the way to Overview and to adding papers |
| Investigation still loading | Skeleton; no map from an empty document |
| Investigation failed to load | The same message Overview shows; papers are not drawn alone |
| Project failed to load, or is denied | As today: the alert, or the shell's denial |
| A finding's paper is not in the project (removed, redacted, unbound) | The finding is drawn without a paper edge; its detail says the source is not available |
| A relation or citation names a missing or archived claim or finding | The edge is left out |
| Selected node disappears (archived, deleted elsewhere) | The selection clears |
| Viewer role | Same map; the actions lead to read-only views |

## Checks

- `tsc --noEmit`, eslint on touched files, production build, `git diff --check`.
- `test:textfold` with a new `test-project-canvas.cjs`: no overlaps, everything inside the bounds, one node per shown entity, edges only between drawn nodes, archived left out, order rules, determinism.
- Existing journeys at 1440 and 390, the touch check and the flow check. Steps that opened the home page to reach Overview now open `/overview`; their assertions stay.
- New `test:canvas:browser` at 1440 and 390: the home page shows the canvas with the fixture's nodes and edges; selecting a claim shows its text and its evidence link; a paper node opens the reader and closing it returns focus to the node; a finding's "Open in Evidence" lands on that finding; leaving and returning restores camera and selection; an empty project shows the prompt; `?claim=` on the home address lands on the claim in Overview; no horizontal page overflow; no page errors.
- `measure-canvas.cjs` figures recorded, with the decision on `content-visibility`.
- `measure:route` against `a3b8c877`.

## Amended during implementation, 2026-11-19

- **A paper opens from its detail, not from a click on its node.** Every click on a node selects it; the reader opens from the "Open in reader" button in the detail, and closing the reader returns focus to that button. Opening a panel on every click made exploring the map's links awkward.
- **Return visits draw from a kept copy.** Leaving a project unmounts the investigation provider, so on coming back the canvas would have waited on the investigation request behind a skeleton, which the flow slice had just removed from the home page. The last saved investigation the server returned is now kept in memory per project (`lib/investigation-snapshot.ts`) and the canvas draws from it until the current copy loads. Rules: memory only, never browser storage; never edited or saved; emptied at sign-out and on a change of user, and an answer asked for before that is not kept; dropped for a project that is denied or whose investigation request is refused (401, 403, 404); the most recent eight projects only. If the current copy then fails to load, the canvas keeps the kept copy and says it is the last saved one.
- **`content-visibility` was measured and declined** (scope item 5). It shortened the warm mount of the largest canvas but made zooming stutter. The 1 s line is therefore not met in every run at 4× slowdown; the figures are in the verification record.
- The destination bar now has five entries and scrolls sideways when the window is too narrow for them.

## Amended after independent review, 2026-11-19

- **The investigation belongs to the session that asked for it.** The provider starts again empty when the signed-in user changes or signs out, so the previous user's document, saved or unsaved, leaves the screen at once. An answer to a request made before the change is not applied.
- **Kept copies follow request order.** Of two requests for a project the later-started decides; a refusal (401, 403, 404) on load, reload or save drops the kept copy; an older answer cannot restore it, and an older refusal cannot remove a newer copy.
- **Only an anchored source ties a finding to a paper.** A redacted source has no edge, no "Open source" and is not listed under the paper.
- **A section's lines to what it cites are drawn only while the section, or a claim or finding it cites, is selected**, and to at most 100 items; the detail says when there are more. A draft can cite 18,000 things; drawing them all buried the argument and was the largest rendering cost.
- **Keyboard.** Opening a node with Enter or Space moves focus into its detail; Escape returns to the node and leaves the detail open; Close returns focus to the node.
- **A failed paper list is not an empty one.** With no list and none cached the canvas says the papers could not be loaded.
- **Camera.** Returning to the canvas restores the camera exactly, also when the selection had been panned out of view. A resize keeps the selected node in view only if it was in view before.

Round 2 added:

- **One ordering decision for what is kept and what is shown.** An answer a later request has overtaken is not applied to the live document, its revision tag or its save state either. A save whose answer is overtaken ends as "Save failed", never as a silent success.
- **A view drawing a kept copy is told when the copy changes**, so a refusal that arrives late removes it from the screen at once.
- **Write honours a link to a section once**, when the section first exists, so the link works from a kept copy before the investigation has loaded.
- **Opening a surface with no saved camera shows the selection**, as the brief map did before the surface was shared; a saved camera is restored untouched.
- **Camera and selection are remembered per signed-in session.**
- **A claim counts once for a finding's placement**, however many relations join them.

Round 3 added:

- **A project denial takes the kept investigation with it wherever it is learned**, including by a card's prefetch on the project list with no workspace open.
- **Denials are subscribed to.** The project hooks re-render when a denial is recorded or lifted by a request they did not make. (Before this, a denial learned by a prefetch stayed on screen after access returned with unchanged data. That fault came with the flow slice.)
- **No reload while a save is in flight**, and one save at a time, so a save's outcome can never be overtaken or land on another save. The earlier amendment's "overtaken save ends as Save failed" now applies only to a save cut off by a denial or a change of user.
- **The investigation is asked for again when access to a denied project returns** and nothing had been loaded. A loaded document is never reloaded this way.

Round 4 added:

- **A reload replaces what is on screen only if nothing was edited or sent to be saved since it was asked for.** Otherwise the newer work stays, with its revision tag, and the reload is reported as failed.
- **While a save is in flight the bar says Saving**, whatever is edited meanwhile, so Save and Ctrl/Cmd+S are not offered until it is answered; the later edit is then unsaved. A block review asked for during a save is sent with the next save, and the document counts as unsaved until it has been.
- **Only a denial of the project itself drops the kept investigation**, not a refusal of its paper list alone (round 3 had included the paper list, which could leave the first load waiting for good).

Round 5 added (not reviewed):

- **A reload also gives way to any save attempted since it was asked for**, finished or not.
- **Block reviews**: each save sends its own list; reviews that arrive during it wait for the next save; a failed save's reviews are tried again; a reload that replaces the draft clears them; only blocks still in the draft are sent.

## Not authorised by this intent

Push, pull request changes, deploy.
