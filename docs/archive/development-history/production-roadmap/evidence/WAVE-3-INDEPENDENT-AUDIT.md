# Wave 3 Independent Audit

**Auditor:** separate Codex Sol Medium subagent
**Final verdict:** `PASS_PRE_VPS`
**Scope:** WP-09 through WP-12, all Wave 3 corrections, and closure of the five prior independent-audit blockers
**Candidate:** base SHA `a368a45e164eda92eddf1eccad62e58a7c349399` plus the intentional uncommitted Wave 1-3 candidate worktree
**Live-system changes:** none

## Prior blockers closed

1. The production Product API consumes separate exact client/operator origins, starts from the production container, and fails before listening when a required trusted boundary is absent.
2. The finite operator API and console use durable, resource-specific reads/actions for provisioning, instances, incidents, certification, deployments, maintenance, Librarian candidates, releases, and audit evidence.
3. Orders retain an immutable published-offer snapshot containing the authoritative offering, certified release/digests, terms, commercial descriptor, and configuration schema; later terms/subscription/provisioning must match it.
4. The signed HTTP webhook persists provider timestamp/sequence, performs explicit locked lifecycle transitions, and rejects replay, forgery, stale events, and out-of-order events across restart.
5. Privileged Product API work requires a durable audit reservation. Finalization failure leaves repairable pending evidence and returns `503` rather than claiming an unaudited success.

## Independent proof

- Product API: 24/24 tests, production typecheck, and production build passed.
- Operator console: 4/4 tests, typecheck, and build passed.
- Client application: 10/10 tests, typecheck, and build passed.
- The real Chrome journey passed against disposable Postgres/PostgREST using the same fixed service credential shape as production. It proved delegated organisation scoping, client signup and audited provisioning, operator denial/recovery, provisioning retry, pause/resume, certification separation, canary/promotion/rollback, maintenance, Librarian review, audit evidence, redaction, and cleanup.
- The full disposable database suite passed migration apply, scoped authorization, commercial snapshot and terms/release binding, signed webhook success/failure/replay/restart/forgery/order handling, durable audit outbox, operator actions, restore reconstruction, and reverse rollback.
- `npm run ci`, production Compose rendering, all five production image builds, the Product API container health check, `npm audit --audit-level=high`, `git diff --check`, and labelled disposable-resource reconciliation passed. Dependency audit reported zero vulnerabilities.

## Clarification

If audit storage is unavailable during an unauthorised-role attempt, the request remains denied with `403` but may lack a durable denial record. No privileged handler executes, so this is not a fail-open access path and was not a pre-VPS blocker.

## Remaining deployment gates

Live VPS/Tailscale, DNS/TLS/Traefik, GSM mapping and values, authorised Supabase cloud migration, Platform issuer/JWKS/session endpoints, payment/legal/customer inputs, alert destinations, backup targets, immutable deployment-host image digests, and Principal production approval remain separately gated. `PASS_PRE_VPS` authorises none of them.
