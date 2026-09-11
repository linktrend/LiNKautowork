#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 <dev|prod> [--dry-run] [--build] [--runtime-dir <path>] [--print-release-layout]

Source-only stack helper for AW-05:
  - validates Compose with names-only env
  - renders a 0600 placeholder runtime file outside the git tree
  - prints the atomic current/releases layout

Does not SSH, start containers, pull a registry, resolve GSM, or mutate Server01.
Live install/upgrade/rollback is AW-08 HOLD. --build is accepted as a no-op flag
so existing runbook text does not imply a live build.
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

RUNTIME_DIR="${LINKAUTOWORK_RUNTIME_DIR:-/tmp/linkautowork-runtime-aw05}"
PRINT_LAYOUT=0
DRY_RUN=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --build)
      shift
      ;;
    --runtime-dir)
      RUNTIME_DIR="$2"
      shift 2
      ;;
    --print-release-layout)
      PRINT_LAYOUT=1
      shift
      ;;
    --up|--live|--apply)
      echo "HOLD: live compose up / Server01 apply is forbidden in AW-05 (AW-08)." >&2
      exit 2
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
EXAMPLE_ENV="$ROOT_DIR/deploy/${ENVIRONMENT}/.env.example"
BASE_ENV_FILE="$ROOT_DIR/deploy/${ENVIRONMENT}/.env"
if [[ ! -f "$BASE_ENV_FILE" ]]; then
  BASE_ENV_FILE="$EXAMPLE_ENV"
fi

if [[ ! -f "$BASE_ENV_FILE" || ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing deploy files for environment: $ENVIRONMENT" >&2
  exit 1
fi

COMMIT="$(git -C "$ROOT_DIR" rev-parse HEAD)"
TREE="$(git -C "$ROOT_DIR" rev-parse HEAD^{tree})"
RELEASE_ROOT="/srv/linktrend/deploy/linkautowork"
RUNTIME_ROOT="/srv/linktrend/runtime/linkautowork"

if [[ "$PRINT_LAYOUT" -eq 1 ]]; then
  cat <<LAYOUT
atomic-release-layout (not applied; AW-08 HOLD)
  checkout: ${RELEASE_ROOT}/releases/${COMMIT}
  current:  ${RELEASE_ROOT}/current -> releases/${COMMIT}
  previous: ${RELEASE_ROOT}/previous (retained last accepted)
  runtime:  ${RUNTIME_ROOT}/${ENVIRONMENT}.env.runtime (mode 0600)
  identity: deploy/prod/release-identity.json
  commit:   ${COMMIT}
  tree:     ${TREE}
rollback: retarget current to previous, start that Compose definition, do not apply SQL down.
LAYOUT
fi

"$SCRIPT_DIR/render-env-from-gsm.sh" "$ENVIRONMENT" --placeholders

RUNTIME_ENV_FILE="$RUNTIME_DIR/${ENVIRONMENT}.env.runtime"
mkdir -p "$RUNTIME_DIR"
"$SCRIPT_DIR/render-runtime-env-from-gsm.sh" "$ENVIRONMENT" --placeholders --output "$RUNTIME_ENV_FILE"

if ! command -v docker >/dev/null 2>&1; then
  echo "HOLD: docker CLI is not installed in this disposable environment; compose render skipped after placeholder checks." >&2
  echo "Install Docker Compose only for local 'docker compose ... config'. Do not target Server01." >&2
  exit 0
fi

echo "Rendering Compose config (names-only, no up)."
docker compose --env-file "$BASE_ENV_FILE" -f "$COMPOSE_FILE" -p "linkautowork-${ENVIRONMENT}-dry" config >/dev/null
echo "Compose config OK for $ENVIRONMENT (dry-run=${DRY_RUN}). Live deploy remains HOLD."
