# LiNKautowork

LiNKautowork is the self-hosted automation engine for LiNKtrend operations, built on n8n Community with a policy gateway, canonical templates, governance controls, and audit/event interoperability.

**LiNKdev program:** canonical program is `linktrend-system` in [LiNKtrend-System](https://github.com/linktrend/LiNKtrend-System) only. This repo is the **execution target** (runtime, ops, gateway, templates). SDK/contracts: `LiNKtrend-System/LiNKautowork/`. See `LiNKdev/product/grounding/MVO_ROLE.md`.

## Root Documents

- PRD (source requirements):
  - `260319 - PRD_ LiNKautowork Automation Engine.md`
- Comprehensive implementation trace vs PRD:
  - `IMPLEMENTATION_AGAINST_PRD.md`
- Comprehensive plain-English operating guide:
  - `HOW_THIS_PROJECT_WORKS_PLAIN_ENGLISH.md`

## MVO Highlights (Implemented)

- Internal-only tenant-safe runtime contract with canonical UUID:
  - `00000000-0000-0000-0000-000000000001`
- Canonical workflow source of truth in `automations/templates`.
- Dedicated gateway enforcing:
  - signed ingress (HMAC + timestamp + nonce)
  - service token checks
  - tenant and lineage validation
  - JIT secret retrieval (GSM)
  - canonical audit RPC writes
  - event bridge publishing
  - kill-switch controls
- Ritual alignment windows implemented at:
  - `08:00` strategic
  - `10:45` operational pulse
  - `14:45` quality
- Dual event publish contract:
  - primary `aios.*`
  - optional mirror `linkautowork.v1.*`

## Supabase Schema Standard

Current standard (post ADR 0001, shared `platform` org model):

- n8n runtime schema (single, per Supabase project):
  - `lautowork_n8n` — owned and managed by n8n itself on boot; LiNKautowork never hand-designs tables here. Provisioned by `supabase/migrations/20260715_000002_lautowork_n8n_isolation.sql`, which creates only the empty schema + a dedicated `svc_lautowork_n8n` role (broad DDL grant on that one isolated schema so n8n can create its own tables). LiNKautowork's own control role (`svc_lautowork_runtime`) and `svc_observer` are deliberately never granted access — a hard isolation boundary (ADR 0001 Decision 3).
- Control/ledger schema (single, spec-compliant):
  - `lautowork` — `audit_runs`, `lifecycle_transitions`, `killswitch_events`, org-scoped via `platform.organizations`. Provisioned by `supabase/migrations/20260715_000001_lautowork_control_core.sql`.
- SQL function `public.linkautowork_write_audit_run` uses `search_path=lautowork,public`.
- Migration naming standard for new migrations:
  - `YYYYMMDD_HHMMSS_lautowork_<change>.sql`

### Environment separation (two-project topology)

Under the shared two-Supabase-project topology (`linkplatform-stage` / `linkplatform-prod`, see ADR 0001 Decisions 2–3), environment separation happens at the **Supabase-project level, not via a schema-name suffix**. n8n is therefore pointed at the single schema name `lautowork_n8n` in whichever project is the current target — not the retired `lautowork_n8n_dev` / `lautowork_n8n_prod` split, and not the old `linkautowork_audit` / `linkautowork_control` control schemas.

**Schema wiring status:** `deploy/dev/docker-compose.yml` now sets `DB_POSTGRESDB_SCHEMA=lautowork_n8n` (updated 2026-07-15, matching the isolation migration). The `deploy/prod/docker-compose.yml` value still reads `lautowork_n8n_prod` and is the one remaining follow-up: it is left for the next prod redeploy (prod deploy config is not edited here). No n8n is running anywhere at present (the VPS was destroyed — ADR 0001 Update 2026-07-15), so there is nothing to migrate; the empty `lautowork_n8n` schema will be populated by n8n on its next first boot.

## Repository Layout

- `automations/templates/`: canonical n8n templates and template manifest.
- `automations/live/dev|prod/`: exported deployed workflow snapshots.
- `automations/evals/`: synthetic dirty-data and replay eval assets.
- `gateway/`: Node.js/TypeScript policy and integration gateway.
- `deploy/dev` and `deploy/prod`: Docker Compose stacks and env templates.
- `ops/`: sync/import/export/backup/eval scripts, SQL, alert rules.
- `docs/`: contracts, lifecycle, SLOs, and runbooks.
`link-n8n/`: nested n8n fork — see [docs/UPSTREAM.md](docs/UPSTREAM.md).

## Quick Start

1. Review root docs listed above.
2. Copy and fill env files:
- `deploy/dev/.env`
- `deploy/prod/.env`
   - Store only non-secret config and GSM secret identifiers (`*_SECRET_NAME`).
3. Install dependencies:
- `npm install`
4. Validate and test:
- `npm run ci`
5. Validate GSM secret-name references:
- `ops/render-env-from-gsm.sh dev`
6. Render runtime env from GSM to runtime path:
- `ops/render-runtime-env-from-gsm.sh dev --output /opt/linktrend/runtime/linkautowork/dev.env.runtime`
7. Start dev stack with GSM runtime env:
- `ops/deploy-stack.sh dev --build`

## Daily Operations

- Mirror templates to LiNKtrend-System SDK:
  - `ops/sync-templates-to-aios.sh`
- Import templates into n8n:
  - `ops/import-templates-to-n8n.sh dev|prod`
- Export live workflow evidence:
  - `ops/export-live-from-n8n.sh dev|prod`
- Validate GSM secret references before stack start/restart:
  - `ops/render-env-from-gsm.sh dev|prod`
- Render runtime env from GSM:
  - `ops/render-runtime-env-from-gsm.sh dev|prod --output /opt/linktrend/runtime/linkautowork/<env>.env.runtime`
- Start stack with runtime env injection:
  - `ops/deploy-stack.sh dev|prod --build`
- Enforce tailscale-only firewall for protected ports:
  - `ops/security/install-tailscale-firewall-service.sh`
- Run repository secret scan:
  - `ops/security/scan-secrets.sh`
- Run eval inventory check:
  - `ops/run-evals.sh`
- Backup and restore drill:
  - `ops/run-backup.sh`
  - `ops/restore-drill.sh <db-backup.sql.gz> <templates-backup.tar.gz>`

## Contract and Safety References

- Contract details:
  - `docs/CONTRACTS.md`
- Lifecycle and promotion gates:
  - `docs/AUTOMATION_LIFECYCLE.md`
- SLO and alert baseline:
  - `docs/SLO.md`
- Operator runbook:
  - `docs/runbooks/OPERATIONS.md`
- Tailscale hardening runbook:
  - `docs/runbooks/TAILSCALE_HARDENING.md`

## Documentation Map
- [Docs Index](./docs/README.md)
- [Branching and Deployment Policy](./docs/BRANCHING_AND_DEPLOYMENT_POLICY.md)
- [Documentation Governance](./docs/DOCUMENTATION_GOVERNANCE.md)

## Live Automation Template Inventory (2026-07-15)

Per Principal instruction (2026-07-15), speculative automations that referenced undefined RPCs were dropped, leaving only templates needed to run the real Programs that exist today. Three templates were archived to [`automations/templates/archive/`](./automations/templates/archive/README.md) — `heartbeat-triage.json`, `security-exception-response.json`, `hot-cold-migration.json` — because they called five never-defined Supabase RPCs (`linkautowork_health`, `linkautowork_open_incident`, `linkautowork_find_inactive_files`, `linkautowork_persist_pointer`, `linkautowork_delete_file`). An independent sweep of the remaining templates found no other undefined-RPC or non-existent-schema references.

The **31 live templates** below are the "what's actually needed to run the Programs" set. `validate:templates` passes against this reduced set (32 JSON files / 31 manifest entries).

### Platform / governance (LiNKautowork itself)

| Template | What it's for | Real Program / schema element it connects to |
|----------|---------------|----------------------------------------------|
| `ritual-gates-unified.json` | Scheduled strategic/operational/quality ritual gates with confidence scoring | LiNKautowork → gateway `POST /v1/events/publish` → `lautowork.audit_runs` via `public.linkautowork_write_audit_run` |
| `urgent-event-ingestion.json` | Webhook intake for urgent events, wakes orchestrator, publishes execution event | LiNKautowork / LiNKbrain event bridge → gateway `POST /v1/events/publish` → `lautowork.audit_runs` |
| `promotion-review-governance.json` | Governed lifecycle promotion with auditor/HoQ/COO/Principal approval gates | LiNKautowork lifecycle → gateway `POST /v1/lifecycle/transition` → `lautowork.lifecycle_transitions` |
| `restore-authorization-governance.json` | Governed restore authorization + scoped kill-switch on protected restore | LiNKautowork lifecycle + control → gateway `POST /v1/lifecycle/transition` and `POST /v1/control/killswitch/scoped` → `lautowork.lifecycle_transitions`, `lautowork.killswitch_events` |
| `daily-chairman-briefing.json` | **Deprecated** legacy 08:00 briefing shim; forwards to the unified ritual gate | LiNKautowork (legacy compat) → gateway `POST /v1/events/publish`. Real endpoint, marked `deprecated` in manifest; kept as a compatibility path, superseded by `ritual-gates-unified.json` |

### LiNKsites Program (lead-to-outreach commercial loop)

All LiNKsites templates are thin n8n webhook shells that invoke the real LiNKaios autowork handler (`$env.LINKAIOS_AUTOWORK_INVOKE_URL`, secured by `$env.LINKAUTOWORK_INVOKE_SECRET`) with a stable `workflow_handle`.

| Template | What it's for | Real Program / handle |
|----------|---------------|-----------------------|
| `linksites-artifact_write_local.json` | Persist a generated site artifact locally | LiNKsites → `autowork.linksites.artifact_write_local` |
| `linksites-supabase_mirror_upsert.json` | Mirror site record into Supabase | LiNKsites → `autowork.linksites.supabase_mirror_upsert` |
| `linksites-payload_sync_local.json` | Sync site content to local Payload CMS | LiNKsites → `autowork.linksites.payload_sync_local` |
| `linksites-preview_readiness_check.json` | Gate that a preview site is publish-ready | LiNKsites → `autowork.linksites.preview_readiness_check` |
| `linksites-crm_ready_to_contact_mark.json` | Mark a lead ready-to-contact in CRM | LiNKsites → `autowork.linksites.crm_ready_to_contact_mark` |
| `linksites-outreach_dispatch.json` | Dispatch (governed) outreach to a lead | LiNKsites → `autowork.linksites.outreach_dispatch` |

### LiNKsuitegen (LiNKsites suite-generation factory)

The suite-generation factory behind the LiNKsites loop (discovery → rank → build → validate → export → CRM → orchestrate). Same real invoke pattern as above.

| Template | What it's for | Real Program / handle |
|----------|---------------|-----------------------|
| `linksuitegen-discovery_collect.json` | Collect discovered leads | LiNKsites suite-gen → `autowork.linksuitegen.discovery_collect` |
| `linksuitegen-ranking_persist.json` | Persist lead ranking | LiNKsites suite-gen → `autowork.linksuitegen.ranking_persist` |
| `linksuitegen-factory_generate.json` | Generate a site from an industry template | LiNKsites suite-gen → `autowork.linksuitegen.factory_generate` |
| `linksuitegen-factory_validate.json` | Validate generated site | LiNKsites suite-gen → `autowork.linksuitegen.factory_validate` |
| `linksuitegen-factory_export.json` | Export/publish generated site | LiNKsites suite-gen → `autowork.linksuitegen.factory_export` |
| `linksuitegen-admin_handoff.json` | Hand off completed run to admin | LiNKsites suite-gen → `autowork.linksuitegen.admin_handoff` |
| `linksuitegen-orchestrator_cycle.json` | Drive one orchestration cycle | LiNKsites suite-gen → `autowork.linksuitegen.orchestrator_cycle` |
| `linksuitegen-crm_step.json` | Advance a CRM step | LiNKsites suite-gen → `autowork.linksuitegen.crm_step` |
| `linksuitegen-odoo_lead_create.json` | Create an Odoo CRM lead | LiNKsites suite-gen → `autowork.linksuitegen.odoo_lead_create` |

### LiNKdeveloper (developer/build platform)

Wave 4 deliverable set (see `docs/runbooks/WAVE4_AUTOMATION_PROOF.md`); each shell invokes the real, tested LiNKaios autowork ingress handler (`gateway/src/workflows/linkdeveloper.ts` in LiNKtrend-System). Same real invoke pattern as above — none reference undefined RPCs.

| Template | What it's for | Real Program / handle |
|----------|---------------|-----------------------|
| `linkdeveloper-run_validation.json` | Run validation for a dev run | LiNKdeveloper → `autowork.linkdeveloper.run_validation` |
| `linkdeveloper-status_sync.json` | Sync run status | LiNKdeveloper → `autowork.linkdeveloper.status_sync` |
| `linkdeveloper-starter_generation.json` | Generate a project starter | LiNKdeveloper → `autowork.linkdeveloper.starter_generation` |
| `linkdeveloper-notification.json` | Emit a developer notification | LiNKdeveloper → `autowork.linkdeveloper.notification` |
| `linkdeveloper-report_generation.json` | Generate a report | LiNKdeveloper → `autowork.linkdeveloper.report_generation` |
| `linkdeveloper-run_task.json` | Run a build/dev task | LiNKdeveloper → `autowork.linkdeveloper.run_task` |
| `linkdeveloper-deploy_scaffold.json` | Scaffold a deployment | LiNKdeveloper → `autowork.linkdeveloper.deploy_scaffold` |
| `linkdeveloper-product_run_bootstrap.json` | Bootstrap a product run | LiNKdeveloper → `autowork.linkdeveloper.product_run_bootstrap` |
| `linkdeveloper-issue_dispatch.json` | Dispatch an issue to execution | LiNKdeveloper → `autowork.linkdeveloper.issue_dispatch` |
| `linkdeveloper-validation_record.json` | Record a validation result | LiNKdeveloper → `autowork.linkdeveloper.validation_record` |
| `linkdeveloper-artifact_write.json` | Write a build artifact | LiNKdeveloper → `autowork.linkdeveloper.artifact_write` |
