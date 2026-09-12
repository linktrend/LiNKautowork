import {
  LinksitesConsumerAdmissionError,
  admitLinksitesConsumerRegistration,
  type LinksitesConsumerGrant,
  type LinksitesConsumerRegistration,
} from '../../../packages/automation-contracts/src/linksites-consumer-registration.js';

/** Gateway admission boundary for source-only LiNKsites consumer registration. */
export class LinksitesConsumerRegistrationService {
  constructor(private readonly grant: LinksitesConsumerGrant) {}

  /**
   * Admits a registration only when the authenticated organisation matches the explicit grant.
   * Performs no network health check and issues no organisation-bound receipt.
   */
  admit(claimedOrganisationId: string, input: unknown): LinksitesConsumerRegistration {
    if (claimedOrganisationId !== this.grant.organisationId) {
      throw new LinksitesConsumerAdmissionError('wrong_organisation', 'authenticated organisation is not granted');
    }
    return admitLinksitesConsumerRegistration(input, this.grant);
  }
}

export { LinksitesConsumerAdmissionError };
export type { LinksitesConsumerGrant, LinksitesConsumerRegistration };
