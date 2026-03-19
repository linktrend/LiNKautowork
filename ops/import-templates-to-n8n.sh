#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="${1:-dev}"
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
  echo "Environment must be dev or prod"
  exit 1
fi

RUNTIME_ENV_FILE="/Users/linktrend/Projects/LiNKautowork/deploy/${ENVIRONMENT}/.env.runtime"
if [[ -f "$RUNTIME_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$RUNTIME_ENV_FILE"
  set +a
fi

: "${N8N_BASE_URL:?N8N_BASE_URL is required}"
: "${N8N_API_KEY:?N8N_API_KEY is required}"

TEMPLATE_DIR="/Users/linktrend/Projects/LiNKautowork/automations/templates"

find "$TEMPLATE_DIR" -maxdepth 1 -name '*.json' ! -name 'manifest.json' -print0 | while IFS= read -r -d '' template; do
  echo "Importing $(basename "$template")"
  curl -sS -X POST "$N8N_BASE_URL/api/v1/workflows" \
    -H "x-n8n-api-key: $N8N_API_KEY" \
    -H 'content-type: application/json' \
    --data-binary "@$template" >/dev/null
  echo "Imported $(basename "$template")"
done
