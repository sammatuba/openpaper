# Investigation workspace — acceptance and verification

Intent: [INTENT-investigation-workspace.md](INTENT-investigation-workspace.md).
Implementation contracts: [PLAN-investigation-workspace.md](PLAN-investigation-workspace.md).
This matrix defines the contract. Executed results are recorded in
[VERIFICATION-investigation-workspace.md](VERIFICATION-investigation-workspace.md).
A01–A24 pass; A25 automated rollout/public checks pass, with current-account
authenticated production UI acceptance still open.

## Reproducible fixture

[investigation-workspace-fixture.json](investigation-workspace-fixture.json) is
synthetic test input, not evidence about real papers. Seed it into the existing
socket-only PostgreSQL fixture, with an owner, editor, viewer and outsider, plus
another project/paper accessible only to the outsider. Associate sources A/B
only with the fixture project. Store the exact raw_content strings and use
their line-2 quotations. Do not seed production or use any real account IDs.

Use this fixture in schema/service/API/browser tests so saved state is mutable
and later GET/reload reflects earlier writes. Source changes and revocations
must actually change the backing fixture. A constant success response for
every request is not evidence of persistence, conflict behavior or correctness.

The manual journey creates the fixture claim, attaches A as supporting and B as
qualifying, compares their setups, records the proposed signaling explanation,
adds the expected qualified paragraph and both references, saves and reloads.
Changing A to its replacement text must retain the saved paragraph and old
anchor with a review warning. Unlinking B must show/redact its unavailable
source on subsequent reads. Re-anchoring and reviewing are deliberate actions.

## Acceptance matrix

| ID | Observable pass condition |
| --- | --- |
| A01 — existing projects | GET/render of a project with description and imported research_brief creates no investigation row and changes neither field. An empty project has a useful question-entry state. Start from existing brief is explicit, unsaved and creates no findings. |
| A02 — native provenance | No iframe/srcDoc/window.open reader exists in the new Case/Evidence/Draft flow. Browser interactions exercise the actual derived upstream pieces/zoom/map engine. Generator check reproduces ESM/CSS from pinned inputs with auditable patches; license/notice and original manifests pass. A superficial commit data attribute alone does not prove reuse. |
| A03 — five levels | Topic/Takeaway/Key/Brief/Full, 1–5 keys, buttons, continuous wheel/pinch behavior, local paragraph expansion and Topic-map links work on actual rendered text. Stable pieces/source anchors survive level changes. Full/Brief preserve source wording; locally excerpted and AI-written levels are distinguishable. |
| A04 — scoped lifecycle | Mount two documents simultaneously; each level/selection/scroll belongs to its own reader. Text input elsewhere keeps 1–5 and Ctrl/Meta shortcuts. Mount/unmount/navigate at least 20 times: listener/observer/timer accounting returns to baseline and no old document/user callback fires. Reader never mutates the app root theme or hijacks whole-page scroll. |
| A05 — presentation | Actual project shell at 1440px and 390px, light/dark and reduced-motion settings. Clear active view, no horizontal overflow, usable source comparison, focus restoration, keyboard selection and mobile Back. Theme changes do not remount the reader or erase editor text. Existing artifact/rail preferences work. |
| A06 — claim/finding model | One paper supplies multiple findings; one finding supports one claim and qualifies another. Result, author interpretation, our inference, setup and caveats remain distinct after save/reload. Archived dependencies remain addressable; dangling/duplicate IDs and relation triples are rejected. |
| A07 — exact anchor | Server accepts the fixture's exact inclusive extracted-text line range and hashes, rejects a forged quote/hash, changed-source attach and outside-project paper. UTF-8/Unicode/newline edge cases match across client/server. Display unverified page mapping as unknown. Source text selection works without an index/backfill. |
| A08 — comparison | Compare A/B without leaving the case: result, source, setup differences and limitations visible; candidate reconciliation saved as an interpretation. Neither empty counterevidence nor source counts imply confidence/novelty. |
| A09 — manual draft | Explicit creation/reordering of sections, paragraph editing and selected-evidence insertion, source quote and gap blocks work. Manual drafting works with no model credits. Cancel insertion causes no save. Save/reload retains text, citations and dependency pins. |
| A10 — roundtrip journey | Finish question → claim → both findings → exact quotation → comparison → qualified paragraph → save → full reload → click each citation back to its source. Assertions inspect real values/links, not just headings. |
| A11 — changed dependencies | Changing source A, claim caveat, finding interpretation/setup or link kind/rationale flags the existing paragraph. Archiving a dependency also flags it. Text and old pins remain; an ordinary save does not clear the warning. Explicit reviewed-block acknowledgment clears it only for current accessible dependencies. |
| A12 — source availability | Unlink/delete B and revoke membership in separate cases. Subsequent GET/export/proposal creation cannot disclose unavailable captured source quotes/bibliography or private notes. Tombstones and authored prose remain usable. Redacted-placeholder roundtrip does not erase/reintroduce the canonical source snapshot. |
| A13 — conditional save | Missing If-Match428; stale412; valid200 with incremented ETag. Concurrent first saves and concurrent updates yield one winner/one412. Failed validation/DB commit leaves all original state intact. A client keeps unsaved text on412/500/network loss. A cancelled conflict reload does not discard it. |
| A14 — role boundaries | Owner/admin/editor can save; viewer can read/export but cannot save/generate; outsider/other project404; unauthenticated401. Revoke role after initial load or while generation runs and recheck on next write/read. Legacy brief/settings permissions remain unchanged. |
| A15 — assistant action boundary | Navigation, folding, choosing sources, Save, export, creating a pending draft request and proposal discard make zero provider calls. Explicit run makes one fake-provider invocation, with exactly the chosen current source context/provider and existing quota/message accounting. |
| A16 — assistant identity | Concurrent duplicate create/run, lost response, pending/running/completed replay, changed payload under same UUID, deleted result, timeout and process uncertainty never silently create a second model call. Status read never reruns work. Replaying with lost permissions reveals no result/context. |
| A17 — assistant failures | Credit denial, unavailable provider, no selected current finding, invalid output, empty/error-only stream, cancellation and timeout preserve manuscript/input. Show useful failure/recovery actions, no empty successful proposal and no automatic retry. No running marker is falsely labelled completed. |
| A18 — proposal review | Known finding markers become traceable chips; invented marker UUID is rejected. Uncited sentences stay visibly uncited; arbitrary URLs/[1] text never becomes validated citation metadata. AI prose/edits retain provenance. Insertion/discard is explicit and stale workspace/source/section changes cannot overwrite the draft. |
| A19 — source navigation | Click a draft finding → correct evidence → verified exact quotation → existing project PDF pane, retaining active claim/draft/unsaved text. A real local fixture PDF loads; failed text location shows the extracted quote and an honest unmapped state. Existing chat citation search still works. |
| A20 — portable exports | Saved bundle roundtrips through preview/ID remapping into an unsaved document. Source access is revalidated. Markdown and BibTeX deduplicate references deterministically, escape text, preserve known provenance/location and expose stale/missing/uncited warnings. No invented metadata, hidden quote, signed URL or credential appears. Unsaved export is identified correctly. |
| A21 — hostile input/bounds | Reject invalid formats, booleans-as-versions, oversize UTF-8 payloads/context/output, duplicate/cross-project refs, unsupported provider and bad ETags. Imported Markdown/extension fields with scripts, event attributes, frames and javascript links cannot execute inside native DOM or exported content. |
| A22 — compatibility | Existing imported/local Textfold briefs retain original wording, anchors, provenance/extensions and JSON import/export. Legacy annotations can be exported, never auto-shared. Existing guided/freeform discussions, PDF upload/status, citations, projects/MCP tools and thumbnail regressions pass. |
| A23 — database rollout | One Alembic head reachable from project_research_brief_01. Isolated upgrade creates both tables and leaves old description/brief/papers/messages intact. Disposable downgrade test only: upgrade/downgrade/upgrade is understood. Application rollback keeps authored investigation data in place. |
| A24 — execution evidence | Production client build/typecheck, reader/parser/vendor checks, focused browser suites, required isolated database suites with zero skips and full server/jobs/tool suites pass. Capture logs, environment/tool versions and screenshots; explain pre-existing warnings/skips. Independent reviewer accepts final feature diff and resolved findings. |
| A25 — release readiness | Source/build/migration inputs, exact image/revision checks, smoke/auth/account acceptance and rollback instructions are concrete. Report local-only versus actually deployed status accurately. No production/cloud/model operations occur merely to finish local acceptance. |

## Required test placement

- Add `server/tests/test_project_investigation.py` for strict schemas, anchors,
  digests, export/import and no-provider behavior.
- Add `server/tests/test_project_investigation_postgres.py` for actual API,
  source/role checks, redaction, concurrent saves, migrations and request-ledger
  claims using the existing guarded fixture. Register it in
  `scripts/ci/run_isolated_postgres.py`; any required skip fails the gate.
- Add `server/tests/test_project_draft_requests.py` for the real stream/service
  path with an instrumented fake provider, current credits/messages, replay,
  cancellation and stale proposal behavior. Required DB variants belong in the
  guarded suite, not in a skipped mock-only replacement.
- Add native adapter/source fidelity tests and
  `client/scripts/check-investigation-workspace.cjs`; expose npm scripts
  `test:textfold-native` and `test:investigation:browser`.
- Adapt existing research-overview/project-workflow browser suites to the native
  mount and new entry points while retaining their behavior assertions. Do not
  simply remove failed legacy assertions to make the new UI pass.
- Include new non-browser checks in existing CI. Browser evidence must come
  from the production build with the actual default project shell. Browser API
  mocks must mutate backing state, return accurate ETags/statuses and fail on
  unexpected API/model/external requests. Run separate actual PostgreSQL HTTP
  tests so browser mocking cannot stand in for backend persistence/security.

## Commands and environments

Use the project's locked Python/Yarn versions. Do not upgrade dependencies to
make a check pass without a documented incompatibility. All shell commands use
RTK. Record the actual command and working directory, not only “tests passed.”

From repository root, the required database runner (uses its own scrubbed env):

```bash
rtk proxy server/.venv/bin/python scripts/ci/run_isolated_postgres.py
```

If it refuses an existing dedicated cluster, inspect its identity first. Use
`--run-existing` deliberately only when its data-directory/socket/ownership/TCP
guards pass. Never stop/delete someone else's cluster or substitute DATABASE_URL.
If the local venv is missing, install the locked server environment first with
`rtk proxy uv sync --locked` in the server working directory.

For full server tests, use the existing runner's scrubbed test_environment,
disable its integration flag for this pass and retain no real provider secrets:

```bash
rtk proxy python3 - <<'PY'
from pathlib import Path
import subprocess
from scripts.ci.run_isolated_postgres import test_environment
root = Path.cwd()
env = test_environment()
env['OPENPAPER_ISOLATED_PG_TEST'] = '0'
raise SystemExit(subprocess.run([
    str(root / 'server/.venv/bin/python'), '-m', 'unittest', 'discover',
    '-s', str(root / 'server/tests')
], cwd='/tmp', env=env).returncode)
PY
```

In the **client** working directory:

```bash
rtk proxy ./node_modules/.bin/tsc --noEmit
rtk proxy npm run test:textfold
rtk proxy npm run test:textfold-native
rtk proxy npm run build
rtk proxy npm run test:research-overview:browser
rtk proxy npm run test:project-workflow:browser
rtk proxy npm run test:investigation:browser
```

Start the built frontend locally on port3011 before browser commands, using the
existing harness environment (`OPENPAPER_BROWSER_BASE`,
`OPENPAPER_PLAYWRIGHT_MODULE`, `OPENPAPER_CHROMIUM`). Discover current installed
browser paths rather than assuming `/tmp` or a previous npm cache survives.
Bind to loopback, keep a managed process ID, stop only that process afterward.
No real auth token or production API is needed: browser fixtures intercept all
API/model calls and load a local PDF. No real model call is needed for any
acceptance ID.

Run jobs/tests, Worker and local research/CI tool checks with the existing dummy
environment documented in `.github/workflows/test.yml`; do not source app .env
files. From root, the tool checks are:

```bash
rtk proxy node --test deploy/cloudflare/worker.test.mjs
rtk proxy python3 -m unittest discover -s scripts/research -p 'test_*.py'
rtk proxy python3 -m unittest discover -s scripts/ci -p 'test_*.py'
rtk git diff --check
```

Check the migration graph and upgrade on the disposable database, not by
running unqualified Alembic against the configured application environment.
Run `rtk proxy bash ./meos review --base <recorded-feature-base> --note ...`
after the final code/evidence update. Supply an explicit feature base so the
review covers all implementation commits and relevant uncommitted files, not
merely the last commit on master. Include referenced new tests/docs. Resolve
material findings; rerun changed/affected gates and obtain a final verdict.

## Evidence record

Create `docs/work/VERIFICATION-investigation-workspace.md` during execution
with one row per A01–A25: pending/pass/fail, test name/command, actual result and
artifact. Keep full stdout and synthetic screenshots under a session-specific
`.meos/artifacts/` directory or named /tmp paths, with a persistent written
summary in the verification file. Capture Case/Evidence/Draft at desktop/mobile,
source comparison, source-changed warning and assistant review/failure states.
Record which checks the independent reviewer actually reran and which it only
assessed from logs. Never reuse thumbnail-test counts as this feature's results.
