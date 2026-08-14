import { z } from 'zod';

export * from './provider-contract.js';

export const AUTOMATION_RELEASE_LIFECYCLES = [
  'draft',
  'eval_pending',
  'certified',
  'deprecated',
  'retired',
] as const;
export const AUTOMATION_RELEASE_CHANNELS = ['development', 'canary', 'stable'] as const;
export const AUTOMATION_INSTANCE_STATES = [
  'draft',
  'provisioning',
  'ready',
  'active',
  'paused',
  'failed',
  'retired',
] as const;
export const AUTOMATION_EXECUTION_STATUSES = [
  'accepted',
  'started',
  'succeeded',
  'failed',
  'cancelled',
  'timed_out',
] as const;

const uuid = z.string().uuid();
const digest = z.string().regex(/^sha256:[a-f0-9]{64}$/, 'must be a sha256 digest');
const semver = z.string().regex(
  /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/,
  'must be SemVer',
);
const automationId = z.string().regex(/^[a-z][a-z0-9-]{2,62}$/);
const secretReference = z.string().regex(/^[A-Z][A-Z0-9_]{2,127}$/);

const forbiddenSecretKey = /(password|passwd|secret(?!_ref$)|token(?!_ref$)|api[_-]?key|private[_-]?key|credential|connection[_-]?string)/i;
const secretShapedValue = /-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:sk|pk|ghp|xox[baprs])[_-][A-Za-z0-9-]{12,}|(?:^|[^a-z0-9])bearer\s+[A-Za-z0-9._~+\/-]{8,}/i;
const connectionStringSchemes = ['postgres://', 'postgresql://', 'mysql://', 'mongodb://', 'mongodb+srv://', 'redis://', 'amqp://'] as const;

/** Returns whether text embeds a valid supported connection URI with a username and password. */
function containsCredentialedConnectionString(value: string): boolean {
  const normalized = value.toLowerCase();
  for (const scheme of connectionStringSchemes) {
    let start = normalized.indexOf(scheme);
    while (start !== -1) {
      let end = start;
      while (end < value.length && !/[\s"\\]/.test(value[end])) end += 1;
      try {
        const uri = new URL(value.slice(start, end));
        if (uri.username && uri.password) return true;
      } catch {
        // A malformed URI is not treated as a credentialed connection string.
      }
      start = normalized.indexOf(scheme, start + scheme.length);
    }
  }
  return false;
}

/** Rejects recursive key/value structures that could carry a raw credential. */
export function assertNoSecretShapedContent(value: unknown, path = '$'): void {
  if (typeof value === 'string') {
    if (secretShapedValue.test(value) || containsCredentialedConnectionString(value)) {
      throw new Error(`secret-shaped value is forbidden at ${path}`);
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((entry, index) => assertNoSecretShapedContent(entry, `${path}[${index}]`));
    return;
  }
  if (!value || typeof value !== 'object') return;
  for (const [key, entry] of Object.entries(value as Record<string, unknown>)) {
    if (forbiddenSecretKey.test(key) && !key.endsWith('_ref')) {
      throw new Error(`secret-shaped key is forbidden at ${path}.${key}`);
    }
    assertNoSecretShapedContent(entry, `${path}.${key}`);
  }
}

export const automationDefinitionSchema = z.object({
  id: uuid,
  org_id: uuid,
  automation_id: automationId,
  display_name: z.string().min(3).max(160),
  owning_program: z.string().regex(/^[a-z][a-z0-9-]{1,63}$/),
  owner_kind: z.enum(['internal_system', 'commercial_product', 'shared_internal']),
  classification: z.enum(['internal_only', 'commercial_capable']),
});

export const automationReleaseSchema = z.object({
  id: uuid,
  org_id: uuid,
  definition_id: uuid,
  version: semver,
  channel: z.enum(AUTOMATION_RELEASE_CHANNELS),
  lifecycle: z.enum(AUTOMATION_RELEASE_LIFECYCLES),
  package_digest: digest,
  workflow_digest: digest,
  source_git_sha: z.string().regex(/^[a-f0-9]{40}$/),
  n8n_version: semver,
  package_path: z.string().regex(/^(?!\/)(?!.*(?:^|\/)\.\.(?:\/|$))[A-Za-z0-9][A-Za-z0-9._/-]*$/),
});

export const automationInstanceSchema = z.object({
  id: uuid,
  org_id: uuid,
  definition_id: uuid,
  release_id: uuid,
  instance_key: z.string().regex(/^[a-z][a-z0-9-]{2,62}$/),
  state: z.enum(AUTOMATION_INSTANCE_STATES),
  configuration_digest: digest,
  configuration: z.record(z.string(), z.unknown()),
}).superRefine((value, context) => {
  try {
    assertNoSecretShapedContent(value.configuration, '$.configuration');
  } catch (error) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: error instanceof Error ? error.message : 'invalid configuration' });
  }
});

export const automationSecretBindingSchema = z.object({
  id: uuid,
  org_id: uuid,
  instance_id: uuid,
  secret_ref: secretReference,
  purpose: z.string().min(3).max(240),
  scope: z.enum(['instance', 'connector']),
  required: z.boolean(),
  health_state: z.enum(['unknown', 'healthy', 'expiring', 'invalid', 'revoked']),
  expires_at: z.string().datetime().nullable().optional(),
  rotation_due_at: z.string().datetime().nullable().optional(),
}).strict();

export const automationExecutionEventSchema = z.object({
  org_id: uuid,
  execution_id: uuid,
  sequence: z.number().int().positive(),
  event_type: z.enum(['accepted', 'started', 'checkpoint', 'succeeded', 'failed', 'cancelled', 'timed_out']),
  occurred_at: z.string().datetime(),
  payload_digest: digest.nullable().optional(),
  evidence_ref: z.string().max(512).nullable().optional(),
}).strict();

export const certificationRequestSchema = z.object({
  org_id: uuid,
  release_id: uuid,
  evaluator_ref: z.string().min(3).max(512),
  reason: z.string().min(3).max(1000),
}).strict();

export type AutomationDefinition = z.infer<typeof automationDefinitionSchema>;
export type AutomationRelease = z.infer<typeof automationReleaseSchema>;
export type AutomationInstance = z.infer<typeof automationInstanceSchema>;
export type AutomationSecretBinding = z.infer<typeof automationSecretBindingSchema>;
export type AutomationExecutionEvent = z.infer<typeof automationExecutionEventSchema>;
