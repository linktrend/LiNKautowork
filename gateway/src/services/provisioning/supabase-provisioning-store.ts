import type { SupabaseAuditClient } from '../../integrations/supabase-rpc.js';
import type { ProvisioningRecord, ProvisioningStore } from './provisioning-service.js';

/** Narrow RPC-only provisioning persistence; no broad table write is used. */
export class SupabaseProvisioningStore implements ProvisioningStore {
  constructor(private readonly client: SupabaseAuditClient) {}
  begin(orgId: string, requestRef: string): Promise<ProvisioningRecord | undefined> { return this.client.beginProvisioning(orgId, requestRef); }
  mark(orgId: string, requestId: string, status: string, fields: Record<string, unknown> = {}): Promise<void> { return this.client.markProvisioning(orgId, requestId, status, fields); }
  createDeployment(args: { request: ProvisioningRecord; workflowId: string }): Promise<string> { return this.client.createProvisioningDeployment(args.request, args.workflowId); }
}
