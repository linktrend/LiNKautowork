import { createHmac, randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import request from 'supertest';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createApp, type AppDeps } from '../src/app.js';
import type { AppEnv } from '../src/config/env.js';
import { N8nClient } from '../src/integrations/n8n-client.js';
import { NonceStore } from '../src/lib/nonce-store.js';
import { InMemoryProviderStore } from '../src/services/provider-store.js';
import { connectionHealthPackageDigests, loadConnectionHealthPackage, ProviderRouteService, type ProviderInvocationIdentity } from '../src/services/provider-route-service.js';

const orgId = '11111111-1111-4111-8111-111111111111';
const issuedAt = new Date(Date.now() - 60_000).toISOString();
const expiresAt = new Date(Date.now() + 60_000).toISOString();
const webhookToken = 'test-only-header-token';
const platformSecret = 'ltfx.provider.connection.health.test.secret.15.1.v1';
const identity: ProviderInvocationIdentity = { subject: 'canary-agent', credentialId: 'credential-215', runtimeBindingId: 'binding-215', issuedAt, expiresAt, audience: ['linkautowork-gateway'] };

function input() {
  return {
    contract_version: '2026-08-13.v1', protocol_version: 'http/1', request_id: randomUUID(),
    platform: { org_id: orgId, actor_id: identity.subject, audience: 'lautowork', capability: 'catalogue.invoke', credential_id: identity.credentialId, binding_id: identity.runtimeBindingId, issued_at: issuedAt, expires_at: expiresAt, revocation_ref: 'platform://revocations/current' },
    automation: { automation_id: 'linkautowork-connection-health', version: '1.0.0', definition_digest: connectionHealthPackageDigests.definition, configuration_ref: { ref: 'autowork://config/linkautowork-connection-health/1.0.0', digest: connectionHealthPackageDigests.configuration, observed_at: issuedAt } },
    operation_kind: 'precheck', input_ref: { ref: 'autowork://inputs/linkautowork-connection-health/empty-v1', digest: connectionHealthPackageDigests.input, observed_at: issuedAt }, artifact_refs: [], result_destination_ref: 'autowork://receipts/connection-health', correlation_refs: [{ ref: 'autowork://attempt/connection-health', digest: connectionHealthPackageDigests.definition, observed_at: issuedAt }], idempotency_key: `connection-health-${randomUUID()}`, expires_at: expiresAt,
    policy: { side_effect_class: 'read_only', approval_requirement: 'none', policy_profile_ref: 'autowork://policies/linkautowork-connection-health/read-only-v1', data_classification: 'internal' }, approval_refs: [],
  };
}

function exactResponse(payload: { request_id: string; request_fingerprint: string }) {
  return { status: 'ok', scope: 'provider_to_n8n_dispatch', automation_id: 'linkautowork-connection-health', version: '1.0.0', request_id: payload.request_id, request_fingerprint: payload.request_fingerprint, execution_id: 'exec-215' };
}

function platformToken() {
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const claims = Buffer.from(JSON.stringify({ iss: 'platform-test', aud: 'linkautowork-gateway', sub: identity.subject, exp: Math.floor(Date.now() / 1000) + 3600, service: 'canary-client', org_id: orgId, org_entitlements: [orgId], credential_id: identity.credentialId, binding_id: identity.runtimeBindingId, issued_at: issuedAt, expires_at: expiresAt, jti: 'provider-connection-health-test' })).toString('base64url');
  return `${header}.${claims}.${createHmac('sha256', platformSecret).update(`${header}.${claims}`).digest('base64url')}`;
}

afterEach(() => vi.unstubAllGlobals());

describe('provider connection-health canary', () => {
  it('loads an inactive fixed authenticated webhook graph without embedded credentials', () => {
    const loaded = loadConnectionHealthPackage();
    const workflow = JSON.parse(readFileSync('automations/catalog/linkautowork-connection-health/1.0.0/workflow.json', 'utf8')) as { active: boolean; nodes: Array<{ type: string; parameters?: Record<string, unknown>; credentials?: unknown }> };
    expect(loaded.packageDigest).toBe(connectionHealthPackageDigests.definition);
    expect(workflow.active).toBe(false);
    expect(workflow.nodes.map((node) => node.type)).toEqual(['n8n-nodes-base.webhook', 'n8n-nodes-base.set', 'n8n-nodes-base.respondToWebhook']);
    expect(workflow.nodes[0]?.parameters).toMatchObject({ httpMethod: 'POST', authentication: 'headerAuth', path: 'linkautowork-connection-health-v1' });
    expect(workflow.nodes.every((node) => node.credentials === undefined)).toBe(true);
  });

  it('does not advertise an executable canary or persist a request without its dedicated webhook token', async () => {
    const service = new ProviderRouteService(new InMemoryProviderStore());
    expect(service.catalogue().find((entry) => entry.automation.automation_id === 'linkautowork-connection-health')?.lifecycle).toBe('disabled');
    await expect(service.accept(orgId, input(), identity)).rejects.toMatchObject({ category: 'blocked' });
  });

  it('persists one running claim, dispatches the minimal correlation body once, and admits the exact receipt', async () => {
    const store = new InMemoryProviderStore();
    const calls: unknown[] = [];
    const service = new ProviderRouteService(store, async (payload) => { calls.push(payload); return exactResponse(payload); });
    const request = input();
    const accepted = await service.accept(orgId, request, identity);
    const outcome = await service.dispatchConnectionHealth(orgId, request.request_id);
    expect(accepted.replay).toBe(false);
    expect(calls).toEqual([{ request_id: request.request_id, request_fingerprint: (await store.getRequest(orgId, request.request_id)).fingerprint }]);
    expect(outcome).toMatchObject({ dispatch_attempted: true, dispatch_confirmed: true, ambiguous: false, status: { state: 'succeeded', attempt_count: 1 } });
    const receipt = await service.receipt(orgId, request.request_id);
    expect(receipt).toMatchObject({ state: 'succeeded', attempt_count: 1, uncertain_outcome: false, result_refs: [{ ref: 'n8n://executions/exec-215' }] });
  });

  it('lets only the accepted-version CAS winner dispatch under concurrent attempts', async () => {
    const store = new InMemoryProviderStore();
    let entered!: () => void;
    let release!: (value: unknown) => void;
    const enteredPromise = new Promise<void>((resolve) => { entered = resolve; });
    const responsePromise = new Promise<unknown>((resolve) => { release = resolve; });
    let calls = 0;
    const service = new ProviderRouteService(store, async (payload) => { calls += 1; entered(); return responsePromise.then(() => exactResponse(payload)); });
    const request = input();
    await service.accept(orgId, request, identity);
    const winner = service.dispatchConnectionHealth(orgId, request.request_id);
    await enteredPromise;
    const loser = await service.dispatchConnectionHealth(orgId, request.request_id);
    expect(loser).toMatchObject({ dispatch_attempted: false, dispatch_confirmed: false, ambiguous: true, status: { state: 'running' } });
    release({});
    expect(await winner).toMatchObject({ dispatch_attempted: true, dispatch_confirmed: true, ambiguous: false, status: { state: 'succeeded' } });
    expect(calls).toBe(1);
  });

  it('keeps a timeout ambiguous and never retries a running request', async () => {
    const store = new InMemoryProviderStore();
    let calls = 0;
    const service = new ProviderRouteService(store, async () => { calls += 1; throw new Error('transport timeout'); });
    const request = input();
    await service.accept(orgId, request, identity);
    expect(await service.dispatchConnectionHealth(orgId, request.request_id)).toMatchObject({ dispatch_attempted: true, dispatch_confirmed: false, ambiguous: true, status: { state: 'running' } });
    expect(await service.dispatchConnectionHealth(orgId, request.request_id)).toMatchObject({ dispatch_attempted: false, dispatch_confirmed: false, ambiguous: true, status: { state: 'running' } });
    expect(calls).toBe(1);
    await expect(service.receipt(orgId, request.request_id)).rejects.toMatchObject({ category: 'not_found' });
  });

  it('keeps an invalid successful webhook response ambiguous without admitting a receipt', async () => {
    const store = new InMemoryProviderStore();
    let calls = 0;
    const service = new ProviderRouteService(store, async () => { calls += 1; return { status: 'ok' }; });
    const request = input();
    await service.accept(orgId, request, identity);
    expect(await service.dispatchConnectionHealth(orgId, request.request_id)).toMatchObject({ dispatch_attempted: true, dispatch_confirmed: false, ambiguous: true, recovery_required: false, status: { state: 'running', attempt_count: 1 } });
    expect(await service.dispatchConnectionHealth(orgId, request.request_id)).toMatchObject({ dispatch_attempted: false, ambiguous: true, status: { state: 'running', attempt_count: 1 } });
    expect(calls).toBe(1);
    await expect(service.receipt(orgId, request.request_id)).rejects.toMatchObject({ category: 'not_found' });
  });

  it('terminalizes a confirmed failed claim with a durable unavailable receipt and never calls n8n', async () => {
    const store = new InMemoryProviderStore();
    const transition = store.transition.bind(store);
    vi.spyOn(store, 'transition').mockImplementation(async (org, requestId, version, next, invoker) => {
      if (next === 'running') throw new Error('simulated claim failure');
      return transition(org, requestId, version, next, invoker);
    });
    let calls = 0;
    const service = new ProviderRouteService(store, async () => { calls += 1; return {}; });
    const request = input();
    await service.accept(orgId, request, identity);
    expect(await service.dispatchConnectionHealth(orgId, request.request_id)).toMatchObject({ dispatch_attempted: false, dispatch_confirmed: false, ambiguous: false, recovery_required: false, status: { state: 'unavailable', attempt_count: 0 } });
    expect(await service.receipt(orgId, request.request_id)).toMatchObject({ state: 'unavailable', attempt_count: 0, error: { category: 'unavailable', code: 'dispatch_claim_failed', retryable: false } });
    expect(calls).toBe(0);
  });

  it('returns recovery_required when failed-claim terminalization cannot persist', async () => {
    const store = new InMemoryProviderStore();
    vi.spyOn(store, 'transition').mockRejectedValue(new Error('simulated persistence failure'));
    let calls = 0;
    const service = new ProviderRouteService(store, async () => { calls += 1; return exactResponse({ request_id: '00000000-0000-4000-8000-000000000001', request_fingerprint: connectionHealthPackageDigests.definition }); });
    const env = { NODE_ENV: 'test', REPLAY_WINDOW_SECONDS: 60, serviceTokens: new Map([['canary-client', 'internal-test-token']]), hmacSecrets: new Map(), PLATFORM_JWT_TEST_SECRET: platformSecret, PLATFORM_JWT_ISSUER: 'platform-test', PLATFORM_JWT_AUDIENCE: 'linkautowork-gateway' } as AppEnv;
    const app = createApp({ env, nonceStore: new NonceStore(60), providerRouteService: service } as AppDeps);
    const requestBody = input();
    const headers = { 'x-link-service': 'canary-client', 'x-link-service-token': 'internal-test-token', authorization: `Bearer ${platformToken()}` };
    const response = await request(app).post('/v1/provider/requests').set(headers).send(requestBody).expect(503);
    expect(response.body).toMatchObject({ recovery_required: true, recovery_reason: 'dispatch_claim_terminalization_failed', recovery_ref: 'autowork://runbooks/linkautowork-connection-health', status: { state: 'accepted', attempt_count: 0 } });
    expect(await request(app).post('/v1/provider/requests').set(headers).send(requestBody).expect(503).then((replay) => replay.body)).toMatchObject({ replay: true, recovery_required: true, recovery_reason: 'dispatch_claim_pending_recovery', status: { state: 'accepted' } });
    expect(await store.getRequest(orgId, requestBody.request_id)).toMatchObject({ state: 'accepted', attempts: 0 });
    expect((await store.listEvents(orgId, null, 100)).events.some((event) => event.payload_ref.ref === 'autowork://errors/linkautowork-connection-health/dispatch-claim-failed')).toBe(true);
    expect(calls).toBe(0);
  });

  it('rejects policy broadening before the store accepts the request', async () => {
    const store = new InMemoryProviderStore();
    const service = new ProviderRouteService(store, async () => ({}));
    const request = input();
    request.policy.policy_profile_ref = 'autowork://policies/other';
    await expect(service.accept(orgId, request, identity)).rejects.toMatchObject({ category: 'forbidden' });
    await expect(store.getRequest(orgId, request.request_id)).rejects.toMatchObject({ category: 'not_found' });
    const widenedInput = input();
    widenedInput.input_ref.ref = 'autowork://inputs/arbitrary';
    await expect(service.accept(orgId, widenedInput, identity)).rejects.toMatchObject({ category: 'forbidden' });
    await expect(store.getRequest(orgId, widenedInput.request_id)).rejects.toMatchObject({ category: 'not_found' });
  });

  it('rejects a mismatched configuration reference before the store accepts the request', async () => {
    const store = new InMemoryProviderStore();
    const service = new ProviderRouteService(store, async () => ({}));
    const request = input();
    request.automation.configuration_ref.ref = 'autowork://config/another-automation/1.0.0';
    await expect(service.accept(orgId, request, identity)).rejects.toMatchObject({ category: 'forbidden' });
    await expect(store.getRequest(orgId, request.request_id)).rejects.toMatchObject({ category: 'not_found' });
  });

  it('dispatches a new HTTP request once and returns the durable receipt on replay without dispatching again', async () => {
    const store = new InMemoryProviderStore();
    let calls = 0;
    const service = new ProviderRouteService(store, async (payload) => { calls += 1; return exactResponse(payload); });
    const env = { NODE_ENV: 'test', REPLAY_WINDOW_SECONDS: 60, serviceTokens: new Map([['canary-client', 'internal-test-token']]), hmacSecrets: new Map(), PLATFORM_JWT_TEST_SECRET: platformSecret, PLATFORM_JWT_ISSUER: 'platform-test', PLATFORM_JWT_AUDIENCE: 'linkautowork-gateway' } as AppEnv;
    const app = createApp({ env, nonceStore: new NonceStore(60), providerRouteService: service } as AppDeps);
    const headers = { 'x-link-service': 'canary-client', 'x-link-service-token': 'internal-test-token', authorization: `Bearer ${platformToken()}` };
    const requestBody = input();
    const first = await request(app).post('/v1/provider/requests').set(headers).send(requestBody).expect(202);
    expect(first.body).toMatchObject({ replay: false, dispatch_attempted: true, dispatch_confirmed: true, ambiguous: false, status: { state: 'succeeded', attempt_count: 1 } });
    const replay = await request(app).post('/v1/provider/requests').set(headers).send(requestBody).expect(200);
    expect(replay.body).toMatchObject({ replay: true, status: { state: 'succeeded', attempt_count: 1 } });
    expect(calls).toBe(1);
  });

  it('uses only the fixed webhook path, token header, redirect rejection, and bounded JSON response', async () => {
    const fetchMock = vi.fn(async (_url: string | URL | Request, _init?: RequestInit) => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const client = new N8nClient({ N8N_BASE_URL: 'https://n8n.example.test', N8N_WEBHOOK_PATH_PREFIX: '/webhook', } as AppEnv);
    await expect(client.triggerConnectionHealthWebhook({ request_id: randomUUID(), request_fingerprint: connectionHealthPackageDigests.definition }, webhookToken)).resolves.toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe('https://n8n.example.test/webhook/linkautowork-connection-health-v1');
    expect(init).toMatchObject({ method: 'POST', redirect: 'error', headers: { 'x-link-connection-health-token': webhookToken } });
    expect(JSON.parse(String(init?.body))).toEqual(expect.objectContaining({ request_id: expect.any(String), request_fingerprint: connectionHealthPackageDigests.definition }));
    vi.unstubAllGlobals();
  });

  it('rejects an oversized webhook response without reading it as an unbounded string', async () => {
    const fetchMock = vi.fn(async () => new Response('x'.repeat(8193), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const client = new N8nClient({ N8N_BASE_URL: 'https://n8n.example.test', N8N_WEBHOOK_PATH_PREFIX: '/webhook' } as AppEnv);
    await expect(client.triggerConnectionHealthWebhook({ request_id: randomUUID(), request_fingerprint: connectionHealthPackageDigests.definition }, webhookToken)).rejects.toThrow('response exceeded its size limit');
  });
});
