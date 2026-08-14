import { providerCallbackSchema, providerCanonicalRequestFingerprint, providerCursorPageSchema, providerEventSchema, type ProviderInvocationRequest, type ProviderReceipt } from '../../../packages/automation-contracts/src/provider-contract.js';
import type { ProviderStore, ProviderRequestRecord } from './provider-store.js';

/** Narrow RPC boundary: the runtime JWT and database RLS establish the org context. */
export type ProviderRpcClient = { callProviderRpc<T>(rpcName: string, body: Record<string, unknown>, orgId: string): Promise<T> };

/** PostgREST RPC adapter. Provider SQL functions atomically enforce idempotency and CAS. */
export class SupabaseProviderStore {
  constructor(private readonly rpc: ProviderRpcClient) {}
  accept(orgId: string, request: ProviderInvocationRequest): Promise<{ record: ProviderRequestRecord; replay: boolean }> { return this.rpc.callProviderRpc('linkautowork_provider_accept', { p_request: request, p_request_fingerprint: providerCanonicalRequestFingerprint(request) }, orgId); }
  getRequest(orgId: string, requestId: string): Promise<ProviderRequestRecord> { return this.rpc.callProviderRpc('linkautowork_provider_get_request', { p_request_id: requestId }, orgId); }
  writeReceipt(orgId: string, receipt: ProviderReceipt): Promise<ProviderReceipt> { return this.rpc.callProviderRpc('linkautowork_provider_write_receipt', { p_receipt: receipt }, orgId); }
  transition(orgId: string, requestId: string, expectedVersion: number, nextState: string): Promise<ProviderRequestRecord> { return this.rpc.callProviderRpc('linkautowork_provider_transition', { p_request_id: requestId, p_expected_version: expectedVersion, p_next_state: nextState }, orgId); }
  async admitCallback(orgId: string, callback: unknown): Promise<ProviderReceipt> { return this.rpc.callProviderRpc('linkautowork_provider_admit_callback', { p_callback: providerCallbackSchema.parse(callback) }, orgId); }
  async appendEvent(orgId: string, event: unknown): Promise<void> { await this.rpc.callProviderRpc('linkautowork_provider_append_event', { p_event: providerEventSchema.parse(event) }, orgId); }
  async listEvents(orgId: string, afterCursor: string | null, limit: number): Promise<ReturnType<typeof providerCursorPageSchema.parse>> { return providerCursorPageSchema.parse(await this.rpc.callProviderRpc('linkautowork_provider_list_events', { p_after_cursor: afterCursor, p_limit: limit }, orgId)); }
  async isKillSwitchActive(orgId: string, automationId: string): Promise<boolean> { return this.rpc.callProviderRpc('linkautowork_provider_kill_switch_active', { p_automation_id: automationId }, orgId); }
}
