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
