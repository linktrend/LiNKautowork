import { z } from 'zod';

export const productRoleSchema = z.enum(['visitor', 'client_member', 'client_admin', 'operator', 'approver']);
export type ProductRole = z.infer<typeof productRoleSchema>;
export const platformIdentitySchema = z.object({ sub: z.string().min(1).max(200), org_id: z.string().uuid(), roles: z.array(productRoleSchema).min(1), iss: z.string(), aud: z.union([z.string(), z.array(z.string())]), exp: z.number().int(), nbf: z.number().int().optional(), jti: z.string().min(8).max(200).optional() }).strict();
export type PlatformIdentity = z.infer<typeof platformIdentitySchema>;

export const errorEnvelopeSchema = z.object({ error: z.object({ code: z.string(), message: z.string(), correlationId: z.string() }) });
export const actionSchema = z.object({ action: z.enum(['pause', 'resume']), reason: z.string().min(3).max(280), idempotencyKey: z.string().min(8).max(128) }).strict();
export const operatorProductSchema = z.object({ name: z.string().min(3).max(120), summary: z.string().min(3).max(500), version: z.number().int().positive(), reason: z.string().min(3).max(280), idempotencyKey: z.string().min(8).max(128) }).strict();
export const productUpdateSchema = z.object({ summary: z.string().min(3).max(500), reason: z.string().min(3).max(280), idempotencyKey: z.string().min(8).max(128) }).strict();
export const webhookSchema = z.object({ eventId: z.string().min(8).max(160), eventType: z.enum(['payment.succeeded', 'payment.failed', 'payment.refunded', 'provisioning.completed', 'provisioning.failed']), occurredAt: z.string().datetime(), providerSequence: z.number().int().positive(), orgId: z.string().uuid(), subscriptionId: z.string().uuid() }).strict();
export const pageSchema = z.object({ limit: z.coerce.number().int().min(1).max(100).default(25), cursor: z.string().max(200).optional() }).strict();
export const operatorResourceSchema = z.enum(['packages', 'releases', 'certification', 'products', 'organisations', 'subscriptions', 'provisioning-jobs', 'instances', 'bindings', 'deployments', 'executions', 'health', 'incidents', 'maintenance', 'librarian-candidates', 'audit-evidence']);
export type OperatorResource = z.infer<typeof operatorResourceSchema>;
/** A finite resource-specific command vocabulary.  A route is never a generic state setter. */
export const operatorActionsByResource = {
  packages: [], releases: [], certification: ['approve'], products: [], organisations: ['pause', 'resume'], subscriptions: ['compensate'], 'provisioning-jobs': ['retry'], instances: ['pause', 'resume'], bindings: ['pause', 'resume'], deployments: ['canary', 'promote', 'rollback'], executions: [], health: [], incidents: ['acknowledge', 'resolve'], maintenance: ['retry', 'resolve'], 'librarian-candidates': ['approve', 'reject', 'supersede'], 'audit-evidence': [],
} as const satisfies Record<OperatorResource, readonly string[]>;
export function isOperatorActionAllowed(resource: OperatorResource, action: string): boolean { return (operatorActionsByResource[resource] as readonly string[]).includes(action); }
export const operatorResourcePaths = operatorResourceSchema.options.map((resource) => `/v1/operator/${resource}` as const);
export const clientSupportSchema = z.object({ subject: z.string().min(3).max(160), message: z.string().min(3).max(2000), idempotencyKey: z.string().min(8).max(128) }).strict();
export const clientOrderSchema = z.object({ productId: z.string().min(3).max(120), idempotencyKey: z.string().min(8).max(128) }).strict();
export const clientTermsSchema = z.object({ orderId: z.string().uuid(), termsDocumentId: z.string().min(1).max(160), termsVersion: z.string().min(1).max(128), termsDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/) }).strict();
export const clientSubscriptionSchema = z.object({ orderId: z.string().min(3).max(120), idempotencyKey: z.string().min(8).max(128) }).strict();
export const clientConfigurationSchema = z.object({ subscriptionId: z.string().min(3).max(120), values: z.record(z.string().max(128), z.union([z.string().max(500), z.number().finite(), z.boolean()])).refine((values) => !Object.keys(values).some((key) => /secret|token|password|credential|api[_-]?key/i.test(key)), 'Credential values require operator-assisted configuration'), idempotencyKey: z.string().min(8).max(128) }).strict();
export const clientProvisioningSchema = z.object({ subscriptionId: z.string().min(3).max(120), idempotencyKey: z.string().min(8).max(128) }).strict();
export const operatorActionSchema = z.object({ action: z.enum(['retry', 'compensate', 'pause', 'resume', 'acknowledge', 'resolve', 'canary', 'promote', 'rollback', 'approve', 'reject', 'supersede']), reason: z.string().min(3).max(280), idempotencyKey: z.string().min(8).max(128), expectedVersion: z.number().int().positive().optional() }).strict();

/** Generated OpenAPI source kept with the typed boundary and checked by tests. */
export const openApiDocument = {
  openapi: '3.1.0', info: { title: 'LiNKautowork Product API', version: '1.0.0' },
  paths: {
    '/v1/public/products': { get: { summary: 'Approved commercial product summaries only' } },
    '/v1/client/instances': { get: { security: [{ platformBearer: [] }] } },
    '/v1/client/instances/{id}/actions': { post: { security: [{ platformBearer: [] }] } },
    '/v1/operator/products': { post: { security: [{ platformBearer: [] }] } },
    '/v1/operator/products/{id}': { patch: { security: [{ platformBearer: [] }], parameters: [{ name: 'if-match', in: 'header', required: true }] } },
    '/v1/operator/{resource}': { get: { security: [{ platformBearer: [] }], summary: 'Finite documented operator resource list; never a table proxy.' } },
    '/v1/client/subscriptions': { get: { security: [{ platformBearer: [] }] } },
    '/v1/client/orders': { get: { security: [{ platformBearer: [] }] }, post: { security: [{ platformBearer: [] }], summary: 'Creates an order intent only; never charges a payment method.' } },
    '/v1/client/orders/{id}/terms': { post: { security: [{ platformBearer: [] }], summary: 'Records an exact authoritative document/version/digest acceptance before subscription.' } },
    '/v1/client/configuration': { get: { security: [{ platformBearer: [] }] } },
    '/v1/client/provisioning': { get: { security: [{ platformBearer: [] }] } },
    '/v1/client/support-requests': { get: { security: [{ platformBearer: [] }] }, post: { security: [{ platformBearer: [] }] } },
    '/v1/webhooks/status': { post: { summary: 'Signed allow-listed provider status event' } },
  },
  components: { securitySchemes: { platformBearer: { type: 'http', scheme: 'bearer', bearerFormat: 'JWT' } } },
} as const;
