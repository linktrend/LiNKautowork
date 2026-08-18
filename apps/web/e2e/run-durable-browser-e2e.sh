#!/usr/bin/env bash
set -euo pipefail

# Isolated, loopback-only Postgres/PostgREST backing store for the canonical browser proof.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DB_DIR="$ROOT_DIR/packages/automation-contracts/disposable-db"
COMPOSE_FILE="$DB_DIR/docker-compose.yml"
PROJECT_NAME="linkautowork-browser-e2e-$$"
export LINKAUTOWORK_DISPOSABLE_BROWSER=true
compose() { docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" "$@"; }
MIGRATIONS=(
  "$ROOT_DIR/supabase/migrations/20260715_000001_lautowork_control_core.sql"
  "$ROOT_DIR/supabase/migrations/20260718_000001_lautowork_control_persistence.sql"
  "$ROOT_DIR/supabase/migrations/20260804_000001_lautowork_automation_control_model.sql"
  "$ROOT_DIR/supabase/migrations/20260804_000002_lautowork_wave2_runtime_corrections.sql"
  "$ROOT_DIR/supabase/migrations/20260804_000003_lautowork_librarian_state.sql"
  "$ROOT_DIR/supabase/migrations/20260804_000004_lautowork_operations_runtime.sql"
  "$ROOT_DIR/supabase/migrations/20260804_000005_lautowork_product_durability.sql"
  "$ROOT_DIR/supabase/migrations/20260804_000006_lautowork_product_api_read_models.sql"
  "$ROOT_DIR/supabase/migrations/20260804_000007_lautowork_commercial_lifecycle.sql"
  "$ROOT_DIR/supabase/migrations/20260804_000008_lautowork_product_api_closure.sql"
  "$ROOT_DIR/supabase/migrations/20260804_000010_lautowork_operator_operations.sql"
  "$ROOT_DIR/supabase/migrations/20260804_000011_lautowork_governed_commercial_webhooks.sql"
  "$ROOT_DIR/supabase/migrations/20260804_000012_lautowork_durable_audit_outbox.sql"
)
APPLIED_MIGRATIONS=()
trap cleanup EXIT
apply_up() { awk '/^-- migrate:down/{exit} {print}' "$1" | compose exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts; }
apply_down() { awk 'found {print} /^-- migrate:down/{found=1; next}' "$1" | compose exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts; }
rollback_applied() {
  local index
  for ((index=${#APPLIED_MIGRATIONS[@]} - 1; index >= 0; index--)); do
    echo "Rolling back ${APPLIED_MIGRATIONS[index]}"
    apply_down "${APPLIED_MIGRATIONS[index]}"
  done
  APPLIED_MIGRATIONS=()
}
cleanup() {
  local exit_status=$?
  if ((exit_status != 0)); then
    echo 'Durable browser E2E service diagnostics:' >&2
    compose logs --no-color --tail=120 postgres postgrest >&2 || true
  fi
  if ((${#APPLIED_MIGRATIONS[@]} > 0)); then
    if ! rollback_applied; then
      echo 'Durable browser E2E migration rollback failed' >&2
      exit_status=1
    fi
  fi
  compose down --volumes --remove-orphans >/dev/null 2>&1 || exit_status=1
  return "$exit_status"
}

compose up -d
for _ in $(seq 1 30); do compose exec -T postgres psql -U postgres -d automation_contracts -c 'select 1' >/dev/null 2>&1 && break; sleep 1; done
compose exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts < "$DB_DIR/bootstrap-platform.sql"
for migration in "${MIGRATIONS[@]}"; do apply_up "$migration"; APPLIED_MIGRATIONS+=("$migration"); done
compose exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts < "$DB_DIR/verify.sql"
compose exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts < "$DB_DIR/operator-fixtures.sql"
compose exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts <<'SQL'
insert into lautowork.product_offering_publications(id,org_id,product_id,offering_version,release_id,release_version,release_digest,workflow_digest,terms_document_id,terms_version,terms_digest,commercial_descriptor,configuration_schema_version,configuration_schema,status)
values('91000000-0000-0000-0000-000000000010','00000000-0000-0000-0000-000000000002','90000000-0000-0000-0000-000000000001',1,'20000000-0000-0000-0000-000000000001','1.0.0','sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','hosted-automation-terms','2026-08-04','sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee','{"descriptorVersion":1,"billingModel":"operator_quote","pricePresentation":"Pricing is confirmed with support before activation.","chargesMoney":false,"paymentCollection":"none"}'::jsonb,'v1','{"type":"object","properties":{"timezone":{"type":"string","enum":["Asia/Taipei","UTC"]}},"required":["timezone"],"additionalProperties":false}'::jsonb,'published');
SQL
REST_PORT="$(compose port postgrest 3000 | sed 's/.*://')"
compose exec -T postgres psql -U postgres -d automation_contracts -c "notify pgrst, 'reload schema';" >/dev/null
for _ in $(seq 1 30); do
  curl -fsS --connect-timeout 2 --max-time 5 "http://127.0.0.1:${REST_PORT}/" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS --connect-timeout 2 --max-time 5 "http://127.0.0.1:${REST_PORT}/" >/dev/null 2>&1 || {
  echo 'PostgREST did not become ready after schema reload' >&2
  exit 1
}
TOKEN="$(node -e "const c=require('node:crypto');const h=Buffer.from(JSON.stringify({alg:'HS256',typ:'JWT'})).toString('base64url');const p=Buffer.from(JSON.stringify({role:'service_role',org_id:'00000000-0000-0000-0000-000000000002',exp:Math.floor(Date.now()/1000)+600})).toString('base64url');console.log(h+'.'+p+'.'+c.createHmac('sha256','linkautowork-disposable-postgrest-secret-2026').update(h+'.'+p).digest('base64url'))")"
REST_URL="http://127.0.0.1:${REST_PORT}"
export REST_URL
AUDIT_TOKEN="$TOKEN" node --input-type=module <<'NODE'
const audit = {
  actor: 'browser-fixture-operator',
  resource: 'audit-fixture',
  action: 'read',
  reason: 'Seed durable browser audit evidence',
  correlation: 'browser-audit-fixture',
};
const headers = {
  authorization: `Bearer ${process.env.AUDIT_TOKEN}`,
  apikey: process.env.AUDIT_TOKEN,
  'content-type': 'application/json',
  'x-link-org-id': '00000000-0000-0000-0000-000000000002',
};
const call = async (name, body, withAudit = false) => {
  const response = await fetch(`${process.env.REST_URL}/rpc/${name}`, {
    method: 'POST',
    headers: withAudit ? { ...headers, 'x-link-audit-actor': audit.actor, 'x-link-audit-resource': audit.resource, 'x-link-audit-action': audit.action, 'x-link-audit-reason': audit.reason, 'x-link-audit-correlation': audit.correlation } : headers,
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`browser audit fixture RPC failed: ${response.status}:${await response.text()}`);
  return response.json();
};
await call('linkautowork_product_reserve_audit', { p_actor: audit.actor, p_resource: audit.resource, p_action: audit.action, p_reason: audit.reason, p_correlation_id: audit.correlation });
await call('linkautowork_product_finalize_audit', { p_actor: audit.actor, p_resource: audit.resource, p_action: audit.action, p_reason: audit.reason, p_correlation_id: audit.correlation, p_outcome: 'allowed' }, true);
NODE
LINKAUTOWORK_DISPOSABLE_BROWSER=true DURABLE_POSTGREST_URL="$REST_URL" DURABLE_POSTGREST_JWT_SECRET="ltfx.ph.24c6deb948.v1" npx tsx "$ROOT_DIR/apps/web/e2e/browser-e2e.ts"
