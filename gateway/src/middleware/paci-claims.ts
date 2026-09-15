import { z } from 'zod';
import { HttpError } from '../lib/http-error.js';

/** Frozen Platform PACI claim namespace; consumer claims are never flattened. */
export const PACI_AUTH_CLAIM = 'https://linktrend.dev/claims/auth';
const identifiers = z.array(z.string().min(1)).refine((items) => new Set(items).size === items.length, 'duplicate identifiers');
const authClaims = z.object({
  claimContractVersion: z.literal('platform.auth-claims/1.1.0'),
  actorId: z.string().min(1),
  actorKind: z.enum(['human', 'persona', 'service', 'adapter', 'program_executor']),
  runtimeBindingId: z.string().min(1), credentialId: z.string().min(1),
  orgId: z.string().uuid(), internal: z.literal(true),
  serviceScopes: identifiers.refine((items) => items.length > 0, 'empty identifiers'), permittedOperations: identifiers,
  issuedAt: z.string().datetime({ offset: true }), expiresAt: z.string().datetime({ offset: true }),
  issuer: z.string().min(1), audience: identifiers.refine((items) => items.length > 0, 'empty identifiers'),
  programRestrictions: identifiers.nullable().optional(),
  repositoryRestrictions: identifiers.nullable().optional(),
  correlationId: z.string().min(1),
}).strict();
const envelope = z.object({
  iss: z.string().min(1), sub: z.string().min(1), aud: identifiers.refine((items) => items.length > 0, 'empty identifiers'),
  iat: z.number().int(), nbf: z.number().int(), exp: z.number().int(), jti: z.string().min(1),
  [PACI_AUTH_CLAIM]: authClaims,
}).strict();

/** Verified token dimensions that must also match the live revocation response. */
export type PaciIdentity = { orgId: string; subject: string; credentialId: string; runtimeBindingId: string; jti: string; issuer: string; audience: string[]; iat: number; exp: number; scopes: string[] };

/** Validates canonical claims after signature verification, before any dispatch. */
export function acceptPaciClaims(raw: unknown, issuer: string, audience: string, operation: string, now = Math.floor(Date.now() / 1000)): PaciIdentity {
  const token = envelope.parse(raw);
  const claims = token[PACI_AUTH_CLAIM];
  if (token.iss !== issuer || claims.issuer !== issuer || !token.aud.includes(audience)
      || token.aud.length !== claims.audience.length || !token.aud.every((item) => claims.audience.includes(item))) {
    throw new HttpError(401, 'invalid Platform token issuer or audience');
  }
  if (token.sub !== claims.actorId || token.exp <= now || token.iat > now || token.nbf !== token.iat
      || token.exp <= token.iat || token.exp - token.iat > 900
      || Date.parse(claims.issuedAt) !== token.iat * 1000 || Date.parse(claims.expiresAt) !== token.exp * 1000) {
    throw new HttpError(401, 'Platform token identity or lifetime is invalid');
  }
  if (!claims.serviceScopes.includes('autowork') || !claims.permittedOperations.includes(operation)) {
    throw new HttpError(403, 'Platform service or operation is not permitted');
  }
  // This adapter has no Program/repository authority resolver. Never silently
  // discard a token restriction or infer business permission from Platform access.
  if (claims.programRestrictions?.length || claims.repositoryRestrictions?.length) {
    throw new HttpError(403, 'restricted Platform token requires a bound authority resolver');
  }
  return { orgId: claims.orgId, subject: token.sub, credentialId: claims.credentialId,
    runtimeBindingId: claims.runtimeBindingId, jti: token.jti, issuer: token.iss,
    audience: token.aud, iat: token.iat, exp: token.exp, scopes: claims.serviceScopes };
}

/** Checks live introspection against every identity dimension used for admission. */
export function isActivePaciIdentity(raw: unknown, identity: PaciIdentity): boolean {
  if (!raw || typeof raw !== 'object') return false;
  const result = raw as Record<string, unknown>;
  return result.active === true && result.iss === identity.issuer && result.sub === identity.subject
    && result.jti === identity.jti && result.iat === identity.iat && result.exp === identity.exp
    && result.credential_id === identity.credentialId && result.runtime_binding_id === identity.runtimeBindingId
    && Array.isArray(result.aud) && result.aud.length === identity.audience.length
    && new Set(result.aud).size === result.aud.length
    && result.aud.every((item) => typeof item === 'string' && identity.audience.includes(item))
    && typeof result.scope === 'string'
    && result.scope.split(' ').length === identity.scopes.length
    && new Set(result.scope.split(' ')).size === identity.scopes.length
    && result.scope.split(' ').every((item) => identity.scopes.includes(item));
}
