import { createHmac } from 'node:crypto';
import request from 'supertest';
import { describe, expect, it } from 'vitest';
import { createApp, type AppDeps } from '../src/app.js';
import type { AppEnv } from '../src/config/env.js';
import { NonceStore } from '../src/lib/nonce-store.js';
import { LinksitesConsumerRegistrationService } from '../src/services/linksites-consumer-registration.js';
import { LINKSITES_CONSUMER_CONTRACT_VERSION } from '../../packages/automation-contracts/src/linksites-consumer-registration.js';

const ORG_A = '00000000-0000-4000-8000-000000000147';
const ORG_B = '00000000-0000-4000-8000-000000000148';
const SIGNING_KEY_REF = 'LINKTREND_SITES_DEV_AUTOWORK_SIGNING_KEY';
const PLATFORM_SECRET = 'ltfx.linksites.consumer.registration.test.secret.32.v1';

function token(org = ORG_A) {
  const head = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const claims = Buffer.from(JSON.stringify({
    iss: 'platform-test',
    aud: 'lautowork',
    sub: 'svc:linksites',
    exp: Math.floor(Date.now() / 1000) + 3600,
    service: 'linksites',
    org_id: org,
    org_entitlements: [org],
  })).toString('base64url');
  return `${head}.${claims}.${createHmac('sha256', PLATFORM_SECRET).update(`${head}.${claims}`).digest('base64url')}`;
}

function body(overrides: Record<string, unknown> = {}) {
  return {
    contract_version: LINKSITES_CONSUMER_CONTRACT_VERSION,
    organisation_id: ORG_A,
    environment: 'development',
    event_grants: ['linkautowork.v1.execution.succeeded'],
    signing_key_ref: SIGNING_KEY_REF,
    private_endpoint: 'https://10.8.0.21/v1/autowork/events',
    ...overrides,
  };
}

function fixture() {
  const env = {
    NODE_ENV: 'test',
    REPLAY_WINDOW_SECONDS: 60,
    serviceTokens: new Map([['linksites', 'ltfx.ph.linksites.consumer.v1']]),
    hmacSecrets: new Map(),
    PLATFORM_JWT_TEST_SECRET: PLATFORM_SECRET,
    PLATFORM_JWT_ISSUER: 'platform-test',
    PLATFORM_JWT_AUDIENCE: 'lautowork',
  } as AppEnv;
  const service = new LinksitesConsumerRegistrationService({
    organisationId: ORG_A,
    environment: 'development',
    eventGrants: ['linkautowork.v1.execution.succeeded', 'linkautowork.v1.execution.failed'],
    signingKeyRef: SIGNING_KEY_REF,
  });
  const app = createApp({ env, nonceStore: new NonceStore(60), linksitesConsumerRegistration: service } as AppDeps);
  const headers = {
    'x-link-service': 'linksites',
    'x-link-service-token': 'ltfx.ph.linksites.consumer.v1',
    authorization: `Bearer ${token()}`,
  };
  return { app, headers };
}

describe('LiNKsites consumer-registration gateway admission', () => {
  it('admits an allowed grant and keeps live health and receipt on HOLD', async () => {
    const { app, headers } = fixture();
    const result = await request(app).post('/v1/consumers/linksites/registration').set(headers).send(body()).expect(200);
    expect(result.body.admitted).toBe(true);
    expect(result.body.registration.private_endpoint).toEqual({ scheme: 'https', host: '10.8.0.21', path: '/v1/autowork/events' });
    expect(result.body.live_health).toBe('HOLD');
    expect(result.body.organisation_bound_receipt).toBe('HOLD');
  });

  it('fails closed for the wrong organisation', async () => {
    const { app, headers } = fixture();
    const response = await request(app).post('/v1/consumers/linksites/registration').set(headers).send(body({ organisation_id: ORG_B })).expect(403);
    expect(response.body).toEqual({ error: 'wrong_organisation' });
    await request(app).post('/v1/consumers/linksites/registration').set({ ...headers, authorization: `Bearer ${token(ORG_B)}` }).send(body()).expect(403);
  });

  it('fails closed for the wrong environment', async () => {
    const { app, headers } = fixture();
    const response = await request(app).post('/v1/consumers/linksites/registration').set(headers).send(body({ environment: 'production' })).expect(403);
    expect(response.body).toEqual({ error: 'wrong_environment' });
  });

  it('fails closed for an unknown event', async () => {
    const { app, headers } = fixture();
    const response = await request(app).post('/v1/consumers/linksites/registration').set(headers).send(body({ event_grants: ['linkautowork.v1.lifecycle.transition'] })).expect(403);
    expect(response.body).toEqual({ error: 'unknown_event' });
  });

  it('fails closed when the signing-key reference is missing', async () => {
    const { app, headers } = fixture();
    const { signing_key_ref: _omitted, ...withoutRef } = body();
    const response = await request(app).post('/v1/consumers/linksites/registration').set(headers).send(withoutRef).expect(400);
    expect(response.body).toEqual({ error: 'missing_signing_reference' });
  });

  it('fails closed for an unsafe public endpoint', async () => {
    const { app, headers } = fixture();
    const response = await request(app).post('/v1/consumers/linksites/registration').set(headers).send(body({ private_endpoint: 'https://example.com/hooks' })).expect(403);
    expect(response.body).toEqual({ error: 'unsafe_public_endpoint' });
  });
});
