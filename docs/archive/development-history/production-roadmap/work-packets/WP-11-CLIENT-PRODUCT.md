# WP-11 — Public Website, Client Signup, Provisioning, and Portal

## Objective

Build the commercial product surface: clients view specific automation products, sign up for one, complete safe configuration, receive a separately configured workflow instance in the shared managed n8n environment, and monitor that instance through a restricted portal.

## Product rule

This is not an open marketplace where a client browses internal workflow assets and invokes arbitrary automations. LiNKtrend publishes selected products. A client signs up for a specific product. Provisioning then creates and binds that client's own managed instance.

## Dependencies

WP-05 provisioning/instances, WP-08 health/incidents, and WP-09 API/auth. Payment may remain an adapter if the provider/account is not approved, but the durable order and provisioning states must be real and tested.

## Owned paths

- `apps/web/**` for public site and authenticated client portal
- Product/signup/portal UI tests and fixtures
- Payment adapter contract if not already owned by the API

## Required implementation

### Public product site

1. Explain the managed automation service, supported outcome, prerequisites, included operations, data/integration needs, service limitations, pricing presentation source, and support path in plain English.
2. Show only products explicitly marked published. Do not expose internal packages, workflow JSON, n8n URLs, evaluation fixtures, or unpublished roadmap items.
3. Each product page has a stable product/version or offer identity so signup cannot silently switch to a different automation.

### Signup and order/subscription lifecycle

4. Require LiNKplatform authentication at the appropriate boundary and select/verify the organisation through trusted claims.
5. Capture an idempotent order/subscription for one published product/offer and record accepted terms/version. Implement states including `initiated`, `awaiting_payment` or `payment_not_required`, `paid`, `awaiting_configuration`, `provisioning`, `active`, `suspended`, `cancel_requested`, `cancelled`, and `failed` with allowed transitions.
6. Payment webhooks use WP-09 signature, replay, and idempotency controls. A fake provider supports local E2E. No real charge occurs in these waves.
7. Trigger the WP-05 provisioning state machine only after required commercial and configuration gates pass. Browser refresh/retry cannot create duplicate instances.

### Configuration and credential boundary

8. Render configuration from the product/package's safe schema. Separate ordinary settings from credentials and validate server-side.
9. Do not accept credential secrets in normal forms or persist them in the product database. Until approved GSM-based secure intake exists, present an operator-assisted `credentials_required` step without pretending configuration is complete.
10. Show clear provisioning progress and failure/support path without exposing internal stack traces or n8n identifiers.

### Client portal

11. Show the client's subscribed products, instance state, deployed product release label, configuration completeness, health, recent run summaries, approved outputs/downloads, incidents/service notices, and support/cancellation requests.
12. Allow only product-approved actions such as pause/resume, retry an eligible failed run, or update non-secret settings. Every action is scoped, authorised, idempotent where needed, and audited.
13. Do not expose the n8n editor, arbitrary triggers, catalogue search/invocation, raw workflow JSON, secret names/values, cross-client aggregates, or operator/Librarian controls.

## Test matrix

- Published/unpublished product visibility.
- Signup auth, organisation spoofing, terms version, duplicate submit, refresh/retry.
- Fake payment success/failure/duplicate/out-of-order webhook.
- Provisioning success/failure/compensation and one-instance guarantee.
- Safe configuration validation and credential form prohibition.
- Two-client portal isolation and direct URL attempts.
- Allowed/forbidden lifecycle actions.
- Responsive/accessibility, API failure, redacted errors, and browser E2E.

## Acceptance criteria

- A local user can choose one published product, complete a fake commercial flow, and reach one active isolated test instance through the real provisioning state machine.
- A second organisation cannot observe or affect it.
- Duplicate payment or browser actions do not duplicate subscriptions, workflows, schedules, or bindings.
- The portal gives useful operational status without exposing internal automation assets or secrets.
- Credential onboarding is honestly blocked/assisted until the secure live process is approved.

## Evidence required at handoff

End-to-end trace, two-org isolation proof, webhook replay results, provisioning compensation proof, accessibility/browser results, redaction evidence, changed files, and rollback instructions.

## Stop conditions

Do not choose a payment provider, charge money, create live customer accounts, accept real credentials, or publish legal/pricing claims without Principal approval and authoritative inputs.
