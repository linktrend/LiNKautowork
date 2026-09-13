\set ON_ERROR_STOP on

insert into platform.organizations (id, slug) values
  ('00000000-0000-0000-0000-0000000000a1', 'server01-org-a'),
  ('00000000-0000-0000-0000-0000000000b1', 'server01-org-b')
on conflict (id) do nothing;

select set_config('request.jwt.claim.org_id', '00000000-0000-0000-0000-0000000000a1', false);
select set_config('request.jwt.claim.role', 'svc_lautowork_gateway', false);

insert into lautowork.server01_credential_bindings (org_id, binding_id, secret_ref, purpose, scope)
values (
  '00000000-0000-0000-0000-0000000000a1',
  'gateway-binding-1',
  'LINKTREND_AUTOWORK_STAGE_GSM_GATEWAY_CREDENTIAL',
  'Gateway PACI client credential reference',
  'gateway'
);

do $$
declare
  digest text := 'sha256:' || repeat('ab', 32);
  request jsonb;
  first jsonb;
  replay jsonb;
  receipt jsonb;
  callback jsonb;
begin
  request := jsonb_build_object(
    'request_id', '00000000-0000-0000-0000-0000000000c1',
    'org_id', '00000000-0000-0000-0000-0000000000a1',
    'work_ref', 'program://issues/opaque-work-1',
    'authority_ref', 'platform://authority/opaque-1',
    'actor_id', 'svc-gateway',
    'audience', 'autowork',
    'capability', 'automation.invoke',
    'credential_id', 'credential-1',
    'credential_binding_ref', 'gsm://bindings/gateway-binding-1',
    'binding_id', 'gateway-binding-1',
    'automation_id', 'repo-precheck',
    'automation_version', '1.0.0',
    'definition_digest', digest,
    'configuration_digest', digest,
    'configuration_ref', 'autowork://config/1',
    'allowed_operation', 'precheck',
    'operation_kind', 'precheck',
    'input_ref', 'autowork://input/1',
    'input_digest', digest,
    'idempotency_key', 'idempotency-key-01',
    'callback_binding_ref', 'autowork://callback/1',
    'budget_ceiling_ref', 'autowork://budget/1',
    'expires_at', '2030-01-01T00:00:00Z'
  );
  first := lautowork.server01_accept_invocation(request, digest);
  if (first->>'replay')::boolean then raise exception 'first accept unexpectedly replayed'; end if;
  if first->'intent'->>'state' is distinct from 'PREPARED' then raise exception 'intent was not PREPARED'; end if;
  replay := lautowork.server01_accept_invocation(request, digest);
  if not (replay->>'replay')::boolean then raise exception 'identical replay was not detected'; end if;
  begin
    perform lautowork.server01_accept_invocation(request, 'sha256:' || repeat('cd', 32));
    raise exception 'changed fingerprint unexpectedly accepted';
  exception when unique_violation then null;
  end;
  begin
    perform lautowork.server01_accept_invocation(request || jsonb_build_object('task_body', 'do the issue'), digest);
    raise exception 'task body unexpectedly accepted';
  exception when others then
    if sqlerrm not like '%task bodies%' and sqlerrm not like '%secret-shaped%' then raise; end if;
  end;
  perform set_config('request.jwt.claim.org_id', '00000000-0000-0000-0000-0000000000b1', false);
  begin
    perform lautowork.server01_accept_invocation(request, digest);
    raise exception 'cross-org accept unexpectedly succeeded';
  exception when insufficient_privilege then null;
  end;
  perform set_config('request.jwt.claim.org_id', '00000000-0000-0000-0000-0000000000a1', false);
  perform set_config('request.jwt.claim.role', 'svc_lautowork_runtime_dispatch', false);
  receipt := jsonb_build_object(
    'receipt_id', '00000000-0000-0000-0000-0000000000d1',
    'request_id', '00000000-0000-0000-0000-0000000000c1',
    'state', 'succeeded',
    'request_fingerprint', digest,
    'evidence_ref', 'autowork://evidence/1',
    'result_ref', 'autowork://result/1'
  );
  callback := jsonb_build_object(
    'request_id', '00000000-0000-0000-0000-0000000000c1',
    'org_id', '00000000-0000-0000-0000-0000000000a1',
    'callback_binding_ref', 'autowork://callback/1',
    'callback_fingerprint', digest,
    'source_timestamp', '2030-01-01T00:00:01Z',
    'receipt', receipt
  );
  perform lautowork.server01_admit_callback(callback);
  if not (lautowork.server01_admit_callback(callback)->>'replay')::boolean then
    raise exception 'identical callback was not replayed';
  end if;
  begin
    perform lautowork.server01_admit_callback(callback || jsonb_build_object('callback_fingerprint', 'sha256:' || repeat('ef', 32)));
    raise exception 'changed callback unexpectedly admitted';
  exception when unique_violation then null;
  end;
  begin
    update lautowork.server01_receipts set state = 'failed';
    raise exception 'receipt update unexpectedly succeeded';
  exception when others then
    if sqlerrm not like '%append-only%' then raise; end if;
  end;
end $$;
