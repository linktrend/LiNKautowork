import { describe, expect, it } from 'vitest';
import { SupabaseProviderRpcClient, SupabaseProviderStore, type ProviderRpcClient } from '../src/services/supabase-provider-store.js';

const ORG = '11111111-1111-4111-8111-111111111111';

function jwt(role: string, orgId = ORG): string {
  const encode = (value: unknown) => Buffer.from(JSON.stringify(value)).toString('base64url');
  return `${encode({ alg: 'none', typ: 'JWT' })}.${encode({ role, org_id: orgId })}.signature`;
}

describe('SupabaseProviderStore', () => {
  it('carries the explicit org context into narrow provider RPC calls', async () => {
    const calls: Array<{ name: string; body: Record<string, unknown>; org: string }> = [];
    const rpc: ProviderRpcClient = { callProviderRpc: async <T>(name: string, body: Record<string, unknown>, org: string): Promise<T> => { calls.push({ name, body, org }); return (name === 'linkautowork_provider_kill_switch_active' ? false : null) as T; } };
    const store = new SupabaseProviderStore(rpc);
    await expect(store.isKillSwitchActive('org-a', 'repo-status')).resolves.toBe(false);
    expect(calls).toEqual([{ name: 'linkautowork_provider_kill_switch_active', body: { p_automation_id: 'repo-status' }, org: 'org-a' }]);
  });

  it('sends provider RPCs with the custom schema profile and dedicated runtime JWT', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const fetchImpl: typeof fetch = async (url, init) => { calls.push({ url: String(url), init }); return new Response('{}', { status: 200 }); };
    const client = new SupabaseProviderRpcClient({ supabaseUrl: 'https://db.test', runtimeJwt: jwt('svc_lautowork_runtime'), apiKey: 'public-key' }, fetchImpl);
    await client.callProviderRpc('linkautowork_provider_set_kill_switch', { p_automation_id: 'repo-status', p_active: true, p_reason_ref: 'platform://tests/reason' }, ORG);
    expect(calls[0]).toMatchObject({ url: 'https://db.test/rest/v1/rpc/linkautowork_provider_set_kill_switch' });
    expect(calls[0].init?.headers).toMatchObject({
      apikey: 'public-key', authorization: `Bearer ${jwt('svc_lautowork_runtime')}`,
      'Accept-Profile': 'lautowork', 'Content-Profile': 'lautowork', 'x-link-org-id': ORG,
    });
  });

  it('rejects gateway, service-role, and cross-organisation runtime credentials before fetch', async () => {
    let calls = 0;
    const fetchImpl: typeof fetch = async () => { calls += 1; return new Response('{}'); };
    await expect(new SupabaseProviderRpcClient({ supabaseUrl: 'https://db.test', runtimeJwt: jwt('svc_lautowork_gateway') }, fetchImpl).callProviderRpc('rpc', {}, ORG)).rejects.toThrow(/dedicated runtime role/);
    await expect(new SupabaseProviderRpcClient({ supabaseUrl: 'https://db.test', runtimeJwt: jwt('service_role') }, fetchImpl).callProviderRpc('rpc', {}, ORG)).rejects.toThrow(/dedicated runtime role/);
    await expect(new SupabaseProviderRpcClient({ supabaseUrl: 'https://db.test', runtimeJwt: jwt('svc_lautowork_runtime', '22222222-2222-4222-8222-222222222222') }, fetchImpl).callProviderRpc('rpc', {}, ORG)).rejects.toThrow(/dedicated runtime role/);
    expect(calls).toBe(0);
  });

  it('maps the AW-01 reason reference into the runtime-only kill-switch RPC', async () => {
    const calls: Array<{ name: string; body: Record<string, unknown>; org: string }> = [];
    const rpc: ProviderRpcClient = { callProviderRpc: async <T>(name: string, body: Record<string, unknown>, org: string): Promise<T> => { calls.push({ name, body, org }); return undefined as T; } };
    await new SupabaseProviderStore(rpc).setKillSwitch(ORG, null, true, 'platform://tests/global-activate');
    expect(calls).toEqual([{ name: 'linkautowork_provider_set_kill_switch', body: { p_automation_id: null, p_active: true, p_reason_ref: 'platform://tests/global-activate' }, org: ORG }]);
  });
});
