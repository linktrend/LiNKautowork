\set ON_ERROR_STOP on

create or replace function public.assert_true(condition boolean, message text)
returns void language plpgsql as $$
begin
  if not condition then raise exception 'assertion failed: %', message; end if;
end;
$$;

select public.assert_true(exists(select 1 from pg_roles where rolname='svc_lautowork_gateway'), 'gateway role exists');
select public.assert_true(exists(select 1 from pg_roles where rolname='svc_lautowork_product_api'), 'product api role exists');
select public.assert_true(exists(select 1 from pg_roles where rolname='svc_lautowork_runtime_dispatch'), 'runtime dispatch role exists');
select public.assert_true(exists(select 1 from pg_roles where rolname='svc_lautowork_n8n'), 'n8n role exists');
select public.assert_true(exists(select 1 from pg_roles where rolname='svc_observer'), 'observer role exists');
select public.assert_true(exists(select 1 from pg_roles where rolname='svc_lautowork_migration_backup'), 'migration backup role exists');
select public.assert_true(lautowork.server01_package_status() = 'complete', 'package status is complete');
select public.assert_true(lautowork.server01_live_fingerprint() ~ '^sha256:[a-f0-9]{64}$', 'live fingerprint is sha256');
select public.assert_true((select relrowsecurity and relforcerowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='lautowork' and c.relname='server01_invocation_requests'), 'invocation RLS is forced');
select public.assert_true(not has_table_privilege('svc_lautowork_n8n','lautowork.server01_invocation_requests','select'), 'n8n cannot select invocation rows');
select public.assert_true(not has_function_privilege('svc_lautowork_product_api','lautowork.server01_accept_invocation(jsonb,text)','execute'), 'product api cannot accept invocations');
select public.assert_true(not has_function_privilege('public','lautowork.server01_accept_invocation(jsonb,text)','execute'), 'accept rpc is not public');
select public.assert_true(not has_table_privilege('svc_lautowork_migration_backup','lautowork.server01_invocation_requests','insert'), 'backup role cannot insert invocations');
select public.assert_true(has_table_privilege('svc_lautowork_migration_backup','lautowork.server01_invocation_requests','select'), 'backup role can select invocations');
select public.assert_true(has_function_privilege('svc_lautowork_gateway','lautowork.server01_accept_invocation(jsonb,text)','execute'), 'gateway can accept invocations');
select public.assert_true(has_function_privilege('svc_lautowork_runtime_dispatch','lautowork.server01_admit_callback(jsonb)','execute'), 'dispatch can admit callbacks');
