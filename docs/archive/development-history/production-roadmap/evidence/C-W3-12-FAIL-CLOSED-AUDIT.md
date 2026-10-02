# C-W3-12 — fail-closed privileged Product API audit

Date: 2026-08-04 Asia/Taipei
Scope: Sol Wave 3 blocker 5 / Luna High correction agent D. Privileged Product API access and mutation audit only.

## Outcome

The Product API no longer reports a privileged request before its audit outcome is durably available. Every authenticated client or operator read/action route now reserves an organisation-scoped audit lease before entering the handler. A reservation failure returns `503 audit_unavailable` and the handler is not called. The response is held until the lease is finalized as `allowed` or `denied`.

If finalization is unavailable after the handler has run, the API returns 503 rather than claiming success. The durable reservation remains `pending` and is repairable by the same correlation/action/resource key. Successful replay finalizes the existing row and writes exactly one `product_api_audit_events` record.

Authenticated role denials are recorded as a bounded `authorization.denied` attempt when storage is available. Invalid or unauthenticated requests retain the existing bounded auth error behavior and do not disclose token claims. Public product/signup and signed provider webhook surfaces remain outside privileged user-access auditing.

## Implementation contract

- `apps/product-api/src/app.ts` replaces the asynchronous `res.on('finish')` audit with pre-handler reservation and response-commit finalization. Finalization failures are converted to a bounded 503 response.
- `apps/product-api/src/service.ts` adds `AuditReservationInput`, `AuditReservation`, `reserveAudit`, `finalizeAudit`, and bounded denied-attempt recording. The production adapter now requires a lease before every privileged client/operator read or mutation and calls only audited RPC entry points; the in-memory service exposes forced reservation/finalization failure seams and pending rows for regression proof.
- `apps/product-api/src/postgrest.ts` carries the verified organisation plus audit actor/resource/action/reason/correlation headers to named RPCs and normalizes a configured REST base so `/rest/v1` occurs exactly once.
- `supabase/migrations/20260804_000012_lautowork_durable_audit_outbox.sql` adds `lautowork.product_api_audit_outbox`, unique correlation/action/resource idempotency, strict actor/org/reason/resource/action matching, reservation/finalization RPCs, audited entry points for all privileged client/operator RPCs, and compatibility-context preservation through the operator implementation. Direct client/operator RPCs, direct table access, and the historical fire-and-forget writer are revoked from runtime roles; only audited named RPC execution is granted. The down section drops every new audited entry point, restores the prior authorization function, and restores the pre-migration runtime grants.
- `packages/automation-contracts/disposable-db/audit-outbox-verify.sh` proves legacy direct RPC denial, matching audited client access, PostgREST replay identity, outage failure, restart recovery, visible pending finalization, and one-event completion. `run.sh` applies migration 000012 after 000011, runs the verifier, and rolls 000012 back first.

## Regression coverage

`apps/product-api/tests/app.test.ts` and `apps/product-api/tests/server.test.ts` add:

1. Forced reservation-store failure: pause returns 503, the instance remains active, and no audit success/pending row is created.
2. Forced finalizer failure: pause returns 503 after the mutation, the pending audit lease remains visible, and a same-correlation retry completes it once.
3. Authenticated role denial now expects a bounded denied audit outcome.
4. The production adapter rejects privileged calls without a lease and uses audited RPC names.
5. Production construction captures exactly one `/rest/v1` segment when the environment already supplies the REST base.

## Validation

Passed:

- `npm --prefix apps/product-api run typecheck`
- `npm --prefix apps/product-api run build:production`
- `npm --prefix packages/automation-contracts run typecheck`
- `bash -n packages/automation-contracts/disposable-db/run.sh packages/automation-contracts/disposable-db/audit-outbox-verify.sh`
- `git diff --check` on the owned Product API, migration, verifier, and evidence paths
- Static check confirms no `res.on('finish')` or `service.audit(...)` fire-and-forget path remains in the Product API audit implementation.

Blocked by this CLI environment:

- `npm --prefix apps/product-api run test -- --run`: Supertest cannot bind its ephemeral listener (`listen EPERM: operation not permitted 0.0.0.0`). The suite now includes the prior 18 tests plus the adapter-lease and URL-capture regressions across two files; HTTP tests require a host that permits loopback listeners.
- `npm --prefix packages/automation-contracts run verify:db`: Docker API access is denied at `unix:///Users/linktrend/.docker/run/docker.sock` before Postgres starts. Therefore this checkout does not claim live disposable PostgREST/migration proof here. Rerun the command on a Docker-enabled host; it includes `audit-outbox-verify.sh`.

## Exact correction files

- `apps/product-api/src/app.ts`
- `apps/product-api/src/service.ts`
- `apps/product-api/src/postgrest.ts`
- `apps/product-api/tests/app.test.ts`
- `apps/product-api/tests/server.test.ts`
- `supabase/migrations/20260804_000012_lautowork_durable_audit_outbox.sql`
- `packages/automation-contracts/disposable-db/audit-outbox-verify.sh`
- `docs/production-roadmap/evidence/C-W3-12-FAIL-CLOSED-AUDIT.md`

No live service, secret, migration target, deployment, commit, or push was used. `server.ts`, web/operator UI, migrations 000010/000011, commercial/provider logic, generic operator behavior files, browser scripts, and `run.sh` were not modified. Existing shared dirty-worktree changes were preserved.
