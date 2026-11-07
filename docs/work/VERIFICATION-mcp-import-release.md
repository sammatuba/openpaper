# MCP importer and hostname release verification

2026-11-07. In progress. Intent: [INTENT-mcp-import-release.md](INTENT-mcp-import-release.md).

PR #2 starts at 8e51c247eef9e738320454fb616dc737aa66bdef, based on PR #1 at 22575d1d. Existing live runtime is 2aaa93d5, web openpaper-00010-zkp/jobs openpaper-jobs-00007-v9m. Original dirty master is preserved; work is in /tmp/openpaper-mcp-deploy on fix/mcp-import-release. Neither PR is merged. Repository issues are disabled.

GitHub check annotation explicitly says the account is locked due to a billing issue; no jobs started. Local evidence supplies test acceptance, not a claimed GitHub CI success.

Confirmed defects and fixes:
- arXiv .pdf paths return301; canonicalize to extensionless PDF URLs so no-redirect imports work.
- Migration omitted inherited created_at/updated_at columns, exposed by actual PostgreSQL migration/mapping comparison. Both added before first deployment.
- Preserve committed paper/link/storage after ambiguous task dispatch for MCP imports; no destructive compensation or repeated dispatch on replay. Default browser pipeline behavior is retained.
- Pin vetted public DNS address through TLS with hostname verification and reject redirects. Kill/reap a child after60 seconds to bound DNS/stream/parsing, and reject oversized content.
- Exact normalized arXiv DOI/version matching replaces suffix-only matching; quota and role are rechecked after download.
- User confirmed new canonical origin https://papers.sammatuba.workers.dev. Worker reaches origin, health GET200, but live OAuth discovery still advertises the retired domain. Deploy settings and guide corrected; frontend rebuild and PDF-bucket CORS update required. Google callback registration and actual ChatGPT reconnect/refresh are account-side checks.

Executed acceptance:
- Focused importer tests13 pass (0.138s).
- Required real isolated PostgreSQL suite41 pass, zero skips (5.245s). Includes real PDF submission pipeline with only storage/queue boundaries mocked, ambiguous RPC resources preserved, concurrent source replay, owner/editor revocation, exact DOI/version matching, migration upgrade/downgrade/constraints and authenticated MCP HTTP registry/import/status. Google token verification synthetic; no real OAuth credentials.
- Full server suite407 pass (5.763s),31 skips:25 guarded PG tests run in required suite;6 pre-existing browser OAuth-state tests require separate fixture and are not part of release evidence.
- Actual public arXiv download and PDF validation passed:634503 bytes, SHA2560d57f8961ff51520c905d0dcd7b822222c3c36852a544d1cba2ead045dbc0384. No library write or processing job.
- git diff --check passes. Logs /tmp/openpaper-import-{focused,required,full}.log. Existing server .venv uses Python3.12.13, lockfile unchanged. Tests use dummy environment with .env disabled and no production service calls. Sandbox initial async run timed out; executed acceptance outside sandbox.

Independent review, clean source commit/build, production migration/deployment, updated CORS, and final public probes pending. No production import, new credentials, key rotation or automatic PR merge.

## Independent review corrections

Initial independent review .meos/reviews/20261107T152938Z.md requested rework for outstanding upload quota capacity. Fixed by serializing MCP admission on the authenticated user row through the reservation commit and job-claim commit, with no lock held over remote I/O. A single SQL snapshot counts completed/direct papers, outstanding upload jobs (including browser jobs), ambiguous jobs, and orphaned durable reservations, avoiding double count and completion races. The active request excludes its existing reservation when transitioning to a job. Same-request/source replay still runs before capacity rejection. Browser admission behavior itself is not changed by this importer release.

Required PostgreSQL43 tests now pass with zero skips (5.054s), including concurrent distinct-source requests across two projects competing for the user's last slot and existing reserved/pending/ambiguous/completed occupancy. Focused13 pass (0.146s). Full regression after this fix409 tests passes (5.742s),33 skips:27 guarded PostgreSQL cases covered by required runner,6 baseline browser OAuth-state checks not run.

Minor findings corrected: manifest project/paper association claims explicitly labeled unverified in this session; bounded bucket-only CORS recipe documented. CORS update succeeded, adding the new origin while preserving the prior origin, methods, headers and max age. Google public authorization checks return redirect_uri_mismatch for both new callbacks; user registration confirmation is pending. Full hostname build447ff95f-7723-4f3a-b96e-c8c4192fdbca uses clean1732aac2 source and is in progress; its backend must be superseded by a build of the quota correction before deployment. No deployment of unaccepted code.

Follow-up independent review .meos/reviews/20261107T153744Z.md requested rework for confirmed terminal failures retaining quota. Fixed: successfully dispatched submitted requests are not ambiguous; failed/cancelled jobs with a terminal completion timestamp release capacity even if the ledger remains submitting/needs_reconciliation. Uncertain dispatch without terminal confirmation still reserves its slot. Added PostgreSQL regression calling the real mark_as_failed helper across submitted/submitting/needs_reconciliation and verifying new admission plus old failed-request replay without redispatch. Final required PostgreSQL44 tests pass with zero skips (5.915s); full server410 tests pass (5.725s) with34 skips (28 guarded PG covered separately,6 baseline browser OAuth-state checks unexecuted). Final review and final server-only rebuild pending; intermediate quota server must not be deployed.
