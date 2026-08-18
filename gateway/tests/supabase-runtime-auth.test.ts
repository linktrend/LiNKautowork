import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AppEnv } from '../src/config/env.js';
import { SupabaseAuditClient } from '../src/integrations/supabase-rpc.js';

const org = '00000000-0000-0000-0000-000000000002';
afterEach(() => vi.unstubAllGlobals());

describe('Supabase scoped runtime credential boundary', () => {
  it('uses the apikey only for project routing and the scoped JWT for Authorization with an org consistency header', async () => {
    const fetchMock = vi.fn(async () => new Response('null', { status: 200, headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    const client = new SupabaseAuditClient({ SUPABASE_URL: 'https://db.test', SUPABASE_SERVICE_ROLE_KEY: 'ltfx.ph.943ead1c69.v1', SUPABASE_RUNTIME_JWT: 'signed-scoped-runtime-jwt' } as AppEnv);
    await client.findBoundInstance(org, 'linksites', 'linksites.reminder.run');
    expect(fetchMock).toHaveBeenCalledWith('https://db.test/rest/v1/rpc/linkautowork_resolve_bound_instance', expect.objectContaining({ headers: expect.objectContaining({ apikey: 'ltfx.ph.943ead1c69.v1', authorization: 'Bearer signed-scoped-runtime-jwt', 'x-link-org-id': org }) }));
  });
  it('fails closed instead of falling back to the broad service credential', async () => {
    const client = new SupabaseAuditClient({ SUPABASE_URL: 'https://db.test', SUPABASE_SERVICE_ROLE_KEY: 'ltfx.ph.943ead1c69.v1' } as AppEnv);
    await expect(client.findBoundInstance(org, 'linksites', 'linksites.reminder.run')).rejects.toThrow(/runtime credential/);
  });
});
