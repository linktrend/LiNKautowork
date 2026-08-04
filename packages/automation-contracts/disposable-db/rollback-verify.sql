\set ON_ERROR_STOP on

create or replace function public.assert_true(condition boolean, message text)
returns void language plpgsql as $$
begin
  if not condition then raise exception 'assertion failed: %', message; end if;
end;
$$;

select public.assert_true(
  not exists (
    select 1 from pg_tables where schemaname = 'lautowork' and tablename = 'automation_definitions'
  ),
  'disposable rollback removes automation control tables'
);

select public.assert_true(
  not exists (
    select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where (n.nspname = 'public' and p.proname like 'linkautowork_%automation_release')
       or (n.nspname = 'public' and p.proname in ('linkautowork_append_execution_event', 'linkautowork_append_approval_decision'))
       or (n.nspname = 'lautowork' and p.proname in ('assert_command_authorized', 'assert_instance_lineage', 'assert_provisioning_request_lineage', 'assert_deployment_lineage', 'assert_execution_lineage'))
  ),
  'disposable rollback removes privileged RPCs and trigger helpers'
);

select 'WP-04 disposable rollback verification passed' as result;
