import { createHash } from 'node:crypto';
import type { N8nClient } from './n8n-client.js';

export type WorkflowCopyRequest = { sourceWorkflowId: string; instanceId: string; expectedDigest: string };
export type WorkflowCopyReceipt = { workflowId: string; workflowDigest: string; active: boolean };
function workflowDigest(workflow: unknown): string { return `sha256:${createHash('sha256').update(JSON.stringify(workflow)).digest('hex')}`; }

/** Gateway-only n8n workflow cloning. It never returns or accepts an n8n credential. */
export class N8nProvisioner {
  constructor(private readonly n8n: Pick<N8nClient, 'getWorkflow' | 'createWorkflow' | 'setWorkflowActive' | 'deleteWorkflow' | 'smokeWorkflow'>) {}
  async createInactiveCopy(request: WorkflowCopyRequest): Promise<WorkflowCopyReceipt> {
    const source = await this.n8n.getWorkflow(request.sourceWorkflowId);
    const sourceDigest = workflowDigest({ name: source.name, nodes: source.nodes ?? [], connections: source.connections ?? {}, settings: source.settings ?? {} });
    if (sourceDigest !== request.expectedDigest) throw new Error('source workflow digest mismatch');
    const copy = await this.n8n.createWorkflow({ name: `${source.name} [instance:${request.instanceId}]`, nodes: source.nodes ?? [], connections: source.connections ?? {}, settings: source.settings ?? {} });
    return { workflowId: copy.id, workflowDigest: sourceDigest, active: false };
  }
  async activateAfterSmoke(workflowId: string, smoke: () => Promise<void>): Promise<void> { await smoke(); await this.n8n.setWorkflowActive(workflowId, true); }
  smoke(workflowId: string): Promise<void> { return this.n8n.smokeWorkflow(workflowId); }
  async compensate(workflowId: string): Promise<void> { await this.n8n.setWorkflowActive(workflowId, false).catch(() => undefined); await this.n8n.deleteWorkflow(workflowId).catch(() => undefined); }
}
