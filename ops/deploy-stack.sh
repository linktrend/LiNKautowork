#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 <dev|prod> [--build] [--runtime-dir <path>]

Deploys stack with GSM-resolved runtime env (secrets written to runtime dir, not repo).
USAGE
}

if [[ $# -lt 1 || $# -gt 4 ]]; then
  usage
  exit 1
fi

ENVIRONMENT="$1"
shift
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
  echo "Environment must be dev or prod"
  exit 1
fi

BUILD_FLAG=""
RUNTIME_DIR="${LINKAUTOWORK_RUNTIME_DIR:-/opt/linktrend/runtime/linkautowork}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build)
      BUILD_FLAG="--build"
      shift
      ;;
    --runtime-dir)
      RUNTIME_DIR="$2"
      shift 2
      ;;
    *)
      usage
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/deploy/${ENVIRONMENT}/docker-compose.yml"
BASE_ENV_FILE="$ROOT_DIR/deploy/${ENVIRONMENT}/.env"
RUNTIME_ENV_FILE="$RUNTIME_DIR/${ENVIRONMENT}.env.runtime"

if [[ ! -f "$BASE_ENV_FILE" || ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing deploy files for environment: $ENVIRONMENT"
  exit 1
fi

"$SCRIPT_DIR/render-runtime-env-from-gsm.sh" "$ENVIRONMENT" --output "$RUNTIME_ENV_FILE"

if [[ "$ENVIRONMENT" == "prod" ]]; then
  if [[ -n "${N8N_TAILSCALE_IP:-}" ]]; then
    sed -i "s#^N8N_HOST=.*#N8N_HOST=${N8N_TAILSCALE_IP}#" "$RUNTIME_ENV_FILE"
    sed -i "s#^N8N_PROTOCOL=.*#N8N_PROTOCOL=http#" "$RUNTIME_ENV_FILE"
    sed -i "s#^N8N_EDITOR_BASE_URL=.*#N8N_EDITOR_BASE_URL=http://${N8N_TAILSCALE_IP}:5678#" "$RUNTIME_ENV_FILE"
    sed -i "s#^WEBHOOK_URL=.*#WEBHOOK_URL=http://${N8N_TAILSCALE_IP}:5678/#" "$RUNTIME_ENV_FILE"
  fi
fi

# Export vars required by compose substitutions.
set -a
source "$RUNTIME_ENV_FILE"
set +a

docker compose --env-file "$BASE_ENV_FILE" -f "$COMPOSE_FILE" -p "$ENVIRONMENT" up -d $BUILD_FLAG
