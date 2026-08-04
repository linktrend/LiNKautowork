import { z } from 'zod';

const uuid = z.string().uuid();

/** Public v2 invocation deliberately contains no workflow routing or secret controls. */
export const boundInstanceExecuteSchema = z.object({
  idempotencyKey: z.string().min(1).max(255),
  input: z.record(z.string(), z.unknown()).default({}),
}).strict();

export const provisioningRequestSchema = z.object({
  requestRef: z.string().min(1).max(512),
  environment: z.enum(['development', 'stage', 'production']),
}).strict();

export const platformInvocationClaimSchema = z.object({
  orgId: uuid,
  service: z.string().regex(/^[a-z][a-z0-9-]{1,63}$/),
});

export type BoundInstanceExecuteRequest = z.infer<typeof boundInstanceExecuteSchema>;
export type PlatformInvocationClaim = z.infer<typeof platformInvocationClaimSchema>;
