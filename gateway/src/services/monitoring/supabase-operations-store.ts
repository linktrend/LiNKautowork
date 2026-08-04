import type { SupabaseAuditClient } from '../../integrations/supabase-rpc.js';
import type { ActionAuthority, ActionRequest, DeploymentAuthority, DeploymentRequest, HealthRecord, MonitorTarget, OperationsStore, RetryOutboxItem } from './operations-service.js';

export class SupabaseOperationsStore implements OperationsStore {
  constructor(private readonly client: SupabaseAuditClient) {}
  listMonitorTargets(orgId: string) { return this.client.callOperationsRpc<MonitorTarget[]>('linkautowork_monitor_targets', { p_org_id: orgId }); }
  writeHealth(record: HealthRecord) { return this.client.callOperationsRpc<void>('linkautowork_write_health', { p_record: record }); }
  openAlertIncident(args: { orgId: string; instanceId: string; routingKey: string; severity: string; evidenceRef: string; repeatAfter: string }) { return this.client.callOperationsRpc<{ alertId: string; incidentId: string; deliver: boolean }>('linkautowork_open_alert_incident', { p_record: args }); }
  recoverAlertIncident(args: { orgId: string; instanceId: string; routingKey: string; evidenceRef: string }) { return this.client.callOperationsRpc<{ alertId: string; deliver: boolean } | undefined>('linkautowork_recover_alert_incident', { p_record: args }); }
  listHealth(orgId: string) { return this.client.callOperationsRpc<HealthRecord[]>('linkautowork_health_view', { p_org_id: orgId }); }
  transitionIncident(args: { orgId: string; incidentId: string; status: string; actor: string; evidenceRef?: string }) { return this.client.callOperationsRpc<void>('linkautowork_transition_incident', { p_record: args }); }
  recordAction(args: Record<string, unknown>) { return this.client.callOperationsRpc<void>('linkautowork_record_operation_action', { p_record: args }); }
  recordDeployment(args: Record<string, unknown>) { return this.client.callOperationsRpc<void>('linkautowork_record_deployment_event', { p_record: args }); }
  writePause(args: { orgId: string; scope: string; automationId?: string; instanceId?: string; active: boolean; actor: string; reason: string; evidenceRef: string }) { return this.client.callOperationsRpc<void>('linkautowork_write_pause', { p_record: args }); }
  runMaintenance(orgId: string) { return this.client.callOperationsRpc<Array<{ instanceId: string; findings: string[] }>>('linkautowork_run_maintenance_checks', { p_org_id: orgId }); }
  authorizeAction(orgId: string, instanceId: string, kind: ActionRequest['kind'], evidenceRef: string) { return this.client.callOperationsRpc<ActionAuthority>('linkautowork_authorize_operation_action', { p_org_id: orgId, p_instance_id: instanceId, p_action_kind: kind, p_evidence_ref: evidenceRef }); }
  loadDeploymentAuthority(orgId: string, deploymentId: string) { return this.client.callOperationsRpc<DeploymentAuthority>('linkautowork_deployment_authority', { p_org_id: orgId, p_deployment_id: deploymentId }); }
  claimRetry(orgId: string) { return this.client.callOperationsRpc<RetryOutboxItem | undefined>('linkautowork_claim_retry', { p_org_id: orgId }); }
  completeRetry(orgId: string, outboxId: string, delivered: boolean, error?: string) { return this.client.callOperationsRpc<void>('linkautowork_complete_retry', { p_org_id: orgId, p_outbox_id: outboxId, p_delivered: delivered, p_error: error ?? null }); }
  prepareDeployment(request: DeploymentRequest) { return this.client.callOperationsRpc<{ transitionId: string; disposition: 'prepared' | 'replay' | 'in_progress'; authority: DeploymentAuthority; committedRecord?: Record<string, unknown> }>('linkautowork_prepare_deployment_transition', { p_record: request }); }
  commitDeployment(orgId: string, transitionId: string, record: Record<string, unknown>) { return this.client.callOperationsRpc<void>('linkautowork_commit_deployment_transition', { p_org_id: orgId, p_transition_id: transitionId, p_record: record }); }
  failDeployment(orgId: string, transitionId: string, error: string, compensationFailed: boolean) { return this.client.callOperationsRpc<void>('linkautowork_fail_deployment_transition', { p_org_id: orgId, p_transition_id: transitionId, p_error: error, p_compensation_failed: compensationFailed }); }
}
