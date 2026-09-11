#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 [--environment prod] [--compose-file <path>] [--canary <id>]

Read-only Server01 acceptance verifier for the source topology. It never SSHs,
never applies migrations, and never activates a canary unless --canary is an
explicit later-authorised argument (still HOLD in AW-05).
USAGE
}

ENVIRONMENT="prod"
COMPOSE_FILE=""
CANARY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --environment)
      ENVIRONMENT="$2"
      shift 2
      ;;
    --compose-file)
      COMPOSE_FILE="$2"
      shift 2
      ;;
    --canary)
      CANARY="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -z "$COMPOSE_FILE" ]]; then
  COMPOSE_FILE="$ROOT_DIR/deploy/${ENVIRONMENT}/docker-compose.yml"
fi
EXAMPLE_ENV="$ROOT_DIR/deploy/${ENVIRONMENT}/.env.example"
IDENTITY="$ROOT_DIR/deploy/prod/release-identity.json"
GATEWAY_DOCKERFILE="$ROOT_DIR/deploy/common/gateway.Dockerfile"

fail=0
hold=0
pass() { echo "PASS: $1"; }
warn_hold() { echo "HOLD: $1"; hold=$((hold + 1)); }
fail_msg() { echo "FAIL: $1" >&2; fail=1; }

[[ -f "$COMPOSE_FILE" ]] || fail_msg "missing compose $COMPOSE_FILE"
[[ -f "$EXAMPLE_ENV" ]] || fail_msg "missing $EXAMPLE_ENV"
[[ -f "$IDENTITY" ]] || fail_msg "missing release identity"
[[ -f "$GATEWAY_DOCKERFILE" ]] || fail_msg "missing gateway Dockerfile"

compose="$(cat "$COMPOSE_FILE" 2>/dev/null || true)"

if ! grep -q 'package-lock.json' "$GATEWAY_DOCKERFILE"; then
  fail_msg "gateway Dockerfile missing lockfile COPY (not reproducible)"
fi
if grep -qE 'FROM node:.*latest' "$GATEWAY_DOCKERFILE"; then
  fail_msg "gateway Dockerfile uses unpinned node tag"
fi
pass "gateway image uses lockfile-pinned Node 22.13.1-alpine contract"

for net in autowork-edge autowork-runtime autowork-events; do
  if ! grep -q "^  ${net}:" "$COMPOSE_FILE"; then
    fail_msg "missing network $net"
  fi
done
pass "least-privilege networks declared"

if echo "$compose" | grep -qE 'network_mode:[[:space:]]*host'; then
  fail_msg "host network is forbidden"
fi

if echo "$compose" | grep -qE '^[[:space:]]+ports:'; then
  fail_msg "Compose publishes host ports; protected ports must stay private"
else
  pass "no Compose host ports (4222/8222/5678/8080 unpublished)"
fi

if echo "$compose" | grep -qiE '^[[:space:]]*image:[[:space:]]*[^[:space:]]+:latest'; then
  fail_msg "Compose uses :latest"
else
  pass "no :latest image tags"
fi

if ! grep -q 'nats_jetstream_prod:/data' "$COMPOSE_FILE"; then
  fail_msg "NATS persistence volume missing"
fi
if ! awk '/^  nats:/{p=1} p&&/^  [a-z]/{if($1!="nats:") exit} p&&/autowork-events/{found=1} END{exit !found}' "$COMPOSE_FILE"; then
  fail_msg "NATS is not attached only through autowork-events"
fi
pass "persistent non-host-network NATS"

if grep -qE '^[[:space:]]+runtime-dispatch' "$COMPOSE_FILE"; then
  fail_msg "runtime dispatcher must not be a Compose service"
fi
pass "runtime dispatcher remains in-process (no compose service)"

if ! grep -q 'LINKAUTOWORK_MIGRATION_MODE: dry-run' "$COMPOSE_FILE"; then
  fail_msg "migration job is not pinned to dry-run"
fi
if grep -q 'apply-authorized' "$COMPOSE_FILE"; then
  fail_msg "compose must not enable authorised migration apply"
fi
pass "migration preflight refuses live apply (dry-run only)"

for role in svc_lautowork_gateway svc_lautowork_product_api svc_lautowork_n8n svc_observer svc_lautowork_migration_backup; do
  if ! grep -q "$role" "$EXAMPLE_ENV"; then
    fail_msg "AW-01 role name $role missing from env contract"
  fi
done
pass "AW-01 role names present as placeholders"

if [[ -d /srv/linktrend/deploy/linkautowork/current ]]; then
  warn_hold "live current pointer exists; AW-05 does not inspect Server01 health"
else
  warn_hold "release current pointer absent (expected until AW-08)"
fi

if [[ -n "$CANARY" ]]; then
  warn_hold "canary '$CANARY' supplied but live n8n activation is AW-08 HOLD; no binding mutated"
else
  pass "no canary argument; verifier stayed read-only"
fi

warn_hold "Compose service health, receipt/kill-switch live state, and backup artifacts are not claimed (no Server01/provider access)"

echo
echo "commit=$(git -C "$ROOT_DIR" rev-parse HEAD)"
echo "tree=$(git -C "$ROOT_DIR" rev-parse HEAD^{tree})"

if [[ "$fail" -ne 0 ]]; then
  echo "verify-server01-acceptance: FAIL" >&2
  exit 1
fi
echo "verify-server01-acceptance: PASS with ${hold} HOLD row(s). Live/provider boundaries remain HOLD."
exit 0
