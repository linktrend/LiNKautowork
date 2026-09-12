import { createHash } from 'node:crypto';
import {
  JETSTREAM_ROUTING_KEYS,
  deriveJetStreamHealth,
  jetStreamAlertKeys,
  planJetStreamRecovery,
  type JetStreamClusterSnapshot,
  type JetStreamHealthSummary,
  type JetStreamRecoveryPlan,
} from '../../../../packages/automation-operations/src/index.js';
import type { AlertAdapter } from './operations-service.js';

/** Read-only snapshot source. Tests inject fakes; this module never opens NATS. */
export interface JetStreamSnapshotSource {
  read(orgId: string): Promise<JetStreamClusterSnapshot>;
}

/** Durable alert/incident writer used by JetStream observation. */
export interface JetStreamAlertStore {
  openAlertIncident(args: { orgId: string; instanceId: string; routingKey: string; severity: string; evidenceRef: string; repeatAfter: string }): Promise<{ alertId: string; incidentId: string; deliver: boolean }>;
  recoverAlertIncident(args: { orgId: string; instanceId: string; routingKey: string; evidenceRef: string }): Promise<{ alertId: string; deliver: boolean } | undefined>;
}

/** Observation result that includes a non-executed recovery plan. */
export type JetStreamObservation = {
  health: JetStreamHealthSummary;
  plan: JetStreamRecoveryPlan;
};

const digest = (value: unknown) => `sha256:${createHash('sha256').update(JSON.stringify(value)).digest('hex')}`;

/**
 * Snapshot-only JetStream observer. It records alerts and returns recovery plans without
 * recreating consumers, replaying messages, or touching backups, n8n, or credentials.
 */
export class JetStreamOperations {
  constructor(
    private readonly store: JetStreamAlertStore,
    private readonly alerts: AlertAdapter,
    private readonly clock = () => new Date(),
  ) {}

  /**
   * Observes an already-captured snapshot. Cross-organisation snapshots fail closed.
   */
  async observe(orgId: string, snapshot: JetStreamClusterSnapshot): Promise<JetStreamObservation> {
    if (snapshot.orgId !== orgId) throw new Error('jetstream snapshot returned a cross-organisation cluster');
    const now = this.clock();
    const health = deriveJetStreamHealth(snapshot);
    const evidenceRef = `evidence://jetstream/${digest(health).slice(7)}`;
    const open = jetStreamAlertKeys(health);
    const openSet = new Set(open.map((item) => `${item.instanceId}:${item.routingKey}`));
    for (const item of open) {
      const opened = await this.store.openAlertIncident({
        orgId,
        instanceId: item.instanceId,
        routingKey: item.routingKey,
        severity: item.severity,
        evidenceRef,
        repeatAfter: new Date(now.getTime() + 3_600_000).toISOString(),
      });
      if (opened.deliver) await this.alerts.deliver({ alertId: opened.alertId, orgId, routingKey: item.routingKey, severity: item.severity, recovered: false });
    }
    const instanceIds = new Set<string>([
      'jetstream:cluster',
      ...health.missingStreams.map((name) => `jetstream:stream:${name}`),
      ...health.replicaUnhealthy.map((name) => `jetstream:stream:${name}`),
      ...health.consumers.map((consumer) => `jetstream:${consumer.stream}:${consumer.consumer}`),
    ]);
    for (const instanceId of instanceIds) {
      for (const routingKey of JETSTREAM_ROUTING_KEYS) {
        if (openSet.has(`${instanceId}:${routingKey}`)) continue;
        const recovered = await this.store.recoverAlertIncident({ orgId, instanceId, routingKey, evidenceRef });
        if (recovered?.deliver) await this.alerts.deliver({ alertId: recovered.alertId, orgId, routingKey, severity: 'info', recovered: true });
      }
    }
    return { health, plan: planJetStreamRecovery(health) };
  }

  /**
   * Reads a snapshot from an injected source, then observes it.
   */
  async observeFromSource(source: JetStreamSnapshotSource, orgId: string): Promise<JetStreamObservation> {
    return this.observe(orgId, await source.read(orgId));
  }
}
