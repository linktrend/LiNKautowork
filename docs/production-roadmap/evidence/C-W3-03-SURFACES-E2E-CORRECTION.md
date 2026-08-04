# C-W3-03 — Deployable Operator and Client Surfaces Correction

Date: 2026-08-04
Scope: `apps/operator-console/**` and `apps/web/**` only

## Correction made

The former fixture-led operator page is now an authenticated browser shell. It receives an externally established Platform session at runtime, sends its bearer only to the configured Product API, and calls only the literal finite WP-09 operator routes. It renders typed read, denied, unavailable, success, and correlation states. Confirmation is required before an operator request is sent. Operator incident recovery, provisioning retry, instance pause, and release promotion remain distinct screens and actions; promotion additionally requires the approver role. Secret-shaped records are redacted by the typed API client and no workflow definition or credential is rendered.

The former client-product library is now also a deployable public/client portal shell. It uses `ProductApiHttpAdapter` with an externally established Platform bearer session and a public runtime API-location JSON file. It offers only published products, then performs the explicit local lifecycle calls `order -> subscription -> provisioning request`. The client can pause or resume its own displayed instance. It cannot submit credentials, select a payment provider, promote releases, roll back, or access another organisation.

Both apps now build to their own `dist/` folders, include non-root container images, static Node serving entrypoints, and `/healthz` endpoints. No emitted JavaScript remains beside TypeScript source or tests.

## Validation evidence

Commands completed successfully:

```text
npm --prefix apps/operator-console run typecheck
npm --prefix apps/operator-console run test          # 3 tests passed
npm --prefix apps/operator-console run build
npm --prefix apps/web run typecheck
npm --prefix apps/web run test                       # 10 tests passed
npm --prefix apps/web run build
docker build -f apps/operator-console/Dockerfile -t linkautowork-operator-console:wave3-check .
docker build -f apps/web/Dockerfile -t linkautowork-client-portal:wave3-check .
docker run ... linkautowork-operator-console:wave3-check; curl /healthz  # {"status":"ok"}
docker run ... linkautowork-client-portal:wave3-check; curl /healthz     # {"status":"ok"}
git diff --check -- apps/operator-console apps/web
```

The focused tests cover finite route construction, role denial and approver separation, confirmation/error/redaction/accessibility markers, responsive styles, client lifecycle route selection, absence of credential intake, and absence of client promotion/rollback controls. The existing Product API HTTP integration tests exercise the order, subscription, safe configuration, provisioning, portal, webhook replay, and cross-organisation rejection paths against the local Product API test service.

## Deliberate pre-VPS limits

This is local pre-VPS proof, not live proof. A real Platform issuer/session, production Product API backing store, payment provider, customer identity, and hosted browser URL remain external deployment inputs. The public `runtime-config.json` is deliberately value-free in Git; deployment may set only a public Product API location. Browser sessions must be issued/injected by the Platform host and are never baked into either image.
