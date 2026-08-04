import { z } from 'zod';

/** Machine-readable schema for an Automation Architect request. */
export const ArchitectRequestSchema = z.object({
  taskId: z.string().regex(/^[a-z][a-z0-9-]{2,62}$/),
  mode: z.enum(['create', 'adapt', 'compose', 'refine']),
  target: z.object({
    automationId: z.string().regex(/^[a-z][a-z0-9-]{2,62}$/),
    version: z.string().regex(/^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/),
    displayName: z.string().min(3).max(160),
    owningProgram: z.string().regex(/^[a-z][a-z0-9-]{1,63}$/),
    classification: z.enum(['internal_only', 'commercial_capable']),
    ownerKind: z.enum(['internal_system', 'commercial_product', 'shared_internal']),
    bindingOperations: z.array(z.string().regex(/^[a-z][a-z0-9._-]{2,127}$/)).min(1),
    sourceGitSha: z.string().regex(/^[a-f0-9]{40}$/),
  }).strict(),
  approvedSources: z.array(z.object({
    sourceId: z.string().regex(/^[a-z][a-z0-9-]{2,62}$/),
    kind: z.enum(['n8n_export', 'make_blueprint', 'zapier_export', 'github_repository', 'open_source_project', 'documented_flow', 'manual_specification']),
    locator: z.string().url(),
    revision: z.string().min(1).max(256),
    content: z.string(),
    licence: z.object({ identifier: z.string().min(1), state: z.enum(['cleared', 'not_applicable', 'unknown', 'restricted']) }).strict(),
    components: z.array(z.object({ reference: z.string().min(1), kind: z.enum(['trigger', 'step', 'condition', 'output', 'integration', 'other']), capability: z.string().optional(), sideEffect: z.string().optional() }).strict()),
  }).strict()),
  requirements: z.object({
    summary: z.string().min(20).max(1200),
    expectedOutput: z.object({ description: z.string().min(3).max(1200), fields: z.array(z.string().regex(/^[a-z][a-z0-9_]{0,63}$/)).min(1).max(64) }).strict().optional(),
    triggerMode: z.enum(['webhook', 'schedule', 'event', 'manual', 'hybrid']),
    resultMode: z.enum(['synchronous_response', 'callback', 'event', 'none']),
    sideEffects: z.array(z.string()).min(1),
    requiredCapabilities: z.array(z.string()),
    requiredSecretReferences: z.array(z.object({ secretRef: z.string().regex(/^[A-Z][A-Z0-9_]{2,127}$/), purpose: z.string().min(3) }).strict()),
    redactedEvidence: z.array(z.object({ reference: z.string().min(1), kind: z.enum(['evaluation', 'incident', 'telemetry', 'api_change', 'approved_requirement']), digest: z.string().optional() }).strict()).optional(),
  }).strict(),
  exclusions: z.array(z.string()),
  runtime: z.object({ engine: z.literal('n8n'), n8nVersion: z.string().regex(/^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/), supportedCapabilities: z.array(z.string()) }).strict(),
  evidenceReferences: z.array(z.object({ reference: z.string().min(1), kind: z.enum(['evaluation', 'incident', 'telemetry', 'api_change', 'approved_requirement']), digest: z.string().optional() }).strict()),
  requestProductionMutation: z.boolean().optional(),
  requestedStatus: z.enum(['candidate', 'certified', 'deployed']).optional(),
  resumeFromTaskId: z.string().regex(/^[a-z][a-z0-9-]{2,62}$/).optional(),
}).strict();

/** Minimal machine-readable report schema that enforces candidate-only terminal states. */
export const ArchitectReportSchema = z.object({
  schemaVersion: z.literal('0.1'),
  taskId: z.string(),
  mode: z.enum(['create', 'adapt', 'compose', 'refine']),
  status: z.enum(['candidate', 'stopped']),
  target: z.object({ automationId: z.string(), version: z.string() }).strict(),
  intake: z.array(z.object({ sourceId: z.string(), contentDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/), archiveDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/).optional(), detectedNodeTypes: z.array(z.string()), componentCount: z.number().int().nonnegative(), secretFindingCount: z.number().int().nonnegative(), customerDataFindingCount: z.number().int().nonnegative(), status: z.enum(['assessed', 'rejected']) }).strict()),
  stopConditions: z.array(z.object({ code: z.enum(['DIRECT_PRODUCTION_MUTATION', 'SELF_CERTIFICATION_REQUEST', 'UNKNOWN_LICENCE', 'RESTRICTED_LICENCE', 'EMBEDDED_SECRET_OR_CUSTOMER_DATA', 'MISSING_EXPECTED_OUTPUT', 'MISSING_GSM_REFERENCE_DESIGN', 'UNSUPPORTED_SIDE_EFFECT', 'UNAVAILABLE_RUNTIME_CAPABILITY', 'MISSING_APPROVED_SOURCE', 'INVALID_MODE_SOURCE_COUNT', 'REFINE_EVIDENCE_REQUIRED', 'INVALID_REQUEST', 'INVALID_SOURCE_MAP', 'UNSUPPORTED_RESULT_MODE']), message: z.string(), sourceId: z.string().optional() }).strict()),
  sourceMap: z.array(z.object({ sourceId: z.string(), sourceComponentRef: z.string(), targetComponentRef: z.string(), action: z.enum(['reused_as_reference', 'reimplemented', 'discarded']), reason: z.string() }).strict()),
  candidate: z.object({ root: z.string(), files: z.record(z.string(), z.string()), packageDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/), workflowDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/) }).strict().optional(),
  validation: z.object({ status: z.enum(['passed', 'failed', 'runner_unavailable']), command: z.string(), findings: z.array(z.string()), receiptRef: z.string().optional() }).strict(),
  regressionAdditions: z.array(z.string()),
  productionMutationPerformed: z.literal(false),
  certificationPerformed: z.literal(false),
  deploymentPerformed: z.literal(false),
  resumeKey: z.string().startsWith('architect:'),
}).strict();
