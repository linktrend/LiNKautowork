import { createHash, randomUUID } from 'node:crypto';

export type Severity = 'info' | 'warning' | 'critical';
export type FailureClass = 'platform' | 'automation_version' | 'instance_configuration' | 'credential' | 'dependency' | 'unknown';
export type IncidentStatus = 'open' | 'acknowledged' | 'investigating' | 'mitigated' | 'resolved' | 'closed';
export type PauseScope = 'global' | 'automation' | 'organisation' | 'instance';
export type RemediationKind = 'retry' | 'pause_instance' | 'fail_over' | 'rollback_certified';

export type ExecutionSignal = { orgId: string; automationId: string; instanceId: string; executionId: string; status: 'succeeded' | 'failed' | 'timed_out'; occurredAt: string; startedAt?: string; acceptedAt?: string; retryCount: number; failureHint?: string; callbackAt?: string };
export type SchedulePolicy = { orgId: string; automationId: string; instanceId: string; cadenceMs: number; graceMs: number; lastExpectedAt: string; lastSuccessfulCompletionAt?: string; enabled: boolean };
export type HealthSummary = { orgId: string; instanceId: string; health: 'healthy' | 'degraded' | 'unhealthy' | 'unknown'; successRate: number; consecutiveFailures: number; averageDurationMs: number; averageRetryCount: number; averageQueueDelayMs: number; averageCallbackDelayMs: number; lastSuccessfulCompletionAt?: string; missingSchedule: boolean; staleCallback: boolean; failures: FailureClass[] };
export type Alert = { id: string; dedupeKey: string; orgId: string; severity: Severity; routingKey: string; status: 'open' | 'acknowledged' | 'recovered'; incidentId: string; firstSeenAt: string; lastSentAt: string; repeatIntervalMs: number };
export type IncidentEvent = { at: string; actor: string; action: string; evidenceRefs: string[]; detail?: string };
export type Incident = { id: string; orgId: string; status: IncidentStatus; affectedInstanceIds: string[]; executionIds: string[]; deploymentId?: string; releaseId?: string; alertIds: string[]; history: IncidentEvent[] };
export type OperationAction = { id: string; actor: string; kind: RemediationKind; reason: string; evidenceRefs: string[]; before: Record<string, unknown>; after: Record<string, unknown>; result: 'succeeded' | 'rejected' | 'failed'; compensatingAction?: string };
export type Canary = { id: string; orgId: string; instanceIds: string[]; candidateReleaseId: string; baselineReleaseId: string; minimumSamples: number; minimumWindowMs: number; startedAt: string; candidateSuccessRate: number; baselineSuccessRate: number; status: 'canary' | 'passed' | 'rejected' | 'rolled_back' };
export type DeploymentRecord = { id: string; deploymentId: string; at: string; state: 'canary' | 'promoted' | 'rolled_back'; candidateReleaseId: string; baselineReleaseId: string; immutableEvidenceDigest: string; actor: string; reason: string };
export type Probe = { name: string; safe: true; minIntervalMs: number; run(): Promise<{ ok: boolean; evidenceRef?: string }> };
export type MaintenanceInput = { versionDrift: boolean; disabledWorkflow: boolean; staleCallback: boolean; credentialState: 'unknown' | 'healthy' | 'expiring' | 'invalid' | 'revoked'; dependenciesTested: boolean; storagePressure: boolean; queuePressure: boolean; backupFresh: boolean; unresolvedIncidentCount: number };
export type MaintenanceFinding = { code: string; severity: Severity; detail: string };

const sha = (value: unknown) => `sha256:${createHash('sha256').update(JSON.stringify(value)).digest('hex')}`;
const now = () => new Date().toISOString();

/** Classifies only redacted failure hints; unrecognised failures remain explicitly unknown. */
export function classifyFailure(hint?: string): FailureClass {
  const value = (hint ?? '').toLowerCase();
  if (/timeout|queue|n8n|gateway|network/.test(value)) return 'platform';
  if (/digest|version|release/.test(value)) return 'automation_version';
  if (/binding|configuration|disabled/.test(value)) return 'instance_configuration';
  if (/credential|secret|auth/.test(value)) return 'credential';
  if (/dependency|upstream|provider/.test(value)) return 'dependency';
  return 'unknown';
}

/** Derives job health from executions and declared schedule policy; process liveness is deliberately not an input. */
export function deriveHealth(policy: SchedulePolicy, signals: ExecutionSignal[], at = Date.now()): HealthSummary {
  const relevant = signals.filter((signal) => signal.instanceId === policy.instanceId).sort((a, b) => a.occurredAt.localeCompare(b.occurredAt));
  const completed = relevant.filter((signal) => signal.status === 'succeeded' || signal.status === 'failed' || signal.status === 'timed_out');
  const successes = completed.filter((signal) => signal.status === 'succeeded');
  let consecutiveFailures = 0;
  for (const signal of [...completed].reverse()) { if (signal.status === 'succeeded') break; consecutiveFailures += 1; }
  const duration = completed.map((signal) => signal.startedAt ? Date.parse(signal.occurredAt) - Date.parse(signal.startedAt) : 0).filter(Boolean);
  const queue = completed.map((signal) => signal.startedAt && signal.acceptedAt ? Date.parse(signal.startedAt) - Date.parse(signal.acceptedAt) : 0).filter(Boolean);
  const callbacks = completed.map((signal) => signal.callbackAt ? Date.parse(signal.callbackAt) - Date.parse(signal.occurredAt) : 0).filter(Boolean);
  const avg = (items: number[]) => items.length ? items.reduce((a, b) => a + b, 0) / items.length : 0;
  const scheduledDue = Date.parse(policy.lastExpectedAt) + policy.cadenceMs + policy.graceMs < at;
  const lastSuccess = successes.at(-1)?.occurredAt ?? policy.lastSuccessfulCompletionAt;
  const missingSchedule = policy.enabled && scheduledDue && (!lastSuccess || Date.parse(lastSuccess) < Date.parse(policy.lastExpectedAt));
  const staleCallback = completed.some((signal) => !signal.callbackAt && at - Date.parse(signal.occurredAt) > policy.graceMs);
  const failures = [...new Set(completed.filter((signal) => signal.status !== 'succeeded').map((signal) => classifyFailure(signal.failureHint)))];
  const health = !policy.enabled ? 'unknown' : (missingSchedule || consecutiveFailures >= 2 ? 'unhealthy' : (staleCallback || failures.length ? 'degraded' : 'healthy'));
  return { orgId: policy.orgId, instanceId: policy.instanceId, health, successRate: completed.length ? successes.length / completed.length : 0, consecutiveFailures, averageDurationMs: avg(duration), averageRetryCount: avg(completed.map((signal) => signal.retryCount)), averageQueueDelayMs: avg(queue), averageCallbackDelayMs: avg(callbacks), lastSuccessfulCompletionAt: lastSuccess, missingSchedule, staleCallback, failures };
}

/** Evaluates maintenance signals only; no provider, credential, queue, or storage mutation occurs here. */
export function checkMaintenance(input: MaintenanceInput): MaintenanceFinding[] {
  const findings: MaintenanceFinding[] = [];
  const add = (when: boolean, code: string, severity: Severity, detail: string) => { if (when) findings.push({ code, severity, detail }); };
  add(input.versionDrift, 'version_drift', 'warning', 'deployed workflow differs from its certified release');
  add(input.disabledWorkflow, 'disabled_workflow', 'critical', 'bound workflow is disabled');
  add(input.staleCallback, 'stale_callback', 'warning', 'execution callback is outside declared grace');
  add(['expiring', 'invalid', 'revoked'].includes(input.credentialState), `credential_${input.credentialState}`, input.credentialState === 'expiring' ? 'warning' : 'critical', 'credential reference requires operator attention');
  add(!input.dependenciesTested, 'untested_dependency', 'warning', 'safe dependency probe has not produced current evidence');
  add(input.storagePressure, 'storage_pressure', 'warning', 'storage pressure signal requires review'); add(input.queuePressure, 'queue_pressure', 'warning', 'queue pressure signal requires review');
  add(!input.backupFresh, 'backup_stale', 'critical', 'backup freshness is not evidenced'); add(input.unresolvedIncidentCount > 0, 'unresolved_incidents', 'warning', `${input.unresolvedIncidentCount} incident(s) remain unresolved`);
  return findings;
}

/** Organisation views intentionally exclude payloads and secret references; operator view aggregates only those redacted summaries. */
export function healthView(summaries: HealthSummary[], orgId?: string): HealthSummary[] { return orgId ? summaries.filter((summary) => summary.orgId === orgId) : summaries; }

/** Local adapter boundary: callers can prove routing without selecting real recipients. */
export interface AlertAdapter { deliver(alert: Alert): Promise<void>; }

/** Append-only incident and alert ledger. Production persistence belongs behind this identical interface. */
export class OperationsLedger {
  readonly alerts = new Map<string, Alert>(); readonly incidents = new Map<string, Incident>(); readonly actions: OperationAction[] = []; readonly deployments: DeploymentRecord[] = [];
  constructor(private readonly adapter: AlertAdapter) {}
  async alert(args: { orgId: string; instanceId: string; severity: Severity; routingKey: string; reason: string; repeatIntervalMs: number; at?: string }): Promise<Alert> {
    const at = args.at ?? now(); const dedupeKey = `${args.orgId}:${args.instanceId}:${args.routingKey}`;
    let alert = [...this.alerts.values()].find((candidate) => candidate.dedupeKey === dedupeKey && candidate.status !== 'recovered');
    if (!alert) { const incidentId = randomUUID(); alert = { id: randomUUID(), dedupeKey, orgId: args.orgId, severity: args.severity, routingKey: args.routingKey, status: 'open', incidentId, firstSeenAt: at, lastSentAt: at, repeatIntervalMs: args.repeatIntervalMs }; this.alerts.set(alert.id, alert); this.incidents.set(incidentId, { id: incidentId, orgId: args.orgId, status: 'open', affectedInstanceIds: [args.instanceId], executionIds: [], alertIds: [alert.id], history: [{ at, actor: 'monitor', action: 'opened', evidenceRefs: [], detail: args.reason }] }); await this.adapter.deliver(alert); return alert; }
    if (Date.parse(at) - Date.parse(alert.lastSentAt) >= alert.repeatIntervalMs) { alert = { ...alert, lastSentAt: at }; this.alerts.set(alert.id, alert); await this.adapter.deliver(alert); }
    return alert;
  }
  transition(incidentId: string, status: IncidentStatus, actor: string, action: string, evidenceRefs: string[] = []): Incident { const incident = this.mustIncident(incidentId); const order: IncidentStatus[] = ['open', 'acknowledged', 'investigating', 'mitigated', 'resolved', 'closed']; if (order.indexOf(status) < order.indexOf(incident.status)) throw new Error('incident lifecycle is append-only and cannot move backward'); const next = { ...incident, status, history: [...incident.history, { at: now(), actor, action, evidenceRefs }] }; this.incidents.set(incidentId, next); return next; }
  recover(alertId: string, actor = 'monitor'): Alert { const alert = this.alerts.get(alertId); if (!alert) throw new Error('alert not found'); const recovered = { ...alert, status: 'recovered' as const, lastSentAt: now() }; this.alerts.set(alertId, recovered); const incident = this.mustIncident(alert.incidentId); this.incidents.set(incident.id, { ...incident, history: [...incident.history, { at: recovered.lastSentAt, actor, action: 'recovery_notified', evidenceRefs: [] }] }); return recovered; }
  recordAction(action: OperationAction): void { this.actions.push(Object.freeze({ ...action, evidenceRefs: [...action.evidenceRefs], before: { ...action.before }, after: { ...action.after } })); }
  recordDeployment(record: Omit<DeploymentRecord, 'id' | 'immutableEvidenceDigest'>): DeploymentRecord { const immutableEvidenceDigest = sha(record); const stored = Object.freeze({ ...record, id: randomUUID(), immutableEvidenceDigest }); this.deployments.push(stored); return stored; }
  private mustIncident(id: string): Incident { const incident = this.incidents.get(id); if (!incident) throw new Error('incident not found'); return incident; }
}

/** Executes safe, rate-limited probes; failed probes are evidence, never an automatic business action. */
export class ProbeRunner { private readonly lastRun = new Map<string, number>(); async run(probe: Probe, at = Date.now()) { const last = this.lastRun.get(probe.name); if (last !== undefined && at - last < probe.minIntervalMs) return { skipped: true as const }; this.lastRun.set(probe.name, at); return { skipped: false as const, ...(await probe.run()) }; } }

/** Enforces the packet's bounded remediation allow-list and an explicit capability for each action. */
export function remediate(kind: RemediationKind, allowed: readonly RemediationKind[], input: { actor: string; reason: string; evidenceRefs: string[]; before: Record<string, unknown>; after: Record<string, unknown>; supportsFailover?: boolean }): OperationAction {
  let result: OperationAction['result'] = 'succeeded'; let compensatingAction: string | undefined;
  if (!allowed.includes(kind) || (kind === 'fail_over' && !input.supportsFailover)) result = 'rejected';
  if (kind === 'retry') compensatingAction = 'none: retry is bounded by instance policy'; if (kind === 'pause_instance') compensatingAction = 'release instance pause'; if (kind === 'rollback_certified') compensatingAction = 're-promote only after certification and approval';
  return { id: randomUUID(), actor: input.actor, kind, reason: input.reason, evidenceRefs: input.evidenceRefs, before: input.before, after: input.after, result, compensatingAction };
}

/** Pause resolution is deterministic: global, automation, organisation, then instance. */
export function effectivePause(pauses: Array<{ scope: PauseScope; orgId?: string; automationId?: string; instanceId?: string; reason: string }>, subject: { orgId: string; automationId: string; instanceId: string }) { const match = (scope: PauseScope) => pauses.find((pause) => pause.scope === scope && (scope === 'global' || scope === 'organisation' && pause.orgId === subject.orgId || scope === 'automation' && pause.automationId === subject.automationId || scope === 'instance' && pause.instanceId === subject.instanceId)); return match('global') ?? match('automation') ?? match('organisation') ?? match('instance'); }

/** Canary promotion compares candidate to certified baseline and never promotes without required evidence and authorisation. */
export function assessCanary(canary: Canary, args: { samples: number; elapsedMs: number; compatibleBindings: boolean; baselineCertified: boolean; authorised: boolean; minimumSuccessRate?: number }): 'promote' | 'hold' | 'rollback' { if (args.samples < canary.minimumSamples || args.elapsedMs < canary.minimumWindowMs || !args.compatibleBindings || !args.baselineCertified || !args.authorised) return 'hold'; const threshold = args.minimumSuccessRate ?? canary.baselineSuccessRate; return canary.candidateSuccessRate >= threshold ? 'promote' : 'rollback'; }

export type BackupArtifact = { kind: 'control_records' | 'catalogue_receipts' | 'workflow_configuration'; content: unknown; digest: string };
/** Disposable only: verifies hashes and reconstructs local copies; it neither reads nor writes a live backup target. */
export function rehearseRestore(artifacts: BackupArtifact[]) { if (artifacts.length !== 3) throw new Error('all three backup artifact kinds are required'); const restored = artifacts.map((artifact) => ({ ...artifact, valid: artifact.digest === sha(artifact.content) })); if (!restored.every((artifact) => artifact.valid)) throw new Error('backup integrity check failed'); return { restoredAt: now(), artifacts: restored.map(({ content, ...safe }) => safe) }; }
