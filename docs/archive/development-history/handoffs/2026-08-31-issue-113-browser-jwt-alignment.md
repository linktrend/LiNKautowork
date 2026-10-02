# Issue 113 — align durable browser e2e JWT with disposable PostgREST

**Owner:** Grok 4.6 Medium MAX-REFILL-3 (`bc-ec96dca5-24f0-4930-83b3-88c3b54092a0`)
**Date:** 2026-08-31 (UTC)
**Issue:** https://github.com/linktrend/LiNKautowork/issues/113
**Branch:** `issue/113-align-durable-browser-e2e-jwt-with-scanner-safe`
**Base:** protected `development` `4cf82fed26088b822e624df6102e7659ebafaf5b` / tree `9ab6219d041ab5eead3edd39880cff6d1d94454f`

## Preceding terminal result (reused, not re-analysed)

MAX-CONTINUE-3 shipped issue **#112** SHA `a413189f96d6e64675d83a6bc94612700f763a76` as an independent **fail** review of issue **#110** SHA `d88f3d633f2d6878f35405f166c53ad6992e4ac0`. Required rework item 1 was classify CI run `33359302734` (`browser audit fixture RPC failed: 401` / `PGRST301` / `JWSError JWSInvalidSignature`). XPKT-03 HOLD and draft PR **#111** Fast `stale_fixture_declaration` were not reopened.

## Classification (issue 112 item 1)

The JWT 401 is **pre-existing on protected `development`**, not caused by issue 110 installer files.

| Surface | Run | Same excerpt |
|---|---|---|
| `development` merge of PR #108 (`4cf82fe`) | `33243588092` | `browser audit fixture RPC failed: 401` `PGRST301` `JWSError JWSInvalidSignature` |
| issue 110 tip `d88f3d6` | `33359302734` | identical |
| issue 112 review tip `a413189` | `33376429443` | identical |

Last green `LiNKautowork CI` on `development`: run `32115272201` SHA `d0df74321dabc03ed3197395b37d08e91cf47afc` (2026-08-18). Subsequent scanner-safe disposable-DB fixture rewrite left `apps/web/e2e/run-durable-browser-e2e.sh` signing with a retired HMAC literal and exporting a truncated `ltfx.ph.*` placeholder, while `packages/automation-contracts/disposable-db/docker-compose.yml` uses the full scanner-safe `PGRST_JWT_SECRET`.

## This packet

Narrow harness repair only. `.ide-development/` and installer sources are untouched (packageVersion remains 2.5.2). No XPKT-03, no PR #111, no staging/main/production.

Harness now reads `PGRST_JWT_SECRET` from the disposable compose file for both the audit-fixture JWT and `DURABLE_POSTGREST_JWT_SECRET`.

## Focused checks

| Command | Result |
|---|---|
| `bash -n apps/web/e2e/run-durable-browser-e2e.sh` | pass |
| `npm --prefix apps/web run test -- tests/durable-browser-jwt-alignment.test.ts` | pass (1 file / 1 test) |
| `npm run ci` / `npm run test:browser` | not run — Docker unavailable; not Full suite |
| GitHub `validate-and-test` | deferred to issue-branch CI after push |
| Fast fixture ledger | not mutated this packet; unused disposable-db rows remain packager/follow-up |

`.ide-development/` packageVersion remains 2.5.2.
