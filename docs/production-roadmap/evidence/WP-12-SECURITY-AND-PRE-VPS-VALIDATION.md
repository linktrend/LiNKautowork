# WP-12 security and pre-VPS validation ledger

| Gate | Local proof | Live limitation |
| --- | --- | --- |
| Auth and authorisation | gateway signed/service/control claims; WP-09 RS256/JWKS boundary tests | issuer, JWKS, roles, session/revocation source require authority |
| Organisation isolation | gateway, contracts, named Product API RPCs, two-org API/database/browser denial | target database/RLS apply remains blocked |
| SSRF/egress | n8n target is deployment-configured; no generic URL proxy route | outbound allow-list/network policy must be supplied for VPS |
| Webhook/replay/idempotency | HMAC, raw body, nonce window, provider event replay and action idempotency tests | provider secret and delivery endpoint unconfigured |
| Limits/redaction | bounded JSON/rate limits and product API 32 KiB/page bounds; console redaction tests | production log sink/retention policy not selected |
| Secrets | names-only environment contracts, secret scan, runtime env external to repo | no GSM project/identity/value access authorised |
| Container/runtime | gateway non-root, dropped capabilities, no-new-privileges; n8n/NATS private in prod compose; real n8n 2.30.0 import/evaluation on pinned digest | gateway/NATS build digests, host read-only filesystem and network policy need target validation |
| Dependency scan | clean `npm ci` lockfile build and `npm audit --omit=dev` with zero known vulnerabilities | registry result must be repeated for the eventual deployment candidate |
| Backup/restore | all governed migrations through `20260804_000012`, control-data restore and reverse rollback rehearsal | target backup destination and recovery exercise require authority |

## Required local commands

```bash
npm ci
npm run release:check
npm run validate:templates
npm run validate:automations
ops/validate-env-contract.sh
ops/security/scan-secrets.sh
npm audit --omit=dev
npm run ci
docker compose -f deploy/test/docker-compose.yml config
docker compose -f deploy/prod/docker-compose.yml --env-file deploy/prod/.env.example config
git diff --check
```

Record start/end UTC time, SHA, command exit code, and artifact path in the release-candidate evidence store. `npm run ci` includes unit/integration/package/evaluator, real disposable n8n, and disposable DB restore coverage; it is not a live identity, payment provider, Supabase project, GSM, stage, or VPS proof.

## Current validation result (2026-08-04)

Validation completed against base SHA `a368a45e164eda92eddf1eccad62e58a7c349399` plus the uncommitted Wave 1-3 candidate worktree. Clean `npm ci`, `npm audit --omit=dev`, release/template/package/catalogue checks, the environment contract, secret scan, both Compose renders, deterministic production image builds, and `git diff --check` exited zero. The production names-only render emitted only the expected blank `SUPABASE_DB_PASSWORD` and `N8N_ENCRYPTION_KEY` warnings because no runtime secrets were created. `npm ci` also reported third-party deprecation notices and three install scripts outside the package-manager allow-list; these were warnings, not an `npm audit --omit=dev` finding or evidence that those scripts ran.

The final serial `npm run ci` completed with exit code zero. It passed: root gateway (81), Automation Architect (17), automation contracts (3), automation operations (5), Product API (24), operator console (4), client product (10), Automation Librarian (16), evaluator cleanup/label tests (8), all strict TypeScript checks, all application builds, and the durable real-Chrome journey. Disposable Postgres/PostgREST verified fixed-service-token delegated organisation authorization, commercial lifecycle and history, immutable offer/terms/release binding, signed webhook success/failure/replay/restart/forgery/ordering, audited WP-05 provisioning, operator operations, concurrent idempotency, cross-organisation denial, restore, and reverse rollback. Smoke and full profiles imported and evaluated workflows in real `n8nio/n8n:2.30.0`, image digest `sha256:62294bc32d5a521ebb56abd98d6f6d3c6983cf9cf39c53cafb1fa87d971ae72f`; final receipt digests were `sha256:dad10d29ba12148d0535f024a6579a6e63c276fecfaae2dca9498fe681e79a6f` and `sha256:99805e22e90942e49fdbad52a8ecea742c39429975dcc9ac757c9fee64f596d4`.

The separate Sol Medium audit returned `PASS_PRE_VPS`. WP-12 is therefore `PASS_PRE_VPS_AWAITING_DEPLOYMENT_AUTHORIZATION`, not approved for stage or production. No live infrastructure, database migration, secret, credential, payment, DNS, or deployment action occurred.

## Local E2E trace status

The canonical browser command uses the compiled WP-10/WP-11 applications, real WP-09 Product API, concrete PostgREST service, and accepted WP-05 provisioning adapter in one disposable environment. It proves published offer → durable order → terms/commercial gate → subscription → WP-05 provisioning, client-member operator denial, durable incident acknowledgement, redaction, responsive/accessibility assertions, and separate promotion authority. Database tests prove restart/replay, cross-organisation denial, provider-event ordering, compensation, restore, and rollback.

This is local durable integration proof. The live platform issuer/JWKS/session source, payment provider, GSM-held credentials, approved Supabase target, legal terms/pricing, managed n8n/VPS, and public/private network routes remain deliberately unconfigured and require separate authority.

## Data handling

Classification: secrets/auth credentials and raw workflow payloads are restricted; organisation operational records are confidential; release manifests, hashes, audit IDs, and redacted health summaries are internal evidence. Retention/deletion periods, legal hold, backup target, encryption keys, and recovery targets are deployment decisions in the VPS Input Register. Rollback preserves audit rows, exports, logs, migration receipts, and incident evidence.
