# Server01 runtime acceptance fixture

Technical, **source-only** acceptance evidence for AW-04. It is not a production
automation, catalogue offering, or live n8n import.

This fixture proves declared package, instance, binding, invocation, result, and
receipt **behavior** against AW-02 durable admission and AW-03 n8n activation
contracts using **safe mocks**. It never contacts Server01, n8n, credentials,
GSM, providers, or deployment surfaces.

## Layout

- `package/` — inactive Golden Automation Package v0.1 (n8n-core-only, no secrets, no external nodes).
- `HOLD.md` — live, production, and disposable-n8n boundaries that remain HOLD.
- `deploy/test/fixtures/server01-runtime-acceptance/` — mock runtime that evaluates the suite without Docker or n8n.

## Activation

The workflow remains `active: false`. Activation is reserved for AW-08 technical
canary authority. After live acceptance the fixture must be disabled or removed.

## Catalogue

This package is **not** registered under `automations/catalog/`. `npm run catalog:check`
and `npm run validate:automations` continue to cover the production catalogue only.
