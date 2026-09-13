import { z } from 'zod';

/** Source-only LiNKsites consumer-registration contract family. Not a live install proof. */
export const LINKSITES_CONSUMER_CONTRACT_VERSION = 'linksites-consumer-registration.v1' as const;

/** Environments a source-only consumer grant may name. These are labels, not a deployment proof. */
export const LINKSITES_CONSUMER_ENVIRONMENTS = ['development', 'staging', 'production'] as const;

/** Named Autowork events a LiNKsites consumer may be granted. Unknown names fail closed. */
export const LINKSITES_CONSUMER_EVENT_GRANTS = [
  'linkautowork.v1.execution.succeeded',
  'linkautowork.v1.execution.failed',
  'linkautowork.v1.lifecycle.transition',
] as const;

/** GSM-style signing-key reference. The value of the key is forbidden. */
export const LINKSITES_SIGNING_KEY_REF_PATTERN = /^LINKTREND_[A-Z][A-Z0-9_]{2,127}$/;

const organisationId = z.string().uuid();
const environment = z.enum(LINKSITES_CONSUMER_ENVIRONMENTS);
const eventGrant = z.enum(LINKSITES_CONSUMER_EVENT_GRANTS);
const signingKeyRef = z.string().regex(LINKSITES_SIGNING_KEY_REF_PATTERN, 'must be a GSM-style signing-key reference');

const secretShapedSigningValue = /-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:sk|pk|ghp|xox[baprs])[_-][A-Za-z0-9-]{12,}|[A-Za-z0-9+/]{40,}={0,2}/;

/**
 * Fail-closed admission codes for LiNKsites consumer registration.
 */
export type LinksitesConsumerAdmissionCode =
  | 'wrong_organisation'
  | 'wrong_environment'
  | 'unknown_event'
  | 'missing_signing_reference'
  | 'unsafe_public_endpoint'
  | 'invalid_registration';

/** Typed fail-closed admission error. Never carries a secret value. */
export class LinksitesConsumerAdmissionError extends Error {
  readonly code: LinksitesConsumerAdmissionCode;

  constructor(code: LinksitesConsumerAdmissionCode, message: string) {
    super(message);
    this.name = 'LinksitesConsumerAdmissionError';
    this.code = code;
  }
}

/** Source-only grant a gateway may enforce. Fixture IDs only; not a live organisation. */
export type LinksitesConsumerGrant = {
  organisationId: string;
  environment: (typeof LINKSITES_CONSUMER_ENVIRONMENTS)[number];
  eventGrants: readonly (typeof LINKSITES_CONSUMER_EVENT_GRANTS)[number][];
  signingKeyRef: string;
};

/** Sanitized private endpoint identity. Host and path only; no userinfo, query, or fragment. */
export type LinksitesPrivateEndpointIdentity = {
  scheme: 'https';
  host: string;
  path: string;
};

function isRfc1918Ipv4(host: string): boolean {
  const match = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(host);
  if (!match) return false;
  const octets = match.slice(1).map((value) => Number(value));
  if (octets.some((octet) => !Number.isInteger(octet) || octet < 0 || octet > 255)) return false;
  const [a, b] = octets;
  return a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
}

function isInternalHostname(host: string): boolean {
  return /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*\.internal$/.test(host);
}

/**
 * Returns whether a host is admissible as a private consumer endpoint identity.
 */
export function isPrivateEndpointHost(host: string): boolean {
  return isRfc1918Ipv4(host) || isInternalHostname(host);
}

/**
 * Sanitizes a private HTTPS endpoint into host+path identity. Public, credentialed, and non-HTTPS forms fail closed.
 */
export function sanitizePrivateEndpointIdentity(raw: string): LinksitesPrivateEndpointIdentity {
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new LinksitesConsumerAdmissionError('unsafe_public_endpoint', 'private endpoint identity is not a valid URL');
  }
  if (parsed.username || parsed.password) {
    throw new LinksitesConsumerAdmissionError('unsafe_public_endpoint', 'private endpoint identity must not include credentials');
  }
  if (parsed.protocol !== 'https:') {
    throw new LinksitesConsumerAdmissionError('unsafe_public_endpoint', 'private endpoint identity must use https');
  }
  const host = parsed.hostname.toLowerCase();
  if (!isPrivateEndpointHost(host)) {
    throw new LinksitesConsumerAdmissionError('unsafe_public_endpoint', 'private endpoint identity must not use a public host');
  }
  if (parsed.port && parsed.port !== '443') {
    throw new LinksitesConsumerAdmissionError('unsafe_public_endpoint', 'private endpoint identity must not expose a non-default public port');
  }
  const path = parsed.pathname || '/';
  if (!/^\/[A-Za-z0-9._/-]*$/.test(path) || path.includes('..')) {
    throw new LinksitesConsumerAdmissionError('unsafe_public_endpoint', 'private endpoint path is not a sanitized identity');
  }
  return { scheme: 'https', host, path };
}

const linksitesConsumerRegistrationInputSchema = z.object({
  contract_version: z.literal(LINKSITES_CONSUMER_CONTRACT_VERSION),
  organisation_id: organisationId,
  environment,
  event_grants: z.array(eventGrant).min(1).max(8),
  signing_key_ref: signingKeyRef.optional(),
  private_endpoint: z.string().min(8).max(512),
}).strict();

/** Parsed, sanitized LiNKsites consumer registration. */
export type LinksitesConsumerRegistration = {
  contract_version: typeof LINKSITES_CONSUMER_CONTRACT_VERSION;
  organisation_id: string;
  environment: (typeof LINKSITES_CONSUMER_ENVIRONMENTS)[number];
  event_grants: (typeof LINKSITES_CONSUMER_EVENT_GRANTS)[number][];
  signing_key_ref: string;
  private_endpoint: LinksitesPrivateEndpointIdentity;
};

/**
 * Parses and admits a source-only LiNKsites consumer registration against an explicit grant.
 * Does not perform network I/O, health checks, or receipt issuance.
 */
export function admitLinksitesConsumerRegistration(
  input: unknown,
  grant: LinksitesConsumerGrant,
): LinksitesConsumerRegistration {
  const parsed = linksitesConsumerRegistrationInputSchema.safeParse(input);
  if (!parsed.success) {
    const missingSigning = parsed.error.issues.some((issue) => issue.path[0] === 'signing_key_ref');
    const raw = input && typeof input === 'object' ? (input as Record<string, unknown>) : {};
    if (missingSigning || raw.signing_key_ref === undefined || raw.signing_key_ref === null || raw.signing_key_ref === '') {
      throw new LinksitesConsumerAdmissionError('missing_signing_reference', 'signing-key reference is required');
    }
    if (typeof raw.signing_key_ref === 'string' && secretShapedSigningValue.test(raw.signing_key_ref)) {
      throw new LinksitesConsumerAdmissionError('missing_signing_reference', 'signing-key reference must be a name, never a value');
    }
    throw new LinksitesConsumerAdmissionError('invalid_registration', parsed.error.issues.map((issue) => issue.message).join('; '));
  }

  const registration = parsed.data;
  if (!registration.signing_key_ref) {
    throw new LinksitesConsumerAdmissionError('missing_signing_reference', 'signing-key reference is required');
  }
  if (secretShapedSigningValue.test(registration.signing_key_ref) || registration.signing_key_ref !== grant.signingKeyRef) {
    throw new LinksitesConsumerAdmissionError('missing_signing_reference', 'signing-key reference must match the grant reference and never a value');
  }
  if (registration.organisation_id !== grant.organisationId) {
    throw new LinksitesConsumerAdmissionError('wrong_organisation', 'organisation is not granted');
  }
  if (registration.environment !== grant.environment) {
    throw new LinksitesConsumerAdmissionError('wrong_environment', 'environment is not granted');
  }
  const granted = new Set(grant.eventGrants);
  for (const eventName of registration.event_grants) {
    if (!granted.has(eventName)) {
      throw new LinksitesConsumerAdmissionError('unknown_event', `event is not granted: ${eventName}`);
    }
  }

  const privateEndpoint = sanitizePrivateEndpointIdentity(registration.private_endpoint);
  return {
    contract_version: registration.contract_version,
    organisation_id: registration.organisation_id,
    environment: registration.environment,
    event_grants: [...new Set(registration.event_grants)],
    signing_key_ref: registration.signing_key_ref,
    private_endpoint: privateEndpoint,
  };
}
