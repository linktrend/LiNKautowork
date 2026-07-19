# LiNKautowork

LiNKautowork is LiNKtrend's self-hosted automation engine: a pinned n8n Community runtime, a policy/security gateway, canonical governance templates, persisted kill-switch/lifecycle controls, and audit/event interoperability on the shared platform database.

## Start here (source of truth)

These four documents are the current, authoritative description of this Program. If anything elsewhere in this repo (including older docs under `docs/archive/`) disagrees with them, **these four win**:

- **[`docs/LINKAUTOWORK-INTENT.md`](docs/LINKAUTOWORK-INTENT.md)** — why LiNKautowork exists, who it's for, scope, and what "done" means.
- **[`docs/LINKAUTOWORK-TECHNICAL-PRD.md`](docs/LINKAUTOWORK-TECHNICAL-PRD.md)** — the exhaustive technical reference: architecture, gateway + n8n, Supabase schemas, link-n8n fork relationship, rituals, kill-switch/lifecycle, events, platform integration, and deferred items.
- **[`docs/LINKAUTOWORK-OPERATIONS-MANUAL.md`](docs/LINKAUTOWORK-OPERATIONS-MANUAL.md)** — a plain-English handbook for the Principal.
- **[`docs/OPEN-ISSUES.md`](docs/OPEN-ISSUES.md)** — append-only engineering build / compliance log (what was built, deferred, and limited).

## Layout

- `automations/templates/` — live governance templates (authority for what n8n should run)
- `automations/templates/archive/` — retired templates (kept for history)
- `gateway/` — policy gateway (signed ingress, tokens, GSM secrets, audit, kill-switch, NATS)
- `deploy/dev` / `deploy/prod` — Compose stacks (NATS + gateway + pinned stock n8n `2.30.0`)
- `supabase/migrations/` — `lautowork` control schema + `lautowork_n8n` isolation + persistence RPCs
- `ops/` — import/export/backup/GSM/deploy scripts
- `link-n8n/` — git submodule → `github.com/linktrend/link-n8n` (fork for upstream sync / future custom images; Compose does **not** run it today)
- `docs/runbooks/` — operator procedures still used for real bring-up
- `docs/archive/` — superseded documentation (see `docs/archive/README.md`)
- `archive/legacy-dev-mirrors-2026-07-15/` — pre-existing bulk archive (untouched by doc cleanups)

## MVO highlights

- Internal-only org UUID: `00000000-0000-0000-0000-000000000001` (`linktrend_internal`)
- Ritual windows (Taipei): `08:00` / `10:45` / `14:45`
- Dual event subjects: `aios.*` + optional `linkautowork.v1.*`
- Control schema: `lautowork` · n8n schema: `lautowork_n8n` · env split: `linkplatform-stage` vs `linkplatform-prod`

## Quick start (stage / VPS)

1. Confirm schemas applied on target Supabase project (`lautowork` + `lautowork_n8n`).
2. Copy `deploy/dev/.env.example` or `deploy/prod/.env.example` → `.env`; fill GSM secret **names** (not raw secrets in git).
3. `npm install` && `npm run ci`
4. `ops/render-env-from-gsm.sh <dev|prod>`
5. `ops/render-runtime-env-from-gsm.sh <dev|prod> --output /opt/linktrend/runtime/linkautowork/<env>.env.runtime`
6. `ops/deploy-stack.sh <dev|prod> --build`
7. `ops/import-templates-to-n8n.sh <dev|prod>`
8. Smoke: health → signed ingress → row in `lautowork.audit_runs`

Full operator detail: [`docs/DEPLOY_READINESS.md`](docs/DEPLOY_READINESS.md) and [`docs/runbooks/OPERATIONS.md`](docs/runbooks/OPERATIONS.md).

## Live template inventory (2026-07-18)

Governance-only. Legacy Program shells that called shelved LiNKaios were archived under `automations/templates/archive/legacy-program-shells-2026-07-18/`.

| Template | Purpose |
|----------|---------|
| `ritual-gates-unified.json` | Strategic / operational / quality ritual gates |
| `urgent-event-ingestion.json` | Urgent event intake → gateway publish |
| `promotion-review-governance.json` | Lifecycle promotion approvals |
| `restore-authorization-governance.json` | Restore auth + scoped kill-switch |
| `daily-chairman-briefing.json` | Deprecated shim → unified ritual gate |

## Status

**MVO coding bar met; VPS live bring-up is an ops milestone on ready software (as of 2026-07-19).** `npm run ci` validates templates, runs gateway tests, and typechecks. See the Technical PRD for architecture and `docs/OPEN-ISSUES.md` for the build log. Marketplace, autonomous JSON self-edit, and multi-client SaaS remain deliberately deferred.
