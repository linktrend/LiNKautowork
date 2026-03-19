import { describe, expect, it } from 'vitest';
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
  it('blocks scoped workflow and can release it', () => {
    const service = new KillSwitchService({
      deactivateAllActiveWorkflows: async () => 0,
    } as never);

    service.activateScoped({
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

    service.releaseScoped(mission.tenantId, 'wf-1');
    expect(service.isBlocked(mission.tenantId, 'wf-1')).toEqual({ blocked: false });
  });

  it('activates global kill switch and deactivates workflows', async () => {
    const service = new KillSwitchService({
      deactivateAllActiveWorkflows: async () => 4,
    } as never);

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
  });
});
