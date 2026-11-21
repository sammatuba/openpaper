# VERIFICATION: Spatial workspace, flow slice

Date: 2026-11-19. Intent: [INTENT-spatial-workspace-flow.md](INTENT-spatial-workspace-flow.md). Branch `feat/spatial-workspace`, on top of `3e8dccee`. Client only. Not deployed.

## What changed

- **Panels on demand.** The reader, brief, artifacts panel and add-papers sheet are imported the first time they are needed (`components/project/Deferred.tsx`) and stay mounted afterwards. Once the project is on screen and the browser is idle, their code is fetched ahead of need, unless the browser asks to save data. A failed import shows a notice with Try again and Dismiss.
- **Project data through SWR.** `useProjects`, `useProject`, `useProjectPapers`, `useProjectConversations` keep their return shapes. Hovering or focusing a project card fetches its data.
- **Rules for cached data** (`lib/reads.ts`, pure, tested): responses arriving after sign-out are dropped; a 401, 403 or 404 stands until a later read succeeds; of overlapping reads the later-started decides; a read that begins during a prefetch joins it.
- **Denial at the shell.** A project that is gone or forbidden (401, 403, 404) replaces every view. A plain failure to load does not: the workspace keeps the error states it had. The rail, panels, sheet, upload tracker, and the header's navigation, collaborators and panel buttons are unmounted. The workspace bar stays, and its bundle download is then written from memory instead of fetched.
- **Sign-out** clears the cache, and is announced to other tabs (`BroadcastChannel`). A change of signed-in user by any route clears it too, and is announced. An answer to the identity check that was asked before a sign-out or change is ignored.
- **Transitions.** Panel open, close and swap, last-tab close, and a panel whose code arrives after the click run in a view transition of about 160 ms. No transition under reduced motion or without the API.
- `fetchFromApi` errors carry the HTTP status.

## Measured

Local production build. "Before" is `3e8dccee`, built and measured the same way.

| | Before | After |
| --- | --- | --- |
| Scripts the project route's HTML asks for, legacy polyfill excluded | 46, 1,828.7 KB raw, 563.4 KB gzip (derived: measured 1,938.7 and 602.1 with the polyfill, less its 110.0 and 38.7) | 38, 1,120.5 KB raw, 356.2 KB gzip |
| of which project layout entry only | 891.0 KB raw, 267.2 KB gzip | 175.0 KB raw, 55.3 KB gzip |
| of which page entry | 653.7 KB raw, 201.2 KB gzip | 668.1 KB raw, 207.7 KB gzip |
| Project layout chunk itself | 172.6 KB raw, 49.1 KB gzip | 52.0 KB raw |
| Project API requests on opening a project | 12 | 7 |
| All scripts requested once the network is quiet | 59, 2,115.3 KB raw, 654.3 KB gzip | 67, 2,133.9 KB raw, 667.6 KB gzip |
| All built chunks | 3,889.6 KB raw, 1,179.9 KB gzip | 3,923.1 KB raw, 1,195.3 KB gzip |

Reading the table:

- The scripts the route's document asks for fell by 708 KB raw (207 KB gzip). This is what the document references, not a timing of when the workspace can render.
- Next's build summary reports "First Load JS" for the page rising from 206 to 212 kB. That figure counts the page entry only, not the layout above it. The page entry grew by 6.5 KB gzip because SWR and the read rules are now shared by the page and the provider.
- The total after idle fetching is 18.6 KB raw (13.3 KB gzip) higher. The strategy's rule that the project route ships no more JavaScript than before is **met for startup and not met for the total**.
- The five requests no longer made on open are the artifacts panel's (artifacts, audio, audio jobs, table jobs, chart jobs). They are made when the panel is first opened.
- Second visit to a project with the API answering after 1,500 ms: the project name is shown from cache in 75 to 81 ms in the final run (70 to 380 ms across the runs made during the work).

Not measured: script bytes at the exact moment the project becomes usable. A probe for it did not fire in either build and was removed; with a delayed API, Next's prefetching of linked routes and the idle fetch have all started before the name appears, so a browser sample at that point does not separate the builds. The manifest and document figures above are the deterministic statement.

## Checks run on the final build

| Check | Result |
| --- | --- |
| `tsc --noEmit` | Pass |
| eslint on touched files | 0 errors; 1 warning that predates this work (`ArtifactsPanel.tsx:320`) |
| `npm run test:textfold` (now includes `test-reads.cjs`) | Pass |
| `next build` | Pass |
| `test:research-overview:browser`, 1440 and 390 | Pass, unchanged |
| `test:project-workflow:browser`, 1440 and 390 | Pass, unchanged |
| `test:investigation:browser` | Pass, one step changed (below) |
| `test:map-touch:browser` | Pass, unchanged |
| `test:flow:browser`, 1440, 390, and 1440 with reduced motion | Pass |
| `git diff --check` | Clean |

`test:flow:browser` asserts: hovering a card fetches its project before any click, and opening it adds no second request; a first load that fails with a 500 keeps the workspace and its header controls; no artifacts request and no panel mounted before first open; a failed panel import shows the notice and Try again recovers; Dismiss then reopen is a fresh attempt; each of cold open, close, warm open and last-tab close runs a transition animating the panel (none under reduced motion); two toggles in one tick save the right preference; a rendered PDF page and its canvas are the same elements after the paper list refetches, with no second file-URL request; a cached second visit shows no project skeleton while requests are in flight; on Evidence with the artifacts panel open, a 500 keeps the page, a 404 replaces the view and unmounts the rail list and the panel, a 500 after the 404 does not bring the project back, a 200 does; after the 404 the bundle download is written from memory with no export request, and the header's navigation, brief and artifacts buttons are gone while the link back to the project list stays; sign-out announced from another tab sends this tab to the login page.

## Journey change

`check-investigation-workspace.cjs`: after clicking Close reader, the step now waits up to one second for focus to return to the opener before asserting it. The close is applied inside the transition, one frame after the click, so focus returns a frame later than before. The assertion itself is unchanged.

## Defects found and fixed during verification

1. SWR's `preload()` keeps a prefetched response until the next fetch consumes it. A card hovered and not opened would later be served as fresh, and swallowed a revalidation. Replaced.
2. Closing the artifacts panel saved its preference a frame late, inside the transition; a reload in that frame lost it. The preference is now written at the click.
3. A superseded view transition rejects its promises; these surfaced as page errors. Handled.

## Independent review

`./meos review` (GPT reviewer through Codex, read-only sandbox; it cannot open sockets, so it did not run the browser checks).

| Round | Verdict | Findings | Outcome |
| --- | --- | --- | --- |
| 1, `.meos/reviews/20261119T053513Z.md` | rework | Denied project could reappear after a later network error; prefetch could refill the cache after sign-out; failed prefetch could blank a good load; denial not applied to every view; cold open and last-tab close outside the transition; idle fetch could start before the project loaded; PDF test did not render a PDF | All fixed, with tests |
| 2, `.meos/reviews/20261119T055445Z.md` | rework | Rail and panels kept loaded content after denial; successful prefetch could make SWR discard a newer response; sign-out did not reach other tabs; measurement not at usability and not reconciled with First Load JS; double toggle could save the wrong preference | All fixed with tests, except the at-usability sample, which is reconciled and stated as not measured above |
| 3, `.meos/reviews/20261119T061427Z.md` | rework | Header kept collaborators and the mobile navigation sheet after denial, and the upload tracker stayed; a pending identity check could undo a cross-tab sign-out, and an account switch did not reach other tabs; the recovery download would have asked the server; a render between two toggles could lose the pending preference; the document figure counted a polyfill current browsers skip | All fixed. Browser tests cover the download and the header; the rest are listed under Not verified |
| 4, Claude Opus 5.5, fresh read-only reviewer agent (owner's choice of model; not through `./meos review`, which drives Codex) | accept with findings | Important: the shell was replaced on any first-load failure, not only a denial, against the intent. Minor: the hover test would pass without a prefetch; a timing range in this record did not match the final run; transition 160 ms against design.md's 200 to 300 ms; preference still also written inside state updaters; after an account change in another tab, hooks stay empty until the tab regains focus | Important finding fixed with a test; hover test and timing fixed. The other three are open, below. The fix was made after the verdict and has not been re-reviewed |

Rounds 1 to 3 ran on Codex's configured default, `gpt-6.2-astra` at high reasoning effort. Round 4's reviewer shares a model family with the author; it was given the diff, the intent, this record and the earlier reports, not the author's reasoning. It ran `tsc`, the unit tests and eslint, and read the browser logs; it did not run the browser checks.

Open after round 4:

- Transition timing is 160 ms in and 120 ms out; `client/design.md` says 200 to 300 ms. Owner decision.
- The artifacts preference is written at the click and again inside the state updater a frame later.
- After an account change in another tab, project hooks with nothing in flight stay empty until the tab regains focus or reconnects.

## Not verified

- Chromium only. View transitions in Safari and Firefox were not exercised; without the API the code path is the plain state change.
- No real device, network or signed-in account. The API is mocked in every browser check.
- The sending side of cross-tab sign-out (the sign-out button) is not driven in a browser; the receiving side is. The rules behind it are unit tested.
- `usePapers` and `useActivePapers` (library pages, not project routes) have their own SWR fetchers and do not go through `lib/reads.ts`. Their cache is cleared on sign-out; a response of theirs in flight at that moment is not dropped.
- Whether the transition feels right is a matter for the owner's eye; only that it runs was checked.
- Fixed after review round 3 without a browser test of their own: the upload tracker and a populated collaborators dialog on denial; a render between two artifacts toggles; a slow identity check answered after sign-out; an account switch in another tab. The recovery download after denial was exercised for a saved document, not for one with unsaved edits (that path is the existing local download).

## Not in this slice

The investigation document stays on its own provider. Route-to-route transitions, optimistic writes, the jump palette and panels remembering scroll and level are not built.

## Next

1. Owner: look at the panel transition on a real project and say whether 160 ms and the slide suit.
2. Project canvas (strategy order 3). Its intent must first settle the mount cost of large maps.
