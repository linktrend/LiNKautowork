import { createHmac, randomUUID } from 'node:crypto';
import request from 'supertest';
import { describe, expect, it } from 'vitest';
import { createApp, type AppDeps } from '../src/app.js';
import type { AppEnv } from '../src/config/env.js';
import { NonceStore } from '../src/lib/nonce-store.js';
import { RuntimeDispatchService } from '../src/services/runtime-dispatch/index.js';

const ORG = '11111111-1111-4111-8111-111111111111';
const DIGEST = `sha256:${'a'.repeat(64)}`;
const ISSUED_AT = '2026-08-13T00:00:00.000Z';
const EXPIRES_AT = '2099-08-13T00:00:00.000Z';

function token(org = ORG) {
  const head = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const claims = Buffer.from(JSON.stringify({ iss: 'platform-test', aud: 'lautowork', sub: 'caller', exp: Math.floor(Date.now() / 1000) + 3600, service: 'ide-client', org_id: org, org_entitlements: [org] })).toString('base64url');
  return `${head}.${claims}.${createHmac('sha256', 'ltfx.runtime.dispatch.test.ts.platformjwttestsecre.15.1.v1').update(`${head}.${claims}`).digest('base64url')}`;
}

function body(overrides: Record<string, unknown> = {}) {
  return {
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
    idempotency_key: 'runtime-dispatch-http-idempotency-key',
    expires_at: EXPIRES_AT,
    policy: { side_effect_class: 'read_only', approval_requirement: 'none', policy_profile_ref: 'policy://repo/read-only', data_classification: 'internal' },
    approval_refs: [],
    ...overrides,
  };
}

function fixture(service = new RuntimeDispatchService({ activationInterfaceSupported: true, now: () => new Date(ISSUED_AT) })) {
  const env = {
    NODE_ENV: 'test',
    REPLAY_WINDOW_SECONDS: 60,
    serviceTokens: new Map([['ide-client', 'ltfx.ph.d27582b366.v1']]),
    hmacSecrets: new Map(),
    PLATFORM_JWT_TEST_SECRET: 'ltfx.runtime.dispatch.test.ts.platformjwttestsecre.15.1.v1',
    PLATFORM_JWT_ISSUER: 'platform-test',
    PLATFORM_JWT_AUDIENCE: 'lautowork',
  } as AppEnv;
  const app = createApp({ env, nonceStore: new NonceStore(60), runtimeDispatchService: service } as AppDeps);
  const headers = { 'x-link-service': 'ide-client', 'x-link-service-token': 'ltfx.ph.d27582b366.v1', authorization: `Bearer ${token()}` };
  return { app, service, headers };
}

describe('runtime dispatch HTTP routes', () => {
  it('fails closed when the in-process module is absent and never requires an n8n client', async () => {
    const env = { NODE_ENV: 'test', REPLAY_WINDOW_SECONDS: 60, serviceTokens: new Map([['ide-client', 'ltfx.ph.d27582b366.v1']]), hmacSecrets: new Map(), PLATFORM_JWT_TEST_SECRET: 'ltfx.runtime.dispatch.test.ts.platformjwttestsecre.15.1.v1', PLATFORM_JWT_ISSUER: 'platform-test', PLATFORM_JWT_AUDIENCE: 'lautowork' } as AppEnv;
    const app = createApp({ env, nonceStore: new NonceStore(60) } as AppDeps);
    const headers = { 'x-link-service': 'ide-client', 'x-link-service-token': 'ltfx.ph.d27582b366.v1', authorization: `Bearer ${token()}` };
    await request(app).post('/v1/runtime/activations').send(body()).expect(401);
    await request(app).post('/v1/runtime/activations').set(headers).send(body()).expect(503);
  });

  it('accepts durable activation, replays it, exposes status, and admits one native n8n callback', async () => {
    const { app, headers } = fixture();
    const input = body();
    const first = await request(app).post('/v1/runtime/activations').set(headers).send(input).expect(202);
    expect(first.body.activation.n8n_dispatched).toBe(false);
    expect(first.body.activation.live_n8n_activation).toBe('hold');
    expect(first.body.activation).not.toHaveProperty('input_ref');
    await request(app).post('/v1/runtime/activations').set(headers).send(input).expect(200);
    await request(app).get(`/v1/runtime/activations/${input.request_id}`).set(headers).expect(200);
    const callback = {
      request_id: input.request_id,
      receipt_id: first.body.activation.receipt_id,
      org_id: ORG,
      n8n_execution_ref: 'n8n://executions/http-1',
      source_timestamp: '2026-08-13T00:01:00.000Z',
      outcome: 'succeeded',
      request_fingerprint: first.body.activation.fingerprint,
      callback_binding_ref: input.automation.configuration_ref.ref,
    };
    const admitted = await request(app).post('/v1/runtime/callbacks').set(headers).send(callback).expect(202);
    expect(admitted.body.n8n_dispatched).toBe(false);
    expect(admitted.body.receipt.state).toBe('succeeded');
    await request(app).post('/v1/runtime/callbacks').set(headers).send(callback).expect(400);
  });

  it('returns 503 when live n8n activation remains unavailable in bootstrap wiring', async () => {
    const { app, headers } = fixture(new RuntimeDispatchService({ activationInterfaceSupported: false }));
    await request(app).post('/v1/runtime/activations').set(headers).send(body({ idempotency_key: 'runtime-dispatch-http-unavailable' })).expect(503);
  });
});
