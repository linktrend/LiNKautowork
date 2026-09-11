import { describe, expect, it } from 'vitest';
import type { z } from 'zod';
import {
  PROVIDER_CONTRACT_VERSION,
  providerCanonicalRequestFingerprint,
  providerInvocationRequestSchema,
} from '../src/provider-contract.js';
import {
  PROVIDER_EVENT_PAGE_MAX,
  PROVIDER_INVOKER_RPCS,
  PROVIDER_PERSISTENCE_CONTRACT_VERSION,
  PROVIDER_RPC_SECURITY_MODE,
  assertProviderRuntimeInvoker,
  boundProviderEventPageLimit,
  compareProviderIdempotencyContent,
  projectProviderDurableRequest,
} from '../src/provider-persistence.js';

const digest = `sha256:${'a'.repeat(64)}`;
const org = '00000000-0000-0000-0000-000000000001';
const at = '2026-08-13T00:00:00.000Z';
const later = '2026-08-14T00:00:00.000Z';
const ref = (name: string) => `provider://${name}`;

function request(overrides: Record<string, unknown> = {}): z.input<typeof providerInvocationRequestSchema> {
  return {
    contract_version: PROVIDER_CONTRACT_VERSION, protocol_version: 'http-v1', request_id: '00000000-0000-0000-0000-000000000010',
    platform: { org_id: org, actor_id: 'service-1', audience: 'autowork', capability: 'automation.invoke', credential_id: 'credential-1', binding_id: 'binding-1', issued_at: at, expires_at: later, revocation_ref: ref('revocations/active') },
    automation: { automation_id: 'repo-precheck', version: '1.0.0', definition_digest: digest, configuration_ref: { ref: ref('config/1'), digest, observed_at: at } },
    operation_kind: 'precheck', input_ref: { ref: ref('input/1'), digest, observed_at: at }, artifact_refs: [], result_destination_ref: ref('result/1'), correlation_refs: [{ ref: ref('correlation/1'), digest, observed_at: at }], idempotency_key: 'idempotency-key-0001', expires_at: later,
    policy: { side_effect_class: 'read_only', approval_requirement: 'none', policy_profile_ref: ref('policy/1'), data_classification: 'internal' }, approval_refs: [],
    ...overrides,
  } as z.input<typeof providerInvocationRequestSchema>;
}

describe('provider persistence contract', () => {
  it('names only SECURITY INVOKER RPCs and never public/service-role bypass', () => {
    expect(PROVIDER_PERSISTENCE_CONTRACT_VERSION).toBe('aw-02.v1');
    expect(PROVIDER_RPC_SECURITY_MODE).toBe('INVOKER');
    expect(PROVIDER_INVOKER_RPCS).toContain('linkautowork_provider_accept');
    expect(assertProviderRuntimeInvoker({ org_id: org, jwt_role: 'runtime', claim_org_id: org }).jwt_role).toBe('runtime');
    expect(() => assertProviderRuntimeInvoker({ org_id: org, jwt_role: 'service_role' })).toThrow(/service-role or public bypass/);
    expect(() => assertProviderRuntimeInvoker({ org_id: org, jwt_role: 'runtime', claim_org_id: '00000000-0000-0000-0000-000000000002' })).toThrow();
  });

  it('replays identical (org_id, idempotency_key) content and fails closed on changed content', () => {
    const parsed = providerInvocationRequestSchema.parse(request());
    const fingerprint = providerCanonicalRequestFingerprint(request());
    const durable = projectProviderDurableRequest(parsed, fingerprint);
    expect(durable.request_fingerprint).toBe(fingerprint);
    expect(durable).not.toHaveProperty('input_ref');
    expect(compareProviderIdempotencyContent({ org_id: org, idempotency_key: parsed.idempotency_key, request_fingerprint: fingerprint }, parsed)).toBe('replay');
    expect(() => compareProviderIdempotencyContent({ org_id: org, idempotency_key: parsed.idempotency_key, request_fingerprint: fingerprint }, providerInvocationRequestSchema.parse(request({ result_destination_ref: ref('result/changed') })))).toThrow(/changed canonical/);
    expect(() => compareProviderIdempotencyContent({ org_id: '00000000-0000-0000-0000-000000000002', idempotency_key: parsed.idempotency_key, request_fingerprint: fingerprint }, parsed)).toThrow(/organisation isolation/);
  });

  it('bounds organisation-scoped event pages', () => {
    expect(boundProviderEventPageLimit(1)).toBe(1);
    expect(boundProviderEventPageLimit(PROVIDER_EVENT_PAGE_MAX)).toBe(100);
    expect(() => boundProviderEventPageLimit(0)).toThrow(/1 and 100/);
    expect(() => boundProviderEventPageLimit(101)).toThrow(/1 and 100/);
  });
});
