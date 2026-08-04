import { randomUUID } from 'node:crypto';
import { isOperatorActionAllowed, type OperatorResource, type ProductRole } from './contracts.js';

export type ProductSummary = {
  id: string; name: string; summary: string; signupPrerequisites: string[]; version?: number; offeringVersion?: number;
  release?: { id: string; version: string; digest: string; workflowDigest: string };
  terms?: { documentId: string; version: string; digest: string };
  commercial?: Record<string, unknown>;
  configuration?: { schemaVersion: string; schema: Record<string, unknown> };
};
export type Page<T> = { items: T[]; nextCursor?: string };
export type ClientInstance = { id: string; orgId: string; state: 'ready' | 'active' | 'paused'; configurationStatus: 'operator_assisted_required'; deploymentStatus: string; health: string; executions: Array<{ id: string; status: string }>; incidents: Array<{ id: string; status: string }>; approvedOutputs: Array<{ id: string; status: string }>; supportRequests: Array<{ id: string; status: string }> };
export type AuditEvent = { actor: string; orgId: string; resource: string; action: string; reason: string; correlationId: string; outcome: 'allowed' | 'denied' };
export type AuditReservationInput = Omit<AuditEvent, 'outcome'>;
export type AuditReservation = AuditReservationInput & { auditId: string; status: 'pending' | 'completed' };
export type SafeRecord = { id: string; orgId?: string; state?: string; status?: string; version?: number; summary?: string; evidenceRef?: string; updatedAt?: string };
export type ClientPortal = { subscriptions: SafeRecord[]; orders: SafeRecord[]; configuration: SafeRecord[]; provisioning: SafeRecord[]; supportRequests: SafeRecord[] };

/** Minimal RPC transport used by the production adapter.  It intentionally has no SQL/table endpoint escape hatch. */
export type PostgrestRpc = (name: string, body: Record<string, unknown>, orgId?: string, audit?: AuditReservationInput) => Promise<unknown>;
export type ProductProvisioningAdapter = {
  request(input: { orgId: string; subscriptionId: string; idempotencyKey: string }, audit?: AuditReservationInput): Promise<SafeRecord>;
  compensate(input: { orgId: string; subscriptionId: string; reason: string; idempotencyKey: string }, audit?: AuditReservationInput): Promise<SafeRecord>;
};
export type WebhookReceipt = { replay: boolean; state?: string; providerSequence?: number; occurredAt?: string };

function requireAudit(audit: AuditReservationInput | undefined): AuditReservationInput {
  if (!audit) throw new Error('audit_reservation_required');
  return audit;
}

function normalizeProviderWebhookError(error: unknown): unknown {
  if (!(error instanceof Error)) return error;
  const match = /^product_persistence_unavailable:(\d+):(.*)$/s.exec(error.message);
  if (!match || Number(match[1]) !== 400) return error;
  try {
    const payload = JSON.parse(match[2]) as { code?: unknown; message?: unknown };
    if (payload.code === 'P0001' && payload.message === 'provider event out of order') return new Error('provider_event_out_of_order');
    if (payload.code === 'P0001' && payload.message === 'provider event occurredAt is stale') return new Error('provider_event_out_of_order');
  } catch {
    // Preserve the original persistence error; the HTTP boundary redacts it.
  }
  return error;
}

/** Narrow internal-service boundary: no table, SQL, workflow, or n8n proxy access is exposed here. */
export interface ProductApiService {
  publishedProducts(page: { limit: number; cursor?: string }): Promise<Page<ProductSummary>>;
  clientInstances(orgId: string, page: { limit: number; cursor?: string }, audit?: AuditReservationInput): Promise<Page<ClientInstance>>;
  transitionInstance(input: { orgId: string; actor: string; instanceId: string; action: 'pause' | 'resume'; reason: string; idempotencyKey: string }, audit?: AuditReservationInput): Promise<ClientInstance>;
  createProduct(input: { actor: string; name: string; summary: string; version: number; reason: string; idempotencyKey: string }, audit?: AuditReservationInput): Promise<ProductSummary>;
  updateProduct(input: { actor: string; id: string; summary: string; expectedVersion: number; reason: string; idempotencyKey: string }, audit?: AuditReservationInput): Promise<ProductSummary>;
  receiveWebhook(input: { eventId: string; eventType: string; orgId: string; subscriptionId: string; occurredAt: string; providerSequence: number }): Promise<WebhookReceipt>;
  clientPortal(orgId: string, area: keyof ClientPortal, page: { limit: number; cursor?: string }, audit?: AuditReservationInput): Promise<Page<SafeRecord>>;
  createSupportRequest(input: { orgId: string; actor: string; subject: string; message: string; idempotencyKey: string }, audit?: AuditReservationInput): Promise<SafeRecord>;
  createOrder(input: { orgId: string; actor: string; productId: string; idempotencyKey: string }, audit?: AuditReservationInput): Promise<SafeRecord>;
  acceptTerms(input: { orgId: string; actor: string; orderId: string; termsDocumentId: string; termsVersion: string; termsDigest: string }, audit?: AuditReservationInput): Promise<{ orderId: string; termsDocumentId: string; termsVersion: string; termsDigest: string; accepted: boolean }>;
  createSubscription(input: { orgId: string; actor: string; orderId: string; idempotencyKey: string }, audit?: AuditReservationInput): Promise<SafeRecord>;
  submitConfiguration(input: { orgId: string; actor: string; subscriptionId: string; values: Record<string, string | number | boolean>; idempotencyKey: string }, audit?: AuditReservationInput): Promise<SafeRecord>;
  requestProvisioning(input: { orgId: string; actor: string; subscriptionId: string; idempotencyKey: string }, audit?: AuditReservationInput): Promise<SafeRecord>;
  operatorRecords(resource: OperatorResource, page: { limit: number; cursor?: string }, audit?: AuditReservationInput): Promise<Page<SafeRecord>>;
  operatorAction(input: { actor: string; resource: OperatorResource; id: string; action: string; reason: string; idempotencyKey: string; expectedVersion?: number }, audit?: AuditReservationInput): Promise<SafeRecord>;
  reserveAudit(input: AuditReservationInput): Promise<AuditReservation>;
  finalizeAudit(reservation: AuditReservation, outcome: AuditEvent['outcome']): Promise<void>;
  recordDeniedAudit(input: AuditReservationInput): Promise<void>;
}

export class InMemoryProductApiService implements ProductApiService {
  readonly audits: AuditEvent[] = []; readonly pendingAudits: AuditReservation[] = []; readonly webhooks = new Set<string>();
  failAuditReservation = false;
  failAuditFinalization = false;
  private readonly webhookState = new Map<string, { state: string; providerSequence: number; occurredAt: string }>(); private readonly orderSnapshots = new Map<string, ProductSummary>(); private readonly idempotent = new Map<string, ProductSummary | ClientInstance | SafeRecord>(); private readonly support = new Map<string, SafeRecord[]>(); private readonly portal = new Map<string, ClientPortal>(); private readonly operator = new Map<OperatorResource, SafeRecord[]>();
  constructor(private readonly products: ProductSummary[], private readonly instances: ClientInstance[], operatorFixtures: Partial<Record<OperatorResource, SafeRecord[]>> = {}) { for (const [resource, records] of Object.entries(operatorFixtures) as Array<[OperatorResource, SafeRecord[]]>) this.operator.set(resource, records); }
  async publishedProducts(page: { limit: number; cursor?: string }) { return paginate(this.products, page); }
  async clientInstances(orgId: string, page: { limit: number; cursor?: string }) { return paginate(this.instances.filter((item) => item.orgId === orgId), page); }
  async transitionInstance(input: { orgId: string; actor: string; instanceId: string; action: 'pause' | 'resume'; reason: string; idempotencyKey: string }) { const key = `instance:${input.orgId}:${input.idempotencyKey}`; const replay = this.idempotent.get(key); if (replay) return replay as ClientInstance; const item = this.instances.find((candidate) => candidate.id === input.instanceId && candidate.orgId === input.orgId); if (!item) throw new Error('not_found'); item.state = input.action === 'pause' ? 'paused' : 'active'; this.idempotent.set(key, item); return item; }
  async createProduct(input: { actor: string; name: string; summary: string; version: number; reason: string; idempotencyKey: string }) { const key = `product:${input.idempotencyKey}`; const replay = this.idempotent.get(key); if (replay) return replay as ProductSummary; const product = { id: `product-${this.products.length + 1}`, name: input.name, summary: input.summary, version: 1, signupPrerequisites: ['operator-assisted configuration'] }; this.products.push(product); this.idempotent.set(key, product); return product; }
  async updateProduct(input: { actor: string; id: string; summary: string; expectedVersion: number; reason: string; idempotencyKey: string }) { const key = `product:${input.idempotencyKey}`; const replay = this.idempotent.get(key); if (replay) return replay as ProductSummary; const product = this.products.find((item) => item.id === input.id); if (!product) throw new Error('not_found'); if ((product.version ?? 1) !== input.expectedVersion) throw new Error('concurrency_conflict'); product.summary = input.summary; product.version = input.expectedVersion + 1; this.idempotent.set(key, product); return product; }
  async receiveWebhook(input: { eventId: string; eventType: string; orgId: string; subscriptionId: string; occurredAt: string; providerSequence: number }) { const eventKey = `${input.orgId}:${input.eventId}`; const stateKey = `${input.orgId}:${input.subscriptionId}`; const replay = this.webhooks.has(eventKey); if (replay) return { replay: true, ...this.webhookState.get(stateKey) }; const prior = this.webhookState.get(stateKey); if (prior && (input.providerSequence <= prior.providerSequence || input.occurredAt < prior.occurredAt)) throw new Error('provider_event_out_of_order'); const current = prior?.state ?? 'awaiting_payment'; const state = input.eventType === 'payment.succeeded' ? (current === 'awaiting_payment' ? 'awaiting_configuration' : (() => { throw new Error('invalid_transition'); })()) : input.eventType === 'payment.failed' ? (current === 'awaiting_payment' ? 'failed' : (() => { throw new Error('invalid_transition'); })()) : input.eventType === 'payment.refunded' ? (['paid', 'awaiting_configuration', 'active', 'suspended'].includes(current) ? 'refunded' : (() => { throw new Error('invalid_transition'); })()) : input.eventType === 'provisioning.completed' ? (current === 'provisioning' ? 'active' : (() => { throw new Error('invalid_transition'); })()) : (['awaiting_configuration', 'provisioning'].includes(current) ? 'failed' : (() => { throw new Error('invalid_transition'); })()); const receipt = { state, providerSequence: input.providerSequence, occurredAt: input.occurredAt }; this.webhooks.add(eventKey); this.webhookState.set(stateKey, receipt); return { replay: false, ...receipt }; }
  async clientPortal(orgId: string, area: keyof ClientPortal, page: { limit: number; cursor?: string }) { const saved = this.portal.get(orgId) ?? { subscriptions: [], orders: [], configuration: [], provisioning: [], supportRequests: [] }; const records = area === 'configuration' ? [...this.instances.filter((item) => item.orgId === orgId).map((item) => ({ id: item.id, orgId, status: item.configurationStatus, state: item.state })), ...saved.configuration] : area === 'provisioning' ? [...this.instances.filter((item) => item.orgId === orgId).map((item) => ({ id: `provisioning:${item.id}`, orgId, status: item.state })), ...saved.provisioning] : area === 'supportRequests' ? this.support.get(orgId) ?? [] : saved[area]; return paginate(records, page); }
  async createSupportRequest(input: { orgId: string; actor: string; subject: string; message: string; idempotencyKey: string }) { const key = `support:${input.orgId}:${input.idempotencyKey}`; const replay = this.idempotent.get(key); if (replay) return replay as SafeRecord; const record = { id: `support:${(this.support.get(input.orgId)?.length ?? 0) + 1}`, orgId: input.orgId, status: 'open', summary: input.subject, version: 1 }; this.support.set(input.orgId, [...(this.support.get(input.orgId) ?? []), record]); this.idempotent.set(key, record); return record; }
  async createOrder(input: { orgId: string; actor: string; productId: string; idempotencyKey: string }) { const product = this.products.find((item) => item.id === input.productId); if (!product) throw new Error('not_found'); const order = this.portalRecord(input.orgId, 'orders', 'order', 'pending_operator_review', input.productId, input.idempotencyKey); if (!order.id.includes('-')) order.id = randomUUID(); this.orderSnapshots.set(order.id, product); return order; }
  async acceptTerms(input: { orgId: string; actor: string; orderId: string; termsDocumentId: string; termsVersion: string; termsDigest: string }) { const order = (this.portal.get(input.orgId)?.orders ?? []).find((item) => item.id === input.orderId); if (!order) throw new Error('not_found'); const terms = this.orderSnapshots.get(order.id)?.terms; if (terms && (terms.documentId !== input.termsDocumentId || terms.version !== input.termsVersion || terms.digest !== input.termsDigest)) throw new Error('terms_mismatch'); return { orderId: order.id, termsDocumentId: input.termsDocumentId, termsVersion: input.termsVersion, termsDigest: input.termsDigest, accepted: true }; }
  async createSubscription(input: { orgId: string; actor: string; orderId: string; idempotencyKey: string }) { return this.portalRecord(input.orgId, 'subscriptions', 'subscription', 'pending_provisioning', input.orderId, input.idempotencyKey); }
  async submitConfiguration(input: { orgId: string; actor: string; subscriptionId: string; values: Record<string, string | number | boolean>; idempotencyKey: string }) { return this.portalRecord(input.orgId, 'configuration', 'configuration', 'operator_assisted_required', input.subscriptionId, input.idempotencyKey); }
  async requestProvisioning(input: { orgId: string; actor: string; subscriptionId: string; idempotencyKey: string }) { return this.portalRecord(input.orgId, 'provisioning', 'provisioning', 'requested', input.subscriptionId, input.idempotencyKey); }
  async operatorRecords(resource: OperatorResource, page: { limit: number; cursor?: string }) { return paginate(this.operator.get(resource) ?? [], page); }
  async operatorAction(input: { actor: string; resource: OperatorResource; id: string; action: string; reason: string; idempotencyKey: string; expectedVersion?: number }) { const key = `operator:${input.resource}:${input.idempotencyKey}`; const replay = this.idempotent.get(key); if (replay) return replay as SafeRecord; if (!isOperatorActionAllowed(input.resource, input.action)) throw new Error('invalid_transition'); const records = this.operator.get(input.resource) ?? []; const record = records.find((item) => item.id === input.id); if (!record) throw new Error('not_found'); if (input.expectedVersion !== undefined && record.version !== input.expectedVersion) throw new Error('concurrency_conflict'); if (!stateAllows(record.state ?? record.status ?? 'unknown', input.action)) throw new Error('invalid_transition'); const next = { ...record, state: targetState(input.action), version: (record.version ?? 0) + 1 }; this.operator.set(input.resource, records.map((item) => item.id === input.id ? next : item)); this.idempotent.set(key, next); return next; }
  private portalRecord(orgId: string, area: keyof ClientPortal, kind: string, status: string, summary: string, idempotencyKey: string): SafeRecord { const key = `${kind}:${orgId}:${idempotencyKey}`; const replay = this.idempotent.get(key); if (replay) return replay as SafeRecord; const portal = this.portal.get(orgId) ?? { subscriptions: [], orders: [], configuration: [], provisioning: [], supportRequests: [] }; const record = { id: `${kind}:${portal[area].length + 1}`, orgId, status, summary, version: 1 }; this.portal.set(orgId, { ...portal, [area]: [...portal[area], record] }); this.idempotent.set(key, record); return record; }
  async reserveAudit(input: AuditReservationInput): Promise<AuditReservation> {
    if (this.failAuditReservation) throw new Error('audit_reservation_unavailable');
    const existing = this.pendingAudits.find((item) => item.orgId === input.orgId && item.correlationId === input.correlationId && item.resource === input.resource && item.action === input.action);
    if (existing) return existing;
    const reservation = { ...input, auditId: `audit:${this.pendingAudits.length + 1}`, status: 'pending' as const };
    this.pendingAudits.push(reservation);
    return reservation;
  }
  async finalizeAudit(reservation: AuditReservation, outcome: AuditEvent['outcome']) {
    if (this.failAuditFinalization) throw new Error('audit_finalization_unavailable');
    const current = this.pendingAudits.find((item) => item.auditId === reservation.auditId);
    if (!current) throw new Error('audit_reservation_missing');
    if (current.status === 'completed') return;
    current.status = 'completed';
    this.audits.push({ actor: current.actor, orgId: current.orgId, resource: current.resource, action: current.action, reason: current.reason, correlationId: current.correlationId, outcome });
  }
  async recordDeniedAudit(input: AuditReservationInput) {
    try {
      const reservation = await this.reserveAudit(input);
      await this.finalizeAudit(reservation, 'denied');
    } catch {
      // Authentication failures remain bounded; an unavailable audit store must not disclose claims.
    }
  }
}

/**
 * Production-only PostgREST adapter. Every persistence operation is a named,
 * org-scoped database RPC; it never exposes a generic table or SQL proxy.
 */
export class PostgrestProductApiService implements ProductApiService {
  constructor(private readonly rpc: PostgrestRpc, private readonly provisioning: ProductProvisioningAdapter) {}
  async publishedProducts(page: { limit: number; cursor?: string }) { return this.rpc('linkautowork_product_published_products', { p_limit: page.limit, p_cursor: page.cursor ?? null }) as Promise<Page<ProductSummary>>; }
  async clientInstances(orgId: string, page: { limit: number; cursor?: string }, audit?: AuditReservationInput) { const lease = requireAudit(audit); return this.rpc('linkautowork_product_client_instances_audited', { p_limit: page.limit, p_cursor: page.cursor ?? null }, orgId, lease) as Promise<Page<ClientInstance>>; }
  async transitionInstance(input: { orgId: string; actor: string; instanceId: string; action: 'pause' | 'resume'; reason: string; idempotencyKey: string }, audit?: AuditReservationInput) { const lease = requireAudit(audit); return this.rpc('linkautowork_product_transition_instance_audited', { p_instance_id: input.instanceId, p_action: input.action, p_reason: input.reason, p_idempotency_key: input.idempotencyKey }, input.orgId, lease) as Promise<ClientInstance>; }
  async createProduct(input: { actor: string; name: string; summary: string; version: number; reason: string; idempotencyKey: string }, audit?: AuditReservationInput) { const lease = requireAudit(audit); return this.rpc('linkautowork_product_create_offering_audited', { p_name: input.name, p_summary: input.summary, p_version: input.version, p_reason: input.reason, p_idempotency_key: input.idempotencyKey }, lease.orgId, lease) as Promise<ProductSummary>; }
  async updateProduct(input: { actor: string; id: string; summary: string; expectedVersion: number; reason: string; idempotencyKey: string }, audit?: AuditReservationInput) { const lease = requireAudit(audit); return this.rpc('linkautowork_product_update_offering_audited', { p_id: input.id, p_summary: input.summary, p_expected_version: input.expectedVersion, p_reason: input.reason, p_idempotency_key: input.idempotencyKey }, lease.orgId, lease) as Promise<ProductSummary>; }
  async receiveWebhook(input: { eventId: string; eventType: string; orgId: string; subscriptionId: string; occurredAt: string; providerSequence: number }) {
    try {
      return await this.rpc('linkautowork_product_record_provider_event', { p_event_id: input.eventId, p_event_type: input.eventType, p_subscription_id: input.subscriptionId, p_provider_occurred_at: input.occurredAt, p_provider_sequence: input.providerSequence }, input.orgId, { actor: 'provider:webhook', orgId: input.orgId, resource: 'provider-webhook', action: input.eventType, reason: 'signed provider webhook', correlationId: input.eventId }) as Promise<WebhookReceipt>;
    } catch (error) {
      throw normalizeProviderWebhookError(error);
    }
  }
  async clientPortal(orgId: string, area: keyof ClientPortal, page: { limit: number; cursor?: string }, audit?: AuditReservationInput) { const lease = requireAudit(audit); return this.rpc('linkautowork_product_client_portal_audited', { p_area: area, p_limit: page.limit, p_cursor: page.cursor ?? null }, orgId, lease) as Promise<Page<SafeRecord>>; }
  async createSupportRequest(input: { orgId: string; actor: string; subject: string; message: string; idempotencyKey: string }, audit?: AuditReservationInput) { const lease = requireAudit(audit); return this.rpc('linkautowork_product_create_support_request_audited', { p_subject: input.subject, p_message: input.message, p_idempotency_key: input.idempotencyKey }, input.orgId, lease) as Promise<SafeRecord>; }
  async createOrder(input: { orgId: string; actor: string; productId: string; idempotencyKey: string }, audit?: AuditReservationInput) { const lease = requireAudit(audit); return this.rpc('linkautowork_product_create_order_audited', { p_product_id: input.productId, p_idempotency_key: input.idempotencyKey }, input.orgId, lease) as Promise<SafeRecord>; }
  async createSubscription(input: { orgId: string; actor: string; orderId: string; idempotencyKey: string }, audit?: AuditReservationInput) { const lease = requireAudit(audit); return this.rpc('linkautowork_product_create_subscription_audited', { p_order_id: input.orderId, p_idempotency_key: input.idempotencyKey }, input.orgId, lease) as Promise<SafeRecord>; }
  /** Terms acceptance is durable and separate from subscription creation. */
  async acceptTerms(input: { orgId: string; actor: string; orderId: string; termsDocumentId: string; termsVersion: string; termsDigest: string }, audit?: AuditReservationInput) { const lease = requireAudit(audit); return this.rpc('linkautowork_product_accept_terms_audited', { p_order_id: input.orderId, p_terms_document_id: input.termsDocumentId, p_terms_version: input.termsVersion, p_terms_digest: input.termsDigest, p_actor: input.actor }, input.orgId, lease) as Promise<{ orderId: string; termsDocumentId: string; termsVersion: string; termsDigest: string; accepted: boolean }>; }
  async submitConfiguration(input: { orgId: string; actor: string; subscriptionId: string; values: Record<string, string | number | boolean>; idempotencyKey: string }, audit?: AuditReservationInput) { const lease = requireAudit(audit); return this.rpc('linkautowork_product_submit_configuration_audited', { p_subscription_id: input.subscriptionId, p_values: input.values, p_idempotency_key: input.idempotencyKey }, input.orgId, lease) as Promise<SafeRecord>; }
  async requestProvisioning(input: { orgId: string; actor: string; subscriptionId: string; idempotencyKey: string }, audit?: AuditReservationInput) { const lease = requireAudit(audit); return this.provisioning.request({ orgId: input.orgId, subscriptionId: input.subscriptionId, idempotencyKey: input.idempotencyKey }, lease); }
  async operatorRecords(resource: OperatorResource, page: { limit: number; cursor?: string }, audit?: AuditReservationInput) { const lease = requireAudit(audit); return this.rpc('linkautowork_product_operator_records_audited', { p_resource: resource, p_limit: page.limit, p_cursor: page.cursor ?? null }, lease.orgId, lease) as Promise<Page<SafeRecord>>; }
  async operatorAction(input: { actor: string; resource: OperatorResource; id: string; action: string; reason: string; idempotencyKey: string; expectedVersion?: number }, audit?: AuditReservationInput) { if (!isOperatorActionAllowed(input.resource, input.action)) throw new Error('invalid_transition'); const lease = requireAudit(audit); return this.rpc('linkautowork_product_operator_action_audited', { p_resource: input.resource, p_id: input.id, p_action: input.action, p_reason: input.reason, p_idempotency_key: input.idempotencyKey, p_expected_version: input.expectedVersion ?? null, p_actor: input.actor }, lease.orgId, lease) as Promise<SafeRecord>; }
  async reserveAudit(input: AuditReservationInput) {
    const result = await this.rpc('linkautowork_product_reserve_audit', { p_actor: input.actor, p_resource: input.resource, p_action: input.action, p_reason: input.reason, p_correlation_id: input.correlationId }, input.orgId) as { auditId: string; status: 'pending' | 'completed' };
    return { ...input, auditId: result.auditId, status: result.status };
  }
  async finalizeAudit(reservation: AuditReservation, outcome: AuditEvent['outcome']) {
    await this.rpc('linkautowork_product_finalize_audit', { p_actor: reservation.actor, p_resource: reservation.resource, p_action: reservation.action, p_reason: reservation.reason, p_correlation_id: reservation.correlationId, p_outcome: outcome }, reservation.orgId, reservation);
  }
  async recordDeniedAudit(input: AuditReservationInput) {
    const reservation = await this.reserveAudit(input);
    await this.finalizeAudit(reservation, 'denied');
  }
}

/** Adapter to the accepted WP-05 provisioning state machine; no n8n call happens here. */
export class PostgrestProvisioningAdapter implements ProductProvisioningAdapter {
  constructor(private readonly rpc: PostgrestRpc) {}
  async request(input: { orgId: string; subscriptionId: string; idempotencyKey: string }, audit?: AuditReservationInput) { const lease = requireAudit(audit); return this.rpc('linkautowork_product_request_provisioning_audited', { p_subscription_id: input.subscriptionId, p_idempotency_key: input.idempotencyKey }, input.orgId, lease) as Promise<SafeRecord>; }
  async compensate(input: { orgId: string; subscriptionId: string; reason: string; idempotencyKey: string }, audit?: AuditReservationInput) { const lease = requireAudit(audit); return this.rpc('linkautowork_product_compensate_provisioning_audited', { p_subscription_id: input.subscriptionId, p_reason: input.reason, p_idempotency_key: input.idempotencyKey }, input.orgId, lease) as Promise<SafeRecord>; }
}

export function hasRole(roles: ProductRole[], allowed: ProductRole[]) { return roles.some((role) => allowed.includes(role)); }
function stateAllows(state: string, action: string): boolean { return !((action === 'promote' && state !== 'canary') || (action === 'canary' && !['certified', 'ready'].includes(state)) || (action === 'resolve' && !['open', 'acknowledged'].includes(state)) || (action === 'acknowledge' && state !== 'open') || (action === 'resume' && state !== 'paused') || (action === 'pause' && !['active', 'ready'].includes(state)) || (action === 'retry' && state !== 'failed') || (action === 'compensate' && !['failed', 'provisioning'].includes(state))); }
function targetState(action: string): string { return ({ pause: 'paused', resume: 'active', acknowledge: 'acknowledged', resolve: 'resolved', canary: 'canary', promote: 'active', rollback: 'rolled_back', approve: 'approved', reject: 'rejected', supersede: 'superseded', compensate: 'compensating', retry: 'retrying' } as Record<string, string>)[action] ?? action; }
function paginate<T>(items: T[], page: { limit: number; cursor?: string }): Page<T> { const start = page.cursor ? Number.parseInt(page.cursor, 10) : 0; if (!Number.isSafeInteger(start) || start < 0) throw new Error('invalid_cursor'); const sliced = items.slice(start, start + page.limit); const next = start + sliced.length; return { items: sliced, ...(next < items.length ? { nextCursor: String(next) } : {}) }; }
