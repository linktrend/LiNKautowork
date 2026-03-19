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

RUNTIME_ENV_FILE="/Users/linktrend/Projects/LiNKautowork/deploy/${ENVIRONMENT}/.env.runtime"
if [[ -f "$RUNTIME_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$RUNTIME_ENV_FILE"
  set +a
fi

: "${N8N_BASE_URL:?N8N_BASE_URL is required}"
: "${N8N_API_KEY:?N8N_API_KEY is required}"

TARGET_DIR="/Users/linktrend/Projects/LiNKautowork/automations/live/$ENVIRONMENT"
mkdir -p "$TARGET_DIR"

WORKFLOWS_JSON="$(curl -sS -H "x-n8n-api-key: $N8N_API_KEY" "$N8N_BASE_URL/api/v1/workflows?limit=250")"

echo "$WORKFLOWS_JSON" | jq -c '.data[]' | while read -r workflow; do
  id="$(echo "$workflow" | jq -r '.id')"
  name="$(echo "$workflow" | jq -r '.name' | tr ' /' '__')"
  curl -sS -H "x-n8n-api-key: $N8N_API_KEY" "$N8N_BASE_URL/api/v1/workflows/$id" | jq '.' > "$TARGET_DIR/${name}-${id}.json"
done

echo "Exported active workflow snapshots to $TARGET_DIR"
