import { createHash, createHmac, randomUUID, timingSafeEqual } from 'node:crypto';
import type { LibrarianAutomationRequest, LibrarianCandidateStatus, LibrarianReview } from '../../contracts/librarian-automation.js';

export type CandidateAssertion = { text: string; evidenceRefs: string[]; certainty: 'supported' | 'uncertain' };
export type AutomationImprovementCandidate = {
  id: string; deduplicationKey: string; domain: 'automation'; orgId: string;
  source: LibrarianAutomationRequest['source']; trigger: LibrarianAutomationRequest['trigger'];
  evidence: LibrarianAutomationRequest['evidence']; proposal: LibrarianAutomationRequest['proposal'];
  assertions: CandidateAssertion[]; status: LibrarianCandidateStatus; proposerId: string;
  audit: { model: LibrarianAutomationRequest['model']; policyVersion: string; promptVersion: string; toolActivity: string[]; evidenceHashes: string[]; usage?: LibrarianAutomationRequest['usage']; redaction: 'references_only'; transitions: Array<{ status: LibrarianCandidateStatus; actorId: string; at: string; reason: string }> };
};
export type ResolvedEvidence = { ref: string; payload: unknown; hash: string; orgId?: string; aggregateApproval?: { issuer: string; approvalRef: string; deidentified: boolean }; verifierKeyId?: string; verifierKeyRef?: string };

export interface LibrarianCandidateStore {
  findByDeduplicationKey(orgId: string, dedupeKey: string): Promise<AutomationImprovementCandidate | undefined>;
  findById(orgId: string, id: string): Promise<AutomationImprovementCandidate | undefined>;
  save(candidate: AutomationImprovementCandidate): Promise<AutomationImprovementCandidate>;
  getControl(orgId: string, automationId: string): Promise<{ enabled: boolean; paused: boolean }>;
  setControl(orgId: string, automationId: string | '*', enabled: boolean): Promise<void>;
}
export interface EvidenceResolver { resolve(ref: string, requestingOrgId: string): Promise<ResolvedEvidence | undefined>; }
export interface CandidateValidator { validate(candidate: AutomationImprovementCandidate): Promise<{ passed: boolean; evidenceRef: string }>; }
export interface CandidateEvaluator { evaluate(candidate: AutomationImprovementCandidate, evidence: ResolvedEvidence[]): Promise<{ passed: boolean; evidenceRef: string }>; }

function canonical(value: unknown): string { return Array.isArray(value) ? `[${value.map(canonical).join(',')}]` : value && typeof value === 'object' ? `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical((value as Record<string, unknown>)[key])}`).join(',')}}` : JSON.stringify(value); }
export function sha256(value: unknown): string { return `sha256:${createHash('sha256').update(typeof value === 'string' ? value : canonical(value)).digest('hex')}`; }

/** Durable-test store. Production uses the Supabase/RPC adapter; this survives service reconstruction when the same backing object is reused. */
export class DurableMemoryLibrarianStore implements LibrarianCandidateStore {
  constructor(private readonly state = { candidates: new Map<string, AutomationImprovementCandidate>(), controls: new Map<string, boolean>() }) {}
  async findByDeduplicationKey(orgId: string, key: string) { return structuredClone(this.state.candidates.get(`${orgId}:dedup:${key}`)); }
  async findById(orgId: string, id: string) { return structuredClone(this.state.candidates.get(`${orgId}:id:${id}`)); }
  async save(candidate: AutomationImprovementCandidate) { const dedupKey=`${candidate.orgId}:dedup:${candidate.deduplicationKey}`, existing=this.state.candidates.get(dedupKey); if(existing&&existing.id!==candidate.id)return structuredClone(existing); const value=structuredClone(candidate); this.state.candidates.set(dedupKey,value); this.state.candidates.set(`${candidate.orgId}:id:${candidate.id}`,value); return structuredClone(value); }
  async getControl(orgId: string, automationId: string) { return { enabled: this.state.controls.get(`${orgId}:*`) ?? true, paused: this.state.controls.get(`${orgId}:${automationId}`) === false }; }
  async setControl(orgId: string, automationId: string, enabled: boolean) { this.state.controls.set(`${orgId}:${automationId}`, enabled); }
}

/** Executes the real WP-02 package-directory validator through a bounded adapter. */
export class Wp02PackageValidator implements CandidateValidator {
  constructor(private readonly validateDirectory: (packagePath: string) => Promise<{ errors: Array<{ code: string }> }>) {}
  async validate(candidate: AutomationImprovementCandidate) { const result = await this.validateDirectory(candidate.proposal.packagePath); return { passed: result.errors.length === 0, evidenceRef: `evidence://wp02/${candidate.proposal.patch.digest.slice(7)}` }; }
}

export interface ReceiptVerifierKeyProvider { get(keyId: string, keyRef: string): Promise<Buffer | undefined>; }
/** In-memory view of GSM-resolved verifier keys; only governed key references are accepted and no key is persisted. */
export class GovernedReceiptVerifierKeys implements ReceiptVerifierKeyProvider {
  constructor(private readonly values: ReadonlyMap<string,string>){}
  async get(keyId:string,keyRef:string){if(keyRef!==`gsm://linkautowork/eval-receipt-verifier/${keyId}`)return undefined;const value=this.values.get(keyId);return value?Buffer.from(value):undefined;}
}
/** Verifies WP-06's full governed HMAC envelope instead of trusting a self-hashed receipt. */
export class Wp06ReceiptEvaluator implements CandidateEvaluator {
  constructor(private readonly keys: ReceiptVerifierKeyProvider) {}
  async evaluate(candidate: AutomationImprovementCandidate, evidence: ResolvedEvidence[]) {
    const receipts = evidence.filter((item) => candidate.evidence.some((declared) => declared.ref === item.ref && declared.kind === 'eval_receipt'));
    const valid = receipts.find((item) => {
      if (!item.payload || typeof item.payload !== 'object') return false;
      const envelope=item.payload as {receipt?:Record<string,unknown>;verifier?:Record<string,unknown>}; const receipt=envelope.receipt,verifier=envelope.verifier; if(!receipt||!verifier||verifier.algorithm!=='hmac-sha256'||verifier.keyId!==item.verifierKeyId||typeof verifier.signature!=='string'||!item.verifierKeyRef)return false;
      return receipt.verdict === 'passed' && receipt.automationId === candidate.source.automationId && receipt.automationVersion === candidate.source.version && receipt.packageDigest === candidate.proposal.patch.digest;
    });
    if(!valid)return {passed:false,evidenceRef:'evidence://wp06/no-valid-bound-receipt'};
    const envelope=valid.payload as {receipt:Record<string,unknown>;verifier:{keyId:string;signature:string}}; const key=await this.keys.get(envelope.verifier.keyId,valid.verifierKeyRef!); if(!key)return {passed:false,evidenceRef:'evidence://wp06/verifier-key-unavailable'};
    const calculated=Buffer.from(createHmac('sha256',key).update(canonical(envelope.receipt)).digest('hex')); const supplied=Buffer.from(envelope.verifier.signature);
    return {passed:supplied.length===calculated.length&&timingSafeEqual(supplied,calculated),evidenceRef:valid.ref};
  }
}

/** Automation-mode queue with durable controls, verified evidence, and no publish/deploy capability. */
export class AutomationLibrarianService {
  constructor(private readonly store: LibrarianCandidateStore, private readonly resolver: EvidenceResolver, private readonly validator: CandidateValidator, private readonly evaluator: CandidateEvaluator, private readonly trustedAggregateIssuers: ReadonlySet<string>) {}

  async setEnabled(orgId: string, enabled: boolean): Promise<void> { await this.store.setControl(orgId, '*', enabled); }
  async setAutomationPaused(orgId: string, automationId: string, paused: boolean): Promise<void> { await this.store.setControl(orgId, automationId, !paused); }

  async propose(request: LibrarianAutomationRequest, authenticatedActorId = request.actor.id): Promise<{ created: boolean; candidate?: AutomationImprovementCandidate; reason?: string }> {
    if (authenticatedActorId !== request.actor.id) return { created: false, reason: 'actor_claim_mismatch' };
    const control = await this.store.getControl(request.orgId, request.source.automationId);
    if (!control.enabled) return { created: false, reason: 'librarian_disabled_telemetry_retained' };
    if (control.paused) return { created: false, reason: 'automation_paused_telemetry_retained' };
    const resolved = await this.resolveAndVerifyEvidence(request);
    if ('reason' in resolved) return { created: false, reason: resolved.reason };
    const distinct = new Map(resolved.values.map((item) => [item.hash, item]));
    const minimum = request.trigger === 'repeated_deterministic_failure' || request.trigger === 'slo_regression' ? 2 : 1;
    if (distinct.size < minimum) return { created: false, reason: 'trigger_policy_not_met' };
    const evidenceIdentity = [...distinct.values()].map(({ ref, hash }) => ({ ref, hash })).sort((a, b) => a.hash.localeCompare(b.hash));
    const deduplicationKey = sha256({ domain: request.domain, orgId: request.orgId, source: request.source, trigger: request.trigger, evidence: evidenceIdentity, policyVersion: request.policyVersion });
    const duplicate = await this.store.findByDeduplicationKey(request.orgId, deduplicationKey);
    if (duplicate) return { created: false, candidate: duplicate, reason: 'duplicate_evidence' };
    const candidate = this.createCandidate(request, deduplicationKey, authenticatedActorId);
    const reserved = await this.store.save(candidate);
    if (reserved.id !== candidate.id) return { created: false, candidate: reserved, reason: 'duplicate_evidence' };
    const validation = await this.validator.validate(candidate);
    this.transition(candidate, validation.passed ? 'ready_for_eval' : 'validation_failed', 'wp02-validator', validation.evidenceRef); await this.store.save(candidate);
    if (!validation.passed) return { created: true, candidate };
    const evaluation = await this.evaluator.evaluate(candidate, resolved.values);
    this.transition(candidate, evaluation.passed ? 'awaiting_review' : 'eval_failed', 'wp06-receipt-verifier', evaluation.evidenceRef); await this.store.save(candidate);
    return { created: true, candidate };
  }

  async review(orgId: string, candidateId: string, review: LibrarianReview, actor: { id: string; role: 'independent_reviewer' }): Promise<AutomationImprovementCandidate> {
    const candidate = await this.store.findById(orgId, candidateId); if (!candidate) throw new Error('candidate not found in actor organisation');
    if (candidate.status !== 'awaiting_review') throw new Error('candidate is not awaiting independent review');
    if (actor.role !== 'independent_reviewer' || actor.id === candidate.proposerId) throw new Error('proposer cannot approve, reject, supersede, certify, publish, promote, or deploy own candidate');
    this.transition(candidate, review.decision, actor.id, review.reason); await this.store.save(candidate); return candidate;
  }

  private async resolveAndVerifyEvidence(request: LibrarianAutomationRequest): Promise<{ values: ResolvedEvidence[] } | { reason: string }> {
    const values: ResolvedEvidence[] = [];
    for (const declared of request.evidence) {
      const item = await this.resolver.resolve(declared.ref, request.orgId); if (!item) return { reason: 'evidence_not_found' };
      if (item.hash !== declared.hash || sha256(item.payload) !== declared.hash) return { reason: 'evidence_hash_mismatch' };
      if (item.orgId && item.orgId !== request.orgId) return { reason: 'cross_org_raw_evidence_rejected' };
      if (!item.orgId) {
        const approval = item.aggregateApproval;
        if (!approval || !approval.deidentified || approval.approvalRef !== declared.aggregateApprovalRef || !this.trustedAggregateIssuers.has(approval.issuer)) return { reason: 'aggregate_approval_not_authenticated' };
      }
      values.push(item);
    }
    return { values };
  }
  private createCandidate(request: LibrarianAutomationRequest, deduplicationKey: string, proposerId: string): AutomationImprovementCandidate {
    const refs = request.evidence.map((item) => item.ref); return { id: randomUUID(), deduplicationKey, domain: 'automation', orgId: request.orgId, source: request.source, trigger: request.trigger, evidence: request.evidence, proposal: request.proposal, assertions: [{ text: `Proposed ${request.proposal.opportunityClass} change is bounded to ${request.proposal.scope}.`, evidenceRefs: refs, certainty: 'supported' }], status: 'proposed', proposerId, audit: { model: request.model, policyVersion: request.policyVersion, promptVersion: request.promptVersion, toolActivity: request.toolActivity, evidenceHashes: request.evidence.map((item) => item.hash), usage: request.usage, redaction: 'references_only', transitions: [{ status: 'proposed', actorId: proposerId, at: new Date().toISOString(), reason: 'candidate created from verified immutable evidence' }] } };
  }
  private transition(candidate: AutomationImprovementCandidate, status: LibrarianCandidateStatus, actorId: string, reason: string): void { candidate.status = status; candidate.audit.transitions.push({ status, actorId, at: new Date().toISOString(), reason }); }
}
