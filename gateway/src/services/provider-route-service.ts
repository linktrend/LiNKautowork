import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {
  PROVIDER_CONTRACT_VERSION,
  providerCapabilityStatusSchema,
  providerCallbackSchema,
  providerCatalogueDetailSchema,
  providerCatalogueSummarySchema,
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

const loadedPackage = loadIdeRepositoryStatusPackage();
const canarySummary = providerCatalogueSummarySchema.parse({
  automation: { automation_id: loadedPackage.manifest.automation_id, version: (loadedPackage.manifest.release as JsonObject).version, definition_digest: loadedPackage.packageDigest, configuration_ref: { ref: 'autowork://config/ide-repository-status/1.0.0', digest: loadedPackage.configurationDigest, observed_at: observedAt } },
  owner: 'linkautowork', organization_visibility: 'organization', purpose: loadedPackage.manifest.summary, operation_kinds: ['status_collection', 'precheck'], side_effect_class: 'read_only', lifecycle: 'available', contract_ref: 'autowork://contracts/ide-repository-status/1.0.0',
});
const canaryDetail = providerCatalogueDetailSchema.parse({ ...canarySummary, input_schema_ref: { ref: 'autowork://schemas/ide-repository-status/input', digest: loadedPackage.inputDigest, observed_at: observedAt }, output_schema_ref: { ref: 'autowork://schemas/ide-repository-status/output', digest: loadedPackage.outputDigest, observed_at: observedAt }, capability_requirement: 'catalogue.invoke', retry_policy_ref: 'autowork://policies/retry/read-only', cancellation_policy_ref: 'autowork://policies/cancel/read-only', runbook_ref: 'autowork://runbooks/ide-repository-status', evidence_guide_ref: 'autowork://evidence/ide-repository-status' });

/** Compact route-safe provider status that never claims a consumer result or authority. */
export type ProviderRouteStatus = { request_id: string; state: string; attempt_count: number; automation: { automation_id: string; version: string; definition_digest: string; configuration_digest: string }; receipt_id?: string };

/** Route facade: callers choose exact catalogue entries; this provider never selects consumer work. */
export class ProviderRouteService {
  constructor(private readonly store: ProviderStore = new InMemoryProviderStore()) {}
  capabilities() { return [providerCapabilityStatusSchema.parse({ capability: 'provider.catalogue', state: 'available', observed_at: observedAt, does_not_prove: ['automation_run', 'consumer_outcome', 'consumer_gate', 'external_side_effect', 'e2e_readiness', 'production_readiness'] }), providerCapabilityStatusSchema.parse({ capability: 'provider.external_assistance_activation', state: 'hold', observed_at: observedAt, detail_ref: 'autowork://holds/external-assistance-activation', does_not_prove: ['automation_run', 'consumer_outcome', 'consumer_gate', 'external_side_effect', 'e2e_readiness', 'production_readiness'] })]; }
  catalogue() { return [canarySummary]; }
  detail(automationId: string, version: string) { if (automationId !== canaryDetail.automation.automation_id || version !== canaryDetail.automation.version) throw new ProviderStoreError('not_found', 'exact automation version is unavailable'); return canaryDetail; }
  async accept(orgId: string, input: unknown): Promise<{ replay: boolean; status: ProviderRouteStatus }> {
    const request = providerInvocationRequestSchema.parse(input);
    if (request.platform.org_id !== orgId) throw new ProviderStoreError('forbidden', 'payload organisation does not match authenticated Platform claim');
    if (request.operation_kind === 'external_assistance') throw new ProviderStoreError('blocked', 'external assistance activation is HOLD/unavailable');
    const detail = this.detail(request.automation.automation_id, request.automation.version);
    if (request.platform.audience !== 'lautowork' || request.platform.capability !== detail.capability_requirement) throw new ProviderStoreError('forbidden', 'payload Platform audience or capability does not satisfy exact automation');
    if (detail.automation.definition_digest !== request.automation.definition_digest || detail.automation.configuration_ref.digest !== request.automation.configuration_ref.digest) throw new ProviderStoreError('forbidden', 'exact automation digest/configuration does not match catalogue');
    let accepted: Awaited<ReturnType<ProviderStore['accept']>>;
    try { accepted = await this.store.accept(orgId, request); } catch (error) { if (error instanceof ProviderStoreError) throw error; throw new ProviderStoreError('forbidden', error instanceof Error ? error.message : 'provider invocation is invalid'); }
    return { replay: accepted.replay, status: this.status(accepted.record) };
  }
  async request(orgId: string, requestId: string) { return this.status(await this.store.getRequest(orgId, requestId)); }
  async receipt(orgId: string, requestId: string) { const record = await this.store.getRequest(orgId, requestId); if (!record.receipt) throw new ProviderStoreError('not_found', 'provider receipt is not available'); return record.receipt; }
  async callback(orgId: string, callback: unknown) { return this.store.admitCallback(orgId, providerCallbackSchema.parse(callback)); }
  async events(orgId: string, cursor: string | null, limit: number) { return this.store.listEvents(orgId, cursor, limit); }
  private status(record: Awaited<ReturnType<ProviderStore['getRequest']>>): ProviderRouteStatus { return { request_id: record.request.request_id, state: record.state, attempt_count: record.attempts, automation: { automation_id: record.request.automation.automation_id, version: record.request.automation.version, definition_digest: record.request.automation.definition_digest, configuration_digest: record.request.automation.configuration_ref.digest }, ...(record.receipt ? { receipt_id: record.receipt.receipt_id } : {}) }; }
}

export const providerRouteContractVersion = PROVIDER_CONTRACT_VERSION;
/** Verified package digests exported for exact-version contract tests. */
export const ideRepositoryStatusCanaryDigests = { definition: loadedPackage.packageDigest, configuration: loadedPackage.configurationDigest } as const;
