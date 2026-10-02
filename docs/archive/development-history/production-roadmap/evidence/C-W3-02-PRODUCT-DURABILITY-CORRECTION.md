# C-W3-02 Product durability correction

Date: 2026-08-04
Scope: WP-09 Product API only; no deployment, secrets, payment execution, or n8n workflow invocation.

## Corrected boundary

- The production server is constructible only with an RS256/JWKS issuer, a positive session/revocation endpoint, a signed webhook secret, and a trusted Product API-to-PostgREST service boundary. Missing values make it exit before listening.
- Browser-facing routes remain finite literal routes. There is no catalogue search, generic table endpoint, SQL proxy, raw credential intake, or payment-charge route.
- Operator actions use a resource-specific allowlist and state transition check. Invalid resource/action pairs and invalid source states reject.
- One correlation identifier is attached once per request. The durable audit hook records one allowed or denied outcome after the response outcome, rather than recording an allowed event before a later failure.
- The webhook handler consumes `express.raw` before JSON parsing and signs exactly the received bytes. Provider receipts are unique by provider event identifier, so replay is durable.
- Orders, subscriptions, terms acceptances, safe configuration submissions, provider event receipts, and Product API audits have additive organization-scoped durable tables/RPCs. The PostgREST adapter calls named RPCs only.
- Provisioning is an adapter to the accepted WP-05 state machine: the product subscription must be operator-assigned to an approved instance and certified release; the request reference is idempotent and `linkautowork_begin_provisioning` is the only start transition. It returns the real state and exposes compensation as `compensation_pending`, never pretending a failed workflow was fixed.

## Validation performed

```text
npm --prefix apps/product-api run test                 PASS (10 tests)
npm --prefix apps/product-api run typecheck            PASS
npm --prefix apps/product-api run build:production     PASS; generated dist removed afterwards
docker build -f apps/product-api/Dockerfile ...        PASS
```

The canonical `npm --prefix packages/automation-contracts run verify:db` runner now applies the migration, executes the Product API durability fixture, exercises a signed PostgREST order RPC and authorization denial, rehearses restart-safe provisioning replay, verifies durable terms/provider receipts, tests cross-organization subscription denial, tests compensation truth, and completes the existing restore/rollback checks. It passed end to end. A direct Org B attempt to create a subscription from an Org A order failed with `order not found in organization`, proving database-side organization isolation rather than relying only on API filtering.

## Limits retained deliberately

This is pre-VPS evidence only. The run did not contact a live identity issuer, Google Secret Manager, payment provider, client, VPS, or n8n tenant. Payment provider events are verified state receipts only; they do not charge, store payment material, or authorize provisioning by themselves.
