import { generateKeyPairSync, verify } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { clientAssertion, configuredPaciIntrospector, RemotePaciIntrospector } from '../src/middleware/paci-introspection.js';
import type { AppEnv } from '../src/config/env.js';

const ec = generateKeyPairSync('ec', { namedCurve: 'P-256' });
const endpoint = 'https://platform.example.test/oauth/introspect';
describe('PACI authenticated live introspection', () => {
  it('signs endpoint-bound, short-lived, unique client assertions', () => {
    const first = clientAssertion('gateway', 'client-kid', endpoint, ec.privateKey);
    const second = clientAssertion('gateway', 'client-kid', endpoint, ec.privateKey);
    const [header, payload, signature] = first.split('.');
    expect(JSON.parse(Buffer.from(header, 'base64url').toString())).toEqual({ alg: 'ES256', typ: 'JWT', kid: 'client-kid' });
    const claims = JSON.parse(Buffer.from(payload, 'base64url').toString());
    expect(claims).toMatchObject({ iss: 'gateway', sub: 'gateway', aud: endpoint });
    expect(claims.exp - claims.iat).toBe(60);
    expect(first).not.toBe(second);
    expect(verify('SHA256', Buffer.from(`${header}.${payload}`), { key: ec.publicKey, dsaEncoding: 'ieee-p1363' }, Buffer.from(signature, 'base64url'))).toBe(true);
    expect(() => clientAssertion('gateway', 'kid', endpoint, ec.publicKey)).toThrow(/private P-256/);
  });
  it('does not cache active responses and forbids redirects', async () => {
    let calls = 0; let loads = 0;
    const fetcher: typeof fetch = async (url, init) => {
      expect(url).toBe(endpoint); expect(init?.redirect).toBe('error'); expect(init?.signal).toBeDefined();
      const form = init?.body as URLSearchParams;
      expect(form.get('client_id')).toBe('gateway');
      expect(form.get('token')).toBe('disposable-subject-token');
      expect(form.get('client_assertion_type')).toBe('urn:ietf:params:oauth:client-assertion-type:jwt-bearer');
      calls += 1;
      return new Response(JSON.stringify({ active: calls === 1 }));
    };
    const probe = new RemotePaciIntrospector(endpoint, 'gateway', 'kid', async () => { loads += 1; return ec.privateKey; }, fetcher);
    expect(await probe.introspect('disposable-subject-token')).toEqual({ active: true });
    expect(await probe.introspect('disposable-subject-token')).toEqual({ active: false });
    expect(calls).toBe(2); expect(loads).toBe(1);
  });
  it('fails closed on non-success responses and unsafe configuration', async () => {
    const probe = new RemotePaciIntrospector(endpoint, 'gateway', 'kid', async () => ec.privateKey, async () => new Response('', { status: 401 }));
    await expect(probe.introspect('disposable-subject-token')).rejects.toThrow(/rejected/);
    const env = { PLATFORM_JWT_ISSUER: 'https://platform.example.test', PLATFORM_INTROSPECTION_URL: endpoint,
      PLATFORM_CLIENT_ID: 'gateway', PLATFORM_CLIENT_KEY_ID: 'kid',
      PLATFORM_CLIENT_ASSERTION_SECRET_RESOURCE: 'projects/disposable-project/secrets/disposable-client/versions/1' } as AppEnv;
    expect(configuredPaciIntrospector(env)).toBeDefined();
    expect(configuredPaciIntrospector({ ...env, PLATFORM_CLIENT_ASSERTION_SECRET_RESOURCE: env.PLATFORM_CLIENT_ASSERTION_SECRET_RESOURCE!.replace('/1', '/latest') })).toBeUndefined();
    expect(configuredPaciIntrospector({ ...env, PLATFORM_INTROSPECTION_URL: 'https://other.test/oauth/introspect' })).toBeUndefined();
    expect(configuredPaciIntrospector({ ...env, PLATFORM_CLIENT_ID: undefined })).toBeUndefined();
  });
});
