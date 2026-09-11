import { randomUUID } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { providerInvocationRequestSchema, type ProviderInvocationRequest } from '../../../packages/automation-contracts/src/index.js';
import { RuntimeDispatchError, RuntimeDispatchService } from '../../src/services/runtime-dispatch/index.js';

const ORG = '11111111-1111-4111-8111-111111111111';
const OTHER = '22222222-2222-4222-8222-222222222222';
const DIGEST = `sha256:${'a'.repeat(64)}`;
const ISSUED_AT = '2026-08-13T00:00:00.000Z';
const EXPIRES_AT = '2099-08-13T00:00:00.000Z';

function invocation(overrides: Record<string, unknown> = {}): ProviderInvocationRequest {
  return providerInvocationRequestSchema.parse({
    contract_version: '2026-08-13.v1',
    protocol_version: 'http/1',
    request_id: randomUUID(),
    platform: { org_id: ORG, actor_id: 'caller', audience: 'lautowork', capability: 'catalogue.invoke', credential_id: 'credential-1', binding_id: 'binding-1', issued_at: ISSUED_AT, expires_at: EXPIRES_AT, revocation_ref: 'platform://revocations/current' },
    automation: { automation_id: 'ide-repository-status', version: '1.0.0', definition_digest: DIGEST, configuration_ref: { ref: 'autowork://config/ide-repository-status/1.0.0', digest: DIGEST, observed_at: ISSUED_AT } },
    operation_kind: 'precheck',
    input_ref: { ref: 'ide://inputs/status', digest: DIGEST, observed_at: ISSUED_AT },
    artifact_refs: [],
    result_destination_ref: 'ide://receipts/inbox',
    correlation_refs: [{ ref: 'ide://attempt/one', digest: DIGEST, observed_at: ISSUED_AT }],
    idempotency_key: 'runtime-dispatch-idempotency-key',
    expires_at: EXPIRES_AT,
    policy: { side_effect_class: 'read_only', approval_requirement: 'none', policy_profile_ref: 'policy://repo/read-only', data_classification: 'internal' },
    approval_refs: [],
    ...overrides,
  });
}

describe('RuntimeDispatchService', () => {
  it('queues durable n8n activation without dispatching and replays identical idempotency keys', () => {
    const service = new RuntimeDispatchService({ activationInterfaceSupported: true, now: () => new Date(ISSUED_AT) });
    const request = invocation();
    const first = service.activate(ORG, request);
    expect(first.replay).toBe(false);
    expect(first.disposition).toBe('queued');
    expect(first.activation.n8n_dispatched).toBe(false);
    expect(first.activation.live_n8n_activation).toBe('hold');
    expect(first.activation).not.toHaveProperty('input_ref');
    const replay = service.activate(ORG, request);
    expect(replay.replay).toBe(true);
    expect(replay.activation.request_id).toBe(first.activation.request_id);
    expect(replay.activation.receipt_id).toBe(first.activation.receipt_id);
  });

  it('fails closed on changed idempotency content, tenant mismatch, kill switch, and missing activation interface', () => {
    const service = new RuntimeDispatchService({ activationInterfaceSupported: true });
    const request = invocation();
    service.activate(ORG, request);
    expect(() => service.activate(ORG, invocation({ input_ref: { ref: 'ide://inputs/changed', digest: DIGEST, observed_at: ISSUED_AT } }))).toThrow(RuntimeDispatchError);
    expect(() => service.activate(OTHER, request)).toThrow(/organisation/);
    const killed = new RuntimeDispatchService({ activationInterfaceSupported: true, isKilled: () => true });
    expect(() => killed.activate(ORG, invocation({ idempotency_key: 'runtime-dispatch-killed-key' }))).toThrow(/kill switch/);
    const unsupported = new RuntimeDispatchService({ activationInterfaceSupported: false });
    expect(() => unsupported.activate(ORG, invocation({ idempotency_key: 'runtime-dispatch-unsupported-key' }))).toThrow(/unavailable/);
  });

  it('holds external assistance and rejects consumer factory destinations', () => {
    const service = new RuntimeDispatchService({ activationInterfaceSupported: true });
    expect(() => service.activate(ORG, invocation({
      operation_kind: 'external_assistance',
      brain_handoff_ref: { ref: 'brain://handoff/exact', digest: DIGEST, observed_at: ISSUED_AT },
      idempotency_key: 'runtime-dispatch-external-key',
    }))).toThrow(/HOLD/);
    expect(() => service.activate(ORG, invocation({
      result_destination_ref: 'ide://issue/ledger-gate',
      idempotency_key: 'runtime-dispatch-rejected-key',
    }))).toThrow(/not dispatchable/);
  });

  it('admits a bounded n8n callback once, then rejects replay, binding, fingerprint, and receipt mismatches', () => {
    const service = new RuntimeDispatchService({ activationInterfaceSupported: true, now: () => new Date(ISSUED_AT) });
    const request = invocation({ idempotency_key: 'runtime-dispatch-callback-key' });
    const activation = service.activate(ORG, request).activation;
    const callback = {
      request_id: request.request_id,
      receipt_id: activation.receipt_id,
      org_id: ORG,
      n8n_execution_ref: 'n8n://executions/exec-1',
      source_timestamp: '2026-08-13T00:01:00.000Z',
      outcome: 'succeeded' as const,
      request_fingerprint: activation.fingerprint,
      callback_binding_ref: request.automation.configuration_ref.ref,
    };
    const receipt = service.admitCallback(ORG, callback);
    expect(receipt.state).toBe('succeeded');
    expect(receipt.uncertain_outcome).toBe(true);
    expect(receipt.request_id).toBe(request.request_id);
    expect(() => service.admitCallback(ORG, callback)).toThrow(/replayed|out of order/);
    expect(() => service.admitCallback(ORG, { ...callback, source_timestamp: '2026-08-13T00:02:00.000Z', callback_binding_ref: 'autowork://forged/config' })).toThrow(/binding/);
    expect(() => service.admitCallback(ORG, { ...callback, source_timestamp: '2026-08-13T00:02:00.000Z', request_fingerprint: `sha256:${'b'.repeat(64)}` })).toThrow(/fingerprint/);
    expect(() => service.admitCallback(ORG, { ...callback, source_timestamp: '2026-08-13T00:02:00.000Z', receipt_id: randomUUID() })).toThrow(/receipt/);
    expect(() => service.admitCallback(OTHER, { ...callback, source_timestamp: '2026-08-13T00:02:00.000Z', org_id: OTHER })).toThrow(/isolation|organisation/);
  });
});
