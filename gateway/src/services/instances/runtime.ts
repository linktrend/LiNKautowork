import { createHash, randomUUID } from 'node:crypto';
import { HttpError } from '../../lib/http-error.js';
import Ajv2020, { type ValidateFunction } from 'ajv/dist/2020.js';

export type BoundInstance = {
  bindingId: string; orgId: string; automationId: string; instanceId: string; consumerSystem: string; operation: string;
  enabled: boolean; instanceState: string; releaseId: string; releaseLifecycle: string;
  deploymentId: string; workflowId: string; workflowDigest: string; deployedDigest: string;
  configurationDigest: string; deployedConfigurationDigest: string; inputSchema: Record<string, unknown>;
  webhookPath: string; method: string; criticality: 'critical' | 'non_critical';
  timeoutMs: number; retryCount: number; secretRefs: string[];
};
export type ExecutionReceipt = { executionId: string; status: 'accepted'; correlationId: string; duplicate: boolean };
export type ExecutionStore = {
  findBoundInstance(orgId: string, service: string, operation: string): Promise<BoundInstance | undefined>;
  acceptExecution(args: { executionId: string; orgId: string; instanceId: string; releaseId: string; deploymentId: string; idempotencyKey: string; inputDigest: string; callbackService: string; callbackTokenDigest: string }): Promise<ExecutionReceipt>;
};
export type InstanceDispatcher = { triggerWebhook(path: string, method: string, payload: Record<string, unknown>, signal?: AbortSignal): Promise<{ status: number; body: unknown }> };
export type KillSwitchReader = { isBlocked(orgId: string, workflowId: string): { blocked: boolean; scope?: string; reason?: string } };
export type PauseReader = { isPaused(args: { orgId: string; automationId: string; instanceId: string }): Promise<{ paused: boolean; scope?: 'global' | 'organisation' | 'automation' | 'instance'; reason?: string }> };

function digest(value: unknown): string { return `sha256:${createHash('sha256').update(JSON.stringify(value)).digest('hex')}`; }
function tokenDigest(value: string): string { return `sha256:${createHash('sha256').update(value).digest('hex')}`; }
const Ajv2020Constructor = Ajv2020 as unknown as new (options: Record<string, unknown>) => { compile(schema: Record<string, unknown>): ValidateFunction };
const ajv = new Ajv2020Constructor({ allErrors: true, strict: true, validateFormats: false });
const validators = new Map<string, ValidateFunction>();
function inputMatchesSchema(schema: Record<string, unknown>, input: Record<string, unknown>): boolean {
  const key = digest(schema);
  let validate = validators.get(key);
  if (!validate) { const compiled = ajv.compile(schema); validators.set(key, compiled); validate = compiled; }
  return Boolean(validate(input));
}

/** Resolves all executable controls from the durable org-scoped binding, never from the caller. */
export class InstanceRuntimeService {
  constructor(private readonly store: ExecutionStore, private readonly dispatcher: InstanceDispatcher, private readonly kills: KillSwitchReader, private readonly pauses: PauseReader) {}

  async execute(orgId: string, service: string, instanceId: string, operation: string, input: Record<string, unknown>, idempotencyKey: string): Promise<ExecutionReceipt> {
    const binding = await this.store.findBoundInstance(orgId, service, operation);
    if (!binding || !binding.enabled || binding.consumerSystem !== service || binding.operation !== operation) throw new HttpError(404, 'bound automation operation not found');
    if (binding.instanceId !== instanceId) throw new HttpError(404, 'bound automation instance not found');
    if (!['ready', 'active'].includes(binding.instanceState)) throw new HttpError(409, 'automation instance is not enabled');
    if (!['certified', 'deprecated'].includes(binding.releaseLifecycle) || binding.releaseLifecycle === 'deprecated') throw new HttpError(409, 'automation release is not executable');
    if (binding.workflowDigest !== binding.deployedDigest) throw new HttpError(409, 'deployed workflow digest has drifted');
    if (binding.configurationDigest !== binding.deployedConfigurationDigest) throw new HttpError(409, 'deployed configuration digest has drifted');
    try { if (!inputMatchesSchema(binding.inputSchema, input)) throw new HttpError(400, 'automation input does not match the bound schema'); }
    catch (error) { if (error instanceof HttpError) throw error; throw new HttpError(409, 'bound automation input schema is invalid'); }
    const blocked = this.kills.isBlocked(orgId, binding.workflowId);
    if (blocked.blocked) throw new HttpError(503, `${blocked.scope} kill switch active: ${blocked.reason}`);
    const paused = await this.pauses.isPaused({ orgId, automationId: binding.automationId, instanceId: binding.instanceId });
    if (paused.paused) throw new HttpError(503, `${paused.scope ?? 'instance'} automation pause active: ${paused.reason ?? 'paused'}`);
    const executionId = randomUUID(); const inputDigest = digest(input);
    const callbackToken = randomUUID() + randomUUID();
    const receipt = await this.store.acceptExecution({ executionId, orgId, instanceId: binding.instanceId, releaseId: binding.releaseId, deploymentId: binding.deploymentId, idempotencyKey, inputDigest, callbackService: 'linkautowork-n8n', callbackTokenDigest: tokenDigest(callbackToken) });
    if (receipt.duplicate) return receipt;
    try {
      // Secret refs are intentionally not resolved into this payload. A native n8n credential or broker owns resolution.
      let lastError: unknown;
      for (let attempt = 0; attempt <= binding.retryCount; attempt += 1) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(new Error('dispatch timeout')), binding.timeoutMs);
        try {
          const dispatch = await this.dispatcher.triggerWebhook(binding.webhookPath, binding.method, { executionId, callbackToken, input, timeoutMs: binding.timeoutMs, retryCount: binding.retryCount, secretBroker: { mode: 'native_instance_credentials', refs: binding.secretRefs } }, controller.signal);
          if (dispatch.status >= 200 && dispatch.status < 300) { lastError = undefined; break; }
          lastError = new Error(`n8n dispatch failed with status ${dispatch.status}`);
        } catch (error) {
          lastError = error;
          // A timeout or transport failure is ambiguous: n8n may have accepted
          // the request before cancellation. Never retry and risk duplicate work.
          break;
        } finally { clearTimeout(timer); }
      }
      if (lastError) throw lastError;
    } catch (error) { throw new HttpError(502, 'automation dispatch was not accepted'); }
    return receipt;
  }
}
