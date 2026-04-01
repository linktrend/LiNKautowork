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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/deploy/${ENVIRONMENT}/.env"

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

echo "Validating GSM secret accessibility for $ENVIRONMENT (project: $PROJECT_ID)"

for key in "${!kv[@]}"; do
  if [[ "$key" != *_SECRET_NAME ]]; then
    continue
  fi

  secret_name="${kv[$key]}"
  if [[ -z "$secret_name" ]]; then
    echo "Secret name is empty for key: $key"
    exit 1
  fi

  gcloud secrets versions access latest --project "$PROJECT_ID" --secret "$secret_name" >/dev/null
  echo "  OK $key -> $secret_name"
done

echo "Validation complete. No resolved secrets were written to disk."
