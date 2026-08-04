/** Safe configuration field rendered by the client product surface. Credential fields are deliberately unsupported. */
export type SafeField = { key: string; label: string; kind: 'text' | 'url' | 'select'; required: boolean; options?: readonly string[] };
export type PublishedOffer = { productId: string; offerId: string; releaseLabel: string; name: string; summary: string; prerequisites: readonly string[]; pricePresentation: string; supportPath: string; fields: readonly SafeField[]; terms?: { documentId: string; version: string; digest: string }; published: boolean };
export type ClientIdentity = { subject: string; organisationId: string; roles: readonly ('client_member' | 'client_admin')[] };
export type OrderState = 'initiated' | 'awaiting_payment' | 'payment_not_required' | 'paid' | 'awaiting_configuration' | 'credentials_required' | 'provisioning' | 'active' | 'suspended' | 'cancel_requested' | 'cancelled' | 'failed';
export type ClientOrder = { id: string; organisationId: string; offerId: string; acceptedTermsVersion: string; state: OrderState; settings: Record<string, string>; instanceId?: string; failureCode?: 'payment_failed' | 'provisioning_failed' };
export type PortalInstance = { id: string; organisationId: string; productName: string; releaseLabel: string; state: 'active' | 'paused' | 'failed'; configurationStatus: 'complete' | 'credentials_required'; health: 'healthy' | 'degraded'; recentRuns: readonly { id: string; status: string }[]; incidents: readonly { id: string; status: string }[]; approvedOutputs: readonly { id: string; label: string }[] };

export interface Provisioner { provision(request: { idempotencyKey: string; organisationId: string; offerId: string }): Promise<{ instanceId: string }>; compensate?(instanceId: string): Promise<void>; }
export interface ProductClientAdapter {
  currentIdentity(): Promise<ClientIdentity | undefined>;
  publishedOffers(): Promise<PublishedOffer[]>;
  createOrder(input: { organisationId: string; offerId: string; termsVersion: string; idempotencyKey: string; paymentRequired: boolean }): Promise<ClientOrder>;
  getOrder(id: string, identity: ClientIdentity): Promise<ClientOrder>;
  saveSettings(id: string, identity: ClientIdentity, settings: Record<string, string>): Promise<ClientOrder>;
  paymentEvent(input: { eventId: string; orderId: string; type: 'payment.succeeded' | 'payment.failed'; signature: string }): Promise<ClientOrder>;
  provision(id: string, identity: ClientIdentity): Promise<ClientOrder>;
  portal(identity: ClientIdentity): Promise<PortalInstance[]>;
  action(input: { identity: ClientIdentity; instanceId: string; action: 'pause' | 'resume' | 'retry'; idempotencyKey: string }): Promise<PortalInstance>;
}
