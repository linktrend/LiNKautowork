import type { MissionEnvelope } from '../contracts/types.js';
import type { N8nClient } from '../integrations/n8n-client.js';

type ScopedEntry = {
  reason: string;
  incidentId: string;
  mission: MissionEnvelope;
  activatedAt: string;
};

type GlobalState = {
  active: boolean;
  reason?: string;
  incidentId?: string;
  mission?: MissionEnvelope;
  activatedAt?: string;
  revokedWorkflows?: number;
};

export class KillSwitchService {
  private readonly scoped = new Map<string, ScopedEntry>();
  private globalState: GlobalState = { active: false };

  constructor(private readonly n8nClient: N8nClient) {}

  private scopedKey(tenantId: string, workflowId: string): string {
    return `${tenantId}:${workflowId}`;
  }

  activateScoped(args: {
    tenantId: string;
    workflowId: string;
    reason: string;
    incidentId: string;
    mission: MissionEnvelope;
  }): void {
    this.scoped.set(this.scopedKey(args.tenantId, args.workflowId), {
      reason: args.reason,
      incidentId: args.incidentId,
      mission: args.mission,
      activatedAt: new Date().toISOString(),
    });
  }

  releaseScoped(tenantId: string, workflowId: string): void {
    this.scoped.delete(this.scopedKey(tenantId, workflowId));
  }

  async activateGlobal(args: {
    reason: string;
    incidentId: string;
    mission: MissionEnvelope;
  }): Promise<{ revokedWorkflows: number }> {
    const revokedWorkflows = await this.n8nClient.deactivateAllActiveWorkflows();
    this.globalState = {
      active: true,
      reason: args.reason,
      incidentId: args.incidentId,
      mission: args.mission,
      activatedAt: new Date().toISOString(),
      revokedWorkflows,
    };
    return { revokedWorkflows };
  }

  releaseGlobal(): void {
    this.globalState = { active: false };
  }

  isBlocked(tenantId: string, workflowId: string):
    | { blocked: false }
    | { blocked: true; scope: 'global' | 'scoped'; reason: string } {
    if (this.globalState.active) {
      return {
        blocked: true,
        scope: 'global',
        reason: this.globalState.reason ?? 'global kill switch active',
      };
    }

    const scoped = this.scoped.get(this.scopedKey(tenantId, workflowId));
    if (scoped) {
      return {
        blocked: true,
        scope: 'scoped',
        reason: scoped.reason,
      };
    }

    return { blocked: false };
  }

  snapshot(): { global: GlobalState; scopedCount: number } {
    return {
      global: this.globalState,
      scopedCount: this.scoped.size,
    };
  }
}
