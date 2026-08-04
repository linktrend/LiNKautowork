import express, { type NextFunction, type Request, type Response } from 'express';
import rateLimit from 'express-rate-limit';
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
import { requireControlToken, requireInternalServiceToken, requireLibrarianInstitutionalClaim, requirePlatformInvocationClaim, requireSignedIngress } from './middleware/auth.js';
import { captureRawBody, ensureRawBody } from './middleware/raw-body.js';
import { AuditService } from './services/audit.js';
import { EventBridgeService } from './services/event-bridge.js';
import { KillSwitchService } from './services/killswitch.js';
import { type LifecycleApprovals, validateLifecycleTransition } from './services/lifecycle.js';
import { executionCallbackSchema } from './contracts/execution-callback.js';
import { ExecutionService } from './services/executions/execution-service.js';
import { SupabaseExecutionEventStore } from './services/executions/supabase-execution-store.js';
import { boundInstanceExecuteSchema } from './contracts/instance-runtime.js';
import { librarianAutomationRequestSchema, librarianReviewSchema } from './contracts/librarian-automation.js';
import { AutomationLibrarianService, GovernedReceiptVerifierKeys, Wp02PackageValidator, Wp06ReceiptEvaluator } from './services/librarian/automation-librarian.js';
import { SupabaseLibrarianEvidenceResolver, SupabaseLibrarianStore } from './services/librarian/supabase-librarian-store.js';
import { validateWp02Package } from './services/librarian/wp02-runtime.js';
import { InstanceRuntimeService } from './services/instances/runtime.js';
import { SupabasePauseReader } from './services/instances/supabase-pause-reader.js';
import { N8nProvisioner } from './integrations/n8n-provisioner.js';
import { ProvisioningService } from './services/provisioning/provisioning-service.js';
import { SupabaseProvisioningStore } from './services/provisioning/supabase-provisioning-store.js';
import { provisioningRequestSchema } from './contracts/instance-runtime.js';
import { executionOutcome, getMetricsRegistry, ingressLatencyMs, killSwitchEvents } from './services/metrics.js';
import { deploymentDecisionSchema, incidentTransitionSchema, operationsActionSchema, pauseCommandSchema } from './contracts/operations.js';
import { OperationsService, type AlertAdapter } from './services/monitoring/operations-service.js';
import { SupabaseOperationsStore } from './services/monitoring/supabase-operations-store.js';
import { N8nOperationsExecutor } from './services/deployments/n8n-operations-executor.js';

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

export type AppDeps = {
  env: AppEnv;
  nonceStore: NonceStore;
  n8nClient: N8nClient;
  natsPublisher: NatsPublisher;
  secretsProvider: SecretsProvider;
  auditService: AuditService;
  eventBridgeService: EventBridgeService;
  killSwitchService: KillSwitchService;
  supabaseClient: SupabaseAuditClient;
  executionService: ExecutionService;
  instanceRuntimeService: InstanceRuntimeService;
  librarianService: AutomationLibrarianService;
  provisioningService: ProvisioningService;
  operationsService: OperationsService;
};

export function buildDependencies(env: AppEnv): AppDeps {
  const nonceStore = new NonceStore(env.REPLAY_WINDOW_SECONDS);
  const n8nClient = new N8nClient(env);
  const natsPublisher = new NatsPublisher(env);
  const secretsProvider = new SecretsProvider(env);
  const supabaseClient = new SupabaseAuditClient(env);
  const auditService = new AuditService(supabaseClient);
  const eventBridgeService = new EventBridgeService(env, natsPublisher);
  const killSwitchService = new KillSwitchService(n8nClient, supabaseClient);
  const executionService = new ExecutionService(new SupabaseExecutionEventStore(supabaseClient));
  const instanceRuntimeService = new InstanceRuntimeService(supabaseClient, n8nClient, killSwitchService, new SupabasePauseReader(supabaseClient));
  const n8nProvisioner = new N8nProvisioner(n8nClient);
  const provisioningService = new ProvisioningService(new SupabaseProvisioningStore(supabaseClient), n8nProvisioner, (workflowId) => n8nProvisioner.smoke(workflowId));
  const librarianService = new AutomationLibrarianService(
    new SupabaseLibrarianStore(supabaseClient), new SupabaseLibrarianEvidenceResolver(supabaseClient),
    new Wp02PackageValidator(validateWp02Package), new Wp06ReceiptEvaluator(new GovernedReceiptVerifierKeys(env.evalReceiptVerifierKeys)),
    new Set(env.LIBRARIAN_TRUSTED_AGGREGATE_ISSUERS.split(',').map((value) => value.trim()).filter(Boolean)),
  );
  const operationsStore = new SupabaseOperationsStore(supabaseClient);
  const alertAdapter: AlertAdapter = { deliver: (alert) => supabaseClient.callOperationsRpc<void>('linkautowork_record_alert_delivery', { p_record: alert }) };
  const operationsExecutor = new N8nOperationsExecutor(n8nClient, supabaseClient);
  const operationsService = new OperationsService(operationsStore, alertAdapter, operationsExecutor, operationsExecutor, operationsExecutor);

  return {
    env,
    nonceStore,
    n8nClient,
    natsPublisher,
    secretsProvider,
    auditService,
    eventBridgeService,
    killSwitchService,
    supabaseClient,
    executionService,
    instanceRuntimeService,
    librarianService,
    provisioningService,
    operationsService,
  };
}

export function createApp(deps: AppDeps) {
  const app = express();
  const ingressRateLimiter = rateLimit({
    windowMs: 60_000,
    max: 120,
    standardHeaders: true,
    legacyHeaders: false,
    message: { error: 'rate_limit_exceeded' },
  });
  const slackRateLimiter = rateLimit({
    windowMs: 60_000,
    max: 60,
    standardHeaders: true,
    legacyHeaders: false,
    message: { error: 'rate_limit_exceeded' },
  });

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

  app.post('/v1/executions/callback', requireSignedIngress(deps.env, deps.nonceStore), async (req, res, next) => {
    try {
      const callback = parseSchema(executionCallbackSchema, req.body);
      const callbackToken = req.header('x-link-execution-callback-token');
      if (!req.linkService || !callbackToken) throw new HttpError(401, 'missing execution callback capability');
      const result = await deps.executionService.record(callback, { service: req.linkService, token: callbackToken });
      res.status(result.disposition === 'out_of_order' ? 202 : 200).json({
        accepted: result.disposition !== 'out_of_order',
        disposition: result.disposition,
        projection: result.projection,
      });
    } catch (error) {
      next(error);
    }
  });

  app.post('/v2/instances/:instanceId/operations/:operation/execute', ingressRateLimiter, requireInternalServiceToken(deps.env), requirePlatformInvocationClaim(deps.env), async (req, res, next) => {
    try {
      const body = parseSchema(boundInstanceExecuteSchema, req.body);
      const claim = req.platformInvocation!;
      const receipt = await deps.instanceRuntimeService.execute(claim.orgId, claim.service, req.params.instanceId, req.params.operation, body.input ?? {}, body.idempotencyKey);
      res.status(receipt.duplicate ? 200 : 202).json(receipt);
    } catch (error) { next(error); }
  });

  app.post('/v2/provisioning/run', requireInternalServiceToken(deps.env), requirePlatformInvocationClaim(deps.env), async (req, res, next) => {
    try {
      const body = parseSchema(provisioningRequestSchema, req.body);
      const result = await deps.provisioningService.run(req.platformInvocation!.orgId, body.requestRef, body.environment);
      res.status(result.status === 'completed' ? 200 : 202).json({ requestId: result.requestId, status: result.status, deploymentId: result.deploymentId, workflowId: result.workflowId });
    } catch (error) { next(error); }
  });

  app.post('/v1/operations/monitor/run', requireInternalServiceToken(deps.env), requirePlatformInvocationClaim(deps.env), async (req, res, next) => {
    try { res.status(200).json({ health: await deps.operationsService.monitor(req.platformInvocation!.orgId) }); } catch (error) { next(error); }
  });

  app.get('/v1/operations/health', requireInternalServiceToken(deps.env), requirePlatformInvocationClaim(deps.env), async (req, res, next) => {
    try { res.status(200).json({ health: await deps.operationsService.health(req.platformInvocation!.orgId) }); } catch (error) { next(error); }
  });

  app.post('/v1/operations/maintenance/run', requireInternalServiceToken(deps.env), requirePlatformInvocationClaim(deps.env), async (req, res, next) => {
    try { res.status(200).json({ maintenance: await deps.operationsService.maintenance(req.platformInvocation!.orgId) }); } catch (error) { next(error); }
  });

  app.post('/v1/operations/incidents/transition', requireInternalServiceToken(deps.env), requirePlatformInvocationClaim(deps.env), async (req, res, next) => {
    try { const body = parseSchema(incidentTransitionSchema, req.body); const claim = req.platformInvocation!; await deps.operationsService.transitionIncident(claim.orgId, body.incidentId, body.status, claim.subject, body.evidenceRef); res.status(200).json({ accepted: true }); } catch (error) { next(error); }
  });

  app.post('/v1/operations/actions', requireInternalServiceToken(deps.env), requirePlatformInvocationClaim(deps.env), async (req, res, next) => {
    try { const body = parseSchema(operationsActionSchema, req.body); const claim = req.platformInvocation!; const result = await deps.operationsService.executeAction({ ...body, orgId: claim.orgId, actor: claim.subject }); res.status(result.result === 'succeeded' ? 200 : 409).json(result); } catch (error) { next(error); }
  });

  app.post('/v1/operations/retries/deliver', requireInternalServiceToken(deps.env), requirePlatformInvocationClaim(deps.env), async (req, res, next) => {
    try { res.status(200).json(await deps.operationsService.deliverRetry(req.platformInvocation!.orgId)); } catch (error) { next(error); }
  });

  app.post('/v1/operations/deployments', requireInternalServiceToken(deps.env), requirePlatformInvocationClaim(deps.env), async (req, res, next) => {
    try { const body = parseSchema(deploymentDecisionSchema, req.body); const claim = req.platformInvocation!; res.status(200).json({ record: await deps.operationsService.deployment({ ...body, orgId: claim.orgId, actor: claim.subject }) }); } catch (error) { next(error); }
  });

  app.post('/v1/operations/pauses', requireInternalServiceToken(deps.env), requirePlatformInvocationClaim(deps.env), async (req, res, next) => {
    try { const body = parseSchema(pauseCommandSchema, req.body); const claim = req.platformInvocation!; await deps.operationsService.pause({ ...body, orgId: claim.orgId, actor: claim.subject }); res.status(200).json({ accepted: true }); } catch (error) { next(error); }
  });

  app.post('/v1/librarian/automation/candidates', requireInternalServiceToken(deps.env), requirePlatformInvocationClaim(deps.env), requireLibrarianInstitutionalClaim(deps.env), async (req, res, next) => {
    try {
      const request = parseSchema(librarianAutomationRequestSchema, req.body);
      if (request.orgId !== req.platformInvocation!.orgId) throw new HttpError(403, 'candidate organisation does not match platform claim');
      if (request.orgId !== req.librarianInstitutional!.orgId) throw new HttpError(403, 'institutional actor organisation does not match candidate');
      if (req.librarianInstitutional!.role !== 'proposer') throw new HttpError(403, 'institutional proposer role required');
      const result = await deps.librarianService.propose(request, req.librarianInstitutional!.actorId);
      res.status(result.created ? 202 : result.candidate ? 200 : 409).json(result);
    } catch (error) { next(error); }
  });

  app.post('/v1/librarian/automation/candidates/:candidateId/review', requireInternalServiceToken(deps.env), requirePlatformInvocationClaim(deps.env), requireLibrarianInstitutionalClaim(deps.env), async (req, res, next) => {
    try {
      const review = parseSchema(librarianReviewSchema, req.body); const claim = req.librarianInstitutional!;
      if (claim.role !== 'independent_reviewer') throw new HttpError(403, 'independent reviewer role required');
      if (claim.orgId !== req.platformInvocation!.orgId) throw new HttpError(403, 'institutional reviewer organisation mismatch');
      const candidate = await deps.librarianService.review(req.platformInvocation!.orgId, req.params.candidateId, review, { id: claim.actorId, role: claim.role });
      res.status(200).json({ candidate });
    } catch (error) { next(error); }
  });

  app.post('/v1/control/librarian/automation', requireControlToken(deps.env), async (req, res, next) => {
    try {
      const body = parseSchema(z.object({ orgId: z.string().uuid(), action: z.enum(['enable', 'disable', 'pause', 'resume']), automationId: z.string().min(3).max(128).optional() }).strict(), req.body);
      if ((body.action === 'pause' || body.action === 'resume') && !body.automationId) throw new HttpError(400, 'automationId is required for pause or resume');
      if (body.action === 'enable') await deps.librarianService.setEnabled(body.orgId, true);
      if (body.action === 'disable') await deps.librarianService.setEnabled(body.orgId, false);
      if (body.action === 'pause') await deps.librarianService.setAutomationPaused(body.orgId, body.automationId!, true);
      if (body.action === 'resume') await deps.librarianService.setAutomationPaused(body.orgId, body.automationId!, false);
      res.status(200).json({ accepted: true, action: body.action });
    } catch (error) { next(error); }
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

      const approvals = normalizeApprovals(body.approvals);

      await deps.supabaseClient.writeLifecycleTransition({
        orgId: body.mission.tenantId,
        workflowId: body.workflowId,
        fromState: body.fromState,
        toState: body.toState,
        protectedAction: body.protectedAction ?? false,
        approvals: { ...approvals },
        reason: `transition ${body.fromState} -> ${body.toState}`,
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
        await deps.killSwitchService.activateScoped({
          tenantId: body.mission.tenantId,
          workflowId: body.workflowId,
          reason: body.reason,
          incidentId: body.incidentId,
          mission: body.mission,
        });
        killSwitchEvents.inc({ scope: 'scoped', action: 'activate' });
      } else {
        await deps.killSwitchService.releaseScoped(body.mission.tenantId, body.workflowId, {
          reason: body.reason,
          incidentId: body.incidentId,
        });
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
        await deps.killSwitchService.releaseGlobal({
          tenantId: body.mission.tenantId,
          reason: body.reason,
          incidentId: body.incidentId,
        });
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
  await deps.killSwitchService.hydrate();
  return {
    app: createApp(deps),
    deps,
  };
}
