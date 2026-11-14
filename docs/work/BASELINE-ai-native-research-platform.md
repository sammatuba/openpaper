# BASELINE: AI-native research platform — P00 re-established 2026-11-13

Strategy: [STRATEGY-ai-native-research-platform.md](STRATEGY-ai-native-research-platform.md). Intent: [INTENT-ai-native-research-platform.md](INTENT-ai-native-research-platform.md). This record discharges P00's inventory and verification obligations. All prior work-pointer values remain authoritative and unchanged.

## 1. Deployed/source divergence

| Item | Recorded | Verified today |
| --- | --- | --- |
| Working tree | branch `feat/native-investigation-workspace` @ `ef2a6731f9e429d45b30055940c0238e965df3a9` | matches; only work-pointer update + this platform's docs/work files are new (uncommitted at P00 start) |
| Deployed source | `c757bbf0` (release `investigation-c757bbf00d6d`, images pinned by digest, `openpaper-00014-vjm` 100%) | historical release record; not re-inspected remotely in P00 (no production change is authorized) |
| Divergence | HEAD = deployed source + one docs-only commit (`ef2a6731`) | `git log` confirms `ef2a6731` touches docs/work records only |
| master | `09bf3bae` — two commits behind the feature branch | feature branch is **not merged**; release was archive-based (matches §0.1) |
| Alembic head | `project_investigation_01` (down `project_research_brief_01`) | single head; nothing references it as a down_revision |

## 2. Extension-seam inventory (file:line evidence)

### Storage
- `ProjectInvestigation` (`server/app/database/models.py:1818`): one JSONB row per project, `revision BigInteger`, check `schema_version = 1 AND revision > 0`. `ProjectDraftRequest` (`:1828`): durable drafting identity with state machine `pending/running/completed/failed/uncertain`.
- Strict v1 document schema: `server/app/schemas/investigation.py` — claims/findings with discriminated `anchored|unbound|redacted` sources, `supports|challenges|qualifies` relations, manuscript blocks with provenance (`human|assembled|assistant|imported`), dependency pins, quote snapshots; 2 MB canonical byte cap; graph validation (no dangling refs, unique IDs, source_quote needs exactly one finding).
- Service invariants to preserve (`server/app/services/investigation.py`): `access()` (owner-without-membership passes; write requires owner or admin/editor role), conditional save (If-Match → 428/400/412), server-side source integrity (raw-content hash + exact-line quotation match → 409/422), redaction on access loss, provenance preservation rules (assistant provenance cannot be erased/replaced; imported stays imported until reviewed), canonical re-validation before commit, single commit.

### Compute/E2B boundary (P00 classification)
- `Sandbox.create(api_key=..., timeout=300)` only — **no network-restriction/firewall parameter** (`server/app/helpers/compute_agent.py:299`; same shape in `unit_conversion.py:171`). "No network" exists only as prose in the model prompt (`compute_agent.py:79`). **Classification: network isolation is NOT enforced; any strategy text claiming sandbox network isolation must not rely on it.**
- `MAX_ATTEMPTS = 3` generation/repair loop (`compute_agent.py:41,307`); each attempt is a paid provider call; failure raises after 3 attempts.
- Table webhook commit boundary: `POST /api/webhooks/data-table-processing/{job_id}` — sync handler, `with_for_update` job lock, idempotent for COMPLETED jobs, single commit of result+rows+status (`server/app/api/webhook_api.py:741-923`); auth via `X-Jobs-Secret` HMAC compare.
- Chart jobs run as FastAPI BackgroundTasks on the server (no webhook): `server/app/api/projects/project_charts_api.py:121-126`, status transitions in `server/app/tasks/chart_generation.py`.

### Task transport
- Backends: `celery` (default) and `cloudtasks` via `TASK_BACKEND` env (`server/app/helpers/task_backend.py:34-39`). Cloud Tasks requires project/location/queue/target config + OIDC SA + `X-Jobs-Secret` defense-in-depth.
- Jobs allowlist: `RUNNABLE_TASKS = {"upload_and_process_file", "process_data_table", "periodic_zotero_sync", "delayed_referral_settlement_callback"}` (`jobs/src/app.py:63-70`); `/tasks/run` 404s anything else; cloudtasks mode replays saved outcomes for idempotent tasks and 503s on failure for Cloud Tasks retry.

### Roles semantics (P00 parity finding)
Three different owner/membership checks exist today:
- Investigation REST `access()`: owner-without-membership **passes** (read and write) — `server/app/services/investigation.py:24-35`.
- MCP project management `_role()`: membership row **required**; owner-without-membership **denied** — `server/app/mcp/project_tools.py:33-43`.
- MCP research reads `project_access()`: owner **or** membership — `server/app/mcp/research.py:12-14`; MCP uploads require membership admin/editor — `server/app/mcp/uploads.py:22-30`.
This is the §14.2 "owner-versus-membership" integration issue. P02's shared authorization service must define one semantic (owner passes; membership governs editors/viewers) and MCP surfaces adopt it without widening rights.

### OAuth/sessions
- Google OAuth2 upstream identity; opaque DB-backed `session_token` cookie (Secure/HttpOnly/SameSite, `server/app/auth/utils.py:37-67`); server-side `GoogleOAuthState` CSRF/replay rows with replay-safe reattach (`server/app/api/auth_api.py:266-283`); email sign-in with verification codes; `ALLOWED_EMAILS` allowlist re-checked per MCP tool call (`server/app/mcp/server.py:79-91`).
- Separate fastmcp `GoogleProvider` for the MCP endpoint (`/api/mcp` callback, JWT signing key, Fernet-encrypted store) — a second Google integration whose audience is distinct from browser sessions (the §12.3 upstream-identity vs resource-audience distinction).

### MCP surface
- 21 registered tools, single Streamable-HTTP transport (`mcp.http_app(path="/api/mcp", stateless_http=True)`), most tools annotated read-only (`server/app/mcp/server.py`).

### Frontend contract
- `client/src/lib/investigation.ts`: Zod mirror of the server schema incl. byte cap; `downloadInvestigation` deliberately downgrades anchored sources to unbound for offline recovery.
- `client/src/components/project/InvestigationProvider.tsx`: in-memory state only — **no localStorage/sessionStorage**; explicit save with If-Match; 412 → `Conflict` status; beforeunload/in-app navigation guards offering download; revision parsed from ETag.

## 3. Executed verification (P00, this session)

| Command (root) | Result |
| --- | --- |
| `server/.venv/bin/python scripts/ci/run_isolated_postgres.py --run-existing` (cluster `/tmp/openpaper-pg-transaction-test`, socket-only `listen_addresses=''`, owned `sammatuba 700`, data_directory verified via SQL before reuse) | **Ran 100 tests, 0 skips, OK, 9.194s** — includes investigation conditional-save/ETag, forgery rejection (quote/quote_sha256/source_sha256/paper_id), concurrency single-winner, failed-commit atomicity, migration upgrade/downgrade/upgrade, quote snapshot preservation, two-source fixture journey + exports |

A fresh-cluster invocation was first attempted and correctly **refused** an existing directory/socket (guard works). The cluster was verified (owner, mode 700, `SHOW data_directory`, `SHOW listen_addresses` empty) before `--run-existing` per the documented procedure.

Full server suite (`server`: 55 files), jobs suite, client tsc/build, and worker tests are not re-run in P00 beyond the required lane; they remain available and are listed in §4. C35's full-regression obligation attaches to P12/package exits, not P00 alone.

## 4. Existing test commands (inventory)

| Area | Command | Notes |
| --- | --- | --- |
| Server required PG lane | `server/.venv/bin/python scripts/ci/run_isolated_postgres.py` | 15 suites incl. all investigation/postgres suites; fails on any skip |
| Server full | `cd server && uv run python -m unittest discover -s tests` | 55 test files; guarded integration tests skip without the isolated cluster |
| Jobs | `cd jobs && TASK_BACKEND=cloudtasks uv run python -m unittest discover -s tests` | 5 test files |
| Client | `cd client && yarn tsc --noEmit && yarn build` (+ browser suites per package.json) | no separate `typecheck` script |
| Worker | `node --test deploy/cloudflare/worker.test.mjs` | Cloudflare front door |
| Research tools | `python3 -m unittest discover -s scripts/research -p 'test_*.py'` | local-only tooling |
| CI runner tests | `python3 -m unittest discover -s scripts/ci -p 'test_*.py'` | isolated-cluster runner self-tests |

## 5. Outstanding operator gates (carried forward, unchanged)

1. **A25 authenticated production acceptance** — operator sign-in at canonical origin exercising Case → Evidence → Draft save/reload, citation/PDF and export. Not exercised in P00; no production change made.
2. **Live-AI acceptance** — separately authorized; `live_inference: false` remains true for the deployed release.
3. Pilot PDF/Notes operator browser check, idle-login observation, one-week billing observation, citations/project-chat validation before corpus expansion.
4. New-platform packages (P01–P02 in this PR; P03+ later) must not obscure or claim these gates.

## 6. No-provider boundary

The required PG lane runs with placeholder API keys and `LANGFUSE_TRACING_ENABLED=false` (`scripts/ci/run_isolated_postgres.py:87-102`); every suite passed with **zero** provider/network calls. Investigation save/read/export paths make no model calls (verified by the passing suites + service code inspection). P02 preserves this: metered dispatch stays unavailable until the admission core exists and passes its tests.
