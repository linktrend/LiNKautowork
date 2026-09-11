import { randomUUID } from 'node:crypto';
import {
  PROVIDER_RUN_STATES,
  providerCallbackSchema,
  providerCanonicalRequestFingerprint,
  providerCursorPageSchema,
  providerEventSchema,
  providerReceiptSchema,
  validateProviderInvocation,
  type ProviderInvocationRequest,
  type ProviderReceipt,
} from '../../../packages/automation-contracts/src/provider-contract.js';
import {
  PROVIDER_INVOKER_RPCS,
  assertProviderRuntimeInvoker,
  boundProviderEventPageLimit,
  compareProviderIdempotencyContent,
  projectProviderDurableRequest,
  type ProviderDurableAttempt,
  type ProviderDurableOutbox,
  type ProviderInvokerRpcName,
  type ProviderRuntimeInvoker,
} from '../../../packages/automation-contracts/src/provider-persistence.js';

type ProviderState = (typeof PROVIDER_RUN_STATES)[number];
type ProviderEvent = ReturnType<typeof providerEventSchema.parse>;
type ProviderCallback = ReturnType<typeof providerCallbackSchema.parse>;

/** A fail-closed persistence error whose category is safe to return from a route. */
export class ProviderStoreError extends Error {
  constructor(readonly category: 'conflict' | 'forbidden' | 'blocked' | 'invalid_state' | 'not_found' | 'invalid_callback', message: string) {
    super(message);
  }
}

/** Durable request metadata; inputs remain only opaque contract references. */
export type ProviderRequestRecord = {
  orgId: string;
  request: ProviderInvocationRequest;
  fingerprint: string;
  state: ProviderState;
  version: number;
  attempts: number;
  receipt?: ProviderReceipt;
  callbackTimestamp?: string;
};

/** Runtime JWT context required by every AW-02 invoker RPC. */
export type ProviderInvokerContext = ProviderRuntimeInvoker | { org_id: string; jwt_role: 'service_role' | 'anon' | 'public'; claim_org_id?: string };

export type ProviderStore = {
  accept(orgId: string, request: ProviderInvocationRequest, now?: Date, invoker?: ProviderInvokerContext): Promise<{ record: ProviderRequestRecord; replay: boolean }>;
  getRequest(orgId: string, requestId: string, invoker?: ProviderInvokerContext): Promise<ProviderRequestRecord>;
  transition(orgId: string, requestId: string, expectedVersion: number, next: ProviderState, invoker?: ProviderInvokerContext): Promise<ProviderRequestRecord>;
  writeReceipt(orgId: string, receipt: ProviderReceipt, invoker?: ProviderInvokerContext): Promise<ProviderReceipt>;
  admitCallback(orgId: string, callback: ProviderCallback, invoker?: ProviderInvokerContext): Promise<ProviderReceipt>;
  appendEvent(orgId: string, event: ProviderEvent, invoker?: ProviderInvokerContext): Promise<void>;
  listEvents(orgId: string, afterCursor: string | null, limit: number, invoker?: ProviderInvokerContext): Promise<ReturnType<typeof providerCursorPageSchema.parse>>;
  setKillSwitch(orgId: string, automationId: string | null, active: boolean): Promise<void>;
};

const terminal = new Set<ProviderState>(['succeeded', 'failed', 'expired', 'cancelled', 'timed_out', 'rejected', 'quarantined', 'unavailable', 'contract_incompatible']);
const allowedTransitions: Readonly<Record<ProviderState, readonly ProviderState[]>> = {
  accepted: ['queued', 'running', 'cancelled', 'expired', 'blocked', 'rejected', 'unavailable'],
  queued: ['running', 'cancelled', 'expired', 'blocked', 'failed', 'unavailable'],
  running: ['succeeded', 'failed', 'cancelled', 'timed_out', 'blocked', 'unavailable'],
  succeeded: [], failed: [], expired: [], cancelled: [], timed_out: [], rejected: [], quarantined: [], unavailable: [], contract_incompatible: [],
  blocked: ['cancelled', 'expired', 'unavailable'],
};

function runtimeInvoker(orgId: string, invoker?: ProviderInvokerContext): ProviderRuntimeInvoker {
  try {
    return assertProviderRuntimeInvoker(invoker ?? { org_id: orgId, jwt_role: 'runtime', claim_org_id: orgId });
  } catch (error) {
    throw new ProviderStoreError('forbidden', error instanceof Error ? error.message : 'organisation isolation denied');
  }
}

/**
 * Stateful reference store used by route tests. It models SECURITY INVOKER
 * provider-plane invariants without storing raw caller payloads, credentials,
 * logs, live queues, or consumer-domain state.
 */
export class InMemoryProviderStore implements ProviderStore {
  private readonly records = new Map<string, ProviderRequestRecord>();
  private readonly idempotency = new Map<string, string>();
  private readonly events = new Map<string, ProviderEvent[]>();
  private readonly killSwitches = new Set<string>();
  private readonly attempts = new Map<string, ProviderDurableAttempt[]>();
  private readonly outbox: ProviderDurableOutbox[] = [];

  async accept(orgId: string, input: ProviderInvocationRequest, now = new Date(), invoker?: ProviderInvokerContext): Promise<{ record: ProviderRequestRecord; replay: boolean }> {
    return this.invokeProviderRpc('linkautowork_provider_accept', { p_request: input, p_request_fingerprint: providerCanonicalRequestFingerprint(input), p_now: now.toISOString() }, orgId, invoker) as Promise<{ record: ProviderRequestRecord; replay: boolean }>;
  }

  async getRequest(orgId: string, requestId: string, invoker?: ProviderInvokerContext): Promise<ProviderRequestRecord> {
    return this.invokeProviderRpc('linkautowork_provider_get_request', { p_request_id: requestId }, orgId, invoker) as Promise<ProviderRequestRecord>;
  }

  async transition(orgId: string, requestId: string, expectedVersion: number, next: ProviderState, invoker?: ProviderInvokerContext): Promise<ProviderRequestRecord> {
    return this.invokeProviderRpc('linkautowork_provider_transition', { p_request_id: requestId, p_expected_version: expectedVersion, p_next_state: next }, orgId, invoker) as Promise<ProviderRequestRecord>;
  }

  async writeReceipt(orgId: string, input: ProviderReceipt, invoker?: ProviderInvokerContext): Promise<ProviderReceipt> {
    return this.invokeProviderRpc('linkautowork_provider_write_receipt', { p_receipt: input }, orgId, invoker) as Promise<ProviderReceipt>;
  }

  async admitCallback(orgId: string, input: ProviderCallback, invoker?: ProviderInvokerContext): Promise<ProviderReceipt> {
    return this.invokeProviderRpc('linkautowork_provider_admit_callback', { p_callback: input }, orgId, invoker) as Promise<ProviderReceipt>;
  }

  async appendEvent(orgId: string, input: ProviderEvent, invoker?: ProviderInvokerContext): Promise<void> {
    await this.invokeProviderRpc('linkautowork_provider_append_event', { p_event: input }, orgId, invoker);
  }

  async listEvents(orgId: string, afterCursor: string | null, limit: number, invoker?: ProviderInvokerContext): Promise<ReturnType<typeof providerCursorPageSchema.parse>> {
    return this.invokeProviderRpc('linkautowork_provider_list_events', { p_after_cursor: afterCursor, p_limit: limit }, orgId, invoker) as Promise<ReturnType<typeof providerCursorPageSchema.parse>>;
  }

  async setKillSwitch(orgId: string, automationId: string | null, active: boolean): Promise<void> {
    const key = `${orgId}:${automationId ?? '*'}`;
    if (active) this.killSwitches.add(key); else this.killSwitches.delete(key);
  }

  /** Returns tenant-isolated attempt rows for one request. */
  listAttempts(orgId: string, requestId: string): ProviderDurableAttempt[] {
    this.require(orgId, requestId);
    return (this.attempts.get(requestId) ?? []).map((attempt) => ({ ...attempt }));
  }

  /** Returns organisation-scoped outbox rows. Live delivery is not performed. */
  listOutbox(orgId: string): ProviderDurableOutbox[] {
    return this.outbox.filter((row) => row.org_id === orgId).map((row) => ({ ...row }));
  }

  /** Live queue drain is HOLD; this source boundary never delivers outbox rows. */
  deliverOutbox(): never {
    throw new ProviderStoreError('blocked', 'live outbox delivery remains HOLD');
  }

  /**
   * Atomic SECURITY INVOKER RPC surface. Unknown RPCs and service-role callers fail closed.
   */
  async invokeProviderRpc(name: ProviderInvokerRpcName, body: Record<string, unknown>, orgId: string, invoker?: ProviderInvokerContext): Promise<unknown> {
    if (!(PROVIDER_INVOKER_RPCS as readonly string[]).includes(name)) throw new ProviderStoreError('forbidden', 'unknown provider RPC');
    const runtime = runtimeInvoker(orgId, invoker);
    if (runtime.org_id !== orgId) throw new ProviderStoreError('forbidden', 'organisation isolation denied');
    switch (name) {
      case 'linkautowork_provider_accept':
        return this.acceptAtomic(orgId, body.p_request as ProviderInvocationRequest, String(body.p_request_fingerprint ?? ''), typeof body.p_now === 'string' ? new Date(body.p_now) : new Date());
      case 'linkautowork_provider_get_request':
        return this.clone(this.require(orgId, String(body.p_request_id)));
      case 'linkautowork_provider_transition':
        return this.transitionAtomic(orgId, String(body.p_request_id), Number(body.p_expected_version), body.p_next_state as ProviderState);
      case 'linkautowork_provider_write_receipt':
        return this.writeReceiptAtomic(orgId, body.p_receipt as ProviderReceipt);
      case 'linkautowork_provider_admit_callback':
        return this.admitCallbackAtomic(orgId, body.p_callback);
      case 'linkautowork_provider_append_event':
        return this.appendEventAtomic(orgId, body.p_event as ProviderEvent);
      case 'linkautowork_provider_list_events':
        return this.listEventsAtomic(orgId, body.p_after_cursor === undefined ? null : body.p_after_cursor as string | null, Number(body.p_limit));
      case 'linkautowork_provider_kill_switch_active':
        return this.isKilled(orgId, String(body.p_automation_id ?? ''));
      default:
        throw new ProviderStoreError('forbidden', 'unknown provider RPC');
    }
  }

  private acceptAtomic(orgId: string, input: ProviderInvocationRequest, suppliedFingerprint: string, now: Date): { record: ProviderRequestRecord; replay: boolean } {
    let request: ProviderInvocationRequest;
    try {
      request = validateProviderInvocation(input, now);
    } catch (error) {
      throw new ProviderStoreError('forbidden', error instanceof Error ? error.message : 'provider invocation is invalid');
    }
    this.assertOrg(orgId, request.platform.org_id);
    this.assertNotKilled(orgId, request.automation.automation_id);
    const fingerprint = providerCanonicalRequestFingerprint(request);
    if (suppliedFingerprint !== fingerprint) throw new ProviderStoreError('conflict', 'supplied request fingerprint does not match AW-01 canonical content');
    const key = `${orgId}:${request.idempotency_key}`;
    const priorId = this.idempotency.get(key);
    if (priorId) {
      const prior = this.records.get(priorId)!;
      try {
        compareProviderIdempotencyContent({ org_id: prior.orgId, idempotency_key: prior.request.idempotency_key, request_fingerprint: prior.fingerprint }, request);
      } catch (error) {
        throw new ProviderStoreError('conflict', error instanceof Error ? error.message : 'idempotency key conflicts with changed canonical request content');
      }
      return { record: this.clone(prior), replay: true };
    }
    const projection = projectProviderDurableRequest(request, fingerprint);
    const record: ProviderRequestRecord = { orgId, request, fingerprint, state: projection.state, version: projection.expected_version, attempts: 0 };
    this.records.set(request.request_id, record);
    this.idempotency.set(key, request.request_id);
    const cursor = `request:${request.request_id}:accepted`;
    this.appendEventAtomic(orgId, providerEventSchema.parse({
      event_id: randomUUID(), source_ref: 'autowork://outbox/request', cursor, correlation_refs: request.correlation_refs,
      occurred_at: now.toISOString(), type: 'request', payload_ref: { ref: `autowork://payload/${request.request_id}`, digest: fingerprint, observed_at: now.toISOString() },
    }));
    this.outbox.push({
      id: randomUUID(), org_id: orgId, request_id: request.request_id, kind: 'event_delivery', state: 'pending',
      payload_ref: `autowork://payload/${request.request_id}`, payload_digest: fingerprint, attempt_count: 0,
    });
    return { record: this.clone(record), replay: false };
  }

  private transitionAtomic(orgId: string, requestId: string, expectedVersion: number, next: ProviderState): ProviderRequestRecord {
    const record = this.require(orgId, requestId);
    if (record.version !== expectedVersion) throw new ProviderStoreError('invalid_state', 'expected version does not match durable request version');
    if (terminal.has(record.state) || !allowedTransitions[record.state].includes(next)) throw new ProviderStoreError('invalid_state', 'provider lifecycle transition is not allowed');
    if ((next === 'queued' || next === 'running') && this.isKilled(orgId, record.request.automation.automation_id)) throw new ProviderStoreError('blocked', 'provider kill switch prevents new start');
    record.state = next;
    record.version += 1;
    if (next === 'running') {
      record.attempts += 1;
      const rows = this.attempts.get(requestId) ?? [];
      rows.push({ request_id: requestId, attempt_number: record.attempts, state: next, job_retry: false, outbox_retry: false });
      this.attempts.set(requestId, rows);
    }
    return this.clone(record);
  }

  private writeReceiptAtomic(orgId: string, input: ProviderReceipt): ProviderReceipt {
    const receipt = providerReceiptSchema.parse(input);
    const record = this.require(orgId, receipt.request_id);
    if (receipt.automation.automation_id !== record.request.automation.automation_id || receipt.automation.version !== record.request.automation.version || receipt.automation.configuration_ref.digest !== record.request.automation.configuration_ref.digest) {
      throw new ProviderStoreError('forbidden', 'receipt automation/configuration does not bind to request');
    }
    if (record.receipt) {
      if (record.receipt.receipt_id !== receipt.receipt_id) throw new ProviderStoreError('conflict', 'provider receipt is immutable');
      return record.receipt;
    }
    record.receipt = receipt;
    record.state = receipt.state;
    record.attempts = receipt.attempt_count;
    return receipt;
  }

  private async admitCallbackAtomic(orgId: string, input: unknown): Promise<ProviderReceipt> {
    const callback = providerCallbackSchema.parse(input);
    this.assertOrg(orgId, callback.org_id);
    const record = this.require(orgId, callback.request_id);
    if (callback.callback_binding_ref !== record.request.automation.configuration_ref.ref) throw new ProviderStoreError('invalid_callback', 'callback configuration binding does not match request');
    if (record.callbackTimestamp && new Date(callback.source_timestamp) <= new Date(record.callbackTimestamp)) throw new ProviderStoreError('invalid_callback', 'callback is replayed or out of order');
    if (callback.receipt.request_fingerprint !== record.fingerprint) throw new ProviderStoreError('invalid_callback', 'callback receipt fingerprint does not match request');
    const receipt = this.writeReceiptAtomic(orgId, callback.receipt);
    record.callbackTimestamp = callback.source_timestamp;
    return receipt;
  }

  private appendEventAtomic(orgId: string, input: ProviderEvent): void {
    const event = providerEventSchema.parse(input);
    const records = this.events.get(orgId) ?? [];
    if (records.some((existing) => existing.event_id === event.event_id || (existing.source_ref === event.source_ref && existing.cursor === event.cursor))) return;
    records.push(event);
    this.events.set(orgId, records);
  }

  private listEventsAtomic(orgId: string, afterCursor: string | null, limit: number): ReturnType<typeof providerCursorPageSchema.parse> {
    try {
      boundProviderEventPageLimit(limit);
    } catch (error) {
      throw new ProviderStoreError('forbidden', error instanceof Error ? error.message : 'event cursor limit must be between 1 and 100');
    }
    const records = this.events.get(orgId) ?? [];
    const start = afterCursor === null ? 0 : records.findIndex((event) => event.cursor === afterCursor) + 1;
    if (afterCursor !== null && start === 0) throw new ProviderStoreError('not_found', 'cursor is not available for organisation');
    const events = records.slice(start, start + limit);
    return providerCursorPageSchema.parse({ events, next_cursor: records[start + events.length]?.cursor ?? null, acknowledged_cursor: afterCursor });
  }

  private require(orgId: string, requestId: string): ProviderRequestRecord {
    const record = this.records.get(requestId);
    if (!record) throw new ProviderStoreError('not_found', 'provider request not found');
    this.assertOrg(orgId, record.orgId);
    return record;
  }
  private assertOrg(expected: string, actual: string): void { if (expected !== actual) throw new ProviderStoreError('forbidden', 'organisation isolation denied'); }
  private isKilled(orgId: string, automationId: string): boolean { return this.killSwitches.has(`${orgId}:*`) || this.killSwitches.has(`${orgId}:${automationId}`); }
  private assertNotKilled(orgId: string, automationId: string): void { if (this.isKilled(orgId, automationId)) throw new ProviderStoreError('blocked', 'provider kill switch prevents request acceptance'); }
  private clone(record: ProviderRequestRecord): ProviderRequestRecord { return { ...record, request: structuredClone(record.request), receipt: record.receipt ? structuredClone(record.receipt) : undefined }; }
}

/** Creates an immutable initial receipt after a successful durable acceptance. */
export function createAcceptedProviderReceipt(record: ProviderRequestRecord, now = new Date()): ProviderReceipt {
  return providerReceiptSchema.parse({ contract_version: record.request.contract_version, request_id: record.request.request_id, receipt_id: randomUUID(), state: 'accepted', accepted_at: now.toISOString(), updated_at: now.toISOString(), attempt_count: 0, request_fingerprint: record.fingerprint, automation: record.request.automation, result_refs: [], evidence_refs: [], uncertain_outcome: false });
}
