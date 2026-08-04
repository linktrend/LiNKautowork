# LiNKautowork

LiNKautowork is LiNKtrend's self-hosted automation engine: a pinned n8n Community runtime, a policy/security gateway, canonical governance templates, persisted kill-switch/lifecycle controls, and audit/event interoperability on the shared platform database.

## Start here (source of truth)

These four documents are the current, authoritative description of this Program. If anything elsewhere in this repo (including older docs under `docs/archive/`) disagrees with them, **these four win**:

- **[`docs/LINKAUTOWORK-INTENT.md`](docs/LINKAUTOWORK-INTENT.md)** — why LiNKautowork exists, who it's for, scope, and what "done" means.
- **[`docs/LINKAUTOWORK-TECHNICAL-PRD.md`](docs/LINKAUTOWORK-TECHNICAL-PRD.md)** — the exhaustive technical reference: architecture, gateway + stock upstream n8n, Supabase schemas, rituals, kill-switch/lifecycle, events, platform integration, and deferred items.
- **[`docs/LINKAUTOWORK-OPERATIONS-MANUAL.md`](docs/LINKAUTOWORK-OPERATIONS-MANUAL.md)** — a plain-English handbook for the Principal.
- **[`docs/OPEN-ISSUES.md`](docs/OPEN-ISSUES.md)** — append-only engineering build / compliance log (what was built, deferred, and limited).

## Layout

- `automations/templates/` — live governance templates (authority for what n8n should run)
- `automations/templates/archive/` — retired templates (kept for history)
- `gateway/` — policy gateway (signed ingress, tokens, GSM secrets, audit, kill-switch, NATS)
- `deploy/dev` / `deploy/prod` — Compose stacks (NATS + gateway + pinned stock n8n `2.30.0`)
- `supabase/migrations/` — `lautowork` control schema + `lautowork_n8n` isolation + persistence RPCs
- `ops/` — import/export/backup/GSM/deploy scripts
- `docs/runbooks/` — operator procedures still used for real bring-up
- `docs/archive/` — superseded documentation (see `docs/archive/README.md`)
- `archive/legacy-dev-mirrors-2026-07-15/` — pre-existing bulk archive (untouched by doc cleanups)

## MVO highlights

- Internal-only org UUID: `00000000-0000-0000-0000-000000000001` (`linktrend_internal`)
- Ritual windows (Taipei): `08:00` / `10:45` / `14:45`
- Event contract: `linkautowork.v1.*`
- Control schema: `lautowork` · n8n schema: `lautowork_n8n` · env split: `linkplatform-stage` vs `linkplatform-prod`

## Pre-VPS release package

1. Run `npm ci && npm run release:check && npm run ci` from a clean checkout.
2. Review the [release candidate manifest](docs/production-roadmap/evidence/WP-12-RELEASE-CANDIDATE-MANIFEST.md), environment matrix, and [VPS Deployment Input Register](docs/production-roadmap/evidence/WP-12-VPS-DEPLOYMENT-INPUT-REGISTER.md).
3. Do not render GSM values, apply migrations, or start a stack until the external inputs and explicit authority in that register are supplied.

Full operator detail: [`docs/DEPLOY_READINESS.md`](docs/DEPLOY_READINESS.md) and [`docs/runbooks/OPERATIONS.md`](docs/runbooks/OPERATIONS.md).

## Live template inventory (2026-07-18)

Governance-only. The historical program-shell archive is non-authoritative and cannot be generated or imported by current release scripts.

| Template | Purpose |
|----------|---------|
| `ritual-gates-unified.json` | Strategic / operational / quality ritual gates |
| `urgent-event-ingestion.json` | Urgent event intake → gateway publish |
| `promotion-review-governance.json` | Lifecycle promotion approvals |
| `restore-authorization-governance.json` | Restore auth + scoped kill-switch |

## Status

**Pre-VPS release-readiness is in progress.** Local validation can prove source and disposable dependencies only. It cannot prove a selected VPS, live migration, GSM, DNS/TLS, payment, external identity, alert delivery, backup target, or production integration. See the WP-12 evidence for the exact state.
