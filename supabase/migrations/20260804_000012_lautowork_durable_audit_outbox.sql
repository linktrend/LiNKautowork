-- Wave 3 blocker 5: Product API privileged access and mutation audit must fail closed.
--
-- A request reserves one durable outbox row before its handler runs.  The row is
-- completed only after the handler has produced its result.  A failed finalizer
-- therefore leaves repairable evidence instead of turning an operation into an
-- unaudited success.  The unique correlation key makes retries and restarts
-- idempotent.
-- migrate:up

create table if not exists lautowork.product_api_audit_outbox (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  actor text not null check (char_length(actor) between 1 and 200),
  resource text not null check (char_length(resource) between 1 and 200),
  action text not null check (char_length(action) between 1 and 200),
  reason text not null check (char_length(reason) between 3 and 280),
  correlation_id text not null check (char_length(correlation_id) between 8 and 128),
  status text not null default 'pending' check (status in ('pending','completed')),
  outcome text check (outcome is null or outcome in ('allowed','denied')),
  reserved_at timestamptz not null default now(),
  finalized_at timestamptz,
  unique (org_id, correlation_id, action, resource)
);

create index if not exists idx_lautowork_product_api_audit_outbox_pending
  on lautowork.product_api_audit_outbox (reserved_at)
  where status = 'pending';

create or replace function lautowork.assert_product_api_audit_reserved()
returns void language plpgsql stable set search_path=lautowork,pg_temp as $$
declare
  headers jsonb := coalesce(nullif(current_setting('request.headers', true), '')::jsonb, '{}'::jsonb);
  v_org uuid := lautowork.product_api_org();
  v_actor text := coalesce(headers->>'x-link-audit-actor', nullif(current_setting('lautowork.product_api_audit_actor', true), ''));
  v_resource text := coalesce(headers->>'x-link-audit-resource', nullif(current_setting('lautowork.product_api_audit_resource', true), ''));
  v_action text := coalesce(headers->>'x-link-audit-action', nullif(current_setting('lautowork.product_api_audit_action', true), ''));
  v_reason text := coalesce(headers->>'x-link-audit-reason', nullif(current_setting('lautowork.product_api_audit_reason', true), ''));
  v_correlation text := coalesce(headers->>'x-link-audit-correlation', nullif(current_setting('lautowork.product_api_audit_correlation', true), ''));
begin
  if not exists (
    select 1 from product_api_audit_outbox
    where org_id = v_org
      and actor = v_actor
      and resource = v_resource
      and action = v_action
      and reason = v_reason
      and correlation_id = v_correlation
      and status in ('pending','completed')
  ) then
    raise exception 'Product API audit reservation is required';
  end if;
end $$;

-- Existing Product API RPCs already call this organization/role guard.  When
-- invoked through PostgREST with the audit context headers, the guard now also
-- requires the matching durable reservation.  Direct SQL fixture sessions keep
-- their existing setup path; production PostgREST calls cannot omit the lease.
-- The signed provider-webhook RPC is a separate bounded ingress with its own
-- HMAC/replay/order contract and uses the explicit provider-webhook context.
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
  if role_name not in ('service_role','svc_lautowork_runtime') or header_org is distinct from p_target_org_id::text then
    raise exception 'Product API organization authorization denied';
  end if;
end $$;

create or replace function lautowork.assert_product_api_authorized(p_target_org_id uuid)
returns void language plpgsql stable set search_path=lautowork,pg_temp as $$
declare
  audit_resource text:=coalesce(nullif(current_setting('request.headers',true),'')::jsonb->>'x-link-audit-resource', nullif(current_setting('lautowork.product_api_audit_resource',true),''));
begin
  perform lautowork.assert_product_api_transport_authorized(p_target_org_id);
  -- PostgREST supplies the JWT claims JSON.  Existing disposable SQL fixtures
  -- use the individual request.jwt.claim.* settings and remain migration-testable.
  if nullif(current_setting('request.jwt.claims', true), '') is not null
     and coalesce(audit_resource, '') <> 'provider-webhook' then
    perform lautowork.assert_product_api_audit_reserved();
  end if;
end $$;

-- The legacy Product API routines remain as private implementation details.
-- These audited entry points are the only client/operator Product API RPCs
-- granted to runtime roles; each verifies the transport and durable lease
-- before delegating to the finite implementation.
create or replace function public.linkautowork_product_client_instances_audited(
  p_limit integer, p_cursor text
) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
begin
  perform lautowork.assert_product_api_authorized(lautowork.product_api_org());
  return public.linkautowork_product_client_instances(p_limit, p_cursor);
end $$;

create or replace function public.linkautowork_product_client_portal_audited(
  p_area text, p_limit integer, p_cursor text
) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
begin
  perform lautowork.assert_product_api_authorized(lautowork.product_api_org());
  return public.linkautowork_product_client_portal(p_area, p_limit, p_cursor);
end $$;

create or replace function public.linkautowork_product_transition_instance_audited(
  p_instance_id uuid, p_action text, p_reason text, p_idempotency_key text
) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
begin
  perform lautowork.assert_product_api_authorized(lautowork.product_api_org());
  return public.linkautowork_product_transition_instance(p_instance_id, p_action, p_reason, p_idempotency_key);
end $$;

create or replace function public.linkautowork_product_create_order_audited(
  p_product_id text, p_idempotency_key text
) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
begin
  perform lautowork.assert_product_api_authorized(lautowork.product_api_org());
  return public.linkautowork_product_create_order(p_product_id, p_idempotency_key);
end $$;

create or replace function public.linkautowork_product_accept_terms_audited(
  p_order_id uuid, p_terms_document_id text, p_terms_version text, p_terms_digest text, p_actor text
) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
begin
  perform lautowork.assert_product_api_authorized(lautowork.product_api_org());
  return public.linkautowork_product_accept_terms(p_order_id, p_terms_document_id, p_terms_version, p_terms_digest, p_actor);
end $$;

create or replace function public.linkautowork_product_create_subscription_audited(
  p_order_id uuid, p_idempotency_key text
) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
begin
  perform lautowork.assert_product_api_authorized(lautowork.product_api_org());
  return public.linkautowork_product_create_subscription(p_order_id, p_idempotency_key);
end $$;

create or replace function public.linkautowork_product_submit_configuration_audited(
  p_subscription_id uuid, p_values jsonb, p_idempotency_key text
) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
begin
  perform lautowork.assert_product_api_authorized(lautowork.product_api_org());
  return public.linkautowork_product_submit_configuration(p_subscription_id, p_values, p_idempotency_key);
end $$;

create or replace function public.linkautowork_product_request_provisioning_audited(
  p_subscription_id uuid, p_idempotency_key text
) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
begin
  perform lautowork.assert_product_api_authorized(lautowork.product_api_org());
  return public.linkautowork_product_request_provisioning(p_subscription_id, p_idempotency_key);
end $$;

create or replace function public.linkautowork_product_compensate_provisioning_audited(
  p_subscription_id uuid, p_reason text, p_idempotency_key text
) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
begin
  perform lautowork.assert_product_api_authorized(lautowork.product_api_org());
  return public.linkautowork_product_compensate_provisioning(p_subscription_id, p_reason, p_idempotency_key);
end $$;

create or replace function public.linkautowork_product_create_support_request_audited(
  p_subject text, p_message text, p_idempotency_key text
) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
begin
  perform lautowork.assert_product_api_authorized(lautowork.product_api_org());
  return public.linkautowork_product_create_support_request(p_subject, p_message, p_idempotency_key);
end $$;

create or replace function public.linkautowork_product_create_offering_audited(
  p_name text, p_summary text, p_version integer, p_reason text, p_idempotency_key text
) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
begin
  perform lautowork.assert_product_api_authorized(lautowork.product_api_org());
  return public.linkautowork_product_create_offering(p_name, p_summary, p_version, p_reason, p_idempotency_key);
end $$;

create or replace function public.linkautowork_product_update_offering_audited(
  p_id text, p_summary text, p_expected_version integer, p_reason text, p_idempotency_key text
) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
begin
  perform lautowork.assert_product_api_authorized(lautowork.product_api_org());
  return public.linkautowork_product_update_offering(p_id, p_summary, p_expected_version, p_reason, p_idempotency_key);
end $$;

create or replace function public.linkautowork_product_operator_records_audited(
  p_resource text, p_limit integer, p_cursor text
) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
begin
  perform lautowork.assert_product_api_authorized(lautowork.product_api_org());
  return public.linkautowork_product_operator_records(p_resource, p_limit, p_cursor);
end $$;

create or replace function public.linkautowork_product_operator_action_audited(
  p_resource text, p_id uuid, p_action text, p_reason text, p_idempotency_key text,
  p_expected_version integer, p_actor text
) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare
  headers jsonb := coalesce(nullif(current_setting('request.headers', true), '')::jsonb, '{}'::jsonb);
begin
  perform lautowork.assert_product_api_authorized(lautowork.product_api_org());
  if p_actor is distinct from headers->>'x-link-audit-actor' then
    raise exception 'operator actor does not match audit reservation';
  end if;
  perform set_config('lautowork.product_api_audit_actor', headers->>'x-link-audit-actor', true);
  perform set_config('lautowork.product_api_audit_resource', headers->>'x-link-audit-resource', true);
  perform set_config('lautowork.product_api_audit_action', headers->>'x-link-audit-action', true);
  perform set_config('lautowork.product_api_audit_reason', headers->>'x-link-audit-reason', true);
  perform set_config('lautowork.product_api_audit_correlation', headers->>'x-link-audit-correlation', true);
  return public.linkautowork_product_operator_action(p_resource, p_id, p_action, p_reason, p_idempotency_key, p_expected_version, p_actor);
end $$;

create or replace function public.linkautowork_product_reserve_audit(
  p_actor text,
  p_resource text,
  p_action text,
  p_reason text,
  p_correlation_id text
) returns jsonb
language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare
  v_org uuid := lautowork.product_api_org();
  v_existing product_api_audit_outbox%rowtype;
begin
  perform lautowork.assert_product_api_transport_authorized(v_org);
  if coalesce(char_length(p_actor), 0) not between 1 and 200
     or coalesce(char_length(p_resource), 0) not between 1 and 200
     or coalesce(char_length(p_action), 0) not between 1 and 200
     or coalesce(char_length(p_reason), 0) not between 3 and 280
     or coalesce(char_length(p_correlation_id), 0) not between 8 and 128 then
    raise exception 'invalid audit reservation';
  end if;

  insert into product_api_audit_outbox(org_id, actor, resource, action, reason, correlation_id)
    values (v_org, p_actor, p_resource, p_action, p_reason, p_correlation_id)
    on conflict (org_id, correlation_id, action, resource) do nothing;
  select * into strict v_existing
    from product_api_audit_outbox
    where org_id = v_org and correlation_id = p_correlation_id
      and action = p_action and resource = p_resource
    for update;
  if v_existing.actor <> p_actor or v_existing.reason <> p_reason then
    raise exception 'audit correlation was reused with different actor or reason';
  end if;
  return jsonb_build_object('auditId', v_existing.id, 'orgId', v_existing.org_id, 'status', v_existing.status);
end $$;

create or replace function public.linkautowork_product_finalize_audit(
  p_actor text,
  p_resource text,
  p_action text,
  p_reason text,
  p_correlation_id text,
  p_outcome text
) returns jsonb
language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare
  v_org uuid := lautowork.product_api_org();
  v_reservation product_api_audit_outbox%rowtype;
  v_event product_api_audit_events%rowtype;
begin
  perform lautowork.assert_product_api_authorized(v_org);
  if p_outcome not in ('allowed','denied') then raise exception 'invalid audit outcome'; end if;
  select * into strict v_reservation
    from product_api_audit_outbox
    where org_id = v_org and correlation_id = p_correlation_id
      and action = p_action and resource = p_resource
    for update;
  if v_reservation.actor <> p_actor or v_reservation.reason <> p_reason then
    raise exception 'audit reservation identity mismatch';
  end if;
  if v_reservation.status = 'completed' then
    if v_reservation.outcome <> p_outcome then raise exception 'audit outcome mismatch'; end if;
    return jsonb_build_object('auditId', v_reservation.id, 'orgId', v_org, 'status', 'completed', 'outcome', p_outcome);
  end if;

  select * into v_event from product_api_audit_events
    where org_id = v_org and correlation_id = p_correlation_id
      and action = p_action and resource = p_resource;
  if found then
    if v_event.outcome <> p_outcome then raise exception 'audit outcome mismatch'; end if;
  else
    insert into product_api_audit_events(org_id, actor, resource, action, reason, correlation_id, outcome)
      values (v_org, p_actor, p_resource, p_action, p_reason, p_correlation_id, p_outcome);
  end if;
  update product_api_audit_outbox
    set status = 'completed', outcome = p_outcome, finalized_at = now()
    where id = v_reservation.id;
  return jsonb_build_object('auditId', v_reservation.id, 'orgId', v_org, 'status', 'completed', 'outcome', p_outcome);
end $$;

-- Legacy direct client/operator routines and the compatibility fire-and-forget
-- writer are no longer application authorities. Keep their definitions for
-- rollback compatibility, but remove runtime execution so only audited entry
-- points are reachable through PostgREST.
do $$ declare f record; begin
  for f in
    select p.oid::regprocedure sig
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.proname in (
      'linkautowork_product_client_instances',
      'linkautowork_product_client_portal',
      'linkautowork_product_transition_instance',
      'linkautowork_product_create_order',
      'linkautowork_product_accept_terms',
      'linkautowork_product_create_subscription',
      'linkautowork_product_submit_configuration',
      'linkautowork_product_request_provisioning',
      'linkautowork_product_compensate_provisioning',
      'linkautowork_product_create_support_request',
      'linkautowork_product_create_offering',
      'linkautowork_product_update_offering',
      'linkautowork_product_operator_records',
      'linkautowork_product_operator_action'
    )
  loop
    execute format('revoke all on function %s from public, service_role, svc_lautowork_runtime', f.sig);
  end loop;
end $$;
revoke all on function public.linkautowork_product_write_audit(text,text,text,text,text,text)
  from public, service_role, svc_lautowork_runtime;
revoke all on table lautowork.product_api_audit_outbox from public, service_role, svc_lautowork_runtime;
do $$ declare f record; begin
  for f in select p.oid::regprocedure sig from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.proname in (
      'linkautowork_product_client_instances_audited',
      'linkautowork_product_client_portal_audited',
      'linkautowork_product_transition_instance_audited',
      'linkautowork_product_create_order_audited',
      'linkautowork_product_accept_terms_audited',
      'linkautowork_product_create_subscription_audited',
      'linkautowork_product_submit_configuration_audited',
      'linkautowork_product_request_provisioning_audited',
      'linkautowork_product_compensate_provisioning_audited',
      'linkautowork_product_create_support_request_audited',
      'linkautowork_product_create_offering_audited',
      'linkautowork_product_update_offering_audited',
      'linkautowork_product_operator_records_audited',
      'linkautowork_product_operator_action_audited'
    )
  loop execute format('revoke all on function %s from public', f.sig); end loop;
end $$;
grant execute on function public.linkautowork_product_reserve_audit(text,text,text,text,text)
  to service_role, svc_lautowork_runtime;
grant execute on function public.linkautowork_product_finalize_audit(text,text,text,text,text,text)
  to service_role, svc_lautowork_runtime;
grant execute on function public.linkautowork_product_client_instances_audited(integer,text)
  to service_role, svc_lautowork_runtime;
grant execute on function public.linkautowork_product_client_portal_audited(text,integer,text)
  to service_role, svc_lautowork_runtime;
grant execute on function public.linkautowork_product_transition_instance_audited(uuid,text,text,text)
  to service_role, svc_lautowork_runtime;
grant execute on function public.linkautowork_product_create_order_audited(text,text)
  to service_role, svc_lautowork_runtime;
grant execute on function public.linkautowork_product_accept_terms_audited(uuid,text,text,text,text)
  to service_role, svc_lautowork_runtime;
grant execute on function public.linkautowork_product_create_subscription_audited(uuid,text)
  to service_role, svc_lautowork_runtime;
grant execute on function public.linkautowork_product_submit_configuration_audited(uuid,jsonb,text)
  to service_role, svc_lautowork_runtime;
grant execute on function public.linkautowork_product_request_provisioning_audited(uuid,text)
  to service_role, svc_lautowork_runtime;
grant execute on function public.linkautowork_product_compensate_provisioning_audited(uuid,text,text)
  to service_role, svc_lautowork_runtime;
grant execute on function public.linkautowork_product_create_support_request_audited(text,text,text)
  to service_role, svc_lautowork_runtime;
grant execute on function public.linkautowork_product_create_offering_audited(text,text,integer,text,text)
  to service_role, svc_lautowork_runtime;
grant execute on function public.linkautowork_product_update_offering_audited(text,text,integer,text,text)
  to service_role, svc_lautowork_runtime;
grant execute on function public.linkautowork_product_operator_records_audited(text,integer,text)
  to service_role, svc_lautowork_runtime;
grant execute on function public.linkautowork_product_operator_action_audited(text,uuid,text,text,text,integer,text)
  to service_role, svc_lautowork_runtime;

-- migrate:down
drop function if exists public.linkautowork_product_finalize_audit(text,text,text,text,text,text);
drop function if exists public.linkautowork_product_reserve_audit(text,text,text,text,text);
drop function if exists public.linkautowork_product_operator_action_audited(text,uuid,text,text,text,integer,text);
drop function if exists public.linkautowork_product_operator_records_audited(text,integer,text);
drop function if exists public.linkautowork_product_update_offering_audited(text,text,integer,text,text);
drop function if exists public.linkautowork_product_create_offering_audited(text,text,integer,text,text);
drop function if exists public.linkautowork_product_create_support_request_audited(text,text,text);
drop function if exists public.linkautowork_product_compensate_provisioning_audited(uuid,text,text);
drop function if exists public.linkautowork_product_request_provisioning_audited(uuid,text);
drop function if exists public.linkautowork_product_submit_configuration_audited(uuid,jsonb,text);
drop function if exists public.linkautowork_product_create_subscription_audited(uuid,text);
drop function if exists public.linkautowork_product_accept_terms_audited(uuid,text,text,text,text);
drop function if exists public.linkautowork_product_create_order_audited(text,text);
drop function if exists public.linkautowork_product_transition_instance_audited(uuid,text,text,text);
drop function if exists public.linkautowork_product_client_portal_audited(text,integer,text);
drop function if exists public.linkautowork_product_client_instances_audited(integer,text);
drop function if exists lautowork.assert_product_api_audit_reserved();
drop table if exists lautowork.product_api_audit_outbox;
create or replace function lautowork.assert_product_api_authorized(p_target_org_id uuid)
returns void language plpgsql stable set search_path=lautowork,pg_temp as $$
declare claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb); headers jsonb:=coalesce(nullif(current_setting('request.headers',true),'')::jsonb,'{}'::jsonb); role_name text:=claims->>'role'; header_org text:=headers->>'x-link-org-id'; begin
  if coalesce(current_setting('lautowork.test_context',true),'off')='on' then role_name:=coalesce(role_name,nullif(current_setting('request.jwt.claim.role',true),'')); header_org:=coalesce(header_org,nullif(current_setting('request.jwt.claim.org_id',true),'')); end if;
  if role_name not in ('service_role','svc_lautowork_runtime') or header_org is distinct from p_target_org_id::text then raise exception 'Product API organization authorization denied'; end if;
end $$;
drop function if exists lautowork.assert_product_api_transport_authorized(uuid);
do $$ declare f record; begin
  for f in
    select p.oid::regprocedure sig
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.proname in (
      'linkautowork_product_client_instances',
      'linkautowork_product_client_portal',
      'linkautowork_product_transition_instance',
      'linkautowork_product_create_order',
      'linkautowork_product_accept_terms',
      'linkautowork_product_create_subscription',
      'linkautowork_product_submit_configuration',
      'linkautowork_product_request_provisioning',
      'linkautowork_product_compensate_provisioning',
      'linkautowork_product_create_support_request',
      'linkautowork_product_create_offering',
      'linkautowork_product_update_offering',
      'linkautowork_product_operator_records',
      'linkautowork_product_operator_action',
      'linkautowork_product_write_audit'
    )
  loop
    execute format('grant execute on function %s to service_role, svc_lautowork_runtime', f.sig);
  end loop;
end $$;
