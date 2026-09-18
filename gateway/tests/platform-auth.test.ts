import { createHmac, generateKeyPairSync, sign } from 'node:crypto';
import { describe, expect, it, vi } from 'vitest';
import { HttpError } from '../src/lib/http-error.js';
import {
  RemotePlatformJwksProvider,
  requirePlatformInvocationClaim,
  type PlatformJwk,
  type PlatformJwksProvider,
} from '../src/middleware/auth.js';
import { PACI_AUTH_CLAIM } from '../src/middleware/paci-claims.js';
import type { PlatformIntrospector } from '../src/middleware/paci-introspection.js';
import type { AppEnv } from '../src/config/env.js';

const secret = 'ltfx.ph.40fdef7128.v1';
const org = '00000000-0000-0000-0000-000000000002';
const env = { NODE_ENV: 'test', PLATFORM_JWT_ISSUER: 'https://platform.test.linktrend.local', PLATFORM_JWT_AUDIENCE: 'linkautowork-gateway', PLATFORM_JWT_TEST_SECRET: secret } as AppEnv;
const productionEnv = {
  NODE_ENV: 'production',
  PLATFORM_JWT_ISSUER: 'https://platform.example.test',
  PLATFORM_JWT_AUDIENCE: 'linkautowork-gateway',
  PLATFORM_JWKS_CACHE_TTL_SECONDS: 60,
} as AppEnv;
const ec = generateKeyPairSync('ec', { namedCurve: 'P-256' });
const rotatedEc = generateKeyPairSync('ec', { namedCurve: 'P-256' });

function jwt(overrides: Record<string, unknown> = {}) {
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const claims = Buffer.from(JSON.stringify({ iss: env.PLATFORM_JWT_ISSUER, aud: env.PLATFORM_JWT_AUDIENCE, sub: 'svc:linksites', exp: Math.floor(Date.now()/1000)+60, service: 'linksites', org_id: org, org_entitlements: [org], ...overrides })).toString('base64url');
  const signature = createHmac('sha256', secret).update(`${header}.${claims}`).digest('base64url');
  return `${header}.${claims}.${signature}`;
}
function tamperSignedClaims(encodedJwt: string): string {
  const [header, encodedClaims, signature] = encodedJwt.split('.');
  const claims = JSON.parse(Buffer.from(encodedClaims, 'base64url').toString('utf8')) as Record<string, unknown>;
  claims.sub = `${String(claims.sub)}:tampered`;
  return `${header}.${Buffer.from(JSON.stringify(claims)).toString('base64url')}.${signature}`;
}
function esJwt(privateKey: typeof ec.privateKey, kid: string, overrides: Record<string, unknown> = {}, alg = 'ES256', claimOverrides: Record<string, unknown> = {}, typ = 'paci+jwt') {
  const header = Buffer.from(JSON.stringify({ alg, typ, kid })).toString('base64url');
  const now = Math.floor(Date.now() / 1000);
  const claims = Buffer.from(JSON.stringify({
    iss: productionEnv.PLATFORM_JWT_ISSUER, aud: [productionEnv.PLATFORM_JWT_AUDIENCE],
    sub: 'svc:linksites', iat: now, nbf: now, exp: now + 60, jti: 'disposable-access-token',
    [PACI_AUTH_CLAIM]: {
      claimContractVersion: 'platform.auth-claims/1.1.0', actorId: 'svc:linksites', actorKind: 'service',
      runtimeBindingId: 'gateway-binding', credentialId: 'gateway-credential', orgId: org, internal: true,
      serviceScopes: ['autowork'], permittedOperations: ['read', 'precheck'],
      issuedAt: new Date(now * 1000).toISOString(), expiresAt: new Date((now + 60) * 1000).toISOString(),
      issuer: productionEnv.PLATFORM_JWT_ISSUER, audience: [productionEnv.PLATFORM_JWT_AUDIENCE], correlationId: 'disposable-correlation',
      ...claimOverrides,
    }, ...overrides,
  })).toString('base64url');
  const signature = sign('SHA256', Buffer.from(`${header}.${claims}`), { key: privateKey, dsaEncoding: 'ieee-p1363' }).toString('base64url');
  return `${header}.${claims}.${signature}`;
}
const activeIntrospector: PlatformIntrospector = {
  async introspect(token) {
    const c = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString());
    const auth = c[PACI_AUTH_CLAIM];
    return { active: true, iss: c.iss, aud: c.aud, sub: c.sub, exp: c.exp, iat: c.iat, jti: c.jti,
      credential_id: auth.credentialId, runtime_binding_id: auth.runtimeBindingId, scope: auth.serviceScopes.join(' ') };
  },
};
class FakePlatformJwks implements PlatformJwksProvider {
  unavailable = false;
  keys = new Map<string, PlatformJwk>([['key-1', { ...ec.publicKey.export({ format: 'jwk' }), kid: 'key-1', use: 'sig' }]]);
  async get(kid: string) {
    if (this.unavailable) throw new Error('offline');
    return this.keys.get(kid);
  }
}
async function invoke(token: string, service = 'linksites', customEnv = env, provider?: PlatformJwksProvider, introspector: PlatformIntrospector | undefined = activeIntrospector, method = 'GET', operation?: string) {
  const req = { method, params: { operation }, header: (name: string) => name === 'authorization' ? `Bearer ${token}` : undefined, linkService: service } as never;
  const next = vi.fn();
  requirePlatformInvocationClaim(customEnv, provider, introspector)(req, {} as never, next);
  if (!next.mock.calls.length) await vi.waitFor(() => expect(next).toHaveBeenCalled());
  return { req: req as unknown as { platformInvocation?: unknown }, error: next.mock.calls[0]?.[0] as Error | undefined };
}
describe('Platform JWT claim adapter', () => {
  it('derives org and service only from a verified entitled token', async () => {
    const result = await invoke(jwt()); expect(result.error).toBeUndefined(); expect(result.req.platformInvocation).toMatchObject({ orgId: org, service: 'linksites' });
  });
  it('rejects tampering, expiry, wrong audience/service, and missing org entitlement', async () => {
    expect((await invoke(tamperSignedClaims(jwt()))).error?.message).toMatch(/signature/);
    expect((await invoke(jwt({ exp: 1 }))).error?.message).toMatch(/expired/);
    expect((await invoke(jwt({ aud: 'other' }))).error?.message).toMatch(/issuer or audience/);
    expect((await invoke(jwt({ service: 'other' }))).error?.message).toMatch(/entitlement/);
    expect((await invoke(jwt({ org_entitlements: [] }))).error?.message).toMatch(/entitlement/);
  });
  it('keeps HS256 exclusive to NODE_ENV=test and never falls back in other environments', async () => {
    expect((await invoke(jwt())).error).toBeUndefined();
    const developmentHs256 = await invoke(jwt(), 'linksites', { ...env, NODE_ENV: 'development' });
    expect(developmentHs256.error).toBeInstanceOf(HttpError);
    expect((developmentHs256.error as HttpError).statusCode).toBe(401);
    expect(developmentHs256.error?.message).toMatch(/ES256/);
    const productionHs256 = await invoke(jwt(), 'linksites', { ...productionEnv, PLATFORM_JWKS_URL: 'https://local.invalid/jwks' });
    expect(productionHs256.error).toBeInstanceOf(HttpError);
    expect((productionHs256.error as HttpError).statusCode).toBe(401);
    expect(productionHs256.error?.message).toMatch(/ES256/);
  });
  it('fails closed with 503 when non-test Platform JWKS configuration is missing', async () => {
    const missingJwks = await invoke(esJwt(ec.privateKey, 'key-1'), 'linksites', productionEnv);
    expect(missingJwks.error).toBeInstanceOf(HttpError);
    expect((missingJwks.error as HttpError).statusCode).toBe(503);
    expect(missingJwks.error?.message).toMatch(/live Platform JWT verifier/);
  });
  it('accepts a valid Platform PACI ES256 token through JWKS kid lookup', async () => {
    const provider = new FakePlatformJwks();
    const result = await invoke(esJwt(ec.privateKey, 'key-1'), 'linksites', productionEnv, provider);
    expect(result.error).toBeUndefined();
    expect(result.req.platformInvocation).toMatchObject({ orgId: org, service: 'linksites', subject: 'svc:linksites' });
  });
  it('rejects invalid ES256 signatures, issuer, audience, and unknown kids', async () => {
    const provider = new FakePlatformJwks();
    const signature = await invoke(esJwt(rotatedEc.privateKey, 'key-1'), 'linksites', productionEnv, provider);
    expect(signature.error).toBeInstanceOf(HttpError);
    expect((signature.error as HttpError).statusCode).toBe(401);
    expect(signature.error?.message).toMatch(/signature/);
    const issuer = await invoke(esJwt(ec.privateKey, 'key-1', { iss: 'https://evil.test' }), 'linksites', productionEnv, provider);
    expect(issuer.error?.message).toMatch(/issuer or audience/);
    const audience = await invoke(esJwt(ec.privateKey, 'key-1', { aud: ['other'] }), 'linksites', productionEnv, provider);
    expect(audience.error?.message).toMatch(/issuer or audience/);
    const kid = await invoke(esJwt(ec.privateKey, 'unknown'), 'linksites', productionEnv, provider);
    expect(kid.error).toBeInstanceOf(HttpError);
    expect((kid.error as HttpError).statusCode).toBe(401);
    expect(kid.error?.message).toMatch(/unknown/);
  });
  it('fails closed with 503 when Platform JWKS is unavailable and does not use HS256', async () => {
    const provider = new FakePlatformJwks();
    provider.unavailable = true;
    const unavailable = await invoke(esJwt(ec.privateKey, 'key-1'), 'linksites', productionEnv, provider);
    expect(unavailable.error).toBeInstanceOf(HttpError);
    expect((unavailable.error as HttpError).statusCode).toBe(503);
    expect(unavailable.error?.message).toMatch(/JWKS verifier unavailable/);
    const hs256WithJwks = await invoke(jwt(), 'linksites', { ...productionEnv, PLATFORM_JWKS_URL: 'https://local.invalid/jwks' }, provider);
    expect(hs256WithJwks.error).toBeInstanceOf(HttpError);
    expect((hs256WithJwks.error as HttpError).statusCode).toBe(401);
  });
  it('rejects legacy flattened claims, wrong token type, restricted and unentitled identities', async () => {
    const p = new FakePlatformJwks();
    for (const token of [
      esJwt(ec.privateKey, 'key-1', {}, 'ES256', {}, 'JWT'),
      esJwt(ec.privateKey, 'key-1', { [PACI_AUTH_CLAIM]: undefined, org_id: org }),
      esJwt(ec.privateKey, 'key-1', {}, 'ES256', { serviceScopes: ['lbrain'] }),
      esJwt(ec.privateKey, 'key-1', {}, 'ES256', { programRestrictions: ['program-a'] }),
      esJwt(ec.privateKey, 'key-1', {}, 'ES256', { actorId: 'different-actor' }),
      esJwt(ec.privateKey, 'key-1', {}, 'ES256', { serviceScopes: ['autowork', 'autowork'] }),
    ]) expect((await invoke(token, 'linksites', productionEnv, p)).error).toBeInstanceOf(HttpError);
  });
  it('admits only the exact operation on a durable instance route', async () => {
    const token = esJwt(ec.privateKey, 'key-1'); const p = new FakePlatformJwks();
    expect((await invoke(token, 'linksites', productionEnv, p, activeIntrospector, 'POST', 'precheck')).error).toBeUndefined();
    expect((await invoke(token, 'linksites', productionEnv, p, activeIntrospector, 'POST', 'delete')).error?.message).toMatch(/operation/);
    expect((await invoke(token, 'linksites', productionEnv, p, activeIntrospector, 'POST')).error?.message).toMatch(/operation/);
  });
  it('fails closed on revocation, unavailable introspection, or any identity mismatch', async () => {
    const token = esJwt(ec.privateKey, 'key-1'); const p = new FakePlatformJwks();
    for (const patch of [{ active: false }, { credential_id: 'other' }, { runtime_binding_id: 'other' },
      { jti: 'other' }, { sub: 'other' }, { iss: 'other' }, { aud: ['other'] }, { exp: 1 }, { iat: 1 }, { scope: 'lbrain' }]) {
      const probe = { introspect: async (t: string) => ({ ...await activeIntrospector.introspect(t) as object, ...patch }) };
      expect((await invoke(token, 'linksites', productionEnv, p, probe)).error?.message).toMatch(/inactive or identity changed/);
    }
    const offline = { introspect: async () => { throw new Error('offline'); } };
    expect((await invoke(token, 'linksites', productionEnv, p, offline)).error?.message).toMatch(/introspection unavailable/);
    const req = { method: 'GET', header: () => `Bearer ${token}`, linkService: 'linksites' } as never;
    const next = vi.fn(); requirePlatformInvocationClaim(productionEnv, p)(req, {} as never, next);
    await vi.waitFor(() => expect(next).toHaveBeenCalled());
    expect(next.mock.calls[0][0].statusCode).toBe(503);
  });
  it('bounds remote Platform JWKS caching and unknown-kid refresh attempts without a live call', async () => {
    let calls = 0;
    const jwk = { ...ec.publicKey.export({ format: 'jwk' }), kid: 'key-1', use: 'sig' };
    const fetcher = async () => {
      calls += 1;
      return new Response(JSON.stringify({ keys: [jwk] }), { status: 200, headers: { 'content-type': 'application/json' } });
    };
    const provider = new RemotePlatformJwksProvider('https://local.invalid/jwks', 300_000, fetcher);
    expect(await provider.get('key-1')).toMatchObject({ kid: 'key-1' });
    expect(await provider.get('key-1')).toBeTruthy();
    expect(await provider.get('unknown')).toBeUndefined();
    expect(await provider.get('another-unknown')).toBeUndefined();
    expect(calls).toBe(2);
  });
});
