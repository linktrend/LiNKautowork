# C-W1-05 correction evidence — callback and event result modes

**Scope:** Close the Wave 1 re-audit gap in package graph validation. No Automation Architect source, database migration, gateway, live workflow, external service, or deployment setting was changed.

## Decision enforced

GAP v0.1 has one concrete asynchronous boundary-free result contract: `synchronous_response` is valid only with a webhook trigger and exactly one n8n Respond to Webhook node. `none` remains valid when that response node is absent.

GAP v0.1 does not yet define a controlled callback emitter or controlled event emitter with governed destinations, authentication, delivery receipts, redaction, and completion semantics. A generic HTTP Request or NATS node is therefore insufficient evidence that the declared result was delivered safely. Packages declaring `callback` or `event` now fail closed with `unsupported_result_behavior`. This is a deliberate availability restriction, not an implied implementation of those modes.

## Regression evidence

The catalogue suite contains:

- a positive synchronous webhook graph with exactly one Respond to Webhook node;
- the existing positive inactive `none` Golden package;
- rejection of synchronous mode without the required graph;
- adversarial callback and event workflows containing plausible generic emitter nodes, both rejected without echoing their configured destination in findings.

WP-05 or a later versioned contract may introduce controlled callback/event emitters. That change must define their exact node type, safe parameter invariants, authentication references, durable receipts, and tests before removing this fail-closed gate.

## Validation

- `npm run test:catalog` passed: 37 tests across 8 files.
- `npm run ci` passed end to end: legacy and GAP validators, deterministic catalogue check, 37 root tests, 17 Automation Architect tests, 3 Automation Contracts tests, and all three TypeScript typechecks.
- The established mocked audit-RPC warning appeared during the root Vitest run; it did not fail a test and is unrelated to this correction.
