/** Snapshot-only JetStream observability and recovery planning. Never connects to NATS. */

export type JetStreamHealth = 'healthy' | 'degraded' | 'unhealthy' | 'unknown';

/** Conservative source defaults; they are not production SLO claims. */
export const JETSTREAM_DEFAULTS = {
  lagWarning: 100,
  lagCritical: 1_000,
  ackPendingWarning: 50,
  ackPendingCritical: 500,
  staleMs: 60_000,
} as const;

/** Redacted stream observation. Subject names only; no payloads. */
export type JetStreamStreamSnapshot = {
  name: string;
  available: boolean;
  replicaHealthy: boolean;
  lastSeq: number;
  consumerCount: number;
  subjects: string[];
};

/** Redacted consumer observation. Sequence numbers only; no message bodies. */
export type JetStreamConsumerSnapshot = {
  stream: string;
  consumer: string;
  lastStreamSeq: number;
  deliveredStreamSeq: number;
  numPending: number;
  numAckPending: number;
  lastActivityAt?: string;
};

/** Organisation-bound cluster snapshot supplied by a fake or future adapter. */
export type JetStreamClusterSnapshot = {
  orgId: string;
  observedAt: string;
  connected: boolean;
  streams: JetStreamStreamSnapshot[];
  consumers: JetStreamConsumerSnapshot[];
};

/** Consumer lag and health derived from a snapshot. */
export type JetStreamConsumerHealth = {
  stream: string;
  consumer: string;
  lag: number;
  numPending: number;
  numAckPending: number;
  stale: boolean;
  health: JetStreamHealth;
  routingKey: string;
};

/** Cluster-level JetStream health with per-consumer rows. */
export type JetStreamHealthSummary = {
  orgId: string;
  observedAt: string;
  connected: boolean;
  health: JetStreamHealth;
  missingStreams: string[];
  replicaUnhealthy: string[];
  consumers: JetStreamConsumerHealth[];
};

/** Planned recovery only; callers must not treat this as an executed action. */
export type JetStreamRecoveryKind = 'observe' | 'recreate_consumer' | 'replay_from_ack_floor' | 'fail_closed';

/** Explicit non-execution recovery plan. */
export type JetStreamRecoveryPlan = {
  kind: JetStreamRecoveryKind;
  safe: true;
  executed: false;
  orgId: string;
  reason: string;
  steps: string[];
  compensatingAction: string;
};

/**
 * Computes consumer lag as last stream sequence minus delivered sequence.
 * Negative values are clamped to zero so a rewind snapshot cannot look healthy by accident.
 */
export function consumerLag(consumer: JetStreamConsumerSnapshot): number {
  return Math.max(0, consumer.lastStreamSeq - consumer.deliveredStreamSeq);
}

/**
 * Derives JetStream health from a redacted snapshot. Process liveness is not an input.
 */
export function deriveJetStreamHealth(snapshot: JetStreamClusterSnapshot, at = Date.parse(snapshot.observedAt), thresholds = JETSTREAM_DEFAULTS): JetStreamHealthSummary {
  const missingStreams = snapshot.streams.filter((stream) => !stream.available).map((stream) => stream.name);
  const replicaUnhealthy = snapshot.streams.filter((stream) => stream.available && !stream.replicaHealthy).map((stream) => stream.name);
  const consumers: JetStreamConsumerHealth[] = snapshot.consumers.map((consumer) => {
    const lag = consumerLag(consumer);
    const stale = !consumer.lastActivityAt || at - Date.parse(consumer.lastActivityAt) > thresholds.staleMs;
    let health: JetStreamHealth = 'healthy';
    if (!snapshot.connected || missingStreams.includes(consumer.stream)) health = 'unhealthy';
    else if (lag >= thresholds.lagCritical || consumer.numAckPending >= thresholds.ackPendingCritical) health = 'unhealthy';
    else if (stale || lag >= thresholds.lagWarning || consumer.numAckPending >= thresholds.ackPendingWarning || replicaUnhealthy.includes(consumer.stream)) health = 'degraded';
    const routingKey = !snapshot.connected || missingStreams.includes(consumer.stream)
      ? 'jetstream-unavailable'
      : health === 'unhealthy'
        ? 'jetstream-lag-critical'
        : health === 'degraded'
          ? (stale ? 'jetstream-stale' : 'jetstream-lag')
          : 'jetstream-health';
    return { stream: consumer.stream, consumer: consumer.consumer, lag, numPending: consumer.numPending, numAckPending: consumer.numAckPending, stale, health, routingKey };
  });
  let health: JetStreamHealth = 'healthy';
  if (!snapshot.connected || missingStreams.length) health = 'unhealthy';
  else if (!snapshot.streams.length) health = 'unknown';
  else if (replicaUnhealthy.length || consumers.some((row) => row.health === 'unhealthy')) health = 'unhealthy';
  else if (consumers.some((row) => row.health === 'degraded')) health = 'degraded';
  return { orgId: snapshot.orgId, observedAt: snapshot.observedAt, connected: snapshot.connected, health, missingStreams, replicaUnhealthy, consumers };
}

/**
 * Returns a non-executing recovery plan. Replay and consumer recreation are described, never performed.
 */
export function planJetStreamRecovery(summary: JetStreamHealthSummary): JetStreamRecoveryPlan {
  if (!summary.connected || summary.missingStreams.length) {
    return {
      kind: 'fail_closed',
      safe: true,
      executed: false,
      orgId: summary.orgId,
      reason: summary.connected ? `streams unavailable: ${summary.missingStreams.join(',')}` : 'jetstream disconnected',
      steps: [
        'do not publish new work onto unavailable streams',
        'retain the last redacted snapshot as incident evidence',
        'wait for an authorised operator to restore JetStream from a rehearsed backup',
      ],
      compensatingAction: 'resume publishing only after a healthy snapshot and incident recovery notification',
    };
  }
  const critical = summary.consumers.find((row) => row.health === 'unhealthy');
  if (critical) {
    return {
      kind: 'replay_from_ack_floor',
      safe: true,
      executed: false,
      orgId: summary.orgId,
      reason: `consumer ${critical.consumer} lag ${critical.lag} or ack-pending ${critical.numAckPending} exceeded critical threshold`,
      steps: [
        `plan a bounded replay of ${critical.stream}/${critical.consumer} from the stored ack floor`,
        'do not delete the stream or rewrite payloads',
        're-evaluate health from a fresh snapshot after an authorised replay',
      ],
      compensatingAction: 'leave the consumer at its ack floor if replay is not authorised',
    };
  }
  const degraded = summary.consumers.find((row) => row.health === 'degraded');
  if (degraded?.stale) {
    return {
      kind: 'recreate_consumer',
      safe: true,
      executed: false,
      orgId: summary.orgId,
      reason: `consumer ${degraded.consumer} is stale without a critical lag breach`,
      steps: [
        'record the last delivered sequence',
        'plan durable consumer recreate with the same durable name and ack policy',
        'do not reset the stream sequence',
      ],
      compensatingAction: 'keep the existing durable consumer if recreate is not authorised',
    };
  }
  if (degraded) {
    return {
      kind: 'observe',
      safe: true,
      executed: false,
      orgId: summary.orgId,
      reason: `consumer ${degraded.consumer} is degraded; continue observation`,
      steps: ['repeat snapshot observation at the maintenance interval', 'open or refresh a lag alert if thresholds still breach'],
      compensatingAction: 'none: observation does not mutate JetStream',
    };
  }
  return {
    kind: 'observe',
    safe: true,
    executed: false,
    orgId: summary.orgId,
    reason: 'cluster snapshot is healthy',
    steps: ['continue scheduled snapshot observation'],
    compensatingAction: 'none',
  };
}

/** Alert routing keys that monitoring should open or recover for a summary. */
export function jetStreamAlertKeys(summary: JetStreamHealthSummary): Array<{ routingKey: string; severity: 'warning' | 'critical'; instanceId: string }> {
  if (!summary.connected) return [{ routingKey: 'jetstream-unavailable', severity: 'critical', instanceId: 'jetstream:cluster' }];
  const keys: Array<{ routingKey: string; severity: 'warning' | 'critical'; instanceId: string }> = [];
  for (const name of summary.missingStreams) keys.push({ routingKey: 'jetstream-unavailable', severity: 'critical', instanceId: `jetstream:stream:${name}` });
  for (const name of summary.replicaUnhealthy) keys.push({ routingKey: 'jetstream-replica', severity: 'warning', instanceId: `jetstream:stream:${name}` });
  for (const consumer of summary.consumers) {
    if (consumer.health === 'healthy') continue;
    keys.push({
      routingKey: consumer.routingKey,
      severity: consumer.health === 'unhealthy' ? 'critical' : 'warning',
      instanceId: `jetstream:${consumer.stream}:${consumer.consumer}`,
    });
  }
  return keys;
}

/** Routing keys this observer owns so recovery can close them without touching unrelated incidents. */
export const JETSTREAM_ROUTING_KEYS = ['jetstream-unavailable', 'jetstream-replica', 'jetstream-lag', 'jetstream-lag-critical', 'jetstream-stale', 'jetstream-health'] as const;
