import { describe, expect, it } from 'vitest';
import {
  JETSTREAM_DEFAULTS,
  checkMaintenance,
  consumerLag,
  deriveJetStreamHealth,
  jetStreamAlertKeys,
  planJetStreamRecovery,
  type JetStreamClusterSnapshot,
} from '../src/index.js';

const orgId = '00000000-0000-0000-0000-000000000001';
const observedAt = '2026-09-11T00:02:00.000Z';
const at = Date.parse(observedAt);

function snapshot(overrides: Partial<JetStreamClusterSnapshot> = {}): JetStreamClusterSnapshot {
  return {
    orgId,
    observedAt,
    connected: true,
    streams: [{ name: 'linkautowork-v1', available: true, replicaHealthy: true, lastSeq: 40, consumerCount: 1, subjects: ['linkautowork.v1.workflow.execution'] }],
    consumers: [{ stream: 'linkautowork-v1', consumer: 'gateway-executions', lastStreamSeq: 40, deliveredStreamSeq: 40, numPending: 0, numAckPending: 0, lastActivityAt: '2026-09-11T00:01:50.000Z' }],
    ...overrides,
  };
}

describe('AW-06 JetStream observability and recovery plans', () => {
  it('treats a current connected snapshot as healthy and plans observation only', () => {
    const health = deriveJetStreamHealth(snapshot(), at);
    expect(health).toMatchObject({ health: 'healthy', connected: true, missingStreams: [] });
    expect(health.consumers[0]).toMatchObject({ lag: 0, health: 'healthy' });
    const plan = planJetStreamRecovery(health);
    expect(plan).toMatchObject({ kind: 'observe', executed: false, safe: true });
    expect(jetStreamAlertKeys(health)).toEqual([]);
  });

  it('clamps negative lag and opens a warning alert for warning-threshold lag', () => {
    expect(consumerLag({ stream: 's', consumer: 'c', lastStreamSeq: 10, deliveredStreamSeq: 12, numPending: 0, numAckPending: 0 })).toBe(0);
    const health = deriveJetStreamHealth(snapshot({
      consumers: [{ stream: 'linkautowork-v1', consumer: 'gateway-executions', lastStreamSeq: 40, deliveredStreamSeq: 40 - JETSTREAM_DEFAULTS.lagWarning, numPending: JETSTREAM_DEFAULTS.lagWarning, numAckPending: 0, lastActivityAt: '2026-09-11T00:01:50.000Z' }],
    }), at);
    expect(health.health).toBe('degraded');
    expect(health.consumers[0]?.lag).toBe(JETSTREAM_DEFAULTS.lagWarning);
    expect(jetStreamAlertKeys(health)).toEqual([{ routingKey: 'jetstream-lag', severity: 'warning', instanceId: 'jetstream:linkautowork-v1:gateway-executions' }]);
    expect(planJetStreamRecovery(health).kind).toBe('observe');
  });

  it('plans a non-executing replay when lag is critical and never mutates the snapshot', () => {
    const input = snapshot({
      consumers: [{ stream: 'linkautowork-v1', consumer: 'gateway-executions', lastStreamSeq: 5000, deliveredStreamSeq: 1, numPending: 4999, numAckPending: 0, lastActivityAt: '2026-09-11T00:01:50.000Z' }],
    });
    const health = deriveJetStreamHealth(input, at);
    expect(health.health).toBe('unhealthy');
    const plan = planJetStreamRecovery(health);
    expect(plan).toMatchObject({ kind: 'replay_from_ack_floor', executed: false, safe: true });
    expect(input.consumers[0]?.deliveredStreamSeq).toBe(1);
    expect(jetStreamAlertKeys(health)[0]).toMatchObject({ routingKey: 'jetstream-lag-critical', severity: 'critical' });
  });

  it('fail-closes when disconnected or a required stream is missing', () => {
    const disconnected = deriveJetStreamHealth(snapshot({ connected: false }), at);
    expect(disconnected.health).toBe('unhealthy');
    expect(planJetStreamRecovery(disconnected).kind).toBe('fail_closed');
    expect(jetStreamAlertKeys(disconnected)).toEqual([{ routingKey: 'jetstream-unavailable', severity: 'critical', instanceId: 'jetstream:cluster' }]);
    const missing = deriveJetStreamHealth(snapshot({
      streams: [{ name: 'linkautowork-v1', available: false, replicaHealthy: false, lastSeq: 0, consumerCount: 0, subjects: ['linkautowork.v1.workflow.execution'] }],
    }), at);
    expect(missing.missingStreams).toEqual(['linkautowork-v1']);
    expect(planJetStreamRecovery(missing).kind).toBe('fail_closed');
  });

  it('plans durable consumer recreate for stale consumers and records jetstream maintenance findings', () => {
    const health = deriveJetStreamHealth(snapshot({
      consumers: [{ stream: 'linkautowork-v1', consumer: 'gateway-executions', lastStreamSeq: 40, deliveredStreamSeq: 40, numPending: 0, numAckPending: 0, lastActivityAt: '2026-09-11T00:00:00.000Z' }],
    }), at);
    expect(health.consumers[0]).toMatchObject({ stale: true, health: 'degraded' });
    expect(planJetStreamRecovery(health).kind).toBe('recreate_consumer');
    expect(planJetStreamRecovery(health).executed).toBe(false);
    const findings = checkMaintenance({ versionDrift: false, disabledWorkflow: false, staleCallback: false, credentialState: 'healthy', dependenciesTested: true, storagePressure: false, queuePressure: false, backupFresh: true, unresolvedIncidentCount: 0, jetStreamLag: true, jetStreamUnavailable: true });
    expect(findings.map((finding) => finding.code)).toEqual(['jetstream_lag', 'jetstream_unavailable']);
  });
});
