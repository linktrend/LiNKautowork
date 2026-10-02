# C-W3-11 — operator operations durability correction

Date: 2026-08-04 Asia/Taipei
Scope: Sol Wave 3 blocker 2 / Luna High implementation agent C. Operator dashboard operational completeness only.

## Outcome

The operator console no longer treats declared resources as empty façades. Additive migration `20260804_000010_lautowork_operator_operations.sql` keeps the existing Product API routes and RPC names, but dispatches them through finite resource-specific readers and bounded actions over the durable LiNKautowork control tables.

The implementation does not add a generic table/SQL/workflow proxy, expose raw workflow JSON or secrets, alter commercial migration `000008`, or touch the client web, gateway server, order/terms/webhook paths, or audit middleware.

## Durable resource coverage

| Operator resource | Durable read mapping | Supported action boundary |
|---|---|---|
| packages | automation definitions/latest release | read-only |
| releases | immutable automation releases | read-only; deployment operations are on deployments |
| certification | evaluation runs and release lifecycle | approve only after independent matching evidence |
| products | automation products | read-only |
| organisations | platform organisations | append-only organisation pause/resume control |
| subscriptions | durable product subscriptions | compensation only for failed/provisioning state |
| provisioning-jobs | provisioning requests and step evidence | retry only for requested/failed/awaiting-configuration |
| instances | instances, deployment status, latest health | pause/resume with valid state |
| bindings | enabled bindings | pause/resume |
| deployments | deployment state and workflow reference | canary/promotion/rollback through WP-08 transition authority |
| executions | redacted execution summaries and evidence refs | read-only |
| health | durable health snapshots | read-only |
| incidents | durable incidents | acknowledge/resolve with append-only incident events |
| maintenance | maintenance cases/classification | approved bounded retry or resolve |
| librarian-candidates | candidate status/proposer/evidence projection | approve/reject/supersede with state checks |
| audit-evidence | domain and Product API audit projections | read-only |

Every mutation validates the finite resource/action pair, resolves organisation from the addressed durable record, checks an expected version derived from append-only transition history, supports idempotency, stores actor/reason/from/to/correlation evidence, and appends a domain audit event. The Product API adapter now supplies the verified Platform actor to the RPC. Unsupported actions were removed from the public action matrix rather than returning success.

## Console journeys implemented

- Provisioning queue: inspect durable request/step state and retry a failed state-machine request.
- Instance directory: pause and resume with state-aware controls.
- Certification: operator sees approval disabled; a separately authorised approver can certify only a matching independent evaluation.
- Release/deployment: canary, promotion, and rollback use the existing durable deployment authority, approval, health, sample, and baseline checks.
- Maintenance: approved bounded retry is shown with a reason and confirmation.
- Librarian: candidate review is separate from production rewrite and supports approve/reject/supersede states.
- Incident centre: acknowledge then resolve with durable incident history.
- Audit/system health: reads redacted durable evidence and shows receipts.

The UI now selects actions per record state, scopes confirmation to the selected record, requires a reason and confirmation, disables certification/promotion for non-approvers, and displays the Product API correlation/audit receipt after an action.

## Fixtures and browser proof

`packages/automation-contracts/disposable-db/operator-fixtures.sql` seeds durable records for all 16 declared resources, including a failed provisioning request, evaluation-backed certification candidate, Librarian candidate, maintenance approval, deployment canary candidate, health sample, execution evidence, incident, binding, subscription, and audit-producing controls. It uses existing tables and lineage/state-machine constraints.

The durable browser harness was extended to exercise client lifecycle, operator denial, provisioning retry, instance pause/resume, incident acknowledgement/resolution, certification approval separation, canary/promotion/rollback, maintenance retry, Librarian approval, and audit evidence.

## Validation

Passed:

- `npm --prefix apps/operator-console run typecheck`
- `npm --prefix apps/operator-console run test -- --run` — 3 tests
- `npm --prefix apps/operator-console run build`
- `npm --prefix apps/product-api run typecheck`
- `npm --prefix apps/product-api run build:production`
- `npm --prefix apps/product-api run test -- --run -t 'passes the verified operator actor'` — 1 test
- `npm --prefix apps/web run typecheck`
- `npm --prefix packages/automation-contracts run typecheck`
- `bash -n packages/automation-contracts/disposable-db/run.sh apps/web/e2e/run-durable-browser-e2e.sh`
- scoped `git diff --check`

Blocked by the execution environment:

- `npm --prefix apps/product-api run test -- --run` — Supertest cannot bind its ephemeral listener: `listen EPERM: operation not permitted 0.0.0.0`.
- `npm --prefix packages/automation-contracts run verify:db` — Docker Desktop socket denied: `permission denied ... /Users/linktrend/.docker/run/docker.sock`.
- `npm --prefix apps/web run test:browser` — same Docker socket denial before Postgres/PostgREST startup.

Therefore this handoff records the durable SQL/PostgREST/Chrome commands and fixtures but does not claim a live PostgREST or Chrome pass from this sandbox. The master verification commands are:

```text
npm --prefix packages/automation-contracts run verify:db
npm --prefix apps/web run test:browser
npm --prefix apps/product-api run test -- --run
```

## Changed files owned by this correction

- `supabase/migrations/20260804_000010_lautowork_operator_operations.sql`
- `packages/automation-contracts/disposable-db/operator-fixtures.sql`
- `packages/automation-contracts/disposable-db/operator-verify.sql`
- `packages/automation-contracts/disposable-db/run.sh`
- `apps/product-api/src/contracts.ts`
- `apps/product-api/src/service.ts`
- `apps/product-api/tests/app.test.ts`
- `apps/operator-console/src/api.ts`
- `apps/operator-console/src/console.ts`
- `apps/operator-console/src/app.ts`
- `apps/operator-console/tests/console.test.ts`
- `apps/web/e2e/browser-e2e.ts`
- `apps/web/e2e/run-durable-browser-e2e.sh`
- this evidence file

No live service, secret, migration target, commit, push, deployment, or external communication was performed. The shared dirty worktree contains other agents' changes, including adjacent commercial migrations; those were preserved.
