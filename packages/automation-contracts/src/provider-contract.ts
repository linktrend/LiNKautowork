import { createHash } from 'node:crypto';
import { z } from 'zod';

/** Immutable version for the bounded Autowork provider contract family. */
export const PROVIDER_CONTRACT_VERSION = '2026-08-13.v1' as const;

const uuid = z.string().uuid();
const iso = z.string().datetime({ offset: true });
const digest = z.string().regex(/^sha256:[a-f0-9]{64}$/, 'must be a sha256 digest');
const opaqueRef = z.string().regex(/^[a-z][a-z0-9+.-]*:\/\/[A-Za-z0-9._~/%:-]+$/, 'must be an opaque reference').max(512);
const boundedText = z.string().min(1).max(256).regex(/^[A-Za-z0-9._:/@-]+$/);
const semver = z.string().regex(/^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?$/);

/** States that describe only an Autowork request or attempt, never consumer-domain authority. */
export const PROVIDER_RUN_STATES = [
  'accepted', 'queued', 'running', 'succeeded', 'failed', 'expired', 'cancelled', 'timed_out',
  'rejected', 'blocked', 'quarantined', 'unavailable', 'contract_incompatible',
] as const;

/** Truthful availability outcomes for an individual provider capability. */
export const PROVIDER_CAPABILITY_STATES = [
  'available', 'degraded', 'offline', 'unauthorized', 'forbidden', 'stale', 'incompatible', 'disabled', 'unavailable', 'hold',
] as const;

/** Supported deterministic operation families; callers cannot name a workflow, command, URL, or agent. */
export const PROVIDER_OPERATION_KINDS = [
  'status_collection', 'precheck', 'evidence_collection', 'notification_delivery', 'external_assistance',
  'artifact_transform', 'media_package', 'outreach_adapter',
] as const;

const platformBindingSchema = z.object({
  org_id: uuid,
  actor_id: boundedText,
  audience: boundedText,
  capability: boundedText,
  credential_id: boundedText,
  binding_id: boundedText,
  issued_at: iso,
  expires_at: iso,
  revocation_ref: opaqueRef,
}).strict();

const immutableReferenceSchema = z.object({
  ref: opaqueRef,
  digest,
  observed_at: iso,
}).strict();

/** An opaque, integrity-bound artifact reference. Payload bytes and private text never travel in this contract. */
export const providerArtifactReferenceSchema = z.object({
  ref: opaqueRef,
  digest,
  media_type: z.string().regex(/^[a-z]+\/[a-z0-9.+-]+$/).max(128),
  byte_size: z.number().int().positive().max(10_000_000),
  provenance_ref: opaqueRef,
  retention_profile_ref: opaqueRef,
  retrieval_authorization_ref: opaqueRef,
}).strict();

const approvalReferenceSchema = z.object({
  approval_ref: opaqueRef,
  approver_id: boundedText,
  credential_id: boundedText,
  binding_id: boundedText,
  role: z.enum(['matter_lawyer', 'tenant_administrator']).optional(),
  expires_at: iso,
}).strict();

const operationPolicySchema = z.object({
  side_effect_class: z.enum(['read_only', 'reversible_external_write', 'irreversible_external_write']),
  approval_requirement: z.enum(['none', 'explicit', 'dual_human']),
  policy_profile_ref: opaqueRef,
  data_classification: z.enum(['public', 'internal', 'confidential_metadata', 'restricted_metadata']),
  rate_policy_ref: opaqueRef.optional(),
  quiet_hour_policy_ref: opaqueRef.optional(),
  suppression_ref: opaqueRef.optional(),
}).strict();

const exactAutomationSchema = z.object({
  automation_id: boundedText,
  version: semver,
  definition_digest: digest,
  configuration_ref: immutableReferenceSchema,
}).strict();

/** A compact, authorization-filtered catalogue row. Discovery does not grant execution authority. */
export const providerCatalogueSummarySchema = z.object({
  automation: exactAutomationSchema,
  owner: boundedText,
  organization_visibility: z.enum(['private', 'organization']),
  purpose: z.string().min(1).max(240),
  operation_kinds: z.array(z.enum(PROVIDER_OPERATION_KINDS)).min(1).max(8),
  side_effect_class: operationPolicySchema.shape.side_effect_class,
  lifecycle: z.enum(['available', 'deprecated', 'disabled', 'revoked']),
  contract_ref: opaqueRef,
}).strict();

/** One exact, progressively disclosed automation definition. */
export const providerCatalogueDetailSchema = providerCatalogueSummarySchema.extend({
  input_schema_ref: immutableReferenceSchema,
  output_schema_ref: immutableReferenceSchema,
  capability_requirement: boundedText,
  retry_policy_ref: opaqueRef,
  cancellation_policy_ref: opaqueRef,
  runbook_ref: opaqueRef,
  evidence_guide_ref: opaqueRef,
}).strict();

/** The bounded invocation submitted by a caller that has already selected an exact automation version. */
export const providerInvocationRequestSchema = z.object({
  contract_version: z.literal(PROVIDER_CONTRACT_VERSION),
  protocol_version: z.string().min(1).max(64),
  request_id: uuid,
  platform: platformBindingSchema,
  automation: exactAutomationSchema,
  operation_kind: z.enum(PROVIDER_OPERATION_KINDS),
  input_ref: immutableReferenceSchema,
  artifact_refs: z.array(providerArtifactReferenceSchema).max(16).default([]),
  result_destination_ref: opaqueRef,
  correlation_refs: z.array(immutableReferenceSchema).min(1).max(8),
  brain_handoff_ref: immutableReferenceSchema.optional(),
  idempotency_key: z.string().min(16).max(160).regex(/^[A-Za-z0-9._:-]+$/),
  expires_at: iso,
  cancellation_requested_at: iso.optional(),
  policy: operationPolicySchema,
  approval_refs: z.array(approvalReferenceSchema).max(2).default([]),
  sanitized_brain_candidate_ref: opaqueRef.optional(),
}).strict().superRefine((value, context) => {
  if (value.policy.approval_requirement === 'explicit' && value.approval_refs.length !== 1) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['approval_refs'], message: 'explicit approval requires exactly one reference' });
  }
  if (value.policy.approval_requirement === 'dual_human') {
    if (value.approval_refs.length !== 2 || new Set(value.approval_refs.map((entry) => entry.approver_id)).size !== 2) {
      context.addIssue({ code: z.ZodIssueCode.custom, path: ['approval_refs'], message: 'dual approval requires two distinct approvers' });
    }
    if (new Set(value.approval_refs.map((entry) => entry.role)).size !== 2 || !value.approval_refs.some((entry) => entry.role === 'matter_lawyer') || !value.approval_refs.some((entry) => entry.role === 'tenant_administrator')) {
      context.addIssue({ code: z.ZodIssueCode.custom, path: ['approval_refs'], message: 'legal promotion requires matter lawyer and tenant administrator approvals' });
    }
    if (!value.sanitized_brain_candidate_ref) {
      context.addIssue({ code: z.ZodIssueCode.custom, path: ['sanitized_brain_candidate_ref'], message: 'dual approval requires a sanitized candidate reference' });
    }
  }
  if (value.operation_kind === 'external_assistance' && !value.brain_handoff_ref) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['brain_handoff_ref'], message: 'external assistance requires an exact Brain handoff reference' });
  }
  if (value.operation_kind === 'outreach_adapter' && !value.policy.suppression_ref) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['policy', 'suppression_ref'], message: 'outreach requires a supplied suppression policy reference' });
  }
});

/** Creates a stable canonical fingerprint used to detect changed-content idempotency conflicts. */
export function providerCanonicalRequestFingerprint(request: z.input<typeof providerInvocationRequestSchema>): string {
  const canonicalize = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(canonicalize);
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value as Record<string, unknown>).sort(([left], [right]) => left.localeCompare(right)).map(([key, entry]) => [key, canonicalize(entry)]));
    return value;
  };
  const canonical = JSON.stringify(canonicalize(providerInvocationRequestSchema.parse(request)));
  return `sha256:${createHash('sha256').update(canonical).digest('hex')}`;
}

/** Fails closed when an idempotency key is replayed with changed canonical request content. */
export function assertProviderIdempotencyFingerprint(existingFingerprint: string, incomingRequest: z.input<typeof providerInvocationRequestSchema>): void {
  if (existingFingerprint !== providerCanonicalRequestFingerprint(incomingRequest)) {
    throw new Error('idempotency key conflicts with changed canonical request content');
  }
}

/** Validates expiry and revocation facts using an injected clock; signature verification remains a Platform dependency. */
export function validateProviderInvocation(request: z.input<typeof providerInvocationRequestSchema>, now = new Date()): z.infer<typeof providerInvocationRequestSchema> {
  const parsed = providerInvocationRequestSchema.parse(request);
  if (new Date(parsed.expires_at) <= now || new Date(parsed.platform.expires_at) <= now) throw new Error('provider request is expired');
  if (parsed.platform.revocation_ref.endsWith('/revoked')) throw new Error('provider identity is revoked');
  return parsed;
}

const boundedEvidenceSchema = z.object({ ref: opaqueRef, digest, classification: z.enum(['public', 'internal', 'confidential_metadata', 'restricted_metadata']) }).strict();
const safeErrorSchema = z.object({ category: z.enum(['validation', 'authorization', 'forbidden', 'expired', 'unavailable', 'incompatible', 'cancelled', 'timeout', 'transient', 'uncertain_outcome']), code: boundedText, retryable: z.boolean() }).strict();

/** Durable, bounded attempt metadata. It describes Autowork mechanics only. */
export const providerAttemptSchema = z.object({ attempt: z.number().int().positive(), state: z.enum(PROVIDER_RUN_STATES), started_at: iso.optional(), finished_at: iso.optional(), backoff_until: iso.optional(), error: safeErrorSchema.optional() }).strict();

/** Immutable result receipt whose evidence is progressive and reference-only. */
export const providerReceiptSchema = z.object({
  contract_version: z.literal(PROVIDER_CONTRACT_VERSION), request_id: uuid, receipt_id: uuid, state: z.enum(PROVIDER_RUN_STATES),
  accepted_at: iso, updated_at: iso, attempt_count: z.number().int().nonnegative(), request_fingerprint: digest,
  automation: exactAutomationSchema, freshness_at: iso.optional(), result_refs: z.array(boundedEvidenceSchema).max(8).default([]),
  evidence_refs: z.array(boundedEvidenceSchema).max(8).default([]), error: safeErrorSchema.optional(), uncertain_outcome: z.boolean().default(false),
}).strict();

/** Authenticated callback that binds a provider result to one request and exact automation configuration. */
export const providerCallbackSchema = z.object({ request_id: uuid, receipt_id: uuid, org_id: uuid, callback_binding_ref: opaqueRef, source_timestamp: iso, receipt: providerReceiptSchema }).strict()
  .superRefine((value, context) => { if (value.request_id !== value.receipt.request_id) context.addIssue({ code: z.ZodIssueCode.custom, path: ['receipt', 'request_id'], message: 'callback receipt must bind to request' }); });

/** Acknowledges a cancellation request without claiming that a completed effect was reversed. */
export const providerCancellationAcknowledgementSchema = z.object({ request_id: uuid, receipt_id: uuid, accepted_at: iso, state: z.enum(['accepted', 'queued', 'running', 'cancelled', 'unavailable']), cancellation_execution_proven: z.literal(false) }).strict();
/** A durable, source-correlated provider event carrying only an immutable payload reference. */
export const providerEventSchema = z.object({ event_id: uuid, source_ref: opaqueRef, cursor: z.string().min(1).max(256), correlation_refs: z.array(immutableReferenceSchema).max(8), occurred_at: iso, type: z.enum(['request', 'attempt', 'receipt', 'notification']), payload_ref: immutableReferenceSchema }).strict();
/** A bounded cursor page with explicit acknowledgement state for restart-safe consumers. */
export const providerCursorPageSchema = z.object({ events: z.array(providerEventSchema).max(100), next_cursor: z.string().max(256).nullable(), acknowledged_cursor: z.string().max(256).nullable() }).strict();
/** A redacted, rate-policy-bound mechanical notification record. */
export const providerNotificationSchema = z.object({ notification_id: uuid, request_id: uuid, recipient_ref: opaqueRef, channel_ref: opaqueRef, rate_policy_ref: opaqueRef, redacted_body_ref: immutableReferenceSchema, state: z.enum(['accepted', 'delivered', 'failed', 'suppressed']), delivery_receipt_ref: opaqueRef.optional() }).strict();

/** Capability-specific status; it is deliberately not a run, authority, readiness, or deployment claim. */
export const providerCapabilityStatusSchema = z.object({ capability: boundedText, state: z.enum(PROVIDER_CAPABILITY_STATES), observed_at: iso, freshness_at: iso.optional(), detail_ref: opaqueRef.optional(), does_not_prove: z.array(z.enum(['automation_run', 'consumer_outcome', 'consumer_gate', 'external_side_effect', 'e2e_readiness', 'production_readiness'])).min(1) }).strict();

/** Parsed, bounded invocation request metadata. */
export type ProviderInvocationRequest = z.infer<typeof providerInvocationRequestSchema>;
/** Parsed immutable provider receipt metadata. */
export type ProviderReceipt = z.infer<typeof providerReceiptSchema>;
