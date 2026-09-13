import { z } from 'zod';
import {
  assertNoSecretShapedContent,
  providerCallbackSchema,
  providerReceiptSchema,
  type ProviderInvocationRequest,
  type ProviderReceipt,
} from '../../../../packages/automation-contracts/src/index.js';
import { RuntimeDispatchError } from './errors.js';

const uuid = z.string().uuid();
const iso = z.string().datetime({ offset: true });
const digest = z.string().regex(/^sha256:[a-f0-9]{64}$/, 'must be a sha256 digest');
const opaqueRef = z.string().regex(/^[a-z][a-z0-9+.-]*:\/\/[A-Za-z0-9._~/%:-]+$/).max(512);
const n8nExecutionRef = z.string().regex(/^n8n:\/\/[A-Za-z0-9._~/%:-]+$/).max(512);

const terminalOutcomes = ['succeeded', 'failed', 'cancelled', 'timed_out'] as const;

/**
 * Bounded n8n callback ingress. Raw execution payloads, credentials, and logs are rejected.
 * Live n8n delivery is not implied by a valid body.
 */
export const n8nRuntimeCallbackSchema = z.object({
  request_id: uuid,
  receipt_id: uuid,
  org_id: uuid,
  n8n_execution_ref: n8nExecutionRef,
  source_timestamp: iso,
  outcome: z.enum(terminalOutcomes),
  request_fingerprint: digest,
  callback_binding_ref: opaqueRef,
  evidence_ref: opaqueRef.optional(),
  result_ref: opaqueRef.optional(),
}).strict();

/** Parsed bounded n8n callback ingress. */
export type N8nRuntimeCallback = z.infer<typeof n8nRuntimeCallbackSchema>;

const boundedEvidence = (ref: string, digestValue: string) => ({
  ref,
  digest: digestValue,
  classification: 'internal' as const,
});

/**
 * Translates a bounded n8n callback into the AW-02 provider callback schema.
 * Does not contact n8n, providers, or credential stores.
 */
export function bridgeN8nCallbackToProvider(input: unknown, request: ProviderInvocationRequest, fingerprint: string, acceptedAt: string): ReturnType<typeof providerCallbackSchema.parse> {
  try {
    assertNoSecretShapedContent(input);
  } catch {
    throw new RuntimeDispatchError('invalid_callback', 'callback contains secret-shaped content');
  }
  let callback: N8nRuntimeCallback;
  try {
    callback = n8nRuntimeCallbackSchema.parse(input);
  } catch (error) {
    if (error instanceof z.ZodError) {
      throw new RuntimeDispatchError('invalid_callback', error.issues.map((issue) => issue.message).join('; '));
    }
    throw error;
  }
  if (callback.request_id !== request.request_id) {
    throw new RuntimeDispatchError('invalid_callback', 'callback request does not bind to activation');
  }
  if (callback.org_id !== request.platform.org_id) {
    throw new RuntimeDispatchError('forbidden', 'callback organisation does not match activation');
  }
  if (callback.callback_binding_ref !== request.automation.configuration_ref.ref) {
    throw new RuntimeDispatchError('invalid_callback', 'callback configuration binding does not match request');
  }
  if (callback.request_fingerprint !== fingerprint) {
    throw new RuntimeDispatchError('invalid_callback', 'callback receipt fingerprint does not match request');
  }

  const receipt: ProviderReceipt = providerReceiptSchema.parse({
    contract_version: request.contract_version,
    request_id: request.request_id,
    receipt_id: callback.receipt_id,
    state: callback.outcome,
    accepted_at: acceptedAt,
    updated_at: callback.source_timestamp,
    attempt_count: 1,
    request_fingerprint: fingerprint,
    automation: request.automation,
    freshness_at: callback.source_timestamp,
    result_refs: callback.result_ref ? [boundedEvidence(callback.result_ref, callback.request_fingerprint)] : [],
    evidence_refs: [
      boundedEvidence(callback.n8n_execution_ref, callback.request_fingerprint),
      ...(callback.evidence_ref ? [boundedEvidence(callback.evidence_ref, callback.request_fingerprint)] : []),
    ],
    error: callback.outcome === 'failed' || callback.outcome === 'timed_out'
      ? { category: callback.outcome === 'timed_out' ? 'timeout' : 'uncertain_outcome', code: `n8n.${callback.outcome}`, retryable: false }
      : undefined,
    uncertain_outcome: true,
  });

  return providerCallbackSchema.parse({
    request_id: callback.request_id,
    receipt_id: callback.receipt_id,
    org_id: callback.org_id,
    callback_binding_ref: callback.callback_binding_ref,
    source_timestamp: callback.source_timestamp,
    receipt,
  });
}
