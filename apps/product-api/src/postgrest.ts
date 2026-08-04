import type { AuditReservationInput, PostgrestRpc } from './service.js';

/** Runtime-only configuration for the trusted Product API server-to-PostgREST boundary. */
export type PostgrestConfig = { restUrl: string; serviceRoleToken: string; rpcPath?: string };

/**
 * Makes only named RPC calls. The caller's organisation is carried in both
 * the governed request claims and header expected by `assert_command_authorized`.
 * No secret is returned, stored, or sent to a browser.
 */
export function createPostgrestRpc(config: PostgrestConfig): PostgrestRpc {
  if (!/^https?:\/\//.test(config.restUrl) || config.serviceRoleToken.length < 20) throw new Error('Product API PostgREST configuration is unavailable');
  const base = config.restUrl.replace(/\/+$/, '');
  const rpcRoot = (config.rpcPath ?? '/rest/v1').replace(/^\/+|\/+$/g, '');
  const restBase = rpcRoot === '' ? base : base.endsWith(`/${rpcRoot}`) ? base : `${base}/${rpcRoot}`;
  return async (name, body, orgId, audit?: AuditReservationInput) => {
    if (!/^linkautowork_product_[a-z0-9_]+$/.test(name)) throw new Error('Product API RPC name is not allow-listed');
    const claims = orgId ? { role: 'service_role', org_id: orgId } : { role: 'service_role' };
    const response = await fetch(`${restBase}/rpc/${name}`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${config.serviceRoleToken}`,
        apikey: config.serviceRoleToken,
        'content-type': 'application/json',
        prefer: 'return=representation',
        ...(orgId ? { 'x-link-org-id': orgId, 'x-link-request-claims': JSON.stringify(claims) } : {}),
        ...(audit ? { 'x-link-audit-actor': audit.actor, 'x-link-audit-resource': audit.resource, 'x-link-audit-action': audit.action, 'x-link-audit-reason': audit.reason, 'x-link-audit-correlation': audit.correlationId } : {}),
      },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error(`product_persistence_unavailable:${response.status}:${(await response.text()).slice(0, 240)}`);
    return response.json() as Promise<unknown>;
  };
}
