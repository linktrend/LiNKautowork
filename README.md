# LiNKautowork

LiNKautowork is the self-hosted automation engine for LiNKtrend operations: n8n Community runtime, policy gateway, canonical templates, governance controls, and audit/event interoperability.

## Root Documents

- PRD: `260319 - PRD_ LiNKautowork Automation Engine.md`
- Implementation vs PRD: `IMPLEMENTATION_AGAINST_PRD.md`
- Plain English: `HOW_THIS_PROJECT_WORKS_PLAIN_ENGLISH.md`
- Upstream / fork policy: `docs/UPSTREAM.md`
- Deploy readiness: `docs/DEPLOY_READINESS.md`

## MVO Highlights

- Internal-only tenant UUID: `00000000-0000-0000-0000-000000000001`
- Canonical templates in `automations/templates` (governance set)
- Gateway: signed ingress, service tokens, tenant checks, GSM secrets, audit + **persisted** kill-switch/lifecycle, NATS events
- Ritual windows: `08:00` / `10:45` / `14:45` (Taipei)
- Dual event subjects: `aios.*` + optional `linkautowork.v1.*`

## Supabase

- Control schema: `lautowork` (`audit_runs`, `lifecycle_transitions`, `killswitch_events`)
- n8n schema: `lautowork_n8n` (empty until n8n first boot; isolated role `svc_lautowork_n8n`)
- Env separation: `linkplatform-stage` vs `linkplatform-prod` (not schema-name suffixes)
- Migrations under `supabase/migrations/`

## Runtime image

Compose pins **stock** `docker.n8n.io/n8nio/n8n:2.30.0`. The `link-n8n` submodule is the separate-repo fork for upstream sync and future custom images — see `docs/UPSTREAM.md`.

## Repository Layout

- `automations/templates/` — live governance templates
- `automations/templates/archive/` — retired templates (kept for history)
- `gateway/` — policy gateway
- `deploy/dev` / `deploy/prod` — Compose stacks
- `ops/` — import/export/backup/GSM/deploy scripts
- `link-n8n/` — submodule → `github.com/linktrend/link-n8n`

## Quick Start (stage / VPS)

1. Confirm schemas applied on target Supabase project (`lautowork` + `lautowork_n8n`).
2. Copy `deploy/dev/.env.example` or `deploy/prod/.env.example` → `.env`; fill GSM secret **names** (not raw secrets in git).
3. `npm install` && `npm run ci`
4. `ops/render-env-from-gsm.sh <dev|prod>`
5. `ops/render-runtime-env-from-gsm.sh <dev|prod> --output /opt/linktrend/runtime/linkautowork/<env>.env.runtime`
6. `ops/deploy-stack.sh <dev|prod> --build`
7. `ops/import-templates-to-n8n.sh <dev|prod>`
8. Smoke: health → signed ingress → row in `lautowork.audit_runs`

Full gate list: `docs/RELEASE_GATE_CHECKLIST.md` and `docs/DEPLOY_READINESS.md`.

## Live template inventory (2026-07-18)

Governance-only. Legacy LiNKsites / suitegen / linkdeveloper shells that called shelved LiNKaios were archived under `automations/templates/archive/legacy-program-shells-2026-07-18/`.

| Template | Purpose |
|----------|---------|
| `ritual-gates-unified.json` | Strategic / operational / quality ritual gates |
| `urgent-event-ingestion.json` | Urgent event intake → gateway publish |
| `promotion-review-governance.json` | Lifecycle promotion approvals |
| `restore-authorization-governance.json` | Restore auth + scoped kill-switch |
| `daily-chairman-briefing.json` | Deprecated shim → unified ritual gate |

## Documentation Map

- [Docs Index](./docs/README.md)
- [Branching and Deployment](./docs/BRANCHING_AND_DEPLOYMENT_POLICY.md)
- [Contracts](./docs/CONTRACTS.md)
- [Operations](./docs/runbooks/OPERATIONS.md)
- [Tailscale hardening](./docs/runbooks/TAILSCALE_HARDENING.md)
