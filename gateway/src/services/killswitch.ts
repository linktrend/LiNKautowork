import type { MissionEnvelope } from '../contracts/types.js';
import type { N8nClient } from '../integrations/n8n-client.js';
import type { ActiveKillSwitch, SupabaseAuditClient } from '../integrations/supabase-rpc.js';

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

export type KillSwitchStore = Pick<
  SupabaseAuditClient,
  'writeKillSwitchEvent' | 'listActiveKillSwitches'
>;

export class KillSwitchService {
  private readonly scoped = new Map<string, ScopedEntry>();
  private globalState: GlobalState = { active: false };

  constructor(
    private readonly n8nClient: N8nClient,
    private readonly store?: KillSwitchStore,
  ) {}

  private scopedKey(tenantId: string, workflowId: string): string {
    return `${tenantId}:${workflowId}`;
  }

  async hydrate(): Promise<void> {
    if (!this.store) {
      return;
    }

    const active = await this.store.listActiveKillSwitches();
    this.scoped.clear();
    this.globalState = { active: false };

    for (const entry of active) {
      this.applyHydratedEntry(entry);
    }
  }

  private applyHydratedEntry(entry: ActiveKillSwitch): void {
    if (entry.scope === 'global') {
      this.globalState = {
        active: true,
        reason: entry.reason,
        incidentId: entry.incident_id,
        activatedAt: entry.activated_at ?? new Date().toISOString(),
        mission: {
          tenantId: entry.org_id ?? '00000000-0000-0000-0000-000000000001',
          missionId: 'hydrated-killswitch',
          runId: 'hydrated-killswitch',
          taskId: 'hydrated-killswitch',
          dprId: 'hydrated-killswitch',
          triggerSource: 'killswitch_hydrate',
        },
      };
      return;
    }

    const workflowId = entry.workflow_id;
    if (!workflowId) {
      return;
    }

    const tenantId = entry.org_id ?? '00000000-0000-0000-0000-000000000001';
    this.scoped.set(this.scopedKey(tenantId, workflowId), {
      reason: entry.reason,
      incidentId: entry.incident_id,
      activatedAt: entry.activated_at ?? new Date().toISOString(),
      mission: {
        tenantId,
        missionId: 'hydrated-killswitch',
        runId: 'hydrated-killswitch',
        taskId: 'hydrated-killswitch',
        dprId: 'hydrated-killswitch',
        triggerSource: 'killswitch_hydrate',
      },
    });
  }

  async activateScoped(args: {
    tenantId: string;
    workflowId: string;
    reason: string;
    incidentId: string;
    mission: MissionEnvelope;
  }): Promise<void> {
    this.scoped.set(this.scopedKey(args.tenantId, args.workflowId), {
      reason: args.reason,
      incidentId: args.incidentId,
      mission: args.mission,
      activatedAt: new Date().toISOString(),
    });

    await this.persist({
      orgId: args.tenantId,
      scope: 'scoped',
      action: 'activate',
      incidentId: args.incidentId,
      reason: args.reason,
      metadata: { workflow_id: args.workflowId },
    });
  }

  async releaseScoped(tenantId: string, workflowId: string, args?: {
    reason?: string;
    incidentId?: string;
  }): Promise<void> {
    this.scoped.delete(this.scopedKey(tenantId, workflowId));

    await this.persist({
      orgId: tenantId,
      scope: 'scoped',
      action: 'release',
      incidentId: args?.incidentId ?? 'release',
      reason: args?.reason ?? 'release',
      metadata: { workflow_id: workflowId },
    });
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

    await this.persist({
      orgId: args.mission.tenantId,
      scope: 'global',
      action: 'activate',
      incidentId: args.incidentId,
      reason: args.reason,
      metadata: { revoked_workflows: revokedWorkflows },
    });

    return { revokedWorkflows };
  }

  async releaseGlobal(args?: {
    tenantId?: string;
    reason?: string;
    incidentId?: string;
  }): Promise<void> {
    const tenantId =
      args?.tenantId ??
      this.globalState.mission?.tenantId ??
      '00000000-0000-0000-0000-000000000001';
    this.globalState = { active: false };

    await this.persist({
      orgId: tenantId,
      scope: 'global',
      action: 'release',
      incidentId: args?.incidentId ?? 'release',
      reason: args?.reason ?? 'release',
      metadata: {},
    });
  }

  private async persist(record: {
    orgId: string;
    scope: 'global' | 'scoped';
    action: 'activate' | 'release';
    incidentId: string;
    reason: string;
    metadata: Record<string, unknown>;
  }): Promise<void> {
    if (!this.store) {
      return;
    }
    await this.store.writeKillSwitchEvent(record);
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
