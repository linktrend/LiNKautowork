/** Deterministic Automation Architect support for candidate-only Golden Automation Packages. */
export { prepareCandidate, unavailableWp02Validator } from './architect.js';
export { assessSource, canTransitionIntake, extractSourceMetadata, hashIntakeArtifact, intakeStates, scanIntakeContent, sha256 } from './intake.js';
export type { IntakeState } from './intake.js';
export { calculatePackageDigest, scaffoldCandidate } from './candidate.js';
export { ArchitectReportSchema, ArchitectRequestSchema } from './schemas.js';
export { createWp02Validator } from './wp02-adapter.js';
export type { Wp02CommandRunner } from './wp02-adapter.js';
export type * from './types.js';
