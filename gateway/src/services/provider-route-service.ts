import { createHash, randomUUID } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {
  PROVIDER_CONTRACT_VERSION,
  providerCapabilityStatusSchema,
  providerCallbackSchema,
  providerCatalogueDetailSchema,
  providerCatalogueSummarySchema,
  providerEventSchema,
  providerInvocationRequestSchema,
  type ProviderInvocationRequest,
} from '../../../packages/automation-contracts/src/provider-contract.js';
import { InMemoryProviderStore, ProviderStoreError, type ProviderStore } from './provider-store.js';

const observedAt = '2026-08-13T00:00:00.000Z';

type JsonObject = Record<string, unknown>;
type LoadedIdeRepositoryStatus = {
  manifest: JsonObject;
  packageDigest: string;
  workflowDigest: string;
  configurationDigest: string;
  inputDigest: string;
  outputDigest: string;
};
type ConnectionHealthWebhook = (payload: { request_id: string; request_fingerprint: string }) => Promise<unknown>;
type ConnectionHealthDispatchOutcome = {
  dispatch_attempted: boolean;
  dispatch_confirmed: boolean;
  ambiguous: boolean;
  recovery_required: boolean;
  recovery_reason?: 'dispatch_claim_state_unavailable' | 'dispatch_claim_state_changed' | 'dispatch_claim_terminalization_failed' | 'dispatch_claim_receipt_failed';
  status: ProviderRouteStatus | null;
};
const connectionHealthId = 'linkautowork-connection-health';
const connectionHealthVersion = '1.0.0';
const connectionHealthPolicyRef = 'autowork://policies/linkautowork-connection-health/read-only-v1';
const connectionHealthConfigRef = 'autowork://config/linkautowork-connection-health/1.0.0';
const connectionHealthInputRef = 'autowork://inputs/linkautowork-connection-health/empty-v1';
const connectionHealthClaimFailureRef = 'autowork://errors/linkautowork-connection-health/dispatch-claim-failed';

const digestOf = (value: string | Buffer) => `sha256:${createHash('sha256').update(value).digest('hex')}`;

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value as JsonObject).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson((value as JsonObject)[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function readJson(file: string): JsonObject {
  let value: unknown;
  try {
    value = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    throw new Error(`ide-repository-status package JSON is malformed: ${path.basename(file)}`);
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`ide-repository-status package JSON is not an object: ${path.basename(file)}`);
  return value as JsonObject;
}

function safePackageFile(packageDir: string, reference: unknown): string {
  if (typeof reference !== 'string' || !reference || path.isAbsolute(reference) || reference.includes('..')) throw new Error('ide-repository-status package reference is unsafe');
  const root = fs.realpathSync(packageDir);
  const file = path.resolve(root, reference);
  if (!file.startsWith(`${root}${path.sep}`) || !fs.existsSync(file) || !fs.statSync(file).isFile()) throw new Error('ide-repository-status package reference is unavailable');
  return file;
}

function governedJsonFiles(packageDir: string): string[] {
  const files = ['automation.json', 'workflow.json'];
  for (const directory of ['contracts', 'evals']) {
    const root = path.join(packageDir, directory);
    if (!fs.existsSync(root)) throw new Error(`ide-repository-status package directory is missing: ${directory}`);
    const visit = (current: string, relative: string) => {
      for (const entry of fs.readdirSync(current, { withFileTypes: true }).sort((left, right) => left.name.localeCompare(right.name))) {
        const entryPath = path.join(current, entry.name);
        const entryRelative = path.posix.join(relative, entry.name);
        if (entry.isDirectory()) visit(entryPath, entryRelative);
        else if (entry.name.endsWith('.json')) files.push(entryRelative);
      }
    };
    visit(root, directory);
  }
  files.push('operations/monitoring.json', 'operations/maintenance.json', 'operations/deployment.json', 'provenance/sources.json');
  return [...new Set(files)].sort();
}

function calculatePackageDigest(packageDir: string, manifest: JsonObject): string {
  const stream = createHash('sha256');
  for (const relative of governedJsonFiles(packageDir)) {
    const file = safePackageFile(packageDir, relative);
    const value = readJson(file);
    if (relative === 'automation.json') {
      const release = { ...((value.release as JsonObject) ?? {}) };
      release.identity = { ...((release.identity as JsonObject) ?? {}), package_digest: 'sha256:__excluded__' };
      value.release = release;
    }
    stream.update(relative);
    stream.update('\0');
    stream.update(createHash('sha256').update(`${canonicalJson(value)}\n`).digest('hex'));
    stream.update('\0');
  }
  return `sha256:${stream.digest('hex')}`;
}

/** Loads and verifies the checked-in package without executing its workflow or contacting a network. */
export function loadIdeRepositoryStatusPackage(packageDir = path.resolve(process.cwd(), 'automations/catalog/ide-repository-status/1.0.0')): LoadedIdeRepositoryStatus {
  const manifest = readJson(safePackageFile(packageDir, 'automation.json'));
  const release = manifest.release as JsonObject | undefined;
  const identity = release?.identity as JsonObject | undefined;
  if (manifest.automation_id !== 'ide-repository-status' || release?.version !== '1.0.0' || release?.lifecycle !== 'draft') throw new Error('ide-repository-status package identity is invalid');
  if (manifest.runtime && (manifest.runtime as JsonObject).workflow_ref !== 'workflow.json') throw new Error('ide-repository-status workflow reference is invalid');
  if (!Array.isArray(manifest.secrets) || manifest.secrets.length !== 0) throw new Error('ide-repository-status package must declare zero credentials');

  const workflowFile = safePackageFile(packageDir, (manifest.runtime as JsonObject | undefined)?.workflow_ref);
  const workflow = readJson(workflowFile);
  const nodes = workflow.nodes;
  if (workflow.active !== false || !Array.isArray(nodes) || nodes.length !== 2 || nodes.some((node) => !node || typeof node !== 'object' || !['n8n-nodes-base.manualTrigger', 'n8n-nodes-base.set'].includes((node as JsonObject).type as string))) throw new Error('ide-repository-status workflow must be inactive manual n8n core Manual Trigger plus Set');
  if (nodes.some((node) => Object.prototype.hasOwnProperty.call(node as JsonObject, 'credentials'))) throw new Error('ide-repository-status workflow must declare zero credentials');
  const workflowDigest = digestOf(fs.readFileSync(workflowFile));
  const packageDigest = calculatePackageDigest(packageDir, manifest);
  const configurationFile = safePackageFile(packageDir, (manifest.contracts as JsonObject | undefined)?.configuration_schema_ref);
  const inputFile = safePackageFile(packageDir, (manifest.contracts as JsonObject | undefined)?.input_schema_ref);
  const outputFile = safePackageFile(packageDir, (manifest.contracts as JsonObject | undefined)?.output_schema_ref);
  const configurationDigest = digestOf(fs.readFileSync(configurationFile));
  if (identity?.package_digest !== packageDigest || identity?.workflow_digest !== workflowDigest || !identity?.package_digest || !identity?.workflow_digest) throw new Error('ide-repository-status package identity digest verification failed');
  return { manifest, packageDigest, workflowDigest, configurationDigest, inputDigest: digestOf(fs.readFileSync(inputFile)), outputDigest: digestOf(fs.readFileSync(outputFile)) };
}

/** Loads the inactive, fixed webhook package; no workflow is executed or activated here. */
export function loadConnectionHealthPackage(packageDir = path.resolve(process.cwd(), 'automations/catalog/linkautowork-connection-health/1.0.0')): LoadedIdeRepositoryStatus {
  const manifest = readJson(safePackageFile(packageDir, 'automation.json'));
  const release = manifest.release as JsonObject | undefined;
  const identity = release?.identity as JsonObject | undefined;
  if (manifest.automation_id !== connectionHealthId || release?.version !== connectionHealthVersion || release?.lifecycle !== 'draft') throw new Error('connection-health package identity is invalid');
  if ((manifest.runtime as JsonObject | undefined)?.workflow_ref !== 'workflow.json' || (manifest.runtime as JsonObject | undefined)?.trigger_mode !== 'webhook' || (manifest.runtime as JsonObject | undefined)?.result_mode !== 'synchronous_response') throw new Error('connection-health runtime contract is invalid');
  if (!Array.isArray(manifest.secrets) || manifest.secrets.length !== 0) throw new Error('connection-health package must not contain secret values or package secret inputs');
  const workflowFile = safePackageFile(packageDir, (manifest.runtime as JsonObject).workflow_ref);
  const workflow = readJson(workflowFile);
  const nodes = workflow.nodes;
  const allowedNodes = ['n8n-nodes-base.webhook', 'n8n-nodes-base.set', 'n8n-nodes-base.respondToWebhook'];
  if (workflow.active !== false || !Array.isArray(nodes) || nodes.length !== 3 || nodes.some((node) => !node || typeof node !== 'object' || !allowedNodes.includes((node as JsonObject).type as string))) throw new Error('connection-health workflow must be an inactive Webhook, Set, and Respond to Webhook graph');
  const webhook = nodes.find((node) => (node as JsonObject).type === 'n8n-nodes-base.webhook') as JsonObject | undefined;
  const parameters = webhook?.parameters as JsonObject | undefined;
  if (parameters?.authentication !== 'headerAuth' || parameters?.httpMethod !== 'POST' || parameters?.path !== 'linkautowork-connection-health-v1' || parameters?.responseMode !== 'responseNode') throw new Error('connection-health webhook must use the fixed authenticated synchronous endpoint');
  if (nodes.some((node) => Object.prototype.hasOwnProperty.call(node as JsonObject, 'credentials'))) throw new Error('connection-health package must not embed a credential reference');
  const workflowDigest = digestOf(fs.readFileSync(workflowFile));
  const packageDigest = calculatePackageDigest(packageDir, manifest);
  const configurationFile = safePackageFile(packageDir, (manifest.contracts as JsonObject).configuration_schema_ref);
  const inputFile = safePackageFile(packageDir, (manifest.contracts as JsonObject).input_schema_ref);
  const outputFile = safePackageFile(packageDir, (manifest.contracts as JsonObject).output_schema_ref);
  const configurationDigest = digestOf(fs.readFileSync(configurationFile));
  if (identity?.package_digest !== packageDigest || identity?.workflow_digest !== workflowDigest || !identity?.package_digest || !identity?.workflow_digest) throw new Error('connection-health package identity digest verification failed');
  return { manifest, packageDigest, workflowDigest, configurationDigest, inputDigest: digestOf(fs.readFileSync(inputFile)), outputDigest: digestOf(fs.readFileSync(outputFile)) };
}

const loadedPackage = loadIdeRepositoryStatusPackage();
const canarySummary = providerCatalogueSummarySchema.parse({
  automation: { automation_id: loadedPackage.manifest.automation_id, version: (loadedPackage.manifest.release as JsonObject).version, definition_digest: loadedPackage.packageDigest, configuration_ref: { ref: 'autowork://config/ide-repository-status/1.0.0', digest: loadedPackage.configurationDigest, observed_at: observedAt } },
  owner: 'linkautowork', organization_visibility: 'organization', purpose: loadedPackage.manifest.summary, operation_kinds: ['status_collection', 'precheck'], side_effect_class: 'read_only', lifecycle: 'available', contract_ref: 'autowork://contracts/ide-repository-status/1.0.0',
});
const canaryDetail = providerCatalogueDetailSchema.parse({ ...canarySummary, input_schema_ref: { ref: 'autowork://schemas/ide-repository-status/input', digest: loadedPackage.inputDigest, observed_at: observedAt }, output_schema_ref: { ref: 'autowork://schemas/ide-repository-status/output', digest: loadedPackage.outputDigest, observed_at: observedAt }, capability_requirement: 'catalogue.invoke', retry_policy_ref: 'autowork://policies/retry/read-only', cancellation_policy_ref: 'autowork://policies/cancel/read-only', runbook_ref: 'autowork://runbooks/ide-repository-status', evidence_guide_ref: 'autowork://evidence/ide-repository-status' });
const loadedConnectionHealthPackage = loadConnectionHealthPackage();
const connectionHealthSummary = providerCatalogueSummarySchema.parse({
  automation: { automation_id: connectionHealthId, version: connectionHealthVersion, definition_digest: loadedConnectionHealthPackage.packageDigest, configuration_ref: { ref: connectionHealthConfigRef, digest: loadedConnectionHealthPackage.configurationDigest, observed_at: observedAt } },
  owner: 'linkautowork', organization_visibility: 'organization', purpose: 'Read-only provider-to-n8n connectivity canary with a durable correlated execution receipt.', operation_kinds: ['status_collection', 'precheck'], side_effect_class: 'read_only', lifecycle: 'available', contract_ref: 'autowork://contracts/linkautowork-connection-health/1.0.0',
});
const connectionHealthDetail = providerCatalogueDetailSchema.parse({ ...connectionHealthSummary, input_schema_ref: { ref: 'autowork://schemas/linkautowork-connection-health/input', digest: loadedConnectionHealthPackage.inputDigest, observed_at: observedAt }, output_schema_ref: { ref: 'autowork://schemas/linkautowork-connection-health/output', digest: loadedConnectionHealthPackage.outputDigest, observed_at: observedAt }, capability_requirement: 'catalogue.invoke', retry_policy_ref: 'autowork://policies/linkautowork-connection-health/retry-none', cancellation_policy_ref: 'autowork://policies/linkautowork-connection-health/manual-reconcile', runbook_ref: 'autowork://runbooks/linkautowork-connection-health', evidence_guide_ref: 'autowork://evidence/linkautowork-connection-health' });

/** Compact route-safe provider status that never claims a consumer result or authority. */
export type ProviderRouteStatus = { request_id: string; state: string; attempt_count: number; automation: { automation_id: string; version: string; definition_digest: string; configuration_digest: string }; receipt_id?: string };

/** Authenticated PACI dimensions that are mirrored by the provider request binding. */
export type ProviderInvocationIdentity = {
  subject: string;
  credentialId: string;
  runtimeBindingId: string;
  issuedAt: string;
  expiresAt: string;
  audience: readonly string[];
};

function assertRequestIdentity(request: ProviderInvocationRequest, identity: ProviderInvocationIdentity): void {
  const binding = request.platform;
  if (binding.actor_id !== identity.subject
    || binding.credential_id !== identity.credentialId
    || binding.binding_id !== identity.runtimeBindingId
    || Date.parse(binding.issued_at) !== Date.parse(identity.issuedAt)
    || Date.parse(binding.expires_at) !== Date.parse(identity.expiresAt)) {
    throw new ProviderStoreError('forbidden', 'provider request identity does not match the authenticated Platform claim');
  }
}

/** Route facade: callers choose exact catalogue entries; this provider never selects consumer work. */
export class ProviderRouteService {
  constructor(private readonly store: ProviderStore = new InMemoryProviderStore(), private readonly connectionHealthWebhook?: ConnectionHealthWebhook) {}
  capabilities() { return [providerCapabilityStatusSchema.parse({ capability: 'provider.catalogue', state: 'available', observed_at: observedAt, does_not_prove: ['automation_run', 'consumer_outcome', 'consumer_gate', 'external_side_effect', 'e2e_readiness', 'production_readiness'] }), providerCapabilityStatusSchema.parse({ capability: 'provider.external_assistance_activation', state: 'hold', observed_at: observedAt, detail_ref: 'autowork://holds/external-assistance-activation', does_not_prove: ['automation_run', 'consumer_outcome', 'consumer_gate', 'external_side_effect', 'e2e_readiness', 'production_readiness'] })]; }
  catalogue() { return [canarySummary, this.connectionHealthWebhook ? connectionHealthSummary : providerCatalogueSummarySchema.parse({ ...connectionHealthSummary, lifecycle: 'disabled' })]; }
  detail(automationId: string, version: string) { if (automationId === connectionHealthId && version === connectionHealthVersion) return this.connectionHealthWebhook ? connectionHealthDetail : providerCatalogueDetailSchema.parse({ ...connectionHealthDetail, lifecycle: 'disabled' }); if (automationId !== canaryDetail.automation.automation_id || version !== canaryDetail.automation.version) throw new ProviderStoreError('not_found', 'exact automation version is unavailable'); return canaryDetail; }
  async accept(orgId: string, input: unknown, identity?: ProviderInvocationIdentity): Promise<{ replay: boolean; status: ProviderRouteStatus }> {
    const request = providerInvocationRequestSchema.parse(input);
    if (request.platform.org_id !== orgId) throw new ProviderStoreError('forbidden', 'payload organisation does not match authenticated Platform claim');
    if (identity) assertRequestIdentity(request, identity);
    if (request.operation_kind === 'external_assistance') throw new ProviderStoreError('blocked', 'external assistance activation is HOLD/unavailable');
    const detail = this.detail(request.automation.automation_id, request.automation.version);
    if (request.automation.automation_id === connectionHealthId) {
      if (!this.connectionHealthWebhook) throw new ProviderStoreError('blocked', 'connection-health webhook is not configured');
      if (!['status_collection', 'precheck'].includes(request.operation_kind)
        || request.input_ref.ref !== connectionHealthInputRef || request.input_ref.digest !== loadedConnectionHealthPackage.inputDigest
        || request.policy.side_effect_class !== 'read_only' || request.policy.approval_requirement !== 'none'
        || request.policy.data_classification !== 'internal' || request.policy.policy_profile_ref !== connectionHealthPolicyRef
        || request.policy.rate_policy_ref !== undefined || request.policy.quiet_hour_policy_ref !== undefined || request.policy.suppression_ref !== undefined
        || request.approval_refs.length !== 0 || request.artifact_refs.length !== 0
        || request.brain_handoff_ref !== undefined || request.sanitized_brain_candidate_ref !== undefined || request.cancellation_requested_at !== undefined) {
        throw new ProviderStoreError('forbidden', 'connection-health request does not satisfy its exact read-only policy');
      }
    }
    if (request.platform.audience !== 'lautowork' || request.platform.capability !== detail.capability_requirement) throw new ProviderStoreError('forbidden', 'payload Platform audience or capability does not satisfy exact automation');
    if (detail.automation.definition_digest !== request.automation.definition_digest || detail.automation.configuration_ref.digest !== request.automation.configuration_ref.digest
      || (request.automation.automation_id === connectionHealthId && request.automation.configuration_ref.ref !== connectionHealthConfigRef)) throw new ProviderStoreError('forbidden', 'exact automation digest/configuration does not match catalogue');
    let accepted: Awaited<ReturnType<ProviderStore['accept']>>;
    try { accepted = await this.store.accept(orgId, request); } catch (error) { if (error instanceof ProviderStoreError) throw error; throw new ProviderStoreError('forbidden', error instanceof Error ? error.message : 'provider invocation is invalid'); }
    return { replay: accepted.replay, status: this.status(accepted.record) };
  }
  async request(orgId: string, requestId: string) { return this.status(await this.store.getRequest(orgId, requestId)); }
  async dispatchConnectionHealth(orgId: string, requestId: string): Promise<ConnectionHealthDispatchOutcome> {
    if (!this.connectionHealthWebhook) throw new ProviderStoreError('blocked', 'connection-health webhook is not configured');
    const record = await this.store.getRequest(orgId, requestId);
    if (record.request.automation.automation_id !== connectionHealthId || record.request.automation.version !== connectionHealthVersion || record.state !== 'accepted') return { dispatch_attempted: false, dispatch_confirmed: false, ambiguous: record.state === 'running', recovery_required: false, status: this.status(record) };
    try { await this.store.transition(orgId, requestId, record.version, 'running'); }
    catch { return await this.handleConnectionHealthClaimFailure(orgId, record); }
    try {
      const response = await this.connectionHealthWebhook({ request_id: requestId, request_fingerprint: record.fingerprint });
      const result = response && typeof response === 'object' && !Array.isArray(response) ? response as JsonObject : {};
      const executionId = result.execution_id;
      if (result.status !== 'ok' || result.scope !== 'provider_to_n8n_dispatch' || result.automation_id !== connectionHealthId || result.version !== connectionHealthVersion || result.request_id !== requestId || result.request_fingerprint !== record.fingerprint || typeof executionId !== 'string' || !/^[A-Za-z0-9._:-]{1,128}$/.test(executionId)) throw new Error('connection-health webhook response did not match the dispatched request');
      const now = new Date().toISOString();
      const executionRef = `n8n://executions/${executionId}`;
      const receiptId = randomUUID();
      const receipt = providerCallbackSchema.parse({
        request_id: requestId,
        receipt_id: receiptId,
        org_id: orgId,
        callback_binding_ref: record.request.automation.configuration_ref.ref,
        source_timestamp: now,
        receipt: {
          contract_version: PROVIDER_CONTRACT_VERSION, request_id: requestId, receipt_id: receiptId, state: 'succeeded', accepted_at: record.request.platform.issued_at, updated_at: now, attempt_count: record.attempts + 1, request_fingerprint: record.fingerprint,
          automation: record.request.automation, freshness_at: now, result_refs: [{ ref: executionRef, digest: record.fingerprint, classification: 'internal' }], evidence_refs: [{ ref: executionRef, digest: record.fingerprint, classification: 'internal' }], uncertain_outcome: false,
        },
      });
      await this.store.admitCallback(orgId, receipt);
      return { dispatch_attempted: true, dispatch_confirmed: true, ambiguous: false, recovery_required: false, status: await this.request(orgId, requestId) };
    } catch {
      // A timeout or invalid reply can follow a real execution; leave running for manual status reconciliation.
      return { dispatch_attempted: true, dispatch_confirmed: false, ambiguous: true, recovery_required: false, status: await this.request(orgId, requestId) };
    }
  }
  private async handleConnectionHealthClaimFailure(orgId: string, record: Awaited<ReturnType<ProviderStore['getRequest']>>): Promise<ConnectionHealthDispatchOutcome> {
    let current: Awaited<ReturnType<ProviderStore['getRequest']>>;
    try { current = await this.store.getRequest(orgId, record.request.request_id); }
    catch {
      await this.appendConnectionHealthClaimFailureEvent(orgId, record);
      return { dispatch_attempted: false, dispatch_confirmed: false, ambiguous: true, recovery_required: true, recovery_reason: 'dispatch_claim_state_unavailable', status: null };
    }
    if (current.state !== 'accepted' || current.version !== record.version || current.fingerprint !== record.fingerprint) {
      await this.appendConnectionHealthClaimFailureEvent(orgId, record);
      return { dispatch_attempted: false, dispatch_confirmed: false, ambiguous: current.state === 'running', recovery_required: true, recovery_reason: 'dispatch_claim_state_changed', status: this.status(current) };
    }

    let unavailable: Awaited<ReturnType<ProviderStore['transition']>>;
    try { unavailable = await this.store.transition(orgId, record.request.request_id, current.version, 'unavailable'); }
    catch {
      await this.appendConnectionHealthClaimFailureEvent(orgId, record);
      return await this.connectionHealthRecoveryRequired(orgId, record, 'dispatch_claim_terminalization_failed');
    }

    try {
      await this.store.writeReceipt(orgId, {
        contract_version: PROVIDER_CONTRACT_VERSION, request_id: record.request.request_id, receipt_id: randomUUID(), state: 'unavailable',
        accepted_at: record.request.platform.issued_at, updated_at: new Date().toISOString(), attempt_count: unavailable.attempts,
        request_fingerprint: record.fingerprint, automation: record.request.automation, result_refs: [], evidence_refs: [],
        error: { category: 'unavailable', code: 'dispatch_claim_failed', retryable: false }, uncertain_outcome: false,
      });
      return { dispatch_attempted: false, dispatch_confirmed: false, ambiguous: false, recovery_required: false, status: await this.request(orgId, record.request.request_id) };
    } catch {
      await this.appendConnectionHealthClaimFailureEvent(orgId, record);
      return await this.connectionHealthRecoveryRequired(orgId, record, 'dispatch_claim_receipt_failed');
    }
  }
  private async connectionHealthRecoveryRequired(orgId: string, record: Awaited<ReturnType<ProviderStore['getRequest']>>, reason: NonNullable<ConnectionHealthDispatchOutcome['recovery_reason']>): Promise<ConnectionHealthDispatchOutcome> {
    try {
      const current = await this.store.getRequest(orgId, record.request.request_id);
      return { dispatch_attempted: false, dispatch_confirmed: false, ambiguous: current.state === 'running', recovery_required: true, recovery_reason: reason, status: this.status(current) };
    } catch {
      return { dispatch_attempted: false, dispatch_confirmed: false, ambiguous: true, recovery_required: true, recovery_reason: reason, status: null };
    }
  }
  private async appendConnectionHealthClaimFailureEvent(orgId: string, record: Awaited<ReturnType<ProviderStore['getRequest']>>): Promise<void> {
    const observedAt = new Date().toISOString();
    try {
      await this.store.appendEvent(orgId, providerEventSchema.parse({
        event_id: randomUUID(), source_ref: 'autowork://provider/linkautowork-connection-health',
        cursor: `request:${record.request.request_id}:dispatch-claim-failure:${record.version}`,
        correlation_refs: record.request.correlation_refs, occurred_at: observedAt, type: 'attempt',
        payload_ref: { ref: connectionHealthClaimFailureRef, digest: record.fingerprint, observed_at: observedAt },
      }));
    } catch { /* The explicit recovery_required response remains the fallback if persistence is unavailable. */ }
  }
  async receipt(orgId: string, requestId: string) { const record = await this.store.getRequest(orgId, requestId); if (!record.receipt) throw new ProviderStoreError('not_found', 'provider receipt is not available'); return record.receipt; }
  async callback(orgId: string, callback: unknown) { return this.store.admitCallback(orgId, providerCallbackSchema.parse(callback)); }
  async events(orgId: string, cursor: string | null, limit: number) { return this.store.listEvents(orgId, cursor, limit); }
  private status(record: Awaited<ReturnType<ProviderStore['getRequest']>>): ProviderRouteStatus { return { request_id: record.request.request_id, state: record.state, attempt_count: record.attempts, automation: { automation_id: record.request.automation.automation_id, version: record.request.automation.version, definition_digest: record.request.automation.definition_digest, configuration_digest: record.request.automation.configuration_ref.digest }, ...(record.receipt ? { receipt_id: record.receipt.receipt_id } : {}) }; }
}

export const providerRouteContractVersion = PROVIDER_CONTRACT_VERSION;
/** Verified package digests exported for exact-version contract tests. */
export const ideRepositoryStatusCanaryDigests = { definition: loadedPackage.packageDigest, configuration: loadedPackage.configurationDigest } as const;
export const connectionHealthPackageDigests = { definition: loadedConnectionHealthPackage.packageDigest, configuration: loadedConnectionHealthPackage.configurationDigest, input: loadedConnectionHealthPackage.inputDigest } as const;
