import { describe, expect, it } from 'vitest';
import { providerInvocationRequestSchema } from '../../../packages/automation-contracts/src/index.js';
import { bridgeN8nCallbackToProvider, n8nRuntimeCallbackSchema } from '../../src/services/runtime-dispatch/index.js';

const ORG = '11111111-1111-4111-8111-111111111111';
const DIGEST = `sha256:${'a'.repeat(64)}`;
const ISSUED_AT = '2026-08-13T00:00:00.000Z';
const EXPIRES_AT = '2099-08-13T00:00:00.000Z';
const REQUEST_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const RECEIPT_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

const request = providerInvocationRequestSchema.parse({
  contract_version: '2026-08-13.v1',
  protocol_version: 'http/1',
  request_id: REQUEST_ID,
  platform: { org_id: ORG, actor_id: 'caller', audience: 'lautowork', capability: 'catalogue.invoke', credential_id: 'credential-1', binding_id: 'binding-1', issued_at: ISSUED_AT, expires_at: EXPIRES_AT, revocation_ref: 'platform://revocations/current' },
  automation: { automation_id: 'ide-repository-status', version: '1.0.0', definition_digest: DIGEST, configuration_ref: { ref: 'autowork://config/ide-repository-status/1.0.0', digest: DIGEST, observed_at: ISSUED_AT } },
  operation_kind: 'precheck',
  input_ref: { ref: 'ide://inputs/status', digest: DIGEST, observed_at: ISSUED_AT },
  artifact_refs: [],
  result_destination_ref: 'ide://receipts/inbox',
  correlation_refs: [{ ref: 'ide://attempt/one', digest: DIGEST, observed_at: ISSUED_AT }],
  idempotency_key: 'runtime-dispatch-bridge-key',
  expires_at: EXPIRES_AT,
  policy: { side_effect_class: 'read_only', approval_requirement: 'none', policy_profile_ref: 'policy://repo/read-only', data_classification: 'internal' },
  approval_refs: [],
});

describe('n8n callback bridge', () => {
  it('maps a bounded n8n callback onto the AW-02 provider callback schema', () => {
    const bridged = bridgeN8nCallbackToProvider({
      request_id: REQUEST_ID,
      receipt_id: RECEIPT_ID,
      org_id: ORG,
      n8n_execution_ref: 'n8n://executions/exec-9',
      source_timestamp: '2026-08-13T00:01:00.000Z',
      outcome: 'failed',
      request_fingerprint: DIGEST,
      callback_binding_ref: request.automation.configuration_ref.ref,
      evidence_ref: 'autowork://evidence/n8n/exec-9',
    }, request, DIGEST, ISSUED_AT);
    expect(bridged.receipt.state).toBe('failed');
    expect(bridged.receipt.uncertain_outcome).toBe(true);
    expect(bridged.receipt.evidence_refs.some((entry) => entry.ref.startsWith('n8n://'))).toBe(true);
    expect(bridged).not.toHaveProperty('payload');
  });

  it('rejects secret-shaped values, raw n8n payloads, and unbound callbacks', () => {
    expect(() => n8nRuntimeCallbackSchema.parse({
      request_id: REQUEST_ID,
      receipt_id: RECEIPT_ID,
      org_id: ORG,
      n8n_execution_ref: 'n8n://executions/exec-9',
      source_timestamp: '2026-08-13T00:01:00.000Z',
      outcome: 'succeeded',
      request_fingerprint: DIGEST,
      callback_binding_ref: request.automation.configuration_ref.ref,
      payload: { nodes: [] },
    })).toThrow();
    expect(() => bridgeN8nCallbackToProvider({
      request_id: REQUEST_ID,
      receipt_id: RECEIPT_ID,
      org_id: ORG,
      n8n_execution_ref: 'n8n://executions/exec-9',
      source_timestamp: '2026-08-13T00:01:00.000Z',
      outcome: 'succeeded',
      request_fingerprint: DIGEST,
      callback_binding_ref: request.automation.configuration_ref.ref,
      token: 'sk-thisisnotareal-secretvalue',
    }, request, DIGEST, ISSUED_AT)).toThrow(/secret-shaped/);
    expect(() => bridgeN8nCallbackToProvider({
      request_id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
      receipt_id: RECEIPT_ID,
      org_id: ORG,
      n8n_execution_ref: 'n8n://executions/exec-9',
      source_timestamp: '2026-08-13T00:01:00.000Z',
      outcome: 'succeeded',
      request_fingerprint: DIGEST,
      callback_binding_ref: request.automation.configuration_ref.ref,
    }, request, DIGEST, ISSUED_AT)).toThrow(/bind/);
  });
});
