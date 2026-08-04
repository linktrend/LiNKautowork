\set ON_ERROR_STOP on

select set_config('request.jwt.claim.org_id', '00000000-0000-0000-0000-000000000002', false);
select set_config('request.jwt.claim.role', 'service_role', false);

insert into lautowork.product_orders(id,org_id,product_ref,status,idempotency_key,offering_snapshot,offering_snapshot_digest)
values
('92000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','90000000-0000-0000-0000-000000000001','pending_operator_review','webhook-http-success',
 '{"offeringPublicationId":"91000000-0000-0000-0000-000000000001","offeringId":"90000000-0000-0000-0000-000000000001","offeringVersion":3,"definitionId":"10000000-0000-0000-0000-000000000001","offeringOrgId":"00000000-0000-0000-0000-000000000002","releaseId":"20000000-0000-0000-0000-000000000001","releaseVersion":"1.0.0","releaseDigest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","workflowDigest":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","terms":{"documentId":"hosted-automation-terms","version":"2026-08-04","digest":"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"},"commercial":{"descriptorVersion":1,"chargesMoney":false,"paymentCollection":"none"},"configuration":{"schemaVersion":"v1","schema":{"type":"object"}}}'::jsonb,
 'sha256:1111111111111111111111111111111111111111111111111111111111111111'),
('92000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000002','90000000-0000-0000-0000-000000000001','pending_operator_review','webhook-http-failure',
 '{"offeringPublicationId":"91000000-0000-0000-0000-000000000001","offeringId":"90000000-0000-0000-0000-000000000001","offeringVersion":3,"definitionId":"10000000-0000-0000-0000-000000000001","offeringOrgId":"00000000-0000-0000-0000-000000000002","releaseId":"20000000-0000-0000-0000-000000000001","releaseVersion":"1.0.0","releaseDigest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","workflowDigest":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","terms":{"documentId":"hosted-automation-terms","version":"2026-08-04","digest":"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"},"commercial":{"descriptorVersion":1,"chargesMoney":false,"paymentCollection":"none"},"configuration":{"schemaVersion":"v1","schema":{"type":"object"}}}'::jsonb,
 'sha256:2222222222222222222222222222222222222222222222222222222222222222');

insert into lautowork.product_terms_acceptances(org_id,order_id,terms_document_id,terms_version,terms_digest,accepted_by)
values
('00000000-0000-0000-0000-000000000002','92000000-0000-0000-0000-000000000001','hosted-automation-terms','2026-08-04','sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee','webhook-verifier'),
('00000000-0000-0000-0000-000000000002','92000000-0000-0000-0000-000000000002','hosted-automation-terms','2026-08-04','sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee','webhook-verifier');

update lautowork.commercial_lifecycles set state='awaiting_payment', provider_event_sequence=0, provider_occurred_at=null
where order_id in ('92000000-0000-0000-0000-000000000001','92000000-0000-0000-0000-000000000002');

insert into lautowork.product_subscriptions(id,org_id,order_id,status,automation_instance_id,requested_release_id,idempotency_key)
values
('93000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','92000000-0000-0000-0000-000000000001','eligible','40000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','webhook-http-success-subscription'),
('93000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000002','92000000-0000-0000-0000-000000000002','eligible','40000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','webhook-http-failure-subscription');
