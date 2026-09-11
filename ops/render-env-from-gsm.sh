#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 <dev|prod> [--placeholders]

Validates *_SECRET_NAME entries in deploy/<env>/.env.example (or .env if present)
as GSM name placeholders. Does not call gcloud, GSM, Server01, Tailscale, or a
registry. Live secret access is HOLD (AW-08).
USAGE
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage
  exit 1
fi

ENVIRONMENT="$1"
shift
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
  echo "Environment must be dev or prod" >&2
  exit 1
fi

PLACEHOLDERS=1
if [[ $# -eq 1 ]]; then
  if [[ "$1" != "--placeholders" ]]; then
    usage
    exit 1
  fi
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/deploy/${ENVIRONMENT}/.env"
EXAMPLE_FILE="$ROOT_DIR/deploy/${ENVIRONMENT}/.env.example"

if [[ -f "$ENV_FILE" ]]; then
  SOURCE_FILE="$ENV_FILE"
else
  SOURCE_FILE="$EXAMPLE_FILE"
fi

if [[ ! -f "$SOURCE_FILE" ]]; then
  echo "Missing env contract: $SOURCE_FILE" >&2
  exit 1
fi

if command -v gcloud >/dev/null 2>&1; then
  echo "HOLD: gcloud is present but AW-05 will not access GSM. Placeholder validation only."
fi

secret_count=0
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  [[ "$line" != *"="* ]] && continue
  key="${line%%=*}"
  value="${line#*=}"
  key="${key//[$'\t\r\n ']/}"
  if [[ "$key" != *_SECRET_NAME ]]; then
    continue
  fi
  if [[ -z "$value" ]]; then
    echo "Secret name is empty for key: $key" >&2
    exit 1
  fi
  if [[ "$value" =~ ^(sk-|ghp_|xox|AKIA|-----BEGIN) ]]; then
    echo "Refusing inline credential-like value for $key" >&2
    exit 1
  fi
  echo "  PLACEHOLDER $key -> $value"
  secret_count=$((secret_count + 1))
done < "$SOURCE_FILE"

if [[ "$secret_count" -lt 1 ]]; then
  echo "No *_SECRET_NAME placeholders found in $SOURCE_FILE" >&2
  exit 1
fi

echo "GSM placeholder validation complete for $ENVIRONMENT (source: $SOURCE_FILE)."
echo "Resolved secrets were not read. Live GSM access remains HOLD."
echo "Use ops/render-runtime-env-from-gsm.sh --placeholders to write a 0600 names-only runtime file."
