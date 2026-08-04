import type { SupabaseAuditClient } from '../../integrations/supabase-rpc.js';
import type { PauseReader } from './runtime.js';

/** WP-05 enforcement adapter over the WP-08 durable pause read contract. */
export class SupabasePauseReader implements PauseReader {
  constructor(private readonly client: SupabaseAuditClient) {}
  async isPaused(args: { orgId: string; automationId: string; instanceId: string }) {
    const result = await this.client.callOperationsRpc<{ scope: 'global' | 'organisation' | 'automation' | 'instance'; reason?: string } | null>('linkautowork_active_pause', { p_org_id: args.orgId, p_automation_id: args.automationId, p_instance_id: args.instanceId }, args.orgId);
    return result ? { paused: true, ...result } : { paused: false };
  }
}
