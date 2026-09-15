import { generateKeyPairSync, sign, verify } from 'node:crypto';
import request from 'supertest';
import { describe, expect, it } from 'vitest';
import { createProductApi, platformIdentity, type ProductApiEnv } from '../src/app.ts';
import { RemoteProductApiPaciIntrospector, type ProductApiPaciIntrospector, type ProductApiPaciJwksProvider } from '../src/paci.ts';
import { InMemoryProductApiService } from '../src/service.ts';

const issuer = 'https://auth.example.test'; const audience = 'linkautowork-product-api';
const org = '00000000-0000-4000-8000-000000000002'; const otherOrg = '00000000-0000-4000-8000-000000000003';
const keys = generateKeyPairSync('ec', { namedCurve: 'P-256' });
const jwk = { ...keys.publicKey.export({ format: 'jwk' }), kid: 'paci-key-1', use: 'sig', alg: 'ES256' };

function paciToken(overrides: { header?: Record<string, unknown>; envelope?: Record<string, unknown>; claims?: Record<string, unknown> } = {}): string {
  const now = Math.floor(Date.now() / 1000); const header = Buffer.from(JSON.stringify({ alg: 'ES256', typ: 'paci+jwt', kid: 'paci-key-1', ...overrides.header })).toString('base64url');
  const payload = Buffer.from(JSON.stringify({ iss: issuer, aud: [audience], sub: 'server01-product-api', iat: now, nbf: now, exp: now + 60, jti: '10000000-0000-4000-8000-000000000001', 'https://linktrend.dev/claims/auth': { claimContractVersion: 'platform.auth-claims/1.1.0', actorId: 'server01-product-api', actorKind: 'service', runtimeBindingId: 'runtime-binding-1', credentialId: 'credential-1', orgId: org, internal: true, serviceScopes: ['autowork'], permittedOperations: ['read'], issuedAt: new Date(now * 1000).toISOString(), expiresAt: new Date((now + 60) * 1000).toISOString(), issuer, audience: [audience], correlationId: 'paci-test-correlation', ...overrides.claims }, ...overrides.envelope })).toString('base64url');
  return `${header}.${payload}.${sign('SHA256', Buffer.from(`${header}.${payload}`), { key: keys.privateKey, dsaEncoding: 'ieee-p1363' }).toString('base64url')}`;
}

function active(token: string): Record<string, unknown> { const payload = JSON.parse(Buffer.from(token.split('.')[1]!, 'base64url').toString()) as Record<string, any>; const claims = payload['https://linktrend.dev/claims/auth']; return { active: true, iss: payload.iss, aud: payload.aud, sub: payload.sub, exp: payload.exp, iat: payload.iat, jti: payload.jti, client_id: 'autowork-runtime-token-minter', scope: claims.serviceScopes.join(' '), credential_id: claims.credentialId, runtime_binding_id: claims.runtimeBindingId, token_type: 'Bearer' }; }
const goodJwks: ProductApiPaciJwksProvider = { get: async (kid) => kid === 'paci-key-1' ? jwk : undefined };
const goodIntrospector: ProductApiPaciIntrospector = { introspect: async (token) => active(token) };
function env(overrides: Partial<ProductApiEnv> = {}): ProductApiEnv { return { nodeEnv: 'production', issuer, audience, orgId: org, paciClientId: 'server01-lautowork-product-api', paciJwks: goodJwks, paciIntrospector: goodIntrospector, publicClientOrigin: 'https://client.example', operatorConsoleOrigin: 'https://operator.example', ...overrides }; }
function req(token: string) { return { header: (name: string) => name === 'authorization' ? `Bearer ${token}` : undefined } as never; }

describe('Product API canonical PACI verifier', () => {
  it('accepts a valid exact ES256 PACI identity and permits only org-scoped client reads', async () => {
    const token = paciToken(); const identity = await platformIdentity(env(), req(token)); expect(identity).toMatchObject({ sub: 'server01-product-api', org_id: org, authentication: 'paci', permittedOperations: ['read'], roles: [] });
    const service = new InMemoryProductApiService([], [{ id: 'own', orgId: org, state: 'active', configurationStatus: 'ready', deploymentStatus: 'active', health: 'healthy', executions: [], incidents: [], approvedOutputs: [], supportRequests: [] }, { id: 'other', orgId: otherOrg, state: 'active', configurationStatus: 'ready', deploymentStatus: 'active', health: 'healthy', executions: [], incidents: [], approvedOutputs: [], supportRequests: [] }]);
    const app = createProductApi(env(), service); const read = await request(app).get('/v1/client/instances').set('authorization', `Bearer ${token}`); expect(read.status).toBe(200); expect(read.body.items.map((item: { id: string }) => item.id)).toEqual(['own']); expect(service.audits).toContainEqual(expect.objectContaining({ orgId: org, action: 'client.instances.read', outcome: 'allowed' }));
    expect((await request(app).post('/v1/client/support-requests').set('authorization', `Bearer ${token}`).send({ subject: 'not allowed', message: 'PACI read tokens cannot mutate', idempotencyKey: 'paci-mutation-denied' })).status).toBe(403);
    expect((await request(app).get('/v1/operator/incidents').set('authorization', `Bearer ${token}`)).status).toBe(403);
  });

  it.each([
    ['algorithm', { header: { alg: 'RS256' } }, 401], ['type', { header: { typ: 'JWT' } }, 401],
    ['issuer', { envelope: { iss: 'https://wrong.example' } }, 401], ['audience', { envelope: { aud: ['wrong-api'] } }, 401],
    ['organisation', { claims: { orgId: otherOrg } }, 401], ['service', { claims: { serviceScopes: ['lbrain'] } }, 403],
    ['operation', { claims: { permittedOperations: ['execute'] } }, 403], ['expiry', { envelope: { exp: 1 } }, 401],
  ])('rejects the wrong %s', async (_name, overrides, status) => { await expect(platformIdentity(env(), req(paciToken(overrides)))).rejects.toMatchObject({ status }); });

  it('rejects revoked, inactive, malformed, or identity-changing introspection responses', async () => {
    const token = paciToken();
    for (const response of [{ active: false }, { ...active(token), credential_id: 'other' }, { ...active(token), org_id: org }]) await expect(platformIdentity(env({ paciIntrospector: { introspect: async () => response } }), req(token))).rejects.toMatchObject({ status: 401 });
  });

  it('uses the exact authenticated RFC 7662 request without caching active responses', async () => {
    let calls = 0; const endpoint = `${issuer}/oauth/introspect`;
    const introspector = new RemoteProductApiPaciIntrospector(endpoint, 'server01-lautowork-product-api', 'client-key-1', async () => keys.privateKey, async (url, init) => {
      calls += 1; expect(url).toBe(endpoint); expect(init?.method).toBe('POST'); expect(init?.redirect).toBe('error');
      const form = init?.body as URLSearchParams; expect(form.get('token')).toBe('subject-token'); expect(form.get('token_type_hint')).toBe('access_token'); expect(form.get('client_id')).toBe('server01-lautowork-product-api'); expect(form.get('client_assertion_type')).toBe('urn:ietf:params:oauth:client-assertion-type:jwt-bearer');
      const assertion = form.get('client_assertion')!; const [header, payload, signature] = assertion.split('.'); expect(JSON.parse(Buffer.from(header!, 'base64url').toString())).toEqual({ alg: 'ES256', typ: 'JWT', kid: 'client-key-1' }); expect(JSON.parse(Buffer.from(payload!, 'base64url').toString())).toMatchObject({ iss: 'server01-lautowork-product-api', sub: 'server01-lautowork-product-api', aud: endpoint }); expect(verify('SHA256', Buffer.from(`${header}.${payload}`), { key: keys.publicKey, dsaEncoding: 'ieee-p1363' }, Buffer.from(signature!, 'base64url'))).toBe(true);
      return new Response(JSON.stringify({ active: calls === 1 }));
    });
    expect(await introspector.introspect('subject-token')).toEqual({ active: true }); expect(await introspector.introspect('subject-token')).toEqual({ active: false }); expect(calls).toBe(2);
  });

  it('rejects unknown kids and distinguishes JWKS or introspection authority outages as unavailable', async () => {
    await expect(platformIdentity(env(), req(paciToken({ header: { kid: 'unknown' } })))).rejects.toMatchObject({ status: 401 });
    await expect(platformIdentity(env({ paciJwks: { get: async () => { throw new Error('PACI JWKS unavailable'); } } }), req(paciToken()))).rejects.toMatchObject({ status: 503 });
    await expect(platformIdentity(env({ paciIntrospector: { introspect: async () => { throw new Error('PACI introspection unavailable'); } } }), req(paciToken()))).rejects.toMatchObject({ status: 503 });
  });
});
