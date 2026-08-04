# WP-09 Product API evidence

The product API is an isolated typed Express boundary at `apps/product-api`. It intentionally offers no n8n proxy, raw catalogue/table endpoint, workflow JSON, secrets, or generic action route.

| Route family | Roles | Boundary |
| --- | --- | --- |
| Public products and signup prerequisites | visitor | published summaries only; configuration remains operator-assisted |
| Client subscriptions, orders, configuration, provisioning, support and instances | client member/admin | organisation derived exclusively from the signed identity and each list is paged; lifecycle writes are bounded/idempotent |
| Operator packages, releases, certification, products, organisations, subscriptions, provisioning, instances/bindings, deployments, executions, health, incidents, maintenance, Librarian candidates and audit evidence | explicit operator/approver | finite literal routes call narrow typed read/action services; no table/path proxy |
| Operator mutation | operator/approver; promotion/approval needs approver | idempotency, state-machine action, expected version and privileged audit |
| Provider status webhook | signed provider only | allow-listed event type, idempotent event retention service contract |

`openapi.json` is generated from the typed route source. Errors use `{ error: { code, message, correlationId } }` and do not expose exceptions, tokens, workflow payloads, or storage details. Input is bounded at 32 KiB, lists have a maximum 100-item page, action/create payloads require idempotency keys, updates require an expected version, and operational updates use explicit service calls.

Validation: `npm --prefix apps/product-api run test` (11 passed) and `npm --prefix apps/product-api run typecheck`. The Product API tests prove forged/expired/wrong-audience/missing-org rejection, client/operator separation and direct arbitrary-route rejection, body organisation spoof rejection, two-organisation isolation, safe client lifecycle intents and support isolation, configuration credential rejection, pagination bounds, idempotency, optimistic conflict, separated approver promotion, audit capture, signed replay-safe webhook acceptance, generated-contract availability, and exact-origin CORS acceptance/refusal.

The local HS256 issuer is test-only. Non-test verification accepts only RS256 with a governed JWKS URL, issuer/audience/expiry/not-before/subject/org claims and a positive injected session/revocation check; it fails closed when those production inputs are absent. Rollback is removal of this additive API package; it owns no migration or live state.
