#!/usr/bin/env bash
set -euo pipefail

compose_file="$1"
project_name="$2"
jwt_secret='linkautowork-disposable-postgrest-secret-2026'
org_a='00000000-0000-0000-0000-000000000002'
org_b='00000000-0000-0000-0000-000000000003'

sign_jwt() {
  JWT_SECRET="$jwt_secret" JWT_ROLE="$1" JWT_ORG="$2" node -e '
    const crypto=require("node:crypto");
    const enc=(value)=>Buffer.from(JSON.stringify(value)).toString("base64url");
    const header=enc({alg:"HS256",typ:"JWT"});
    const payload=enc({role:process.env.JWT_ROLE,org_id:process.env.JWT_ORG,exp:Math.floor(Date.now()/1000)+300});
    const sig=crypto.createHmac("sha256",process.env.JWT_SECRET).update(`${header}.${payload}`).digest("base64url");
    process.stdout.write(`${header}.${payload}.${sig}`);'
}

token_a="$(sign_jwt svc_lautowork_runtime "$org_a")"
token_b="$(sign_jwt svc_lautowork_runtime "$org_b")"
wrong_role_token="$(sign_jwt wrong_runtime "$org_a")"

for _ in $(seq 1 30); do
  if docker compose -f "$compose_file" -p "$project_name" exec -T http curl -fsS http://postgrest:3000/ >/dev/null 2>&1; then break; fi
  sleep 1
done
docker compose -f "$compose_file" -p "$project_name" exec -T postgres psql -U postgres -d automation_contracts -c "notify pgrst, 'reload schema';" >/dev/null
sleep 1

rpc_status() {
  local token="$1" header_org="$2" rpc="$3" body="$4"
  docker compose -f "$compose_file" -p "$project_name" exec -T http curl -sS -o /dev/null -w '%{http_code}' \
    -H 'apikey: disposable-project-api-key' -H "Authorization: Bearer $token" -H "x-link-org-id: $header_org" \
    -H 'content-type: application/json' --data "$body" "http://postgrest:3000/rpc/$rpc"
}

expect_success() { local status; status="$(rpc_status "$@")"; [[ "$status" == 2* ]] || { echo "expected success, got HTTP $status for $3" >&2; exit 1; }; }
expect_denied() { local status; status="$(rpc_status "$@")"; [[ "$status" == 4* ]] || { echo "expected denial, got HTTP $status for $3" >&2; exit 1; }; }

# Representative SECURITY DEFINER calls from migrations 000002, 000003, 000004.
expect_success "$token_a" "$org_a" linkautowork_resolve_bound_instance "{\"p_org_id\":\"$org_a\",\"p_consumer_system\":\"linksites\",\"p_operation\":\"linksites.reminder.run\"}"
expect_success "$token_a" "$org_a" linkautowork_librarian_get_control "{\"p_org_id\":\"$org_a\",\"p_automation_id\":\"client-a-reminder\"}"
expect_success "$token_a" "$org_a" linkautowork_active_pause "{\"p_org_id\":\"$org_a\",\"p_automation_id\":\"client-a-reminder\",\"p_instance_id\":\"40000000-0000-0000-0000-000000000001\"}"
expect_denied "$token_a" "$org_a" linkautowork_product_create_order "{\"p_product_id\":\"90000000-0000-0000-0000-000000000001\",\"p_idempotency_key\":\"postgrest-product-order-key\"}"

expect_denied "$token_b" "$org_b" linkautowork_resolve_bound_instance "{\"p_org_id\":\"$org_a\",\"p_consumer_system\":\"linksites\",\"p_operation\":\"linksites.reminder.run\"}"
expect_denied "$token_a" "$org_b" linkautowork_librarian_get_control "{\"p_org_id\":\"$org_a\",\"p_automation_id\":\"client-a-reminder\"}"
expect_denied "$wrong_role_token" "$org_a" linkautowork_active_pause "{\"p_org_id\":\"$org_a\",\"p_automation_id\":\"client-a-reminder\",\"p_instance_id\":\"40000000-0000-0000-0000-000000000001\"}"
expect_denied "$wrong_role_token" "$org_a" linkautowork_product_create_order "{\"p_product_id\":\"90000000-0000-0000-0000-000000000001\",\"p_idempotency_key\":\"postgrest-product-denied-key\"}"

echo 'PostgREST scoped JWT authorization verification passed'
