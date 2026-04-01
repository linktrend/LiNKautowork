#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <dev|prod>"
  exit 1
fi

ENVIRONMENT="$1"
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
  echo "Environment must be dev or prod"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/deploy/${ENVIRONMENT}/.env"
declare -A KV
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# || "$line" != *=* ]] && continue
  key="${line%%=*}"
  value="${line#*=}"
  key="${key//[$'\t\r\n ']/}"
  KV["$key"]="$value"
done < "$ENV_FILE"

N8N_BASE_URL="${KV[N8N_BASE_URL]:-}"
: "${N8N_BASE_URL:?N8N_BASE_URL is required}"
PROJECT_ID="${GCP_PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:-${KV[GCP_PROJECT_ID]:-${KV[GOOGLE_CLOUD_PROJECT]:-}}}}"
if [[ -z "$PROJECT_ID" ]]; then
  echo "Missing GCP project (GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT)"
  exit 1
fi
N8N_API_KEY_SECRET_NAME="${KV[N8N_API_KEY_SECRET_NAME]:-}"
: "${N8N_API_KEY_SECRET_NAME:?N8N_API_KEY_SECRET_NAME is required}"
N8N_API_KEY="$(gcloud secrets versions access latest --project "$PROJECT_ID" --secret "$N8N_API_KEY_SECRET_NAME")"

TARGET_DIR="$ROOT_DIR/automations/live/$ENVIRONMENT"
mkdir -p "$TARGET_DIR"

WORKFLOWS_JSON="$(curl -sS -H "x-n8n-api-key: $N8N_API_KEY" "$N8N_BASE_URL/api/v1/workflows?limit=250")"

echo "$WORKFLOWS_JSON" | jq -c '.data[]' | while read -r workflow; do
  id="$(echo "$workflow" | jq -r '.id')"
  name="$(echo "$workflow" | jq -r '.name' | tr ' /' '__')"
  curl -sS -H "x-n8n-api-key: $N8N_API_KEY" "$N8N_BASE_URL/api/v1/workflows/$id" | jq '.' > "$TARGET_DIR/${name}-${id}.json"
done

echo "Exported active workflow snapshots to $TARGET_DIR"
