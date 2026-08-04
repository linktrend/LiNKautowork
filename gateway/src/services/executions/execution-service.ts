import type { ExecutionCallback } from '../../contracts/execution-callback.js';

export type ExecutionProjection = {
  orgId: string;
  executionId: string;
  status: ExecutionCallback['eventType'];
  lastSequence: number;
  acceptedAt?: string;
  startedAt?: string;
  completedAt?: string;
  evidenceRef?: string | null;
};

export interface ExecutionEventStore {
  recordAtomic(event: ExecutionCallback, capability: ExecutionCallbackCapability): Promise<ExecutionRecordResult>;
}
export type ExecutionCallbackCapability = { service: string; token: string };
export type ExecutionRecordResult = { disposition: 'applied' | 'duplicate' | 'out_of_order'; projection?: ExecutionProjection };

/**
 * Applies durable execution events in sequence. The store is the durable source
 * of truth; this projection deliberately retains only redacted references.
 */
export class ExecutionService {
  constructor(private readonly store: ExecutionEventStore) {}

  async record(event: ExecutionCallback, capability: ExecutionCallbackCapability): Promise<ExecutionRecordResult> {
    if (!capability.service || !capability.token) throw new Error('execution callback capability is required');
    return this.store.recordAtomic(event, capability);
  }
}
