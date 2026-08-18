\set ON_ERROR_STOP on

select set_config('request.jwt.claim.org_id', '00000000-0000-0000-0000-000000000002', false);
select set_config('request.jwt.claim.role', 'service_role', false);

insert into lautowork.automation_products(id,org_id,definition_id,offering_key,display_name,status)
values('90000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000001','approved-automation','Approved Automation','active') on conflict (id) do nothing;
insert into lautowork.automation_products(id,org_id,definition_id,offering_key,display_name,status)
values('90000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000001','unpublished-automation','Unpublished Automation','draft') on conflict (id) do nothing;
insert into lautowork.automation_products(id,org_id,definition_id,offering_key,display_name,status)
values('90000000-0000-0000-0000-000000000003','00000000-0000-0000-0000-000000000003','10000000-0000-0000-0000-000000000002','cross-org-automation','Cross Organisation Automation','active') on conflict (id) do nothing;
insert into lautowork.product_offering_publications(id,org_id,product_id,offering_version,release_id,release_version,release_digest,workflow_digest,terms_document_id,terms_version,terms_digest,commercial_descriptor,configuration_schema_version,configuration_schema,status)
values('91000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','90000000-0000-0000-0000-000000000001',3,'20000000-0000-0000-0000-000000000001','1.0.0','sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','hosted-automation-terms','2026-08-04','sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee','{"descriptorVersion":1,"billingModel":"operator_quote","pricePresentation":"Pricing is confirmed with support before activation.","chargesMoney":false,"paymentCollection":"none"}'::jsonb,'v1','{"type":"object","properties":{"timezone":{"type":"string","enum":["Asia/Taipei","UTC"]}},"required":["timezone"],"additionalProperties":false}'::jsonb,'published');

do $$
begin
  begin
    perform public.linkautowork_product_create_order('90000000-0000-0000-0000-000000000099', 'product-order-unknown-key');
    raise exception 'unknown published offering unexpectedly succeeded';
  exception when others then
    if position('published offering not found' in sqlerrm)=0 then raise; end if;
  end;
  begin
    perform public.linkautowork_product_create_order('90000000-0000-0000-0000-000000000002', 'product-order-unpublished-key');
    raise exception 'unpublished offering unexpectedly succeeded';
  exception when others then
    if position('published offering not found' in sqlerrm)=0 then raise; end if;
  end;
end $$;

do $$
begin
  begin
    perform public.linkautowork_product_create_order('90000000-0000-0000-0000-000000000003', 'cross-org-offer-order-key');
    raise exception 'unpublished cross-organization offering unexpectedly succeeded';
  exception when others then
    if position('published offering not found' in sqlerrm)=0 then raise; end if;
  end;
end $$;

do $$
declare order_a jsonb; terms_first jsonb; terms_replay jsonb; subscription_a jsonb; subscription_replay jsonb; replay jsonb; receipt_first jsonb; receipt_replay jsonb; provision_first jsonb; provision_replay jsonb;
begin
  order_a := public.linkautowork_product_create_order('90000000-0000-0000-0000-000000000001', 'product-order-disposable-key');
  if order_a->>'status' <> 'pending_operator_review' then raise exception 'product order was not durable'; end if;
  if not exists (
    select 1 from lautowork.product_orders
    where id=(order_a->>'id')::uuid
      and offering_snapshot @> '{"offeringId":"90000000-0000-0000-0000-000000000001","offeringVersion":3,"releaseId":"20000000-0000-0000-0000-000000000001","releaseDigest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","terms":{"documentId":"hosted-automation-terms","version":"2026-08-04","digest":"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"},"commercial":{"chargesMoney":false,"paymentCollection":"none"},"configuration":{"schemaVersion":"v1"}}'::jsonb
  ) then raise exception 'published offering snapshot was not durable'; end if;
  begin
    perform public.linkautowork_product_accept_terms((order_a->>'id')::uuid, 'hosted-automation-terms', 'wrong-version', 'sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee', 'disposable-client');
    raise exception 'arbitrary terms unexpectedly accepted';
  exception when others then
    if position('terms do not match' in sqlerrm)=0 then raise; end if;
  end;
  terms_first := public.linkautowork_product_accept_terms((order_a->>'id')::uuid, 'hosted-automation-terms', '2026-08-04', 'sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee', 'disposable-client');
  terms_replay := public.linkautowork_product_accept_terms((order_a->>'id')::uuid, 'hosted-automation-terms', '2026-08-04', 'sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee', 'disposable-client');
  if (terms_first->>'replay')::boolean or not (terms_replay->>'replay')::boolean then raise exception 'terms acceptance was not idempotent'; end if;
  subscription_a := public.linkautowork_product_create_subscription((order_a->>'id')::uuid, 'product-subscription-disposable-key');
  subscription_replay := public.linkautowork_product_create_subscription((order_a->>'id')::uuid, 'product-subscription-retry-key');
  if subscription_replay->>'id' is distinct from subscription_a->>'id' or not (subscription_replay->>'replay')::boolean then raise exception 'one governed subscription was not restart safe'; end if;
  update lautowork.commercial_lifecycles set state='awaiting_payment' where order_id=(order_a->>'id')::uuid;
  receipt_first := public.linkautowork_product_record_provider_event('provider-event-disposable-0001', 'payment.succeeded', (subscription_a->>'id')::uuid, '2026-08-04T00:00:10Z', 10);
  receipt_replay := public.linkautowork_product_record_provider_event('provider-event-disposable-0001', 'payment.succeeded', (subscription_a->>'id')::uuid, '2026-08-04T00:00:10Z', 10);
  if (receipt_first->>'replay')::boolean or not (receipt_replay->>'replay')::boolean then raise exception 'provider event replay receipt is not durable'; end if;
  begin
    perform public.linkautowork_product_record_provider_event('provider-event-disposable-0001', 'payment.failed', (subscription_a->>'id')::uuid, '2026-08-04T00:00:10Z', 10);
    raise exception 'conflicting provider event replay unexpectedly succeeded';
  exception when others then
    if position('provider event id conflicts with its durable receipt' in sqlerrm)=0 then raise; end if;
  end;
  begin
    perform public.linkautowork_commercial_transition((order_a->>'id')::uuid, 'provisioning', 'stale-provider', 'provider-event-disposable-stale', 11, '2026-08-04T00:00:09Z');
    raise exception 'stale provider event unexpectedly succeeded';
  exception when others then
    if position('provider event occurredAt is stale' in sqlerrm)=0 then raise; end if;
  end;
  begin
    perform public.linkautowork_product_request_provisioning((subscription_a->>'id')::uuid, 'product-provision-before-config-key');
    raise exception 'provisioning bypassed the configuration gate';
  exception when others then
    if position('durable safe configuration' in sqlerrm)=0 then raise; end if;
  end;
  update lautowork.product_subscriptions set status='eligible', automation_instance_id='40000000-0000-0000-0000-000000000001', requested_release_id='20000000-0000-0000-0000-000000000001' where id=(subscription_a->>'id')::uuid;
  begin
    perform public.linkautowork_product_submit_configuration((subscription_a->>'id')::uuid,'{"apiKey":"ltfx.ph.e789616d1c.v1"}'::jsonb,'product-config-secret-key');
    raise exception 'credential-shaped configuration unexpectedly succeeded';
  exception when others then
    if position('credentials require operator-assisted binding' in sqlerrm)=0 then raise; end if;
  end;
  perform public.linkautowork_product_submit_configuration((subscription_a->>'id')::uuid,'{"timezone":"Asia/Taipei"}'::jsonb,'product-config-disposable-key');
  provision_first := public.linkautowork_product_request_provisioning((subscription_a->>'id')::uuid, 'product-provision-disposable-key');
  provision_replay := public.linkautowork_product_request_provisioning((subscription_a->>'id')::uuid, 'product-provision-disposable-key');
  if provision_first->>'id' is distinct from provision_replay->>'id' then raise exception 'product provisioning did not replay its WP-05 request'; end if;
  update lautowork.product_subscriptions set status='failed' where id=(subscription_a->>'id')::uuid;
  if (public.linkautowork_product_compensate_provisioning((subscription_a->>'id')::uuid, 'durable failure evidence', 'product-compensation-key')->>'status') <> 'compensation_pending' then raise exception 'compensation outcome is not truthful'; end if;
  replay := public.linkautowork_product_create_order('90000000-0000-0000-0000-000000000001', 'product-order-disposable-key');
  if replay->>'id' is distinct from order_a->>'id' or replay->>'summary' <> '90000000-0000-0000-0000-000000000001' then raise exception 'product order idempotency was not restart safe'; end if;
end $$;

do $$
declare order_a uuid;
begin
  select id into order_a from lautowork.product_orders where org_id='00000000-0000-0000-0000-000000000002' and idempotency_key='product-order-disposable-key';
  perform set_config('request.jwt.claim.org_id', '00000000-0000-0000-0000-000000000003', true);
  begin
    perform public.linkautowork_product_create_subscription(order_a, 'cross-org-subscription-key');
    raise exception 'cross-organization subscription unexpectedly succeeded';
  exception when others then
    if position('not found in organization' in sqlerrm)=0 then raise; end if;
  end;
end $$;

select set_config('request.jwt.claim.org_id', '00000000-0000-0000-0000-000000000002', false);
select public.assert_true((select count(*)=1 from lautowork.product_terms_acceptances), 'terms acceptance is durable');
select public.assert_true((select count(*)=1 from lautowork.product_provider_event_receipts), 'provider replay receipt is durable');
select public.assert_true((select count(*)=1 from lautowork.provisioning_requests where request_ref like 'product-subscription:%'), 'product provisioning delegates to one WP-05 request');
-- 000007 lifecycle guards: no provider values are stored; only event identity/sequence is durable.
select public.linkautowork_commercial_transition((select id from lautowork.product_orders where idempotency_key='product-order-disposable-key'),'active','fake-provider','provider-event-0001',11);
select public.assert_true((public.linkautowork_commercial_transition((select id from lautowork.product_orders where idempotency_key='product-order-disposable-key'),'suspended','fake-provider','provider-event-0001',11)->>'replay')::boolean,'provider replay is durable');
do $$ begin
  begin perform public.linkautowork_commercial_transition((select id from lautowork.product_orders where idempotency_key='product-order-disposable-key'),'suspended','fake-provider','provider-event-0002',10); raise exception 'out of order provider event succeeded'; exception when others then if position('out of order' in sqlerrm)=0 then raise; end if; end;
  begin perform public.linkautowork_commercial_transition((select id from lautowork.product_orders where idempotency_key='product-order-disposable-key'),'initiated','disposable-client'); raise exception 'invalid lifecycle transition succeeded'; exception when others then if position('invalid commercial transition' in sqlerrm)=0 then raise; end if; end;
end $$;
select public.assert_true((select from_state='provisioning' and to_state='active' from lautowork.commercial_lifecycle_events where provider_event_id='provider-event-0001'),'commercial event history preserves previous state');
select public.assert_true((select provider_occurred_at='2026-08-04T00:00:10Z'::timestamptz and provider_sequence=10 from lautowork.product_provider_event_receipts where provider_event_id='provider-event-disposable-0001'),'provider occurredAt and sequence are durable');
select 'WP-09 durable product verification passed' as result;
