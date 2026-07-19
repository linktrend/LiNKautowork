import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AppEnv } from '../src/config/env.js';
import type { MissionEnvelope } from '../src/contracts/types.js';
import { AuditService } from '../src/services/audit.js';
import { SupabaseAuditClient, type AuditRecord } from '../src/integrations/supabase-rpc.js';

const auditEnv = {
  SUPABASE_URL: 'https://project.supabase.co',
  SUPABASE_AUDIT_RPC: 'linkautowork_write_audit_run',
  SUPABASE_SERVICE_ROLE_KEY: 'service-role-key',
} as unknown as AppEnv;

const record: AuditRecord = {
  orgId: '00000000-0000-0000-0000-000000000001',
  run_id: 'r-1',
  task_id: 't-1',
  dpr_id: 'd-1',
  status: 'success',
  token_usage: 0,
  command_log: { gateway_service: 'n8n' },
  details: { automation_workflow_id: 'wf-1' },
  created_at: '2026-07-15T00:00:00.000Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('SupabaseAuditClient.writeAudit', () => {
  it('posts to the configured RPC URL with service-role auth headers', async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await new SupabaseAuditClient(auditEnv).writeAudit(record);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('https://project.supabase.co/rest/v1/rpc/linkautowork_write_audit_run');
    expect(init.method).toBe('POST');
    const headers = init.headers as Record<string, string>;
    expect(headers.apikey).toBe('service-role-key');
    expect(headers.authorization).toBe('Bearer service-role-key');
    expect(headers['content-type']).toBe('application/json');
  });

  it('maps the internal orgId onto the wire key `tenant_id` (RPC compat) and never sends org_id', async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await new SupabaseAuditClient(auditEnv).writeAudit(record);

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    // The DB column is org_id, but the RPC parameter is still literally named
    // tenant_id (docs/archive/adr/0001). Regressing this mapping silently breaks the
    // PostgREST call, so it is asserted explicitly.
    expect(body.tenant_id).toBe('00000000-0000-0000-0000-000000000001');
    expect(body).not.toHaveProperty('org_id');
    expect(body).not.toHaveProperty('orgId');
    expect(body.run_id).toBe('r-1');
    expect(body.task_id).toBe('t-1');
    expect(body.dpr_id).toBe('d-1');
    expect(body.status).toBe('success');
    expect(body.command_log).toEqual({ gateway_service: 'n8n' });
    expect(body.details).toEqual({ automation_workflow_id: 'wf-1' });
  });

  it('throws when the RPC responds with a non-ok status', async () => {
    const fetchMock = vi.fn(async () => new Response('permission denied', { status: 403 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(new SupabaseAuditClient(auditEnv).writeAudit(record)).rejects.toThrow(
      /audit rpc failed with status 403/,
    );
  });
});

describe('AuditService.writeRunAudit', () => {
  const mission: MissionEnvelope = {
    tenantId: '00000000-0000-0000-0000-000000000001',
    missionId: 'm-1',
    runId: 'r-9',
    taskId: 't-9',
    dprId: 'd-9',
    triggerSource: 'test',
  };

  it('maps the inbound mission envelope into an audit record (tenantId -> orgId)', async () => {
    const writes: AuditRecord[] = [];
    const client = { writeAudit: async (r: AuditRecord) => void writes.push(r) } as SupabaseAuditClient;

    await new AuditService(client).writeRunAudit({
      mission,
      status: 'success',
      tokenUsage: 5,
      commandLog: { route: '/v1/ingress' },
      details: { latency_ms: 12 },
    });

    expect(writes).toHaveLength(1);
    const written = writes[0];
    expect(written.orgId).toBe(mission.tenantId);
    expect(written.run_id).toBe('r-9');
    expect(written.task_id).toBe('t-9');
    expect(written.dpr_id).toBe('d-9');
    expect(written.status).toBe('success');
    expect(written.token_usage).toBe(5);
    expect(written.command_log).toEqual({ route: '/v1/ingress' });
    expect(written.details).toEqual({ latency_ms: 12 });
    expect(typeof written.created_at).toBe('string');
  });
});
