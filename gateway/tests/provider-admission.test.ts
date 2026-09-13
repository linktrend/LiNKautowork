import { randomUUID } from 'node:crypto';
import express from 'express';
import request from 'supertest';
import { describe, expect, it } from 'vitest';
import { createProviderV2Router } from '../src/routes/provider-v2/index.js';
import { ProviderAdmissionService } from '../src/services/provider-admission.js';
import { createAcceptedProviderReceipt, InMemoryProviderStore, ProviderStoreError } from '../src/services/provider-store.js';
import type { ProviderInvocationRequest } from '../../packages/automation-contracts/src/provider-contract.js';

const ORG_A = '11111111-1111-4111-8111-111111111111';
const ORG_B = '22222222-2222-4222-8222-222222222222';
const DIGEST = `sha256:${'a'.repeat(64)}`;
const NOW = new Date(Date.now() - 60_000).toISOString();
const EXPIRES = new Date(Date.now() + 86_400_000).toISOString();

function invocation(orgId = ORG_A, overrides: Partial<ProviderInvocationRequest> = {}): ProviderInvocationRequest {
  return {
    contract_version: '2026-08-13.v1', protocol_version: 'http/1', request_id: randomUUID(),
    platform: { org_id: orgId, actor_id: 'ide-client', audience: 'lautowork', capability: 'catalogue.invoke', credential_id: 'credential-1', binding_id: 'binding-1', issued_at: NOW, expires_at: EXPIRES, revocation_ref: 'platform://revocations/current' },
    automation: { automation_id: 'repo-status', version: '1.0.0', definition_digest: DIGEST, configuration_ref: { ref: 'autowork://config/repo-status-v1', digest: DIGEST, observed_at: NOW } },
    operation_kind: 'precheck', input_ref: { ref: 'ide://inputs/repo-status', digest: DIGEST, observed_at: NOW }, artifact_refs: [], result_destination_ref: 'ide://receipts/inbox', correlation_refs: [{ ref: 'ide://attempt/one', digest: DIGEST, observed_at: NOW }],
    idempotency_key: 'provider-admission-idempotency-key', expires_at: EXPIRES, policy: { side_effect_class: 'read_only', approval_requirement: 'none', policy_profile_ref: 'policy://repo/read-only', data_classification: 'internal' }, approval_refs: [], ...overrides,
  };
}

function appFor(store: InMemoryProviderStore, orgId = ORG_A) {
  const app = express();
  app.use(express.json());
  app.use(createProviderV2Router(store, () => orgId));
  return app;
}

describe('provider admission lifecycle and durable event boundary', () => {
  it('admits a request, replays identical content, and fails closed on changed idempotency content', async () => {
    const store = new InMemoryProviderStore();
    const admission = new ProviderAdmissionService(store);
    const input = invocation();
    const first = await admission.admit(ORG_A, input, new Date(NOW));
    const replay = await admission.admit(ORG_A, structuredClone(input), new Date(NOW));
    expect(first.replay).toBe(false);
    expect(replay.replay).toBe(true);
    expect(replay.request_id).toBe(first.request_id);
    await expect(admission.admit(ORG_A, { ...structuredClone(input), input_ref: { ...input.input_ref, ref: 'ide://inputs/changed' } }, new Date(NOW))).rejects.toMatchObject({ category: 'conflict' });
  });

  it('requires a runtime JWT invoker and never accepts service-role bypass', async () => {
    const store = new InMemoryProviderStore();
    await expect(store.accept(ORG_A, invocation(), new Date(NOW), { org_id: ORG_A, jwt_role: 'service_role' })).rejects.toMatchObject({ category: 'forbidden' });
    await expect(store.invokeProviderRpc('linkautowork_provider_accept', { p_request: invocation(), p_request_fingerprint: 'sha256:dead' }, ORG_A, { org_id: ORG_A, jwt_role: 'anon' })).rejects.toMatchObject({ category: 'forbidden' });
  });

  it('records attempts, configuration-bound receipts, org-scoped events, and pending outbox without live delivery', async () => {
    const store = new InMemoryProviderStore();
    const input = invocation();
    const accepted = await store.accept(ORG_A, input, new Date(NOW));
    const queued = await store.transition(ORG_A, accepted.record.request.request_id, 1, 'queued');
    const running = await store.transition(ORG_A, queued.request.request_id, queued.version, 'running');
    expect(store.listAttempts(ORG_A, running.request.request_id)).toEqual([expect.objectContaining({ attempt_number: 1, state: 'running', job_retry: false, outbox_retry: false })]);
    const receipt = createAcceptedProviderReceipt(running, new Date(NOW));
    await store.writeReceipt(ORG_A, { ...receipt, state: 'succeeded', attempt_count: 1 });
    await expect(store.writeReceipt(ORG_A, { ...receipt, receipt_id: randomUUID(), automation: { ...receipt.automation, configuration_ref: { ...receipt.automation.configuration_ref, digest: `sha256:${'b'.repeat(64)}` } } })).rejects.toMatchObject({ category: 'forbidden' });
    const page = await store.listEvents(ORG_A, null, 10);
    expect(page.events).toHaveLength(1);
    expect(page.events[0]).not.toHaveProperty('input_ref');
    expect(page.events[0].payload_ref.digest).toBe(accepted.record.fingerprint);
    expect((await store.listEvents(ORG_B, null, 10)).events).toHaveLength(0);
    expect(store.listOutbox(ORG_A)).toEqual([expect.objectContaining({ kind: 'event_delivery', state: 'pending', request_id: input.request_id })]);
    expect(store.listOutbox(ORG_B)).toHaveLength(0);
    expect(() => store.deliverOutbox()).toThrow(ProviderStoreError);
  });

  it('exposes source-only v2 admission, CAS transition, receipt, and bounded event routes', async () => {
    const store = new InMemoryProviderStore();
    const app = appFor(store);
    const input = invocation();
    const first = await request(app).post('/v2/provider/requests').send(input).expect(202);
    expect(first.body.status).not.toHaveProperty('input_ref');
    await request(app).post('/v2/provider/requests').send(input).expect(200);
    await request(app).post('/v2/provider/requests').send({ ...input, input_ref: { ...input.input_ref, ref: 'ide://inputs/changed' } }).expect(409);
    await request(app).post(`/v2/provider/requests/${input.request_id}/transitions`).send({ expected_version: 1, next_state: 'queued' }).expect(200);
    await request(app).get(`/v2/provider/requests/${input.request_id}/receipt`).expect(404);
    const events = await request(app).get('/v2/provider/events?limit=10').expect(200);
    expect(events.body.events).toHaveLength(1);
    await request(app).get('/v2/provider/events?limit=101').expect(403);
    const foreign = appFor(store, ORG_B);
    await request(foreign).get(`/v2/provider/requests/${input.request_id}`).expect(403);
  });
});
