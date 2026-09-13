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

  it('degrades replica health without a zero-lag lag incident and plans replica observation', () => {
    const health = deriveJetStreamHealth(snapshot({
      streams: [{ name: 'linkautowork-v1', available: true, replicaHealthy: false, lastSeq: 40, consumerCount: 1, subjects: ['linkautowork.v1.workflow.execution'] }],
    }), at);
    expect(health).toMatchObject({ health: 'degraded', replicaUnhealthy: ['linkautowork-v1'] });
    expect(health.consumers[0]).toMatchObject({ lag: 0, health: 'healthy', routingKey: 'jetstream-health' });
    expect(jetStreamAlertKeys(health)).toEqual([{ routingKey: 'jetstream-replica', severity: 'warning', instanceId: 'jetstream:stream:linkautowork-v1' }]);
    const plan = planJetStreamRecovery(health);
    expect(plan).toMatchObject({ kind: 'observe', executed: false, safe: true });
    expect(plan.reason).toMatch(/replica/);
    expect(plan.reason).toMatch(/separate from consumer sequence health/);
    expect(plan.steps.join(' ')).not.toMatch(/lag alert/);
  });

  it('keeps replica and warning-lag alerts as separate routing keys', () => {
    const health = deriveJetStreamHealth(snapshot({
      streams: [{ name: 'linkautowork-v1', available: true, replicaHealthy: false, lastSeq: 40, consumerCount: 1, subjects: ['linkautowork.v1.workflow.execution'] }],
      consumers: [{ stream: 'linkautowork-v1', consumer: 'gateway-executions', lastStreamSeq: 40, deliveredStreamSeq: 40 - JETSTREAM_DEFAULTS.lagWarning, numPending: JETSTREAM_DEFAULTS.lagWarning, numAckPending: 0, lastActivityAt: '2026-09-11T00:01:50.000Z' }],
    }), at);
    expect(health.health).toBe('degraded');
    expect(jetStreamAlertKeys(health)).toEqual([
      { routingKey: 'jetstream-replica', severity: 'warning', instanceId: 'jetstream:stream:linkautowork-v1' },
      { routingKey: 'jetstream-lag', severity: 'warning', instanceId: 'jetstream:linkautowork-v1:gateway-executions' },
    ]);
  });

  it('opens an ack-pending warning without collapsing replica into the lag signal', () => {
    const health = deriveJetStreamHealth(snapshot({
      consumers: [{ stream: 'linkautowork-v1', consumer: 'gateway-executions', lastStreamSeq: 40, deliveredStreamSeq: 40, numPending: 0, numAckPending: JETSTREAM_DEFAULTS.ackPendingWarning, lastActivityAt: '2026-09-11T00:01:50.000Z' }],
    }), at);
    expect(health.health).toBe('degraded');
    expect(health.consumers[0]).toMatchObject({ lag: 0, numAckPending: JETSTREAM_DEFAULTS.ackPendingWarning, health: 'degraded', routingKey: 'jetstream-lag' });
    expect(jetStreamAlertKeys(health)).toEqual([{ routingKey: 'jetstream-lag', severity: 'warning', instanceId: 'jetstream:linkautowork-v1:gateway-executions' }]);
    expect(planJetStreamRecovery(health).kind).toBe('observe');
  });

  it('classifies a connected snapshot with no streams as unknown and does not invent lag or replica incidents', () => {
    const health = deriveJetStreamHealth(snapshot({ streams: [], consumers: [] }), at);
    expect(health).toMatchObject({ health: 'unknown', missingStreams: [], replicaUnhealthy: [], consumers: [] });
    expect(jetStreamAlertKeys(health)).toEqual([]);
    const plan = planJetStreamRecovery(health);
    expect(plan).toMatchObject({ kind: 'observe', executed: false });
    expect(plan.reason).toMatch(/no streams/);
  });

  it('judges consumer staleness from snapshot observedAt even when the caller clock is newer', () => {
    const later = Date.parse('2026-09-11T00:10:00.000Z');
    const health = deriveJetStreamHealth(snapshot(), later);
    expect(health.consumers[0]).toMatchObject({ stale: false, health: 'healthy' });
    const stale = deriveJetStreamHealth(snapshot({
      consumers: [{ stream: 'linkautowork-v1', consumer: 'gateway-executions', lastStreamSeq: 40, deliveredStreamSeq: 40, numPending: 0, numAckPending: 0, lastActivityAt: '2026-09-11T00:00:00.000Z' }],
    }), later);
    expect(stale.consumers[0]).toMatchObject({ stale: true, health: 'degraded', routingKey: 'jetstream-stale' });
  });
});
