# WP-08 — Durable operational safety evidence

## Scope and safety boundary

WP-08 is wired through authenticated, organisation-bound gateway routes, `OperationsService`, a narrow Supabase adapter, and migration `20260804_000004_lautowork_operations_runtime.sql`. Alerts, incidents, health, maintenance findings, action outcomes, deployment decisions, delivery attempts, and pause records survive gateway restart. No real alert recipient, production credential, destructive probe, or retention decision is selected; tests inject fakes and the production adapter records a durable delivery outbox attempt.

## Scenario results

| Scenario | Local proof |
| --- | --- |
| Missing scheduled run | Declared cadence plus grace with no succeeding execution is unhealthy; one alert and one open incident are produced for the dedupe interval. |
| Success/failure/stale callback | Health derives rates, consecutive failures, duration, retries, queue/callback delay, redacted failure class and explicit unknown state. |
| Alerts/incidents | Alerts dedupe by organisation, instance and routing key; acknowledgement, investigation, recovery and append-only history are covered. |
| Remediation | Only retry, instance pause, explicitly-supported failover and certified rollback are modeled; any unallowed action is rejected and actions retain actor/evidence/before/after/compensation. |
| Canary/rollback | Minimum samples/window, binding compatibility, baseline certification and authorisation gate promotion. Regression returns rollback. Immutable deployment records bind an evidence digest. |
| Pause hierarchy | Global overrides automation, organisation and instance; automation overrides organisation; organisation overrides instance. |
| Restore rehearsal | A disposable, hash-checked reconstruction requires control records, catalogue receipts, and workflow/configuration references. |

## Correction evidence

- Accepted or started executions that never produce a callback become stale; cadence plus grace independently detects a missed business schedule.
- A simulated gateway restart reuses the durable store and does not open or deliver a duplicate alert. Recovery is persisted before the recovery adapter is invoked.
- Action execution calls an injected allow-listed operation. Both success and thrown executor failure are durably audited with actor, reason, evidence, before/after state, result, error summary, and compensation.
- Promotion is rejected without compatible bindings, certified candidate/baseline, minimum sample/time evidence, healthy comparison, and an authorisation evidence reference. Rollback intent is immutable and the runtime rollback RPC restores the latest certified deployment transactionally.
- Global, automation, organisation, and instance pause records always carry `org_id`; database authority and API claims prevent cross-organisation access.
- C-W2-08: every `000004` privileged RPC either directly calls `lautowork.assert_command_authorized` or invokes a narrow helper that does; `PUBLIC` execution is revoked, while the actual gateway `service_role` and `svc_lautowork_runtime` receive explicit execution grants. Disposable SQL switches to `service_role` and successfully calls the exact WP-05 contract `linkautowork_active_pause(p_org_id,p_automation_id,p_instance_id)`.
- C-W2-11: action allow-list, failover support, approval evidence, certification, binding compatibility, canary samples/window, health evidence, baseline and success rates are loaded from durable control rows. The public request schemas contain no authority booleans or caller-supplied metrics.
- Retry is an idempotent durable outbox with claim, delivery lease, completion/failure, attempt count and delayed retry state. A gateway job route dispatches claimed work through n8n and durably completes or fails it.
- Promotion and rollback use the injected n8n adapter to activate the target and deactivate the prior workflow. A partial n8n failure compensates by reversing the switch, and the immutable deployment event records the failure.
- Final correction C makes deployment actuation an explicit two-phase state machine. `prepare` derives and freezes the expected candidate/baseline authority under an advisory lock and idempotency key; n8n actuation occurs next; `commit` atomically changes authoritative deployment states and appends immutable transition/deployment evidence. Resolver-visible database state therefore remains unchanged until commit.
- A committed idempotency key replays its committed record, while a second transition for the same deployment observes `in_progress`. Promotion and rollback use symmetric activation/deactivation. If the database commit fails after n8n succeeds, n8n is restored to the prior active workflow. If that compensation also fails, the transition becomes `compensation_failed` and a durable critical unresolved incident is opened.
- Final correction D gives each instance one independently constrained active baseline and at most one canary. Resolution returns the active baseline as authoritative plus explicit canary deployment/workflow fields. Transition preparation locks and reserves by organisation plus instance, not deployment ID; a real two-session PostgreSQL test proves two different candidate deployment IDs cannot both prepare on the same instance. The disposable lifecycle also commits a canary alongside its active baseline, promotes it, verifies resolver state, and rolls back to the prior certified baseline.

## Example redacted incident timeline

`monitor opened (missing scheduled run)` → `operator acknowledged` → `operator investigating [evidence://ops/one]` → `monitor recovery_notified`.

## Validation

Run `npm test -- --run gateway/tests/operations-service.test.ts`, `npm --prefix packages/automation-operations run test`, `npm run typecheck`, and `npm run restore:rehearse`. The final correction-D disposable run passed the lifecycle, real concurrent-session reservation, PostgREST scope, restore, and migration rollback gates; its reconstructed dump digest was `sha256:2abf9db3e09e38ca46300a3759e5695f73eb1219cd8e24259b5b349b0bfeb9ea`. The restore gate starts disposable PostgreSQL, applies all control migrations, writes catalogue/evaluation/operational rows, exports the `platform` and `lautowork` schemas and data with `pg_dump`, restores them into a fresh database, and verifies reconstructed instances, catalogue releases, WP-06 evaluation receipt references, health, incidents, and pauses. WP-06's later full evaluator gate independently exports/imports n8n workflow state into a fresh n8n volume, so full CI covers both halves of the restore boundary. These are disposable local proofs; they do not prove a live monitor, external delivery, backup target, recovery objective, or production disaster recovery.

## Deployment inputs and rollback

Principal-approved policies are still required for alert recipients, repeat/retention values, real probe endpoints, remediation authority, canary selection/fraction and backup recovery targets. Removing the new package cleanly rolls back this local contract; no live state is created by it.
