# C-W3-05 Durable Browser E2E Correction

The canonical `npm run test:browser` now runs an isolated, loopback-only disposable Postgres/PostgREST project, applies migrations through `20260804_000007`, seeds two organisations plus a published offering, approved instance/release, and incident, reloads the PostgREST schema cache, and drives the compiled client and operator shells with system Chrome.

The browser proof uses `PostgrestProductApiService` and `PostgrestProvisioningAdapter`, not `InMemoryProductApiService`. It proves the public offering, durable order, durable terms acceptance, commercial `initiated -> payment_not_required -> awaiting_configuration` gate, eligible subscription, WP-05 provisioning request, client/operator separation, operator incident acknowledgement, redaction, responsive/a11y shell checks, and promotion separation. The database verification also proves lifecycle replay, invalid/out-of-order rejection, and correct previous-state history. It has no real payment provider, customer identity, credentials, or deployed service.

Validated locally on 2026-08-04:

- `npm --prefix packages/automation-contracts run verify:db` — passed, including apply/rollback and restore.
- `npm --prefix apps/web run test:browser` — passed after the final lifecycle gate linkage.
