# WP-06 — Executable Evaluation, Execution Events, and Telemetry

## Objective

Implement real candidate evaluation and trustworthy execution lifecycle evidence. Replace fixture counting and dispatch-only success with hash-bound eval receipts and accepted/started/completed/failed execution events.

## Dependencies

Wave 1 package and data contracts. Integrates with WP-05 instance runtime.

## Owned paths

- `packages/automation-eval-runner/**`
- `deploy/test/**`
- `scripts/run-automation-evals.mjs`
- `gateway/src/services/executions/**`
- `gateway/src/contracts/execution-*.ts`
- Package eval fixtures and tests

## Required implementation

1. Build a disposable pinned-n8n test harness with fake HTTP dependencies and test-only secrets.
2. Execute package eval suites rather than count files. Support happy path, validation, idempotency, retry/upstream failure, missing config/secret, binding/auth failure, dry-run side-effect safety, schedule/SLO, regression replay, compatibility, and privacy/redaction.
3. Convert current dirty-data and known-failure assets only after explicit inputs, expected outputs, assertions, and failure classes exist.
4. Emit immutable receipts binding automation/version, package/workflow/suite/fixture hashes, Git SHA, n8n image, execution environment, observations, assertions, redaction, timestamps, and verdict.
5. Exit nonzero when required cases fail; CI cannot infer certification from file presence.
6. Add signed/schema-validated execution callbacks: accepted, started, checkpoint, succeeded, failed, cancelled, timed_out.
7. Persist idempotent ordered events and derived execution projection. Duplicate/out-of-order callbacks are safely handled and evidenced.
8. Redact sensitive inputs/outputs and store approved evidence references rather than arbitrary payloads.
9. Scheduled definitions declare cadence/grace so WP-08 can detect a missing run.
10. Provide smoke profile for provisioning and full profile for certification/regression.

## Acceptance criteria

- At least one packaged governance automation executes locally in the disposable harness.
- The runner demonstrates a pass, an intentional deterministic failure, and a fixed regression replay.
- Completion evidence is separate from gateway dispatch response.
- Eval receipt cannot be reused for another package hash or n8n version.
- No live external service, client data, or production secret is needed.
- Unit, integration, and CI profiles pass reproducibly.

## Risks

Local execution validates the pinned runtime but is not live environment proof. Every external integration still requires separately authorized stage smoke tests.
