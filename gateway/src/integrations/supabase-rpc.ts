import type { AppEnv } from '../config/env.js';
import { logWarn } from '../lib/logger.js';
import type { ExecutionCallback } from '../contracts/execution-callback.js';
import type { BoundInstance, ExecutionReceipt, ExecutionStore } from '../services/instances/runtime.js';
import type { ExecutionCallbackCapability, ExecutionRecordResult } from '../services/executions/execution-service.js';
import type { ProvisioningRecord } from '../services/provisioning/provisioning-service.js';

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

export class SupabaseAuditClient implements ExecutionStore {
  constructor(private readonly env: AppEnv) {}

  private headers(): Record<string, string> {
    return {
      apikey: this.env.SUPABASE_SERVICE_ROLE_KEY,
      authorization: `Bearer ${this.env.SUPABASE_SERVICE_ROLE_KEY}`,
      'content-type': 'application/json',
    };
  }

  private async callRpc(rpcName: string, body: Record<string, unknown>, label: string, runtimeOrgId?: string): Promise<Response> {
    if (runtimeOrgId && !this.env.SUPABASE_RUNTIME_JWT) throw new Error('organisation-scoped automation runtime credential is not configured');
    const url = `${this.env.SUPABASE_URL}/rest/v1/rpc/${rpcName}`;
    const response = await fetch(url, {
      method: 'POST',
      headers: runtimeOrgId ? { ...this.headers(), authorization: `Bearer ${this.env.SUPABASE_RUNTIME_JWT}`, 'x-link-org-id': runtimeOrgId } : this.headers(),
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const responseBody = await response.text();
      logWarn(`${label} rpc failed`, { status: response.status, body: responseBody });
      throw new Error(`${label} rpc failed with status ${response.status}`);
    }

    return response;
  }

  private async table(path: string, init?: RequestInit): Promise<Response> {
    const response = await fetch(`${this.env.SUPABASE_URL}/rest/v1/${path}`, { ...init, headers: { ...this.headers(), 'Accept-Profile': 'lautowork', 'Content-Profile': 'lautowork', ...(init?.headers ?? {}) } });
    if (!response.ok) throw new Error(`automation runtime storage failed with status ${response.status}`);
    return response;
  }

  async findBoundInstance(orgId: string, service: string, operation: string): Promise<BoundInstance | undefined> {
    const response = await this.callRpc('linkautowork_resolve_bound_instance', { p_org_id: orgId, p_consumer_system: service, p_operation: operation }, 'resolve-bound-instance', orgId);
    const payload = await response.json() as BoundInstance | null;
    return payload ?? undefined;
  }
  async acceptExecution(args: { executionId: string; orgId: string; instanceId: string; releaseId: string; deploymentId: string; idempotencyKey: string; inputDigest: string; callbackService: string; callbackTokenDigest: string }): Promise<ExecutionReceipt> {
    const response = await this.callRpc('linkautowork_accept_execution', {
      p_execution_id: args.executionId, p_org_id: args.orgId, p_instance_id: args.instanceId,
      p_release_id: args.releaseId, p_deployment_id: args.deploymentId, p_idempotency_key: args.idempotencyKey,
      p_input_digest: args.inputDigest, p_callback_service: args.callbackService, p_callback_token_digest: args.callbackTokenDigest,
    }, 'accept-execution', args.orgId);
    return await response.json() as ExecutionReceipt;
  }
  async beginProvisioning(orgId: string, requestRef: string): Promise<ProvisioningRecord | undefined> {
    const response = await this.callRpc('linkautowork_begin_provisioning', { p_org_id: orgId, p_request_ref: requestRef }, 'begin-provisioning', orgId);
    return (await response.json() as ProvisioningRecord | null) ?? undefined;
  }
  async markProvisioning(orgId: string, requestId: string, status: string, fields: Record<string, unknown>): Promise<void> {
    await this.callRpc('linkautowork_mark_provisioning', { p_request_id: requestId, p_status: status, p_fields: fields }, 'mark-provisioning', orgId);
  }
  async createProvisioningDeployment(request: ProvisioningRecord, workflowId: string): Promise<string> {
    const response = await this.callRpc('linkautowork_create_provisioning_deployment', { p_request_id: request.requestId, p_workflow_id: workflowId }, 'create-provisioning-deployment', request.orgId);
    return await response.json() as string;
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

  async appendExecutionEvent(event: ExecutionCallback): Promise<void> {
    await this.callRpc('linkautowork_append_execution_event', {
      p_org_id: event.orgId,
      p_execution_id: event.executionId,
      p_sequence: event.sequence,
      p_event_type: event.eventType,
      p_occurred_at: event.occurredAt,
      p_payload_digest: event.payloadDigest ?? null,
      p_evidence_ref: event.evidenceRef ?? null,
    }, 'execution-event');
  }

  async recordExecutionCallback(event: ExecutionCallback, capability: ExecutionCallbackCapability): Promise<ExecutionRecordResult> {
    const response = await this.callRpc('linkautowork_record_execution_callback', {
      p_org_id: event.orgId, p_execution_id: event.executionId, p_callback_service: capability.service,
      p_callback_token: capability.token, p_sequence: event.sequence, p_event_type: event.eventType,
      p_occurred_at: event.occurredAt, p_payload_digest: event.payloadDigest ?? null, p_evidence_ref: event.evidenceRef ?? null,
    }, 'record-execution-callback', event.orgId);
    return await response.json() as ExecutionRecordResult;
  }

  /** Calls an org-scoped Librarian RPC. Only the narrow durable adapter uses this boundary. */
  async callLibrarianRpc<T>(rpcName: string, body: Record<string, unknown>): Promise<T> {
    const orgId=body.p_org_id; if(typeof orgId!=='string')throw new Error('Librarian RPC requires an organisation consistency guard');
    const response = await this.callRpc(rpcName,body,'automation-librarian',orgId);
    return (await response.json()) as T;
  }

  /** Narrow durable operations boundary; every RPC re-derives and checks org ownership. */
  async callOperationsRpc<T>(rpcName: string, body: Record<string, unknown>, explicitOrgId?: string): Promise<T> {
    const record = body.p_record as Record<string, unknown> | undefined;
    const orgId = explicitOrgId ?? (typeof body.p_org_id === 'string' ? body.p_org_id : typeof record?.orgId === 'string' ? record.orgId : undefined);
    const response = await this.callRpc(rpcName, body, 'automation-operations', orgId);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  /** Calls an org-scoped provider-plane RPC with the runtime JWT; never service-role bypasses RLS. */
  async callProviderRpc<T>(rpcName: string, body: Record<string, unknown>, orgId: string): Promise<T> {
    const response = await this.callRpc(rpcName, body, 'provider-plane', orgId);
    return (await response.json()) as T;
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
