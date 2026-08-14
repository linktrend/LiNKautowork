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

export type ProviderStore = {
  accept(orgId: string, request: ProviderInvocationRequest, now?: Date): Promise<{ record: ProviderRequestRecord; replay: boolean }>;
  getRequest(orgId: string, requestId: string): Promise<ProviderRequestRecord>;
  transition(orgId: string, requestId: string, expectedVersion: number, next: ProviderState): Promise<ProviderRequestRecord>;
  writeReceipt(orgId: string, receipt: ProviderReceipt): Promise<ProviderReceipt>;
  admitCallback(orgId: string, callback: ProviderCallback): Promise<ProviderReceipt>;
  appendEvent(orgId: string, event: ProviderEvent): Promise<void>;
  listEvents(orgId: string, afterCursor: string | null, limit: number): Promise<ReturnType<typeof providerCursorPageSchema.parse>>;
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

/**
 * Stateful reference store used by route tests. It models provider-plane invariants
 * without storing raw caller payloads, credentials, logs, or consumer-domain state.
 */
export class InMemoryProviderStore implements ProviderStore {
  private readonly records = new Map<string, ProviderRequestRecord>();
  private readonly idempotency = new Map<string, string>();
  private readonly events = new Map<string, ProviderEvent[]>();
  private readonly killSwitches = new Set<string>();

  async accept(orgId: string, input: ProviderInvocationRequest, now = new Date()): Promise<{ record: ProviderRequestRecord; replay: boolean }> {
    const request = validateProviderInvocation(input, now);
    this.assertOrg(orgId, request.platform.org_id);
    this.assertNotKilled(orgId, request.automation.automation_id);
    const fingerprint = providerCanonicalRequestFingerprint(request);
    const key = `${orgId}:${request.idempotency_key}`;
    const priorId = this.idempotency.get(key);
    if (priorId) {
      const prior = this.records.get(priorId)!;
      if (prior.fingerprint !== fingerprint) throw new ProviderStoreError('conflict', 'idempotency key conflicts with changed canonical request content');
      return { record: this.clone(prior), replay: true };
    }
    const record: ProviderRequestRecord = { orgId, request, fingerprint, state: 'accepted', version: 1, attempts: 0 };
    this.records.set(request.request_id, record);
    this.idempotency.set(key, request.request_id);
    return { record: this.clone(record), replay: false };
  }

  async getRequest(orgId: string, requestId: string): Promise<ProviderRequestRecord> {
    return this.clone(this.require(orgId, requestId));
  }

  async transition(orgId: string, requestId: string, expectedVersion: number, next: ProviderState): Promise<ProviderRequestRecord> {
    const record = this.require(orgId, requestId);
    if (record.version !== expectedVersion) throw new ProviderStoreError('invalid_state', 'expected version does not match durable request version');
    if (terminal.has(record.state) || !allowedTransitions[record.state].includes(next)) throw new ProviderStoreError('invalid_state', 'provider lifecycle transition is not allowed');
    if ((next === 'queued' || next === 'running') && this.isKilled(orgId, record.request.automation.automation_id)) throw new ProviderStoreError('blocked', 'provider kill switch prevents new start');
    record.state = next;
    record.version += 1;
    if (next === 'running') record.attempts += 1;
    return this.clone(record);
  }

  async writeReceipt(orgId: string, input: ProviderReceipt): Promise<ProviderReceipt> {
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

  async admitCallback(orgId: string, input: ProviderCallback): Promise<ProviderReceipt> {
    const callback = providerCallbackSchema.parse(input);
    this.assertOrg(orgId, callback.org_id);
    const record = this.require(orgId, callback.request_id);
    if (callback.callback_binding_ref !== record.request.automation.configuration_ref.ref) throw new ProviderStoreError('invalid_callback', 'callback configuration binding does not match request');
    if (record.callbackTimestamp && new Date(callback.source_timestamp) <= new Date(record.callbackTimestamp)) throw new ProviderStoreError('invalid_callback', 'callback is replayed or out of order');
    if (callback.receipt.request_fingerprint !== record.fingerprint) throw new ProviderStoreError('invalid_callback', 'callback receipt fingerprint does not match request');
    const receipt = await this.writeReceipt(orgId, callback.receipt);
    record.callbackTimestamp = callback.source_timestamp;
    return receipt;
  }

  async appendEvent(orgId: string, input: ProviderEvent): Promise<void> {
    const event = providerEventSchema.parse(input);
    const records = this.events.get(orgId) ?? [];
    if (records.some((existing) => existing.event_id === event.event_id || (existing.source_ref === event.source_ref && existing.cursor === event.cursor))) return;
    records.push(event);
    this.events.set(orgId, records);
  }

  async listEvents(orgId: string, afterCursor: string | null, limit: number): Promise<ReturnType<typeof providerCursorPageSchema.parse>> {
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) throw new ProviderStoreError('forbidden', 'event cursor limit must be between 1 and 100');
    const records = this.events.get(orgId) ?? [];
    const start = afterCursor === null ? 0 : records.findIndex((event) => event.cursor === afterCursor) + 1;
    if (afterCursor !== null && start === 0) throw new ProviderStoreError('not_found', 'cursor is not available for organisation');
    const events = records.slice(start, start + limit);
    return providerCursorPageSchema.parse({ events, next_cursor: records[start + events.length]?.cursor ?? null, acknowledged_cursor: afterCursor });
  }

  async setKillSwitch(orgId: string, automationId: string | null, active: boolean): Promise<void> {
    const key = `${orgId}:${automationId ?? '*'}`;
    if (active) this.killSwitches.add(key); else this.killSwitches.delete(key);
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
