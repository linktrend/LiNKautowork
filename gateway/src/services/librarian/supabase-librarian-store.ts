import type { SupabaseAuditClient } from '../../integrations/supabase-rpc.js';
import type { AutomationImprovementCandidate, EvidenceResolver, LibrarianCandidateStore, ResolvedEvidence } from './automation-librarian.js';

/** Durable organisation-scoped WP-07 state adapter backed by least-purpose RPCs. */
export class SupabaseLibrarianStore implements LibrarianCandidateStore {
  constructor(private readonly client: SupabaseAuditClient) {}
  async findByDeduplicationKey(orgId: string, key: string) { return this.one(await this.client.callLibrarianRpc<unknown>('linkautowork_librarian_find_candidate', { p_org_id: orgId, p_deduplication_key: key, p_candidate_id: null })); }
  async findById(orgId: string, id: string) { return this.one(await this.client.callLibrarianRpc<unknown>('linkautowork_librarian_find_candidate', { p_org_id: orgId, p_deduplication_key: null, p_candidate_id: id })); }
  async save(candidate: AutomationImprovementCandidate) { return await this.client.callLibrarianRpc<AutomationImprovementCandidate>('linkautowork_librarian_save_candidate', { p_org_id: candidate.orgId, p_candidate: candidate }); }
  async getControl(orgId: string, automationId: string) { return await this.client.callLibrarianRpc<{ enabled: boolean; paused: boolean }>('linkautowork_librarian_get_control', { p_org_id: orgId, p_automation_id: automationId }); }
  async setControl(orgId: string, automationId: string, enabled: boolean) { await this.client.callLibrarianRpc('linkautowork_librarian_set_control', { p_org_id: orgId, p_automation_id: automationId, p_enabled: enabled }); }
  private one(value: unknown): AutomationImprovementCandidate | undefined { if (Array.isArray(value)) return value[0] as AutomationImprovementCandidate | undefined; return value && typeof value === 'object' ? value as AutomationImprovementCandidate : undefined; }
}

/** Resolves immutable evidence and its authenticated aggregate approval metadata from the durable registry. */
export class SupabaseLibrarianEvidenceResolver implements EvidenceResolver {
  constructor(private readonly client: SupabaseAuditClient) {}
  async resolve(ref: string, requestingOrgId: string): Promise<ResolvedEvidence | undefined> {
    const value = await this.client.callLibrarianRpc<ResolvedEvidence[] | ResolvedEvidence | null>('linkautowork_librarian_resolve_evidence', { p_org_id: requestingOrgId, p_evidence_ref: ref });
    return Array.isArray(value) ? value[0] : value ?? undefined;
  }
}
