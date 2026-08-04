# C-W2-08 and C-W2-09 — Runtime Authorization and Invocation Enforcement

## C-W2-08 closed

- Every SECURITY DEFINER RPC introduced by migration `20260804_000002` now calls the accepted `lautowork.assert_command_authorized` boundary. RPCs addressing an instance, execution, or provisioning request derive the authoritative organisation from that row and reject disagreement with the requested organisation.
- PostgREST runtime requests use the project API key only as `apikey`; `Authorization` carries the separately configured scoped runtime JWT. The JWT's signed `role` and `org_id` claims must match the gateway's `x-link-org-id` consistency header and the addressed record.
- The gateway fails closed when `SUPABASE_RUNTIME_JWT` is absent. It does not silently fall back to the broad service-role bearer credential.
- Execution acceptance uses one `INSERT ... ON CONFLICT DO NOTHING` transaction. A two-session concurrent PostgreSQL test proves one execution and one accepted event for a shared idempotency key; reuse with a different input digest is rejected.
- Input validation now uses Ajv's Draft 2020 implementation in strict mode, covering nested arrays, conditionals, required properties, enumerations, and other full-schema behavior rather than the earlier hand-written subset.
- n8n webhook dispatch receives an AbortSignal. Explicit non-success responses may follow the configured retry policy; timeouts and transport failures are treated as ambiguous and are never retried, preventing duplicate business side effects after an uncancelled/possibly accepted request.

## C-W2-09 closed

- `InstanceRuntimeService` requires an injected durable `PauseReader` and checks it before execution acceptance or n8n dispatch.
- The reader receives the server-derived organisation, automation, and instance identity. `SupabasePauseReader` consumes WP-08's narrow `linkautowork_active_pause(org, automation, instance)` contract, which applies the durable global/organisation/automation/instance hierarchy and returns the active scope/reason.
- Missing pause storage or runtime credentials fail closed; there is no in-memory production fallback.

## Evidence

- `gateway/tests/instance-runtime.test.ts`: Draft 2020 nested conditional validation, durable pause denial before acceptance, AbortSignal timeout, no ambiguous retry, drift/binding/state/kill-switch enforcement.
- `gateway/tests/supabase-runtime-auth.test.ts`: PostgREST-equivalent header verification and missing-scoped-credential fail-closed behavior.
- `packages/automation-contracts/disposable-db/wave2-runtime-verify.sql`: signed-claim/header/record organisation agreement and cross-org denial.
- `packages/automation-contracts/disposable-db/concurrent-accept.sh`: two genuinely concurrent database sessions with one durable acceptance/event outcome.
- `npm test -- --run gateway/tests/instance-runtime.test.ts gateway/tests/supabase-runtime-auth.test.ts gateway/tests/provisioning-service.test.ts gateway/tests/execution-service.test.ts` — PASS, 13 tests.
- `npm run typecheck` — PASS.
- `npm --prefix packages/automation-contracts run verify:db` — PASS, including concurrent acceptance, WP-08 pause storage, restore, and rollback.
- `npm run ci` — PASS: 74 gateway tests, package/librarian suites, both disposable DB/restore passes, smoke and full n8n evals, restore rehearsal, and every TypeScript package check.

No live database, n8n, GSM, deploy, commit, or external system was changed.
