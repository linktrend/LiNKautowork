# WP-12 pre-VPS release-readiness handoff

## Delivered

- Eight migrations provide organisation-scoped automation, runtime, Librarian, operations, durable product, finite Product API read/action, commercial lifecycle, and Product API closure contracts.
- Product API, client site, and operator console are runnable non-root services with deterministic builds and health endpoints.
- The canonical real-browser test uses disposable Postgres/PostgREST, durable terms/commercial gates, and the accepted WP-05 provisioning state machine; it is not an in-memory-only demo.
- Production Compose includes persistent NATS JetStream, gateway, private n8n, Product API, public client site, private operator console, migration/publisher jobs, and authenticated operations scheduler. No service is publicly routed inline.
- LiNKaios/AIOS runtime, shim, sync/scaffold, mirror subject, and supported-document references are retired; archives are non-authoritative.
- Recorded local validation covers full CI, real n8n smoke/full evaluation, database restore/rollback, real Chrome E2E, dependency audit, secret/env/release checks, Compose rendering, deterministic image builds, and resource cleanup. This is executable local proof, still awaiting independent Wave 3 audit.

## Do not proceed without

Complete every row of `WP-12-VPS-DEPLOYMENT-INPUT-REGISTER.md`, obtain the independent `PASS_PRE_VPS` verdict, record immutable candidate image digests, and explicitly authorise the named stage target. No document here permits a live migration, GSM action, DNS/TLS change, deployment, payment/customer action, or communication.

## Remaining external boundary

Live LiNKplatform issuer/JWKS/session endpoints, authorised Supabase apply, GSM identity/secret mapping, VPS/Tailscale/Traefik/DNS/TLS, payment provider and approved legal/pricing terms, secure credential onboarding, alert recipients, backup/retention targets, and Principal deployment approval are not present and were not fabricated.
