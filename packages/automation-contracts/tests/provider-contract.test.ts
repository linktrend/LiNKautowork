import { describe, expect, it } from 'vitest';
import type { z } from 'zod';
import {
  PROVIDER_CONTRACT_VERSION,
  assertProviderIdempotencyFingerprint,
  providerCallbackSchema,
  providerCanonicalRequestFingerprint,
  providerCapabilityStatusSchema,
  providerInvocationRequestSchema,
  validateProviderInvocation,
} from '../src/provider-contract.js';

const digest = `sha256:${'a'.repeat(64)}`;
const org = '00000000-0000-0000-0000-000000000001';
const requestId = '00000000-0000-0000-0000-000000000010';
const receiptId = '00000000-0000-0000-0000-000000000011';
const at = '2026-08-13T00:00:00.000Z';
const later = '2026-08-14T00:00:00.000Z';
const ref = (name: string) => `provider://${name}`;

function request(overrides: Record<string, unknown> = {}): z.input<typeof providerInvocationRequestSchema> {
  return {
    contract_version: PROVIDER_CONTRACT_VERSION, protocol_version: 'http-v1', request_id: requestId,
    platform: { org_id: org, actor_id: 'service-1', audience: 'autowork', capability: 'automation.invoke', credential_id: 'credential-1', binding_id: 'binding-1', issued_at: at, expires_at: later, revocation_ref: ref('revocations/active') },
    automation: { automation_id: 'repo-precheck', version: '1.0.0', definition_digest: digest, configuration_ref: { ref: ref('config/1'), digest, observed_at: at } },
    operation_kind: 'precheck', input_ref: { ref: ref('input/1'), digest, observed_at: at }, artifact_refs: [], result_destination_ref: ref('result/1'), correlation_refs: [{ ref: ref('correlation/1'), digest, observed_at: at }], idempotency_key: 'idempotency-key-0001', expires_at: later,
    policy: { side_effect_class: 'read_only', approval_requirement: 'none', policy_profile_ref: ref('policy/1'), data_classification: 'internal' }, approval_refs: [],
    ...overrides,
  } as z.input<typeof providerInvocationRequestSchema>;
}

describe('provider contract family', () => {
  it('accepts a compact exact-version request and yields a stable nested canonical fingerprint', () => {
    const parsed = validateProviderInvocation(request(), new Date(at));
    expect(parsed.automation.version).toBe('1.0.0');
    expect(providerCanonicalRequestFingerprint(request())).toBe(providerCanonicalRequestFingerprint({ ...request(), platform: { ...request().platform, audience: 'autowork' } }));
    expect(() => assertProviderIdempotencyFingerprint(providerCanonicalRequestFingerprint(request()), request({ result_destination_ref: ref('result/changed') }))).toThrow(/changed canonical/);
  });

  it('rejects expired, revoked, unbounded and unsafe invocation forms', () => {
    expect(() => validateProviderInvocation(request({ expires_at: at }), new Date(at))).toThrow(/expired/);
    expect(() => validateProviderInvocation(request({ platform: { ...request().platform, revocation_ref: ref('revocations/revoked') } }), new Date(at))).toThrow(/revoked/);
    expect(() => providerInvocationRequestSchema.parse(request({ operation_kind: 'order_placement' }))).toThrow();
    expect(() => providerInvocationRequestSchema.parse(request({ input_ref: { ref: ref('input/1'), digest, observed_at: at, raw_payload: 'forbidden' } }))).toThrow();
    expect(() => providerInvocationRequestSchema.parse(request({ artifact_refs: [{ ref: ref('artifact/1'), digest, media_type: 'application/pdf', byte_size: 10_000_001, provenance_ref: ref('source/1'), retention_profile_ref: ref('retention/1'), retrieval_authorization_ref: ref('authorization/1') }] }))).toThrow();
  });

  it('requires an exact handoff for external assistance and a suppression policy for outreach', () => {
    expect(() => providerInvocationRequestSchema.parse(request({ operation_kind: 'external_assistance' }))).toThrow(/handoff/);
    expect(() => providerInvocationRequestSchema.parse(request({ operation_kind: 'outreach_adapter', policy: { ...request().policy } }))).toThrow(/suppression/);
  });

  it('requires two distinct people and a sanitized candidate for dual approval', () => {
    const approval = { approval_ref: ref('approval/1'), approver_id: 'lawyer-1', credential_id: 'credential-1', binding_id: 'binding-1', role: 'matter_lawyer' as const, expires_at: later };
    expect(() => providerInvocationRequestSchema.parse(request({ policy: { ...request().policy, approval_requirement: 'dual_human' }, approval_refs: [approval, { ...approval, approval_ref: ref('approval/2') }] }))).toThrow(/distinct/);
    expect(providerInvocationRequestSchema.parse(request({ policy: { ...request().policy, approval_requirement: 'dual_human' }, approval_refs: [approval, { ...approval, approval_ref: ref('approval/2'), approver_id: 'tenant-admin-1', credential_id: 'credential-2', binding_id: 'binding-2', role: 'tenant_administrator' }], sanitized_brain_candidate_ref: ref('brain/sanitized/1') })).approval_refs).toHaveLength(2);
  });

  it('binds callbacks and makes capability truthfulness explicit', () => {
    const receipt = { contract_version: PROVIDER_CONTRACT_VERSION, request_id: requestId, receipt_id: receiptId, state: 'succeeded', accepted_at: at, updated_at: at, attempt_count: 1, request_fingerprint: digest, automation: request().automation, result_refs: [], evidence_refs: [] };
    expect(providerCallbackSchema.parse({ request_id: requestId, receipt_id: receiptId, org_id: org, callback_binding_ref: ref('callback/1'), source_timestamp: at, receipt }).receipt.receipt_id).toBe(receiptId);
    expect(() => providerCallbackSchema.parse({ request_id: '00000000-0000-0000-0000-000000000012', receipt_id: receiptId, org_id: org, callback_binding_ref: ref('callback/1'), source_timestamp: at, receipt })).toThrow(/bind/);
    expect(providerCapabilityStatusSchema.parse({ capability: 'catalogue', state: 'available', observed_at: at, does_not_prove: ['automation_run', 'consumer_outcome', 'consumer_gate', 'external_side_effect', 'e2e_readiness', 'production_readiness'] }).does_not_prove).toContain('production_readiness');
  });
});
