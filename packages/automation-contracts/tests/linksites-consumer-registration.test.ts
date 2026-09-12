import { describe, expect, it } from 'vitest';
import {
  LINKSITES_CONSUMER_CONTRACT_VERSION,
  LinksitesConsumerAdmissionError,
  admitLinksitesConsumerRegistration,
  sanitizePrivateEndpointIdentity,
  type LinksitesConsumerGrant,
} from '../src/linksites-consumer-registration.js';

const fixtureOrganisationId = '00000000-0000-4000-8000-000000000147';
const otherOrganisationId = '00000000-0000-4000-8000-000000000148';
const signingKeyRef = 'LINKTREND_SITES_DEV_AUTOWORK_SIGNING_KEY';
const privateEndpoint = 'https://10.8.0.21/v1/autowork/events';

const grant: LinksitesConsumerGrant = {
  organisationId: fixtureOrganisationId,
  environment: 'development',
  eventGrants: ['linkautowork.v1.execution.succeeded', 'linkautowork.v1.execution.failed'],
  signingKeyRef,
};

function registration(overrides: Record<string, unknown> = {}) {
  return {
    contract_version: LINKSITES_CONSUMER_CONTRACT_VERSION,
    organisation_id: fixtureOrganisationId,
    environment: 'development',
    event_grants: ['linkautowork.v1.execution.succeeded'],
    signing_key_ref: signingKeyRef,
    private_endpoint: privateEndpoint,
    ...overrides,
  };
}

describe('LiNKsites consumer-registration contract', () => {
  it('admits an allowed grant with a signing-key reference and sanitized private endpoint identity', () => {
    const admitted = admitLinksitesConsumerRegistration(registration(), grant);
    expect(admitted.organisation_id).toBe(fixtureOrganisationId);
    expect(admitted.environment).toBe('development');
    expect(admitted.event_grants).toEqual(['linkautowork.v1.execution.succeeded']);
    expect(admitted.signing_key_ref).toBe(signingKeyRef);
    expect(admitted.private_endpoint).toEqual({ scheme: 'https', host: '10.8.0.21', path: '/v1/autowork/events' });
    expect(sanitizePrivateEndpointIdentity('https://linksites.internal/v1/autowork/events')).toEqual({
      scheme: 'https',
      host: 'linksites.internal',
      path: '/v1/autowork/events',
    });
  });

  it('fails closed for the wrong organisation', () => {
    expect(() => admitLinksitesConsumerRegistration(registration({ organisation_id: otherOrganisationId }), grant)).toThrow(
      LinksitesConsumerAdmissionError,
    );
    try {
      admitLinksitesConsumerRegistration(registration({ organisation_id: otherOrganisationId }), grant);
    } catch (error) {
      expect(error).toBeInstanceOf(LinksitesConsumerAdmissionError);
      expect((error as LinksitesConsumerAdmissionError).code).toBe('wrong_organisation');
    }
  });

  it('fails closed for the wrong environment', () => {
    expect(() => admitLinksitesConsumerRegistration(registration({ environment: 'production' }), grant)).toThrow(/environment/);
    try {
      admitLinksitesConsumerRegistration(registration({ environment: 'production' }), grant);
    } catch (error) {
      expect((error as LinksitesConsumerAdmissionError).code).toBe('wrong_environment');
    }
  });

  it('fails closed for an unknown event', () => {
    expect(() => admitLinksitesConsumerRegistration(registration({ event_grants: ['linkautowork.v1.lifecycle.transition'] }), grant)).toThrow(
      /event/,
    );
    try {
      admitLinksitesConsumerRegistration(registration({ event_grants: ['linkautowork.v1.lifecycle.transition'] }), grant);
    } catch (error) {
      expect((error as LinksitesConsumerAdmissionError).code).toBe('unknown_event');
    }
  });

  it('fails closed when the signing-key reference is missing or is a value', () => {
    const { signing_key_ref: _omitted, ...withoutRef } = registration();
    expect(() => admitLinksitesConsumerRegistration(withoutRef, grant)).toThrow(/signing-key/);
    try {
      admitLinksitesConsumerRegistration(withoutRef, grant);
    } catch (error) {
      expect((error as LinksitesConsumerAdmissionError).code).toBe('missing_signing_reference');
    }
    expect(() => admitLinksitesConsumerRegistration(registration({ signing_key_ref: '-----BEGIN PRIVATE KEY-----abc' }), grant)).toThrow(
      /signing-key/,
    );
  });

  it('fails closed for an unsafe public endpoint', () => {
    expect(() => admitLinksitesConsumerRegistration(registration({ private_endpoint: 'https://example.com/hooks' }), grant)).toThrow(
      /public/,
    );
    try {
      admitLinksitesConsumerRegistration(registration({ private_endpoint: 'https://example.com/hooks' }), grant);
    } catch (error) {
      expect((error as LinksitesConsumerAdmissionError).code).toBe('unsafe_public_endpoint');
    }
    expect(() => sanitizePrivateEndpointIdentity('https://user:value@10.8.0.21/v1/autowork/events')).toThrow(/credentials/);
  });
});
