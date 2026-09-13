import { providerInvocationRequestSchema, type ProviderInvocationRequest } from '../../../packages/automation-contracts/src/provider-contract.js';
import { InMemoryProviderStore, ProviderStoreError, type ProviderInvokerContext, type ProviderStore, type ProviderRequestRecord } from './provider-store.js';

type ProviderState = ProviderRequestRecord['state'];

/** Compact admission receipt that never includes raw inputs or consumer-domain fields. */
export type ProviderAdmissionStatus = {
  request_id: string;
  state: string;
  attempt_count: number;
  replay: boolean;
  automation: { automation_id: string; version: string; definition_digest: string; configuration_digest: string };
  receipt_id?: string;
};

/**
 * Source-only admission lifecycle over the AW-02 durable store.
 * It never activates a provider, drains a live queue, or claims production.
 */
export class ProviderAdmissionService {
  constructor(private readonly store: ProviderStore = new InMemoryProviderStore()) {}

  async admit(orgId: string, input: unknown, now?: Date, invoker?: ProviderInvokerContext): Promise<ProviderAdmissionStatus> {
    const request = providerInvocationRequestSchema.parse(input) as ProviderInvocationRequest;
    if (request.platform.org_id !== orgId) throw new ProviderStoreError('forbidden', 'payload organisation does not match authenticated Platform claim');
    const accepted = await this.store.accept(orgId, request, now, invoker);
    return this.status(accepted.record, accepted.replay);
  }

  async request(orgId: string, requestId: string, invoker?: ProviderInvokerContext): Promise<ProviderAdmissionStatus> {
    return this.status(await this.store.getRequest(orgId, requestId, invoker), false);
  }

  async transition(orgId: string, requestId: string, expectedVersion: number, next: ProviderState, invoker?: ProviderInvokerContext): Promise<ProviderAdmissionStatus> {
    const record = await this.store.transition(orgId, requestId, expectedVersion, next, invoker);
    return this.status(record, false);
  }

  async receipt(orgId: string, requestId: string, invoker?: ProviderInvokerContext) {
    const record = await this.store.getRequest(orgId, requestId, invoker);
    if (!record.receipt) throw new ProviderStoreError('not_found', 'provider receipt is not available');
    return record.receipt;
  }

  async events(orgId: string, cursor: string | null, limit: number, invoker?: ProviderInvokerContext) {
    return this.store.listEvents(orgId, cursor, limit, invoker);
  }

  private status(record: ProviderRequestRecord, replay: boolean): ProviderAdmissionStatus {
    return {
      request_id: record.request.request_id,
      state: record.state,
      attempt_count: record.attempts,
      replay,
      automation: {
        automation_id: record.request.automation.automation_id,
        version: record.request.automation.version,
        definition_digest: record.request.automation.definition_digest,
        configuration_digest: record.request.automation.configuration_ref.digest,
      },
      ...(record.receipt ? { receipt_id: record.receipt.receipt_id } : {}),
    };
  }
}
