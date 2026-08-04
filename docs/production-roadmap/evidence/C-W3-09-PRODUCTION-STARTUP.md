# C-W3-09 Product API production startup correction

Date: 2026-08-04 14:48 Asia/Taipei
Scope: Wave 3 blocker 1 only — Product API production constructor origin wiring.

## Correction

`createProductionServer` now requires and copies the two deploy-time browser
origins into `ProductApiEnv`:

- `PRODUCT_API_CLIENT_ORIGIN` → `publicClientOrigin`
- `PRODUCT_API_OPERATOR_ORIGIN` → `operatorConsoleOrigin`

Both values are required before the production app is constructed. This keeps
the existing production CORS guard fail-closed and preserves separate client
and operator browser origins. No Product API service, migration, operator, or
web surface was changed.

## Regression and local validation

The bounded regression constructs the production server from `process.env` with
separate origins and verifies that either missing origin fails before app
construction. It uses dummy local URLs only as constructor configuration; no
external request is made.

```text
npm --prefix apps/product-api run test -- --run tests/server.test.ts   PASS (2 tests)
npm --prefix apps/product-api run typecheck                           PASS
npm --prefix apps/product-api run build:production                    PASS
docker compose --project-directory . --file deploy/prod/docker-compose.yml \
  --env-file deploy/prod/.env.example config                         PASS
git diff --check                                                       PASS
```

Compose rendering confirmed the `product-api` service receives both
`PRODUCT_API_CLIENT_ORIGIN` and `PRODUCT_API_OPERATOR_ORIGIN` as distinct
values. The render emitted the expected blank-value warnings for unavailable
pre-VPS secrets (`SUPABASE_DB_PASSWORD` and `N8N_ENCRYPTION_KEY`).

## Container boundary

The isolated Luna workspace could not reach Docker Desktop or open a host
listener. After its handoff, the master workspace built the production
Dockerfile, started the exact image with distinct client/operator origins and
local non-live dependency URLs, and received a successful `/healthz` response.
The disposable probe container was then removed.

```text
docker build --tag linkautowork-product-api:w3-09-local \
  --file apps/product-api/Dockerfile .                              PASS
docker run ... linkautowork-product-api:w3-09-local
curl http://127.0.0.1:<ephemeral-port>/healthz                     PASS
```

No live deploy, secret access, migration, external service call, commit, or
push was performed.
