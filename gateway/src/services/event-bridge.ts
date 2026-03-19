import type { EventPublishRequest, MissionEnvelope } from '../contracts/types.js';
import type { AppEnv } from '../config/env.js';
import { NatsPublisher } from '../integrations/nats-client.js';
import { logWarn } from '../lib/logger.js';

export type EventType = EventPublishRequest['eventType'];

const SUBJECT_MAP: Record<EventType, { primary: string; mirror: string }> = {
  'ritual.strategic': {
    primary: 'aios.ritual.strategic',
    mirror: 'linkautowork.v1.ritual.strategic',
  },
  'ritual.operational': {
    primary: 'aios.ritual.operational',
    mirror: 'linkautowork.v1.ritual.operational',
  },
  'ritual.quality': {
    primary: 'aios.ritual.quality',
    mirror: 'linkautowork.v1.ritual.quality',
  },
  'workflow.execution': {
    primary: 'aios.workflow.execution',
    mirror: 'linkautowork.v1.workflow.execution',
  },
  'security.exception': {
    primary: 'aios.security.exception',
    mirror: 'linkautowork.v1.security.exception',
  },
  killswitch: {
    primary: 'aios.killswitch',
    mirror: 'linkautowork.v1.killswitch',
  },
  'lifecycle.transition': {
    primary: 'aios.lifecycle.transition',
    mirror: 'linkautowork.v1.lifecycle.transition',
  },
};

export function subjectsForEvent(eventType: EventType, includeMirror: boolean): string[] {
  const mapping = SUBJECT_MAP[eventType];
  return includeMirror ? [mapping.primary, mapping.mirror] : [mapping.primary];
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
    const subjects = subjectsForEvent(args.eventType, this.env.enableInternalMirrorSubjects);
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
