import type { AppEnv } from '../config/env.js';

type N8nWorkflow = {
  id: string;
  name: string;
  active: boolean;
};

type N8nWorkflowListResponse = {
  data?: N8nWorkflow[];
};

export class N8nClient {
  constructor(private readonly env: AppEnv) {}

  async triggerWebhook(path: string, method: string, payload: Record<string, unknown>): Promise<{
    status: number;
    body: unknown;
  }> {
    const normalizedPrefix = this.env.N8N_WEBHOOK_PATH_PREFIX.endsWith('/')
      ? this.env.N8N_WEBHOOK_PATH_PREFIX.slice(0, -1)
      : this.env.N8N_WEBHOOK_PATH_PREFIX;
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    const url = `${this.env.N8N_BASE_URL}${normalizedPrefix}${normalizedPath}`;

    const response = await fetch(url, {
      method,
      headers: {
        'content-type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    let body: unknown;
    const raw = await response.text();
    try {
      body = raw ? JSON.parse(raw) : {};
    } catch {
      body = raw;
    }

    return {
      status: response.status,
      body,
    };
  }

  async listWorkflows(): Promise<N8nWorkflow[]> {
    const url = `${this.env.N8N_BASE_URL}${this.env.N8N_API_BASE_PATH}/workflows?limit=250`;
    const response = await fetch(url, {
      headers: {
        'x-n8n-api-key': this.env.N8N_API_KEY,
      },
    });

    if (!response.ok) {
      throw new Error(`n8n list workflows failed with status ${response.status}`);
    }

    const json = (await response.json()) as N8nWorkflowListResponse;
    return json.data ?? [];
  }

  async setWorkflowActive(workflowId: string, active: boolean): Promise<void> {
    const url = `${this.env.N8N_BASE_URL}${this.env.N8N_API_BASE_PATH}/workflows/${workflowId}`;
    const response = await fetch(url, {
      method: 'PATCH',
      headers: {
        'x-n8n-api-key': this.env.N8N_API_KEY,
        'content-type': 'application/json',
      },
      body: JSON.stringify({ active }),
    });

    if (!response.ok) {
      throw new Error(`n8n workflow update failed for ${workflowId} with status ${response.status}`);
    }
  }

  async deactivateAllActiveWorkflows(): Promise<number> {
    const workflows = await this.listWorkflows();
    const active = workflows.filter((w) => w.active);
    for (const workflow of active) {
      await this.setWorkflowActive(workflow.id, false);
    }
    return active.length;
  }
}
