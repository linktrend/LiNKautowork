# WP-06 — Evaluation and execution telemetry handoff

## Delivered local evidence

- `packages/automation-eval-runner` executes the package suite; it does not certify from fixture presence.
- Each receipt binds package, workflow, suite and fixture digests, Git SHA, pinned n8n image, isolated environment, assertions, redaction policy, timestamps and verdict.
- Smoke selects the first health case; full executes happy path, validation, idempotency, fake-upstream failure, missing-secret, binding denial, dry-run safety, schedule/grace declaration, regression replay, compatibility, and privacy cases.
- A forced deterministic failure produces a failed receipt; a clean re-run demonstrates the fixed replay path.
- Root `npm run ci` and GitHub Actions run evaluator tests plus both `eval:smoke` and `eval:full`; a non-passing receipt exits nonzero and therefore fails certification CI.
- The gateway callback route requires the existing signed-ingress HMAC envelope, validates a strict callback schema, writes through the narrow append-event RPC, and projects only ordered, idempotent, redacted evidence references.

## Boundary and limitation

`deploy/test/docker-compose.yml` pins stock `n8nio/n8n:2.30.0` and a fake upstream with test-only state. The corrected official profiles inspect the image digest, run its version command, import the exact package workflow, execute it, export it, restore it into a fresh disposable volume, and execute the restored workflow. This is local container proof only; it is not VPS, stage, or production proof. See `C-W2-04-C-W2-07-EVAL-RUNTIME-CORRECTION.md` for the remaining synthetic-case boundary.
