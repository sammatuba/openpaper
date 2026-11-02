# Personal Cloud Run deploy

One user, scale to zero, cold starts accepted. Target cost: a few dollars a
month, most of it Gemini usage. Decisions and acceptance checks:
[`docs/work/INTENT-personal-cloud-run-deploy.md`](../docs/work/INTENT-personal-cloud-run-deploy.md).

```
                 ┌────────────── Cloud Run service "openpaper" (one origin) ─────────────┐
 browser ──────► │ caddy :8080 ─► /api/*, /docs, /admin ─► server (FastAPI, gunicorn x1)   │
                 │               └► everything else      ─► client (Next.js)              │
                 └───────────────────────────────────────────────┬──────────────────────┘
                                                                 │ Cloud Tasks (OIDC)
                 Neon Postgres (Singapore)  ◄── server            ▼
                 GCS bucket (PDFs, backups)   ◄── server, jobs    Cloud Run "openpaper-jobs"
                 Cloud Scheduler: nightly backup job, daily Zotero sync       (PDF parsing, 30 min max)
```

What changed in the fork to make this work, all switched by environment and
off by default so upstream merges stay clean:

| Switch | Effect |
|---|---|
| `TASK_BACKEND=cloudtasks` | server enqueues on Cloud Tasks instead of the Celery broker; jobs runs tasks in-process at `POST /tasks/run`. RabbitMQ and Redis disappear. |
| `ALLOWED_EMAILS=a@x,b@y` | sign-in limited to those addresses (Google and email code). |
| `SELF_HOSTED_PLAN=researcher` | every user gets that plan's limits without Stripe (Basic would cap you at 10 papers and 2 projects). |
| missing `STRIPE_API_KEY` / `FIRECRAWL_API_KEY` | server starts; billing endpoints and the web-scrape tool fail only when called. |
| missing `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | provider skipped instead of failing startup; set `LLM_FALLBACK_PROVIDER=` empty. |
| missing `E2B_API_KEY` | server starts; chart unit conversion and computed columns report the missing sandbox. |
| `WEB_CONCURRENCY=1` | gunicorn worker count (Cloud Run reports the host's CPUs). |
| `--build-arg NEXT_PUBLIC_API_URL=...` | client image for a different origin, no PostHog/Stripe keys. |
| `AWS_ENDPOINT_URL_S3` | boto3 talks to GCS through its S3 interop API with an HMAC key (no code change; botocore honours it). |

## Secrets

No secret is ever written to a local file. `deploy/config.env` (committed)
holds only non-secret settings. Secret values are typed once at a prompt, or
piped on stdin, and go straight into Secret Manager:

```bash
deploy/deploy.sh secrets-init                 # prompts for every secret not yet set
deploy/deploy.sh secret-set GEMINI_API_KEY    # rotate one
powershell.exe -c Get-Clipboard | tr -d '\r\n' | deploy/deploy.sh secret-set DATABASE_URL   # or pipe it (WSL clipboard)
deploy/deploy.sh secrets-status
```

Cloud Run resolves them at deploy time (`secretKeyRef`, always `latest`), the
migrate and backup jobs the same way, and the Zotero scheduler job reads
`JOBS_INTERNAL_SECRET` from Secret Manager when it is (re)created. The runtime
service account has `secretmanager.secretAccessor`; your user account only
needs it to add versions. Rotating a secret is `secret-set` then `deploy`.

| Secret | Source |
|---|---|
| `DATABASE_URL` | Neon pooled connection string |
| `DATABASE_URL_DIRECT` | Neon direct string (backups); blank copies `DATABASE_URL` |
| `GEMINI_API_KEY` | Google AI Studio |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | OAuth web client in the personal project |
| `GCS_HMAC_ACCESS_ID`, `GCS_HMAC_SECRET` | created by `bootstrap` for the runtime SA, never shown |
| `JOBS_INTERNAL_SECRET`, `ADMIN_SECRET_KEY` | generated at the prompt when left blank |

## One-time operator steps

The public URL is deterministic (`https://openpaper-<project-number>.<region>.run.app`),
so the Google OAuth client can be created before anything is deployed.

1. **gcloud, personal account.** Keep the work configuration untouched:
   ```bash
   gcloud config configurations create personal
   gcloud auth login          # jansammat26@gmail.com
   ```
2. **Check `deploy/config.env`** (project id, region, allowed emails), then:
   ```bash
   deploy/deploy.sh bootstrap   # project, billing (prompts), APIs, registry, SA, queue
   deploy/deploy.sh oauth-uri   # the redirect URI for step 3
   ```
3. **Google OAuth** in the new project: APIs & Services → OAuth consent screen
   (External, Testing, add your Gmail as a test user) → Credentials → OAuth
   client (Web application) with the redirect URI from step 2.
4. **Storage** needs nothing from you: bootstrap created the private GCS
   bucket, its CORS rule for the service origin, and the HMAC key.
5. **Neon.** New project, region `aws-ap-southeast-1` (Singapore). Keep the
   pooled and direct connection strings at hand for the prompt.
6. **Gemini API key** from AI Studio.
7. **Enter secrets, then ship:**
   ```bash
   deploy/deploy.sh secrets-init
   deploy/deploy.sh build && deploy/deploy.sh migrate && deploy/deploy.sh deploy && deploy/deploy.sh schedule
   ```
8. Open the URL, sign in with the allow-listed Gmail, upload a PDF.

## Day to day

```bash
deploy/deploy.sh build && deploy/deploy.sh migrate && deploy/deploy.sh deploy   # ship a change
deploy/deploy.sh logs            # web service logs
deploy/deploy.sh logs openpaper-jobs
deploy/deploy.sh backup-now      # ad-hoc dump to the bucket (backups/ prefix)
```

Rollback: Cloud Run keeps revisions; `gcloud run services update-traffic openpaper --to-revisions=<rev>=100 --region asia-southeast1`.

## Behaviour to expect

- **Cold start** 10 to 20 s on the first request after idle; the three
  containers start together. Neon resumes in about a second; `pool_pre_ping`
  handles the stale connection.
- **Upload progress** shows "pending" until the PDF finishes, because Cloud
  Tasks has no readable task state. Completion and failure arrive by webhook.
- **Request size** on Cloud Run is 32 MiB per request; PDFs above that will
  not upload. Rare for papers.
- **Retries.** A task that fails inside the runner returns 200 (it already
  reported the failure), so it is not re-run. Only a crashed instance is
  retried, once.
- **Backups** land in `backups/` in the bucket nightly at 02:30 Manila
  time, kept 14 days. Restore with `pg_restore --no-owner -d "$DATABASE_URL_DIRECT" file.dump`.

## Costs (expected)

| Item | Monthly |
|---|---|
| Cloud Run (web + jobs, a few hours of use) | within free tier, else under $3 |
| Cloud Build (a few builds a week) | free tier (120 min/day) |
| Cloud Tasks, Scheduler, Secret Manager | cents |
| Neon free tier (0.5 GB) | $0 |
| GCS (a few GB in asia-southeast1, plus egress when reading) | about $0.10 plus cents |
| Gemini Flash | usage; a few dollars at heavy reading |

## Troubleshooting

- `services replace` complains about a missing secret: `deploy.sh secrets-init`
  creates every referenced secret (placeholder `unset` when left blank); rerun it.
- `builds submit` permission errors: new projects build as the compute default
  service account; bootstrap grants it `roles/cloudbuild.builds.builder`.
  Re-run bootstrap if the project predates that.
- PDF viewer says `NetworkError`: the bucket CORS origin must match the
  service URL exactly; rerun `bootstrap` (it rewrites the rule).
- PDF viewer 403 on the file: the app presigns by object key with the HMAC
  key, so the bucket stays private. Check `secrets-status` shows both
  `GCS_HMAC_*` set and that the runtime SA has `storage.objectAdmin`.
- Cancelling an upload returns `CANCEL_ERROR`: the runtime SA needs
  `roles/cloudtasks.taskDeleter` (bootstrap grants it).

## Local development is unchanged

With `TASK_BACKEND` unset everything runs as in `DEVELOPMENT.md`
(Celery, RabbitMQ, Redis, `scripts/dev`).
