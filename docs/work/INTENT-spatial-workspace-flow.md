# INTENT: Spatial workspace, flow slice

Date: 2026-11-19. Slice 2 of [STRATEGY-spatial-workspace.md](STRATEGY-spatial-workspace.md). Client only. Branch `feat/spatial-workspace`.

## Outcome

Opening a project a second time shows its content at once instead of a skeleton. The project route loads less JavaScript and makes fewer requests before it is usable. The right-hand panels open and close with a short transition instead of a jump.

## Scope

1. **Panels load on demand.** The reader, the brief, the artifacts panel and the add-papers sheet leave the project layout chunk. Each loads the first time it is needed and stays mounted afterwards. They are fetched in idle time after the page is usable, unless the browser asks to save data.
2. **Project data through SWR.** `useProjects`, `useProject`, `useProjectPapers` and `useProjectConversations` keep their return shapes and move to SWR: cached value first, revalidate after. Hovering or focusing a project card fetches that project's data ahead of the click.
3. **Panel transitions.** Panel open, close and switch run inside a native view transition, about 160 ms. Browsers without the API and users who ask for reduced motion get the instant switch they have now.

## Not in this slice

- The investigation document stays on its own provider. It holds unsaved edits and a revision tag; a cache that revalidates under it could overwrite work.
- Route-to-route transitions (Overview to Evidence). They need an experimental Next.js flag.
- Optimistic writes, the jump palette, and panels remembering scroll and level. The palette belongs with the project canvas.
- No server, API or schema change. No new dependency.

## Boundaries

- Every existing selector, label and keyboard behaviour of the panels stays. The three browser journeys pass with no assertion weakened.
- The artifacts panel today fetches five endpoints on every project load even when closed. After this slice it fetches them when first opened. Nothing outside the panel reads that data. A job that finishes while the panel has never been opened is shown when it is opened, as now.
- A reader that is open keeps its PDF mounted when the paper list revalidates: the signed file URL patched into a paper is kept across a refetch.
- Cached data belongs to the signed-in user. Signing out clears the cache.

## Failure cases

| Case | Behaviour |
| --- | --- |
| A panel's code fails to load | A notice names the panel and offers Try again and Dismiss. The rest of the workspace keeps working |
| Revalidation fails on the network while cached data is shown | The cached data stays. No error replaces the page |
| The project is gone or access was removed (401, 403, 404) | The error replaces the cached project, as a first load would show it |
| First load fails | Same error states as today |
| Two panel changes in quick succession | Both state changes apply in order; the earlier transition is skipped |

## Amended after independent review, 2026-11-19

- "Signing out clears the cache" also covers a response still in flight at sign-out, sign-out in another tab, and a change of signed-in user by any route.
- A denial (401, 403, 404) stands until a later read succeeds. It replaces every view at the workspace shell and unmounts the rail, the panels and the sheet. The workspace bar stays so work in memory can be downloaded.
- A read that begins while a card's prefetch is in flight joins it. A prefetch never overrides a newer read.
- A panel whose code arrives after the click, and closing the last reader tab, also run in the transition. The idle fetch of panel code waits for the project to be on screen.
- A panel change is applied one frame after the click. One journey step (reader close restores focus) now waits for the focus instead of reading it in the same tick; its assertion is unchanged. This qualifies the boundary "no assertion weakened".
- The weight check is stated on what the route's HTML loads, with the page and layout entries shown apart.

## Checks

- `tsc --noEmit`, eslint on touched files, `test:textfold`, production build.
- The three browser journeys at 1440 and 390, and the touch check.
- New browser check `test:flow:browser`:
  - no artifacts request before the panel is first opened; the panel then opens and requests them;
  - with panel code blocked, opening the brief shows the notice; unblocked, Try again opens it;
  - a second visit to a project with a slow API shows the project name without waiting for the response;
  - a failed revalidation leaves the content in place; a 404 revalidation shows the error;
  - an open reader's PDF pane is the same element after the paper list refetches.
- `measure:bundle` before and after: project layout chunk smaller than 172.6 KB.
