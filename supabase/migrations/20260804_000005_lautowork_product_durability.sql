-- WP-09 correction: durable commercial lifecycle state.  This is additive and
-- deliberately reuses WP-05 provisioning RPCs; it never stores payment or credentials.
-- migrate:up

create table if not exists lautowork.product_orders (
  id uuid primary key default gen_random_uuid(), org_id uuid not null references platform.organizations(id) on delete restrict,
  product_ref text not null check (char_length(product_ref) between 3 and 120), status text not null default 'pending_operator_review' check (status in ('pending_operator_review','approved','rejected','cancelled')),
  idempotency_key text not null check (char_length(idempotency_key) between 8 and 128), created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique(org_id,idempotency_key), unique(id,org_id)
);
-- The Product API is a trusted server boundary: it derives this header only
-- from a verified Platform identity, while PostgREST authenticates the server
-- with its service role. This prevents client-chosen organisation values from
-- becoming database authority and keeps the existing general runtime contract untouched.
create or replace function lautowork.assert_product_api_authorized(p_target_org_id uuid) returns void language plpgsql stable set search_path=lautowork,pg_temp as $$
declare claims jsonb:=coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb); headers jsonb:=coalesce(nullif(current_setting('request.headers',true),'')::jsonb,'{}'::jsonb); role_name text:=claims->>'role'; header_org text:=headers->>'x-link-org-id'; begin
  if coalesce(current_setting('lautowork.test_context',true),'off')='on' then role_name:=coalesce(role_name,nullif(current_setting('request.jwt.claim.role',true),'')); header_org:=coalesce(header_org,nullif(current_setting('request.jwt.claim.org_id',true),'')); end if;
  if role_name not in ('service_role','svc_lautowork_runtime') or header_org is distinct from p_target_org_id::text then raise exception 'Product API organization authorization denied'; end if;
end $$;
create or replace function lautowork.product_api_org() returns uuid language sql stable set search_path=lautowork,pg_temp as $$ select nullif(coalesce(current_setting('request.headers',true)::jsonb->>'x-link-org-id',current_setting('request.jwt.claim.org_id',true)),'')::uuid $$;
create table if not exists lautowork.product_terms_acceptances (
  id uuid primary key default gen_random_uuid(), org_id uuid not null references platform.organizations(id) on delete restrict,
  order_id uuid not null, terms_version text not null check (char_length(terms_version) between 1 and 128), accepted_by text not null check (char_length(accepted_by) between 1 and 200), accepted_at timestamptz not null default now(),
  foreign key(order_id,org_id) references lautowork.product_orders(id,org_id) on delete restrict, unique(order_id,terms_version)
);
create table if not exists lautowork.product_subscriptions (
  id uuid primary key default gen_random_uuid(), org_id uuid not null references platform.organizations(id) on delete restrict,
  order_id uuid not null, status text not null default 'pending_provisioning' check (status in ('pending_provisioning','eligible','provisioning','active','failed','compensation_pending','cancelled')),
  automation_instance_id uuid, requested_release_id uuid, idempotency_key text not null check (char_length(idempotency_key) between 8 and 128), created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  foreign key(order_id,org_id) references lautowork.product_orders(id,org_id) on delete restrict,
  foreign key(automation_instance_id,org_id) references lautowork.automation_instances(id,org_id) on delete restrict,
  foreign key(requested_release_id,org_id) references lautowork.automation_releases(id,org_id) on delete restrict,
  unique(org_id,idempotency_key), unique(id,org_id)
);
create table if not exists lautowork.product_configuration_submissions (
  id uuid primary key default gen_random_uuid(), org_id uuid not null references platform.organizations(id) on delete restrict, instance_id uuid not null,
  values jsonb not null check (not lautowork.jsonb_has_secret_shaped_key(values)), status text not null default 'operator_assisted_required' check(status='operator_assisted_required'),
  idempotency_key text not null check (char_length(idempotency_key) between 8 and 128), created_at timestamptz not null default now(),
  foreign key(instance_id,org_id) references lautowork.automation_instances(id,org_id) on delete restrict, unique(org_id,idempotency_key)
);
create table if not exists lautowork.product_provider_event_receipts (
  id uuid primary key default gen_random_uuid(), org_id uuid not null references platform.organizations(id) on delete restrict, subscription_id uuid not null,
  provider_event_id text not null check (char_length(provider_event_id) between 8 and 160), event_type text not null check(event_type in ('payment.succeeded','provisioning.completed','provisioning.failed')),
  received_at timestamptz not null default now(), foreign key(subscription_id,org_id) references lautowork.product_subscriptions(id,org_id) on delete restrict, unique(provider_event_id)
);
create table if not exists lautowork.product_api_audit_events (
  id uuid primary key default gen_random_uuid(), org_id uuid not null references platform.organizations(id) on delete restrict, actor text not null, resource text not null, action text not null,
  reason text not null, correlation_id text not null, outcome text not null check(outcome in ('allowed','denied')), created_at timestamptz not null default now(), unique(org_id,correlation_id,action,resource)
);

create or replace function public.linkautowork_product_create_order(p_product_id text,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare o product_orders%rowtype; v_org uuid:=nullif(coalesce(current_setting('request.headers',true)::jsonb->>'x-link-org-id',current_setting('request.jwt.claim.org_id',true)),'')::uuid; begin perform lautowork.assert_product_api_authorized(v_org); insert into product_orders(org_id,product_ref,idempotency_key) values(v_org,p_product_id,p_idempotency_key) on conflict(org_id,idempotency_key) do update set product_ref=product_orders.product_ref returning * into o; return jsonb_build_object('id',o.id,'orgId',o.org_id,'status',o.status,'summary',o.product_ref,'version',1); end $$;
create or replace function public.linkautowork_product_create_subscription(p_order_id uuid,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare s product_subscriptions%rowtype; v_org uuid; begin v_org:=lautowork.product_api_org(); perform lautowork.assert_product_api_authorized(v_org); perform 1 from product_orders where id=p_order_id and org_id=v_org; if not found then raise exception 'order not found in organization'; end if; insert into product_subscriptions(org_id,order_id,idempotency_key) values(v_org,p_order_id,p_idempotency_key) on conflict(org_id,idempotency_key) do update set order_id=product_subscriptions.order_id returning * into s; return jsonb_build_object('id',s.id,'orgId',s.org_id,'status',s.status,'summary',s.order_id,'version',1); end $$;
create or replace function public.linkautowork_product_accept_terms(p_order_id uuid,p_terms_version text,p_actor text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid; begin v_org:=lautowork.product_api_org(); perform lautowork.assert_product_api_authorized(v_org); perform 1 from product_orders where id=p_order_id and org_id=v_org; if not found then raise exception 'order not found in organization'; end if; insert into product_terms_acceptances(org_id,order_id,terms_version,accepted_by) values(v_org,p_order_id,p_terms_version,p_actor) on conflict(order_id,terms_version) do nothing; return jsonb_build_object('orderId',p_order_id,'termsVersion',p_terms_version,'accepted',true); end $$;
create or replace function public.linkautowork_product_submit_configuration(p_instance_id uuid,p_values jsonb,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare c product_configuration_submissions%rowtype; v_org uuid; begin v_org:=lautowork.product_api_org(); perform lautowork.assert_product_api_authorized(v_org); if lautowork.jsonb_has_secret_shaped_key(p_values) then raise exception 'credentials require operator-assisted binding'; end if; insert into product_configuration_submissions(org_id,instance_id,values,idempotency_key) values(v_org,p_instance_id,p_values,p_idempotency_key) on conflict(org_id,idempotency_key) do update set values=product_configuration_submissions.values returning * into c; return jsonb_build_object('id',c.id,'orgId',c.org_id,'status',c.status,'summary','configuration submitted','version',1); end $$;
create or replace function public.linkautowork_product_record_provider_event(p_event_id text,p_event_type text,p_subscription_id uuid) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid; inserted boolean; begin v_org:=lautowork.product_api_org(); perform lautowork.assert_product_api_authorized(v_org); perform 1 from product_subscriptions where id=p_subscription_id and org_id=v_org; if not found then raise exception 'subscription not found in organization'; end if; insert into product_provider_event_receipts(org_id,subscription_id,provider_event_id,event_type) values(v_org,p_subscription_id,p_event_id,p_event_type) on conflict(provider_event_id) do nothing returning true into inserted; return jsonb_build_object('replay',not coalesce(inserted,false)); end $$;
create or replace function public.linkautowork_product_request_provisioning(p_subscription_id uuid,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare s product_subscriptions%rowtype; p provisioning_requests%rowtype; v_request_ref text; result jsonb; v_org uuid; begin v_org:=lautowork.product_api_org(); perform lautowork.assert_product_api_authorized(v_org); select * into strict s from product_subscriptions where id=p_subscription_id and org_id=v_org for update; if s.status not in ('eligible','provisioning','active') then raise exception 'subscription is not eligible for provisioning'; end if; if s.automation_instance_id is null or s.requested_release_id is null then raise exception 'operator has not assigned an approved automation target'; end if; v_request_ref:='product-subscription:'||s.id::text||':'||p_idempotency_key; insert into provisioning_requests(org_id,instance_id,requested_release_id,status,request_ref) values(v_org,s.automation_instance_id,s.requested_release_id,'requested',v_request_ref) on conflict(org_id,request_ref) do nothing; select * into strict p from provisioning_requests where org_id=v_org and request_ref=v_request_ref; if p.status='requested' then result:=public.linkautowork_begin_provisioning(v_org,v_request_ref); else result:=jsonb_build_object('requestId',p.id,'orgId',p.org_id,'instanceId',p.instance_id,'releaseId',p.requested_release_id,'requestRef',p.request_ref,'status',p.status); end if; update product_subscriptions set status=case when result->>'status'='completed' then 'active' else 'provisioning' end,updated_at=now() where id=s.id; return jsonb_build_object('id',result->>'requestId','orgId',v_org,'status',result->>'status','summary','WP-05 provisioning request','version',1); end $$;
create or replace function public.linkautowork_product_compensate_provisioning(p_subscription_id uuid,p_reason text,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare s product_subscriptions%rowtype; v_org uuid; begin v_org:=lautowork.product_api_org(); perform lautowork.assert_product_api_authorized(v_org); select * into strict s from product_subscriptions where id=p_subscription_id and org_id=v_org for update; if s.status not in ('failed','provisioning') then raise exception 'subscription has no compensable provisioning state'; end if; update product_subscriptions set status='compensation_pending',updated_at=now() where id=s.id; return jsonb_build_object('id',s.id,'orgId',v_org,'status','compensation_pending','summary','compensation requires operator evidence','version',1); end $$;
create or replace function public.linkautowork_product_write_audit(p_actor text,p_resource text,p_action text,p_reason text,p_correlation_id text,p_outcome text) returns void language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid; begin v_org:=lautowork.product_api_org(); perform lautowork.assert_product_api_authorized(v_org); insert into product_api_audit_events(org_id,actor,resource,action,reason,correlation_id,outcome) values(v_org,p_actor,p_resource,p_action,p_reason,p_correlation_id,p_outcome) on conflict(org_id,correlation_id,action,resource) do nothing; end $$;
do $$ declare f record; begin for f in select p.oid::regprocedure sig from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname like 'linkautowork_product_%' loop execute format('revoke all on function %s from public',f.sig); execute format('grant execute on function %s to service_role, svc_lautowork_runtime',f.sig); end loop; end $$;

-- migrate:down
drop function if exists public.linkautowork_product_write_audit(text,text,text,text,text,text);
drop function if exists public.linkautowork_product_compensate_provisioning(uuid,text,text);
drop function if exists public.linkautowork_product_request_provisioning(uuid,text);
drop function if exists public.linkautowork_product_record_provider_event(text,text,uuid);
drop function if exists public.linkautowork_product_submit_configuration(uuid,jsonb,text);
drop function if exists public.linkautowork_product_create_subscription(uuid,text);
drop function if exists public.linkautowork_product_accept_terms(uuid,text,text);
drop function if exists public.linkautowork_product_create_order(text,text);
drop function if exists lautowork.product_api_org();
drop function if exists lautowork.assert_product_api_authorized(uuid);
drop table if exists lautowork.product_api_audit_events;
drop table if exists lautowork.product_provider_event_receipts;
drop table if exists lautowork.product_configuration_submissions;
drop table if exists lautowork.product_subscriptions;
drop table if exists lautowork.product_terms_acceptances;
drop table if exists lautowork.product_orders;
