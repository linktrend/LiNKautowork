import type { ExecutionCallback } from '../../contracts/execution-callback.js';
import type { SupabaseAuditClient } from '../../integrations/supabase-rpc.js';
import type { ExecutionCallbackCapability, ExecutionEventStore, ExecutionRecordResult } from './execution-service.js';

/** Writes the append-only event through the least-privilege WP-04 RPC. */
export class SupabaseExecutionEventStore implements ExecutionEventStore {
  constructor(private readonly client: SupabaseAuditClient) {}

  recordAtomic(event: ExecutionCallback, capability: ExecutionCallbackCapability): Promise<ExecutionRecordResult> {
    return this.client.recordExecutionCallback(event, capability);
  }
}
