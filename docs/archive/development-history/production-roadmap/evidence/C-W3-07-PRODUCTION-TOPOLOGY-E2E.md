# C-W3-07 — production browser topology and durable lifecycle evidence

## Decision implemented

LiNKautowork uses an explicit separate Product API origin. The client portal and
operator console load only non-secret runtime coordinates: the Product API origin,
Platform OIDC issuer, public client ID, and redirect URI. They use Platform OIDC
Authorization Code + PKCE. An access token is held only in page memory. The
`LINKAUTOWORK_*_SESSION` browser globals are accepted only when the served runtime
configuration sets `testMode: true`; production servers always emit `false`.

The Product API allows only the configured client and operator origins. This is not
a wildcard CORS design and no browser token is embedded in source, configuration,
or durable browser storage. Traefik retains three separate HTTPS host routes:
public client, operator console protected by Tailscale, and Product API.

## Durable Chrome proof

The canonical browser launcher now applies the ordered disposable database
migrations through `20260804_000012_lautowork_durable_audit_outbox.sql`, tells
PostgREST to reload its schema, and runs headless local Chrome against distinct UI
and API origins. The audit fixture is created and finalized through the named
`linkautowork_product_reserve_audit` and `linkautowork_product_finalize_audit` RPCs;
the browser still reaches the Product API's normal reservation/finalization
middleware and PostgREST adapter path, with no direct audit-table insert.

The runner records each successfully applied migration and rolls those migrations
back in reverse order on exit, including `000012` before `000011`. Compose resources
use the labelled disposable-browser project and are removed with volumes and
orphans after rollback.

The completed run verified:

- Chrome client portal reaches the separate API origin with exact-origin CORS.
- A double-clicked request uses persistent browser intent/idempotency keys and
  drives durable order, terms acceptance, one subscription, safe configuration,
  and one provisioning request through PostgREST/WP-05.
- Refresh retains only the non-secret signup intent; it does not retain an access
  token. Credential fields do not exist in the customer UI and the UI says that an
  operator completes credential onboarding.
- A client-member receives a Product API 403 and no operator action controls.
- An operator can acknowledge an incident through typed confirmation, reason,
  idempotency and Product API audit receipt; response content is redacted.
- An operator without the approver role sees promotion disabled.
- Responsive mobile viewport and structural accessibility assertions pass.

## Commands and results

```text
npm --prefix apps/web run typecheck                         PASS
npm --prefix apps/operator-console run typecheck            PASS
npm --prefix apps/web run test                              PASS (10)
npm --prefix apps/operator-console run test                 PASS (3)
npm --prefix apps/web run build                             PASS
npm --prefix apps/operator-console run build                PASS
npm --prefix apps/web run test:browser                      PASS (Docker-enabled run)
```

Correction checks on 2026-08-04: `bash -n apps/web/e2e/run-durable-browser-e2e.sh`
and static migration/path/ownership checks passed. The root browser command is
`npm run test:browser`; its rerun may be blocked in this workspace by denied Docker
socket access. The browser command creates an isolated disposable Compose project
and removes it on exit. This is pre-VPS evidence only: it does not prove approved
DNS/TLS, real Platform OIDC configuration, real payment provider credentials, GSM
resolution, or a live VPS deployment.
