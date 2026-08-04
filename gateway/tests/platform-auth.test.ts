import { createHmac } from 'node:crypto';
import { describe, expect, it, vi } from 'vitest';
import { requirePlatformInvocationClaim } from '../src/middleware/auth.js';
import type { AppEnv } from '../src/config/env.js';

const secret = 'a-very-long-platform-test-signing-secret';
const org = '00000000-0000-0000-0000-000000000002';
const env = { NODE_ENV: 'test', PLATFORM_JWT_ISSUER: 'https://platform.test.linktrend.local', PLATFORM_JWT_AUDIENCE: 'linkautowork-gateway', PLATFORM_JWT_TEST_SECRET: secret } as AppEnv;
function jwt(overrides: Record<string, unknown> = {}) {
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const claims = Buffer.from(JSON.stringify({ iss: env.PLATFORM_JWT_ISSUER, aud: env.PLATFORM_JWT_AUDIENCE, sub: 'svc:linksites', exp: Math.floor(Date.now()/1000)+60, service: 'linksites', org_id: org, org_entitlements: [org], ...overrides })).toString('base64url');
  const signature = createHmac('sha256', secret).update(`${header}.${claims}`).digest('base64url');
  return `${header}.${claims}.${signature}`;
}
function tamperSignedClaims(token: string): string {
  const [header, encodedClaims, signature] = token.split('.');
  const claims = JSON.parse(Buffer.from(encodedClaims, 'base64url').toString('utf8')) as Record<string, unknown>;
  claims.sub = `${String(claims.sub)}:tampered`;
  return `${header}.${Buffer.from(JSON.stringify(claims)).toString('base64url')}.${signature}`;
}
async function invoke(token: string, service = 'linksites', customEnv = env) {
  const req = { header: (name: string) => name === 'authorization' ? `Bearer ${token}` : undefined, linkService: service } as never;
  const next = vi.fn(); requirePlatformInvocationClaim(customEnv)(req, {} as never, next);
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
  it('keeps production fail-closed until a live issuer verifier is configured', async () => {
    expect((await invoke(jwt(), 'linksites', { ...env, NODE_ENV: 'production' })).error?.message).toMatch(/live Platform JWT verifier/);
  });
});
