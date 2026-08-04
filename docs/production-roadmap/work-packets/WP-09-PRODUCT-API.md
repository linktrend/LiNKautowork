# WP-09 — Organisation-Scoped Product and Operator API

## Objective

Provide one authenticated application API for the public product flow, client portal, and private operator console without exposing n8n, internal catalogue mutation, arbitrary workflow selection, or secret material.

## Dependencies

All Wave 2 lifecycle, execution, health, incident, evaluation, and provisioning contracts.

## Owned paths

- `apps/product-api/**` or the roadmap-approved API boundary
- Shared API contracts under `packages/**`
- Authentication/authorisation middleware and policy tests
- API-focused migrations only if not already owned by WP-04

Do not duplicate gateway execution logic. The product API calls typed internal services; the gateway remains the governed runtime ingress.

## Roles and access model

Use LiNKplatform identity and canonical `org_id`. Required roles are at minimum: unauthenticated visitor, client member, client admin, LiNKtrend operator, and authorised approver. Authentication proves identity; authorisation separately decides what that identity may do.

## Required implementation

1. Verify issuer, audience, signature, expiry, subject, organisation claims, and revocation/session policy according to the LiNKplatform contract. Do not trust an `orgId` submitted in a request body.
2. Implement policy middleware and negative tests for every route. Operator access requires an explicit platform role, not merely membership in a special organisation name.
3. Publish a typed/OpenAPI contract and stable error envelope with correlation ID; redact internals from client errors.
4. Public read endpoints expose only approved commercial product summaries and signup prerequisites, not the internal catalogue, unpublished releases, n8n identifiers, or workflow JSON.
5. Client endpoints provide the caller's subscriptions/orders, instances, configuration schema/status, deployment status, health summary, execution history/status, incident summary, approved outputs, and support requests.
6. Operator endpoints provide package/releases, certification, products, organisations, subscriptions, provisioning jobs, instances/bindings, deployments, executions, health, alerts/incidents, maintenance, Librarian candidates, and audit evidence.
7. Mutations invoke explicit services and state machines. No generic `table/update`, arbitrary path, arbitrary automation ID execution, raw SQL, or n8n proxy route.
8. Add pagination, bounded filters, input size limits, idempotency for creation/action endpoints, optimistic concurrency for operator edits, and rate-limit hooks.
9. Provide safe webhook boundaries for payment/provisioning status if required by WP-11: signature verification, replay protection, idempotency, event retention, and allow-listed event types.
10. Keep secret values out of request/response bodies, logs, analytics, and database records. Until secure credential intake is separately approved, return a required operator-assisted configuration state.
11. Generate audit events for privileged reads and all mutations with actor, org, resource, action, reason/correlation, and outcome.

## Test matrix

- Valid/expired/wrong-audience/forged tokens.
- Missing org claim and body/header org spoofing.
- Cross-org reads and actions rejected.
- Client cannot reach operator or unpublished catalogue routes.
- Operator privilege is explicit and audited.
- Idempotency, replay, concurrency conflict, pagination, validation, size/rate boundaries.
- Errors/logs contain no workflow payloads, secrets, tokens, or stack traces.
- Contract tests against Wave 2 services.

## Acceptance criteria

- Two test organisations can use the same API with proven isolation.
- A client can observe and manage only the safe lifecycle actions for its configured automation instance.
- An operator can follow a product from certified release through provisioning and operations using stable contracts.
- No supported API allows discovery-and-invocation of arbitrary catalogue entries.
- API documentation is generated and checked for drift.

## Evidence required at handoff

Route/role matrix, generated contract, negative authorisation results, redaction test, two-org isolation proof, changed files, and rollback instructions.

## Stop conditions

If the live LiNKplatform token/role contract is unavailable, implement a local standards-based test issuer adapter and mark live auth conformance blocked. Do not invent a permanent identity store or ship a bypass.
