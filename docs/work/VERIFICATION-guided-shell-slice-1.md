# VERIFICATION: Guided shell, slice 1 (P03a)

Date: 2026-11-18. Intent: [INTENT-guided-shell-slice-1.md](INTENT-guided-shell-slice-1.md). Branch `feat/guided-shell`, based on `1c6e1f9f`. Client only; no server, schema or API change. Pushed and deployed; see Deployment below.

## What changed

- `client/src/components/project/investigation/`: `WorkspaceBar` (destinations, save state, Save, export/import, conflict banner), `OverviewView`, `EvidenceView`, `DraftView`, `shared` primitives.
- `projects/[projectId]/page.tsx` is the Overview. The discussion starter and working brief moved unchanged to `projects/[projectId]/discuss`.
- `InvestigationWorkspace.tsx` removed; `DraftAssistant.tsx` restyled with the same logic and network calls.
- `ProjectRail`: the "Research workspace" link is gone (destinations are in the bar); "Start a discussion" points at `/discuss`.

## Behaviour changes a reviewer should know

- Save is disabled until there is an unsaved change; Ctrl/Cmd+S saves. Viewers are not shown Save or mutation controls (previously shown disabled).
- "Reload latest" and bundle import confirm in an in-page dialog instead of `window.confirm`. The unsaved-leave guard is unchanged.
- Evidence: sources can be found by search (`/sources/search`, existing endpoint) as well as by line; the anchored quote still always comes from `/sources/{paper_id}`. A relation can now be removed. A relationship kind that would duplicate an existing claim/finding/kind triple is not selectable.
- Evidence gap text is limited to 10,000 characters in the field, matching the schema (the old field allowed 20,000 and failed at save).
- Finding cards and per-section add panels are collapsed by default once content exists.

## Executed checks (WSL, Node 22.23.1, production build)

| Check | Result |
| --- | --- |
| `tsc --noEmit` | Pass |
| `eslint` on `src/components/project` and the project routes | Pass, 0 errors; 1 pre-existing warning in `ArtifactsPanel.tsx` |
| `npm run test:textfold` | Pass |
| `npm run build` | Pass |
| `npm run test:investigation:browser` (1440 and 390) | Pass |
| `npm run test:project-workflow:browser` (1440 and 390) | Pass on rerun; the first run timed out on the initial page load |
| `npm run test:research-overview:browser` (1440 and 390) | Pass |
| `git diff --check` | Pass |

The investigation journey keeps every earlier assertion (capture → relation → comparison → draft → save → reload; assistant review/discard/insert with provider-call counts 0/1/2; 412 and 500 preserving text; leave guard; native preview attribution and finding links; theme change without remount; source-changed state; viewer read-only; no unexpected API request). Added: destination bar state, next-step guide at "state the question" then "capture a finding" then absent when complete, claim evidence counts, the discussion starter no longer stacked under the case, no horizontal page overflow on Overview, Evidence and Write.

Screenshots in `.meos/artifacts/investigation-workspace/` (local, ignored): `overview-{1440,390}.png`, `overview-dark-{1440,390}.png`, `evidence-{1440,390}.png`, `write-{1440,390}.png` plus the regenerated earlier set. Inspected by eye: Overview light 1440, Overview dark 390, Evidence 1440, comparison 390, Write 1440, assistant review 1440.

## Review round 1 (`.meos/reviews/20261118T114503Z.md`, verdict rework) and corrections

| Finding | Correction | Evidence |
| --- | --- | --- |
| Discussion starter wrote the prompt and brief to localStorage (pre-existing, carried into `/discuss`) | The pending prompt and mentions are handed over through an in-memory map on `ProjectWorkspaceProvider`; nothing is written to browser storage | Workflow journey asserts no `pending-*` storage key after a discussion starts; the prompt still dispatches once |
| Write link dropped `?block=` when returning from a citation | The Write destination forwards a `block` parameter that names an existing block | Investigation journey waits for `/draft?block=<citing block>` and asserts that block is in the viewport, for both findings |
| Ctrl/Cmd+S saved an unchanged document | The shortcut uses the same condition as the Save button | Journey: one PUT for a changed document via the shortcut, zero for an unchanged one, revision stays 1 |
| A failed project request rendered an unexplained read-only Overview | Overview shows the project error or "Project not found" | Journey: project GET 500 shows an alert and no case fields |
| Journey could not exercise capture by search | Search mock added; the first finding is captured through "Use these lines" after one failed inspection that offers nothing to attach | Saved quote and both digests equal the inspected lines; the search excerpt is deliberately different text |
| `h1` always read "The case" | The `h1` is the research question, with a fallback when empty | Journey asserts the level-1 heading name |
| Visual inspection incomplete | Overview, Evidence and Write are captured at 1440 and 390 in light and dark (12 files) | Inspected by eye in addition to the earlier set: Evidence dark 1440, Write dark 390, Evidence light 390 |
| Intent's provider boundary contradicted Discuss | Intent now names the two explicit provider actions | [INTENT-guided-shell-slice-1.md](INTENT-guided-shell-slice-1.md) |

After the corrections: `tsc --noEmit`, eslint (0 errors), production build and all three browser journeys pass at both widths, first run each.

## Review round 2

The Codex reviewer ran out of workspace credits before a verdict (`.meos/reviews/20261118T115550Z.md`, incomplete). A stand-in review by a fresh agent with no authoring context read the branch against the baseline and returned **accept** with seven findings, none blocking. This is a stand-in, not parity with the Codex gate: it was a read-through and executed nothing.

| Finding | Disposition |
| --- | --- |
| Moving a claim swapped it with a hidden archived neighbour, so the move looked dead | Fixed: a move swaps with the neighbouring claim on screen; the menu items disable from visible neighbours. Not asserted by a journey |
| A save refused by client validation showed a truncated reason | Fixed: the full reason is shown in an alert under the bar with Download unsaved. Not asserted by a journey |
| "New Chat" on Past Conversations linked to the Overview | Fixed: links to the discussion starter |
| Ctrl/Cmd+S disabled the fields mid-typing and dropped focus | Fixed: fields are no longer disabled while saving; the provider already keeps edits made during a save and leaves the document unsaved |
| Reordering sections in an empty manuscript unmounted the auto-opened add panel and its assistant state | Fixed |
| "Add a paper" flashed as the next step while papers were loading | Fixed |
| A hard reload before a new discussion consumes its first prompt loses the prompt | Accepted: the cost of keeping research text out of browser storage; the conversation exists and the prompt can be retyped |

After these: `tsc --noEmit`, eslint (0 errors), production build and all three browser journeys pass at both widths, first run each.

## Deployment (2026-11-18, owner instruction)

Client container only. Cloud Build `502daac4-5348-4f8d-ae04-3abc862e569b` from `fc39aa29`, image `client@sha256:8283db3b57cd7e8246f738be1ab84009cb1695bd92b51b8f752d5867268b7a82` (its tag is `guided-` with no commit suffix because of a quoting slip; the digest is the reference). Staged without traffic as `openpaper-00017-lax`, smoke-checked, then moved to 100%; staging tag removed. Server and Caddy image digests are unchanged from the previous revision. No migration ran. Rollback: `gcloud run services update-traffic openpaper --region asia-southeast1 --to-revisions openpaper-00014-vjm=100`.

Smoke on the staged URL and then on `papers.sammatuba.workers.dev` and the `run.app` host: `/api/health` 200, `/` 200, `/login` 200, `/projects` 200, the new `/projects/{id}/discuss` route 200, unauthenticated investigation 401, unauthenticated MCP POST 401. The signed-in interface on real data was not exercised.

## Not executed

- Server suites: no server file changed, so they were not rerun.
- Authenticated production acceptance: no operator session.
- Firefox/Safari: only Chromium was run. `ProseField` has a scripted height fallback for browsers without `field-sizing`, untested.
- Independent review (`./meos review`): not run.
- Unfamiliar-user first-value exercise (C03): needs a person.
