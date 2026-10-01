\set ON_ERROR_STOP on

do $$
declare
  org_a constant uuid := '00000000-0000-0000-0000-000000000002';
  org_b constant uuid := '00000000-0000-0000-0000-000000000003';
  org_legacy constant uuid := '00000000-0000-0000-0000-000000000004';
  request_fingerprint constant text := 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  config_digest constant text := 'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
  v_request jsonb;
  v_legacy_replay jsonb;
  v_accept jsonb;
  v_replay jsonb;
  v_record jsonb;
  v_receipt jsonb;
  v_saved_receipt jsonb;
  v_legacy_receipt_request jsonb;
  v_callback jsonb;
  v_killed boolean;
begin
  perform public.assert_true(
    (select request_json is null from lautowork.provider_requests where id='a0000000-0000-0000-0000-000000000001'),
    'upgrade leaves unavailable historical request payload null'
  );
  perform public.assert_true(
    (select receipt_json is null from lautowork.provider_receipts where id='b0000000-0000-0000-0000-000000000001'),
    'upgrade leaves unavailable historical receipt payload null'
  );

  perform set_config('request.jwt.claim.org_id', org_legacy::text, false);
  v_legacy_replay := jsonb_build_object(
    'platform', jsonb_build_object('org_id', org_legacy),
    'automation', jsonb_build_object('automation_id', 'ide-repository-status'),
    'idempotency_key', 'legacy-provider-request-key'
  );
  begin
    perform lautowork.linkautowork_provider_accept(v_legacy_replay, 'sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc');
    raise exception 'legacy replay unexpectedly fabricated the unavailable invocation';
  exception when sqlstate '55000' then
    if sqlerrm <> 'provider legacy request payload unavailable' then raise; end if;
  end;
  begin
    perform lautowork.linkautowork_provider_get_request('a0000000-0000-0000-0000-000000000001');
    raise exception 'legacy read unexpectedly fabricated the unavailable invocation';
  exception when sqlstate '55000' then
    if sqlerrm <> 'provider legacy request payload unavailable' then raise; end if;
  end;

  perform set_config('request.jwt.claim.org_id', org_a::text, false);
  v_request := jsonb_build_object(
    'contract_version', '2026-08-13.v1',
    'protocol_version', 'http/1',
    'request_id', 'a0000000-0000-0000-0000-000000000002',
    'platform', jsonb_build_object(
      'org_id', org_a, 'actor_id', 'provider-disposable-actor', 'audience', 'lautowork',
      'capability', 'catalogue.invoke', 'credential_id', 'credential-disposable',
      'binding_id', 'binding-disposable', 'issued_at', '2026-10-01T00:00:00Z',
      'expires_at', '2026-10-02T00:00:00Z', 'revocation_ref', 'platform://revocations/current'
    ),
    'automation', jsonb_build_object(
      'automation_id', 'ide-repository-status', 'version', '1.0.0',
      'definition_digest', request_fingerprint,
      'configuration_ref', jsonb_build_object(
        'ref', 'autowork://config/ide-repository-status/1.0.0',
        'digest', config_digest, 'observed_at', '2026-10-01T00:00:00Z'
      )
    ),
    'operation_kind', 'precheck',
    'input_ref', jsonb_build_object('ref', 'ide://input/status', 'digest', request_fingerprint, 'observed_at', '2026-10-01T00:00:00Z'),
    'artifact_refs', '[]'::jsonb,
    'result_destination_ref', 'ide://receipts/inbox',
    'correlation_refs', jsonb_build_array(jsonb_build_object('ref', 'ide://attempt/one', 'digest', request_fingerprint, 'observed_at', '2026-10-01T00:00:00Z')),
    'idempotency_key', 'provider-disposable-request-key',
    'expires_at', '2026-10-02T00:00:00Z',
    'policy', jsonb_build_object(
      'side_effect_class', 'read_only', 'approval_requirement', 'none',
      'policy_profile_ref', 'policy://repo/read-only', 'data_classification', 'internal'
    ),
    'approval_refs', '[]'::jsonb
  );
  v_accept := lautowork.linkautowork_provider_accept(v_request, request_fingerprint);
  perform public.assert_true(v_accept->'record'->'request' = v_request, 'accept returns exact full invocation JSON');
  perform public.assert_true(v_accept->'record'->>'orgId' = org_a::text, 'accept returns the ProviderStore organization field');
  perform public.assert_true(v_accept->'record'->>'fingerprint' = request_fingerprint, 'accept returns the canonical fingerprint');
  perform public.assert_true(v_accept->'record'->>'version' = '1', 'accept returns the initial CAS version');
  perform public.assert_true(v_accept->>'replay' = 'false', 'first exact request is accepted once');

  v_replay := lautowork.linkautowork_provider_accept(v_request, request_fingerprint);
  perform public.assert_true(v_replay->'record'->'request' = v_request and v_replay->>'replay' = 'true', 'same canonical request replays its full request');
  begin
    perform lautowork.linkautowork_provider_accept(v_request || jsonb_build_object('input_ref', jsonb_build_object('ref', 'ide://input/changed', 'digest', request_fingerprint, 'observed_at', '2026-10-01T00:00:00Z')), request_fingerprint);
    raise exception 'changed JSON with the old fingerprint unexpectedly replayed';
  exception when unique_violation then null;
  end;

  v_record := lautowork.linkautowork_provider_get_request((v_request->>'request_id')::uuid);
  perform public.assert_true(v_record->'request' = v_request and v_record->>'attempts' = '0', 'request read round-trips the invocation and zero attempts');
  v_record := lautowork.linkautowork_provider_transition((v_request->>'request_id')::uuid, 1, 'queued');
  perform public.assert_true(v_record->'request' = v_request and v_record->>'state' = 'queued' and v_record->>'version' = '2', 'CAS transition returns the full request record');
  v_record := lautowork.linkautowork_provider_transition((v_request->>'request_id')::uuid, 2, 'running');
  perform public.assert_true(v_record->>'attempts' = '1' and v_record->>'state' = 'running', 'running transition returns its durable attempt count');

  v_receipt := jsonb_build_object(
    'contract_version', '2026-08-13.v1',
    'request_id', v_request->>'request_id',
    'receipt_id', 'b0000000-0000-0000-0000-000000000002',
    'state', 'succeeded',
    'accepted_at', '2026-10-01T00:00:00Z',
    'updated_at', '2026-10-01T00:01:00Z',
    'attempt_count', 1,
    'request_fingerprint', request_fingerprint,
    'automation', v_request->'automation',
    'result_refs', jsonb_build_array(jsonb_build_object('ref', 'ide://result/full', 'digest', request_fingerprint, 'classification', 'internal')),
    'evidence_refs', jsonb_build_array(jsonb_build_object('ref', 'ide://evidence/full', 'digest', request_fingerprint, 'classification', 'internal')),
    'uncertain_outcome', false
  );
  v_saved_receipt := lautowork.linkautowork_provider_write_receipt(v_receipt);
  perform public.assert_true(v_saved_receipt = v_receipt, 'receipt write returns the exact complete receipt JSON');
  perform public.assert_true((lautowork.linkautowork_provider_get_request((v_request->>'request_id')::uuid)->'receipt') = v_receipt, 'request read includes the complete receipt');
  perform public.assert_true(lautowork.linkautowork_provider_write_receipt(v_receipt) = v_receipt, 'same complete receipt is idempotent');
  begin
    perform lautowork.linkautowork_provider_write_receipt(v_receipt || jsonb_build_object('state', 'failed'));
    raise exception 'changed receipt with the same id unexpectedly replayed';
  exception when unique_violation then null;
  end;

  v_callback := jsonb_build_object(
    'request_id', v_request->>'request_id',
    'receipt_id', v_receipt->>'receipt_id',
    'org_id', org_a,
    'callback_binding_ref', v_request->'automation'->'configuration_ref'->>'ref',
    'source_timestamp', '2026-10-01T00:02:00Z',
    'receipt', v_receipt
  );
  perform public.assert_true(lautowork.linkautowork_provider_admit_callback(v_callback) = v_receipt, 'callback returns the complete persisted receipt');
  v_record := lautowork.linkautowork_provider_get_request((v_request->>'request_id')::uuid);
  perform public.assert_true(v_record->'request' = v_request and v_record->'receipt' = v_receipt and v_record ? 'callbackTimestamp', 'post-callback read returns request, receipt, and callback time');

  v_legacy_receipt_request := v_request || jsonb_build_object(
    'request_id', 'a0000000-0000-0000-0000-000000000003',
    'idempotency_key', 'provider-disposable-legacy-receipt-key'
  );
  perform lautowork.linkautowork_provider_accept(v_legacy_receipt_request, request_fingerprint);
  insert into lautowork.provider_receipts
    (id, request_id, org_id, state, attempt_count, evidence_ref, result_ref)
  values
    ('b0000000-0000-0000-0000-000000000003', (v_legacy_receipt_request->>'request_id')::uuid, org_a,
     'accepted', 0, 'ide://evidence/projected-only', 'ide://result/projected-only');
  begin
    perform lautowork.linkautowork_provider_get_request((v_legacy_receipt_request->>'request_id')::uuid);
    raise exception 'legacy receipt read unexpectedly fabricated the unavailable receipt';
  exception when sqlstate '55000' then
    if sqlerrm <> 'provider legacy receipt payload unavailable' then raise; end if;
  end;
  begin
    perform lautowork.linkautowork_provider_transition((v_legacy_receipt_request->>'request_id')::uuid, 1, 'queued');
    raise exception 'transition unexpectedly proceeded with an unavailable receipt';
  exception when sqlstate '55000' then
    if sqlerrm <> 'provider legacy receipt payload unavailable' then raise; end if;
  end;
  perform public.assert_true(
    (select state = 'accepted' and expected_version = 1 from lautowork.provider_requests where id=(v_legacy_receipt_request->>'request_id')::uuid),
    'legacy receipt transition fails before changing request state'
  );
  begin
    perform lautowork.linkautowork_provider_accept(v_legacy_receipt_request, request_fingerprint);
    raise exception 'legacy receipt replay unexpectedly omitted unavailable receipt data';
  exception when sqlstate '55000' then
    if sqlerrm <> 'provider legacy receipt payload unavailable' then raise; end if;
  end;

  perform lautowork.linkautowork_provider_set_kill_switch('ide-repository-status', true, 'platform://evidence/provider-killswitch/scoped-activate');
  v_killed := lautowork.linkautowork_provider_kill_switch_active('ide-repository-status');
  perform public.assert_true(v_killed, 'scoped kill switch activates for its automation');
  perform public.assert_true(not lautowork.linkautowork_provider_kill_switch_active('other-automation'), 'scoped kill switch leaves sibling automation available');
  perform lautowork.linkautowork_provider_set_kill_switch('ide-repository-status', false, 'platform://evidence/provider-killswitch/scoped-release');
  perform public.assert_true(not lautowork.linkautowork_provider_kill_switch_active('ide-repository-status'), 'scoped release overrides the latest scoped activation');
  perform lautowork.linkautowork_provider_set_kill_switch(null, true, 'platform://evidence/provider-killswitch/global-activate');
  perform public.assert_true(lautowork.linkautowork_provider_kill_switch_active('ide-repository-status'), 'global kill switch blocks all automations');
  perform lautowork.linkautowork_provider_set_kill_switch(null, false, 'platform://evidence/provider-killswitch/global-release');
  perform public.assert_true(not lautowork.linkautowork_provider_kill_switch_active('ide-repository-status'), 'global release restores the prior scoped state');
  begin
    perform lautowork.linkautowork_provider_set_kill_switch('ide-repository-status', true, 'raw reason text');
    raise exception 'raw kill-switch reason unexpectedly accepted';
  exception when invalid_parameter_value then null;
  end;

  perform set_config('request.jwt.claim.org_id', org_b::text, false);
  begin
    perform lautowork.linkautowork_provider_get_request((v_request->>'request_id')::uuid);
    raise exception 'cross-organization request read unexpectedly succeeded';
  exception when sqlstate '42501' then null;
  end;
  perform lautowork.linkautowork_provider_set_kill_switch('other-automation', true, 'platform://evidence/provider-killswitch/org-b');
  perform public.assert_true(lautowork.linkautowork_provider_kill_switch_active('other-automation'), 'kill switch is active only in its JWT organization');
  perform set_config('request.jwt.claim.org_id', org_a::text, false);
  perform public.assert_true(not lautowork.linkautowork_provider_kill_switch_active('other-automation'), 'organization B kill switch is invisible to organization A');
end $$;

reset role;
select 'AW-01 provider payload and kill-switch verification passed' as result;
