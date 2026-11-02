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
                 Cloudflare R2 (PDFs, backups) ◄── server, jobs   Cloud Run "openpaper-jobs"
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
| `AWS_ENDPOINT_URL_S3` | boto3 talks to R2 (no code change; botocore honours it). |

## One-time operator steps

1. **gcloud, personal account.** Keep the work configuration untouched:
   ```bash
   gcloud config configurations create personal
   gcloud auth login          # jansammat26@gmail.com
   gcloud billing accounts list
   ```
2. **Neon.** New project, region `aws-ap-southeast-1` (Singapore), Postgres 17+.
   Copy both connection strings: the pooled one (`-pooler` host) for the app,
   the direct one for backups.
3. **Cloudflare R2.** Create bucket `openpaper-papers`. Create an R2 API token
   with Object Read & Write on that bucket; note the Account ID. Set the bucket
   CORS policy (Settings → CORS) to the client origin printed by
   `deploy.sh url` (exact origin, no trailing slash):
   ```json
   [{"AllowedOrigins": ["https://openpaper-NNNN.asia-southeast1.run.app"],
     "AllowedMethods": ["GET", "HEAD", "PUT"],
     "AllowedHeaders": ["*"],
     "ExposeHeaders": ["Content-Length", "Content-Range", "Accept-Ranges", "ETag"],
     "MaxAgeSeconds": 3000}]
   ```
4. **Gemini API key** from AI Studio.
5. **Fill `deploy/personal.env`** from `personal.env.example`. Generate
   `JOBS_INTERNAL_SECRET` and `ADMIN_SECRET_KEY` with `openssl rand -hex 32`.
6. **First deploy** (Google OAuth values can be empty for now):
   ```bash
   deploy/deploy.sh all
   ```
7. **Google OAuth.** In the personal project: APIs & Services → OAuth consent
   screen (External, Testing, add your Gmail as a test user), then Credentials
   → OAuth client (Web application) with redirect URI
   `https://<service-url>/api/auth/google/callback` (printed by `deploy.sh deploy`).
   Put the client id and secret in `personal.env`, then:
   ```bash
   deploy/deploy.sh secrets && deploy/deploy.sh deploy
   ```

## Day to day

```bash
deploy/deploy.sh build && deploy/deploy.sh migrate && deploy/deploy.sh deploy   # ship a change
deploy/deploy.sh logs            # web service logs
deploy/deploy.sh logs openpaper-jobs
deploy/deploy.sh backup-now      # ad-hoc dump to R2 (backups/ prefix)
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
- **Backups** land in `backups/` in the R2 bucket nightly at 02:30 Manila
  time, kept 14 days. Restore with `pg_restore --no-owner -d "$DATABASE_URL_DIRECT" file.dump`.

## Costs (expected)

| Item | Monthly |
|---|---|
| Cloud Run (web + jobs, a few hours of use) | within free tier, else under $3 |
| Cloud Build (a few builds a week) | free tier (120 min/day) |
| Cloud Tasks, Scheduler, Secret Manager | cents |
| Neon free tier (0.5 GB) | $0 |
| R2 (10 GB free, no egress) | $0 |
| Gemini Flash | usage; a few dollars at heavy reading |

## Local development is unchanged

With `TASK_BACKEND` unset everything runs as in `DEVELOPMENT.md`
(Celery, RabbitMQ, Redis, `scripts/dev`).
