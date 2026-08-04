import { createHmac, createPublicKey, timingSafeEqual, verify as verifySignature } from 'node:crypto';
import express, { type NextFunction, type Request, type Response } from 'express';
import rateLimit from 'express-rate-limit';
import { ZodError } from 'zod';
import { actionSchema, clientConfigurationSchema, clientOrderSchema, clientProvisioningSchema, clientSubscriptionSchema, clientSupportSchema, clientTermsSchema, errorEnvelopeSchema, openApiDocument, operatorActionSchema, operatorProductSchema, operatorResourceSchema, pageSchema, platformIdentitySchema, productUpdateSchema, webhookSchema, type OperatorResource, type PlatformIdentity, type ProductRole } from './contracts.js';
import { hasRole, type AuditReservationInput, type ProductApiService } from './service.js';

export type ProductApiEnv = { nodeEnv: 'test' | 'development' | 'production'; issuer: string; audience: string; testJwtSecret?: string; webhookSecret?: string; maxBodyBytes?: number; platformJwksUrl?: string; sessionActive?: (subject: string, sessionId?: string) => Promise<boolean>; publicClientOrigin?: string; operatorConsoleOrigin?: string };
export class ProductApiError extends Error { constructor(readonly status: number, readonly code: string, message: string) { super(message); } }
type AuditedRequest = Request & { identity?: PlatformIdentity; correlationId?: string; auditMeta?: { action: string; resource: string; reason: string }; auditLease?: Awaited<ReturnType<ProductApiService['reserveAudit']>> };
function correlation(req: AuditedRequest) { return req.correlationId ?? (req.correlationId = req.header('x-correlation-id')?.slice(0, 128) || crypto.randomUUID()); }
function auditReason(req: Request): string { return typeof req.body?.reason === 'string' ? req.body.reason.slice(0, 280) : 'privileged read'; }
function auditFailure(req: AuditedRequest): ProductApiError { return new ProductApiError(503, 'audit_unavailable', `Privileged request could not be processed safely (${correlation(req)})`); }
function auditOutcome(status: number): 'allowed' | 'denied' { return status >= 200 && status < 400 ? 'allowed' : 'denied'; }
function fail(res: Response, req: AuditedRequest, error: unknown) { const known = error instanceof ProductApiError ? error : error instanceof ZodError ? new ProductApiError(400, 'validation_failed', 'Request validation failed') : error instanceof Error && error.message === 'not_found' ? new ProductApiError(404, 'not_found', 'Resource was not found') : error instanceof Error && error.message === 'concurrency_conflict' ? new ProductApiError(409, 'concurrency_conflict', 'The resource changed; refresh and retry') : error instanceof Error && error.message === 'invalid_cursor' ? new ProductApiError(400, 'invalid_cursor', 'Pagination cursor is invalid') : error instanceof Error && (error.message === 'invalid_transition' || error.message === 'terms_mismatch') ? new ProductApiError(400, error.message, error.message === 'terms_mismatch' ? 'Terms do not match the authoritative order snapshot' : 'That action is not valid for the resource state') : error instanceof Error && error.message === 'provider_event_out_of_order' ? new ProductApiError(409, 'provider_event_out_of_order', 'The provider event is stale or out of order') : new ProductApiError(500, 'internal_error', 'Request could not be processed'); const body = { error: { code: known.code, message: known.message, correlationId: correlation(req) } }; errorEnvelopeSchema.parse(body); res.status(known.status).json(body); }

/** Local HS256 issuer is test-only; production has no bypass and must inject a live JWT/JWKS verifier. */
export function localTestIdentity(env: ProductApiEnv, req: Request): PlatformIdentity {
  if (env.nodeEnv !== 'test' || !env.testJwtSecret) throw new ProductApiError(503, 'identity_unavailable', 'Live Platform identity conformance is not configured');
  const token = req.header('authorization')?.replace(/^Bearer\s+/, ''); const parts = token?.split('.') ?? [];
  if (parts.length !== 3) throw new ProductApiError(401, 'unauthenticated', 'Authentication is required');
  const [header, payload, signature] = parts;
  let decodedHeader: { alg?: string; typ?: string }; let decodedPayload: unknown;
  try { decodedHeader = JSON.parse(Buffer.from(header, 'base64url').toString()) as { alg?: string; typ?: string }; decodedPayload = JSON.parse(Buffer.from(payload, 'base64url').toString()); } catch { throw new ProductApiError(401, 'invalid_token', 'Authentication token is invalid'); }
  if (decodedHeader.alg !== 'HS256' || decodedHeader.typ !== 'JWT') throw new ProductApiError(401, 'invalid_token', 'Authentication token is invalid');
  const expected = createHmac('sha256', env.testJwtSecret).update(`${header}.${payload}`).digest(); const supplied = Buffer.from(signature, 'base64url');
  if (expected.length !== supplied.length || !timingSafeEqual(expected, supplied)) throw new ProductApiError(401, 'invalid_token', 'Authentication token is invalid');
  let identity: PlatformIdentity; try { identity = platformIdentitySchema.parse(decodedPayload); } catch { throw new ProductApiError(401, 'invalid_token', 'Authentication token is invalid'); } const audiences = Array.isArray(identity.aud) ? identity.aud : [identity.aud];
  if (identity.iss !== env.issuer || !audiences.includes(env.audience) || identity.exp <= Math.floor(Date.now() / 1000) || (identity.nbf !== undefined && identity.nbf > Math.floor(Date.now() / 1000))) throw new ProductApiError(401, 'invalid_token', 'Authentication token is invalid'); return identity;
}

/** Production verifier accepts only governed RS256/JWKS tokens and a positive session check. */
export async function platformIdentity(env: ProductApiEnv, req: Request): Promise<PlatformIdentity> {
  if (env.nodeEnv === 'test') return localTestIdentity(env, req);
  if (!env.platformJwksUrl || !env.sessionActive) throw new ProductApiError(503, 'identity_unavailable', 'Live Platform identity conformance is not configured');
  const token = req.header('authorization')?.replace(/^Bearer\s+/, ''); const parts = token?.split('.') ?? []; if (parts.length !== 3) throw new ProductApiError(401, 'unauthenticated', 'Authentication is required');
  const [header, payload, signature] = parts; let meta: { alg?: string; typ?: string; kid?: string }; let raw: unknown; try { meta = JSON.parse(Buffer.from(header, 'base64url').toString()) as { alg?: string; typ?: string; kid?: string }; raw = JSON.parse(Buffer.from(payload, 'base64url').toString()); } catch { throw new ProductApiError(401, 'invalid_token', 'Authentication token is invalid'); }
  if (meta.alg !== 'RS256' || meta.typ !== 'JWT' || !meta.kid) throw new ProductApiError(401, 'invalid_token', 'Authentication token is invalid');
  let jwks: { keys?: Array<JsonWebKey & { kid?: string; use?: string; kty?: string }> }; try { const response = await fetch(env.platformJwksUrl, { headers: { accept: 'application/json' } }); if (!response.ok) throw new Error(); jwks = await response.json() as typeof jwks; } catch { throw new ProductApiError(503, 'identity_unavailable', 'Live Platform identity verifier is unavailable'); }
  const key = jwks.keys?.find((item) => item.kid === meta.kid && item.kty === 'RSA' && item.use === 'sig'); if (!key || !verifySignature('RSA-SHA256', Buffer.from(`${header}.${payload}`), createPublicKey({ key: key as unknown as import('node:crypto').JsonWebKey, format: 'jwk' }), Buffer.from(signature, 'base64url'))) throw new ProductApiError(401, 'invalid_token', 'Authentication token is invalid');
  let identity: PlatformIdentity; try { identity = platformIdentitySchema.parse(raw); } catch { throw new ProductApiError(401, 'invalid_token', 'Authentication token is invalid'); } const audiences = Array.isArray(identity.aud) ? identity.aud : [identity.aud]; const now = Math.floor(Date.now() / 1000); if (identity.iss !== env.issuer || !audiences.includes(env.audience) || identity.exp <= now || (identity.nbf !== undefined && identity.nbf > now) || !(await env.sessionActive(identity.sub, identity.jti))) throw new ProductApiError(401, 'invalid_token', 'Authentication token is invalid'); return identity;
}

export function createProductApi(env: ProductApiEnv, service: ProductApiService, identityVerifier: (request: Request) => Promise<PlatformIdentity> | PlatformIdentity = (req) => platformIdentity(env, req)) {
  const app = express(); app.disable('x-powered-by');
  const allowedOrigins = [env.publicClientOrigin, env.operatorConsoleOrigin].filter((value): value is string => Boolean(value));
  if (env.nodeEnv === 'production' && allowedOrigins.length !== 2) throw new Error('Product API exact browser origins are required in production');
  app.use((req, res, next) => { const origin = req.header('origin'); if (!origin) return next(); if (!allowedOrigins.includes(origin)) return next(new ProductApiError(403, 'origin_forbidden', 'Browser origin is not authorised')); res.setHeader('access-control-allow-origin', origin); res.setHeader('vary', 'Origin'); res.setHeader('access-control-allow-methods', 'GET,POST,PATCH,OPTIONS'); res.setHeader('access-control-allow-headers', 'authorization,content-type,if-match,x-correlation-id,x-link-webhook-signature'); if (req.method === 'OPTIONS') return res.sendStatus(204); return next(); });
  app.use((req, res, next) => { const request = req as AuditedRequest; const id = correlation(request); res.setHeader('x-correlation-id', id); res.setHeader('x-audit-reference', id); next(); });
  /* Must precede JSON parsing: provider HMAC covers the exact transmitted bytes. */
  app.post('/v1/webhooks/status', express.raw({ type: 'application/json', limit: env.maxBodyBytes ?? '32kb' }), async (req, res, next) => { try { if (!env.webhookSecret) throw new ProductApiError(503, 'webhook_unavailable', 'Webhook verification is not configured'); const raw = Buffer.isBuffer(req.body) ? req.body : Buffer.alloc(0); const signature = req.header('x-link-webhook-signature'); const expected = createHmac('sha256', env.webhookSecret).update(raw).digest('hex'); if (!signature || signature.length !== expected.length || !timingSafeEqual(Buffer.from(signature), Buffer.from(expected))) throw new ProductApiError(401, 'invalid_webhook', 'Webhook signature is invalid'); const event = webhookSchema.parse(JSON.parse(raw.toString('utf8'))); const receipt = await service.receiveWebhook(event); res.status(202).json({ accepted: true, replay: receipt.replay, state: receipt.state, providerSequence: receipt.providerSequence, occurredAt: receipt.occurredAt }); } catch (error) { next(error); } });
  app.use(express.json({ limit: env.maxBodyBytes ?? '32kb' })); app.use(rateLimit({ windowMs: 60_000, max: 120, standardHeaders: true, legacyHeaders: false }));
  const identity = (roles: ProductRole[]) => async (req: Request, _res: Response, next: NextFunction) => {
    try {
      const request = req as AuditedRequest;
      const actor = await identityVerifier(req);
      request.identity = actor;
      if (!hasRole(actor.roles, roles)) {
        await service.recordDeniedAudit({ actor: actor.sub, orgId: actor.org_id, resource: 'product-api.route', action: 'authorization.denied', reason: 'authenticated role is not authorised', correlationId: correlation(request) }).catch(() => undefined);
        throw new ProductApiError(403, 'forbidden', 'This role is not authorised for the resource');
      }
      next();
    } catch (error) { next(error); }
  };
  const audited = (action: string, resource: (req: Request) => string) => async (req: Request, res: Response, next: NextFunction) => {
    const request = req as AuditedRequest;
    const actor = request.identity;
    if (!actor) return next(new ProductApiError(401, 'unauthenticated', 'Authentication is required'));
    const meta = { action, resource: resource(req), reason: auditReason(req) };
    request.auditMeta = meta;
    const input: AuditReservationInput = { actor: actor.sub, orgId: actor.org_id, ...meta, correlationId: correlation(request) };
    try {
      request.auditLease = await service.reserveAudit(input);
    } catch {
      return next(auditFailure(request));
    }
    const originalEnd = res.end.bind(res);
    let committed = false;
    res.end = ((...args: any[]) => {
      if (committed) return res;
      committed = true;
      void service.finalizeAudit(request.auditLease!, auditOutcome(res.statusCode)).then(() => originalEnd(...args)).catch(() => {
        if (res.headersSent) return originalEnd(...args);
        const body = JSON.stringify({ error: { code: 'audit_unavailable', message: `Privileged request could not be completed durably (${correlation(request)})`, correlationId: correlation(request) } });
        res.statusCode = 503;
        res.setHeader('content-type', 'application/json; charset=utf-8');
        res.setHeader('content-length', Buffer.byteLength(body));
        return originalEnd(body, 'utf8');
      });
      return res;
    }) as typeof res.end;
    next();
  };
  app.get('/openapi.json', (_req, res) => res.json(openApiDocument));
  app.get('/v1/public/products', async (req, res, next) => { try { res.json(await service.publishedProducts(pageSchema.parse(req.query))); } catch (error) { next(error); } });
  app.get('/v1/public/signup-prerequisites', (_req, res) => res.json({ configuration: 'operator_assisted_required', credentialIntake: 'not_available' }));
  app.get('/v1/client/instances', identity(['client_member', 'client_admin']), audited('client.instances.read', () => 'instances'), async (req, res, next) => { try { const request = req as AuditedRequest; res.json(await service.clientInstances((request.identity as PlatformIdentity).org_id, pageSchema.parse(req.query), request.auditLease)); } catch (error) { next(error); } });
  app.post('/v1/client/instances/:id/actions', identity(['client_member', 'client_admin']), audited('client.instance.transition', (req) => `instance:${req.params.id}`), async (req, res, next) => { try { const input = actionSchema.parse(req.body); const request = req as AuditedRequest; const actor = request.identity as PlatformIdentity; res.json(await service.transitionInstance({ orgId: actor.org_id, actor: actor.sub, instanceId: req.params.id, ...input }, request.auditLease)); } catch (error) { next(error); } });
  app.post('/v1/operator/products', identity(['operator', 'approver']), audited('operator.product.create', () => 'product'), async (req, res, next) => { try { const input = operatorProductSchema.parse(req.body); const request = req as AuditedRequest; const actor = request.identity as PlatformIdentity; res.status(201).json(await service.createProduct({ actor: actor.sub, ...input }, request.auditLease)); } catch (error) { next(error); } });
  app.patch('/v1/operator/products/:id', identity(['operator', 'approver']), audited('operator.product.update', (req) => `product:${req.params.id}`), async (req, res, next) => { try { const input = productUpdateSchema.parse(req.body); const expectedVersion = Number.parseInt(req.header('if-match') ?? '', 10); if (!Number.isSafeInteger(expectedVersion) || expectedVersion < 1) throw new ProductApiError(428, 'precondition_required', 'An If-Match version is required'); const request = req as AuditedRequest; const actor = request.identity as PlatformIdentity; res.json(await service.updateProduct({ actor: actor.sub, id: req.params.id, expectedVersion, ...input }, request.auditLease)); } catch (error) { next(error); } });
  const clientAreas = ['subscriptions', 'orders', 'configuration', 'provisioning', 'supportRequests'] as const;
  for (const area of clientAreas) app.get(`/v1/client/${area === 'supportRequests' ? 'support-requests' : area}`, identity(['client_member', 'client_admin']), audited(`client.${area}.read`, () => area), async (req, res, next) => { try { const request = req as AuditedRequest; const actor = request.identity as PlatformIdentity; res.json(await service.clientPortal(actor.org_id, area, pageSchema.parse(req.query), request.auditLease)); } catch (error) { next(error); } });
  app.post('/v1/client/support-requests', identity(['client_member', 'client_admin']), audited('client.support.create', () => 'support-request'), async (req, res, next) => { try { const input = clientSupportSchema.parse(req.body); const request = req as AuditedRequest; const actor = request.identity as PlatformIdentity; res.status(201).json(await service.createSupportRequest({ orgId: actor.org_id, actor: actor.sub, ...input }, request.auditLease)); } catch (error) { next(error); } });
  app.post('/v1/client/orders', identity(['client_member', 'client_admin']), audited('client.order.create', () => 'order'), async (req, res, next) => { try { const input = clientOrderSchema.parse(req.body); const request = req as AuditedRequest; const actor = request.identity as PlatformIdentity; res.status(201).json(await service.createOrder({ orgId: actor.org_id, actor: actor.sub, ...input }, request.auditLease)); } catch (error) { next(error); } });
  app.post('/v1/client/orders/:id/terms', identity(['client_member', 'client_admin']), audited('client.terms.accept', (req) => `order:${req.params.id}`), async (req, res, next) => { try { const input = clientTermsSchema.parse({ ...req.body, orderId: req.params.id }); const request = req as AuditedRequest; const actor = request.identity as PlatformIdentity; res.status(201).json(await service.acceptTerms({ orgId: actor.org_id, actor: actor.sub, ...input }, request.auditLease)); } catch (error) { next(error); } });
  app.post('/v1/client/subscriptions', identity(['client_member', 'client_admin']), audited('client.subscription.create', () => 'subscription'), async (req, res, next) => { try { const input = clientSubscriptionSchema.parse(req.body); const request = req as AuditedRequest; const actor = request.identity as PlatformIdentity; res.status(201).json(await service.createSubscription({ orgId: actor.org_id, actor: actor.sub, ...input }, request.auditLease)); } catch (error) { next(error); } });
  app.post('/v1/client/configuration', identity(['client_member', 'client_admin']), audited('client.configuration.submit', () => 'configuration'), async (req, res, next) => { try { const input = clientConfigurationSchema.parse(req.body); const request = req as AuditedRequest; const actor = request.identity as PlatformIdentity; res.status(202).json(await service.submitConfiguration({ orgId: actor.org_id, actor: actor.sub, ...input }, request.auditLease)); } catch (error) { next(error); } });
  app.post('/v1/client/provisioning', identity(['client_member', 'client_admin']), audited('client.provisioning.request', () => 'provisioning'), async (req, res, next) => { try { const input = clientProvisioningSchema.parse(req.body); const request = req as AuditedRequest; const actor = request.identity as PlatformIdentity; res.status(202).json(await service.requestProvisioning({ orgId: actor.org_id, actor: actor.sub, ...input }, request.auditLease)); } catch (error) { next(error); } });
  const operatorResources = operatorResourceSchema.options;
  for (const resource of operatorResources) {
    app.get(`/v1/operator/${resource}`, identity(['operator', 'approver']), audited(`operator.${resource}.read`, () => resource), async (req, res, next) => { try { const request = req as AuditedRequest; res.json(await service.operatorRecords(resource, pageSchema.parse(req.query), request.auditLease)); } catch (error) { next(error); } });
    app.post(`/v1/operator/${resource}/:id/actions`, identity(['operator', 'approver']), audited(`operator.${resource}.action`, (req) => `${resource}:${req.params.id}`), async (req, res, next) => { try { const input = operatorActionSchema.parse(req.body); const request = req as AuditedRequest; const actor = request.identity as PlatformIdentity; if (['promote', 'approve'].includes(input.action) && !actor.roles.includes('approver')) throw new ProductApiError(403, 'approval_required', 'A separate authorised approver role is required'); res.json(await service.operatorAction({ actor: actor.sub, resource: resource as OperatorResource, id: req.params.id, ...input }, request.auditLease)); } catch (error) { next(error); } });
  }
  app.use((error: unknown, req: Request, res: Response, _next: NextFunction) => fail(res, req, error)); return app;
}
