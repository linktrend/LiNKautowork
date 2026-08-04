#!/usr/bin/env bash
set -euo pipefail

compose_file="$1"
project_name="$2"

invoke() {
  local execution_id="$1"
  docker compose -f "$compose_file" -p "$project_name" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts >/dev/null <<SQL
begin;
set local request.jwt.claims = '{"role":"svc_lautowork_runtime","org_id":"00000000-0000-0000-0000-000000000002"}';
set local request.headers = '{"x-link-org-id":"00000000-0000-0000-0000-000000000002"}';
select public.linkautowork_accept_execution(
  '$execution_id','00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001',
  '20000000-0000-0000-0000-000000000001','50000000-0000-0000-0000-000000000001','wave2-concurrent-idempotency',
  'sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc','linkautowork-n8n',
  'sha256:2bab857641ead2282344948fa6e48b34d6048089f1fd912e68c2f4fafb9c6a8f');
commit;
SQL
}

invoke '60000000-0000-0000-0000-000000000020' &
first_pid=$!
invoke '60000000-0000-0000-0000-000000000021' &
second_pid=$!
wait "$first_pid"
wait "$second_pid"

docker compose -f "$compose_file" -p "$project_name" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_contracts <<'SQL'
select public.assert_true((select count(*)=1 from lautowork.automation_executions where idempotency_key='wave2-concurrent-idempotency'),'concurrent acceptance creates one execution');
select public.assert_true((select count(*)=1 from lautowork.automation_execution_events e join lautowork.automation_executions x on x.id=e.execution_id where x.idempotency_key='wave2-concurrent-idempotency' and e.sequence=1),'concurrent acceptance creates one accepted event');
select 'Wave 2 concurrent idempotency verification passed' as result;
SQL
