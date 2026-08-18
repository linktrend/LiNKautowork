#!/usr/bin/env bash
set -euo pipefail

compose_file="$1"
project_name="$2"
org_id='00000000-0000-0000-0000-000000000002'
jwt_secret='ltfx.ph.24c6deb948.v1'
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sign_jwt() {
  JWT_SECRET="${jwt_secret}" JWT_ORG="$org_id" node -e '
    const crypto=require("node:crypto");
    const enc=(value)=>Buffer.from(JSON.stringify(value)).toString("base64url");
    const header=enc({alg:"HS256",typ:"JWT"});
    const payload=enc({role:"svc_lautowork_runtime",org_id:process.env.JWT_ORG,exp:Math.floor(Date.now()/1000)+300});
    const sig=crypto.createHmac("sha256",process.env.JWT_SECRET).update(`${header}.${payload}`).digest("base64url");
    process.stdout.write(`${header}.${payload}.${sig}`);'
}

token="$(sign_jwt)"
rpc() {
  local name="$1" body="$2"
  docker compose -f "$compose_file" -p "$project_name" exec -T http curl -fsS \
    -H 'apikey: ltfx.ph.a076393258.v1 -H "Authorization: Bearer $token" \
    -H "x-link-org-id: $org_id" -H 'content-type: application/json' \
    --data "$body" "http://postgrest:3000/rpc/$name"
}

rpc_status() {
  local name="$1" body="$2"
  docker compose -f "$compose_file" -p "$project_name" exec -T http curl -sS -o /dev/null -w '%{http_code}' \
    -H 'apikey: ltfx.ph.a076393258.v1 -H "Authorization: Bearer $token" \
    -H "x-link-org-id: $org_id" -H 'content-type: application/json' \
    --data "$body" "http://postgrest:3000/rpc/$name"
}

rpc_with_audit() {
  local name="$1" body="$2" actor="$3" resource="$4" action="$5" reason="$6" correlation="$7"
  docker compose -f "$compose_file" -p "$project_name" exec -T http curl -fsS \
    -H 'apikey: ltfx.ph.a076393258.v1 -H "Authorization: Bearer $token" \
    -H "x-link-org-id: $org_id" -H "x-link-audit-actor: $actor" \
    -H "x-link-audit-resource: $resource" -H "x-link-audit-action: $action" \
    -H "x-link-audit-reason: $reason" -H "x-link-audit-correlation: $correlation" \
    -H 'content-type: application/json' --data "$body" "http://postgrest:3000/rpc/$name"
}

rpc_with_audit_status() {
  local name="$1" body="$2" actor="$3" resource="$4" action="$5" reason="$6" correlation="$7"
  docker compose -f "$compose_file" -p "$project_name" exec -T http curl -sS -o /dev/null -w '%{http_code}' \
    -H 'apikey: ltfx.ph.a076393258.v1 -H "Authorization: Bearer $token" \
    -H "x-link-org-id: $org_id" -H "x-link-audit-actor: $actor" \
    -H "x-link-audit-resource: $resource" -H "x-link-audit-action: $action" \
    -H "x-link-audit-reason: $reason" -H "x-link-audit-correlation: $correlation" \
    -H 'content-type: application/json' --data "$body" "http://postgrest:3000/rpc/$name"
}

wait_for_postgrest() {
  for _ in $(seq 1 30); do
    if docker compose -f "$compose_file" -p "$project_name" exec -T http curl -fsS --connect-timeout 2 --max-time 5 http://postgrest:3000/ >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo 'PostgREST did not become ready for durable audit verification' >&2
  return 1
}

wait_for_postgrest

unaudited_status="$(rpc_status linkautowork_product_client_instances '{"p_limit":10,"p_cursor":null}')"
old_operator_status="$(rpc_status linkautowork_product_operator_records '{"p_resource":"audit-evidence","p_limit":10,"p_cursor":null}')"
old_writer_status="$(rpc_status linkautowork_product_write_audit '{"p_actor":"audit-verifier-actor","p_resource":"instances","p_action":"pause","p_reason":"unaudited writer","p_correlation_id":"audit-old-writer","p_outcome":"allowed"}')"
[[ "$unaudited_status" == 4* && "$old_operator_status" == 4* && "$old_writer_status" == 4* ]] || {
  echo "unaudited or compatibility audit RPC unexpectedly callable: client=$unaudited_status operator=$old_operator_status writer=$old_writer_status" >&2
  exit 1
}

reserve_body='{"p_actor":"audit-verifier-actor","p_resource":"instances","p_action":"pause","p_reason":"disposable audit verifier","p_correlation_id":"audit-replay-correlation"}'
first="$(rpc linkautowork_product_reserve_audit "$reserve_body")"
replay="$(rpc linkautowork_product_reserve_audit "$reserve_body")"
FIRST="$first" REPLAY="$replay" node -e '
  const read=(value)=>{const parsed=JSON.parse(value); return Array.isArray(parsed)?parsed[0]:parsed;};
  const first=read(process.env.FIRST); const replay=read(process.env.REPLAY);
  if (first.auditId !== replay.auditId || first.status !== "pending" || replay.status !== "pending") process.exit(1);
'

audited_client_status="$(rpc_with_audit_status linkautowork_product_client_instances_audited '{"p_limit":10,"p_cursor":null}' audit-verifier-actor instances pause 'disposable audit verifier' audit-replay-correlation)"
[[ "$audited_client_status" == 2* ]] || { echo "audited client RPC did not accept its matching reservation: status=$audited_client_status" >&2; exit 1; }

docker compose -f "$compose_file" -p "$project_name" stop postgrest >/dev/null
if docker compose -f "$compose_file" -p "$project_name" exec -T http curl -fsS --connect-timeout 2 --max-time 5 http://postgrest:3000/ >/dev/null 2>&1; then
  echo 'PostgREST outage did not fail closed' >&2
  exit 1
fi
docker compose -f "$compose_file" -p "$project_name" start postgrest >/dev/null
wait_for_postgrest

finalize_body='{"p_actor":"audit-verifier-actor","p_resource":"instances","p_action":"pause","p_reason":"disposable audit verifier","p_correlation_id":"audit-replay-correlation","p_outcome":"allowed"}'
rpc_with_audit linkautowork_product_finalize_audit "$finalize_body" audit-verifier-actor instances pause 'disposable audit verifier' audit-replay-correlation >/dev/null
pending_body='{"p_actor":"audit-verifier-actor","p_resource":"instances","p_action":"resume","p_reason":"pending finalization verifier","p_correlation_id":"audit-pending-correlation"}'
rpc linkautowork_product_reserve_audit "$pending_body" >/dev/null

pending_count="$(docker compose -f "$compose_file" -p "$project_name" exec -T postgres psql -U postgres -d automation_contracts -Atc "select count(*) from lautowork.product_api_audit_outbox where org_id='$org_id' and status='pending' and correlation_id='audit-pending-correlation';")"
audit_count="$(docker compose -f "$compose_file" -p "$project_name" exec -T postgres psql -U postgres -d automation_contracts -Atc "select count(*) from lautowork.product_api_audit_events where org_id='$org_id' and correlation_id='audit-pending-correlation';")"
[[ "$pending_count" == '1' && "$audit_count" == '0' ]] || { echo 'pending audit evidence was not visible before finalization' >&2; exit 1; }

pending_finalize_body='{"p_actor":"audit-verifier-actor","p_resource":"instances","p_action":"resume","p_reason":"pending finalization verifier","p_correlation_id":"audit-pending-correlation","p_outcome":"denied"}'
rpc_with_audit linkautowork_product_finalize_audit "$pending_finalize_body" audit-verifier-actor instances resume 'pending finalization verifier' audit-pending-correlation >/dev/null
completed_count="$(docker compose -f "$compose_file" -p "$project_name" exec -T postgres psql -U postgres -d automation_contracts -Atc "select count(*) from lautowork.product_api_audit_outbox where org_id='$org_id' and status='completed' and correlation_id='audit-pending-correlation';")"
event_count="$(docker compose -f "$compose_file" -p "$project_name" exec -T postgres psql -U postgres -d automation_contracts -Atc "select count(*) from lautowork.product_api_audit_events where org_id='$org_id' and correlation_id='audit-pending-correlation' and outcome='denied';")"
[[ "$completed_count" == '1' && "$event_count" == '1' ]] || { echo 'audit finalization did not produce one durable event' >&2; exit 1; }

echo 'Durable Product API audit outbox verification passed'
