import { describe, expect, it, vi } from 'vitest';
import { KillSwitchService } from '../src/services/killswitch.js';

const mission = {
  tenantId: '00000000-0000-0000-0000-000000000001',
  missionId: 'm-1',
  runId: 'r-1',
  taskId: 't-1',
  dprId: 'd-1',
  triggerSource: 'test',
};

describe('KillSwitchService', () => {
  it('blocks scoped workflow and can release it', async () => {
    const store = {
      writeKillSwitchEvent: vi.fn(async () => undefined),
      listActiveKillSwitches: vi.fn(async () => []),
    };
    const service = new KillSwitchService(
      {
        deactivateAllActiveWorkflows: async () => 0,
      } as never,
      store,
    );

    await service.activateScoped({
      tenantId: mission.tenantId,
      workflowId: 'wf-1',
      reason: 'quality-failure',
      incidentId: 'inc-1',
      mission,
    });

    expect(service.isBlocked(mission.tenantId, 'wf-1')).toEqual({
      blocked: true,
      scope: 'scoped',
      reason: 'quality-failure',
    });
    expect(store.writeKillSwitchEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        scope: 'scoped',
        action: 'activate',
        metadata: { workflow_id: 'wf-1' },
      }),
    );

    await service.releaseScoped(mission.tenantId, 'wf-1', {
      reason: 'resolved',
      incidentId: 'inc-1',
    });
    expect(service.isBlocked(mission.tenantId, 'wf-1')).toEqual({ blocked: false });
    expect(store.writeKillSwitchEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        scope: 'scoped',
        action: 'release',
        metadata: { workflow_id: 'wf-1' },
      }),
    );
  });

  it('activates global kill switch and deactivates workflows', async () => {
    const store = {
      writeKillSwitchEvent: vi.fn(async () => undefined),
      listActiveKillSwitches: vi.fn(async () => []),
    };
    const service = new KillSwitchService(
      {
        deactivateAllActiveWorkflows: async () => 4,
      } as never,
      store,
    );

    const result = await service.activateGlobal({
      reason: 'platform-incident',
      incidentId: 'inc-2',
      mission,
    });

    expect(result).toEqual({ revokedWorkflows: 4 });
    expect(service.isBlocked(mission.tenantId, 'wf-any')).toEqual({
      blocked: true,
      scope: 'global',
      reason: 'platform-incident',
    });
    expect(store.writeKillSwitchEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        scope: 'global',
        action: 'activate',
      }),
    );

    await service.releaseGlobal({
      tenantId: mission.tenantId,
      reason: 'cleared',
      incidentId: 'inc-2',
    });
    expect(service.isBlocked(mission.tenantId, 'wf-any')).toEqual({ blocked: false });
  });

  it('gives the global kill switch precedence over an unaffected scoped path', async () => {
    const service = new KillSwitchService({
      deactivateAllActiveWorkflows: async () => 1,
    } as never);

    await service.activateGlobal({ reason: 'global-halt', incidentId: 'inc-3', mission });

    expect(service.isBlocked(mission.tenantId, 'never-scoped')).toEqual({
      blocked: true,
      scope: 'global',
      reason: 'global-halt',
    });
  });

  it('hydrates active kill switches from the store on boot', async () => {
    const store = {
      writeKillSwitchEvent: vi.fn(async () => undefined),
      listActiveKillSwitches: vi.fn(async () => [
        {
          scope: 'global' as const,
          reason: 'persisted-global',
          incident_id: 'inc-h1',
          org_id: mission.tenantId,
          activated_at: '2026-07-18T00:00:00.000Z',
        },
        {
          scope: 'scoped' as const,
          workflow_id: 'wf-persisted',
          reason: 'persisted-scoped',
          incident_id: 'inc-h2',
          org_id: mission.tenantId,
          activated_at: '2026-07-18T00:00:00.000Z',
        },
      ]),
    };

    const service = new KillSwitchService(
      {
        deactivateAllActiveWorkflows: async () => 0,
      } as never,
      store,
    );

    await service.hydrate();

    expect(service.isBlocked(mission.tenantId, 'any')).toEqual({
      blocked: true,
      scope: 'global',
      reason: 'persisted-global',
    });
  });
});
