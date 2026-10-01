import {
  providerCallbackSchema,
  providerCanonicalRequestFingerprint,
  providerCursorPageSchema,
  providerEventSchema,
  PROVIDER_RUN_STATES,
  type ProviderInvocationRequest,
  type ProviderReceipt,
} from '../../../packages/automation-contracts/src/provider-contract.js';
import { assertProviderRuntimeInvoker, type ProviderRuntimeInvoker } from '../../../packages/automation-contracts/src/provider-persistence.js';
import type { ProviderInvokerContext, ProviderRequestRecord, ProviderStore } from './provider-store.js';

type ProviderState = (typeof PROVIDER_RUN_STATES)[number];
type ProviderCallback = ReturnType<typeof providerCallbackSchema.parse>;
type ProviderEvent = ReturnType<typeof providerEventSchema.parse>;

/** The only configuration a provider RPC client needs; no service-role key is accepted. */
export type ProviderRpcClientConfig = {
  supabaseUrl: string;
  runtimeJwt: string;
  apiKey?: string;
};

/** Narrow RPC boundary. Provider calls must use the dedicated runtime role and org claim. */
export type ProviderRpcClient = {
  callProviderRpc<T>(rpcName: string, body: Record<string, unknown>, orgId: string, invoker?: ProviderInvokerContext): Promise<T>;
};

type ProviderJwtClaims = { role?: unknown; org_id?: unknown };

function decodeProviderJwt(token: string): ProviderJwtClaims {
  const payload = token.split('.')[1];
  if (!payload) throw new Error('provider runtime credential is not a JWT');
  try {
    const parsed = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('provider runtime credential claims are invalid');
    return parsed as ProviderJwtClaims;
  } catch {
    throw new Error('provider runtime credential claims are invalid');
  }
}

function assertProviderJwt(config: ProviderRpcClientConfig, orgId: string, invoker?: ProviderInvokerContext): ProviderRuntimeInvoker {
  if (!config.runtimeJwt) throw new Error('provider runtime credential is not configured');
  const claims = decodeProviderJwt(config.runtimeJwt);
  if (claims.role !== 'svc_lautowork_runtime' || claims.org_id !== orgId) {
    throw new Error('provider runtime credential must match the dedicated runtime role and requested organisation');
  }
  try {
    return assertProviderRuntimeInvoker(invoker ?? { org_id: orgId, jwt_role: 'runtime', claim_org_id: orgId });
  } catch (error) {
    throw new Error(error instanceof Error ? error.message : 'provider runtime invoker is invalid');
  }
}

/** PostgREST provider RPC client. It selects `lautowork` and never falls back to service_role. */
export class SupabaseProviderRpcClient implements ProviderRpcClient {
  constructor(private readonly config: ProviderRpcClientConfig, private readonly fetchImpl: typeof fetch = fetch) {}

  async callProviderRpc<T>(rpcName: string, body: Record<string, unknown>, orgId: string, invoker?: ProviderInvokerContext): Promise<T> {
    assertProviderJwt(this.config, orgId, invoker);
    const response = await this.fetchImpl(`${this.config.supabaseUrl}/rest/v1/rpc/${rpcName}`, {
      method: 'POST',
      headers: {
        ...(this.config.apiKey ? { apikey: this.config.apiKey } : {}),
        authorization: `Bearer ${this.config.runtimeJwt}`,
        'content-type': 'application/json',
        'Accept-Profile': 'lautowork',
        'Content-Profile': 'lautowork',
        'x-link-org-id': orgId,
      },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      // Keep response details out of the caller-facing error; PostgREST may include SQL text.
      throw new Error(`provider RPC ${rpcName} failed with status ${response.status}`);
    }
    if (response.status === 204) return undefined as T;
    return await response.json() as T;
  }
}

/** PostgREST adapter for the AW-02 ProviderStore contract. */
export class SupabaseProviderStore implements ProviderStore {
  constructor(private readonly rpc: ProviderRpcClient) {}

  accept(orgId: string, request: ProviderInvocationRequest, _now?: Date, invoker?: ProviderInvokerContext): Promise<{ record: ProviderRequestRecord; replay: boolean }> {
    return this.rpc.callProviderRpc('linkautowork_provider_accept', { p_request: request, p_request_fingerprint: providerCanonicalRequestFingerprint(request) }, orgId, invoker);
  }

  getRequest(orgId: string, requestId: string, invoker?: ProviderInvokerContext): Promise<ProviderRequestRecord> {
    return this.rpc.callProviderRpc('linkautowork_provider_get_request', { p_request_id: requestId }, orgId, invoker);
  }

  writeReceipt(orgId: string, receipt: ProviderReceipt, invoker?: ProviderInvokerContext): Promise<ProviderReceipt> {
    return this.rpc.callProviderRpc('linkautowork_provider_write_receipt', { p_receipt: receipt }, orgId, invoker);
  }

  transition(orgId: string, requestId: string, expectedVersion: number, nextState: ProviderState, invoker?: ProviderInvokerContext): Promise<ProviderRequestRecord> {
    return this.rpc.callProviderRpc('linkautowork_provider_transition', { p_request_id: requestId, p_expected_version: expectedVersion, p_next_state: nextState }, orgId, invoker);
  }

  admitCallback(orgId: string, callback: ProviderCallback, invoker?: ProviderInvokerContext): Promise<ProviderReceipt> {
    return this.rpc.callProviderRpc('linkautowork_provider_admit_callback', { p_callback: providerCallbackSchema.parse(callback) }, orgId, invoker);
  }

  async appendEvent(orgId: string, event: ProviderEvent, invoker?: ProviderInvokerContext): Promise<void> {
    await this.rpc.callProviderRpc<void>('linkautowork_provider_append_event', { p_event: providerEventSchema.parse(event) }, orgId, invoker);
  }

  listEvents(orgId: string, afterCursor: string | null, limit: number, invoker?: ProviderInvokerContext): Promise<ReturnType<typeof providerCursorPageSchema.parse>> {
    return this.rpc.callProviderRpc<ReturnType<typeof providerCursorPageSchema.parse>>('linkautowork_provider_list_events', { p_after_cursor: afterCursor, p_limit: limit }, orgId, invoker).then((page) => providerCursorPageSchema.parse(page));
  }

  isKillSwitchActive(orgId: string, automationId: string, invoker?: ProviderInvokerContext): Promise<boolean> {
    return this.rpc.callProviderRpc('linkautowork_provider_kill_switch_active', { p_automation_id: automationId }, orgId, invoker);
  }

  setKillSwitch(orgId: string, automationId: string | null, active: boolean, reasonRef: string, invoker?: ProviderInvokerContext): Promise<void> {
    return this.rpc.callProviderRpc<void>('linkautowork_provider_set_kill_switch', { p_automation_id: automationId, p_active: active, p_reason_ref: reasonRef }, orgId, invoker);
  }
}
