import { createHash } from 'node:crypto';
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

const definitionContent = '{"automation_id":"ide-repository-status","operation_kinds":["status_collection","precheck"],"side_effect_class":"read_only","version":"1.0.0"}';
const configurationContent = '{"cache":"disabled","execution":"read_only","network":"disabled"}';
const digestOf = (value: string) => `sha256:${createHash('sha256').update(value).digest('hex')}`;
const definitionDigest = digestOf(definitionContent);
const configurationDigest = digestOf(configurationContent);
const observedAt = '2026-08-13T00:00:00.000Z';
const canarySummary = providerCatalogueSummarySchema.parse({
  automation: { automation_id: 'ide-repository-status', version: '1.0.0', definition_digest: definitionDigest, configuration_ref: { ref: 'autowork://config/ide-repository-status/1.0.0', digest: configurationDigest, observed_at: observedAt } },
  owner: 'linkautowork', organization_visibility: 'organization', purpose: 'Read-only repository status and deterministic precheck.', operation_kinds: ['status_collection', 'precheck'], side_effect_class: 'read_only', lifecycle: 'available', contract_ref: 'autowork://contracts/ide-repository-status/1.0.0',
});
const canaryDetail = providerCatalogueDetailSchema.parse({ ...canarySummary, input_schema_ref: { ref: 'autowork://schemas/ide-repository-status/input', digest: definitionDigest, observed_at: observedAt }, output_schema_ref: { ref: 'autowork://schemas/ide-repository-status/output', digest: definitionDigest, observed_at: observedAt }, capability_requirement: 'catalogue.invoke', retry_policy_ref: 'autowork://policies/retry/read-only', cancellation_policy_ref: 'autowork://policies/cancel/read-only', runbook_ref: 'autowork://runbooks/ide-repository-status', evidence_guide_ref: 'autowork://evidence/ide-repository-status' });

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
/** Immutable canary content digests, exported for exact-version contract tests. */
export const ideRepositoryStatusCanaryDigests = { definition: definitionDigest, configuration: configurationDigest } as const;
