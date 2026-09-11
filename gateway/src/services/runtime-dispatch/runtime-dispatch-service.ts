import { randomUUID } from 'node:crypto';
import {
  providerCanonicalRequestFingerprint,
  providerReceiptSchema,
  validateProviderInvocation,
  type ProviderInvocationRequest,
  type ProviderReceipt,
} from '../../../../packages/automation-contracts/src/index.js';
import { dispatchDisposition } from '../provider-dispatch.js';
import { RuntimeDispatchError } from './errors.js';
import { bridgeN8nCallbackToProvider, type N8nRuntimeCallback } from './n8n-callback-bridge.js';

const DOES_NOT_PROVE = [
  'automation_run',
  'consumer_outcome',
  'consumer_gate',
  'external_side_effect',
  'e2e_readiness',
  'production_readiness',
] as const;

/** Compact durable activation view that never includes caller payloads or credentials. */
export type RuntimeActivationStatus = {
  request_id: string;
  org_id: string;
  state: 'accepted' | 'queued' | 'succeeded' | 'failed' | 'cancelled' | 'timed_out';
  fingerprint: string;
  callback_binding_ref: string;
  receipt_id: string;
  n8n_dispatched: false;
  live_n8n_activation: 'hold';
  does_not_prove: typeof DOES_NOT_PROVE;
};

/** Result of a source-only durable activation. */
export type RuntimeActivationResult = {
  replay: boolean;
  disposition: 'queued';
  activation: RuntimeActivationStatus;
};

type ActivationRecord = {
  orgId: string;
  request: ProviderInvocationRequest;
  fingerprint: string;
  receiptId: string;
  acceptedAt: string;
  state: RuntimeActivationStatus['state'];
  receipt?: ProviderReceipt;
  callbackTimestamp?: string;
};

/** Injected clock and eligibility flags. This object must not include n8n clients or credentials. */
export type RuntimeDispatchOptions = {
  activationInterfaceSupported?: boolean;
  now?: () => Date;
  isKilled?: (orgId: string, automationId: string) => boolean;
};

/**
 * In-process gateway module for durable n8n activation intent and callback bridging.
 * It never constructs or calls an n8n client, provider HTTP client, or credential store.
 */
export class RuntimeDispatchService {
  private readonly records = new Map<string, ActivationRecord>();
  private readonly idempotency = new Map<string, string>();
  private readonly activationInterfaceSupported: boolean;
  private readonly now: () => Date;
  private readonly isKilled: (orgId: string, automationId: string) => boolean;

  constructor(options: RuntimeDispatchOptions = {}) {
    this.activationInterfaceSupported = options.activationInterfaceSupported === true;
    this.now = options.now ?? (() => new Date());
    this.isKilled = options.isKilled ?? (() => false);
  }

  /**
   * Records a durable n8n activation intent for an AW-02 request.
   * Eligible requests are queued locally and are never dispatched to n8n.
   */
  activate(orgId: string, input: unknown): RuntimeActivationResult {
    const request = this.parseInvocation(orgId, input);
    const fingerprint = providerCanonicalRequestFingerprint(request);
    const key = `${orgId}:${request.idempotency_key}`;
    const priorId = this.idempotency.get(key);
    if (priorId) {
      const prior = this.require(orgId, priorId);
      if (prior.fingerprint !== fingerprint) {
        throw new RuntimeDispatchError('conflict', 'idempotency key conflicts with changed canonical request content');
      }
      return { replay: true, disposition: 'queued', activation: this.status(prior) };
    }

    this.assertEligible(request, orgId);
    if (this.isKilled(orgId, request.automation.automation_id)) {
      throw new RuntimeDispatchError('blocked', 'provider kill switch prevents n8n activation');
    }

    const record: ActivationRecord = {
      orgId,
      request,
      fingerprint,
      receiptId: randomUUID(),
      acceptedAt: this.now().toISOString(),
      state: 'queued',
    };
    this.records.set(request.request_id, record);
    this.idempotency.set(key, request.request_id);
    return { replay: false, disposition: 'queued', activation: this.status(record) };
  }

  /** Returns compact durable activation metadata for one organisation-scoped request. */
  statusOf(orgId: string, requestId: string): RuntimeActivationStatus {
    return this.status(this.require(orgId, requestId));
  }

  /**
   * Admits a bounded n8n callback and binds it to the durable AW-02 request/receipt pair.
   * Out-of-order, mismatched, or secret-shaped callbacks fail closed.
   */
  admitCallback(orgId: string, input: unknown): ProviderReceipt {
    const record = this.locateForCallback(orgId, input);
    const bridged = bridgeN8nCallbackToProvider(input, record.request, record.fingerprint, record.acceptedAt);
    if (bridged.receipt_id !== record.receiptId) {
      throw new RuntimeDispatchError('invalid_callback', 'callback receipt does not bind to activation');
    }
    if (record.callbackTimestamp && new Date(bridged.source_timestamp) <= new Date(record.callbackTimestamp)) {
      throw new RuntimeDispatchError('invalid_callback', 'callback is replayed or out of order');
    }
    const receipt = providerReceiptSchema.parse(bridged.receipt);
    if (record.receipt) {
      if (record.receipt.receipt_id !== receipt.receipt_id) {
        throw new RuntimeDispatchError('conflict', 'provider receipt is immutable');
      }
    }
    record.receipt = receipt;
    record.state = receipt.state as ActivationRecord['state'];
    record.callbackTimestamp = bridged.source_timestamp;
    return receipt;
  }

  private parseInvocation(orgId: string, input: unknown): ProviderInvocationRequest {
    let request: ProviderInvocationRequest;
    try {
      request = validateProviderInvocation(input as Parameters<typeof validateProviderInvocation>[0], this.now());
    } catch (error) {
      const message = error instanceof Error ? error.message : 'provider invocation is invalid';
      if (message.includes('expired') || message.includes('revoked')) {
        throw new RuntimeDispatchError('forbidden', message);
      }
      throw new RuntimeDispatchError('invalid_state', message);
    }
    if (request.platform.org_id !== orgId) {
      throw new RuntimeDispatchError('forbidden', 'payload organisation does not match authenticated Platform claim');
    }
    return request;
  }

  private assertEligible(request: ProviderInvocationRequest, orgId: string): void {
    const target = `${request.operation_kind}:${request.result_destination_ref}`;
    const disposition = dispatchDisposition({
      handoffRef: request.brain_handoff_ref?.ref ?? 'brain://handoff/unspecified',
      handoffOrg: orgId,
      requestOrg: orgId,
      activationSupported: this.activationInterfaceSupported,
      target,
    });
    if (disposition === 'rejected') {
      throw new RuntimeDispatchError('rejected', 'consumer factory targets are not dispatchable');
    }
    if (request.operation_kind === 'external_assistance') {
      throw new RuntimeDispatchError('hold', 'external assistance activation is HOLD');
    }
    if (!this.activationInterfaceSupported || disposition === 'unavailable') {
      throw new RuntimeDispatchError('unavailable', 'n8n activation interface is unavailable');
    }
  }

  private locateForCallback(orgId: string, input: unknown): ActivationRecord {
    const requestId = typeof input === 'object' && input && 'request_id' in input && typeof (input as N8nRuntimeCallback).request_id === 'string'
      ? (input as { request_id: string }).request_id
      : '';
    if (!requestId) throw new RuntimeDispatchError('invalid_callback', 'callback request_id is required');
    return this.require(orgId, requestId);
  }

  private require(orgId: string, requestId: string): ActivationRecord {
    const record = this.records.get(requestId);
    if (!record) throw new RuntimeDispatchError('not_found', 'runtime activation is not found');
    if (record.orgId !== orgId) throw new RuntimeDispatchError('forbidden', 'organisation isolation denied');
    return record;
  }

  private status(record: ActivationRecord): RuntimeActivationStatus {
    return {
      request_id: record.request.request_id,
      org_id: record.orgId,
      state: record.state,
      fingerprint: record.fingerprint,
      callback_binding_ref: record.request.automation.configuration_ref.ref,
      receipt_id: record.receiptId,
      n8n_dispatched: false,
      live_n8n_activation: 'hold',
      does_not_prove: [...DOES_NOT_PROVE],
    };
  }
}
