#!/usr/bin/env bash
# Personal Cloud Run deploy for Open Paper. Idempotent: every step can be rerun.
#
#   deploy/deploy.sh bootstrap   project, billing, APIs, registry, service account, queue
#   deploy/deploy.sh secrets     push secrets from deploy/personal.env to Secret Manager
#   deploy/deploy.sh build       build all images with Cloud Build
#   deploy/deploy.sh migrate     run alembic migrations as a Cloud Run job
#   deploy/deploy.sh deploy      deploy the web and jobs services
#   deploy/deploy.sh schedule    nightly backup + daily Zotero sync (Cloud Scheduler)
#   deploy/deploy.sh all         bootstrap → secrets → build → migrate → deploy → schedule
#   deploy/deploy.sh url         print the public URL (deterministic, known before deploy)
#   deploy/deploy.sh oauth-uri   print the Google OAuth redirect URI (needs only bootstrap)
#   deploy/deploy.sh backup-now  run the backup job once
#   deploy/deploy.sh logs [svc]  tail recent logs
#
# Uses its own gcloud configuration (GCLOUD_CONFIGURATION) so the work
# configuration is never touched.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"
env_file="$here/personal.env"
[[ -f "$env_file" ]] || { echo "missing $env_file (copy personal.env.example)"; exit 1; }
set -a; # shellcheck disable=SC1090
source "$env_file"; set +a

export CLOUDSDK_ACTIVE_CONFIG_NAME="${GCLOUD_CONFIGURATION:-personal}"
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

: "${PROJECT_ID:?}" "${REGION:?}" "${R2_ACCOUNT_ID:?}" "${R2_BUCKET:?}" "${ALLOWED_EMAILS:?}"
TAG="${TAG:-latest}"
REPO=openpaper
QUEUE=openpaper-jobs
SA_NAME=openpaper-runtime
RUNTIME_SA="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"
R2_ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
R2_PUBLIC_HOST="${R2_PUBLIC_HOST:-${R2_ACCOUNT_ID}.r2.cloudflarestorage.com/${R2_BUCKET}}"
export PROJECT_ID REGION TAG QUEUE RUNTIME_SA IMAGE_BASE R2_ENDPOINT R2_BUCKET R2_PUBLIC_HOST ALLOWED_EMAILS

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
  gcloud config set project "$PROJECT_ID" >/dev/null
  if [[ -n "${BILLING_ACCOUNT:-}" ]]; then
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
  log "public URL will be: $(public_url)"
}

SECRET_NAMES=(DATABASE_URL DATABASE_URL_DIRECT GEMINI_API_KEY GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET
              R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY JOBS_INTERNAL_SECRET ADMIN_SECRET_KEY)

cmd_secrets() {
  require_login
  gcloud config set project "$PROJECT_ID" >/dev/null
  local name value
  for name in "${SECRET_NAMES[@]}"; do
    value="${!name:-}"
    # Every secret the services reference must exist or `services replace`
    # fails; an empty value gets a placeholder you replace later.
    if [[ -z "$value" ]]; then
      if [[ "$name" == DATABASE_URL_DIRECT ]]; then value="${DATABASE_URL:-unset}"; else value=unset; fi
      echo "warning: $name is empty in personal.env; storing placeholder"
    fi
    if ! gcloud secrets describe "$name" >/dev/null 2>&1; then
      gcloud secrets create "$name" --replication-policy=automatic >/dev/null
    fi
    # Only add a version when the value changed.
    if [[ "$(gcloud secrets versions access latest --secret="$name" 2>/dev/null || true)" != "$value" ]]; then
      printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- >/dev/null
      echo "updated $name"
    else
      echo "unchanged $name"
    fi
  done
}

cmd_build() {
  require_login
  gcloud config set project "$PROJECT_ID" >/dev/null
  log "cloud build → $IMAGE_BASE/*:$TAG"
  gcloud builds submit "$root" --config="$here/cloudbuild.yaml" \
    --substitutions="_REGION=${REGION},_REPO=${REPO},_TAG=${TAG},_PUBLIC_URL=$(public_url)"
}

cmd_migrate() {
  require_login
  gcloud config set project "$PROJECT_ID" >/dev/null
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
  (( ${#missing[@]} == 0 )) || { echo "missing secrets: ${missing[*]} — run deploy/deploy.sh secrets"; exit 1; }
}

render() { envsubst '${PROJECT_ID} ${REGION} ${TAG} ${QUEUE} ${RUNTIME_SA} ${IMAGE_BASE} ${R2_ENDPOINT} ${R2_BUCKET} ${R2_PUBLIC_HOST} ${ALLOWED_EMAILS} ${PUBLIC_URL} ${JOBS_URL}' < "$1"; }

cmd_deploy() {
  require_login
  gcloud config set project "$PROJECT_ID" >/dev/null
  PUBLIC_URL="$(public_url)"; JOBS_URL="$(jobs_url)"; export PUBLIC_URL JOBS_URL
  require_secrets "${SECRET_NAMES[@]}"
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
  gcloud config set project "$PROJECT_ID" >/dev/null
  require_secrets DATABASE_URL DATABASE_URL_DIRECT R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY JOBS_INTERNAL_SECRET
  local verb
  log "backup job"
  verb=create; gcloud run jobs describe openpaper-backup --region="$REGION" >/dev/null 2>&1 && verb=update
  gcloud run jobs "$verb" openpaper-backup --region="$REGION" \
    --image="${IMAGE_BASE}/backup:${TAG}" --service-account="$RUNTIME_SA" \
    --set-secrets=DATABASE_URL=DATABASE_URL:latest,DATABASE_URL_DIRECT=DATABASE_URL_DIRECT:latest,AWS_ACCESS_KEY_ID=R2_ACCESS_KEY_ID:latest,AWS_SECRET_ACCESS_KEY=R2_SECRET_ACCESS_KEY:latest \
    --set-env-vars="AWS_ENDPOINT_URL_S3=${R2_ENDPOINT},AWS_ENDPOINT_URL=${R2_ENDPOINT},AWS_DEFAULT_REGION=auto,AWS_REQUEST_CHECKSUM_CALCULATION=when_required,AWS_RESPONSE_CHECKSUM_VALIDATION=when_required,S3_BUCKET_NAME=${R2_BUCKET},BACKUP_KEEP_DAYS=14" \
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
  secrets)   cmd_secrets ;;
  build)     cmd_build ;;
  migrate)   cmd_migrate ;;
  deploy)    cmd_deploy ;;
  schedule)  cmd_schedule ;;
  all)       cmd_bootstrap; cmd_secrets; cmd_build; cmd_migrate; cmd_deploy; cmd_schedule ;;
  oauth-uri) require_login; gcloud config set project "$PROJECT_ID" >/dev/null; echo "$(public_url)/api/auth/google/callback" ;;
  url)       require_login; gcloud config set project "$PROJECT_ID" >/dev/null; public_url ;;
  backup-now) require_login; gcloud run jobs execute openpaper-backup --region="$REGION" --wait ;;
  logs)      cmd_logs "${2:-openpaper}" ;;
  *) sed -n '2,16p' "$0"; exit 1 ;;
esac
