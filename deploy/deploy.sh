#!/usr/bin/env bash
# Personal Cloud Run deploy for Open Paper. Idempotent: every step can be rerun.
#
#   deploy/deploy.sh bootstrap   project, billing, APIs, registry, service account, queue
#   deploy/deploy.sh secrets-init    prompt for every secret not yet in Secret Manager
#   deploy/deploy.sh secret-set NAME prompt for one secret (or pipe it on stdin) and add a version
#   deploy/deploy.sh secrets-status  which secrets exist and when they were last changed
#   deploy/deploy.sh build       build all images with Cloud Build
#   deploy/deploy.sh migrate     run alembic migrations as a Cloud Run job
#   deploy/deploy.sh deploy      deploy the web and jobs services
#   deploy/deploy.sh schedule    nightly backup + daily Zotero sync (Cloud Scheduler)
#   deploy/deploy.sh all         bootstrap → secrets-init → build → migrate → deploy → schedule
#   deploy/deploy.sh url         print the public URL (deterministic, known before deploy)
#   deploy/deploy.sh oauth-uri   print the Google OAuth redirect URI (needs only bootstrap)
#   deploy/deploy.sh backup-now  run the backup job once
#   deploy/deploy.sh logs [svc]  tail recent logs
#
# Secrets are never written to disk here: they go from the prompt (or stdin)
# straight into Secret Manager, and Cloud Run / Cloud Run jobs / Scheduler
# read them from there. deploy/config.env holds only non-secret settings.
# Uses its own gcloud configuration (GCLOUD_CONFIGURATION) so the work
# configuration is never touched.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"
config_file="$here/config.env"
[[ -f "$config_file" ]] || { echo "missing $config_file"; exit 1; }
set -a; # shellcheck disable=SC1090
source "$config_file"; set +a

export CLOUDSDK_ACTIVE_CONFIG_NAME="${GCLOUD_CONFIGURATION:-personal}"
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

: "${PROJECT_ID:?}" "${REGION:?}" "${GCS_BUCKET:?}" "${ALLOWED_EMAILS:?}"
TAG="${TAG:-latest}"
REPO=openpaper
QUEUE=openpaper-jobs
SA_NAME=openpaper-runtime
RUNTIME_SA="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"
S3_ENDPOINT="https://storage.googleapis.com"
# Host written into stored object URLs; the app presigns by key, so this only shapes the prefix.
STORAGE_PUBLIC_HOST="storage.googleapis.com/${GCS_BUCKET}"
export PROJECT_ID REGION TAG QUEUE RUNTIME_SA IMAGE_BASE S3_ENDPOINT GCS_BUCKET STORAGE_PUBLIC_HOST ALLOWED_EMAILS

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

require_login() {
  local account
  account="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null || true)"
  [[ -n "$account" ]] || { echo "No active account in gcloud configuration '$CLOUDSDK_ACTIVE_CONFIG_NAME'. Run: gcloud config configurations create $CLOUDSDK_ACTIVE_CONFIG_NAME && gcloud auth login"; exit 1; }
  echo "gcloud account: $account (configuration $CLOUDSDK_ACTIVE_CONFIG_NAME)"
}

project_number() { gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)'; }
public_url() { echo "https://openpaper-$(project_number).${REGION}.run.app"; }
jobs_url() { echo "https://openpaper-jobs-$(project_number).${REGION}.run.app"; }

cmd_bootstrap() {
  require_login
  log "project $PROJECT_ID"
  if ! gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud projects create "$PROJECT_ID" --name="Open Paper personal"
  fi
  gcloud config set project "$PROJECT_ID" >/dev/null 2>&1
  if [[ -z "$(gcloud billing projects describe "$PROJECT_ID" --format='value(billingAccountName)' 2>/dev/null)" ]]; then
    if [[ -z "${BILLING_ACCOUNT:-}" ]]; then
      gcloud billing accounts list
      read -rp "Billing account id to link (XXXXXX-XXXXXX-XXXXXX): " BILLING_ACCOUNT
    fi
    gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT" >/dev/null
  fi
  log "APIs"
  gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
    cloudtasks.googleapis.com cloudscheduler.googleapis.com secretmanager.googleapis.com iam.googleapis.com
  log "artifact registry $REPO"
  gcloud artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 || \
    gcloud artifacts repositories create "$REPO" --location="$REGION" --repository-format=docker
  log "service account $RUNTIME_SA"
  gcloud iam service-accounts describe "$RUNTIME_SA" >/dev/null 2>&1 || \
    gcloud iam service-accounts create "$SA_NAME" --display-name="Open Paper runtime"
  for role in roles/secretmanager.secretAccessor roles/cloudtasks.enqueuer roles/cloudtasks.taskDeleter roles/run.invoker roles/logging.logWriter; do
    gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${RUNTIME_SA}" --role="$role" --condition=None >/dev/null
  done
  # The server enqueues tasks that carry an OIDC token for this same account.
  gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
    --member="serviceAccount:${RUNTIME_SA}" --role=roles/iam.serviceAccountUser >/dev/null
  # Cloud Build pushes images and needs the registry.
  local build_sa="$(project_number)-compute@developer.gserviceaccount.com"
  for role in roles/cloudbuild.builds.builder roles/artifactregistry.writer roles/logging.logWriter roles/storage.objectViewer; do
    gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${build_sa}" --role="$role" --condition=None >/dev/null
  done
  log "cloud tasks queue $QUEUE"
  gcloud tasks queues describe "$QUEUE" --location="$REGION" >/dev/null 2>&1 || \
    gcloud tasks queues create "$QUEUE" --location="$REGION"
  # One retry covers an instance crash; a PDF that fails deterministically
  # reports its own failure and must not be re-run (LLM spend).
  gcloud tasks queues update "$QUEUE" --location="$REGION" \
    --max-attempts=2 --max-concurrent-dispatches=2 --max-dispatches-per-second=5 >/dev/null
  log "bucket gs://$GCS_BUCKET"
  if ! gcloud storage buckets describe "gs://$GCS_BUCKET" >/dev/null 2>&1; then
    gcloud storage buckets create "gs://$GCS_BUCKET" --location="$REGION" \
      --uniform-bucket-level-access --public-access-prevention >/dev/null
  fi
  gcloud storage buckets add-iam-policy-binding "gs://$GCS_BUCKET" \
    --member="serviceAccount:${RUNTIME_SA}" --role=roles/storage.objectAdmin >/dev/null
  # The browser fetches PDFs with presigned URLs (range requests), so the
  # bucket must allow the app's exact origin.
  local cors; cors="$(mktemp)"
  cat > "$cors" <<JSON
[{"origin": ["$(public_url)"], "method": ["GET", "HEAD", "PUT"],
  "responseHeader": ["Content-Type", "Content-Length", "Content-Range", "Accept-Ranges", "ETag", "Range"],
  "maxAgeSeconds": 3000}]
JSON
  gcloud storage buckets update "gs://$GCS_BUCKET" --cors-file="$cors" >/dev/null; rm -f "$cors"
  # boto3 reaches GCS through the S3 interop API with an HMAC key for the
  # runtime SA. The secret is shown once by the API; it goes straight into
  # Secret Manager and is never printed.
  if ! secret_exists GCS_HMAC_SECRET || [[ "$(gcloud secrets versions access latest --secret=GCS_HMAC_SECRET)" == unset ]]; then
    log "HMAC key for $RUNTIME_SA"
    local key; key="$(gcloud storage hmac create "$RUNTIME_SA" --format=json)"
    push_secret GCS_HMAC_ACCESS_ID "$(printf '%s' "$key" | python3 -c 'import json,sys; print(json.load(sys.stdin)["metadata"]["accessId"])')"
    push_secret GCS_HMAC_SECRET "$(printf '%s' "$key" | python3 -c 'import json,sys; print(json.load(sys.stdin)["secret"])')"
    unset key
  else
    echo "have   GCS_HMAC_* "
  fi
  log "public URL will be: $(public_url)"
}

# Prompted by secrets-init. GCS_HMAC_* are created by bootstrap, not prompted.
SECRET_NAMES=(DATABASE_URL DATABASE_URL_DIRECT GEMINI_API_KEY GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET
              JOBS_INTERNAL_SECRET ADMIN_SECRET_KEY)
ALL_SECRETS=("${SECRET_NAMES[@]}" GCS_HMAC_ACCESS_ID GCS_HMAC_SECRET)
# Generated locally when left blank at the prompt; never need to be known.
GENERATED_SECRETS=(JOBS_INTERNAL_SECRET ADMIN_SECRET_KEY)

secret_hint() {
  case "$1" in
    DATABASE_URL) echo "Neon pooled connection string (host contains -pooler), with ?sslmode=require" ;;
    DATABASE_URL_DIRECT) echo "Neon direct connection string (no -pooler); blank = same as DATABASE_URL" ;;
    GEMINI_API_KEY) echo "Google AI Studio API key" ;;
    GOOGLE_CLIENT_ID|GOOGLE_CLIENT_SECRET) echo "OAuth web client in the personal project; blank = placeholder until created" ;;
    JOBS_INTERNAL_SECRET|ADMIN_SECRET_KEY) echo "blank = generate 32 random bytes" ;;
  esac
}

secret_exists() { gcloud secrets describe "$1" >/dev/null 2>&1; }

# Add a version to NAME from stdin (no echo, no file). Creates the secret if needed.
push_secret() {
  local name="$1" value="$2"
  secret_exists "$name" || gcloud secrets create "$name" --replication-policy=automatic >/dev/null
  printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- >/dev/null
  echo "stored $name"
}

read_secret_value() {
  local name="$1" value=""
  if [[ -t 0 ]]; then
    printf '%s  (%s)\n' "$name" "$(secret_hint "$name")" >&2
    read -rsp "  value: " value; echo >&2
  else
    IFS= read -r value || true
  fi
  if [[ -z "$value" ]]; then
    for g in "${GENERATED_SECRETS[@]}"; do
      [[ "$name" == "$g" ]] && value="$(openssl rand -hex 32)" && echo "  generated" >&2
    done
  fi
  if [[ -z "$value" && "$name" == DATABASE_URL_DIRECT ]] && secret_exists DATABASE_URL; then
    value="$(gcloud secrets versions access latest --secret=DATABASE_URL)"
  fi
  [[ -n "$value" ]] || value=unset   # every referenced secret must exist for `services replace`
  printf '%s' "$value"
}

cmd_secrets_init() {
  require_login
  gcloud config set project "$PROJECT_ID" >/dev/null 2>&1
  local name
  for name in "${SECRET_NAMES[@]}"; do
    if secret_exists "$name" && [[ "$(gcloud secrets versions access latest --secret="$name")" != unset ]]; then
      echo "have   $name"; continue
    fi
    push_secret "$name" "$(read_secret_value "$name")"
  done
}

cmd_secret_set() {
  require_login
  gcloud config set project "$PROJECT_ID" >/dev/null 2>&1
  (( $# >= 1 )) || { echo "usage: deploy.sh secret-set NAME [NAME...]   (value prompted, or piped on stdin for one NAME)"; exit 1; }
  local name
  for name in "$@"; do push_secret "$name" "$(read_secret_value "$name")"; done
}

cmd_secrets_status() {
  require_login
  gcloud config set project "$PROJECT_ID" >/dev/null 2>&1
  local name state
  for name in "${ALL_SECRETS[@]}"; do
    if ! secret_exists "$name"; then state="MISSING"
    elif [[ "$(gcloud secrets versions access latest --secret="$name")" == unset ]]; then state="placeholder"
    else state="set $(gcloud secrets versions describe latest --secret="$name" --format='value(createTime)' 2>/dev/null)"
    fi
    printf '%-22s %s\n' "$name" "$state"
  done
}

cmd_build() {
  require_login
  gcloud config set project "$PROJECT_ID" >/dev/null 2>&1
  log "cloud build → $IMAGE_BASE/*:$TAG"
  gcloud builds submit "$root" --config="$here/cloudbuild.yaml" \
    --substitutions="_REGION=${REGION},_REPO=${REPO},_TAG=${TAG},_PUBLIC_URL=$(public_url)"
}

cmd_migrate() {
  require_login
  gcloud config set project "$PROJECT_ID" >/dev/null 2>&1
  log "migrations"
  local verb=create
  gcloud run jobs describe openpaper-migrate --region="$REGION" >/dev/null 2>&1 && verb=update
  gcloud run jobs "$verb" openpaper-migrate --region="$REGION" \
    --image="${IMAGE_BASE}/server:${TAG}" --service-account="$RUNTIME_SA" \
    --command=alembic --args=upgrade,head \
    --set-secrets=DATABASE_URL=DATABASE_URL:latest \
    --memory=1Gi --max-retries=0 --task-timeout=15m >/dev/null
  gcloud run jobs execute openpaper-migrate --region="$REGION" --wait
}

require_secrets() {
  local missing=() name
  for name in "$@"; do
    gcloud secrets describe "$name" >/dev/null 2>&1 || missing+=("$name")
  done
  (( ${#missing[@]} == 0 )) || { echo "missing secrets: ${missing[*]} — run deploy/deploy.sh secrets-init"; exit 1; }
}

render() { envsubst '${PROJECT_ID} ${REGION} ${TAG} ${QUEUE} ${RUNTIME_SA} ${IMAGE_BASE} ${S3_ENDPOINT} ${GCS_BUCKET} ${STORAGE_PUBLIC_HOST} ${ALLOWED_EMAILS} ${PUBLIC_URL} ${JOBS_URL}' < "$1"; }

cmd_deploy() {
  require_login
  gcloud config set project "$PROJECT_ID" >/dev/null 2>&1
  PUBLIC_URL="$(public_url)"; JOBS_URL="$(jobs_url)"; export PUBLIC_URL JOBS_URL
  require_secrets "${ALL_SECRETS[@]}"
  local tmp; tmp="$(mktemp -d)"
  log "jobs service"
  render "$here/service.jobs.yaml" > "$tmp/jobs.yaml"
  gcloud run services replace "$tmp/jobs.yaml" --region="$REGION" >/dev/null
  # Invoked only by Cloud Tasks (OIDC as the runtime SA); no public access.
  gcloud run services add-iam-policy-binding openpaper-jobs --region="$REGION" \
    --member="serviceAccount:${RUNTIME_SA}" --role=roles/run.invoker >/dev/null
  log "web service"
  render "$here/service.openpaper.yaml" > "$tmp/web.yaml"
  gcloud run services replace "$tmp/web.yaml" --region="$REGION" >/dev/null
  gcloud run services add-iam-policy-binding openpaper --region="$REGION" \
    --member=allUsers --role=roles/run.invoker >/dev/null
  rm -rf "$tmp"
  log "deployed: $PUBLIC_URL"
  echo "Google OAuth redirect URI: ${PUBLIC_URL}/api/auth/google/callback"
}

cmd_schedule() {
  require_login
  gcloud config set project "$PROJECT_ID" >/dev/null 2>&1
  require_secrets DATABASE_URL DATABASE_URL_DIRECT GCS_HMAC_ACCESS_ID GCS_HMAC_SECRET JOBS_INTERNAL_SECRET
  local verb
  log "backup job"
  verb=create; gcloud run jobs describe openpaper-backup --region="$REGION" >/dev/null 2>&1 && verb=update
  gcloud run jobs "$verb" openpaper-backup --region="$REGION" \
    --image="${IMAGE_BASE}/backup:${TAG}" --service-account="$RUNTIME_SA" \
    --set-secrets=DATABASE_URL=DATABASE_URL:latest,DATABASE_URL_DIRECT=DATABASE_URL_DIRECT:latest,AWS_ACCESS_KEY_ID=GCS_HMAC_ACCESS_ID:latest,AWS_SECRET_ACCESS_KEY=GCS_HMAC_SECRET:latest \
    --set-env-vars="AWS_ENDPOINT_URL_S3=${S3_ENDPOINT},AWS_ENDPOINT_URL=${S3_ENDPOINT},AWS_DEFAULT_REGION=auto,AWS_REQUEST_CHECKSUM_CALCULATION=when_required,AWS_RESPONSE_CHECKSUM_VALIDATION=when_required,S3_BUCKET_NAME=${GCS_BUCKET},BACKUP_KEEP_DAYS=14" \
    --memory=512Mi --max-retries=1 --task-timeout=20m >/dev/null
  local backup_uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/openpaper-backup:run"
  verb=create; gcloud scheduler jobs describe openpaper-backup-nightly --location="$REGION" >/dev/null 2>&1 && verb=update
  gcloud scheduler jobs "$verb" http openpaper-backup-nightly --location="$REGION" \
    --schedule="30 18 * * *" --time-zone="Asia/Manila" --http-method=POST --uri="$backup_uri" \
    --oauth-service-account-email="$RUNTIME_SA" >/dev/null
  log "zotero sync (daily)"
  local secret; secret="$(gcloud secrets versions access latest --secret=JOBS_INTERNAL_SECRET)"
  verb=create; gcloud scheduler jobs describe openpaper-zotero-sync --location="$REGION" >/dev/null 2>&1 && verb=update
  gcloud scheduler jobs "$verb" http openpaper-zotero-sync --location="$REGION" \
    --schedule="0 19 * * *" --time-zone="Asia/Manila" --http-method=POST \
    --uri="$(public_url)/api/webhooks/internal/zotero-sync-all?threshold_seconds=86400" \
    --headers="Authorization=Bearer ${secret}" --attempt-deadline=180s >/dev/null
  echo "scheduled: backup 02:30, Zotero sync 03:00 (Asia/Manila)"
}

cmd_logs() {
  local svc="${1:-openpaper}"
  gcloud run services logs read "$svc" --region="$REGION" --limit=100
}

case "${1:-}" in
  bootstrap) cmd_bootstrap ;;
  secrets-init)   cmd_secrets_init ;;
  secret-set)     shift; cmd_secret_set "$@" ;;
  secrets-status) cmd_secrets_status ;;
  build)     cmd_build ;;
  migrate)   cmd_migrate ;;
  deploy)    cmd_deploy ;;
  schedule)  cmd_schedule ;;
  all)       cmd_bootstrap; cmd_secrets_init; cmd_build; cmd_migrate; cmd_deploy; cmd_schedule ;;
  oauth-uri) require_login; gcloud config set project "$PROJECT_ID" >/dev/null 2>&1; echo "$(public_url)/api/auth/google/callback" ;;
  url)       require_login; gcloud config set project "$PROJECT_ID" >/dev/null 2>&1; public_url ;;
  backup-now) require_login; gcloud run jobs execute openpaper-backup --region="$REGION" --wait ;;
  logs)      cmd_logs "${2:-openpaper}" ;;
  *) sed -n '2,20p' "$0"; exit 1 ;;
esac
