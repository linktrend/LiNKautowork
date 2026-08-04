import { describe, expect, it, vi } from 'vitest';
import { InstanceRuntimeService, type BoundInstance, type ExecutionStore, type InstanceDispatcher } from '../src/services/instances/runtime.js';

const org = '00000000-0000-0000-0000-000000000002';
const instance: BoundInstance = { bindingId: 'b', orgId: org, automationId: 'client-a-reminder', instanceId: '40000000-0000-0000-0000-000000000001', consumerSystem: 'linksites', operation: 'linksites.reminder.run', enabled: true, instanceState: 'active', releaseId: 'r', releaseLifecycle: 'certified', deploymentId: 'd', workflowId: 'workflow-a', workflowDigest: `sha256:${'a'.repeat(64)}`, deployedDigest: `sha256:${'a'.repeat(64)}`, configurationDigest: `sha256:${'b'.repeat(64)}`, deployedConfigurationDigest: `sha256:${'b'.repeat(64)}`, inputSchema: { type: 'object', properties: { customer: { type: 'string' } }, additionalProperties: false }, webhookPath: '/instance/a', method: 'POST', criticality: 'critical', timeoutMs: 30000, retryCount: 1, secretRefs: ['LINK_CLIENT_A_TOKEN'] };

function setup(overrides: Partial<BoundInstance> = {}) {
  const store: ExecutionStore & { acceptExecution: ReturnType<typeof vi.fn> } = { findBoundInstance: vi.fn(async () => ({ ...instance, ...overrides })), acceptExecution: vi.fn(async (args) => ({ executionId: args.executionId, status: 'accepted' as const, correlationId: args.executionId, duplicate: false })) };
  const dispatcher = { triggerWebhook: vi.fn<InstanceDispatcher['triggerWebhook']>(async () => ({ status: 202, body: {} })) };
  const pauses = { isPaused: vi.fn(async (): Promise<{ paused: boolean; scope?: 'global' | 'organisation' | 'automation' | 'instance'; reason?: string }> => ({ paused: false })) };
  return { store, dispatcher, pauses, service: new InstanceRuntimeService(store, dispatcher, { isBlocked: () => ({ blocked: false }) }, pauses) };
}

describe('InstanceRuntimeService', () => {
  it('uses only the durable binding and sends secret references, never values', async () => {
    const { service, dispatcher } = setup();
    const receipt = await service.execute(org, 'linksites', instance.instanceId, instance.operation, { customer: 'a' }, 'idempotent-1');
    expect(receipt.status).toBe('accepted');
    expect(dispatcher.triggerWebhook).toHaveBeenCalledWith('/instance/a', 'POST', expect.objectContaining({ secretBroker: { mode: 'native_instance_credentials', refs: ['LINK_CLIENT_A_TOKEN'] } }), expect.any(AbortSignal));
  });
  it('rejects cross-system, mismatched instance, drift, and duplicate non-idempotent dispatch', async () => {
    const { service } = setup();
    await expect(service.execute(org, 'other', instance.instanceId, instance.operation, {}, 'x')).rejects.toThrow(/not found/);
    await expect(service.execute(org, 'linksites', '40000000-0000-0000-0000-000000000009', instance.operation, {}, 'x')).rejects.toThrow(/not found/);
    const drift = setup({ deployedDigest: `sha256:${'b'.repeat(64)}` }).service;
    await expect(drift.execute(org, 'linksites', instance.instanceId, instance.operation, {}, 'x')).rejects.toThrow(/drifted/);
    const duplicate = setup(); duplicate.store.acceptExecution.mockImplementation(async () => ({ executionId: 'prior', status: 'accepted' as const, correlationId: 'prior', duplicate: true }));
    await expect(duplicate.service.execute(org, 'linksites', instance.instanceId, instance.operation, {}, 'x')).resolves.toMatchObject({ executionId: 'prior', duplicate: true });
    expect(duplicate.dispatcher.triggerWebhook).not.toHaveBeenCalled();
  });
  it('fails closed for paused instances, deprecated releases, and kill switches', async () => {
    await expect(setup({ instanceState: 'paused' }).service.execute(org, 'linksites', instance.instanceId, instance.operation, {}, 'x')).rejects.toThrow(/not enabled/);
    await expect(setup({ releaseLifecycle: 'deprecated' }).service.execute(org, 'linksites', instance.instanceId, instance.operation, {}, 'x')).rejects.toThrow(/not executable/);
    const halted = setup(); const service = new InstanceRuntimeService(halted.store, halted.dispatcher, { isBlocked: () => ({ blocked: true, scope: 'scoped', reason: 'incident' }) }, halted.pauses);
    await expect(service.execute(org, 'linksites', instance.instanceId, instance.operation, {}, 'x')).rejects.toThrow(/kill switch/);
  });
  it('enforces Draft 2020 nested/conditional schema semantics', async () => {
    const schema = { type: 'object', properties: { kind: { type: 'string', enum: ['email','sms'] }, recipients: { type: 'array', minItems: 1, items: { type: 'string', minLength: 3 } } }, required: ['kind','recipients'], additionalProperties: false, allOf: [{ if: { type: 'object', properties: { kind: { const: 'sms' } }, required: ['kind'] }, then: { type: 'object', properties: { recipients: { type: 'array', maxItems: 1 } } } }] };
    const runtime = setup({ inputSchema: schema }).service;
    await expect(runtime.execute(org, 'linksites', instance.instanceId, instance.operation, { kind: 'sms', recipients: ['one','two'] }, 'schema-bad')).rejects.toThrow(/input/);
    await expect(runtime.execute(org, 'linksites', instance.instanceId, instance.operation, { kind: 'sms', recipients: ['one'] }, 'schema-good')).resolves.toMatchObject({ status: 'accepted' });
  });
  it('enforces injected durable pauses before acceptance or dispatch', async () => {
    const context = setup(); context.pauses.isPaused.mockResolvedValue({ paused: true, scope: 'automation', reason: 'operator hold' });
    await expect(context.service.execute(org, 'linksites', instance.instanceId, instance.operation, { customer: 'a' }, 'paused')).rejects.toThrow(/automation pause/);
    expect(context.pauses.isPaused).toHaveBeenCalledWith({ orgId: org, automationId: 'client-a-reminder', instanceId: instance.instanceId });
    expect(context.store.acceptExecution).not.toHaveBeenCalled(); expect(context.dispatcher.triggerWebhook).not.toHaveBeenCalled();
  });
  it('aborts an ambiguous timeout and never retries possible side effects', async () => {
    const context = setup({ timeoutMs: 5, retryCount: 3 });
    context.dispatcher.triggerWebhook.mockImplementation(async (_path, _method, _payload, signal?: AbortSignal) => new Promise((_, reject) => signal?.addEventListener('abort', () => reject(signal.reason))));
    await expect(context.service.execute(org, 'linksites', instance.instanceId, instance.operation, { customer: 'a' }, 'timeout')).rejects.toThrow(/not accepted/);
    expect(context.dispatcher.triggerWebhook).toHaveBeenCalledTimes(1);
    expect(context.dispatcher.triggerWebhook.mock.calls[0]?.[3]?.aborted).toBe(true);
  });
});
