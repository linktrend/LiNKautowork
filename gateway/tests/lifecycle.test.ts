import { describe, expect, it } from 'vitest';
import { validateLifecycleTransition } from '../src/services/lifecycle.js';

describe('validateLifecycleTransition', () => {
  it('requires auditor and head of quality for qa_approved', () => {
    expect(() =>
      validateLifecycleTransition({
        fromState: 'dev_tested',
        toState: 'qa_approved',
        protectedAction: false,
        approvals: {
          auditorRecommendation: false,
          headOfQualityApproved: true,
          cooApproved: false,
          chairmanApproved: false,
        },
      }),
    ).toThrow(/qa_approved/);
  });

  it('requires Principal approval for protected actions', () => {
    expect(() =>
      validateLifecycleTransition({
        fromState: 'ops_approved',
        toState: 'prod_deployed',
        protectedAction: true,
        approvals: {
          auditorRecommendation: true,
          headOfQualityApproved: true,
          cooApproved: true,
          chairmanApproved: false,
        },
      }),
    ).toThrow(/Principal/);
  });

  it('accepts a valid ops approval transition', () => {
    expect(() =>
      validateLifecycleTransition({
        fromState: 'qa_approved',
        toState: 'ops_approved',
        protectedAction: false,
        approvals: {
          auditorRecommendation: true,
          headOfQualityApproved: true,
          cooApproved: true,
          chairmanApproved: false,
        },
      }),
    ).not.toThrow();
  });
});
