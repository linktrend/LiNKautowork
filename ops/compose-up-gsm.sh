#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <dev|prod> [--build]"
  exit 1
fi

ENVIRONMENT="$1"
BUILD_FLAG="${2:-}"
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
  echo "Environment must be dev or prod"
  exit 1
fi
if [[ -n "$BUILD_FLAG" && "$BUILD_FLAG" != "--build" ]]; then
  echo "Only optional flag supported is --build"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/deploy/${ENVIRONMENT}/.env"
COMPOSE_FILE="$ROOT_DIR/deploy/${ENVIRONMENT}/docker-compose.yml"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE"
  exit 1
fi
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing compose file: $COMPOSE_FILE"
  exit 1
fi
if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI is required"
  exit 1
fi

declare -A KV
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# || "$line" != *=* ]] && continue
  key="${line%%=*}"
  value="${line#*=}"
  key="${key//[$'\t\r\n ']/}"
  KV["$key"]="$value"
done < "$ENV_FILE"

PROJECT_ID="${GCP_PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:-${KV[GCP_PROJECT_ID]:-${KV[GOOGLE_CLOUD_PROJECT]:-}}}}"
if [[ -z "$PROJECT_ID" ]]; then
  echo "Missing GCP_PROJECT_ID/GOOGLE_CLOUD_PROJECT in $ENV_FILE"
  exit 1
fi

resolve_secret() {
  local secret_name="$1"
  if [[ -z "$secret_name" ]]; then
    echo ""
    return 0
  fi
  gcloud secrets versions access latest --project "$PROJECT_ID" --secret "$secret_name"
}

# n8n requires concrete values for these vars at process start.
export N8N_ENCRYPTION_KEY
N8N_ENCRYPTION_KEY="$(resolve_secret "${KV[N8N_ENCRYPTION_KEY_SECRET_NAME]:-}")"
export SUPABASE_DB_PASSWORD
SUPABASE_DB_PASSWORD="$(resolve_secret "${KV[SUPABASE_DB_PASSWORD_SECRET_NAME]:-}")"

if [[ -z "$N8N_ENCRYPTION_KEY" || -z "$SUPABASE_DB_PASSWORD" ]]; then
  echo "Required n8n startup secrets are missing (N8N_ENCRYPTION_KEY or SUPABASE_DB_PASSWORD)."
  exit 1
fi

export N8N_HOST="${KV[N8N_HOST]:-}"
export N8N_PORT="${KV[N8N_PORT]:-}"
export N8N_PROTOCOL="${KV[N8N_PROTOCOL]:-}"
export N8N_EDITOR_BASE_URL="${KV[N8N_EDITOR_BASE_URL]:-}"
export WEBHOOK_URL="${KV[WEBHOOK_URL]:-}"
export SUPABASE_DB_HOST="${KV[SUPABASE_DB_HOST]:-}"
export SUPABASE_DB_PORT="${KV[SUPABASE_DB_PORT]:-}"
export SUPABASE_DB_DATABASE="${KV[SUPABASE_DB_DATABASE]:-}"
export SUPABASE_DB_USER="${KV[SUPABASE_DB_USER]:-}"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d ${BUILD_FLAG}
