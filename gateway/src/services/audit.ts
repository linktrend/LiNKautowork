import type { MissionEnvelope } from '../contracts/types.js';
import type { AuditRecord, SupabaseAuditClient } from '../integrations/supabase-rpc.js';

export class AuditService {
  constructor(private readonly client: SupabaseAuditClient) {}

  async writeRunAudit(args: {
    mission: MissionEnvelope;
    status: string;
    tokenUsage: number;
    commandLog: Record<string, unknown>;
    details: Record<string, unknown>;
  }): Promise<void> {
    const payload: AuditRecord = {
      tenant_id: args.mission.tenantId,
      run_id: args.mission.runId,
      task_id: args.mission.taskId,
      dpr_id: args.mission.dprId,
      status: args.status,
      token_usage: args.tokenUsage,
      command_log: args.commandLog,
      details: args.details,
      created_at: new Date().toISOString(),
    };

    await this.client.writeAudit(payload);
  }
}
