import type { AppEnv } from '../config/env.js';
import { logWarn } from '../lib/logger.js';

export type AuditRecord = {
  // Internal name reflects the database reality: the value is written into
  // lautowork.audit_runs.org_id (FK to platform.organizations). See the
  // wire-mapping note in writeAudit for why the RPC still receives it as
  // `tenant_id`. (docs/adr/0001, migration 20260715_000001.)
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

export class SupabaseAuditClient {
  constructor(private readonly env: AppEnv) {}

  async writeAudit(record: AuditRecord): Promise<void> {
    const url = `${this.env.SUPABASE_URL}/rest/v1/rpc/${this.env.SUPABASE_AUDIT_RPC}`;

    // Wire-boundary mapping. The database column is now `org_id` (FK to
    // platform.organizations), but the RPC public.linkautowork_write_audit_run
    // was deliberately kept accepting a SQL parameter literally named
    // `tenant_id` for backward compatibility — it writes that value into the
    // org_id column internally (see supabase/migrations/20260715_000001_
    // lautowork_control_core.sql and docs/adr/0001 "Consequences"). PostgREST
    // maps JSON body keys to the RPC's named parameters, so the key sent on the
    // wire MUST remain `tenant_id`; changing it to `org_id` would break the
    // call until a separate, coordinated RPC signature change is made. The
    // internal field is `orgId` because that is what the value actually is now.
    const { orgId, ...auditColumns } = record;
    const rpcBody = { tenant_id: orgId, ...auditColumns };

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        apikey: this.env.SUPABASE_SERVICE_ROLE_KEY,
        authorization: `Bearer ${this.env.SUPABASE_SERVICE_ROLE_KEY}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify(rpcBody),
    });

    if (!response.ok) {
      const body = await response.text();
      logWarn('audit rpc write failed', { status: response.status, body });
      throw new Error(`audit rpc write failed with status ${response.status}`);
    }
  }
}
