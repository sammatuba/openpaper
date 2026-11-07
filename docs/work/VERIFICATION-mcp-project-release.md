# MCP project release verification

Updated: 2026-11-07. Release is not yet deployed.
Intent: [INTENT-mcp-project-release.md](INTENT-mcp-project-release.md).
Starting feature SHA: `9404869b55ee2c8fc62a4c4f2e6f742769c3a77c`.
Origin was refreshed on 2026-11-07 and its feature ref still matches that SHA.
Implementation is in `/tmp/openpaper-mcp-deploy`; original dirty checkout preserved.

## Review disposition

Initial independent verdict: rework, report
`/tmp/openpaper-mcp-deploy/.meos/reviews/20261107T070014Z.md`.

- Project quota: MCP creation, browser CRUD creation and invitation acceptance
  acquire the same user row lock before the count and hold it through commit.
  The quota query now uses a direct distinct count and fails closed on DB errors.
- Browser project and creator membership commit together.
- Durable original payload hash/user/request ledger is committed with MCP
  project and membership. Rename/edit no longer invalidate matching retries;
  deletion retains history and rejects reuse. Replies contain current metadata.
- Unlink annotation now reflects its destructive association change. The current
  user task authorizes this bounded operation; earlier ecosystem restrictions
  do not prohibit the explicitly requested project-management release. The
  underlying library paper, note and annotation survive in integration tests.
- Required CI runs actual PostgreSQL mappings, quota logic, concurrency and MCP
  HTTP transport rather than only the earlier SQLite substitutes. Only Google's
  external token verifier is substituted in the local transport test.

Second review (`20261107T072244Z.md`) found mixed browser/MCP paper admission
races and the update tool's inaccurate destructive annotation. Fixes now lock
the project across browser batches, PDF association creation and MCP additions;
all new paper links pass quota/duplicate checks under that lock. Batches commit
atomically and count only distinct, new links. A database uniqueness constraint
prevents duplicate associations. Migration retains one row per legacy duplicate
pair without modifying papers, notes or annotations. Both update and unlink tools
now advertise destructive effects, verified in the MCP registry test.

## Executed checks on the fixes

Python: existing server virtualenv, Python 3.12.13. Both checkouts' `server/uv.lock`
SHA256: `fd7dfa8e2935b6eb6346fa4813c383f993f243188e42053073f24cc0b2558994`.
No dependency or lock changes were made.

1. Required integration runner:

   ```bash
   /home/sammatuba/projects/ps/openpaper/server/.venv/bin/python scripts/ci/run_isolated_postgres.py --run-existing
   ```

   Result: **34 tests, OK, zero skips**, latest rerun 6.351 seconds. Log:
   `/tmp/openpaper-release-required.log`. Existing guarded socket-only cluster
   `/tmp/openpaper-pg-transaction-test`, port 55439, no production database.
   Test-owned schemas cleaned up; existing cluster was not stopped or deleted.
   Covers same-UUID concurrent creation; different-UUID/browser/invitation
   last-slot races; rollback on failed membership; rename/deletion/cross-user
   replays; migration upgrade/downgrade; fail-closed quota count; five tool
   transport paths; synthetic verified, missing, invalid, blocked, inactive,
   disallowed, unverified and wrong-audience identities; role and ownership
   denials; unlink preservation; existing MCP note and PDF/table transaction checks.
   Also covers mixed browser/MCP last-paper-slot races and same-paper retries,
   browser batch atomicity/duplicate input, caller-owned transaction rollback,
   migration duplicate-link reconciliation/uniqueness, and update clearing.

2. Full server suite:

   ```bash
   python -m unittest discover -s tests
   ```

   Run from isolated checkout `server/` with the launcher's dummy environment,
   `PYTHON_DOTENV_DISABLED=1`, and `OPENPAPER_ISOLATED_PG_TEST` removed. Reused the
   existing Python executable above, redirected output to
   `/tmp/openpaper-release-full.log`, with a 120-second subprocess timeout.
   Executed outside the sandbox because the sandbox stalls async executor
   shutdown in an unrelated audio test.

   Result: **387 tests, OK, 24 skips**, 6.128 seconds.
   Six skips require a separately migrated browser-OAuth-state database; eighteen
   are guarded PostgreSQL cases (including nine new project cases). All eighteen
   guarded cases also passed in the required runner; the six baseline browser
   OAuth claim cases remain unexecuted in this release check.

3. `git diff --check`: passed.

GitHub Actions has not been run or claimed successful. Previous billing failures
do not stand in for test results. The CI workflow now runs locked dependencies
and the required PostgreSQL launcher on its own disposable cluster.

## Pending release evidence

- Follow-up independent review `20261107T073023Z.md`: **accept**, no blocking or
  important release-code findings. Reviewer independently passed 16 focused
  tests and checked retained full/integration logs. Minor late-batch-failure
  regression recommendation was implemented in the existing PostgreSQL batch
  test; required suite rerun passed all 34 checks without skips. No runtime
  change after acceptance. Retained report: [REVIEW-mcp-project-release.md](REVIEW-mcp-project-release.md).
- Successor commit SHA, build ID/digests, additive migration, both revisions.
- Fresh rollback traffic/revisions/digests; earlier candidates were web
  `openpaper-00009-fb9` and jobs `openpaper-jobs-00006-r7q`.

Preflight refreshed at 2026-11-07T07:23:34Z: same rollback revisions, both at
100% traffic. Account `jansammat26@gmail.com`, configuration `personal`, explicit
target `openpaper-sammatuba`, region `asia-southeast1`. Configuration's default
project was still `health-facility-finder`; deployment script sets the correct
OpenPaper target. Retained client and Caddy latest digests match the running
revision. Complete filtered revision/traffic/digest/secret-reference metadata is
in `.meos/artifacts/mcp-release-preflight.json`; no secret values were read.

Before-release public probes passed homepage200, health200, protected-resource
and authorization-server discovery200 (public Worker origin and S256), anonymous
MCP401/no-store with resource-metadata challenge, and direct Cloud Run health200.
Evidence: `.meos/artifacts/mcp-smoke-before.json`. No Worker routing fix needed.
- Live application health, OAuth discovery, anonymous rejection, authenticated
  registry and operations through an existing authorized MCP connection.
- Existing authorized connection is in the user's ChatGPT custom integration;
  this Codex session exposes no OpenPaper connector. Final authenticated checks
  will need that existing ChatGPT connection. Do not create credentials or
  extract/mint user tokens from the OAuth database or signing secret.
- SwarmLab scaffold/RRL is in the user's prior ChatGPT thread. The final project
  setup handoff must run there; do not fabricate prior results or substitute
  reviewer collusion.
- Project existence check, persisted creation request UUID, project ID and replay.

No build, deployment, schema change to Neon, project creation, paper import,
secret rotation, Worker change or PR merge has been performed in this release.
