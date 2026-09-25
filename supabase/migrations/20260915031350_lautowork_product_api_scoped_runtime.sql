-- AW08: dedicated Product API transport identity; no BYPASSRLS or role inheritance.
-- Existing SECURITY DEFINER audited commands retain their org/audit guards.
-- Platform applies after the accepted sixteen-file package and verified backup.
-- migrate:up

-- Supabase has no superuser migration identity, and only a superuser may
-- restate SUPERUSER/REPLICATION/BYPASSRLS. Assert them instead, then drop LOGIN.
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'svc_lautowork_product_api'
              and (rolsuper or rolcreatedb or rolcreaterole or rolreplication or rolbypassrls)) then
    raise exception 'svc_lautowork_product_api must not hold superuser, createdb, createrole, replication, or bypassrls';
  end if;
end
$$;
alter role svc_lautowork_product_api nologin;
grant usage on schema public, lautowork to svc_lautowork_product_api;

create or replace function lautowork.assert_product_api_transport_authorized(p_target_org_id uuid)
returns void language plpgsql stable set search_path=lautowork,pg_temp as $$
declare
  claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb);
  headers jsonb:=coalesce(nullif(current_setting('request.headers',true),'')::jsonb,'{}'::jsonb);
  role_name text:=claims->>'role'; header_org text:=headers->>'x-link-org-id';
begin
  if coalesce(current_setting('lautowork.test_context',true),'off')='on' then
    role_name:=coalesce(role_name,nullif(current_setting('request.jwt.claim.role',true),''));
    header_org:=coalesce(header_org,nullif(current_setting('request.jwt.claim.org_id',true),''));
  end if;
  if role_name is distinct from 'svc_lautowork_product_api' or p_target_org_id is null or header_org is distinct from p_target_org_id::text then
    raise exception 'Product API organization authorization denied';
  end if;
end $$;

-- Retire only the Product API surface from legacy broad identities. The frozen
-- namespace contains public transport entrypoints, including unaudited predecessors.
do $$ declare f record; begin
 for f in select p.oid::regprocedure signature from pg_proc p
   join pg_namespace n on n.oid=p.pronamespace
   where n.nspname='public' and p.proname like 'linkautowork\_product\_%' escape '\'
 loop
   execute format('revoke all on function %s from public, service_role, svc_lautowork_runtime', f.signature);
 end loop;
end $$;

grant execute on function public.linkautowork_product_reserve_audit(text,text,text,text,text)
  to svc_lautowork_product_api;
grant execute on function public.linkautowork_product_finalize_audit(text,text,text,text,text,text)
  to svc_lautowork_product_api;
grant execute on function public.linkautowork_product_client_instances_audited(integer,text)
  to svc_lautowork_product_api;
grant execute on function public.linkautowork_product_client_portal_audited(text,integer,text)
  to svc_lautowork_product_api;
grant execute on function public.linkautowork_product_transition_instance_audited(uuid,text,text,text)
  to svc_lautowork_product_api;
grant execute on function public.linkautowork_product_create_order_audited(text,text)
  to svc_lautowork_product_api;
grant execute on function public.linkautowork_product_accept_terms_audited(uuid,text,text,text,text)
  to svc_lautowork_product_api;
grant execute on function public.linkautowork_product_create_subscription_audited(uuid,text)
  to svc_lautowork_product_api;
grant execute on function public.linkautowork_product_submit_configuration_audited(uuid,jsonb,text)
  to svc_lautowork_product_api;
grant execute on function public.linkautowork_product_request_provisioning_audited(uuid,text)
  to svc_lautowork_product_api;
grant execute on function public.linkautowork_product_compensate_provisioning_audited(uuid,text,text)
  to svc_lautowork_product_api;
grant execute on function public.linkautowork_product_create_support_request_audited(text,text,text)
  to svc_lautowork_product_api;
grant execute on function public.linkautowork_product_create_offering_audited(text,text,integer,text,text)
  to svc_lautowork_product_api;
grant execute on function public.linkautowork_product_update_offering_audited(text,text,integer,text,text)
  to svc_lautowork_product_api;
grant execute on function public.linkautowork_product_operator_records_audited(text,integer,text)
  to svc_lautowork_product_api;
grant execute on function public.linkautowork_product_operator_action_audited(text,uuid,text,text,text,integer,text)
  to svc_lautowork_product_api;
grant execute on function public.linkautowork_product_published_products(integer,text) to svc_lautowork_product_api;

-- Existing HMAC-verified webhook ingress retains its finite replay/order guard.
grant execute on function public.linkautowork_product_record_provider_event(text,text,uuid,timestamptz,bigint) to svc_lautowork_product_api;

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

  if claim_role in ('service_role', 'svc_lautowork_runtime') then
    return;
  end if;

  if platform.has_org_access(p_target_org_id, 'client_viewer') then
    return;
  end if;

  raise exception 'caller has no membership authority for target organization';
end;
$$;

-- Recovery is forward-fix only. This additive grant migration deletes no data.
