import { describe, expect, it } from 'vitest';
import { ExecutionService, type ExecutionCallbackCapability, type ExecutionEventStore, type ExecutionProjection, type ExecutionRecordResult } from '../src/services/executions/execution-service.js';
import { executionCallbackSchema, type ExecutionCallback } from '../src/contracts/execution-callback.js';

const orgId = '00000000-0000-0000-0000-000000000001';
const otherOrg = '00000000-0000-0000-0000-000000000002';
const executionId = '60000000-0000-0000-0000-000000000001';
const capability = { service: 'linkautowork-n8n', token: 'bound-callback-token' };
const event = (sequence: number, eventType: ExecutionCallback['eventType'], org = orgId): ExecutionCallback => ({ orgId: org, executionId, sequence, eventType, occurredAt: `2026-08-04T00:00:0${sequence}.000Z`, evidenceRef: `evidence://eval/run-${sequence}` });

class DurableFake implements ExecutionEventStore {
  readonly events = new Map<number, ExecutionCallback>();
  projection: ExecutionProjection = { orgId, executionId, status: 'accepted', lastSequence: 1, acceptedAt: '2026-08-04T00:00:01.000Z' };
  async recordAtomic(value: ExecutionCallback, supplied: ExecutionCallbackCapability): Promise<ExecutionRecordResult> {
    if (supplied.service !== capability.service || supplied.token !== capability.token || value.orgId !== orgId) throw new Error('execution callback capability denied');
    const prior = this.events.get(value.sequence);
    if (prior) {
      if (JSON.stringify(prior) === JSON.stringify(value)) return { disposition: 'duplicate', projection: this.projection };
      throw new Error('conflicting execution callback sequence');
    }
    if (value.sequence !== this.projection.lastSequence + 1) return { disposition: 'out_of_order', projection: this.projection };
    this.events.set(value.sequence, value);
    this.projection = { ...this.projection, status: value.eventType === 'checkpoint' ? this.projection.status : value.eventType, lastSequence: value.sequence, completedAt: ['succeeded','failed','cancelled','timed_out'].includes(value.eventType) ? value.occurredAt : undefined, evidenceRef: value.evidenceRef };
    return { disposition: 'applied', projection: this.projection };
  }
}

describe('ExecutionService', () => {
  it('accepts only digest and approved evidence-reference callback payloads', () => {
    expect(() => executionCallbackSchema.parse({ ...event(2, 'started'), payloadDigest: 'raw-client-data' })).toThrow();
    expect(() => executionCallbackSchema.parse({ ...event(2, 'started'), evidenceRef: 'https://unbounded.example/payload' })).toThrow();
  });
  it('persists atomically and survives service restart against the same durable store', async () => {
    const store = new DurableFake(); const service = new ExecutionService(store);
    await service.record(event(2, 'started'), capability);
    const restarted = new ExecutionService(store);
    await restarted.record(event(3, 'checkpoint'), capability);
    const completed = await restarted.record(event(4, 'succeeded'), capability);
    expect(completed.projection).toMatchObject({ status: 'succeeded', lastSequence: 4 });
  });
  it('records exact duplicates, rejects conflicts/out-of-order and denies cross-org/wrong capability', async () => {
    const store = new DurableFake(); const service = new ExecutionService(store);
    await service.record(event(2, 'started'), capability);
    expect((await service.record(event(2, 'started'), capability)).disposition).toBe('duplicate');
    await expect(service.record({ ...event(2, 'started'), evidenceRef: 'evidence://other' }, capability)).rejects.toThrow(/conflicting/);
    expect((await service.record(event(4, 'succeeded'), capability)).disposition).toBe('out_of_order');
    await expect(service.record(event(3, 'checkpoint', otherOrg), capability)).rejects.toThrow(/denied/);
    await expect(service.record(event(3, 'checkpoint'), { ...capability, token: 'wrong' })).rejects.toThrow(/denied/);
  });
});
