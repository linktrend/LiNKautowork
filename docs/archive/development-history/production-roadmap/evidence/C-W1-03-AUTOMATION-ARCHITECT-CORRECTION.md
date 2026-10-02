# C-W1-03 correction evidence — Automation Architect integrity

**Scope:** Wave 1 Sol audit correction. Only the candidate-preparation boundary, intake material, runbook, tests, and this evidence were changed. No catalogue release, live workflow, credential, deployment pointer, certification record, or external service was changed.

## Audit findings resolved

1. `prepareCandidate` now accepts `unknown` and strictly parses it with `ArchitectRequestSchema` before it can call the scaffold or validator. Malformed runtime JavaScript input returns only a machine-validated `stopped` report with `INVALID_REQUEST`.
2. Generated reports and injected validator results are machine-validated. A malformed validator result becomes a failed validation; it cannot become a passing receipt.
3. Source mappings are complete and deterministic. The public report keeps the existing WP-03 actions (`reused_as_reference`, `reimplemented`, `discarded`); the frozen WP-02 provenance contract records their equivalent values (`reference_only`, `reimplemented`, `not_used`). Every provenance mapping includes the exact source digest.
4. Create, adapt, compose, and refine now produce different inactive workflow plan nodes, redacted fixtures, and evaluation cases. Required output fields become the output contract and candidate output assignments. Refine has regression coverage; compose has compatibility coverage.
5. Candidate provenance now meets the frozen WP-02 identity contract: automation ID/version, exact n8n runtime, source records, and full source-to-target mappings. A synchronous response without a webhook is rejected before generation rather than producing an invalid package.

## Validation evidence

| Command | Result |
|---|---|
| `npm --prefix packages/automation-architect run typecheck` | Passed. |
| `npm --prefix packages/automation-architect test` | Passed: 16 tests in 2 files, including malformed runtime input, all four mode behaviours, mapping dispositions, and webhook synchronous responses. |
| `npm run validate:automations` | Passed: zero committed catalogue releases. |
| `git diff --check` | Passed. |

The WP-02 adapter integration test writes each generated candidate to a disposable directory and runs the real exported `validatePackageDirectory` function. It passes for a candidate using the frozen package digest and provenance algorithm.

## Remaining boundary

This is still a candidate-only component. The Architect cannot certify or deploy. WP-06 evaluation, independent review, and controlled promotion remain required for every future candidate.
