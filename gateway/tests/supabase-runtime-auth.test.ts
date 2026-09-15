import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AppEnv } from '../src/config/env.js';
import { SupabaseAuditClient } from '../src/integrations/supabase-rpc.js';

const org = '00000000-0000-0000-0000-000000000002';
afterEach(() => vi.unstubAllGlobals());

describe('Supabase scoped runtime credential boundary', () => {
  it('uses the apikey only for project routing and the scoped JWT for Authorization with an org consistency header', async () => {
    const fetchMock = vi.fn(async () => new Response('null', { status: 200, headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    const client = new SupabaseAuditClient({ NODE_ENV: 'test', SUPABASE_URL: 'https://db.test', SUPABASE_SERVICE_ROLE_KEY: 'ltfx.ph.943ead1c69.v1', SUPABASE_RUNTIME_JWT: 'signed-scoped-runtime-jwt' } as AppEnv);
    await client.findBoundInstance(org, 'linksites', 'linksites.reminder.run');
    expect(fetchMock).toHaveBeenCalledWith('https://db.test/rest/v1/rpc/linkautowork_resolve_bound_instance', expect.objectContaining({ headers: expect.objectContaining({ apikey: 'ltfx.ph.943ead1c69.v1', authorization: 'Bearer signed-scoped-runtime-jwt', 'x-link-org-id': org }) }));
  });
  it('fails closed instead of falling back to the broad service credential', async () => {
    const client = new SupabaseAuditClient({ NODE_ENV: 'test', SUPABASE_URL: 'https://db.test', SUPABASE_SERVICE_ROLE_KEY: 'ltfx.ph.943ead1c69.v1' } as AppEnv);
    await expect(client.findBoundInstance(org, 'linksites', 'linksites.reminder.run')).rejects.toThrow(/runtime credential/);
  });
});

describe('dedicated production gateway credential', () => {
  const runtimeToken = (role: string, orgId = org) => ['configuration', Buffer.from(JSON.stringify({ role, org_id: orgId })).toString('base64url'), 'signature-checked-by-postgrest'].join('.');
  const production = { NODE_ENV: 'production', ACTIVE_TENANT_UUID: org, SUPABASE_URL: 'https://db.test', SUPABASE_API_KEY: 'ltfx.ph.gateway-publishable.v1' } as AppEnv;
  it('uses dedicated gateway bearer for hydration and dispatch without a broad fallback', async () => {
    const fetchMock = vi.fn(async () => new Response('[]'));
    vi.stubGlobal('fetch', fetchMock);
    const token = runtimeToken('svc_lautowork_gateway');
    const client = new SupabaseAuditClient({ ...production, SUPABASE_RUNTIME_JWT: token });
    await client.listActiveKillSwitches();
    expect(fetchMock).toHaveBeenCalledWith('https://db.test/rest/v1/rpc/linkautowork_gateway_active_killswitches', expect.objectContaining({
      headers: expect.objectContaining({ authorization: `Bearer ${token}`, apikey: 'ltfx.ph.gateway-publishable.v1', 'x-link-org-id': org }),
      body: JSON.stringify({ p_org_id: org }),
    }));
  });
  it('rejects legacy/broad roles and mismatched org before contacting PostgREST', async () => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    for (const token of [runtimeToken('service_role'), runtimeToken('svc_lautowork_runtime'), runtimeToken('svc_lautowork_gateway', 'other-org')]) {
      await expect(new SupabaseAuditClient({ ...production, SUPABASE_RUNTIME_JWT: token }).findBoundInstance(org, 'gateway', 'precheck')).rejects.toThrow(/dedicated role/);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
