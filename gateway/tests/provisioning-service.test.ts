import { describe, expect, it, vi } from 'vitest';
import { ProvisioningService } from '../src/services/provisioning/provisioning-service.js';
const request = { requestId: 'p', orgId: '00000000-0000-0000-0000-000000000002', instanceId: 'i', releaseId: 'r', requestRef: 'ref', sourceWorkflowId: 'source', workflowDigest: `sha256:${'a'.repeat(64)}`, configurationDigest: `sha256:${'b'.repeat(64)}`, environment: 'production' as const, status: 'requested' };
describe('ProvisioningService', () => {
  it('creates a distinct inactive copy, smokes it, then activates and records deployment', async () => {
    const store = { begin: vi.fn(async () => request), mark: vi.fn(async () => undefined), createDeployment: vi.fn(async () => 'deploy') };
    const provisioner = { createInactiveCopy: vi.fn(async () => ({ workflowId: 'copy', workflowDigest: request.workflowDigest, active: false })), activateAfterSmoke: vi.fn(async (_id, smoke) => smoke()), compensate: vi.fn(async () => undefined) };
    const service = new ProvisioningService(store, provisioner as never, vi.fn(async () => undefined));
    await expect(service.run(request.orgId, request.requestRef)).resolves.toMatchObject({ status: 'completed', workflowId: 'copy' });
    expect(provisioner.activateAfterSmoke).toHaveBeenCalledWith('copy', expect.any(Function));
  });
  it('compensates and marks failure if smoke or activation fails', async () => {
    const store = { begin: vi.fn(async () => request), mark: vi.fn(async () => undefined), createDeployment: vi.fn(async () => 'deploy') };
    const provisioner = { createInactiveCopy: vi.fn(async () => ({ workflowId: 'copy', workflowDigest: request.workflowDigest, active: false })), activateAfterSmoke: vi.fn(async () => { throw new Error('smoke failed'); }), compensate: vi.fn(async () => undefined) };
    await expect(new ProvisioningService(store, provisioner as never, async () => undefined).run(request.orgId, request.requestRef)).rejects.toThrow('smoke failed');
    expect(provisioner.compensate).toHaveBeenCalledWith('copy');
    expect(store.mark).toHaveBeenLastCalledWith(request.orgId, 'p', 'failed');
  });
});
