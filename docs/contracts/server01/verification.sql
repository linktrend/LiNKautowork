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
select public.assert_true(
  (
    select p.prosecdef
      from pg_proc p
      join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'lautowork'
       and p.proname = 'server01_package_status'
       and pg_get_function_identity_arguments(p.oid) = ''
  ),
  'package status is security definer'
);
select public.assert_true(
  not has_table_privilege('svc_lautowork_gateway', 'lautowork.server01_package_control', 'select'),
  'gateway has no direct package_control select'
);
select public.assert_true(
  not has_table_privilege('svc_lautowork_runtime_dispatch', 'lautowork.server01_package_control', 'select'),
  'runtime dispatch has no direct package_control select'
);
select public.assert_true((select relrowsecurity and relforcerowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='lautowork' and c.relname='server01_invocation_requests'), 'invocation RLS is forced');
select public.assert_true(not has_table_privilege('svc_lautowork_n8n','lautowork.server01_invocation_requests','select'), 'n8n cannot select invocation rows');
select public.assert_true(not has_function_privilege('svc_lautowork_product_api','lautowork.server01_accept_invocation(jsonb,text)','execute'), 'product api cannot accept invocations');
select public.assert_true(not has_function_privilege('public','lautowork.server01_accept_invocation(jsonb,text)','execute'), 'accept rpc is not public');
select public.assert_true(not has_table_privilege('svc_lautowork_migration_backup','lautowork.server01_invocation_requests','insert'), 'backup role cannot insert invocations');
select public.assert_true(has_table_privilege('svc_lautowork_migration_backup','lautowork.server01_invocation_requests','select'), 'backup role can select invocations');
select public.assert_true(has_function_privilege('svc_lautowork_gateway','lautowork.server01_accept_invocation(jsonb,text)','execute'), 'gateway can accept invocations');
select public.assert_true(has_function_privilege('svc_lautowork_runtime_dispatch','lautowork.server01_admit_callback(jsonb)','execute'), 'dispatch can admit callbacks');
select public.assert_true(
  not exists (
    select 1
      from pg_proc p
      join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'lautowork'
       and p.proname = 'server01_live_fingerprint'
       and pg_get_functiondef(p.oid) ilike '%information_schema.role_table_grants%'
  ),
  'fingerprint does not use role_table_grants'
);

do $$
declare
  v_fp text := lautowork.server01_live_fingerprint();
  v_status text := lautowork.server01_package_status();
  r name;
  n integer := 0;
begin
  if v_status is distinct from 'complete' then
    raise exception 'owner package status is %, expected complete', v_status;
  end if;
  for r in
    select fp.rolname
      from (
        select distinct pg_get_userbyid(ae.grantee) as rolname
          from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace
          cross join lateral aclexplode(coalesce(p.proacl, acldefault('f'::"char", p.proowner))) as ae
         where n.nspname = 'lautowork'
           and p.proname = 'server01_live_fingerprint'
           and pg_get_function_identity_arguments(p.oid) = ''
           and ae.privilege_type = 'EXECUTE'
           and ae.grantee <> 0
      ) fp
      join (
        select distinct pg_get_userbyid(ae.grantee) as rolname
          from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace
          cross join lateral aclexplode(coalesce(p.proacl, acldefault('f'::"char", p.proowner))) as ae
         where n.nspname = 'lautowork'
           and p.proname = 'server01_package_status'
           and pg_get_function_identity_arguments(p.oid) = ''
           and ae.privilege_type = 'EXECUTE'
           and ae.grantee <> 0
      ) st on st.rolname = fp.rolname
     order by 1
  loop
    n := n + 1;
    execute format('set local role %I', r);
    if lautowork.server01_live_fingerprint() is distinct from v_fp then
      raise exception 'fingerprint drifted for role %', r;
    end if;
    if lautowork.server01_package_status() is distinct from v_status then
      raise exception 'package status drifted for role %', r;
    end if;
    execute 'reset role';
  end loop;
  if n = 0 then
    raise exception 'no EXECUTE grantees found for both fingerprint and package status';
  end if;
end $$;
