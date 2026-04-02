#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 <dev|prod> [--output <path>]

Resolves *_SECRET_NAME values from deploy/<env>/.env via GSM and writes a runtime env file.
The output file is intended for deployment runtime only and must not be committed.
USAGE
}

if [[ $# -lt 1 || $# -gt 3 ]]; then
  usage
  exit 1
fi

ENVIRONMENT="$1"
shift
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
  echo "Environment must be dev or prod"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BASE_ENV_FILE="$ROOT_DIR/deploy/${ENVIRONMENT}/.env"

if [[ ! -f "$BASE_ENV_FILE" ]]; then
  echo "Missing env file: $BASE_ENV_FILE"
  exit 1
fi

OUTPUT_FILE="${ROOT_DIR}/deploy/${ENVIRONMENT}/.env.runtime"
if [[ $# -gt 0 ]]; then
  if [[ "$1" != "--output" || $# -ne 2 ]]; then
    usage
    exit 1
  fi
  OUTPUT_FILE="$2"
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI is required to resolve GSM secrets"
  exit 1
fi

declare -A kv
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  [[ "$line" != *=* ]] && continue

  key="${line%%=*}"
  value="${line#*=}"
  key="${key//[$'\t\r\n ']/}"
  kv["$key"]="$value"
done < "$BASE_ENV_FILE"

PROJECT_ID="${GCP_PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:-${kv[GCP_PROJECT_ID]:-${kv[GOOGLE_CLOUD_PROJECT]:-}}}}"
if [[ -z "$PROJECT_ID" ]]; then
  echo "Missing GCP project. Set GCP_PROJECT_ID/GOOGLE_CLOUD_PROJECT in env or $BASE_ENV_FILE"
  exit 1
fi

resolve_secret() {
  local secret_name="$1"
  gcloud secrets versions access latest --project "$PROJECT_ID" --secret "$secret_name"
}

mkdir -p "$(dirname "$OUTPUT_FILE")"
{
  echo "# generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# source: $BASE_ENV_FILE"
  echo "# project: $PROJECT_ID"

  for key in "${!kv[@]}"; do
    if [[ "$key" == *_SECRET_NAME ]]; then
      continue
    fi
    printf '%s=%s\n' "$key" "${kv[$key]}"
  done

  for key in "${!kv[@]}"; do
    if [[ "$key" != *_SECRET_NAME ]]; then
      continue
    fi

    secret_name="${kv[$key]}"
    if [[ -z "$secret_name" ]]; then
      echo "Secret name is empty for key: $key" >&2
      exit 1
    fi

    target_key="${key%_SECRET_NAME}"
    secret_value="$(resolve_secret "$secret_name")"
    printf '%s=%s\n' "$target_key" "$secret_value"
  done
} > "$OUTPUT_FILE"

# Force Tailscale URL canonicalization when configured.
if grep -q '^N8N_TAILSCALE_IP=' "$OUTPUT_FILE"; then
  ts_ip="$(grep '^N8N_TAILSCALE_IP=' "$OUTPUT_FILE" | cut -d= -f2-)"
  if [[ -n "$ts_ip" ]]; then
    sed -i "s#^N8N_HOST=.*#N8N_HOST=${ts_ip}#" "$OUTPUT_FILE"
    sed -i "s#^N8N_PROTOCOL=.*#N8N_PROTOCOL=http#" "$OUTPUT_FILE"
    sed -i "s#^N8N_EDITOR_BASE_URL=.*#N8N_EDITOR_BASE_URL=http://${ts_ip}:5678#" "$OUTPUT_FILE"
    sed -i "s#^WEBHOOK_URL=.*#WEBHOOK_URL=http://${ts_ip}:5678/#" "$OUTPUT_FILE"
  fi
fi

chmod 600 "$OUTPUT_FILE"
echo "Rendered runtime env: $OUTPUT_FILE"
