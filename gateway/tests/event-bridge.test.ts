import { describe, expect, it } from 'vitest';
import { subjectsForEvent } from '../src/services/event-bridge.js';

describe('subjectsForEvent', () => {
  it('publishes only the supported Linkautowork subject', () => {
    const subjects = subjectsForEvent('workflow.execution');
    expect(subjects).toEqual(['linkautowork.v1.workflow.execution']);
  });

  it('does not expose a compatibility mirror switch', () => {
    const subjects = subjectsForEvent('ritual.operational');
    expect(subjects).toEqual(['linkautowork.v1.ritual.operational']);
  });
});
