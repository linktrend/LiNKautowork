#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="$1"
PROJECT_NAME="$2"
RESULT_DIR="$(mktemp -d)"
FIRST_RESULT="$RESULT_DIR/first.txt"
SECOND_RESULT="$RESULT_DIR/second.txt"
trap 'rm -rf "$RESULT_DIR"' EXIT

prepare_transition() {
  local deployment_id="$1"
  local idempotency_key="$2"
  docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres \
    psql -At -v ON_ERROR_STOP=1 -U postgres -d automation_contracts <<SQL
begin;
select set_config('request.jwt.claim.org_id','00000000-0000-0000-0000-000000000002',false);
select set_config('request.jwt.claim.role','service_role',false);
select public.linkautowork_prepare_deployment_transition('{"orgId":"00000000-0000-0000-0000-000000000002","deploymentId":"${deployment_id}","action":"canary","idempotencyKey":"${idempotency_key}","actor":"concurrency-test","reason":"same-instance reservation proof"}'::jsonb);
select pg_sleep(2);
commit;
SQL
}

prepare_transition '50000000-0000-0000-0000-000000000001' 'concurrent-first' >"$FIRST_RESULT" &
FIRST_PID=$!
sleep 0.4
prepare_transition '50000000-0000-0000-0000-000000000004' 'concurrent-second' >"$SECOND_RESULT"
wait "$FIRST_PID"

grep -q '"disposition": "prepared"' "$FIRST_RESULT"
grep -q '"disposition": "in_progress"' "$SECOND_RESULT"

docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres \
  psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts <<'SQL'
select set_config('request.jwt.claim.org_id','00000000-0000-0000-0000-000000000002',false);
select set_config('request.jwt.claim.role','service_role',false);
select public.assert_true(
  (select count(*)=1 from lautowork.deployment_transitions
   where org_id='00000000-0000-0000-0000-000000000002'
     and instance_id='40000000-0000-0000-0000-000000000001'
     and status='prepared'),
  'two sessions reserve only one prepared transition per instance');
select public.linkautowork_fail_deployment_transition(
  '00000000-0000-0000-0000-000000000002',
  (select id from lautowork.deployment_transitions
   where org_id='00000000-0000-0000-0000-000000000002'
     and instance_id='40000000-0000-0000-0000-000000000001'
     and status='prepared'),
  'concurrency proof cleanup',false);
SQL

echo 'WP-08 concurrent deployment reservation verification passed'
