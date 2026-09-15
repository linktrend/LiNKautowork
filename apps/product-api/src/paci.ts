import { createPrivateKey, createPublicKey, randomUUID, sign, verify, type JsonWebKey, type KeyObject } from 'node:crypto';
import { SecretManagerServiceClient } from '@google-cloud/secret-manager';
import { z } from 'zod';
import type { PlatformIdentity } from './contracts.js';

const PACI_AUTH_CLAIM = 'https://linktrend.dev/claims/auth';
const identifiers = z.array(z.string().min(1)).refine((items) => new Set(items).size === items.length, 'duplicate identifiers');
const authClaimsSchema = z.object({
  claimContractVersion: z.literal('platform.auth-claims/1.1.0'), actorId: z.string().min(1),
  actorKind: z.enum(['human', 'persona', 'service', 'adapter', 'program_executor']),
  runtimeBindingId: z.string().min(1), credentialId: z.string().min(1), orgId: z.string().uuid(), internal: z.literal(true),
  serviceScopes: identifiers.refine((items) => items.length > 0, 'empty identifiers'), permittedOperations: identifiers,
  issuedAt: z.string().datetime({ offset: true }), expiresAt: z.string().datetime({ offset: true }),
  issuer: z.string().min(1), audience: identifiers.refine((items) => items.length > 0, 'empty identifiers'), programRestrictions: identifiers.nullable().optional(),
  repositoryRestrictions: identifiers.nullable().optional(), correlationId: z.string().min(1),
}).strict();
const envelopeSchema = z.object({
  iss: z.string().min(1), aud: identifiers.refine((items) => items.length > 0, 'empty identifiers'), sub: z.string().min(1), iat: z.number().int().nonnegative(),
  nbf: z.number().int().nonnegative(), exp: z.number().int().nonnegative(), jti: z.string().uuid(), [PACI_AUTH_CLAIM]: authClaimsSchema,
}).strict();
const activeIntrospectionSchema = z.object({
  active: z.literal(true), iss: z.string(), aud: identifiers.refine((items) => items.length > 0, 'empty identifiers'), sub: z.string(), exp: z.number().int(),
  iat: z.number().int(), jti: z.string(), client_id: z.string().min(1), scope: z.string().min(1),
  credential_id: z.string().min(1), runtime_binding_id: z.string().min(1), token_type: z.literal('Bearer'),
}).strict();

/** Public key shape admitted from the Platform PACI JWKS. */
export type ProductApiPaciJwk = JsonWebKey & { kid?: string; use?: string; kty?: string; crv?: string; alg?: string };
/** Resolves one Platform PACI signing key by exact kid. */
export interface ProductApiPaciJwksProvider { get(kid: string): Promise<ProductApiPaciJwk | undefined>; }
/** Performs one authenticated live PACI introspection request. */
export interface ProductApiPaciIntrospector { introspect(token: string): Promise<unknown>; }

/** Bounded PACI JWKS cache. Unknown kids cause at most one refresh per 30 seconds. */
export class RemoteProductApiPaciJwksProvider implements ProductApiPaciJwksProvider {
  private readonly keys = new Map<string, ProductApiPaciJwk>(); private expiresAt = 0; private lastUnknownRefresh = 0; private inFlight?: Promise<void>;
  constructor(private readonly url: string, private readonly ttlMs: number, private readonly fetcher: typeof fetch = fetch) {}
  async get(kid: string): Promise<ProductApiPaciJwk | undefined> { const now = Date.now(); if (now < this.expiresAt && this.keys.has(kid)) return this.keys.get(kid); if (now < this.expiresAt && !this.keys.has(kid)) { if (now - this.lastUnknownRefresh < 30_000) return undefined; this.lastUnknownRefresh = now; } await this.refresh(); return this.keys.get(kid); }
  private async refresh(): Promise<void> { if (this.inFlight) return this.inFlight; this.inFlight = (async () => { const response = await this.fetcher(this.url, { headers: { accept: 'application/json' }, redirect: 'error', signal: AbortSignal.timeout(5000) }); if (!response.ok) throw new Error('PACI JWKS unavailable'); const body = await response.json() as { keys?: ProductApiPaciJwk[] }; if (!Array.isArray(body.keys) || body.keys.length === 0 || body.keys.length > 20) throw new Error('PACI JWKS payload is invalid'); const next = new Map<string, ProductApiPaciJwk>(); for (const key of body.keys) { if (key.kty === 'EC' && key.crv === 'P-256' && key.use === 'sig' && (key.alg === undefined || key.alg === 'ES256') && typeof key.kid === 'string' && key.kid.trim().length > 0 && !('d' in key)) { if (next.has(key.kid)) throw new Error('PACI JWKS kid collision'); next.set(key.kid, key); } } if (next.size === 0) throw new Error('PACI JWKS has no usable signing keys'); this.keys.clear(); for (const [id, key] of next) this.keys.set(id, key); this.expiresAt = Date.now() + Math.min(this.ttlMs, 300_000); })().finally(() => { this.inFlight = undefined; }); return this.inFlight; }
}

/** Creates the exact endpoint-bound ES256 private_key_jwt required by Platform PACI. */
export function productApiClientAssertion(clientId: string, kid: string, endpoint: string, key: KeyObject): string {
  if (key.type !== 'private' || key.asymmetricKeyType !== 'ec' || key.asymmetricKeyDetails?.namedCurve !== 'prime256v1') throw new Error('PACI client signing key must be a private P-256 key');
  const now = Math.floor(Date.now() / 1000); const header = Buffer.from(JSON.stringify({ alg: 'ES256', typ: 'JWT', kid })).toString('base64url'); const payload = Buffer.from(JSON.stringify({ iss: clientId, sub: clientId, aud: endpoint, iat: now, exp: now + 60, jti: randomUUID() })).toString('base64url'); const input = `${header}.${payload}`;
  return `${input}.${sign('SHA256', Buffer.from(input), { key, dsaEncoding: 'ieee-p1363' }).toString('base64url')}`;
}

/** Uncached RFC 7662 lookup authenticated with the Product API client credential. */
export class RemoteProductApiPaciIntrospector implements ProductApiPaciIntrospector {
  private key?: Promise<KeyObject>;
  constructor(private readonly endpoint: string, private readonly clientId: string, private readonly kid: string, private readonly loadKey: () => Promise<KeyObject>, private readonly fetcher: typeof fetch = fetch) {}
  async introspect(token: string): Promise<unknown> { this.key ??= this.loadKey().catch((error) => { this.key = undefined; throw error; }); const assertion = productApiClientAssertion(this.clientId, this.kid, this.endpoint, await this.key); const response = await this.fetcher(this.endpoint, { method: 'POST', redirect: 'error', signal: AbortSignal.timeout(5000), headers: { 'content-type': 'application/x-www-form-urlencoded', accept: 'application/json' }, body: new URLSearchParams({ token, token_type_hint: 'access_token', client_id: this.clientId, client_assertion_type: 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer', client_assertion: assertion }) }); if (!response.ok) throw new Error('PACI introspection rejected'); return response.json(); }
}

/** Loads only a pinned GSM secret version containing the Product API client private key. */
export function gsmProductApiPaciIntrospector(endpoint: string, clientId: string, kid: string, resource: string): RemoteProductApiPaciIntrospector {
  if (!/^projects\/[a-z0-9-]+\/secrets\/[A-Za-z0-9_-]+\/versions\/[1-9][0-9]*$/.test(resource)) throw new Error('PRODUCT_API_PACI_CLIENT_ASSERTION_SECRET_RESOURCE must pin a numeric GSM version');
  return new RemoteProductApiPaciIntrospector(endpoint, clientId, kid, async () => { const [version] = await new SecretManagerServiceClient().accessSecretVersion({ name: resource }); const pem = version.payload?.data?.toString('utf8'); if (!pem) throw new Error('PACI client key unavailable'); return createPrivateKey(pem); });
}

/** Inputs pinned by the Product API production environment. */
export type VerifyProductApiPaciInput = { token: string; issuer: string; audience: string; orgId: string; clientId: string; jwks: ProductApiPaciJwksProvider; introspector: ProductApiPaciIntrospector; now?: number };

/** Verifies the canonical PACI envelope and live credential state for Product API read access. */
export async function verifyProductApiPaci(input: VerifyProductApiPaciInput): Promise<PlatformIdentity> {
  const parts = input.token.split('.'); if (parts.length !== 3) throw new Error('invalid_token'); const [encodedHeader, encodedPayload, encodedSignature] = parts;
  let header: { alg?: string; typ?: string; kid?: string }; let raw: unknown;
  try { header = JSON.parse(Buffer.from(encodedHeader, 'base64url').toString('utf8')) as typeof header; raw = JSON.parse(Buffer.from(encodedPayload, 'base64url').toString('utf8')); } catch { throw new Error('invalid_token'); }
  if (header.alg !== 'ES256' || header.typ !== 'paci+jwt' || !header.kid || Object.keys(header).some((key) => !['alg', 'typ', 'kid'].includes(key))) throw new Error('invalid_token');
  let jwk: ProductApiPaciJwk | undefined; try { jwk = await input.jwks.get(header.kid); } catch { throw new Error('jwks_unavailable'); } if (!jwk) throw new Error('unknown_kid');
  let signatureValid = false; try { signatureValid = verify('SHA256', Buffer.from(`${encodedHeader}.${encodedPayload}`), { key: createPublicKey({ key: jwk, format: 'jwk' }), dsaEncoding: 'ieee-p1363' }, Buffer.from(encodedSignature, 'base64url')); } catch { throw new Error('invalid_token'); }
  if (!signatureValid) throw new Error('invalid_token');
  const token = envelopeSchema.parse(raw); const claims = token[PACI_AUTH_CLAIM]; const now = input.now ?? Math.floor(Date.now() / 1000);
  if (token.iss !== input.issuer || claims.issuer !== input.issuer || token.aud.length !== 1 || token.aud[0] !== input.audience || claims.audience.length !== 1 || claims.audience[0] !== input.audience || token.sub !== claims.actorId || claims.orgId !== input.orgId) throw new Error('invalid_token');
  if (token.iat > now || token.nbf !== token.iat || token.exp <= now || token.exp <= token.iat || token.exp - token.iat > 900 || Date.parse(claims.issuedAt) !== token.iat * 1000 || Date.parse(claims.expiresAt) !== token.exp * 1000) throw new Error('invalid_token');
  if (claims.actorKind !== 'service' || claims.serviceScopes.length !== 1 || claims.serviceScopes[0] !== 'autowork' || claims.permittedOperations.length !== 1 || claims.permittedOperations[0] !== 'read' || claims.programRestrictions?.length || claims.repositoryRestrictions?.length) throw new Error('forbidden_token');
  let introspection: unknown; try { introspection = await input.introspector.introspect(input.token); } catch { throw new Error('introspection_unavailable'); }
  const active = activeIntrospectionSchema.parse(introspection); const scopes = active.scope.split(' ');
  if (active.iss !== token.iss || active.aud.length !== token.aud.length || active.aud.some((item, index) => item !== token.aud[index]) || active.sub !== token.sub || active.exp !== token.exp || active.iat !== token.iat || active.jti !== token.jti || active.client_id !== input.clientId || active.credential_id !== claims.credentialId || active.runtime_binding_id !== claims.runtimeBindingId || scopes.length !== claims.serviceScopes.length || scopes.some((scope, index) => scope !== claims.serviceScopes[index])) throw new Error('inactive_token');
  return { sub: token.sub, org_id: claims.orgId, roles: [], iss: token.iss, aud: token.aud, exp: token.exp, nbf: token.nbf, jti: token.jti, authentication: 'paci', permittedOperations: claims.permittedOperations };
}
