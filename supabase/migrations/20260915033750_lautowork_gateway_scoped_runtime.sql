-- AW08 dedicated gateway access to the existing durable v2 execution path.
-- No table writes, role inheritance, BYPASSRLS, provisioning or operator grants.
-- migrate:up
-- Supabase has no superuser migration identity, and only a superuser may
-- restate SUPERUSER/REPLICATION/BYPASSRLS. Assert them instead, then drop LOGIN.
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'svc_lautowork_gateway'
              and (rolsuper or rolcreatedb or rolcreaterole or rolreplication or rolbypassrls)) then
    raise exception 'svc_lautowork_gateway must not hold superuser, createdb, createrole, replication, or bypassrls';
  end if;
end
$$;
alter role svc_lautowork_gateway nologin;
grant usage on schema public, lautowork to svc_lautowork_gateway;

create or replace function lautowork.assert_command_authorized(p_target_org_id uuid)
returns void
language plpgsql
stable
set search_path = lautowork, pg_temp
as $$
declare
  claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  headers jsonb := coalesce(nullif(current_setting('request.headers', true), '')::jsonb, '{}'::jsonb);
  delegated_claims jsonb := coalesce(nullif(headers->>'x-link-request-claims', '')::jsonb, '{}'::jsonb);
  test_context boolean := coalesce(current_setting('lautowork.test_context', true), 'off') = 'on';
  claim_org_id text;
  claim_role text;
  transport_role text;
  header_org_id text;
begin
  claim_org_id := claims->>'org_id';
  claim_role := claims->>'role';
  transport_role := claim_role;
  header_org_id := headers->>'x-link-org-id';
  if test_context then
    claim_org_id := coalesce(claim_org_id, nullif(current_setting('request.jwt.claim.org_id', true), ''));
    claim_role := coalesce(claim_role, nullif(current_setting('request.jwt.claim.role', true), ''));
    transport_role := claim_role;
    header_org_id := coalesce(header_org_id, claim_org_id);
  end if;
  if transport_role = 'service_role'
     and delegated_claims->>'role' = 'service_role' then
    claim_org_id := coalesce(claim_org_id, delegated_claims->>'org_id');
  end if;
  -- Audited Product API provisioning calls the durable runtime internally.
  -- Its scoped transport delegates org authority only through the audit guard.
  if transport_role = 'svc_lautowork_product_api' then
    perform lautowork.assert_product_api_authorized(p_target_org_id);
    return;
  end if;
  if p_target_org_id is null or claim_org_id is distinct from p_target_org_id::text then
    raise exception 'command is not authorized for target organization';
  end if;
  if header_org_id is distinct from p_target_org_id::text then
    raise exception 'request organization header does not match authorized organization';
  end if;

  if claim_role in ('service_role', 'svc_lautowork_runtime', 'svc_lautowork_gateway') then
    return;
  end if;

  if platform.has_org_access(p_target_org_id, 'client_viewer') then
    return;
  end if;

  raise exception 'caller has no membership authority for target organization';
end;
$$;


grant execute on function public.linkautowork_resolve_bound_instance(uuid,text,text) to svc_lautowork_gateway;
grant execute on function public.linkautowork_accept_execution(uuid,uuid,uuid,uuid,uuid,text,text,text,text) to svc_lautowork_gateway;
grant execute on function public.linkautowork_record_execution_callback(uuid,uuid,text,text,integer,text,timestamptz,text,text) to svc_lautowork_gateway;
grant execute on function public.linkautowork_active_pause(uuid,text,uuid) to svc_lautowork_gateway;

-- These predecessor SECURITY DEFINER control functions inherited PUBLIC
-- execute. Keep their explicit legacy operator grants, but do not expose them
-- to the dedicated admission identity through PUBLIC.
revoke all on function public.linkautowork_active_killswitches() from public, svc_lautowork_gateway;
revoke all on function public.linkautowork_write_killswitch_event(uuid,text,text,text,text,jsonb) from public, svc_lautowork_gateway;
revoke all on function public.linkautowork_write_lifecycle_transition(uuid,text,text,text,boolean,jsonb,text) from public, svc_lautowork_gateway;
revoke all on function public.linkautowork_write_audit_run(uuid,text,text,text,text,integer,jsonb,jsonb,timestamptz) from public, svc_lautowork_gateway;

-- The predecessor global reader exposes every org. Scope its output before
-- allowing gateway hydration, and retain global kill-switch enforcement.
create or replace function public.linkautowork_gateway_active_killswitches(p_org_id uuid)
returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
begin
 perform lautowork.assert_command_authorized(p_org_id);
 return (select coalesce(jsonb_agg(item),'[]'::jsonb)
   from jsonb_array_elements(public.linkautowork_active_killswitches()) item
   where item->>'scope'='global' or item->>'org_id'=p_org_id::text);
end $$;
revoke all on function public.linkautowork_gateway_active_killswitches(uuid) from public;
grant execute on function public.linkautowork_gateway_active_killswitches(uuid) to svc_lautowork_gateway;
-- Recovery is forward-fix; use a verified backup for an isolated restoration.
