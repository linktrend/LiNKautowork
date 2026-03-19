import { z } from 'zod';
import { LIFECYCLE_STATES } from '../constants/lifecycle.js';

export const missionEnvelopeSchema = z.object({
  tenantId: z.string().uuid(),
  missionId: z.string().min(1),
  runId: z.string().min(1),
  taskId: z.string().min(1),
  dprId: z.string().min(1),
  capabilityId: z.string().min(1).optional(),
  packageId: z.string().min(1).optional(),
  triggerSource: z.string().min(1),
});

export const ingressRequestSchema = z.object({
  mission: missionEnvelopeSchema,
  workflow: z.object({
    id: z.string().min(1),
    path: z.string().min(1).optional(),
    method: z.enum(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']).default('POST'),
    criticality: z.enum(['critical', 'non_critical']).default('non_critical'),
  }),
  payload: z.unknown().optional(),
  requiredSecrets: z.array(z.string().min(1)).default([]),
  idempotencyKey: z.string().min(1),
});

export const eventPublishSchema = z.object({
  eventType: z.enum([
    'ritual.strategic',
    'ritual.operational',
    'ritual.quality',
    'workflow.execution',
    'security.exception',
    'killswitch',
    'lifecycle.transition',
  ]),
  mission: missionEnvelopeSchema,
  payload: z.record(z.string(), z.unknown()).default({}),
  status: z.string().min(1).default('ok'),
});

export const lifecycleTransitionSchema = z.object({
  mission: missionEnvelopeSchema,
  workflowId: z.string().min(1),
  fromState: z.enum(LIFECYCLE_STATES),
  toState: z.enum(LIFECYCLE_STATES),
  protectedAction: z.boolean().default(false),
  approvals: z.object({
    auditorRecommendation: z.boolean().default(false),
    headOfQualityApproved: z.boolean().default(false),
    cooApproved: z.boolean().default(false),
    chairmanApproved: z.boolean().default(false),
  }),
  reason: z.string().min(1),
});

export const scopedKillSwitchSchema = z.object({
  mission: missionEnvelopeSchema,
  workflowId: z.string().min(1),
  reason: z.string().min(1),
  incidentId: z.string().min(1),
  action: z.enum(['activate', 'release']),
});

export const globalKillSwitchSchema = z.object({
  mission: missionEnvelopeSchema,
  reason: z.string().min(1),
  incidentId: z.string().min(1),
  action: z.enum(['activate', 'release']),
});

export type MissionEnvelope = z.infer<typeof missionEnvelopeSchema>;
export type IngressRequest = z.infer<typeof ingressRequestSchema>;
export type EventPublishRequest = z.infer<typeof eventPublishSchema>;
export type LifecycleTransitionRequest = z.infer<typeof lifecycleTransitionSchema>;
export type ScopedKillSwitchRequest = z.infer<typeof scopedKillSwitchSchema>;
export type GlobalKillSwitchRequest = z.infer<typeof globalKillSwitchSchema>;
