#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="${1:-dev}"
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
N8N_API_KEY="$(gcloud secrets versions access latest --project "$PROJECT_ID" --secret "${N8N_API_KEY}_SECRET_NAME")"

TEMPLATE_DIR="$ROOT_DIR/automations/templates"

find "$TEMPLATE_DIR" -maxdepth 1 -name '*.json' ! -name 'manifest.json' -print0 | while IFS= read -r -d '' template; do
  echo "Importing $(basename "$template")"
  curl -sS -X POST "$N8N_BASE_URL/api/v1/workflows" \
    -H "x-n8n-api-key: ${N8N_API_KEY}" \
    -H 'content-type: application/json' \
    --data-binary "@$template" >/dev/null
  echo "Imported $(basename "$template")"
done
