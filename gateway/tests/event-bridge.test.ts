import { describe, expect, it } from 'vitest';
import { subjectsForEvent } from '../src/services/event-bridge.js';

describe('subjectsForEvent', () => {
  it('publishes to canonical aios.* and internal mirror when enabled', () => {
    const subjects = subjectsForEvent('workflow.execution', true);
    expect(subjects).toEqual(['aios.workflow.execution', 'linkautowork.v1.workflow.execution']);
  });

  it('publishes only canonical aios.* when mirrors disabled', () => {
    const subjects = subjectsForEvent('ritual.operational', false);
    expect(subjects).toEqual(['aios.ritual.operational']);
  });
});
