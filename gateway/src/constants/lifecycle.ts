export const LIFECYCLE_STATES = [
  'draft',
  'dev_tested',
  'qa_approved',
  'ops_approved',
  'prod_deployed',
  'deprecated',
  'archived',
] as const;

export type LifecycleState = (typeof LIFECYCLE_STATES)[number];

export const ALLOWED_LIFECYCLE_TRANSITIONS: Record<LifecycleState, LifecycleState[]> = {
  draft: ['dev_tested'],
  dev_tested: ['qa_approved', 'deprecated'],
  qa_approved: ['ops_approved', 'deprecated'],
  ops_approved: ['prod_deployed', 'deprecated'],
  prod_deployed: ['deprecated'],
  deprecated: ['archived'],
  archived: [],
};
