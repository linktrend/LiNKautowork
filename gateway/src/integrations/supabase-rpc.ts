import type { AppEnv } from '../config/env.js';
import { logWarn } from '../lib/logger.js';

export type AuditRecord = {
  tenant_id: string;
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

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        apikey: this.env.SUPABASE_SERVICE_ROLE_KEY,
        authorization: `Bearer ${this.env.SUPABASE_SERVICE_ROLE_KEY}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify(record),
    });

    if (!response.ok) {
      const body = await response.text();
      logWarn('audit rpc write failed', { status: response.status, body });
      throw new Error(`audit rpc write failed with status ${response.status}`);
    }
  }
}
