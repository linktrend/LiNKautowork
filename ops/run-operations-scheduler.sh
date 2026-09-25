#!/usr/bin/env bash
set -euo pipefail

: "${LINKAUTOWORK_GATEWAY_URL:?gateway URL required}"
: "${LINK_SERVICE_TOKEN_OPERATIONS:?operations service token required}"
# Must match the gateway's LINK_SERVICE_TOKENS entry name.
SERVICE_NAME="${LINK_SERVICE_NAME_OPERATIONS:-operations}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

invoke() {
  local method="$1" path="$2" token="$3"
  curl --fail-with-body --silent --show-error -X "$method" "${LINKAUTOWORK_GATEWAY_URL}${path}" \
    -H "x-link-service: ${SERVICE_NAME}" \
    -H "x-link-service-token: ${LINK_SERVICE_TOKEN_OPERATIONS}" \
    -H "authorization: Bearer ${token}" \
    -H 'content-type: application/json' \
    --data '{}'
}

run_once() {
  local token
  # Platform tokens live at most 15 minutes, so every run mints its own.
  # Explicit returns: errexit does not apply inside a function called with ||.
  token="$(node "$ROOT_DIR/ops/mint-platform-token.mjs")" || return 1
  invoke POST /v1/operations/monitor/run "$token" || return 1
  echo
  invoke POST /v1/operations/maintenance/run "$token" || return 1
  echo
  echo "operations run succeeded at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

while true; do
  run_once || echo "operations run failed at $(date -u +%Y-%m-%dT%H:%M:%SZ)" >&2
  sleep "${OPERATIONS_INTERVAL_SECONDS:-300}"
done
