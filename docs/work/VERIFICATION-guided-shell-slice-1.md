# VERIFICATION: Guided shell, slice 1 (P03a)

Date: 2026-11-18. Intent: [INTENT-guided-shell-slice-1.md](INTENT-guided-shell-slice-1.md). Branch `feat/guided-shell`, based on `1c6e1f9f`. Client only; no server, schema or API change. Not pushed, not deployed.

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

## Not executed

- Server suites: no server file changed, so they were not rerun.
- Authenticated production acceptance and deployment: no operator session; nothing deployed.
- Firefox/Safari: only Chromium was run. `ProseField` has a scripted height fallback for browsers without `field-sizing`, untested.
- Independent review (`./meos review`): not run.
- Unfamiliar-user first-value exercise (C03): needs a person.
