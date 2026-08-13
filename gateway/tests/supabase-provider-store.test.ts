import { describe, expect, it } from 'vitest';
import { SupabaseProviderStore, type ProviderRpcClient } from '../src/services/supabase-provider-store.js';

describe('SupabaseProviderStore', () => {
  it('carries the explicit org context into narrow provider RPC calls', async () => {
    const calls: Array<{ name: string; body: Record<string, unknown>; org: string }> = [];
    const rpc: ProviderRpcClient = { callProviderRpc: async <T>(name: string, body: Record<string, unknown>, org: string): Promise<T> => { calls.push({ name, body, org }); return (name === 'linkautowork_provider_kill_switch_active' ? false : null) as T; } };
    const store = new SupabaseProviderStore(rpc);
    await expect(store.isKillSwitchActive('org-a', 'repo-status')).resolves.toBe(false);
    expect(calls).toEqual([{ name: 'linkautowork_provider_kill_switch_active', body: { p_automation_id: 'repo-status' }, org: 'org-a' }]);
  });
});
