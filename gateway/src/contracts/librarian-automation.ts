import { z } from 'zod';

const digest = z.string().regex(/^sha256:[a-f0-9]{64}$/);
const evidenceRef = z.string().regex(/^evidence:\/\/[A-Za-z0-9._~\/-]+$/).max(512);

export const librarianCandidateStatus = z.enum([
  'proposed', 'validation_failed', 'ready_for_eval', 'eval_failed', 'awaiting_review', 'approved', 'rejected', 'superseded',
]);
export const librarianTrigger = z.enum([
  'repeated_deterministic_failure', 'slo_regression', 'incident_closure', 'dependency_deprecation', 'operator_feedback', 'scheduled_review',
]);

const evidenceSchema = z.object({
  ref: evidenceRef,
  hash: digest,
  kind: z.enum(['eval_receipt', 'execution_projection', 'incident', 'maintenance', 'operator_feedback', 'aggregate_measure', 'dependency_notice']),
  orgId: z.string().uuid().optional(),
  aggregateApprovalRef: evidenceRef.optional(),
}).strict().superRefine((value, context) => {
  if (value.orgId === undefined && value.aggregateApprovalRef === undefined) context.addIssue({ code: z.ZodIssueCode.custom, message: 'aggregate evidence needs an authenticated approval reference' });
  if (value.orgId !== undefined && value.aggregateApprovalRef !== undefined) context.addIssue({ code: z.ZodIssueCode.custom, message: 'raw org evidence cannot also claim aggregate approval' });
});

/** Strict automation-only ingress contract; it admits references and hashes, never client payloads or credentials. */
export const librarianAutomationRequestSchema = z.object({
  domain: z.literal('automation'),
  orgId: z.string().uuid(),
  source: z.object({ automationId: z.string().min(3).max(128), version: z.string().min(1).max(64), releaseId: z.string().uuid() }).strict(),
  trigger: librarianTrigger,
  evidence: z.array(evidenceSchema).min(1).max(32),
  proposal: z.object({
    opportunityClass: z.enum(['failure_repair', 'reliability', 'cost', 'compatibility', 'quality', 'security']),
    scope: z.string().min(10).max(2000),
    patch: z.object({ artifactRef: z.string().regex(/^candidate:\/\/[A-Za-z0-9._~\/-]+$/), digest }).strict(),
    packagePath: z.string().regex(/^automations\/(packages|catalog)\/[A-Za-z0-9._~\/-]+$/).max(512),
    expectedBenefit: z.string().min(3).max(1000),
    riskLevel: z.enum(['low', 'medium', 'high']),
    requiredEvalSuites: z.array(z.string().min(1).max(128)).min(1).max(16),
  }).strict(),
  actor: z.object({ id: z.string().min(3).max(256), kind: z.enum(['librarian', 'operator_service']) }).strict(),
  model: z.object({ provider: z.string().min(1).max(128), model: z.string().min(1).max(128), version: z.string().min(1).max(128) }).strict(),
  policyVersion: z.string().min(1).max(128),
  promptVersion: z.string().min(1).max(128),
  toolActivity: z.array(z.enum(['evidence_read', 'candidate_patch_created', 'validator', 'eval_runner'])).max(16),
  usage: z.object({ inputTokens: z.number().int().nonnegative().optional(), outputTokens: z.number().int().nonnegative().optional(), costUsd: z.number().nonnegative().optional() }).strict().optional(),
}).strict();

export const librarianReviewSchema = z.object({
  decision: z.enum(['approved', 'rejected', 'superseded']),
  reason: z.string().min(3).max(1000),
}).strict();

export type LibrarianAutomationRequest = z.infer<typeof librarianAutomationRequestSchema>;
export type LibrarianReview = z.infer<typeof librarianReviewSchema>;
export type LibrarianCandidateStatus = z.infer<typeof librarianCandidateStatus>;
