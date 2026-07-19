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
      // The inbound mission envelope still carries `tenantId` on its own wire
      // contract (missionEnvelopeSchema), which the gateway does not own; that
      // value is the owning organization id and is stored as such (org_id).
      // Renaming the inbound mission field is a separate, caller-coordinated
      // change and is intentionally out of scope here (docs/archive/adr/0001).
      orgId: args.mission.tenantId,
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
