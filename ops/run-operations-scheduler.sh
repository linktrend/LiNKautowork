#!/usr/bin/env bash
set -euo pipefail

: "${LINKAUTOWORK_GATEWAY_URL:?gateway URL required}"
: "${LINK_SERVICE_TOKEN_OPERATIONS:?operations service token required}"
: "${PLATFORM_INVOCATION_TOKEN:?platform invocation token required}"

invoke() {
  local method="$1" path="$2"
  curl --fail-with-body --silent --show-error -X "$method" "${LINKAUTOWORK_GATEWAY_URL}${path}" \
    -H 'x-link-service: operations-scheduler' \
    -H "x-link-service-token: ${LINK_SERVICE_TOKEN_OPERATIONS}" \
    -H "authorization: Bearer ${PLATFORM_INVOCATION_TOKEN}" \
    -H 'content-type: application/json' \
    --data '{}'
}

while true; do
  invoke POST /v1/operations/monitor/run
  invoke POST /v1/operations/maintenance/run
  sleep "${OPERATIONS_INTERVAL_SECONDS:-300}"
done
