import type { CandidatePackage, CandidateValidationResult, CandidateValidator } from './types.js';

/** The narrow command boundary used to integrate WP-02 without importing or editing its implementation. */
export interface Wp02CommandRunner {
  run(packageRoot: string, files: Readonly<Record<string, string>>): Promise<CandidateValidationResult>;
}

/** Converts a supplied WP-02 command runner into the Architect validator interface. */
export function createWp02Validator(runner: Wp02CommandRunner): CandidateValidator {
  return {
    async validate(candidate: CandidatePackage): Promise<CandidateValidationResult> {
      return runner.run(candidate.root, candidate.files);
    },
  };
}
