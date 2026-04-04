import express, { type NextFunction, type Request, type Response } from 'express';
import { z } from 'zod';
import type { AppEnv } from './config/env.js';
import {
  eventPublishSchema,
  globalKillSwitchSchema,
  ingressRequestSchema,
  lifecycleTransitionSchema,
  scopedKillSwitchSchema,
} from './contracts/types.js';
import { N8nClient } from './integrations/n8n-client.js';
import { NatsPublisher } from './integrations/nats-client.js';
import { SecretsProvider } from './integrations/secrets-provider.js';
import { SupabaseAuditClient } from './integrations/supabase-rpc.js';
import { HttpError } from './lib/http-error.js';
import { logWarn } from './lib/logger.js';
import { NonceStore } from './lib/nonce-store.js';
import { verifySlackSignature } from './lib/slack.js';
import { assertCanonicalTenant } from './lib/tenant.js';
import { requireControlToken, requireInternalServiceToken, requireSignedIngress } from './middleware/auth.js';
import { captureRawBody, ensureRawBody } from './middleware/raw-body.js';
import { AuditService } from './services/audit.js';
import { EventBridgeService } from './services/event-bridge.js';
import { KillSwitchService } from './services/killswitch.js';
import { type LifecycleApprovals, validateLifecycleTransition } from './services/lifecycle.js';
import { executionOutcome, getMetricsRegistry, ingressLatencyMs, killSwitchEvents } from './services/metrics.js';

function parseSchema<T>(schema: z.ZodType<T>, input: unknown): T {
  try {
    return schema.parse(input);
  } catch (error) {
    if (error instanceof z.ZodError) {
      throw new HttpError(400, error.issues.map((issue) => issue.message).join('; '));
    }
    throw error;
  }
}

function normalizeApprovals(approvals: Partial<LifecycleApprovals> | undefined): LifecycleApprovals {
  return {
    auditorRecommendation: approvals?.auditorRecommendation ?? false,
    headOfQualityApproved: approvals?.headOfQualityApproved ?? false,
    cooApproved: approvals?.cooApproved ?? false,
    chairmanApproved: approvals?.chairmanApproved ?? false,
  };
}

function createRateLimiter(options: { limit: number; windowMs: number }) {
  const buckets = new Map<string, { count: number; resetAt: number }>();

  return (req: Request, res: Response, next: NextFunction) => {
    const now = Date.now();
    const key = `${req.path}:${req.ip ?? req.socket.remoteAddress ?? 'unknown'}`;
    const bucket = buckets.get(key);

    if (!bucket || bucket.resetAt <= now) {
      buckets.set(key, { count: 1, resetAt: now + options.windowMs });
      next();
      return;
    }

    if (bucket.count >= options.limit) {
      const retryAfter = Math.max(1, Math.ceil((bucket.resetAt - now) / 1000));
      res.setHeader('Retry-After', String(retryAfter));
      res.status(429).json({ error: 'rate_limit_exceeded' });
      return;
    }

    bucket.count += 1;
    next();
  };
}

export type AppDeps = {
  env: AppEnv;
  nonceStore: NonceStore;
  n8nClient: N8nClient;
  natsPublisher: NatsPublisher;
  secretsProvider: SecretsProvider;
  auditService: AuditService;
  eventBridgeService: EventBridgeService;
  killSwitchService: KillSwitchService;
};

export function buildDependencies(env: AppEnv): AppDeps {
  const nonceStore = new NonceStore(env.REPLAY_WINDOW_SECONDS);
  const n8nClient = new N8nClient(env);
  const natsPublisher = new NatsPublisher(env);
  const secretsProvider = new SecretsProvider(env);
  const auditService = new AuditService(new SupabaseAuditClient(env));
  const eventBridgeService = new EventBridgeService(env, natsPublisher);
  const killSwitchService = new KillSwitchService(n8nClient);

  return {
    env,
    nonceStore,
    n8nClient,
    natsPublisher,
    secretsProvider,
    auditService,
    eventBridgeService,
    killSwitchService,
  };
}

export function createApp(deps: AppDeps) {
  const app = express();
  const ingressRateLimiter = createRateLimiter({ limit: 120, windowMs: 60_000 });
  const slackRateLimiter = createRateLimiter({ limit: 60, windowMs: 60_000 });

  app.disable('x-powered-by');
  app.use((_req, res, next) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('X-Frame-Options', 'DENY');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader('Permissions-Policy', 'geolocation=(), microphone=(), camera=()');
    res.setHeader('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'");
    next();
  });

  app.use(express.json({ limit: '2mb', verify: captureRawBody }));
  app.use(express.urlencoded({ extended: true, verify: captureRawBody }));
  app.use(ensureRawBody);

  app.get('/health', (_req, res) => {
    res.json({
      status: 'ok',
      tenantUuid: deps.env.ACTIVE_TENANT_UUID,
      tenantSlug: deps.env.ACTIVE_TENANT_SLUG,
      killSwitch: deps.killSwitchService.snapshot(),
    });
  });

  app.get('/metrics', async (_req, res) => {
    res.setHeader('content-type', getMetricsRegistry().contentType);
    res.send(await getMetricsRegistry().metrics());
  });

  app.post(
    '/v1/ingress/:workflowId',
    ingressRateLimiter,
    requireSignedIngress(deps.env, deps.nonceStore),
    async (req, res, next) => {
    const start = performance.now();
    try {
      const body = parseSchema(ingressRequestSchema, req.body);
      const workflowId = req.params.workflowId || body.workflow.id;

      assertCanonicalTenant(body.mission.tenantId, deps.env.ACTIVE_TENANT_UUID);

      const blocked = deps.killSwitchService.isBlocked(body.mission.tenantId, workflowId);
      if (blocked.blocked) {
        throw new HttpError(503, `${blocked.scope} kill switch active: ${blocked.reason}`);
      }

      const jitSecrets = await deps.secretsProvider.getSecrets(body.requiredSecrets ?? []);
      const dispatchBody = {
        mission: body.mission,
        payload: body.payload ?? {},
        idempotencyKey: body.idempotencyKey,
        jitSecrets,
      };

      const webhookPath = body.workflow.path ?? workflowId;
      const dispatch = await deps.n8nClient.triggerWebhook(
        webhookPath,
        body.workflow.method ?? 'POST',
        dispatchBody,
      );
      const latencyMs = Math.round(performance.now() - start);
      ingressLatencyMs.observe(latencyMs);

      const statusLabel = dispatch.status >= 200 && dispatch.status < 300 ? 'success' : 'failure';
      executionOutcome.inc({ criticality: body.workflow.criticality, status: statusLabel });

      await deps.auditService.writeRunAudit({
        mission: body.mission,
        status: statusLabel,
        tokenUsage: 0,
        commandLog: {
          gateway_service: req.linkService,
          workflow_id: workflowId,
          webhook_path: webhookPath,
        },
        details: {
          automation_workflow_id: workflowId,
          trigger_source: body.mission.triggerSource,
          latency_ms: latencyMs,
          retries: 0,
          error_reason: statusLabel === 'failure' ? 'dispatch_failure' : null,
          response_status: dispatch.status,
        },
      });

      await deps.eventBridgeService.publish({
        eventType: 'workflow.execution',
        mission: body.mission,
        payload: {
          workflowId,
          webhookPath,
          statusCode: dispatch.status,
          latencyMs,
          idempotencyKey: body.idempotencyKey,
        },
        status: statusLabel,
      });

      res.status(dispatch.status).json({
        workflowId,
        status: statusLabel,
        dispatch: dispatch.body,
      });
    } catch (error) {
      next(error);
    }
    },
  );

  app.post('/v1/events/publish', requireInternalServiceToken(deps.env), async (req, res, next) => {
    try {
      const body = parseSchema(eventPublishSchema, req.body);
      assertCanonicalTenant(body.mission.tenantId, deps.env.ACTIVE_TENANT_UUID);

      await deps.eventBridgeService.publish({
        eventType: body.eventType,
        mission: body.mission,
        payload: body.payload ?? {},
        status: body.status ?? 'ok',
      });

      await deps.auditService.writeRunAudit({
        mission: body.mission,
        status: 'event_published',
        tokenUsage: 0,
        commandLog: { publisher_service: req.linkService },
        details: {
          automation_workflow_id: 'event_bridge',
          trigger_source: body.mission.triggerSource,
          latency_ms: 0,
          retries: 0,
          error_reason: null,
          event_type: body.eventType,
        },
      });

      res.status(202).json({ accepted: true });
    } catch (error) {
      next(error);
    }
  });

  app.post('/v1/lifecycle/transition', requireControlToken(deps.env), async (req, res, next) => {
    try {
      const body = parseSchema(lifecycleTransitionSchema, req.body);
      assertCanonicalTenant(body.mission.tenantId, deps.env.ACTIVE_TENANT_UUID);

      validateLifecycleTransition({
        fromState: body.fromState,
        toState: body.toState,
        protectedAction: body.protectedAction ?? false,
        approvals: normalizeApprovals(body.approvals),
      });

      await deps.eventBridgeService.publish({
        eventType: 'lifecycle.transition',
        mission: body.mission,
        payload: {
          workflowId: body.workflowId,
          fromState: body.fromState,
          toState: body.toState,
          protectedAction: body.protectedAction ?? false,
        },
        status: 'approved',
      });

      await deps.auditService.writeRunAudit({
        mission: body.mission,
        status: 'lifecycle_transition',
        tokenUsage: 0,
        commandLog: { route: '/v1/lifecycle/transition' },
        details: {
          automation_workflow_id: body.workflowId,
          trigger_source: body.mission.triggerSource,
          latency_ms: 0,
          retries: 0,
          error_reason: null,
          from_state: body.fromState,
          to_state: body.toState,
          protected_action: body.protectedAction ?? false,
        },
      });

      res.status(200).json({ accepted: true });
    } catch (error) {
      next(error);
    }
  });

  app.post('/v1/control/killswitch/scoped', requireControlToken(deps.env), async (req, res, next) => {
    try {
      const body = parseSchema(scopedKillSwitchSchema, req.body);
      assertCanonicalTenant(body.mission.tenantId, deps.env.ACTIVE_TENANT_UUID);

      if (body.action === 'activate') {
        deps.killSwitchService.activateScoped({
          tenantId: body.mission.tenantId,
          workflowId: body.workflowId,
          reason: body.reason,
          incidentId: body.incidentId,
          mission: body.mission,
        });
        killSwitchEvents.inc({ scope: 'scoped', action: 'activate' });
      } else {
        deps.killSwitchService.releaseScoped(body.mission.tenantId, body.workflowId);
        killSwitchEvents.inc({ scope: 'scoped', action: 'release' });
      }

      await deps.eventBridgeService.publish({
        eventType: 'killswitch',
        mission: body.mission,
        payload: {
          scope: 'scoped',
          action: body.action,
          workflowId: body.workflowId,
          incidentId: body.incidentId,
          reason: body.reason,
        },
        status: body.action,
      });

      res.status(200).json({
        accepted: true,
        killSwitch: deps.killSwitchService.snapshot(),
      });
    } catch (error) {
      next(error);
    }
  });

  app.post('/v1/control/killswitch/global', requireControlToken(deps.env), async (req, res, next) => {
    try {
      const body = parseSchema(globalKillSwitchSchema, req.body);
      assertCanonicalTenant(body.mission.tenantId, deps.env.ACTIVE_TENANT_UUID);

      let revokedWorkflows = 0;
      if (body.action === 'activate') {
        const result = await deps.killSwitchService.activateGlobal({
          reason: body.reason,
          incidentId: body.incidentId,
          mission: body.mission,
        });
        revokedWorkflows = result.revokedWorkflows;
        killSwitchEvents.inc({ scope: 'global', action: 'activate' });
      } else {
        deps.killSwitchService.releaseGlobal();
        killSwitchEvents.inc({ scope: 'global', action: 'release' });
      }

      await deps.eventBridgeService.publish({
        eventType: 'killswitch',
        mission: body.mission,
        payload: {
          scope: 'global',
          action: body.action,
          incidentId: body.incidentId,
          reason: body.reason,
          revokedWorkflows,
        },
        status: body.action,
      });

      res.status(200).json({
        accepted: true,
        revokedWorkflows,
        killSwitch: deps.killSwitchService.snapshot(),
      });
    } catch (error) {
      next(error);
    }
  });

  app.post('/v1/slack/actions', slackRateLimiter, async (req, res, next) => {
    try {
      if (!deps.env.SLACK_SIGNING_SECRET) {
        throw new HttpError(503, 'SLACK_SIGNING_SECRET is not configured');
      }

      const signature = req.header('x-slack-signature');
      const timestamp = req.header('x-slack-request-timestamp');

      if (!signature || !timestamp) {
        throw new HttpError(401, 'missing Slack signature headers');
      }

      const verified = verifySlackSignature({
        signingSecret: deps.env.SLACK_SIGNING_SECRET,
        timestamp,
        signature,
        rawBody: req.rawBody ?? '',
      });

      if (!verified) {
        throw new HttpError(401, 'invalid Slack signature');
      }

      const payload = typeof req.body.payload === 'string' ? JSON.parse(req.body.payload) : req.body;
      const transition = parseSchema(lifecycleTransitionSchema, payload.value ?? payload);
      assertCanonicalTenant(transition.mission.tenantId, deps.env.ACTIVE_TENANT_UUID);

      validateLifecycleTransition({
        fromState: transition.fromState,
        toState: transition.toState,
        protectedAction: transition.protectedAction ?? false,
        approvals: normalizeApprovals(transition.approvals),
      });

      await deps.eventBridgeService.publish({
        eventType: 'lifecycle.transition',
        mission: transition.mission,
        payload: {
          workflowId: transition.workflowId,
          fromState: transition.fromState,
          toState: transition.toState,
          source: 'slack_action',
        },
        status: 'approved',
      });

      res.status(200).json({ accepted: true });
    } catch (error) {
      next(error);
    }
  });

  app.use((error: unknown, _req: Request, res: Response, _next: NextFunction) => {
    if (error instanceof HttpError) {
      res.status(error.statusCode).json({ error: error.message });
      return;
    }

    logWarn('unexpected request failure', {
      error: error instanceof Error ? error.message : 'unknown',
    });
    res.status(500).json({ error: 'internal_server_error' });
  });

  return app;
}

export async function bootstrapApp(env: AppEnv) {
  const deps = buildDependencies(env);
  await deps.natsPublisher.connect();
  return {
    app: createApp(deps),
    deps,
  };
}
