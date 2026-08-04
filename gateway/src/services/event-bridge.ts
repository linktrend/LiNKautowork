import type { EventPublishRequest, MissionEnvelope } from '../contracts/types.js';
import type { AppEnv } from '../config/env.js';
import { NatsPublisher } from '../integrations/nats-client.js';
import { logWarn } from '../lib/logger.js';

export type EventType = EventPublishRequest['eventType'];

/** The sole supported event namespace. Historical compatibility subjects are retired. */
const SUBJECT_MAP: Record<EventType, string> = {
  'ritual.strategic': 'linkautowork.v1.ritual.strategic',
  'ritual.operational': 'linkautowork.v1.ritual.operational',
  'ritual.quality': 'linkautowork.v1.ritual.quality',
  'workflow.execution': 'linkautowork.v1.workflow.execution',
  'security.exception': 'linkautowork.v1.security.exception',
  killswitch: 'linkautowork.v1.killswitch',
  'lifecycle.transition': 'linkautowork.v1.lifecycle.transition',
};

export function subjectsForEvent(eventType: EventType): string[] {
  return [SUBJECT_MAP[eventType]];
}

export class EventBridgeService {
  constructor(
    private readonly env: AppEnv,
    private readonly nats: NatsPublisher,
  ) {}

  async publish(args: {
    eventType: EventType;
    mission: MissionEnvelope;
    payload: Record<string, unknown>;
    status: string;
  }): Promise<void> {
    const subjects = subjectsForEvent(args.eventType);
    const event = {
      eventType: args.eventType,
      tenantId: args.mission.tenantId,
      tenantSlug: this.env.ACTIVE_TENANT_SLUG,
      missionId: args.mission.missionId,
      runId: args.mission.runId,
      taskId: args.mission.taskId,
      dprId: args.mission.dprId,
      triggerSource: args.mission.triggerSource,
      timestamp: new Date().toISOString(),
      status: args.status,
      payload: args.payload,
    };

    for (const subject of subjects) {
      try {
        await this.nats.publish(subject, event);
      } catch (error) {
        logWarn('failed to publish nats event', {
          subject,
          error: error instanceof Error ? error.message : 'unknown',
        });
      }
    }
  }
}
