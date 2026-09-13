import { z } from 'zod';
import {
  PROVIDER_CONTRACT_VERSION,
  PROVIDER_RUN_STATES,
  assertProviderIdempotencyFingerprint,
  providerCanonicalRequestFingerprint,
  providerInvocationRequestSchema,
  type ProviderInvocationRequest,
} from './provider-contract.js';

/** Source-only AW-02 persistence packet identity. Stage apply and production remain HOLD. */
export const PROVIDER_PERSISTENCE_CONTRACT_VERSION = 'aw-02.v1' as const;

/** Atomic provider-plane RPCs. They execute as SECURITY INVOKER under the runtime JWT/RLS org claim. */
export const PROVIDER_INVOKER_RPCS = [
  'linkautowork_provider_accept',
  'linkautowork_provider_get_request',
  'linkautowork_provider_transition',
  'linkautowork_provider_write_receipt',
  'linkautowork_provider_admit_callback',
  'linkautowork_provider_append_event',
  'linkautowork_provider_list_events',
  'linkautowork_provider_kill_switch_active',
] as const;

/** Provider RPCs never use SECURITY DEFINER and never grant PUBLIC execute. */
export const PROVIDER_RPC_SECURITY_MODE = 'INVOKER' as const;

/** Outbox kinds stored as durable delivery intent. Live queue drain is HOLD. */
export const PROVIDER_OUTBOX_KINDS = ['event_delivery', 'notification_delivery'] as const;

/** Durable outbox states. `pending` is stored; delivery and DLQ drain are not live behavior. */
export const PROVIDER_OUTBOX_STATES = ['pending', 'delivered', 'failed', 'dlq'] as const;

/** Maximum organisation-scoped event page accepted by the cursor boundary. */
export const PROVIDER_EVENT_PAGE_MAX = 100;

const digest = z.string().regex(/^sha256:[a-f0-9]{64}$/, 'must be a sha256 digest');
const uuid = z.string().uuid();
const opaqueRef = z.string().regex(/^[a-z][a-z0-9+.-]*:\/\/[A-Za-z0-9._~/%:-]+$/).max(512);

/** Runtime JWT/RLS context. Service-role is never a provider-plane invoker. */
export const providerRuntimeInvokerSchema = z.object({
  org_id: uuid,
  jwt_role: z.enum(['runtime']),
  claim_org_id: uuid,
}).strict().superRefine((value, context) => {
  if (value.org_id !== value.claim_org_id) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['claim_org_id'], message: 'runtime JWT organisation claim does not match requested org' });
  }
});

/** Explicitly rejected provider-plane invoker forms, including service-role bypass. */
export const providerForbiddenInvokerSchema = z.object({
  org_id: uuid,
  jwt_role: z.enum(['service_role', 'anon', 'public']),
}).strict();

/** Tenant-isolated durable request row: references, digests, fingerprint, and CAS version only. */
export const providerDurableRequestSchema = z.object({
  request_id: uuid,
  org_id: uuid,
  contract_version: z.literal(PROVIDER_CONTRACT_VERSION),
  automation_id: z.string().min(1).max(64),
  automation_version: z.string().min(1).max(64),
  definition_digest: digest,
  configuration_ref: opaqueRef,
  configuration_digest: digest,
  idempotency_key: z.string().min(16).max(160),
  request_fingerprint: digest,
  operation_kind: z.string().min(1).max(64),
  state: z.enum(PROVIDER_RUN_STATES),
  expected_version: z.number().int().positive(),
  expires_at: z.string().datetime({ offset: true }),
  correlation_ref: opaqueRef,
  handoff_ref: opaqueRef.nullable(),
}).strict();

/** Bounded attempt metadata bound to one request. Job retry and outbox retry stay distinct flags. */
export const providerDurableAttemptSchema = z.object({
  request_id: uuid,
  attempt_number: z.number().int().positive(),
  state: z.enum(PROVIDER_RUN_STATES),
  job_retry: z.boolean(),
  outbox_retry: z.boolean(),
}).strict();

/** Organisation-scoped outbox row. Payload bytes are never stored. */
export const providerDurableOutboxSchema = z.object({
  id: uuid,
  org_id: uuid,
  request_id: uuid,
  kind: z.enum(PROVIDER_OUTBOX_KINDS),
  state: z.enum(PROVIDER_OUTBOX_STATES),
  payload_ref: opaqueRef,
  payload_digest: digest,
  attempt_count: z.number().int().nonnegative(),
}).strict();

export type ProviderRuntimeInvoker = z.infer<typeof providerRuntimeInvokerSchema>;
export type ProviderDurableRequest = z.infer<typeof providerDurableRequestSchema>;
export type ProviderDurableAttempt = z.infer<typeof providerDurableAttemptSchema>;
export type ProviderDurableOutbox = z.infer<typeof providerDurableOutboxSchema>;
export type ProviderInvokerRpcName = (typeof PROVIDER_INVOKER_RPCS)[number];

/** Fails closed unless the caller is a runtime JWT whose org claim matches the requested organisation. */
export function assertProviderRuntimeInvoker(input: unknown): ProviderRuntimeInvoker {
  if (providerForbiddenInvokerSchema.safeParse(input).success) {
    throw new Error('provider RPC forbids service-role or public bypass');
  }
  return providerRuntimeInvokerSchema.parse(input);
}

/** Compares AW-01 canonical fingerprints for one `(org_id, idempotency_key)` logical request. */
export function compareProviderIdempotencyContent(existing: { org_id: string; idempotency_key: string; request_fingerprint: string }, incoming: ProviderInvocationRequest): 'replay' {
  if (existing.org_id !== incoming.platform.org_id) {
    throw new Error('organisation isolation denied');
  }
  if (existing.idempotency_key !== incoming.idempotency_key) {
    throw new Error('idempotency key does not match durable request');
  }
  assertProviderIdempotencyFingerprint(existing.request_fingerprint, incoming);
  return 'replay';
}

/** Builds the AW-02 durable request projection from an AW-01 invocation. Raw payloads are not copied. */
export function projectProviderDurableRequest(request: ProviderInvocationRequest, fingerprint = providerCanonicalRequestFingerprint(request)): ProviderDurableRequest {
  const parsed = providerInvocationRequestSchema.parse(request);
  return providerDurableRequestSchema.parse({
    request_id: parsed.request_id,
    org_id: parsed.platform.org_id,
    contract_version: parsed.contract_version,
    automation_id: parsed.automation.automation_id,
    automation_version: parsed.automation.version,
    definition_digest: parsed.automation.definition_digest,
    configuration_ref: parsed.automation.configuration_ref.ref,
    configuration_digest: parsed.automation.configuration_ref.digest,
    idempotency_key: parsed.idempotency_key,
    request_fingerprint: fingerprint,
    operation_kind: parsed.operation_kind,
    state: 'accepted',
    expected_version: 1,
    expires_at: parsed.expires_at,
    correlation_ref: parsed.correlation_refs[0].ref,
    handoff_ref: parsed.brain_handoff_ref?.ref ?? null,
  });
}

/** Bounds an event list page. Unknown or oversized limits fail closed. */
export function boundProviderEventPageLimit(limit: number): number {
  if (!Number.isInteger(limit) || limit < 1 || limit > PROVIDER_EVENT_PAGE_MAX) {
    throw new Error('event cursor limit must be between 1 and 100');
  }
  return limit;
}
