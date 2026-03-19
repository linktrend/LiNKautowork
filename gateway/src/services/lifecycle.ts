import {
  ALLOWED_LIFECYCLE_TRANSITIONS,
  type LifecycleState,
} from '../constants/lifecycle.js';
import { HttpError } from '../lib/http-error.js';

export type LifecycleApprovals = {
  auditorRecommendation: boolean;
  headOfQualityApproved: boolean;
  cooApproved: boolean;
  chairmanApproved: boolean;
};

export function validateLifecycleTransition(args: {
  fromState: LifecycleState;
  toState: LifecycleState;
  protectedAction: boolean;
  approvals: LifecycleApprovals;
}): void {
  const allowedTargets = ALLOWED_LIFECYCLE_TRANSITIONS[args.fromState];
  if (!allowedTargets.includes(args.toState)) {
    throw new HttpError(
      409,
      `invalid lifecycle transition from ${args.fromState} to ${args.toState}`,
    );
  }

  if (args.toState === 'qa_approved') {
    if (!args.approvals.auditorRecommendation || !args.approvals.headOfQualityApproved) {
      throw new HttpError(403, 'qa_approved requires auditor recommendation and Head of Quality approval');
    }
  }

  if (args.toState === 'ops_approved') {
    if (
      !args.approvals.auditorRecommendation ||
      !args.approvals.headOfQualityApproved ||
      !args.approvals.cooApproved
    ) {
      throw new HttpError(403, 'ops_approved requires auditor, Head of Quality, and COO approvals');
    }
  }

  if (args.protectedAction && !args.approvals.chairmanApproved) {
    throw new HttpError(403, 'protected action requires Chairman approval');
  }
}
