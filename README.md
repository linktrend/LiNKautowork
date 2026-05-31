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

- Runtime schemas:
  - `lautowork_n8n_dev`
  - `lautowork_n8n_prod`
- Control/audit schemas:
  - `linkautowork_audit`
  - `linkautowork_control`
- SQL function `public.linkautowork_write_audit_run` uses `search_path=linkautowork_audit,public`.
- Migration naming standard for new migrations:
  - `YYYYMMDD_HHMMSS_lautowork_<change>.sql`

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
