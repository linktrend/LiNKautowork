import { createPrivateKey, randomUUID, sign, type KeyObject } from 'node:crypto';
import { SecretManagerServiceClient } from '@google-cloud/secret-manager';
import type { AppEnv } from '../config/env.js';

/** Live, authenticated revocation lookup; no positive-result cache or offline fallback. */
export interface PlatformIntrospector { introspect(token: string): Promise<unknown>; }

/** Signs a short-lived private_key_jwt with the gateway client key, never an issuer key. */
export function clientAssertion(clientId: string, kid: string, endpoint: string, key: KeyObject): string {
  if (key.type !== 'private' || key.asymmetricKeyType !== 'ec' || key.asymmetricKeyDetails?.namedCurve !== 'prime256v1') {
    throw new Error('PACI client signing key must be a private P-256 key');
  }
  const now = Math.floor(Date.now() / 1000);
  const header = Buffer.from(JSON.stringify({ alg: 'ES256', typ: 'JWT', kid })).toString('base64url');
  const payload = Buffer.from(JSON.stringify({ iss: clientId, sub: clientId, aud: endpoint, iat: now, exp: now + 60, jti: randomUUID() })).toString('base64url');
  const input = `${header}.${payload}`;
  return `${input}.${sign('SHA256', Buffer.from(input), { key, dsaEncoding: 'ieee-p1363' }).toString('base64url')}`;
}

/** Resolves a pinned GSM client PEM only within the runtime signing boundary. */
export class RemotePaciIntrospector implements PlatformIntrospector {
  private key?: Promise<KeyObject>;
  constructor(private readonly endpoint: string, private readonly clientId: string, private readonly kid: string,
    private readonly loadKey: () => Promise<KeyObject>, private readonly fetcher: typeof fetch = fetch) {}
  async introspect(token: string): Promise<unknown> {
    this.key ??= this.loadKey().catch((error) => { this.key = undefined; throw error; });
    const assertion = clientAssertion(this.clientId, this.kid, this.endpoint, await this.key);
    const response = await this.fetcher(this.endpoint, {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(5000),
      headers: { 'content-type': 'application/x-www-form-urlencoded', accept: 'application/json' },
      body: new URLSearchParams({ token, token_type_hint: 'access_token', client_id: this.clientId,
        client_assertion_type: 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer', client_assertion: assertion }),
    });
    if (!response.ok) throw new Error('PACI introspection rejected');
    return response.json();
  }
}

/** Missing, cross-origin, or unpinned production configuration leaves dispatch closed. */
export function configuredPaciIntrospector(env: AppEnv): PlatformIntrospector | undefined {
  const endpoint = env.PLATFORM_INTROSPECTION_URL;
  const clientId = env.PLATFORM_CLIENT_ID;
  const kid = env.PLATFORM_CLIENT_KEY_ID;
  const resource = env.PLATFORM_CLIENT_ASSERTION_SECRET_RESOURCE;
  if (!endpoint || !clientId || !kid || !resource) return undefined;
  if (endpoint !== `${env.PLATFORM_JWT_ISSUER}/oauth/introspect` || new URL(endpoint).protocol !== 'https:'
      || !/^projects\/[a-z0-9-]+\/secrets\/[A-Za-z0-9_-]+\/versions\/[1-9][0-9]*$/.test(resource)) return undefined;
  return new RemotePaciIntrospector(endpoint, clientId, kid, async () => {
    const [version] = await new SecretManagerServiceClient().accessSecretVersion({ name: resource });
    const pem = version.payload?.data?.toString('utf8');
    if (!pem) throw new Error('PACI client key unavailable');
    return createPrivateKey(pem);
  });
}
