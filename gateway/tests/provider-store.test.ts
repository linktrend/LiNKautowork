import { randomUUID } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { providerCallbackSchema, providerEventSchema, type ProviderInvocationRequest } from '../../packages/automation-contracts/src/provider-contract.js';
import { createAcceptedProviderReceipt, InMemoryProviderStore, ProviderStoreError } from '../src/services/provider-store.js';

const ORG_A = '11111111-1111-4111-8111-111111111111';
const ORG_B = '22222222-2222-4222-8222-222222222222';
const DIGEST = `sha256:${'a'.repeat(64)}`;
const NOW = '2026-08-13T12:00:00.000Z';

function request(orgId = ORG_A, overrides: Partial<ProviderInvocationRequest> = {}): ProviderInvocationRequest {
  return {
    contract_version: '2026-08-13.v1', protocol_version: 'http/1', request_id: randomUUID(),
    platform: { org_id: orgId, actor_id: 'ide-client', audience: 'lautowork', capability: 'catalogue.invoke', credential_id: 'credential-1', binding_id: 'binding-1', issued_at: NOW, expires_at: '2026-08-14T12:00:00.000Z', revocation_ref: 'platform://revocations/current' },
    automation: { automation_id: 'repo-status', version: '1.0.0', definition_digest: DIGEST, configuration_ref: { ref: 'autowork://config/repo-status-v1', digest: DIGEST, observed_at: NOW } },
    operation_kind: 'precheck', input_ref: { ref: 'ide://inputs/repo-status', digest: DIGEST, observed_at: NOW }, artifact_refs: [], result_destination_ref: 'ide://receipts/inbox', correlation_refs: [{ ref: 'ide://attempt/one', digest: DIGEST, observed_at: NOW }],
    idempotency_key: 'provider-store-idempotency-key', expires_at: '2026-08-14T12:00:00.000Z', policy: { side_effect_class: 'read_only', approval_requirement: 'none', policy_profile_ref: 'policy://repo/read-only', data_classification: 'internal' }, approval_refs: [], ...overrides,
  };
}

describe('InMemoryProviderStore', () => {
  it('accepts one canonical request and replays the same logical durable request', async () => {
    const store = new InMemoryProviderStore(); const input = request();
    const first = await store.accept(ORG_A, input, new Date(NOW));
    const replay = await store.accept(ORG_A, structuredClone(input), new Date(NOW));
    expect(first.replay).toBe(false); expect(replay.replay).toBe(true); expect(replay.record.request.request_id).toBe(first.record.request.request_id);
  });

  it('fails closed for changed-content idempotency conflicts and authoritative org mismatch', async () => {
    const store = new InMemoryProviderStore(); const input = request(); await store.accept(ORG_A, input, new Date(NOW));
    await expect(store.accept(ORG_A, { ...structuredClone(input), input_ref: { ...input.input_ref, ref: 'ide://inputs/changed' } }, new Date(NOW))).rejects.toMatchObject({ category: 'conflict' });
    await expect(store.accept(ORG_B, input, new Date(NOW))).rejects.toMatchObject({ category: 'forbidden' });
    await expect(store.getRequest(ORG_B, input.request_id)).rejects.toMatchObject({ category: 'forbidden' });
  });

  it('honours org and automation kill switches before accepting or starting work', async () => {
    const store = new InMemoryProviderStore(); await store.setKillSwitch(ORG_A, 'repo-status', true);
    await expect(store.accept(ORG_A, request(), new Date(NOW))).rejects.toMatchObject({ category: 'blocked' });
    await store.setKillSwitch(ORG_A, 'repo-status', false); const accepted = await store.accept(ORG_A, request(), new Date(NOW));
    await store.setKillSwitch(ORG_A, null, true);
    await expect(store.transition(ORG_A, accepted.record.request.request_id, 1, 'queued')).rejects.toMatchObject({ category: 'blocked' });
  });

  it('uses CAS and terminal lifecycle rules, and binds immutable receipts to the exact request configuration', async () => {
    const store = new InMemoryProviderStore(); const accepted = await store.accept(ORG_A, request(), new Date(NOW));
    await expect(store.transition(ORG_A, accepted.record.request.request_id, 2, 'queued')).rejects.toMatchObject({ category: 'invalid_state' });
    const queued = await store.transition(ORG_A, accepted.record.request.request_id, 1, 'queued');
    const running = await store.transition(ORG_A, queued.request.request_id, queued.version, 'running');
    const receipt = createAcceptedProviderReceipt(running, new Date(NOW));
    const saved = await store.writeReceipt(ORG_A, { ...receipt, state: 'succeeded', attempt_count: 1 });
    expect(saved.request_id).toBe(running.request.request_id);
    await expect(store.transition(ORG_A, running.request.request_id, running.version, 'failed')).rejects.toMatchObject({ category: 'invalid_state' });
    await expect(store.writeReceipt(ORG_A, { ...saved, receipt_id: randomUUID() })).rejects.toMatchObject({ category: 'conflict' });
  });

  it('rejects forged, replayed, mismatched, and out-of-order callbacks', async () => {
    const store = new InMemoryProviderStore(); const accepted = await store.accept(ORG_A, request(), new Date(NOW));
    const receipt = createAcceptedProviderReceipt(accepted.record, new Date(NOW));
    const callback = providerCallbackSchema.parse({ request_id: accepted.record.request.request_id, receipt_id: receipt.receipt_id, org_id: ORG_A, callback_binding_ref: accepted.record.request.automation.configuration_ref.ref, source_timestamp: '2026-08-13T12:01:00.000Z', receipt });
    await store.admitCallback(ORG_A, callback);
    await expect(store.admitCallback(ORG_A, callback)).rejects.toMatchObject({ category: 'invalid_callback' });
    await expect(store.admitCallback(ORG_A, { ...callback, source_timestamp: '2026-08-13T12:00:59.000Z' })).rejects.toMatchObject({ category: 'invalid_callback' });
    await expect(store.admitCallback(ORG_A, { ...callback, callback_binding_ref: 'autowork://config/forged' })).rejects.toMatchObject({ category: 'invalid_callback' });
    await expect(store.admitCallback(ORG_B, { ...callback, org_id: ORG_B })).rejects.toMatchObject({ category: 'forbidden' });
  });

  it('keeps events tenant-scoped, deduplicated and bounded by an authorized cursor', async () => {
    const store = new InMemoryProviderStore();
    const event = (cursor: string) => providerEventSchema.parse({ event_id: randomUUID(), source_ref: 'autowork://outbox/request', cursor, correlation_refs: [], occurred_at: NOW, type: 'request', payload_ref: { ref: `autowork://payload/${cursor}`, digest: DIGEST, observed_at: NOW } });
    await store.appendEvent(ORG_A, event('cursor-1')); await store.appendEvent(ORG_A, event('cursor-2'));
    const page = await store.listEvents(ORG_A, null, 1); expect(page.events).toHaveLength(1); expect(page.next_cursor).toBe('cursor-2');
    await expect(store.listEvents(ORG_A, 'missing', 1)).rejects.toMatchObject({ category: 'not_found' });
    await expect(store.listEvents(ORG_A, null, 101)).rejects.toMatchObject({ category: 'forbidden' });
    expect((await store.listEvents(ORG_B, null, 10)).events).toHaveLength(0);
  });
});
