import type { N8nProvisioner } from '../../integrations/n8n-provisioner.js';

export type ProvisioningRecord = { requestId: string; orgId: string; instanceId: string; releaseId: string; requestRef: string; sourceWorkflowId: string; workflowDigest: string; configurationDigest: string; environment: 'development' | 'stage' | 'production'; status: string; deploymentId?: string; workflowId?: string };
export interface ProvisioningStore {
  begin(orgId: string, requestRef: string): Promise<ProvisioningRecord | undefined>;
  mark(orgId: string, requestId: string, status: string, fields?: Record<string, unknown>): Promise<void>;
  createDeployment(args: { request: ProvisioningRecord; workflowId: string }): Promise<string>;
}

/** Durable, replay-safe state machine around an inactive n8n workflow copy. */
export class ProvisioningService {
  constructor(private readonly store: ProvisioningStore, private readonly provisioner: N8nProvisioner, private readonly smoke: (workflowId: string) => Promise<void>) {}
  async run(orgId: string, requestRef: string, environment?: ProvisioningRecord['environment']): Promise<ProvisioningRecord> {
    const request = await this.store.begin(orgId, requestRef);
    if (!request) throw new Error('provisioning request not found');
    if (environment && request.environment !== environment) throw new Error('provisioning environment does not match durable request');
    if (request.status === 'completed') return request;
    let workflowId: string | undefined;
    try {
      await this.store.mark(request.orgId, request.requestId, 'provisioning');
      const copy = await this.provisioner.createInactiveCopy({ sourceWorkflowId: request.sourceWorkflowId, instanceId: request.instanceId, expectedDigest: request.workflowDigest });
      workflowId = copy.workflowId;
      const deploymentId = await this.store.createDeployment({ request, workflowId });
      await this.provisioner.activateAfterSmoke(workflowId, () => this.smoke(workflowId!));
      await this.store.mark(request.orgId, request.requestId, 'completed', { deploymentId, workflowId, workflowDigest: copy.workflowDigest });
      return { ...request, status: 'completed', deploymentId, workflowId };
    } catch (error) {
      if (workflowId) await this.provisioner.compensate(workflowId);
      await this.store.mark(request.orgId, request.requestId, 'failed');
      throw error;
    }
  }
}
