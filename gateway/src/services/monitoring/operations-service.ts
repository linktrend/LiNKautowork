import { createHash, randomUUID } from 'node:crypto';

export type ExecutionMonitorRow = { executionId: string; status: 'accepted' | 'started' | 'succeeded' | 'failed' | 'timed_out' | 'cancelled'; acceptedAt: string; startedAt?: string; completedAt?: string; callbackAt?: string; retryCount: number; failureClass?: string };
export type MonitorTarget = { orgId: string; automationId: string; instanceId: string; cadenceMs: number; graceMs: number; lastExpectedAt: string; enabled: boolean; executions: ExecutionMonitorRow[] };
export type HealthRecord = { orgId: string; instanceId: string; state: 'healthy' | 'warning' | 'critical' | 'unknown'; missingSchedule: boolean; staleCallback: boolean; consecutiveFailures: number; successRate: number; observedAt: string; failureClasses: string[] };
export type AlertDelivery = { alertId: string; orgId: string; routingKey: string; severity: string; recovered: boolean };
export type ActionRequest = { orgId: string; actor: string; kind: 'retry' | 'pause_instance' | 'fail_over' | 'rollback_certified'; instanceId: string; reason: string; evidenceRef: string };
export type ActionAuthority = { allowed: boolean; supportsFailover: boolean; authorizationRef?: string; currentWorkflowId?: string; baselineWorkflowId?: string };
export type DeploymentRequest = { orgId: string; actor: string; deploymentId: string; action: 'canary' | 'promote' | 'rollback'; reason: string; idempotencyKey: string };
export type DeploymentAuthority = { baselineDeploymentId: string; candidateReleaseId: string; baselineReleaseId: string; candidateWorkflowId: string; baselineWorkflowId: string; compatibleBindings: boolean; candidateCertified: boolean; baselineCertified: boolean; approvalRef?: string; healthEvidenceRef?: string; sampleCount: number; minimumSamples: number; elapsedMs: number; minimumWindowMs: number; candidateSuccessRate: number; baselineSuccessRate: number };
export type RetryOutboxItem = { id: string; orgId: string; instanceId: string; webhookPath: string; method: string };

export interface OperationsStore {
  listMonitorTargets(orgId: string): Promise<MonitorTarget[]>;
  writeHealth(record: HealthRecord): Promise<void>;
  openAlertIncident(args: { orgId: string; instanceId: string; routingKey: string; severity: string; evidenceRef: string; repeatAfter: string }): Promise<{ alertId: string; incidentId: string; deliver: boolean }>;
  recoverAlertIncident(args: { orgId: string; instanceId: string; routingKey: string; evidenceRef: string }): Promise<{ alertId: string; deliver: boolean } | undefined>;
  listHealth(orgId: string): Promise<HealthRecord[]>;
  transitionIncident(args: { orgId: string; incidentId: string; status: string; actor: string; evidenceRef?: string }): Promise<void>;
  recordAction(args: Record<string, unknown>): Promise<void>;
  recordDeployment(args: Record<string, unknown>): Promise<void>;
  writePause(args: { orgId: string; scope: string; automationId?: string; instanceId?: string; active: boolean; actor: string; reason: string; evidenceRef: string }): Promise<void>;
  runMaintenance(orgId: string): Promise<Array<{ instanceId: string; findings: string[] }>>;
  authorizeAction(orgId: string, instanceId: string, kind: ActionRequest['kind'], evidenceRef: string): Promise<ActionAuthority>;
  loadDeploymentAuthority(orgId: string, deploymentId: string): Promise<DeploymentAuthority>;
  claimRetry(orgId: string): Promise<RetryOutboxItem | undefined>;
  completeRetry(orgId: string, outboxId: string, delivered: boolean, error?: string): Promise<void>;
  prepareDeployment(request: DeploymentRequest): Promise<{ transitionId: string; disposition: 'prepared' | 'replay' | 'in_progress'; authority: DeploymentAuthority; committedRecord?: Record<string, unknown> }>;
  commitDeployment(orgId: string, transitionId: string, record: Record<string, unknown>): Promise<void>;
  failDeployment(orgId: string, transitionId: string, error: string, compensationFailed: boolean): Promise<void>;
}
export interface AlertAdapter { deliver(alert: AlertDelivery): Promise<void>; }
export interface ActionExecutor { retry(orgId: string, instanceId: string, authority: ActionAuthority): Promise<Record<string, unknown>>; pause(orgId: string, instanceId: string, authority: ActionAuthority): Promise<Record<string, unknown>>; failover(orgId: string, instanceId: string, authority: ActionAuthority): Promise<Record<string, unknown>>; rollback(orgId: string, instanceId: string, authority: ActionAuthority): Promise<Record<string, unknown>>; }
export interface DeploymentExecutor { apply(action: 'canary' | 'promote' | 'rollback', authority: DeploymentAuthority): Promise<void>; compensate(action: 'canary' | 'promote' | 'rollback', authority: DeploymentAuthority): Promise<void>; }
export interface RetryDispatcher { dispatch(item: RetryOutboxItem): Promise<void>; }

const digest = (value: unknown) => `sha256:${createHash('sha256').update(JSON.stringify(value)).digest('hex')}`;
export class OperationsService {
  constructor(private readonly store: OperationsStore, private readonly alerts: AlertAdapter, private readonly executor: ActionExecutor, private readonly deployments: DeploymentExecutor, private readonly retryDispatcher: RetryDispatcher, private readonly clock = () => new Date()) {}
  async monitor(orgId: string): Promise<HealthRecord[]> {
    const targets = await this.store.listMonitorTargets(orgId); const results: HealthRecord[] = [];
    for (const target of targets) {
      if (target.orgId !== orgId) throw new Error('monitor store returned cross-organisation target');
      const executions = [...target.executions].sort((a, b) => a.acceptedAt.localeCompare(b.acceptedAt)); const terminal = executions.filter((e) => ['succeeded', 'failed', 'timed_out', 'cancelled'].includes(e.status)); const success = terminal.filter((e) => e.status === 'succeeded'); let failures = 0;
      for (const event of [...terminal].reverse()) { if (event.status === 'succeeded') break; failures += 1; }
      const nowMs = this.clock().getTime(); const lastSuccess = success.at(-1)?.completedAt; const missingSchedule = target.enabled && Date.parse(target.lastExpectedAt) + target.cadenceMs + target.graceMs < nowMs && (!lastSuccess || Date.parse(lastSuccess) < Date.parse(target.lastExpectedAt));
      const staleCallback = executions.some((e) => (e.status === 'accepted' || e.status === 'started') && nowMs - Date.parse(e.startedAt ?? e.acceptedAt) > target.graceMs) || terminal.some((e) => !e.callbackAt && nowMs - Date.parse(e.completedAt ?? e.acceptedAt) > target.graceMs);
      const state = !target.enabled ? 'unknown' : missingSchedule || failures >= 2 ? 'critical' : staleCallback || failures ? 'warning' : 'healthy';
      const record: HealthRecord = { orgId, instanceId: target.instanceId, state, missingSchedule, staleCallback, consecutiveFailures: failures, successRate: terminal.length ? success.length / terminal.length : 0, observedAt: this.clock().toISOString(), failureClasses: [...new Set(terminal.map((e) => e.failureClass).filter((v): v is string => Boolean(v)))] };
      await this.store.writeHealth(record); const routingKey = missingSchedule ? 'missing-schedule' : staleCallback ? 'stale-callback' : failures ? 'execution-failure' : 'health';
      if (state === 'critical' || state === 'warning') { const opened = await this.store.openAlertIncident({ orgId, instanceId: target.instanceId, routingKey, severity: state, evidenceRef: `evidence://monitor/${digest(record).slice(7)}`, repeatAfter: new Date(nowMs + 3600000).toISOString() }); if (opened.deliver) await this.alerts.deliver({ alertId: opened.alertId, orgId, routingKey, severity: state, recovered: false }); }
      else { for (const key of ['missing-schedule', 'stale-callback', 'execution-failure']) { const recovered = await this.store.recoverAlertIncident({ orgId, instanceId: target.instanceId, routingKey: key, evidenceRef: `evidence://monitor/${digest(record).slice(7)}` }); if (recovered?.deliver) await this.alerts.deliver({ alertId: recovered.alertId, orgId, routingKey: key, severity: 'info', recovered: true }); } }
      results.push(record);
    }
    return results;
  }
  health(orgId: string) { return this.store.listHealth(orgId); }
  maintenance(orgId: string) { return this.store.runMaintenance(orgId); }
  transitionIncident(orgId: string, incidentId: string, status: string, actor: string, evidenceRef?: string) { return this.store.transitionIncident({ orgId, incidentId, status, actor, evidenceRef }); }
  async executeAction(request: ActionRequest) {
    const id = randomUUID(); const before = { instanceId: request.instanceId }; let result = 'rejected'; let after: Record<string, unknown> = {}; let error: string | undefined; const authority = await this.store.authorizeAction(request.orgId, request.instanceId, request.kind, request.evidenceRef);
    const allowed = authority.allowed && (request.kind !== 'fail_over' || authority.supportsFailover);
    if (allowed) { try { const operation = request.kind === 'pause_instance' ? this.executor.pause : request.kind === 'rollback_certified' ? this.executor.rollback : request.kind === 'fail_over' ? this.executor.failover : this.executor.retry; after = await operation.call(this.executor, request.orgId, request.instanceId, authority); result = 'succeeded'; } catch (cause) { result = 'failed'; error = cause instanceof Error ? cause.message : 'executor failed'; } }
    await this.store.recordAction({ id, ...request, before, after, result, error, compensatingAction: request.kind === 'pause_instance' ? 'release instance pause' : request.kind === 'rollback_certified' ? 're-promote only after a new approval' : 'none' }); return { id, result, error };
  }
  async deployment(request: DeploymentRequest) {
    const prepared = await this.store.prepareDeployment(request); if (prepared.disposition === 'replay') return prepared.committedRecord; if (prepared.disposition === 'in_progress') throw new Error('deployment transition is already in progress'); const authority = prepared.authority; const evidenceReady = authority.compatibleBindings && authority.baselineCertified && Boolean(authority.approvalRef) && Boolean(authority.healthEvidenceRef); const sampleReady = authority.sampleCount >= authority.minimumSamples && authority.elapsedMs >= authority.minimumWindowMs;
    if (request.action === 'promote' && (!evidenceReady || !authority.candidateCertified || !sampleReady || authority.candidateSuccessRate < authority.baselineSuccessRate)) { await this.store.failDeployment(request.orgId, prepared.transitionId, 'promotion evidence or approval is insufficient', false); throw new Error('promotion evidence or approval is insufficient'); }
    if (request.action === 'rollback' && !authority.baselineCertified) { await this.store.failDeployment(request.orgId, prepared.transitionId, 'rollback baseline is not certified', false); throw new Error('rollback baseline is not certified'); }
    try { await this.deployments.apply(request.action, authority); } catch (cause) { const error = cause instanceof Error ? cause.message : 'deployment action failed'; await this.store.failDeployment(request.orgId, prepared.transitionId, error, false); throw new Error(error); }
    const record = { id: randomUUID(), transitionId: prepared.transitionId, ...request, ...authority, result: 'succeeded', authorisedApprovalRef: authority.approvalRef, healthyEvidenceRef: authority.healthEvidenceRef, evidenceDigest: digest({ request, authority }), recordedAt: this.clock().toISOString() };
    try { await this.store.commitDeployment(request.orgId, prepared.transitionId, record); return record; } catch (cause) { const commitError = cause instanceof Error ? cause.message : 'deployment commit failed'; try { await this.deployments.compensate(request.action, authority); await this.store.failDeployment(request.orgId, prepared.transitionId, commitError, false); } catch (compensation) { const compensationError = compensation instanceof Error ? compensation.message : 'compensation failed'; await this.store.failDeployment(request.orgId, prepared.transitionId, `${commitError}; compensation: ${compensationError}`, true); } throw new Error(commitError); }
  }
  pause(args: { orgId: string; scope: string; automationId?: string; instanceId?: string; active: boolean; actor: string; reason: string; evidenceRef: string }) { if (args.scope === 'organisation' && !args.orgId) throw new Error('organisation scope must be bound'); return this.store.writePause(args); }
  async deliverRetry(orgId: string) { const item = await this.store.claimRetry(orgId); if (!item) return { delivered: false, empty: true }; if (item.orgId !== orgId) throw new Error('retry outbox returned cross-organisation work'); try { await this.retryDispatcher.dispatch(item); await this.store.completeRetry(orgId, item.id, true); return { delivered: true, id: item.id }; } catch (cause) { const error = cause instanceof Error ? cause.message : 'retry delivery failed'; await this.store.completeRetry(orgId, item.id, false, error); return { delivered: false, id: item.id, error }; } }
}
