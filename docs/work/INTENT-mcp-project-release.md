# Intent: finish the authenticated MCP project release

Status: implemented, independently accepted and deployed; public checks passed.
Authenticated live acceptance and SwarmLab setup await the existing ChatGPT thread.
Evidence: [VERIFICATION-mcp-project-release.md](VERIFICATION-mcp-project-release.md).
Opened: 2026-11-07. User requested a proper plan following independent review.

## Outcome and authority

Fix and verify the project-management extension based on
`9404869b55ee2c8fc62a4c4f2e6f742769c3a77c`, deploy the reviewed successor commit
to the existing personal Cloud Run installation, verify live behavior, then
create **MEOS SwarmLab — Swarm Alignment 2026** through authenticated MCP.
PR #1 remains separate; deployment does not authorize merging it.

The current user request authorizes project management, including unlinking a
paper from a project. Record this bounded extension to the older research
intent's no-destructive-writes boundary. Unlinking must be accurately annotated
as destructive and must preserve the library paper, notes and annotations.
Project deletion and role administration are outside the MCP extension.

## Workspace and existing evidence

- Preserve the original dirty master checkout at
  `/home/sammatuba/projects/ps/openpaper`; do not stash, reset or overwrite it.
- Continue in `/tmp/openpaper-mcp-deploy`, the isolated local clone on
  `feat/mcp-project-management`. Recheck its origin and fetched refs before
  committing or publishing: its origin currently points to the original local
  repository, not GitHub. Reconcile any newer remote feature commits by
  fast-forward only; stop and inspect divergence rather than reset it.
- Keep this intent separate from the unrelated live research work pointer.
- Previous evidence at the starting SHA: full server suite 377 tests with 15
  skips; focused MCP suite 20 tests with no skips on a guarded local cluster.
  Full suite required execution outside the sandbox to avoid an async executor
  shutdown stall. These counts are baseline evidence, not acceptance of fixes.
- An additional untracked ASGI MCP exercise passed all five project tools for
  synthetic admin/editor/viewer/non-member identities against actual PostgreSQL.
  Google verification and quotas were stubbed. Promote and strengthen this
  harness rather than describe it as real Google OAuth verification.
- Independent review: `/tmp/openpaper-mcp-deploy/.meos/reviews/20261107T070014Z.md`,
  verdict rework. Review findings concern quota races, mutable retry state,
  unlink annotation/boundary, and insufficient integration evidence.

## 1. Make project admission atomic across entry points

Use one transaction protocol for browser creation, MCP creation and invitation
acceptance. Acquire the authenticated user's database row lock before counting
accessible projects and hold it until membership/project creation commits.
Audit every path that adds project membership and use the same protocol wherever
it consumes this quota. Preserve current subscription semantics: accessible
projects, including memberships, count toward the limit.

Use a direct, distinct database count for the quota gate. The existing metadata
listing catches errors and returns an empty list; a database error must fail
closed rather than grant capacity. Keep unrelated metadata listing behavior
outside the fix. Ensure telemetry cannot commit or release the quota lock before
the write. Create a project and its creator membership in one transaction;
the current browser CRUD commits them separately. Preserve the browser's public
response shape and intended quota-denial status.

Acceptance: at the last available slot, concurrent different-UUID MCP requests,
browser/MCP requests, and invitation/creation requests admit at most one new
project membership. Same-UUID concurrent calls return one project. A failed
membership insertion leaves no orphan project or consumed request record.

Follow-up review extends the same protocol to paper admissions: browser batches,
PDF-upload associations and MCP additions lock the project before duplicate and
quota checks. Enforce a unique project/paper association. The additive migration
may collapse redundant duplicate association rows while preserving every logical
link and all library papers/notes/annotations. Browser batches commit atomically.

## 2. Persist the original creation request

Add an additive Alembic migration and mapped request ledger keyed by authenticated
user ID and request UUID. Persist a canonical original-payload hash and the
created project ID in the same transaction as project and admin membership.
Define canonicalization explicitly: normalized UUID, trimmed title, and the
validated description, with omitted description equivalent to null.

Check committed request history before quota admission. Matching retries return
the same project ID without consuming quota, even after rename or description
changes; a different original payload fails. Retain the ledger if the project is
deleted, and return a clear previously-deleted result/error without recreating
it. Do not use a cascading project foreign key that erases this history. Define
whether replay metadata reflects current project state in documentation and
tests; use current metadata plus `already_created` for an existing project.
User deletion may remove that user's request history.

Acceptance: sequential and concurrent replays; replay after rename and description
change; replay after deletion; mismatched payload; cross-user UUID isolation;
quota exhausted after an earlier success; rollback/retry after failed commit.
Exercise PostgreSQL uniqueness and real models, not only SQLite substitutes.

## 3. Correct the tool contract and retain integration tests

Set the unlink tool's destructive annotation to true and document its exact
association-only effect. Verify admin/editor unlink, viewer/non-member denial,
repeated unlink, and preservation of library paper, notes and annotations.
Mark project updates destructive as well, including description overwrite/clear.

Promote the temporary role exercise into maintained tests using actual model
tables and real quota checks. Synthetic token verification is appropriate for
the local transport matrix, but explicitly label that boundary. Cover missing,
unverified, wrong-audience, blocked, inactive and disallowed identities as well
as roles, ownership, registry and all five project tools.

Use a portable guarded PostgreSQL launcher with dummy environment settings and
dotenv disabled. Create/drop only test-owned schemas. Do not stop or delete the
pre-existing disposable cluster. Replace hardcoded source/migration paths in
tests so they test the isolated checkout, not the dirty original checkout.
Make CI invoke the maintained integration harness and required new migration,
service, API and test paths. Required integration tests must fail on skips.
Billing-related GitHub failures do not substitute for local results.

## 4. Verify and review a concrete successor commit

Run focused MCP, concurrency, migration upgrade/downgrade and affected browser/
invitation regression checks on disposable databases, then the full server
suite. Inspect every skip; record expected optional skips separately from the
required PostgreSQL checks, which must have none. Verify dependency lockfile and
runtime compatibility. Keep fixture helpers and local evidence out of production
build inputs where appropriate.

Record exact commands, results and limitations. Request another independent MEOS
review with this intent and executed evidence supplied. Resolve material findings
and repeat the checks affected by fixes. Commit the reviewed implementation and
evidence on the feature branch. Record the new SHA; the original expected SHA is
the baseline and will no longer be the final deployment SHA.

## 5. Preflight, build, migrate, deploy

Use only the existing `personal` gcloud configuration, personal account
`jansammat26@gmail.com`, target project `openpaper-sammatuba`, region
`asia-southeast1`, and repository deployment scripts. Reconfirm these values
immediately before release. The configuration's project was previously
`health-facility-finder`; the scripts explicitly set the OpenPaper target.

Record both services' traffic allocations, ready/latest revisions and container
digests, not just latest-ready revision names. Previously observed candidates:
web `openpaper-00009-fb9`, jobs `openpaper-jobs-00006-r7q`; refresh before use.
Confirm current schema/migration state without printing connection strings or
secrets. Check that the existing client/Caddy images retained by the backend-only
build match the intended running installation.

Verify an existing authorized MCP connection/token is available for post-release
checks without creating credentials, echoing tokens, or reading secret values
into the conversation. If absent, finish all independent checks and identify the
specific connection step needed; do not impersonate a user or bypass OAuth.

Run `bash deploy/deploy.sh build backend` from a clean, identified release tree.
Verify build success and image digests. Apply the new additive migration with
`bash deploy/deploy.sh migrate` before enabling the new ledger-dependent code;
do not run bootstrap, secrets initialization, scheduling, or provisioning.
Then run `bash deploy/deploy.sh deploy`. Record both resulting revisions and
verify their image digests correspond to the release build.

Preserve Neon, the research library, signing/encryption secrets and the Worker.
Do not change Worker routing unless a demonstrated existing routing failure
requires it. Never access or print credentials for the work packet.

## 6. Live acceptance and rollback

Check application health through the public origin and existing origin as
appropriate, OAuth authorization-server/protected-resource discovery, anonymous
MCP rejection, authenticated registry containing the five tools, and an existing
authorized user's read operations. Actual Google OAuth verification remains a
live check; local synthetic tokens do not establish it.

If deployment or live acceptance fails, diagnose before declaring success.
When rollback is necessary, restore recorded traffic/revisions for each affected
service. Leave the additive request ledger intact; do not downgrade production
schema or erase records to roll back application code. Verify rollback health
and report the failed release honestly.

## 7. Create the requested research project

Only after live authorization succeeds, list existing accessible projects and
check for the exact title and plausible prior matching project. Inspect any
candidate before reusing it. If absent, generate and persist one request UUID
with the exact intended creation payload before the first MCP create call; reuse
both for every retry. Verify the returned project via authenticated listing and
replay the same request to establish live idempotency.

Locate the previous SwarmLab experimental scaffold and RRL in available local or
connected sources; a local search in docs/scripts found no explicit SwarmLab
match. Do not invent prior results or use the reviewer-collusion work as a
substitute. If those sources cannot be located, request their location while
completing independent release work. Distinguish cited prior results from new
2026 sprint hypotheses and experiments in the initial context. Keep the earlier
reviewer-collusion project separate. Do not import research papers until project
creation and authorization are verified.

## Completion evidence

Report exact deployed SHA, web/jobs revisions, image/build identity, migration
result, executed tests and skips, independent verdict, live health/discovery/
registry/authenticated checks, project ID and retry outcome, unresolved failures,
and rollback revisions. Update this packet with actual outcomes. Deployment
success and project creation must each have live evidence. Do not merge PR #1
as part of this work.
