import type { AppEnv } from '../config/env.js';
import { logWarn } from '../lib/logger.js';

export type AuditRecord = {
  // Internal name reflects the database reality: the value is written into
  // lautowork.audit_runs.org_id (FK to platform.organizations). See the
  // wire-mapping note in writeAudit for why the RPC still receives it as
  // `tenant_id`. (docs/archive/adr/0001, migration 20260715_000001.)
  orgId: string;
  run_id: string;
  task_id: string;
  dpr_id: string;
  status: string;
  token_usage: number;
  command_log: Record<string, unknown>;
  details: Record<string, unknown>;
  created_at?: string;
};

export type KillSwitchEventRecord = {
  orgId: string;
  scope: 'global' | 'scoped';
  action: 'activate' | 'release';
  incidentId: string;
  reason: string;
  metadata?: Record<string, unknown>;
};

export type LifecycleTransitionRecord = {
  orgId: string;
  workflowId: string;
  fromState: string;
  toState: string;
  protectedAction: boolean;
  approvals: Record<string, unknown>;
  reason: string;
};

export type ActiveKillSwitch = {
  scope: 'global' | 'scoped';
  workflow_id?: string;
  reason: string;
  incident_id: string;
  org_id?: string;
  activated_at?: string;
  metadata?: Record<string, unknown>;
};

export class SupabaseAuditClient {
  constructor(private readonly env: AppEnv) {}

  private headers(): Record<string, string> {
    return {
      apikey: this.env.SUPABASE_SERVICE_ROLE_KEY,
      authorization: `Bearer ${this.env.SUPABASE_SERVICE_ROLE_KEY}`,
      'content-type': 'application/json',
    };
  }

  private async callRpc(rpcName: string, body: Record<string, unknown>, label: string): Promise<Response> {
    const url = `${this.env.SUPABASE_URL}/rest/v1/rpc/${rpcName}`;
    const response = await fetch(url, {
      method: 'POST',
      headers: this.headers(),
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const responseBody = await response.text();
      logWarn(`${label} rpc failed`, { status: response.status, body: responseBody });
      throw new Error(`${label} rpc failed with status ${response.status}`);
    }

    return response;
  }

  async writeAudit(record: AuditRecord): Promise<void> {
    // Wire-boundary mapping. The database column is now `org_id` (FK to
    // platform.organizations), but the RPC public.linkautowork_write_audit_run
    // was deliberately kept accepting a SQL parameter literally named
    // `tenant_id` for backward compatibility — it writes that value into the
    // org_id column internally (see supabase/migrations/20260715_000001_
    // lautowork_control_core.sql and docs/archive/adr/0001 "Consequences"). PostgREST
    // maps JSON body keys to the RPC's named parameters, so the key sent on the
    // wire MUST remain `tenant_id`; changing it to `org_id` would break the
    // call until a separate, coordinated RPC signature change is made. The
    // internal field is `orgId` because that is what the value actually is now.
    const { orgId, ...auditColumns } = record;
    await this.callRpc(
      this.env.SUPABASE_AUDIT_RPC,
      { tenant_id: orgId, ...auditColumns },
      'audit',
    );
  }

  async writeKillSwitchEvent(record: KillSwitchEventRecord): Promise<void> {
    await this.callRpc(
      'linkautowork_write_killswitch_event',
      {
        tenant_id: record.orgId,
        scope: record.scope,
        action: record.action,
        incident_id: record.incidentId,
        reason: record.reason,
        metadata: record.metadata ?? {},
      },
      'killswitch',
    );
  }

  async writeLifecycleTransition(record: LifecycleTransitionRecord): Promise<void> {
    await this.callRpc(
      'linkautowork_write_lifecycle_transition',
      {
        tenant_id: record.orgId,
        workflow_id: record.workflowId,
        from_state: record.fromState,
        to_state: record.toState,
        protected_action: record.protectedAction,
        approvals: record.approvals,
        reason: record.reason,
      },
      'lifecycle',
    );
  }

  async listActiveKillSwitches(): Promise<ActiveKillSwitch[]> {
    const response = await this.callRpc('linkautowork_active_killswitches', {}, 'active-killswitches');
    const payload = (await response.json()) as unknown;
    if (!Array.isArray(payload)) {
      return [];
    }
    return payload as ActiveKillSwitch[];
  }
}
