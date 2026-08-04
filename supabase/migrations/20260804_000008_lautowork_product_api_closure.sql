-- Closes the durable Product API contract.  This migration replaces the early
-- WP-09 compatibility functions with finite, organization-bound commands.
-- migrate:up

alter table lautowork.product_orders add column if not exists offering_snapshot jsonb;
alter table lautowork.product_orders add column if not exists version integer not null default 1;
alter table lautowork.product_subscriptions add column if not exists version integer not null default 1;
alter table lautowork.product_configuration_submissions add column if not exists subscription_id uuid;
alter table lautowork.product_configuration_submissions add constraint product_configuration_subscription_org_fk foreign key (subscription_id,org_id) references lautowork.product_subscriptions(id,org_id) on delete restrict;
create unique index if not exists product_one_governed_subscription_per_order on lautowork.product_subscriptions(order_id);
create unique index if not exists product_one_provision_intent_per_subscription on lautowork.provisioning_requests(org_id,instance_id,requested_release_id) where request_ref like 'product-subscription:%';
create table if not exists lautowork.product_support_requests (
 id uuid primary key default gen_random_uuid(), org_id uuid not null references platform.organizations(id), subject text not null, message text not null,
 status text not null default 'open' check(status in ('open','acknowledged','resolved','closed')), version integer not null default 1,
 idempotency_key text not null, actor_ref text not null, created_at timestamptz not null default now(), unique(org_id,idempotency_key));
create table if not exists lautowork.product_resource_transition_history (
 id bigserial primary key, org_id uuid not null references platform.organizations(id), resource text not null, resource_id text not null, action text not null,
 actor_ref text not null, reason text not null, idempotency_key text not null, expected_version integer, from_state text, to_state text not null, correlation_ref text, created_at timestamptz not null default now(), unique(org_id,resource,idempotency_key));

create or replace function public.linkautowork_product_create_order(p_product_id text,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid:=lautowork.product_api_org(); o product_orders%rowtype; p automation_products%rowtype; d automation_definitions%rowtype; begin
 perform lautowork.assert_product_api_authorized(v_org); select * into p from automation_products where id=p_product_id::uuid and status='active';
 if not found then raise exception 'published offering not found'; end if; select * into d from automation_definitions where id=p.definition_id and org_id=p.org_id; if not found then raise exception 'published offering definition missing'; end if;
 insert into product_orders(org_id,product_ref,idempotency_key,offering_snapshot) values(v_org,p.id::text,p_idempotency_key,jsonb_build_object('offeringId',p.id,'offeringKey',p.offering_key,'displayName',p.display_name,'definitionId',p.definition_id,'offeringOrgId',p.org_id,'releaseRequirement','certified'))
 on conflict(org_id,idempotency_key) do update set product_ref=product_orders.product_ref returning * into o;
 if o.product_ref <> p_product_id then raise exception 'idempotency key was previously used for another order'; end if;
 return jsonb_build_object('id',o.id,'orgId',o.org_id,'status',o.status,'summary',o.product_ref,'version',o.version); end $$;

create or replace function public.linkautowork_product_accept_terms(p_order_id uuid,p_terms_version text,p_actor text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid:=lautowork.product_api_org(); existing product_terms_acceptances%rowtype; l commercial_lifecycles%rowtype; begin
 perform lautowork.assert_product_api_authorized(v_org); perform 1 from product_orders where id=p_order_id and org_id=v_org; if not found then raise exception 'order not found in organization'; end if;
 select * into existing from product_terms_acceptances where order_id=p_order_id and terms_version=p_terms_version;
 if found then return jsonb_build_object('orderId',p_order_id,'termsVersion',p_terms_version,'accepted',true,'replay',true); end if;
 insert into product_terms_acceptances(org_id,order_id,terms_version,accepted_by) values(v_org,p_order_id,p_terms_version,p_actor);
 select * into l from commercial_lifecycles where order_id=p_order_id for update;
 if l.state='initiated' then perform public.linkautowork_commercial_transition(p_order_id,'payment_not_required',p_actor); end if;
 if (select state from commercial_lifecycles where id=l.id) in ('payment_not_required','paid') then perform public.linkautowork_commercial_transition(p_order_id,'awaiting_configuration',p_actor); end if;
 return jsonb_build_object('orderId',p_order_id,'termsVersion',p_terms_version,'accepted',true,'replay',false); end $$;

create or replace function public.linkautowork_product_create_subscription(p_order_id uuid,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid:=lautowork.product_api_org(); s product_subscriptions%rowtype; o product_orders%rowtype; inst automation_instances%rowtype; begin
 perform lautowork.assert_product_api_authorized(v_org); select * into o from product_orders where id=p_order_id and org_id=v_org for update; if not found then raise exception 'order not found in organization'; end if;
 if not exists(select 1 from product_terms_acceptances where order_id=p_order_id) or not exists(select 1 from commercial_lifecycles where order_id=p_order_id and state='awaiting_configuration') then raise exception 'durable terms and commercial configuration gate are required'; end if;
 select ai.* into inst from automation_instances ai join automation_products p on p.definition_id=ai.definition_id where ai.org_id=v_org and ai.release_id is not null and ai.state in ('ready','active') and p.id=(o.offering_snapshot->>'offeringId')::uuid and p.status='active' order by ai.created_at limit 1;
 if not found then raise exception 'operator has not assigned an approved automation target'; end if;
 select * into s from product_subscriptions where order_id=p_order_id for update;
 if found then
   if s.idempotency_key<>p_idempotency_key then return jsonb_build_object('id',s.id,'orgId',s.org_id,'status',s.status,'summary',s.order_id,'version',s.version,'replay',true); end if;
   return jsonb_build_object('id',s.id,'orgId',s.org_id,'status',s.status,'summary',s.order_id,'version',s.version,'replay',true);
 end if;
 insert into product_subscriptions(org_id,order_id,status,automation_instance_id,requested_release_id,idempotency_key) values(v_org,p_order_id,'eligible',inst.id,inst.release_id,p_idempotency_key) returning * into s;
 return jsonb_build_object('id',s.id,'orgId',s.org_id,'status',s.status,'summary',s.order_id,'version',s.version,'replay',false); end $$;

drop function if exists public.linkautowork_product_submit_configuration(uuid,jsonb,text);
create function public.linkautowork_product_submit_configuration(p_subscription_id uuid,p_values jsonb,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid:=lautowork.product_api_org(); c product_configuration_submissions%rowtype; s product_subscriptions%rowtype; begin perform lautowork.assert_product_api_authorized(v_org);
 if lautowork.jsonb_has_secret_shaped_key(p_values) then raise exception 'credentials require operator-assisted binding'; end if;
 select * into s from product_subscriptions where org_id=v_org and id=p_subscription_id and status in ('eligible','provisioning') order by created_at desc limit 1; if not found then raise exception 'configuration requires eligible governed subscription'; end if;
 insert into product_configuration_submissions(org_id,instance_id,subscription_id,values,idempotency_key) values(v_org,s.automation_instance_id,s.id,p_values,p_idempotency_key) on conflict(org_id,idempotency_key) do update set values=product_configuration_submissions.values returning * into c;
 return jsonb_build_object('id',c.id,'orgId',c.org_id,'status',c.status,'summary','safe configuration submitted','version',1); end $$;

create or replace function public.linkautowork_product_request_provisioning(p_subscription_id uuid,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid:=lautowork.product_api_org(); s product_subscriptions%rowtype; result jsonb; v_ref text; pr provisioning_requests%rowtype; begin perform lautowork.assert_product_api_authorized(v_org); select * into s from product_subscriptions where id=p_subscription_id and org_id=v_org for update; if not found then raise exception 'subscription not found in organization'; end if;
 if not exists(select 1 from product_configuration_submissions where subscription_id=s.id and org_id=v_org) or not exists(select 1 from commercial_lifecycles where order_id=s.order_id and state in ('awaiting_configuration','provisioning')) then raise exception 'durable safe configuration and commercial lifecycle are required'; end if;
 v_ref:='product-subscription:'||s.id::text||':'||p_idempotency_key; insert into provisioning_requests(org_id,instance_id,requested_release_id,status,request_ref) values(v_org,s.automation_instance_id,s.requested_release_id,'requested',v_ref) on conflict(org_id,request_ref) do nothing; select * into pr from provisioning_requests where org_id=v_org and request_ref=v_ref; if pr.status='requested' then result:=public.linkautowork_begin_provisioning(v_org,v_ref); else result:=jsonb_build_object('requestId',pr.id,'status',pr.status); end if; update product_subscriptions set status=case when result->>'status'='completed' then 'active' else 'provisioning' end,version=version+1,updated_at=now() where id=s.id;
 if (result->>'status') in ('requested','provisioning','ready_for_review','completed') and (select state from commercial_lifecycles where order_id=s.order_id)='awaiting_configuration' then perform public.linkautowork_commercial_transition(s.order_id,'provisioning','product-api'); end if;
 return jsonb_build_object('id',result->>'requestId','orgId',v_org,'status',result->>'status','summary','WP-05 provisioning request','version',1); end $$;

create or replace function public.linkautowork_product_transition_instance(p_instance_id uuid,p_action text,p_reason text,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid:=lautowork.product_api_org(); i automation_instances%rowtype; target text; begin perform lautowork.assert_product_api_authorized(v_org); if p_action not in ('pause','resume') then raise exception 'invalid transition'; end if; select * into i from automation_instances where id=p_instance_id and org_id=v_org for update; if not found then raise exception 'instance not found in organization'; end if; target:=case when p_action='pause' then 'paused' else 'active' end; if exists(select 1 from product_resource_transition_history where org_id=v_org and resource='instances' and idempotency_key=p_idempotency_key) then return jsonb_build_object('id',i.id,'orgId',v_org,'state',i.state,'configurationStatus','operator_assisted_required','deploymentStatus','unchanged','health','healthy','executions','[]'::jsonb,'incidents','[]'::jsonb,'approvedOutputs','[]'::jsonb,'supportRequests','[]'::jsonb); end if; if (p_action='pause' and i.state not in ('ready','active')) or (p_action='resume' and i.state<>'paused') then raise exception 'invalid transition'; end if; update automation_instances set state=target,updated_at=now() where id=i.id; insert into product_resource_transition_history(org_id,resource,resource_id,action,actor_ref,reason,idempotency_key,from_state,to_state) values(v_org,'instances',i.id::text,p_action,'product-api',p_reason,p_idempotency_key,i.state,target); return jsonb_build_object('id',i.id,'orgId',v_org,'state',target,'configurationStatus','operator_assisted_required','deploymentStatus','unchanged','health','healthy','executions','[]'::jsonb,'incidents','[]'::jsonb,'approvedOutputs','[]'::jsonb,'supportRequests','[]'::jsonb); end $$;

create or replace function public.linkautowork_product_create_offering(p_name text,p_summary text,p_version integer,p_reason text,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$ begin raise exception 'offering creation requires the governed catalogue publication workflow'; end $$;
create or replace function public.linkautowork_product_update_offering(p_id text,p_summary text,p_expected_version integer,p_reason text,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$ begin raise exception 'offering update requires the governed catalogue publication workflow'; end $$;
create or replace function public.linkautowork_product_create_support_request(p_subject text,p_message text,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$ declare v_org uuid:=lautowork.product_api_org(); s product_support_requests%rowtype; begin perform lautowork.assert_product_api_authorized(v_org); insert into product_support_requests(org_id,subject,message,idempotency_key,actor_ref) values(v_org,p_subject,p_message,p_idempotency_key,'client') on conflict(org_id,idempotency_key) do update set subject=product_support_requests.subject returning * into s; return jsonb_build_object('id',s.id,'orgId',s.org_id,'status',s.status,'summary',s.subject,'version',s.version); end $$;

create or replace function public.linkautowork_product_record_provider_event(p_event_id text,p_event_type text,p_subscription_id uuid) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid:=lautowork.product_api_org(); s product_subscriptions%rowtype; seq bigint; target text; inserted boolean; begin perform lautowork.assert_product_api_authorized(v_org); select * into s from product_subscriptions where id=p_subscription_id and org_id=v_org for update; if not found then raise exception 'subscription not found in organization'; end if; insert into product_provider_event_receipts(org_id,subscription_id,provider_event_id,event_type) values(v_org,s.id,p_event_id,p_event_type) on conflict(provider_event_id) do nothing returning true into inserted; if not coalesce(inserted,false) then return jsonb_build_object('replay',true); end if; if p_event_type='payment.succeeded' then return jsonb_build_object('replay',false); end if; select provider_event_sequence+1 into seq from commercial_lifecycles where order_id=s.order_id for update; target:=case p_event_type when 'provisioning.completed' then 'active' else 'failed' end; perform public.linkautowork_commercial_transition(s.order_id,target,'provider:'||p_event_type,p_event_id,seq); update product_subscriptions set status=case target when 'active' then 'active' when 'failed' then 'failed' else status end,version=version+1 where id=s.id; return jsonb_build_object('replay',false); end $$;

-- All published Product API RPCs are private server-only routines.
do $$ declare f record; begin for f in select p.oid::regprocedure sig from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname like 'linkautowork_product_%' loop execute format('revoke all on function %s from public',f.sig); execute format('grant execute on function %s to service_role, svc_lautowork_runtime',f.sig); end loop; end $$;

-- migrate:down
drop function if exists public.linkautowork_product_transition_instance(uuid,text,text,text);
drop function if exists public.linkautowork_product_create_offering(text,text,integer,text,text);
drop function if exists public.linkautowork_product_update_offering(text,text,integer,text,text);
drop function if exists public.linkautowork_product_create_support_request(text,text,text);
drop table if exists lautowork.product_resource_transition_history;
drop table if exists lautowork.product_support_requests;
