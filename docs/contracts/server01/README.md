# Server01 live-interface and migration identity package

Status: **SOURCE PACKAGE / LIVE APPLY HOLD**
Packet: AW-01
Package id: `lautowork.server01.migration-identity/1.0.0`

LiNKautowork authors this hashed, ordered, additive package. **LiNKplatform** remains the sole live migration and identity operator. This repository does not apply it to stage or production.

## Inventory (existing Autowork SQL, filename order)

| Order | File | Role in package |
|---|---|---|
| 1 | `supabase/migrations/20260715_000001_lautowork_control_core.sql` | `lautowork` schema, observer/runtime roles, core control tables |
| 2 | `supabase/migrations/20260715_000002_lautowork_n8n_isolation.sql` | empty `lautowork_n8n` + `svc_lautowork_n8n` isolation |
| 3 | `supabase/migrations/20260718_000001_lautowork_control_persistence.sql` | durable control persistence |
| 4 | `supabase/migrations/20260804_000001_lautowork_automation_control_model.sql` | catalogue, instances, secret *references* |
| 5 | `supabase/migrations/20260804_000002_lautowork_wave2_runtime_corrections.sql` | wave-2 corrections |
| 6 | `supabase/migrations/20260804_000003_lautowork_librarian_state.sql` | librarian state |
| 7 | `supabase/migrations/20260804_000004_lautowork_operations_runtime.sql` | operations runtime |
| 8 | `supabase/migrations/20260804_000005_lautowork_product_durability.sql` | Product API durability |
| 9 | `supabase/migrations/20260804_000006_lautowork_product_api_read_models.sql` | Product API reads |
| 10 | `supabase/migrations/20260804_000007_lautowork_commercial_lifecycle.sql` | commercial lifecycle |
| 11 | `supabase/migrations/20260804_000008_lautowork_product_api_closure.sql` | Product API closure |
| 12 | `supabase/migrations/20260804_000010_lautowork_operator_operations.sql` | operator operations |
| 13 | `supabase/migrations/20260804_000011_lautowork_governed_commercial_webhooks.sql` | governed webhooks |
| 14 | `supabase/migrations/20260804_000012_lautowork_durable_audit_outbox.sql` | durable audit outbox |
| 15 | `supabase/migrations/20260813_000001_lautowork_provider_plane.sql` | provider v1 request/attempt/receipt/outbox |
| 16 | `supabase/migrations/20260910_000001_lautowork_server01_live_interfaces.sql` | **AW-01 additive live interfaces** |

There is no `20260804_000009_*` file. Archive/legacy mirrors are not part of this package.

## Additive AW-01 surface

The new migration supplies missing invocation, `PREPARED` intent/outbox, callback/receipt and credential-binding **fields** as dedicated `lautowork.server01_*` relations. It does not rewrite provider-plane RPCs (those remain AW-02 runtime consumers).

Records store opaque refs and `sha256:` digests only.

## Machine-readable identity

See `MIGRATION-PACKAGE.json` for SHA-256 of every ordered SQL file and the recovery/role contracts.

## Conformance

1. Hash-validate `MIGRATION-PACKAGE.json`.
2. Fresh install: apply files 1–16 onto disposable Postgres after a minimal `platform` stub.
3. Upgrade: apply files 1–15 then 16.
4. Run `verification.sql` and `fixtures/server01-conformance.sql`.
5. `lautowork.server01_package_status()` must return `complete`.
6. Partial apply (missing relations or `apply_state=started`) must return `partial` and **stop**.
7. Live fingerprint drift must return `drift` and **stop**.
8. Disposable `migrate:down` of file 16 only.

Existing `npm --prefix packages/automation-contracts run verify:db` remains the predecessor harness (it does not yet list file 16). AW-01 focused tests apply the full package.

## HOLD

Live Platform service registration, PACI issuer/JWKS/introspection, production logins for `lautowork` / `lautowork_n8n`, and governed application receipts remain **HOLD**. Source work uses fakes only.
