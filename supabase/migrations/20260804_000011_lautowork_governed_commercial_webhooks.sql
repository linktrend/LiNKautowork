-- Wave 3 blockers 3 and 4: immutable commercial publication snapshots and
-- durable, ordered provider lifecycle events. This is pre-VPS only: it stores
-- no payment instrument, credential, or provider secret and never charges.
-- migrate:up

create table if not exists lautowork.product_offering_publications (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  product_id uuid not null,
  offering_version integer not null check (offering_version > 0),
  release_id uuid not null,
  release_version text not null,
  release_digest text not null check (release_digest ~ '^sha256:[a-f0-9]{64}$'),
  workflow_digest text not null check (workflow_digest ~ '^sha256:[a-f0-9]{64}$'),
  terms_document_id text not null check (char_length(terms_document_id) between 1 and 160),
  terms_version text not null check (char_length(terms_version) between 1 and 128),
  terms_digest text not null check (terms_digest ~ '^sha256:[a-f0-9]{64}$'),
  commercial_descriptor jsonb not null check (
    jsonb_typeof(commercial_descriptor) = 'object'
    and commercial_descriptor->>'chargesMoney' = 'false'
    and commercial_descriptor->>'paymentCollection' = 'none'
  ),
  configuration_schema_version text not null check (char_length(configuration_schema_version) between 1 and 64),
  configuration_schema jsonb not null check (
    jsonb_typeof(configuration_schema) = 'object'
    and not lautowork.jsonb_has_secret_shaped_key(configuration_schema)
  ),
  status text not null check (status in ('published', 'retired')),
  published_at timestamptz not null default now(),
  retired_at timestamptz,
  created_at timestamptz not null default now(),
  unique (product_id, offering_version),
  unique (id, org_id),
  foreign key (product_id, org_id) references lautowork.automation_products(id, org_id) on delete restrict,
  foreign key (release_id, org_id) references lautowork.automation_releases(id, org_id) on delete restrict
);

create index if not exists idx_lautowork_product_publications_active
  on lautowork.product_offering_publications (product_id, offering_version desc)
  where status = 'published';

create or replace function lautowork.assert_product_offering_publication()
returns trigger language plpgsql set search_path=lautowork,pg_temp as $$
declare product_definition_id uuid; release_definition_id uuid; release_package_digest text; release_workflow_digest text; release_lifecycle text;
begin
  if tg_op = 'DELETE' then
    raise exception 'offering publication is immutable';
  end if;
  if tg_op = 'UPDATE' and (
    new.org_id is distinct from old.org_id or new.product_id is distinct from old.product_id
    or new.offering_version is distinct from old.offering_version or new.release_id is distinct from old.release_id
    or new.release_version is distinct from old.release_version or new.release_digest is distinct from old.release_digest
    or new.workflow_digest is distinct from old.workflow_digest or new.terms_document_id is distinct from old.terms_document_id
    or new.terms_version is distinct from old.terms_version or new.terms_digest is distinct from old.terms_digest
    or new.commercial_descriptor is distinct from old.commercial_descriptor
    or new.configuration_schema_version is distinct from old.configuration_schema_version
    or new.configuration_schema is distinct from old.configuration_schema
  ) then raise exception 'published offering publication is immutable'; end if;
  select definition_id into product_definition_id from automation_products where id = new.product_id and org_id = new.org_id;
  select definition_id, package_digest, workflow_digest, lifecycle into release_definition_id, release_package_digest, release_workflow_digest, release_lifecycle
    from automation_releases where id = new.release_id and org_id = new.org_id;
  if product_definition_id is null or release_definition_id is distinct from product_definition_id then raise exception 'published offering lineage is incoherent'; end if;
  if new.status = 'published' and (release_lifecycle is distinct from 'certified' or release_package_digest is distinct from new.release_digest or release_workflow_digest is distinct from new.workflow_digest) then
    raise exception 'published offering must target the exact certified release digest';
  end if;
  if new.status = 'retired' then new.retired_at := coalesce(new.retired_at, now()); end if;
  return new;
end $$;
drop trigger if exists product_offering_publication_guard on lautowork.product_offering_publications;
create trigger product_offering_publication_guard
before insert or update or delete on lautowork.product_offering_publications
for each row execute function lautowork.assert_product_offering_publication();

alter table lautowork.product_orders add column if not exists snapshot_version integer not null default 1;
alter table lautowork.product_orders add column if not exists offering_snapshot_digest text;
alter table lautowork.product_terms_acceptances add column if not exists terms_document_id text;
alter table lautowork.product_terms_acceptances add column if not exists terms_digest text;
alter table lautowork.product_provider_event_receipts drop constraint if exists product_provider_event_receipts_event_type_check;
alter table lautowork.product_provider_event_receipts add constraint product_provider_event_receipts_event_type_check
  check (event_type in ('payment.succeeded','payment.failed','payment.refunded','provisioning.completed','provisioning.failed'));
alter table lautowork.product_provider_event_receipts add column if not exists provider_occurred_at timestamptz;
alter table lautowork.product_provider_event_receipts add column if not exists provider_sequence bigint;
alter table lautowork.commercial_lifecycles drop constraint if exists commercial_lifecycles_state_check;
alter table lautowork.commercial_lifecycles add constraint commercial_lifecycles_state_check
  check (state in ('initiated','awaiting_payment','payment_not_required','paid','awaiting_configuration','provisioning','active','suspended','cancel_requested','cancelled','failed','refunded'));
alter table lautowork.commercial_lifecycles add column if not exists provider_occurred_at timestamptz;
alter table lautowork.commercial_lifecycle_events add column if not exists provider_occurred_at timestamptz;
create unique index if not exists product_provider_event_sequence_unique
  on lautowork.product_provider_event_receipts (subscription_id, provider_sequence)
  where provider_sequence is not null;

create or replace function lautowork.assert_product_order_snapshot_immutable()
returns trigger language plpgsql set search_path=lautowork,pg_temp as $$
begin
  if old.offering_snapshot is not null and new.offering_snapshot is distinct from old.offering_snapshot then raise exception 'order offering snapshot is immutable'; end if;
  return new;
end $$;
drop trigger if exists product_order_snapshot_guard on lautowork.product_orders;
create trigger product_order_snapshot_guard
before update on lautowork.product_orders
for each row execute function lautowork.assert_product_order_snapshot_immutable();

create or replace function public.linkautowork_product_published_products(p_limit integer,p_cursor text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_offset integer:=coalesce(nullif(p_cursor,'')::integer,0); begin
  if p_limit < 1 or p_limit > 100 or v_offset < 0 then raise exception 'invalid cursor'; end if;
  return jsonb_build_object('items',coalesce((select jsonb_agg(jsonb_build_object(
    'id',product_id,'name',display_name,'summary',summary,'signupPrerequisites',jsonb_build_array('operator-assisted configuration'),
    'offeringVersion',offering_version,'release',jsonb_build_object('id',release_id,'version',release_version,'digest',release_digest,'workflowDigest',workflow_digest),
    'terms',jsonb_build_object('documentId',terms_document_id,'version',terms_version,'digest',terms_digest),
    'commercial',commercial_descriptor,'configuration',jsonb_build_object('schemaVersion',configuration_schema_version,'schema',configuration_schema)
  ) order by published_at desc)
    from (
      select publication.*,p.display_name,d.summary
      from (select distinct on (product_id) * from product_offering_publications where status='published' order by product_id,offering_version desc) publication
      join automation_products p on p.id=publication.product_id and p.org_id=publication.org_id and p.status='active'
      join automation_definitions d on d.id=p.definition_id and d.org_id=p.org_id
      join automation_releases r on r.id=publication.release_id and r.org_id=publication.org_id and r.lifecycle='certified' and r.package_digest=publication.release_digest and r.workflow_digest=publication.workflow_digest
      order by publication.published_at desc offset v_offset limit p_limit
    ) pub),'[]'::jsonb));
end $$;

create or replace function public.linkautowork_product_create_order(p_product_id text,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,extensions,pg_temp as $$
declare v_org uuid:=lautowork.product_api_org(); o product_orders%rowtype; pub product_offering_publications%rowtype; p automation_products%rowtype; d automation_definitions%rowtype; r automation_releases%rowtype;
begin
  perform lautowork.assert_product_api_authorized(v_org);
  select publication.* into pub from product_offering_publications publication join automation_releases r0 on r0.id=publication.release_id and r0.org_id=publication.org_id
    where publication.product_id=p_product_id::uuid and publication.status='published' and r0.lifecycle='certified' order by publication.offering_version desc limit 1;
  if not found then raise exception 'published offering not found'; end if;
  select * into p from automation_products where id=pub.product_id and org_id=pub.org_id and status='active';
  select * into d from automation_definitions where id=p.definition_id and org_id=p.org_id;
  select * into r from automation_releases where id=pub.release_id and org_id=pub.org_id and lifecycle='certified' and package_digest=pub.release_digest and workflow_digest=pub.workflow_digest;
  if not found then raise exception 'published offering certified target is unavailable'; end if;
  insert into product_orders(org_id,product_ref,idempotency_key,offering_snapshot,offering_snapshot_digest)
    values(v_org,p.id::text,p_idempotency_key,jsonb_build_object(
      'offeringPublicationId',pub.id,'offeringId',p.id,'offeringKey',p.offering_key,'offeringVersion',pub.offering_version,'displayName',p.display_name,'definitionId',d.id,'offeringOrgId',pub.org_id,
      'releaseId',r.id,'releaseVersion',r.version,'releaseDigest',r.package_digest,'workflowDigest',r.workflow_digest,'releaseRequirement','certified',
      'terms',jsonb_build_object('documentId',pub.terms_document_id,'version',pub.terms_version,'digest',pub.terms_digest),
      'commercial',pub.commercial_descriptor,'configuration',jsonb_build_object('schemaVersion',pub.configuration_schema_version,'schema',pub.configuration_schema)
    ),'sha256:'||encode(digest(convert_to(jsonb_build_object(
      'offeringPublicationId',pub.id,'offeringId',p.id,'offeringVersion',pub.offering_version,'releaseId',r.id,'releaseDigest',r.package_digest,'workflowDigest',r.workflow_digest,
      'terms',jsonb_build_object('documentId',pub.terms_document_id,'version',pub.terms_version,'digest',pub.terms_digest),'commercial',pub.commercial_descriptor,
      'configuration',jsonb_build_object('schemaVersion',pub.configuration_schema_version,'schema',pub.configuration_schema)
    )::text,'UTF8'),'sha256'),'hex'))
    on conflict(org_id,idempotency_key) do update set product_ref=product_orders.product_ref returning * into o;
  if o.product_ref <> p.id::text then raise exception 'idempotency key was previously used for another order'; end if;
  return jsonb_build_object('id',o.id,'orgId',o.org_id,'status',o.status,'summary',o.product_ref,'version',o.version,'snapshotVersion',o.snapshot_version,'offeringSnapshot',o.offering_snapshot);
end $$;

drop function if exists public.linkautowork_product_accept_terms(uuid,text,text);
create function public.linkautowork_product_accept_terms(p_order_id uuid,p_terms_document_id text,p_terms_version text,p_terms_digest text,p_actor text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid:=lautowork.product_api_org(); o product_orders%rowtype; existing product_terms_acceptances%rowtype; l commercial_lifecycles%rowtype; snap jsonb;
begin
  perform lautowork.assert_product_api_authorized(v_org); select * into o from product_orders where id=p_order_id and org_id=v_org for update; if not found then raise exception 'order not found in organization'; end if;
  snap:=o.offering_snapshot; if snap is null or p_terms_document_id is distinct from (snap->'terms'->>'documentId') or p_terms_version is distinct from (snap->'terms'->>'version') or p_terms_digest is distinct from (snap->'terms'->>'digest') then raise exception 'terms do not match the authoritative order snapshot'; end if;
  select * into existing from product_terms_acceptances where order_id=p_order_id and org_id=v_org;
  if found then
    if existing.terms_document_id is distinct from p_terms_document_id or existing.terms_version is distinct from p_terms_version or existing.terms_digest is distinct from p_terms_digest then raise exception 'terms acceptance conflicts with the authoritative order snapshot'; end if;
    return jsonb_build_object('orderId',p_order_id,'termsDocumentId',p_terms_document_id,'termsVersion',p_terms_version,'termsDigest',p_terms_digest,'accepted',true,'replay',true);
  end if;
  insert into product_terms_acceptances(org_id,order_id,terms_document_id,terms_version,terms_digest,accepted_by) values(v_org,p_order_id,p_terms_document_id,p_terms_version,p_terms_digest,p_actor);
  select * into l from commercial_lifecycles where order_id=p_order_id and org_id=v_org for update;
  if l.state='initiated' then perform public.linkautowork_commercial_transition(p_order_id,'payment_not_required',p_actor); end if;
  if (select state from commercial_lifecycles where id=l.id) in ('payment_not_required','paid') then perform public.linkautowork_commercial_transition(p_order_id,'awaiting_configuration',p_actor); end if;
  return jsonb_build_object('orderId',p_order_id,'termsDocumentId',p_terms_document_id,'termsVersion',p_terms_version,'termsDigest',p_terms_digest,'accepted',true,'replay',false);
end $$;

create or replace function public.linkautowork_product_create_subscription(p_order_id uuid,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid:=lautowork.product_api_org(); s product_subscriptions%rowtype; o product_orders%rowtype; inst automation_instances%rowtype; rel automation_releases%rowtype; snap jsonb; v_release_id uuid; v_definition_id uuid; v_offering_id uuid;
begin
  perform lautowork.assert_product_api_authorized(v_org); select * into o from product_orders where id=p_order_id and org_id=v_org for update; if not found then raise exception 'order not found in organization'; end if;
  if not exists(select 1 from product_terms_acceptances where order_id=p_order_id and org_id=v_org) or not exists(select 1 from commercial_lifecycles where order_id=p_order_id and org_id=v_org and state='awaiting_configuration') then raise exception 'durable terms and commercial configuration gate are required'; end if;
  snap:=o.offering_snapshot; v_release_id:=(snap->>'releaseId')::uuid; v_definition_id:=(snap->>'definitionId')::uuid; v_offering_id:=(snap->>'offeringId')::uuid;
  select * into rel from automation_releases ar where ar.id=v_release_id and ar.org_id=(snap->>'offeringOrgId')::uuid and ar.definition_id=v_definition_id and ar.lifecycle='certified' and ar.package_digest=(snap->>'releaseDigest') and ar.workflow_digest=(snap->>'workflowDigest');
  if not found then raise exception 'snapshotted certified release is no longer available'; end if;
  select ai.* into inst from automation_instances ai where ai.org_id=v_org and ai.definition_id=v_definition_id and ai.release_id=v_release_id and ai.state in ('ready','active') and (ai.product_id is null or ai.product_id=v_offering_id) order by ai.created_at limit 1;
  if not found then raise exception 'operator has not assigned the snapshotted certified automation target'; end if;
  select * into s from product_subscriptions where order_id=p_order_id and org_id=v_org for update;
  if found then return jsonb_build_object('id',s.id,'orgId',s.org_id,'status',s.status,'summary',s.order_id,'version',s.version,'releaseId',s.requested_release_id,'replay',true); end if;
  insert into product_subscriptions(org_id,order_id,status,automation_instance_id,requested_release_id,idempotency_key) values(v_org,p_order_id,'eligible',inst.id,rel.id,p_idempotency_key) returning * into s;
  return jsonb_build_object('id',s.id,'orgId',s.org_id,'status',s.status,'summary',s.order_id,'version',s.version,'releaseId',s.requested_release_id,'releaseDigest',rel.package_digest,'replay',false);
end $$;

create or replace function public.linkautowork_product_request_provisioning(p_subscription_id uuid,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid:=lautowork.product_api_org(); s product_subscriptions%rowtype; o product_orders%rowtype; rel automation_releases%rowtype; result jsonb; v_ref text; pr provisioning_requests%rowtype; snap jsonb;
begin
  perform lautowork.assert_product_api_authorized(v_org); select * into s from product_subscriptions where id=p_subscription_id and org_id=v_org for update; if not found then raise exception 'subscription not found in organization'; end if;
  select * into o from product_orders where id=s.order_id and org_id=v_org; snap:=o.offering_snapshot;
  if not exists(select 1 from product_configuration_submissions where subscription_id=s.id and org_id=v_org) or not exists(select 1 from commercial_lifecycles where order_id=s.order_id and state in ('awaiting_configuration','provisioning')) then raise exception 'durable safe configuration and commercial lifecycle are required'; end if;
  select * into rel from automation_releases where id=s.requested_release_id and org_id=(snap->>'offeringOrgId')::uuid and lifecycle='certified' and package_digest=(snap->>'releaseDigest') and workflow_digest=(snap->>'workflowDigest'); if not found then raise exception 'provisioning target is not the snapshotted certified release'; end if;
  v_ref:='product-subscription:'||s.id::text||':'||p_idempotency_key; insert into provisioning_requests(org_id,instance_id,requested_release_id,status,request_ref) values(v_org,s.automation_instance_id,s.requested_release_id,'requested',v_ref) on conflict(org_id,request_ref) do nothing; select * into pr from provisioning_requests where org_id=v_org and request_ref=v_ref; if pr.status='requested' then result:=public.linkautowork_begin_provisioning(v_org,v_ref); else result:=jsonb_build_object('requestId',pr.id,'status',pr.status); end if; update product_subscriptions set status=case when result->>'status'='completed' then 'active' else 'provisioning' end,version=version+1,updated_at=now() where id=s.id;
  if (result->>'status') in ('requested','provisioning','ready_for_review','completed') and (select state from commercial_lifecycles where order_id=s.order_id)='awaiting_configuration' then perform public.linkautowork_commercial_transition(s.order_id,'provisioning','product-api'); end if;
  return jsonb_build_object('id',result->>'requestId','orgId',v_org,'status',result->>'status','summary','WP-05 provisioning request','version',s.version+1,'releaseId',s.requested_release_id);
end $$;

create or replace function public.linkautowork_commercial_transition(p_order_id uuid,p_to_state text,p_actor text,p_provider_event_id text default null,p_provider_sequence bigint default null) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
begin
  return public.linkautowork_commercial_transition(p_order_id,p_to_state,p_actor,p_provider_event_id,p_provider_sequence,NULL::timestamptz);
end $$;

create or replace function public.linkautowork_commercial_transition(p_order_id uuid,p_to_state text,p_actor text,p_provider_event_id text,p_provider_sequence bigint,p_provider_occurred_at timestamptz) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare l commercial_lifecycles%rowtype; ok boolean; old_state text; v_org uuid:=lautowork.product_api_org();
begin
  perform lautowork.assert_product_api_authorized(v_org); select * into l from commercial_lifecycles where order_id=p_order_id and org_id=v_org for update; if not found then raise exception 'commercial lifecycle not found in organization'; end if; old_state:=l.state;
  if p_provider_event_id is not null and exists(select 1 from commercial_lifecycle_events where lifecycle_id=l.id and provider_event_id=p_provider_event_id) then return jsonb_build_object('id',l.id,'state',l.state,'replay',true,'version',l.version); end if;
  if p_provider_sequence is not null and (p_provider_sequence <= 0 or p_provider_sequence <= l.provider_event_sequence) then raise exception 'provider event out of order'; end if;
  if p_provider_occurred_at is not null and l.provider_occurred_at is not null and p_provider_occurred_at < l.provider_occurred_at then raise exception 'provider event occurredAt is stale'; end if;
  ok=(l.state='initiated' and p_to_state in ('awaiting_payment','payment_not_required','cancelled')) or (l.state='awaiting_payment' and p_to_state in ('paid','failed','cancel_requested')) or (l.state in ('paid','payment_not_required') and p_to_state in ('awaiting_configuration','cancel_requested','refunded')) or (l.state='awaiting_configuration' and p_to_state in ('provisioning','cancel_requested','failed','refunded')) or (l.state='provisioning' and p_to_state in ('active','failed','suspended','refunded')) or (l.state='active' and p_to_state in ('suspended','cancel_requested','failed','refunded')) or (l.state='suspended' and p_to_state in ('active','cancel_requested','cancelled','refunded')) or (l.state='cancel_requested' and p_to_state in ('cancelled','active','suspended'));
  if not ok then raise exception 'invalid commercial transition'; end if;
  update commercial_lifecycles set state=p_to_state,version=version+1,provider_event_sequence=coalesce(p_provider_sequence,provider_event_sequence),provider_occurred_at=coalesce(p_provider_occurred_at,provider_occurred_at) where id=l.id returning * into l;
  insert into commercial_lifecycle_events(lifecycle_id,org_id,from_state,to_state,actor_ref,provider_event_id,provider_sequence,provider_occurred_at) values(l.id,l.org_id,old_state,p_to_state,p_actor,p_provider_event_id,p_provider_sequence,p_provider_occurred_at);
  return jsonb_build_object('id',l.id,'state',l.state,'replay',false,'version',l.version,'providerSequence',l.provider_event_sequence,'occurredAt',l.provider_occurred_at);
end $$;

drop function if exists public.linkautowork_product_record_provider_event(text,text,uuid);
create function public.linkautowork_product_record_provider_event(p_event_id text,p_event_type text,p_subscription_id uuid,p_provider_occurred_at timestamptz,p_provider_sequence bigint) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid:=lautowork.product_api_org(); s product_subscriptions%rowtype; l commercial_lifecycles%rowtype; prior product_provider_event_receipts%rowtype; prior_found boolean; target text; result jsonb;
begin
  perform lautowork.assert_product_api_authorized(v_org); if p_event_type not in ('payment.succeeded','payment.failed','payment.refunded','provisioning.completed','provisioning.failed') or p_provider_occurred_at is null or p_provider_sequence is null or p_provider_sequence <= 0 then raise exception 'provider event is not allow-listed'; end if;
  select * into s from product_subscriptions where id=p_subscription_id and org_id=v_org for update; if not found then raise exception 'subscription not found in organization'; end if;
  select * into prior from product_provider_event_receipts where provider_event_id=p_event_id for update;
  prior_found:=prior.id is not null;
  if prior_found then
    if prior.subscription_id<>p_subscription_id or prior.event_type<>p_event_type or prior.provider_sequence is distinct from p_provider_sequence or prior.provider_occurred_at is distinct from p_provider_occurred_at then raise exception 'provider event id conflicts with its durable receipt'; end if;
    select state into target from commercial_lifecycles where order_id=s.order_id and org_id=v_org; return jsonb_build_object('replay',true,'state',target,'providerSequence',prior.provider_sequence,'occurredAt',prior.provider_occurred_at);
  end if;
  select * into l from commercial_lifecycles where order_id=s.order_id and org_id=v_org for update; if not found then raise exception 'commercial lifecycle not found in organization'; end if;
  if p_provider_sequence <= l.provider_event_sequence or (l.provider_occurred_at is not null and p_provider_occurred_at < l.provider_occurred_at) then raise exception 'provider event out of order'; end if;
  insert into product_provider_event_receipts(org_id,subscription_id,provider_event_id,event_type,provider_occurred_at,provider_sequence)
    values(v_org,s.id,p_event_id,p_event_type,p_provider_occurred_at,p_provider_sequence)
    on conflict(provider_event_id) do nothing returning * into prior;
  if not found then
    select * into prior from product_provider_event_receipts where provider_event_id=p_event_id for update;
    if prior.subscription_id<>p_subscription_id or prior.event_type<>p_event_type or prior.provider_sequence is distinct from p_provider_sequence or prior.provider_occurred_at is distinct from p_provider_occurred_at then raise exception 'provider event id conflicts with its durable receipt'; end if;
    select state into target from commercial_lifecycles where order_id=s.order_id and org_id=v_org; return jsonb_build_object('replay',true,'state',target,'providerSequence',prior.provider_sequence,'occurredAt',prior.provider_occurred_at);
  end if;
  if p_event_type='payment.succeeded' then
    if l.state<>'awaiting_payment' then raise exception 'payment success is not valid for the current lifecycle'; end if;
    result:=public.linkautowork_commercial_transition(s.order_id,'paid','provider:payment.succeeded',p_event_id,p_provider_sequence,p_provider_occurred_at);
    result:=public.linkautowork_commercial_transition(s.order_id,'awaiting_configuration','product-api');
  elsif p_event_type='payment.failed' then
    result:=public.linkautowork_commercial_transition(s.order_id,'failed','provider:payment.failed',p_event_id,p_provider_sequence,p_provider_occurred_at);
    update product_subscriptions set status='failed',version=version+1,updated_at=now() where id=s.id;
  elsif p_event_type='payment.refunded' then
    result:=public.linkautowork_commercial_transition(s.order_id,'refunded','provider:payment.refunded',p_event_id,p_provider_sequence,p_provider_occurred_at);
    update product_subscriptions set status='cancelled',version=version+1,updated_at=now() where id=s.id;
  elsif p_event_type='provisioning.completed' then
    result:=public.linkautowork_commercial_transition(s.order_id,'active','provider:provisioning.completed',p_event_id,p_provider_sequence,p_provider_occurred_at);
    update product_subscriptions set status='active',version=version+1,updated_at=now() where id=s.id;
  else
    result:=public.linkautowork_commercial_transition(s.order_id,'failed','provider:provisioning.failed',p_event_id,p_provider_sequence,p_provider_occurred_at);
    update product_subscriptions set status='failed',version=version+1,updated_at=now() where id=s.id;
  end if;
  return jsonb_build_object('replay',false,'state',result->>'state','providerSequence',p_provider_sequence,'occurredAt',p_provider_occurred_at);
end $$;

do $$ declare f record; begin for f in select p.oid::regprocedure sig from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname like 'linkautowork_product_%' or n.nspname='public' and p.proname='linkautowork_commercial_transition' loop execute format('revoke all on function %s from public',f.sig); execute format('grant execute on function %s to service_role, svc_lautowork_runtime',f.sig); end loop; end $$;

-- migrate:down
drop function if exists public.linkautowork_product_record_provider_event(text,text,uuid,timestamptz,bigint);
drop function if exists public.linkautowork_product_accept_terms(uuid,text,text,text,text);
drop function if exists public.linkautowork_commercial_transition(uuid,text,text,text,bigint,timestamptz);

-- The publication and provider-history objects are immutable/additive.  A down
-- migration must not delete their append-only evidence; production recovery is
-- a forward fix, not a destructive rollback.  Their guards, columns,
-- constraints, and indexes therefore remain in place.

-- Restore the exact 000006 published-products projection.
create or replace function public.linkautowork_product_published_products(p_limit integer,p_cursor text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_offset integer:=coalesce(nullif(p_cursor,'')::integer,0); begin
  if p_limit < 1 or p_limit > 100 or v_offset < 0 then raise exception 'invalid cursor'; end if;
  return jsonb_build_object('items',coalesce((select jsonb_agg(jsonb_build_object('id',p.id,'name',p.display_name,'summary',d.summary,'signupPrerequisites',jsonb_build_array('operator-assisted configuration'),'version',1) order by p.created_at desc)
    from (select * from automation_products where status='active' order by created_at desc offset v_offset limit p_limit) p join automation_definitions d on d.id=p.definition_id and d.org_id=p.org_id),'[]'::jsonb));
end $$;

-- Restore the exact 000008 order, terms, subscription, provisioning, and
-- provider-event implementations, plus the 000007 five-argument transition.
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

create or replace function public.linkautowork_product_request_provisioning(p_subscription_id uuid,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid:=lautowork.product_api_org(); s product_subscriptions%rowtype; result jsonb; v_ref text; pr provisioning_requests%rowtype; begin perform lautowork.assert_product_api_authorized(v_org); select * into s from product_subscriptions where id=p_subscription_id and org_id=v_org for update; if not found then raise exception 'subscription not found in organization'; end if;
 if not exists(select 1 from product_configuration_submissions where subscription_id=s.id and org_id=v_org) or not exists(select 1 from commercial_lifecycles where order_id=s.order_id and state in ('awaiting_configuration','provisioning')) then raise exception 'durable safe configuration and commercial lifecycle are required'; end if;
 v_ref:='product-subscription:'||s.id::text||':'||p_idempotency_key; insert into provisioning_requests(org_id,instance_id,requested_release_id,status,request_ref) values(v_org,s.automation_instance_id,s.requested_release_id,'requested',v_ref) on conflict(org_id,request_ref) do nothing; select * into pr from provisioning_requests where org_id=v_org and request_ref=v_ref; if pr.status='requested' then result:=public.linkautowork_begin_provisioning(v_org,v_ref); else result:=jsonb_build_object('requestId',pr.id,'status',pr.status); end if; update product_subscriptions set status=case when result->>'status'='completed' then 'active' else 'provisioning' end,version=version+1,updated_at=now() where id=s.id;
 if (result->>'status') in ('requested','provisioning','ready_for_review','completed') and (select state from commercial_lifecycles where order_id=s.order_id)='awaiting_configuration' then perform public.linkautowork_commercial_transition(s.order_id,'provisioning','product-api'); end if;
 return jsonb_build_object('id',result->>'requestId','orgId',v_org,'status',result->>'status','summary','WP-05 provisioning request','version',1); end $$;

create or replace function public.linkautowork_commercial_transition(p_order_id uuid,p_to_state text,p_actor text,p_provider_event_id text default null,p_provider_sequence bigint default null) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare l commercial_lifecycles%rowtype; ok boolean; old_state text; v_org uuid:=lautowork.product_api_org(); begin perform lautowork.assert_product_api_authorized(v_org); select * into l from commercial_lifecycles where order_id=p_order_id and org_id=v_org for update; if not found then raise exception 'commercial lifecycle not found in organization'; end if; old_state:=l.state;
 if p_provider_event_id is not null and exists(select 1 from commercial_lifecycle_events where lifecycle_id=l.id and provider_event_id=p_provider_event_id) then return jsonb_build_object('id',l.id,'state',l.state,'replay',true,'version',l.version); end if;
 if p_provider_sequence is not null and p_provider_sequence<=l.provider_event_sequence then raise exception 'provider event out of order'; end if;
 ok=(l.state='initiated' and p_to_state in ('awaiting_payment','payment_not_required','cancelled')) or (l.state='awaiting_payment' and p_to_state in ('paid','failed','cancel_requested')) or (l.state in ('paid','payment_not_required') and p_to_state in ('awaiting_configuration','cancel_requested')) or (l.state='awaiting_configuration' and p_to_state in ('provisioning','cancel_requested','failed')) or (l.state='provisioning' and p_to_state in ('active','failed','suspended')) or (l.state='active' and p_to_state in ('suspended','cancel_requested','failed')) or (l.state='suspended' and p_to_state in ('active','cancel_requested','cancelled')) or (l.state='cancel_requested' and p_to_state in ('cancelled','active','suspended'));
 if not ok then raise exception 'invalid commercial transition'; end if;
 update commercial_lifecycles set state=p_to_state,version=version+1,provider_event_sequence=coalesce(p_provider_sequence,provider_event_sequence) where id=l.id returning * into l; insert into commercial_lifecycle_events(lifecycle_id,org_id,from_state,to_state,actor_ref,provider_event_id,provider_sequence) values(l.id,l.org_id,old_state,p_to_state,p_actor,p_provider_event_id,p_provider_sequence); return jsonb_build_object('id',l.id,'state',l.state,'replay',false,'version',l.version); end $$;

create or replace function public.linkautowork_product_record_provider_event(p_event_id text,p_event_type text,p_subscription_id uuid) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid:=lautowork.product_api_org(); s product_subscriptions%rowtype; seq bigint; target text; inserted boolean; begin perform lautowork.assert_product_api_authorized(v_org); select * into s from product_subscriptions where id=p_subscription_id and org_id=v_org for update; if not found then raise exception 'subscription not found in organization'; end if; insert into product_provider_event_receipts(org_id,subscription_id,provider_event_id,event_type) values(v_org,s.id,p_event_id,p_event_type) on conflict(provider_event_id) do nothing returning true into inserted; if not coalesce(inserted,false) then return jsonb_build_object('replay',true); end if; if p_event_type='payment.succeeded' then return jsonb_build_object('replay',false); end if; select provider_event_sequence+1 into seq from commercial_lifecycles where order_id=s.order_id for update; target:=case p_event_type when 'provisioning.completed' then 'active' else 'failed' end; perform public.linkautowork_commercial_transition(s.order_id,target,'provider:'||p_event_type,p_event_id,seq); update product_subscriptions set status=case target when 'active' then 'active' when 'failed' then 'failed' else status end,version=version+1 where id=s.id; return jsonb_build_object('replay',false); end $$;

revoke all on function public.linkautowork_product_published_products(integer,text) from public;
grant execute on function public.linkautowork_product_published_products(integer,text) to service_role,svc_lautowork_runtime;
revoke all on function public.linkautowork_product_create_order(text,text) from public;
grant execute on function public.linkautowork_product_create_order(text,text) to service_role,svc_lautowork_runtime;
revoke all on function public.linkautowork_product_accept_terms(uuid,text,text) from public;
grant execute on function public.linkautowork_product_accept_terms(uuid,text,text) to service_role,svc_lautowork_runtime;
revoke all on function public.linkautowork_product_create_subscription(uuid,text) from public;
grant execute on function public.linkautowork_product_create_subscription(uuid,text) to service_role,svc_lautowork_runtime;
revoke all on function public.linkautowork_product_request_provisioning(uuid,text) from public;
grant execute on function public.linkautowork_product_request_provisioning(uuid,text) to service_role,svc_lautowork_runtime;
revoke all on function public.linkautowork_product_record_provider_event(text,text,uuid) from public;
grant execute on function public.linkautowork_product_record_provider_event(text,text,uuid) to service_role,svc_lautowork_runtime;
revoke all on function public.linkautowork_commercial_transition(uuid,text,text,text,bigint) from public;
grant execute on function public.linkautowork_commercial_transition(uuid,text,text,text,bigint) to service_role,svc_lautowork_runtime;
