-- AW08: dedicated Product API transport identity; no BYPASSRLS or role inheritance.
-- Existing SECURITY DEFINER audited commands retain their org/audit guards.
-- Platform applies after the accepted sixteen-file package and verified backup.
-- migrate:up

alter role svc_lautowork_product_api nologin nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
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
  if role_name is null or role_name not in ('service_role','svc_lautowork_runtime','svc_lautowork_product_api') or p_target_org_id is null or header_org is distinct from p_target_org_id::text then
    raise exception 'Product API organization authorization denied';
  end if;
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

-- Recovery is forward-fix only. This additive grant migration deletes no data.
