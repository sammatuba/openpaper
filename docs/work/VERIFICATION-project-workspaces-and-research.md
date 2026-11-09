# First research workspace slice: verification and exact continuation

Date: 2026-11-04. User requested wrapup before completing remaining live setup.
Intent: [INTENT-project-workspaces-and-research.md](INTENT-project-workspaces-and-research.md).

## Implemented locally

- Shared public HTTPS PDF downloader for browser/MCP: pinned addresses, redirect
  revalidation, actual PDF validation, hard child-process deadline, safe errors.
- Finite SELECT-only passage backfill preview; normal indexing preserves global
  trigger state and repairs missing vectors with bounded batches/savepoints.
- Explicit disposable PostgreSQL CI launcher, expanded test lanes and portable
  migration paths. OAuth state tests now refuse configured/live databases and
  use isolated schemas instead of import-time probing and broad cleanup.
- Local workspace bind/doctor/brief CLI with account/origin/project checks,
  pinned no-follow directory descriptors, no-clobber creation and bounded reads.
  A parallel review found a directory-swap race; the implementation and race
  regressions now address it. Actual sibling binding has NOT been created.
- Seven-paper comparison,14 candidate evidence records, disagreements and
  experiment specification in `docs/research/ai-reviewer-collusion/`.
  Sixteen synthetic fixtures test the scoring contract; no model results claimed.

## Executed checks

- Server discovery:393 tests in6.966s, OK with21 database tests skipped by the
  default unit lane. Log `/tmp/openpaper-w0-server-unit.log`.
- Required PostgreSQL launcher after OAuth isolation:21 tests, zero skips,
 5.206s (maintenance agent). Earlier root integration run15 passed7.655s before
  the additional six OAuth tests joined the lane.
- Maintenance unit9 and actual PostgreSQL4 pass. Launcher safety5 pass.
  Agent separately proved fresh bootstrap/stop/owned cleanup with injected
  unique temporary paths/port55440, preserving the existing55439 cluster.
- Jobs21 tests passed0.123s with normal IPC and dummy credentials. Restricted
  execution stalled and was stopped. One permission review timed out; its
  permitted retry succeeded. No unresolved approval rejection remains.
- Research tools36 passed0.032s on final root rerun, including16 workspace tests
  and six synthetic harness tests. Worker node test1 passes. Client direct
  `node_modules/.bin/tsc --noEmit` passes; local Yarn executable was unavailable.
  No new frontend build or hosted GitHub Actions run is claimed this pass.
- Packet verifier validates7 sources/14 candidates. Root re-extracted every
  excerpt from original primary input bytes and verified raw/extracted hashes,
  offsets and page/line locations. PDF font warnings occurred; selected plain
  text excerpts verified, with no numeric/formula extraction claims.
- Raw primary inputs copied with hash checks into ignored
  `.meos/artifacts/collusion-r1-sources`; originals also remain under
  `/tmp/openpaper-collusion-r1-sources`. These files are not in Git. Run:

```sh
rtk proxy server/.venv/bin/python docs/research/ai-reviewer-collusion/verify_packet.py --source-dir .meos/artifacts/collusion-r1-sources
rtk proxy python3 -m unittest discover -s scripts/research -p 'test_*.py'
rtk proxy server/.venv/bin/python scripts/ci/run_isolated_postgres.py --run-existing
```

The last command requires the existing exact socket-only temporary cluster;
without `--run-existing`, the launcher creates its own and refuses an existing
directory. Do not delete the current test cluster as a routine setup step.

## Live connector observation at wrapup

Tool discovery now exposes all15 tools. Authenticated project context succeeded
for project `a5cf0e26-f8dd-424c-a452-dbcf6ebba946` and returned two papers:

- Existing collusion report: `3fe7dc45-ca32-42d8-8505-6b513a834853`.
- MT-Bench: `bcd665b8-c545-4586-8dee-baf54d4ccfa1`.

Both have highlights and no private note content in this readback. Project
evidence search returned indexed collusion passages. Exact fetch acceptance
and note writes were not newly exercised. Do NOT resubmit MT-Bench: it is
already in the live project. Real attachment handoff remains unverified.

## Review and remaining actions

Independent MEOS review requested: `.meos/reviews/20261104T054504Z.md`.
Read its final verdict; do not assume acceptance while the process is running.

Source remains uncommitted on `master` at40e390800668. No new deployment,
production maintenance, library import, paid model call, or sibling file edit
occurred in this implementation pass. The prior recorded live server remains
revision9; frontend SSR fix and this reliability slice remain undeployed.

Next: resolve review findings; then use WORKSPACES.md's exact bind command to
create the local-only binding in the existing ai-safety collusion directory.
Follow ai-safety's decision/status protocol and run its checker. An online bind
needs a separately valid browser session; the CLI does not reuse ChatGPT OAuth.
Promote the staged research packet deliberately after review; keep candidate
labels and existing hypothesis results. Complete paginated exports, release
alignment and remaining architecture packages in subsequent bounded intents.
