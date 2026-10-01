\set ON_ERROR_STOP on
-- Simulate an existing AW-02 database before the additive request/receipt JSON migration.
insert into platform.organizations(id, name)
values ('00000000-0000-0000-0000-000000000004', 'provider-legacy-upgrade');

insert into lautowork.provider_requests
  (id, org_id, contract_version, automation_id, automation_version,
   definition_digest, configuration_digest, configuration_ref, idempotency_key,
   request_fingerprint, operation_kind, state, expires_at, correlation_ref, handoff_ref)
values
  ('a0000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000004',
   '2026-08-13.v1', 'ide-repository-status', '1.0.0',
   'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
   'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
   'autowork://config/ide-repository-status/1.0.0', 'legacy-provider-request-key',
   'sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
   'precheck', 'accepted', now() + interval '1 day',
   'ide://attempt/legacy', null);

insert into lautowork.provider_receipts
  (id, request_id, org_id, state, attempt_count, evidence_ref, result_ref)
values
  ('b0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000004', 'accepted', 0,
   'ide://evidence/legacy', 'ide://result/legacy');
