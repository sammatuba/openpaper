# INTENT: personal self-hosted Open Paper on Cloud Run

**Owner:** operator (single user). **Opened:** 2026-11-02. **Branch:** `meos/install` → feature branches per phase.
**Purpose:** read, track and annotate papers for `../ai-safety` at near-zero recurring cost, with cold starts accepted.

## Decisions (aligned 2026-11-02)

| Topic | Decision | Rejected |
|---|---|---|
| Hosting | Cloud Run, scale to zero, personal GCP account `jansammat26@gmail.com` (billing exists) | single VM + compose |
| Async jobs | switchable task backend: `TASK_BACKEND=celery` (upstream) or `cloudtasks` (Cloud Tasks → jobs HTTP runner, Cloud Scheduler for Zotero sync) | always-on Celery worker |
| Database | Neon free tier Postgres, Singapore region, pooled connection string; nightly `pg_dump` to R2 | SQLite (schema is Postgres-native: tsvector, pg_trgm, JSONB, ARRAY, UUID), Cloud SQL |
| Object storage | Cloudflare R2 via `AWS_ENDPOINT_URL_S3`, private bucket, presigned URLs, CORS for the client origin | GCS |
| Hostname | free `*.run.app`, no domain | Cloudflare Tunnel / own domain |
| LLM | Gemini only; OpenAI, Anthropic, E2B optional (`LLM_FALLBACK_PROVIDER=` empty) | buying four keys |
| "Connect ChatGPT" | expose the workbench as a remote MCP connector for ChatGPT (last phase) | OpenAI API key |
| Region | GCP `asia-southeast1` paired with Neon `aws-ap-southeast-1` | |

## Constraints

- Fork tracks upstream `khoj-ai/openpaper` (19 of last 20 commits are upstream). Every patch is env-switched and defaults to upstream behaviour.
- One origin for client and API. `run.app` is on the Public Suffix List, so `client-*.run.app` and `server-*.run.app` are cross-site and the httponly `session_token` cookie would not be sent. Design: one Cloud Run service `openpaper` with a Caddy ingress container routing `/api/*` to the server sidecar and everything else to the Next.js sidecar. `CLIENT_DOMAIN == API_DOMAIN == NEXT_PUBLIC_API_URL`.
- Public URL, so sign-in must be gated: `ALLOWED_EMAILS` checked in the Google callback and the email-code path. Unset keeps upstream behaviour.
- gunicorn `cpu_count()*2+1` workers would OOM on 1 vCPU Cloud Run; honour `WEB_CONCURRENCY`.
- Celery tasks are `bind=True` and use `self.request.id` / `self.update_state`; the cloudtasks runner executes them with `task.apply(kwargs, task_id=...)` (eager, in-process) with a memory result backend, so task bodies stay untouched.
- Status polling (`check_celery_task_status`) returns `PENDING` in cloudtasks mode; completion and failure arrive by webhook as today (`send_failure_webhook`). Cloud Tasks retries on non-2xx.
- Cloud Tasks dispatch deadline 30 min; jobs service request timeout 30 min, concurrency 1, 2 GiB.
- Work gcloud configuration (`jmatuba@mabuhayenergy.com`, `core-staging-platform`) is never touched; a separate `personal` configuration is used.
- No cloud resource is created before the operator has logged in to the personal account.
- **No local env files.** Secrets exist only in Secret Manager (operator ruling 2026-11-03): entered at a prompt or piped on stdin by `deploy.sh secret-set` / `secrets-init`, resolved by Cloud Run and the jobs at deploy time, read by the scheduler setup from Secret Manager. `deploy/config.env` is committed and holds only non-secret settings.

## Phases and acceptance checks

### P0 MEOS (done)
- [x] `meos.sh install . --runtime claude`, registered in `../estate.json`, committed `8aee8bb8`.

### P1 Code: run anywhere cheaply (branch `feat/cloud-run-personal`) (done)
1. `server/app/llm/base.py`, `unit_conversion.py`, `compute_agent.py`: providers and E2B initialise only when their key is set; missing E2B degrades chart conversion with a logged warning instead of failing import.
2. `server/app/auth`: `ALLOWED_EMAILS` gate (comma-separated, case-insensitive). Rejected sign-in returns 403 with a plain message.
3. `server/gunicorn.config.py`: `WEB_CONCURRENCY` override.
4. Task backend: `server/app/helpers/pdf_jobs.py` + `referral_jobs.py` dispatch through a `TaskBackend` with `celery` and `cloudtasks` implementations; `jobs/src/app.py` gains `POST /tasks/run` (OIDC-protected via Cloud Tasks service account, or shared `JOBS_INTERNAL_SECRET`) that runs the named task eagerly. Referral task is a no-op in cloudtasks mode.
5. `client/Dockerfile`: `ARG NEXT_PUBLIC_API_URL`; drop the hard-coded Stripe and PostHog values; sourcemap upload stage only when secrets are provided.
6. `deploy/` directory: `Caddyfile`, `cloudbuild.yaml` (three images → Artifact Registry), `service.yaml` (multi-container service), `jobs-service.yaml`, `migrate-job.yaml`, `backup-job.yaml` (pg_dump → R2), `deploy.sh` (idempotent: enable APIs, queue, scheduler, secrets, deploy), `README.md`.
7. Found while doing 1: `STRIPE_API_KEY` (subscription config) and `FIRECRAWL_API_KEY` (scrape tool) also raised at import; both made lazy. The jobs service reads `GOOGLE_API_KEY`, not `GEMINI_API_KEY`; the deploy maps the same secret onto both. Without Stripe every user is on the Basic plan (10 papers, 2 projects), which would block the corpus import, so `SELF_HOSTED_PLAN=researcher` forces a plan without billing.
- Checks (run 2026-11-02): server `unittest discover` 336 tests OK under the CI env and under a Gemini-only env; `from app.main import app` succeeds with only `GEMINI_API_KEY` set (providers: gemini, fallback: none); jobs suite 4 tests OK (runner executes a task under the server's id, failures return 200, unknown task 404, shared secret enforced); `TASK_BACKEND` unset leaves `JobsClient.cloud_tasks` None and the Celery path untouched.
- Status: **done**, committed on `feat/cloud-run-personal`. Not yet exercised: a Cloud Build of the client image and a real Cloud Tasks round trip (P3).

### P2 Operator actions (console/manual, in this order)
1. `! gcloud config configurations create personal` then `! gcloud auth login` as `jansammat26@gmail.com`.
2. Neon: project in `aws-ap-southeast-1`, copy the pooled connection string.
3. Cloudflare: account, R2 bucket `openpaper-papers`, S3 API token (Object Read & Write), note account id.
4. Gemini API key (AI Studio).
5. After the first deploy prints the service URL: OAuth consent screen (External, Testing, own Gmail as test user) and an OAuth web client with redirect `https://<service-url>/api/auth/google/callback`.

### P3 Provision and deploy
- `deploy/deploy.sh` creates project `openpaper-personal-<suffix>`, links billing, enables Run/Build/Tasks/Scheduler/Secret Manager/Artifact Registry, stores secrets, builds images with Cloud Build, runs the migrate job, deploys `openpaper` and `openpaper-jobs`, creates the Tasks queue and two Scheduler jobs (Zotero sync daily, backup nightly).
- Checks: sign in with the allow-listed Gmail; upload a PDF and see it finish processing; chat answers with citations; PDF renders (R2 CORS); second login after 30 min idle works (Neon resume + `pool_pre_ping`); backup object appears in R2.
- Cost check after one week: GCP billing report under $3; Neon and R2 at $0.

### P4 Corpus
- Import the ai-safety literature: extract arXiv ids from `../ai-safety/literature/papers/*.md`, upload into project "Epistemic authority and collusion" (two local PDFs plus arXiv fetches). Verify the Open Paper upload-by-URL path first; otherwise fetch PDFs locally and upload.

### P5 ChatGPT connector
- Remote MCP server (streamable HTTP) on the server exposing `search_papers`, `get_paper`, `list_annotations`, `add_note`, guarded by a bearer token; add it in ChatGPT Developer Mode as a custom connector. Spec written when P3 is verified.

## Open items
- ~~Whether anything fetches the stored `file_url` directly.~~ Closed 2026-11-03: every paper/file URL the API returns comes from `get_cached_presigned_url*` (paper_api.py), so the R2 bucket stays private; `R2_PUBLIC_HOST` only shapes the stored key prefix.
- Whether the jobs → server webhook should also carry `JOBS_INTERNAL_SECRET` (currently matched by unguessable job + task ids).
- Not yet exercised against the real APIs: the Cloud Run service YAML (multi-container, sidecar probes), the Cloud Build run, a Cloud Tasks round trip, R2 presigned GET with the `when_required` checksum setting. All land in P3.
