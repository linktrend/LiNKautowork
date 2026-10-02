import type { AppEnv } from '../config/env.js';

type N8nWorkflow = {
  id: string;
  name: string;
  active: boolean;
  nodes?: unknown[];
  connections?: Record<string, unknown>;
  settings?: Record<string, unknown>;
};

type N8nWorkflowListResponse = {
  data?: N8nWorkflow[];
};

export class N8nClient {
  constructor(private readonly env: AppEnv) {}

  /** Sends only the fixed provider correlation envelope to the authenticated canary webhook. */
  async triggerConnectionHealthWebhook(payload: { request_id: string; request_fingerprint: string }, token: string): Promise<unknown> {
    if (!token.trim()) throw new Error('connection-health webhook token is not configured');
    const normalizedPrefix = this.env.N8N_WEBHOOK_PATH_PREFIX.endsWith('/')
      ? this.env.N8N_WEBHOOK_PATH_PREFIX.slice(0, -1)
      : this.env.N8N_WEBHOOK_PATH_PREFIX;
    const url = `${this.env.N8N_BASE_URL}${normalizedPrefix}/linkautowork-connection-health-v1`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10_000);
    try {
      const response = await fetch(url, {
        method: 'POST',
        redirect: 'error',
        headers: { 'content-type': 'application/json', 'x-link-connection-health-token': token },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      if (!response.ok) {
        await response.body?.cancel();
        throw new Error('connection-health webhook did not return a successful response');
      }
      if (!response.body) throw new Error('connection-health webhook did not return a response body');
      const reader = response.body.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > 8192) {
          await reader.cancel();
          throw new Error('connection-health webhook response exceeded its size limit');
        }
        chunks.push(value);
      }
      const raw = Buffer.concat(chunks).toString('utf8');
      try { return JSON.parse(raw) as unknown; } catch { throw new Error('connection-health webhook response was not valid JSON'); }
    } finally {
      clearTimeout(timeout);
    }
  }

  async triggerWebhook(path: string, method: string, payload: Record<string, unknown>, signal?: AbortSignal): Promise<{
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
      signal,
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

  /** Fetches an upstream workflow only for gateway-controlled copy provisioning. */
  async getWorkflow(workflowId: string): Promise<N8nWorkflow> {
    const response = await fetch(`${this.env.N8N_BASE_URL}${this.env.N8N_API_BASE_PATH}/workflows/${workflowId}`, { headers: { 'x-n8n-api-key': this.env.N8N_API_KEY } });
    if (!response.ok) throw new Error(`n8n workflow get failed with status ${response.status}`);
    return await response.json() as N8nWorkflow;
  }

  async createWorkflow(workflow: Omit<N8nWorkflow, 'id' | 'active'>): Promise<N8nWorkflow> {
    const response = await fetch(`${this.env.N8N_BASE_URL}${this.env.N8N_API_BASE_PATH}/workflows`, { method: 'POST', headers: { 'x-n8n-api-key': this.env.N8N_API_KEY, 'content-type': 'application/json' }, body: JSON.stringify({ ...workflow, active: false }) });
    if (!response.ok) throw new Error(`n8n workflow create failed with status ${response.status}`);
    return await response.json() as N8nWorkflow;
  }

  async deleteWorkflow(workflowId: string): Promise<void> {
    const response = await fetch(`${this.env.N8N_BASE_URL}${this.env.N8N_API_BASE_PATH}/workflows/${workflowId}`, { method: 'DELETE', headers: { 'x-n8n-api-key': this.env.N8N_API_KEY } });
    if (!response.ok && response.status !== 404) throw new Error(`n8n workflow delete failed with status ${response.status}`);
  }

  async smokeWorkflow(workflowId: string): Promise<void> {
    const response = await fetch(`${this.env.N8N_BASE_URL}${this.env.N8N_API_BASE_PATH}/workflows/${workflowId}/run`, { method: 'POST', headers: { 'x-n8n-api-key': this.env.N8N_API_KEY, 'content-type': 'application/json' }, body: JSON.stringify({ mode: 'pre_activation_smoke' }) });
    if (!response.ok) throw new Error(`n8n workflow smoke failed with status ${response.status}`);
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
