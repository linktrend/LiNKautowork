import { z } from 'zod';

const digest = z.string().regex(/^sha256:[a-f0-9]{64}$/);
const evidenceReference = z.string().regex(/^evidence:\/\/[A-Za-z0-9._~\/-]+$/).max(512);

/** The only execution evidence accepted from a controlled runtime callback. */
export const executionCallbackSchema = z.object({
  orgId: z.string().uuid(),
  executionId: z.string().uuid(),
  sequence: z.number().int().positive(),
  eventType: z.enum(['accepted', 'started', 'checkpoint', 'succeeded', 'failed', 'cancelled', 'timed_out']),
  occurredAt: z.string().datetime(),
  payloadDigest: digest.nullable().optional(),
  evidenceRef: evidenceReference.nullable().optional(),
}).strict();

export type ExecutionCallback = z.infer<typeof executionCallbackSchema>;
