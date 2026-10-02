# WP-03 evidence and handoff — Automation Architect and source intake

**Status:** Implemented for source review. C-W1-03 hardens strict public request/report parsing and makes the four modes materially distinct; see `C-W1-03-AUTOMATION-ARCHITECT-CORRECTION.md`. The implementation creates only in-memory candidate Golden Automation Packages. It did not import an n8n workflow, alter a deployment pointer, access a credential, certify a release, or contact an external service.

## Delivered scope

| Path | Purpose |
|---|---|
| `agents/automation-architect/README.md` | Candidate-only AI role boundary and forbidden authority. |
| `packages/automation-architect/src/**` | Machine-readable request/report schemas, deterministic intake scan/hash/metadata helpers, candidate scaffold/digest builder, safety stops, and WP-02 adapter contract. |
| `packages/automation-architect/tests/**` | Create/adapt/compose/refine, licence, secret/customer-data, no-production, resume, schema, hash, and actual WP-02 adapter tests. |
| `automations/intake/_template/**` | Metadata-only quarantined intake template. |
| `automations/fixtures/intake/**` | Sanitized n8n/Make fixtures plus a secret-shaped rejection fixture. |
| `docs/runbooks/AUTOMATION-INTAKE.md` | Intake, stop, resumption, and independent-promotion procedure. |

## Safety evidence

- The only report terminal states are `candidate` and `stopped`; `certified` and `deployed` requests are deterministic stops.
- Every report asserts `productionMutationPerformed: false`, `certificationPerformed: false`, and `deploymentPerformed: false`.
- Unknown/restricted licence, source secret/customer-data findings, missing expected output, unsupported side effect, unavailable runtime capability, invalid source count, missing refine evidence, direct production mutation, and self-certification are hard stops.
- Scaffolds use a new inactive n8n workflow skeleton. Raw source workflow JSON, source credential values, customer data, and unsupported nodes are not copied.
- Compose reports individual provenance and a source-to-target entry for every source, including a source with no declared components.
- Create mode records a LiNKtrend-approved brief as provenance because GAP provenance requires at least one source record.

## Validation and command evidence

| Command | Result |
|---|---|
| `npx tsc --noEmit -p packages/automation-architect/tsconfig.json` | Passed. |
| `npm --prefix packages/automation-architect run typecheck` | Passed. Package-prefixed verification confirms the package-local configuration is portable. |
| `npm --prefix packages/automation-architect test` | Passed: 12 tests in 2 files. Package-prefixed verification confirms the package-local Vitest root is correct. |
| WP-02 `validatePackageDirectory` through an injected adapter and disposable temporary directory | Passed for a generated candidate. No package was committed to `automations/catalog`. |
| `npm run ci` | Passed: legacy template validation, WP-02 empty catalogue validation/index check, 28 existing root tests, root TypeScript check. Existing root CI did not yet include the package-local WP-03 test/typecheck command. |
| `git diff --check` | Passed. |

## WP-02 and WP-06 integration boundary

WP-03 supplies `CandidateValidator` and `createWp02Validator`. It has a real adapter test against WP-02's exported `validatePackageDirectory`, using a disposable directory so candidate files are never added to the live catalogue during testing.

The normal fallback records `runner_unavailable` and names the intended WP-02 command; it never synthesizes a passing receipt. WP-06 has not yet provided an evaluation command, so no evaluation receipt exists and no candidate is certified. This is intentional and remains a Wave 1 follow-up.

## Required integration follow-up

The Wave 1 integration/CI owner must add `packages/automation-architect/tests/**/*.test.ts` and the package typecheck to root CI (and include WP-01 package-contract tests if not already included). This packet did not edit root package or Vitest configuration because they are outside WP-03 ownership.

## Handoff to WP-06 and WP-07

- WP-06 should execute generated candidate GAPs only in a disposable n8n-plus-mock environment and bind evidence to the exact package/workflow/suite/runtime identity.
- WP-07 may consume redacted Architect reports, evaluation results, and incident/telemetry references to propose improvements. It must not grant the Architect self-certification or deployment authority.
- A later publisher may persist an approved candidate in the catalogue only after the relevant package, provenance, validation, independent evaluation, and controlled promotion gates pass.
