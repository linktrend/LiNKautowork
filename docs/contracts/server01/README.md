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

## AW08 scoped Product API supplement

File 17, `20260915031350_lautowork_product_api_scoped_runtime.sql`, preserves all
sixteen predecessor migration bytes. It grants the dedicated Product API role the
existing audited RPC entrypoints and adds that role to the organisation transport
guard. It grants neither role inheritance nor table writes nor BYPASSRLS.

Use `PRODUCT_API_RUNTIME_TOKEN` containing a signed PostgREST JWT with role
`svc_lautowork_product_api`. Platform owns issuance/rotation and the PostgREST
role binding. If the hosted API gateway requires a key, supply its publishable
key separately as `PRODUCT_API_API_KEY`. The JWT is never used as an API key or
copied into browser state. Browser identity remains a separate Platform contract.

Apply the full seventeen-file package for a fresh deployment; for an installation
already receipted through file 16, back up, isolated-restore, then apply only file
17. Recovery uses the prior application plus forward-fix; do not run file 16's
disposable down migration after file 17. The scoped SQL fixture proves audited
read/finalization and rejects forged role headers, wrong org and missing audit.

## AW08 live gateway supplement

File 18, `20260915033750_lautowork_gateway_scoped_runtime.sql`, grants the
`svc_lautowork_gateway` role only the existing v2 resolve/accept/callback/pause
RPCs and an org-filtered kill-switch reader. It adds no direct execution-table
write, provisioning, Product API, or operator grant. The first sixteen migration
files remain byte-for-byte unchanged. Fresh deployment applies all eighteen;
an installation receipted through sixteen applies seventeen and eighteen after
backup and isolated restore verification.

The production gateway uses `SUPABASE_RUNTIME_JWT` with role
`svc_lautowork_gateway` and `org_id` equal to `ACTIVE_TENANT_UUID`.
`SUPABASE_API_KEY` is a separate publishable routing key when the API gateway
requires it. Production never loads `SUPABASE_SERVICE_ROLE_KEY`. The minimum
private workflow uses `POST /v2/instances/:instanceId/operations/precheck/execute`
with a certified release and a durable consumer/instance binding. Database
acceptance and idempotency precede the real n8n webhook; the disabled v1
in-memory activation adapter is not live execution evidence.

Production PACI accepts only ES256 `paci+jwt` and the namespaced
`platform.auth-claims/1.1.0` envelope. It verifies matching identities, issuer,
audience, lifetime, `autowork` scope and exact requested operation, then performs
uncached live introspection. The gateway client needs a separately admitted,
org/audience/service-scoped `introspect` grant. Configure the exact client ID,
registered kid, endpoint, and pinned GSM version resource in the production env
contract. Only the runtime signer reads the client PEM via its dedicated ADC
identity. No issuer private key is used. Missing configuration, revocation,
identity mismatch, or unavailable authority prevents dispatch.

File 17 also revokes legacy Product API transport grants. Its scoped role is the
only accepted Product API transport; nested provisioning requires the existing
audit reservation before delegating to the durable command guard. Browser
identity remains separate and is not inferred from machine PACI claims.

## Product API PACI consumer contract

The production Product API now consumes the same canonical Platform envelope
through the maintained `jose` verifier:
ES256, `typ=paci+jwt`, one exact `linkautowork-product-api` audience, the
configured issuer and `ACTIVE_TENANT_UUID`, and exact `autowork` / `read`
claims. It accepts PACI only for organisation-scoped client GET routes. It does
not translate a service identity into client, operator, or approver roles, so
mutations and operator-wide reads remain denied to this least-privilege token.
The explicit `NODE_ENV=test` HS256 fixture boundary is unchanged.

Configure `PRODUCT_API_PACI_JWKS_URL` as exactly
`<issuer>/.well-known/jwks.json` and `PRODUCT_API_PACI_INTROSPECTION_URL` as
exactly `<issuer>/oauth/introspect`. Introspection uses the RFC 7662 form fields
`token`, `token_type_hint=access_token`, `client_id`, `client_assertion_type`,
and an endpoint-bound ES256 `private_key_jwt`. The client key is read only from
the numeric version named by
`PRODUCT_API_PACI_CLIENT_ASSERTION_SECRET_RESOURCE`; the Product API receives
the existing ADC Docker secret and never receives an issuer private key.

Every protected read performs uncached introspection and requires the exact
active response fields and identity binding published by Platform. Inactive or
revoked credentials, malformed responses, identity drift, unknown signing
kids, and JWKS or introspection outages fail closed. `PRODUCT_API_SESSION_URL`
and the former RS256 verifier are unsupported.

Platform must independently admit an org/audience/service/operation-scoped
introspection grant for the Product API client before live use. The inspected
Platform Issue 282 source intentionally denies Product API introspection, and
the inspected Issue 290 ref does not yet contain a successor grant. This source
checkpoint therefore makes no live-readiness or deployment claim.
