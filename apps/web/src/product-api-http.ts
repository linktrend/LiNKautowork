import type { ClientIdentity, PortalInstance, ProductClientAdapter, PublishedOffer } from './contracts.js';

export type PlatformSession = { accessToken: string; subject: string; organisationId: string; roles: readonly ('client_member' | 'client_admin')[] };
export type ProductApiRecord = { id: string; orgId?: string; state?: string; status?: string; version?: number; summary?: string; evidenceRef?: string; updatedAt?: string };
export type ProductApiPage<T> = { items: T[]; nextCursor?: string };
export type ProductApiProduct = { id: string; name: string; summary: string; signupPrerequisites: string[]; version?: number; offeringVersion?: number; release?: { id: string; version: string; digest: string; workflowDigest: string }; terms?: { documentId: string; version: string; digest: string }; commercial?: { pricePresentation?: string; [key: string]: unknown }; configuration?: { schemaVersion: string; schema: Record<string, unknown> } };
export type ClientPortalSnapshot = { subscriptions: ProductApiPage<ProductApiRecord>; orders: ProductApiPage<ProductApiRecord>; configuration: ProductApiPage<ProductApiRecord>; provisioning: ProductApiPage<ProductApiRecord>; supportRequests: ProductApiPage<ProductApiRecord>; instances: ProductApiPage<PortalInstance> };

/** Browser-side transport contract. The Product API, not this client, verifies the Platform RS256/JWKS session. */
export type PlatformSessionProvider = () => Promise<PlatformSession | undefined>;
export class ProductApiHttpError extends Error { constructor(readonly code: string, message: string, readonly status: number) { super(message); } }

/**
 * Typed client for the finite WP-09 public/client routes. It never accepts an organisation id
 * from caller input: the bearer identity is the only organisation authority at the API boundary.
 */
export class ProductApiHttpAdapter {
  constructor(private readonly baseUrl: string, private readonly session: PlatformSessionProvider, private readonly send: typeof fetch = fetch.bind(globalThis)) {}
  async currentIdentity(): Promise<ClientIdentity | undefined> { const session = await this.session(); return session && { subject: session.subject, organisationId: session.organisationId, roles: session.roles }; }
  async publishedOffers(): Promise<PublishedOffer[]> { const page = await this.request<ProductApiPage<ProductApiProduct>>('/v1/public/products', { public: true }); return page.items.map((product) => ({ productId: product.id, offerId: product.id, releaseLabel: product.release ? `${product.release.version} · ${product.release.digest}` : `Offer v${product.offeringVersion ?? product.version ?? 1}`, name: product.name, summary: product.summary, prerequisites: product.signupPrerequisites, pricePresentation: product.commercial?.pricePresentation as string ?? 'Pricing is confirmed with support before activation.', supportPath: 'Contact LiNKtrend support.', fields: [], ...(product.terms ? { terms: product.terms } : {}), published: true })); }
  async signupPrerequisites(): Promise<{ configuration: 'operator_assisted_required'; credentialIntake: 'not_available' }> { return this.request('/v1/public/signup-prerequisites', { public: true }); }
  async portal(): Promise<ClientPortalSnapshot> { const [subscriptions, orders, configuration, provisioning, supportRequests, instances] = await Promise.all([this.page('subscriptions'), this.page('orders'), this.page('configuration'), this.page('provisioning'), this.page('support-requests'), this.request<ProductApiPage<PortalInstance>>('/v1/client/instances')]); return { subscriptions, orders, configuration, provisioning, supportRequests, instances }; }
  /** Creates an order intent only; payment/provider selection is deliberately outside this client. */
  async createOrder(input: { productId: string; idempotencyKey: string }): Promise<ProductApiRecord> { return this.request('/v1/client/orders', { method: 'POST', body: input }); }
  async acceptTerms(input: { orderId: string; termsDocumentId: string; termsVersion: string; termsDigest: string }): Promise<{ orderId: string; termsDocumentId: string; termsVersion: string; termsDigest: string; accepted: boolean }> { const { orderId, ...body } = input; return this.request(`/v1/client/orders/${encodeURIComponent(orderId)}/terms`, { method: 'POST', body }); }
  async createSubscription(input: { orderId: string; idempotencyKey: string }): Promise<ProductApiRecord> { return this.request('/v1/client/subscriptions', { method: 'POST', body: input }); }
  /** Safe ordinary settings only. The server derives the assigned instance from the subscription and rejects credential-shaped keys. */
  async submitConfiguration(input: { subscriptionId: string; values: Record<string, string | number | boolean>; idempotencyKey: string }): Promise<ProductApiRecord> { return this.request('/v1/client/configuration', { method: 'POST', body: input }); }
  async requestProvisioning(input: { subscriptionId: string; idempotencyKey: string }): Promise<ProductApiRecord> { return this.request('/v1/client/provisioning', { method: 'POST', body: input }); }
  async instanceAction(input: { instanceId: string; action: 'pause' | 'resume'; reason: string; idempotencyKey: string }): Promise<PortalInstance> { const { instanceId, ...body } = input; return this.request(`/v1/client/instances/${encodeURIComponent(instanceId)}/actions`, { method: 'POST', body }); }
  async createSupportRequest(input: { subject: string; message: string; idempotencyKey: string }): Promise<ProductApiRecord> { return this.request('/v1/client/support-requests', { method: 'POST', body: input }); }
  private async page(area: 'subscriptions' | 'orders' | 'configuration' | 'provisioning' | 'support-requests') { return this.request<ProductApiPage<ProductApiRecord>>(`/v1/client/${area}`); }
  private async request<T>(path: string, options: { method?: 'POST'; body?: unknown; public?: boolean } = {}): Promise<T> { const session = options.public ? undefined : await this.session(); if (!options.public && !session?.accessToken) throw new ProductApiHttpError('unauthenticated', 'Sign in with LiNKplatform to continue.', 401); const base = this.baseUrl.endsWith('/') ? this.baseUrl : `${this.baseUrl}/`; const response = await this.send(new URL(path.replace(/^\//, ''), base), { method: options.method ?? 'GET', headers: { accept: 'application/json', ...(options.body ? { 'content-type': 'application/json' } : {}), ...(session ? { authorization: `Bearer ${session.accessToken}` } : {}) }, ...(options.body ? { body: JSON.stringify(options.body) } : {}) }); const parsed = await response.json() as T | { error?: { code?: string; message?: string } }; if (!response.ok) { const error = parsed as { error?: { code?: string; message?: string } }; throw new ProductApiHttpError(error.error?.code ?? 'request_failed', error.error?.message ?? 'Request could not be completed.', response.status); } return parsed as T; }
}

/** Compile-time guard: HTTP transport deliberately remains separate until WP-09 adds lifecycle mutations. */
export type DeterministicLifecycleAdapter = ProductClientAdapter;
