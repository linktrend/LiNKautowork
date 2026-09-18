#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 <dev|prod> --output <path> [--placeholders]

Writes a mode-0600 runtime env file from names-only *_SECRET_NAME placeholders.
Secret values are never resolved. Output must sit outside the git work tree
(typically /srv/linktrend/runtime/linkautowork or a disposable temp dir).
Live GSM, Server01, Tailscale, registry, and providers remain HOLD.
USAGE
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

ENVIRONMENT="$1"
shift
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
  echo "Environment must be dev or prod" >&2
  exit 1
fi

OUTPUT_FILE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      OUTPUT_FILE="${2:-}"
      shift 2
      ;;
    --placeholders)
      shift
      ;;
    --resolve-gsm|--live)
      echo "HOLD: live GSM resolve is forbidden in AW-05 (AW-08)." >&2
      exit 2
      ;;
    *)
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$OUTPUT_FILE" ]]; then
  usage
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BASE_ENV_FILE="$ROOT_DIR/deploy/${ENVIRONMENT}/.env"
if [[ ! -f "$BASE_ENV_FILE" ]]; then
  BASE_ENV_FILE="$ROOT_DIR/deploy/${ENVIRONMENT}/.env.example"
fi
if [[ ! -f "$BASE_ENV_FILE" ]]; then
  echo "Missing env contract for $ENVIRONMENT" >&2
  exit 1
fi

abs_output="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$OUTPUT_FILE")"
git_root="$(git -C "$ROOT_DIR" rev-parse --show-toplevel)"
case "$abs_output" in
  "$git_root"|"$git_root"/*)
    echo "Refusing to write runtime env inside the git work tree: $abs_output" >&2
    echo "Use /srv/linktrend/runtime/linkautowork or a disposable directory." >&2
    exit 1
    ;;
esac

mkdir -p "$(dirname "$abs_output")"
umask 077
{
  echo "# generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# source: $BASE_ENV_FILE"
  echo "# mode: placeholders-only (GSM resolve HOLD)"
  echo "# packet: AW-05"

  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" != *=* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    key="${key//[$'\t\r\n ']/}"
    if [[ "$key" == *_SECRET_NAME ]]; then
      continue
    fi
    printf '%s=%s\n' "$key" "$value"
  done < "$BASE_ENV_FILE"

  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" != *=* ]] && continue
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
    target_key="${key%_SECRET_NAME}"
    printf '%s=%s\n' "$target_key" "<GSM_PLACEHOLDER:${value}>"
  done < "$BASE_ENV_FILE"
} > "$abs_output"

chmod 600 "$abs_output"
echo "Rendered placeholder runtime env: $abs_output (mode 0600). Live GSM remain HOLD."
