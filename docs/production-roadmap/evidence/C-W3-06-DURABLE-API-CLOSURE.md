# C-W3-06 Durable Product API Closure

## Scope

This correction closes the independent Wave 3 audit's Product API durability boundary without contacting a live service. It adds additive migration `20260804_000008_lautowork_product_api_closure.sql` and narrows the typed API contract.

## Governed lifecycle

The only client sequence is published offering snapshot → durable order → durable terms acceptance → one governed subscription per order → safe configuration addressed by subscription (the server derives its assigned instance) → one WP-05 provisioning intent. The database enforces organisation scope, source-offer snapshot, approved target release, duplicate/restart-safe terms, subscription and provisioning uniqueness, and rejects credential-shaped configuration.

The order command takes the published offering UUID returned by the published-products read model. The human-facing `offering_key` is catalogue metadata only; it is not the order command identifier. The disposable PostgREST verifier now uses the published UUID and the SQL verifier checks that the immutable offering snapshot is recorded on the order.

Signed provider status events remain a small raw-byte HMAC endpoint. The persisted receipt is replay-safe and advances only the locked commercial lifecycle with an incrementing provider sequence. It has no payment intake, provider credentials, generic table route, or workflow proxy.

## Operator and audit boundary

The migration supplies all named Product API persistence routines, including instance transition, catalogue-offering refusal outside the governed publication workflow, and support requests. Every private named RPC is revoked from `PUBLIC` and granted only to the trusted runtime roles. Instance transitions keep idempotency, org scope, reason, actor reference, from/to state and history. API responses expose a correlation/audit reference; production browser requests fail closed unless both explicit client and operator origins are configured, and CORS never uses a wildcard.

## Local verification

- `npm --prefix apps/product-api test -- --run` — PASS (11 tests), including exact-origin CORS positive/negative cases.
- `npm --prefix apps/product-api run typecheck` — PASS.
- `npm --prefix packages/automation-contracts run verify:db` — PASS from the master workspace: disposable PostgreSQL/PostgREST migration apply, published-offer UUID/snapshot, unknown/unpublished/cross-organisation rejection, terms/subscription/provisioning replay, configuration gating, provider ordering/replay, operator and audit checks, restore rehearsal, and rollback all completed successfully. The isolated Luna correction workspace could not access Docker Desktop, so this authoritative rerun was performed after its handoff.

No VPS, Supabase cloud migration, GSM read, payment, external provider event, customer action, commit, or deployment occurred.
