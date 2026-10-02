# WP-12 release-candidate manifest

**Candidate state:** `PASS_PRE_VPS_AWAITING_DEPLOYMENT_AUTHORIZATION`. All three pre-VPS waves passed independent audit. Stage/production deployment remains prohibited until the separately authorised deployment inputs and Principal approval exist.

| Contract | Candidate value | Status |
| --- | --- | --- |
| Source/ref | base SHA `a368a45e164eda92eddf1eccad62e58a7c349399` plus the uncommitted Wave 1-3 candidate worktree | recorded; no commit or push authorised |
| Gateway build | Node `22.13.1-alpine`, `npm ci`, non-root `app` user | source-pinned; image digest to record after approved build |
| n8n image | `n8nio/n8n:2.30.0`, digest `sha256:62294bc32d5a521ebb56abd98d6f6d3c6983cf9cf39c53cafb1fa87d971ae72f` | locally resolved, imported, smoke/full evaluated; deployment host must resolve and record its candidate digest |
| NATS image | `nats:2.10.26-alpine` | version pinned; digest requires authorised registry resolution |
| Dependencies | `package-lock.json`, clean `npm ci`, `npm audit --omit=dev` | lockfile controlled; zero known production vulnerabilities on 2026-08-04; install-time third-party deprecation/allow-list warnings are recorded in the validation ledger |
| Schemas | all eleven `20260804_*` migrations through `20260804_000012`, plus prior control migrations | all apply/verify/restore/rollback locally; cloud apply requires authority |
| Workflow release | four current governed templates | publish/import requires approved n8n target |
| Required configuration | names-only GSM contract; stage/prod environment matrix | external authority required |
| Rollback target | prior approved image digest + workflow export + migration recovery plan | must be recorded before deploy |

## Known limits inherited from Wave 3

1. WP-09 exposes finite typed lifecycle/client/operator routes, resource-specific state machines, production RS256/JWKS plus session verification, raw-byte webhook validation, outcome-accurate audit records, and a concrete named-RPC PostgREST service. Its governed live issuer/JWKS/session URLs and authorised Supabase target remain external inputs.
2. WP-10 is a runnable authenticated console bound to literal WP-09 routes. Its real-browser proof uses disposable durable PostgREST and submits a durable operator incident action. This is not proof of a deployed private route or live operator identity.
3. WP-11 is a runnable public/client application. Its real-browser proof uses durable order, terms, commercial lifecycle, subscription, and the accepted WP-05 provisioning state machine. Fake/local payment-state tests deliberately do not prove a provider, charge, legal terms approval, customer account, secure credential intake, or live managed n8n instance.

The independent pre-VPS audit passed. These limits still prohibit stage or production deployment until separately authorised live inputs and deployment validation close them. They are not masked by deployment templates.

## Release order and recovery

1. Validate inputs and render runtime env outside the repository.
2. Run migration checksum/dry-run, take and verify a pre-change backup, then apply only in the approved target.
3. Start persistent NATS, gateway, private n8n, Product API, public client site, and private operator console in dependency order; run migration preflight, publish only certified packages, start the authenticated operations scheduler, then run canary.
4. On regression: stop promotion, preserve logs/audit IDs/export/backup, restore the last approved workflow/image, and use the migration forward-recovery plan. Never delete audit or evidence rows as rollback.
