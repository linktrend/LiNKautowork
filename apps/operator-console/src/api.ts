/** Finite typed client for the frozen WP-09 Product API; no caller-controlled paths or n8n proxy. */
export const operatorResources = ['packages', 'releases', 'certification', 'products', 'organisations', 'subscriptions', 'provisioning-jobs', 'instances', 'bindings', 'deployments', 'executions', 'health', 'incidents', 'maintenance', 'librarian-candidates', 'audit-evidence'] as const;
export type OperatorResource = typeof operatorResources[number];
export type OperatorAction = 'retry' | 'compensate' | 'pause' | 'resume' | 'acknowledge' | 'resolve' | 'canary' | 'promote' | 'rollback' | 'approve' | 'reject' | 'supersede';
/** The finite action vocabulary for each operator resource. */
export const operatorActionsByResource = {
  packages: [], releases: [], certification: ['approve'], products: [], organisations: ['pause', 'resume'], subscriptions: ['compensate'], 'provisioning-jobs': ['retry'], instances: ['pause', 'resume'], bindings: ['pause', 'resume'], deployments: ['canary', 'promote', 'rollback'], executions: [], health: [], incidents: ['acknowledge', 'resolve'], maintenance: ['retry', 'resolve'], 'librarian-candidates': ['approve', 'reject', 'supersede'], 'audit-evidence': [],
} as const satisfies Record<OperatorResource, readonly OperatorAction[]>;
/** Returns whether an action is valid for the addressed finite resource. */
export function isOperatorActionAllowed(resource: OperatorResource, action: OperatorAction) { return (operatorActionsByResource[resource] as readonly OperatorAction[]).includes(action); }
export type SafeRecord = { id: string; orgId?: string; state?: string; status?: string; version?: number; summary?: string; evidenceRef?: string; updatedAt?: string; correlationId?: string; auditReference?: string; [key: string]: unknown };
export type ApiError = { code: string; message: string; correlationId: string };
export type ApiResult<T> = { state: 'ready'; value: T } | { state: 'unavailable' | 'stale' | 'failed' | 'denied'; error: ApiError };
export interface ProductApiTransport { get(path: string): Promise<unknown>; post(path: string, body: unknown): Promise<unknown>; }
function error(value: unknown): ApiResult<never> { const item = value as { error?: Partial<ApiError> }; return { state: item.error?.code === 'forbidden' || item.error?.code === 'approval_required' ? 'denied' : 'failed', error: { code: item.error?.code ?? 'api_unavailable', message: item.error?.message ?? 'The Product API is unavailable; no action was attempted.', correlationId: item.error?.correlationId ?? 'unavailable' } }; }
function records(value: unknown): ApiResult<SafeRecord[]> { const item = value as { items?: SafeRecord[]; error?: unknown }; return Array.isArray(item.items) ? { state: 'ready', value: item.items.map(redact) } : error(item); }
function redact(record: SafeRecord): SafeRecord { const safe = { ...record }; if (/secret|token|password|authorization|workflow\s*json/i.test(JSON.stringify(safe))) return { id: safe.id, status: 'redacted', summary: '[redacted]' }; return safe; }
export class ProductApiClient {
  constructor(private readonly transport: ProductApiTransport) {}
  async list(resource: OperatorResource): Promise<ApiResult<SafeRecord[]>> { try { return records(await this.transport.get(`/v1/operator/${resource}?limit=25`)); } catch { return error(undefined); } }
  async action(resource: OperatorResource, id: string, input: { action: OperatorAction; reason: string; idempotencyKey: string; expectedVersion?: number }): Promise<ApiResult<SafeRecord>> { try { const response = await this.transport.post(`/v1/operator/${resource}/${encodeURIComponent(id)}/actions`, input) as SafeRecord & { error?: unknown }; return typeof response.id === 'string' ? { state: 'ready', value: redact(response) } : error(response); } catch { return error(undefined); } }
}
