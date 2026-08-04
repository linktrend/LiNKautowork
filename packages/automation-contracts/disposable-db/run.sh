#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
PROJECT_NAME="linkautowork-contracts-db-$$"

cleanup() {
  docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_for_postgrest_host() {
  local rest_port
  for _ in $(seq 1 30); do
    if rest_port="$(docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" port postgrest 3000 2>/dev/null)"; then
      rest_port="${rest_port##*:}"
      if [[ -n "$rest_port" ]] && curl -fsS --connect-timeout 2 --max-time 5 "http://127.0.0.1:${rest_port}/" >/dev/null 2>&1; then
        return 0
      fi
    fi
    sleep 1
  done
  echo 'PostgREST did not become reachable on its published host port' >&2
  return 1
}

docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" up -d
for _ in $(seq 1 30); do
  if docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts -c 'select 1' >/dev/null 2>&1; then break; fi
  sleep 1
done
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts -c 'select 1' >/dev/null

apply_up() {
  awk '/^-- migrate:down/{exit} {print}' "$1" | docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts
}

apply_down() {
  awk 'found {print} /^-- migrate:down/{found=1; next}' "$1" | docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts
}

docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts < "$SCRIPT_DIR/bootstrap-platform.sql"
apply_up "$ROOT_DIR/supabase/migrations/20260715_000001_lautowork_control_core.sql"
apply_up "$ROOT_DIR/supabase/migrations/20260718_000001_lautowork_control_persistence.sql"
apply_up "$ROOT_DIR/supabase/migrations/20260804_000001_lautowork_automation_control_model.sql"
apply_up "$ROOT_DIR/supabase/migrations/20260804_000002_lautowork_wave2_runtime_corrections.sql"
apply_up "$ROOT_DIR/supabase/migrations/20260804_000003_lautowork_librarian_state.sql"
apply_up "$ROOT_DIR/supabase/migrations/20260804_000004_lautowork_operations_runtime.sql"
apply_up "$ROOT_DIR/supabase/migrations/20260804_000005_lautowork_product_durability.sql"
apply_up "$ROOT_DIR/supabase/migrations/20260804_000006_lautowork_product_api_read_models.sql"
apply_up "$ROOT_DIR/supabase/migrations/20260804_000007_lautowork_commercial_lifecycle.sql"
apply_up "$ROOT_DIR/supabase/migrations/20260804_000008_lautowork_product_api_closure.sql"
apply_up "$ROOT_DIR/supabase/migrations/20260804_000010_lautowork_operator_operations.sql"
apply_up "$ROOT_DIR/supabase/migrations/20260804_000011_lautowork_governed_commercial_webhooks.sql"
apply_up "$ROOT_DIR/supabase/migrations/20260804_000012_lautowork_durable_audit_outbox.sql"
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts < "$SCRIPT_DIR/verify.sql"
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts < "$SCRIPT_DIR/wave2-runtime-verify.sql"
bash "$SCRIPT_DIR/concurrent-accept.sh" "$COMPOSE_FILE" "$PROJECT_NAME"
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts < "$SCRIPT_DIR/librarian-verify.sql"
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts < "$SCRIPT_DIR/operations-verify.sql"
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts < "$SCRIPT_DIR/product-durability-verify.sql"
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts < "$SCRIPT_DIR/product-webhook-setup.sql"
bash "$SCRIPT_DIR/operations-concurrent-transition.sh" "$COMPOSE_FILE" "$PROJECT_NAME"
bash "$SCRIPT_DIR/postgrest-verify.sh" "$COMPOSE_FILE" "$PROJECT_NAME"
bash "$SCRIPT_DIR/audit-outbox-verify.sh" "$COMPOSE_FILE" "$PROJECT_NAME"
wait_for_postgrest_host
bash "$SCRIPT_DIR/product-webhook-verify.sh" "$COMPOSE_FILE" "$PROJECT_NAME"
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts < "$SCRIPT_DIR/operator-fixtures.sql"
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts < "$SCRIPT_DIR/operator-verify.sql"
bash "$SCRIPT_DIR/control-restore-rehearsal.sh" "$COMPOSE_FILE" "$PROJECT_NAME"
apply_down "$ROOT_DIR/supabase/migrations/20260804_000012_lautowork_durable_audit_outbox.sql"
apply_down "$ROOT_DIR/supabase/migrations/20260804_000011_lautowork_governed_commercial_webhooks.sql"
apply_down "$ROOT_DIR/supabase/migrations/20260804_000010_lautowork_operator_operations.sql"
apply_down "$ROOT_DIR/supabase/migrations/20260804_000008_lautowork_product_api_closure.sql"
apply_down "$ROOT_DIR/supabase/migrations/20260804_000007_lautowork_commercial_lifecycle.sql"
apply_down "$ROOT_DIR/supabase/migrations/20260804_000006_lautowork_product_api_read_models.sql"
apply_down "$ROOT_DIR/supabase/migrations/20260804_000005_lautowork_product_durability.sql"
apply_down "$ROOT_DIR/supabase/migrations/20260804_000004_lautowork_operations_runtime.sql"
apply_down "$ROOT_DIR/supabase/migrations/20260804_000003_lautowork_librarian_state.sql"
apply_down "$ROOT_DIR/supabase/migrations/20260804_000002_lautowork_wave2_runtime_corrections.sql"
apply_down "$ROOT_DIR/supabase/migrations/20260804_000001_lautowork_automation_control_model.sql"
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts < "$SCRIPT_DIR/rollback-verify.sql"
