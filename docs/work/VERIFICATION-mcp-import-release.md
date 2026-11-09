# MCP importer and hostname release verification

Updated 2026-11-07. **Deployed; public checks pass; Google OAuth registration and authenticated ChatGPT acceptance remain pending.**
Intent: [INTENT-mcp-import-release.md](INTENT-mcp-import-release.md).
Independent disposition: [REVIEW-mcp-import-release.md](REVIEW-mcp-import-release.md).
Account handoff: [CHATGPT-mcp-import-release.md](CHATGPT-mcp-import-release.md).

## Released result

PR #2: https://github.com/sammatuba/openpaper/pull/2, source branch `feat/mcp-url-import`, based on PR #1's `feat/mcp-project-management`. Runtime source **36066d53c089e54b6f21cae496bb1c08436c54e0** was pushed to PR #2. Neither PR was merged. Original dirty master and unrelated research/viewer changes are preserved. Implementation checkout: `/tmp/openpaper-mcp-deploy`, branch `fix/mcp-import-release`.

Two tools are verified over locally authenticated MCP HTTP transport: `import_paper_from_url(project_id, request_id, url)` and `get_paper_import_status(request_id)`. Public production probes do not establish authenticated registry contents or successful Google OAuth.

Canonical origin: **https://papers.sammatuba.workers.dev**. The Worker already routes correctly; its source/deployment was not changed. Application origins, browser OAuth callback, MCP discovery and compiled frontend API URL now use this hostname. PDF bucket CORS adds the new origin while preserving prior origin/method/header/max-age settings.

## Corrected defects

- arXiv .pdf URLs redirect301; canonical PDF URLs now omit that extension, preserving the no-redirect policy.
- The import-ledger migration omitted inherited timestamp columns. Actual PostgreSQL schema comparison caught this; both columns were added before first deployment.
- The downloader pins vetted public DNS addresses through TLS hostname verification, rejects redirects and oversized data, and kills/reaps a child after60 seconds to bound DNS/download/PDF validation.
- Ambiguous queue dispatch preserves committed paper/link/storage for reconciliation. Replays do not dispatch again. The browser submission helper's existing default compensation behavior is preserved.
- arXiv reuse matches exact normalized DOI/version identity rather than arbitrary suffixes.
- MCP upload admission locks the user through durable reservation/job commits, with no lock spanning remote I/O. One SQL snapshot counts completed papers, pending jobs, ambiguous claims and orphaned reservations. Confirmed failed/cancelled work releases capacity; uncertain dispatch retains it. Existing browser admission behavior itself is unchanged.
- Source-manifest project/paper associations are explicitly unverified in this session; authenticated readback must establish them before ingestion.

## Executed verification

- Focused importer/network suite: **13 pass**.
- Required isolated PostgreSQL: **44 tests pass, zero skips**,5.915s. Covers migration/mapping/constraints; real submission helper with only storage/queue boundaries substituted; request/source replay; concurrent distinct imports across projects at the last user slot; reserved/pending/ambiguous/completed capacity; real terminal-failure update and subsequent admission; owner/editor revocation; exact DOI/version matching; MCP HTTP registry/import/status; existing project, note and processing transaction checks.
- Full server suite: **410 tests, OK,34 skips**,5.725s.28 guarded PostgreSQL cases are covered separately in the required runner. Six baseline browser OAuth-state cases need their separate fixture and were not run. Python3.12.13, existing locked server environment, dummy settings, .env disabled; no production API/DB calls from tests. Sandbox async executor stalls were avoided by running acceptance outside it.
- Real public arXiv PDF download and validation:634503 bytes, SHA256 `0d57f8961ff51520c905d0dcd7b822222c3c36852a544d1cba2ead045dbc0384`; no library write or processing job.
- Independent review initially requested rework for quota reservation, then terminal-failure capacity. Both material findings and documentation findings were corrected. Final report `20261107T154320Z.md`: **accept**. Reviewer checked syntax/diff; prior focused review reran13 tests. Final PostgreSQL/full-suite execution relies on retained author logs because reviewer sandbox lacked the environment/socket access.
- Diff checks pass. Source manifests remain valid JSON. GitHub Actions are not acceptance evidence: repository issues are disabled, and original PR checks did not start because the account is locked for billing.

## Build, migration and deployment

All builds succeeded in personal configuration, project `openpaper-sammatuba`, region `asia-southeast1`:

| Component | Build/source | Deployed digest |
| --- | --- | --- |
| frontend | `447ff95f-7723-4f3a-b96e-c8c4192fdbca`, `1732aac2`, new public URL | `sha256:b6ebeac0d412cc3795a221ba5d361cba67601b5d1b764ccc7ea66dd4792c2760` |
| server | `557def5c-0cb5-4bbc-9838-b64565d70c36`, `36066d53` | `sha256:d0e3c8cce6aa65b6afc88de0aa47dc386c2526359cddf487ec86041598378fa4` |
| jobs | `9d3ed58a-2a82-46cf-9733-3eefc8745b7d`, `d30ab0e1` | `sha256:883e91ffe8889cc758fdb7ae0812fcdc075ef2a66cea674a330942fdeca268fb` |
| proxy | full build above, `1732aac2` | `sha256:17e8060c41ad2700e3ba80a2b1ac757fb609ac798e8c92e2a9c0850fc9602052` |

Frontend/proxy and jobs source were compared against final36066d53 and are identical in their respective directories. The earlier intermediate server images were superseded before deployment. Release tags were checked against exact final digests after all builds completed. Build archives exclude agent/runtime artifacts and local env files.

Migration execution **openpaper-migrate-894c8** succeeded using the exact final server digest and `alembic upgrade head`, whose sole target is `mcp_research_import_01`. No bootstrap, credential creation/rotation or data-maintenance job.

Postflight2026-11-07T15:52:33Z confirms latest-created equals latest-ready and100% traffic on web **openpaper-00011-wx8** and jobs **openpaper-jobs-00008-plm**. Every container digest matches the release manifest; secret references are unchanged.

Live checks pass: homepage200, health200 on Worker and direct Cloud Run, both OAuth discovery documents200 with new-origin resource/issuer/endpoints andS256, anonymous MCP401/no-store/new metadata challenge, anonymous jobs403.31 served frontend entry bundles checked: new-origin references present and no retired-origin string. GCS CORS preflight200 with `Access-Control-Allow-Origin: https://papers.sammatuba.workers.dev`. This is a preflight check, not an authenticated browser PDF rendering claim.

Rollback revisions: web **openpaper-00010-zkp**, jobs **openpaper-jobs-00007-v9m**. Restore traffic if needed; keep the additive ledger schema. The old web revision still advertises the retired hostname, so rollback would also require origin handling. No rollback needed.

Filtered metadata, review reports and logs are retained locally in `.meos/artifacts/mcp-import-release-20261107/` in both checkouts. No access tokens or raw OAuth login responses are included.

## Remaining acceptance

Google public authorization still returns **redirect_uri_mismatch** for both new callbacks. Register these in the existing Google OAuth client:

- https://papers.sammatuba.workers.dev/api/auth/google/callback
- https://papers.sammatuba.workers.dev/api/mcp/auth/callback

Then reconnect/update the existing ChatGPT OpenPaper integration to **https://papers.sammatuba.workers.dev/api/mcp**, refresh its tools/actions, and verify authenticated discovery plus one separately authorized paper pilot. Follow [the handoff](CHATGPT-mcp-import-release.md); submitted alone is not completion.

This Codex session exposes no OpenPaper connector; plugin discovery returned none. No user tokens were extracted or minted as a workaround. No production paper import, project creation/deletion, note mutation, paid inference, or PR merge was performed. Google/ChatGPT account actions and actual authenticated pilot remain unfinished.
