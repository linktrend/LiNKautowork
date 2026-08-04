# C-W2-01 through C-W2-03 — Runtime, Provisioning, and Execution Corrections

## Closed findings

### C-W2-01 — trusted organisation header and broad database access

- Removed trust in `x-platform-org-id`. The test adapter now verifies a signed JWT's algorithm, signature, issuer, audience, expiry/not-before, authenticated service, organisation, and organisation entitlement.
- Production remains fail-closed until the live Platform OIDC verifier is configured; the local HS256 adapter cannot run in production.
- Instance resolution and execution acceptance use narrow SECURITY DEFINER RPCs. Execution acceptance and its first event are one transaction and idempotency is enforced by the durable unique key.
- The custom-schema helper supplies both `Accept-Profile` and `Content-Profile`; runtime mutations no longer use direct table writes.

### C-W2-02 — incomplete runtime and provisioning enforcement

- The server resolves workflow routing, release/deployment state, criticality, timeout, retry count, input schema, configuration digests, and secret references from the bound instance.
- Invocation fails closed for wrong org/service/instance/operation, disabled state, non-certified release, workflow or configuration drift, invalid input, kill switch, and duplicate request.
- Required secrets remain references. n8n receives a native-credential/broker descriptor, never a resolved raw secret.
- Provisioning is authenticated by the same verified Platform claim, row-locked and replay-safe. It records copy and smoke steps, creates one inactive unique workflow copy, compensates on failure, and atomically activates exactly one deployment only after smoke succeeds.

### C-W2-03 — unauthenticated, memory-only callback projection

- Each accepted execution receives a high-entropy callback capability. Only its SHA-256 digest and bound callback service are stored.
- Callback recording verifies org, execution, service, and token, then appends the event and updates the execution projection transactionally.
- Exact duplicates, conflicts, out-of-order evidence, terminal-state rules, and cross-org attempts are decided from durable rows. A gateway restart therefore does not reset sequence or projection state.

## Adversarial evidence

- `gateway/tests/platform-auth.test.ts`: deterministic signed-payload tampering with the original signature retained, expiry, wrong audience/service, missing org entitlement, and production test-adapter denial. Payload mutation avoids base64url trailing-padding ambiguity in the regression itself.
- `gateway/tests/instance-runtime.test.ts`: cross-system/instance denial, workflow/config drift, schema denial, duplicate suppression, paused/deprecated/kill-switch denial, broker reference dispatch.
- `gateway/tests/execution-service.test.ts`: restart continuity, exact duplicate, conflicting sequence, out-of-order event, wrong callback token, and cross-org denial.
- `gateway/tests/provisioning-service.test.ts`: smoke-before-activation, failure compensation, durable status transition, replay seam.
- `packages/automation-contracts/disposable-db/wave2-runtime-verify.sql`: real PostgreSQL RPC verification for org-scoped resolution, atomic idempotency, callback capability/sequence behavior, durable provisioning steps, one active deployment, replay, and migration rollback.

## Validation

- `npm test -- --run gateway/tests/platform-auth.test.ts gateway/tests/instance-runtime.test.ts gateway/tests/provisioning-service.test.ts gateway/tests/execution-service.test.ts` — PASS, 11 tests.
- Platform JWT tamper regression rerun 10 consecutive times plus one visible targeted run — PASS. The test mutates decoded claims, re-encodes them, and retains the original signature, so rejection cannot depend on unused base64url padding bits.
- `npm run typecheck` — PASS.
- `npm --prefix packages/automation-contracts run verify:db` — PASS, including Wave 2 runtime verification and rollback.
- `npm run ci` — all application/package tests, disposable DB apply/adversarial/rollback checks, smoke/full evals, and restore rehearsal passed. The integrated run then stopped at a concurrent WP-08 type error in `gateway/src/services/monitoring/operations-service.ts` (`fail_over` versus `failover`), outside C-W2-01–03 ownership. WP-05/WP-06 typecheck passed immediately before that parallel change.
- A later integrated `npm run ci` after all Wave 2 lanes settled — PASS: 76 gateway tests, package/librarian suites, disposable database/restore checks, smoke/full evals, restore rehearsal, and all TypeScript checks.

No live database migration, n8n request, GSM access, deploy, commit, or external operation was performed.
