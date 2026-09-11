import { describe, expect, it } from 'vitest';
import { JetStreamOperations, type JetStreamAlertStore } from '../../src/services/monitoring/jetstream-operations.js';
import type { AlertDelivery } from '../../src/services/monitoring/operations-service.js';
import type { JetStreamClusterSnapshot } from '../../../../packages/automation-operations/src/index.js';

const orgA = '00000000-0000-0000-0000-000000000001';
const orgB = '00000000-0000-0000-0000-000000000002';

class FakeJetStreamStore implements JetStreamAlertStore {
  alerts = new Map<string, { alertId: string; incidentId: string; open: boolean }>();
  deliveries: AlertDelivery[] = [];
  async openAlertIncident(args: { orgId: string; instanceId: string; routingKey: string }) {
    const key = `${args.orgId}:${args.instanceId}:${args.routingKey}`;
    const prior = this.alerts.get(key);
    if (prior?.open) return { ...prior, deliver: false };
    const value = { alertId: `js-alert-${this.alerts.size + 1}`, incidentId: `js-incident-${this.alerts.size + 1}`, open: true };
    this.alerts.set(key, value);
    return { ...value, deliver: true };
  }
  async recoverAlertIncident(args: { orgId: string; instanceId: string; routingKey: string }) {
    const key = `${args.orgId}:${args.instanceId}:${args.routingKey}`;
    const value = this.alerts.get(key);
    if (!value?.open) return undefined;
    value.open = false;
    return { alertId: value.alertId, deliver: true };
  }
}

const healthy = (): JetStreamClusterSnapshot => ({
  orgId: orgA,
  observedAt: '2026-09-11T00:02:00.000Z',
  connected: true,
  streams: [{ name: 'linkautowork-v1', available: true, replicaHealthy: true, lastSeq: 10, consumerCount: 1, subjects: ['linkautowork.v1.workflow.execution'] }],
  consumers: [{ stream: 'linkautowork-v1', consumer: 'gateway-executions', lastStreamSeq: 10, deliveredStreamSeq: 10, numPending: 0, numAckPending: 0, lastActivityAt: '2026-09-11T00:01:50.000Z' }],
});

describe('AW-06 gateway JetStream operations', () => {
  it('rejects a cross-organisation snapshot and does not open alerts', async () => {
    const store = new FakeJetStreamStore();
    const service = new JetStreamOperations(store, { deliver: async (alert) => { store.deliveries.push(alert); } }, () => new Date('2026-09-11T00:02:00Z'));
    await expect(service.observe(orgA, { ...healthy(), orgId: orgB })).rejects.toThrow(/cross-organisation/);
    expect(store.alerts.size).toBe(0);
  });

  it('opens one lag incident, deduplicates across restarts, then recovers from a healthy snapshot', async () => {
    const store = new FakeJetStreamStore();
    const service = new JetStreamOperations(store, { deliver: async (alert) => { store.deliveries.push(alert); } }, () => new Date('2026-09-11T00:02:00Z'));
    const lagging: JetStreamClusterSnapshot = {
      ...healthy(),
      consumers: [{ stream: 'linkautowork-v1', consumer: 'gateway-executions', lastStreamSeq: 5000, deliveredStreamSeq: 1, numPending: 4999, numAckPending: 0, lastActivityAt: '2026-09-11T00:01:50.000Z' }],
    };
    const first = await service.observe(orgA, lagging);
    const second = await new JetStreamOperations(store, { deliver: async (alert) => { store.deliveries.push(alert); } }, () => new Date('2026-09-11T00:02:01Z')).observe(orgA, lagging);
    expect(first.plan).toMatchObject({ kind: 'replay_from_ack_floor', executed: false });
    expect(second.health.health).toBe('unhealthy');
    expect(store.deliveries.filter((item) => !item.recovered)).toHaveLength(1);
    const recovered = await service.observe(orgA, healthy());
    expect(recovered.health.health).toBe('healthy');
    expect(recovered.plan.kind).toBe('observe');
    expect(store.deliveries.filter((item) => item.recovered).map((item) => item.routingKey)).toContain('jetstream-lag-critical');
  });

  it('fail-closes on a disconnected snapshot from a fake source without contacting NATS', async () => {
    const store = new FakeJetStreamStore();
    const service = new JetStreamOperations(store, { deliver: async (alert) => { store.deliveries.push(alert); } }, () => new Date('2026-09-11T00:02:00Z'));
    const observation = await service.observeFromSource({
      async read(orgId) { return { ...healthy(), orgId, connected: false }; },
    }, orgA);
    expect(observation.plan.kind).toBe('fail_closed');
    expect(observation.plan.executed).toBe(false);
    expect(store.deliveries[0]).toMatchObject({ routingKey: 'jetstream-unavailable', recovered: false, severity: 'critical' });
  });
});
