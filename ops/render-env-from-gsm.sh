#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <dev|prod>"
  exit 1
fi

ENVIRONMENT="$1"
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
  echo "Environment must be dev or prod"
  exit 1
fi

ENV_FILE="/Users/linktrend/Projects/LiNKautowork/deploy/${ENVIRONMENT}/.env"
OUT_FILE="/Users/linktrend/Projects/LiNKautowork/deploy/${ENVIRONMENT}/.env.runtime"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE"
  exit 1
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI is required to resolve GSM secrets"
  exit 1
fi

declare -A kv
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  [[ "$line" != *"="* ]] && continue

  key="${line%%=*}"
  value="${line#*=}"
  key="${key//[$'\t\r\n ']/}"
  kv["$key"]="$value"
done < "$ENV_FILE"

PROJECT_ID="${GCP_PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:-${kv[GCP_PROJECT_ID]:-${kv[GOOGLE_CLOUD_PROJECT]:-}}}}"
if [[ -z "$PROJECT_ID" ]]; then
  echo "Missing GCP project. Set GCP_PROJECT_ID/GOOGLE_CLOUD_PROJECT in env or $ENV_FILE"
  exit 1
fi

cp "$ENV_FILE" "$OUT_FILE"

for key in "${!kv[@]}"; do
  if [[ "$key" != *_SECRET_NAME ]]; then
    continue
  fi

  secret_name="${kv[$key]}"
  if [[ -z "$secret_name" ]]; then
    echo "Secret name is empty for key: $key"
    exit 1
  fi

  base_key="${key%_SECRET_NAME}"
  secret_value="$(gcloud secrets versions access latest --project "$PROJECT_ID" --secret "$secret_name")"

  if grep -q "^${base_key}=" "$OUT_FILE"; then
    sed -i.bak "/^${base_key}=/d" "$OUT_FILE"
    rm -f "${OUT_FILE}.bak"
  fi

  {
    printf '\n'
    printf '%s=%s\n' "$base_key" "$secret_value"
  } >> "$OUT_FILE"
done

chmod 600 "$OUT_FILE"
echo "Generated runtime env: $OUT_FILE"
