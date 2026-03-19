# LiNKautowork

LiNKautowork is the self-hosted automation engine for LiNKtrend operations, built on n8n Community with a policy gateway, canonical templates, governance controls, and audit/event interoperability.

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

## Repository Layout

- `automations/templates/`: canonical n8n templates and template manifest.
- `automations/live/dev|prod/`: exported deployed workflow snapshots.
- `automations/evals/`: synthetic dirty-data and replay eval assets.
- `gateway/`: Node.js/TypeScript policy and integration gateway.
- `deploy/dev` and `deploy/prod`: Docker Compose stacks and env templates.
- `ops/`: sync/import/export/backup/eval scripts, SQL, alert rules.
- `docs/`: contracts, lifecycle, SLOs, and runbooks.
- `link-n8n/`: independent nested n8n fork/runtime source (explicit fork boundary).

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
5. Render GSM-backed runtime env:
- `ops/render-env-from-gsm.sh dev`
6. Start dev stack:
- `docker compose --env-file deploy/dev/.env.runtime -f deploy/dev/docker-compose.yml up -d --build`

## Daily Operations

- Mirror templates to AIOS:
  - `ops/sync-templates-to-aios.sh`
- Import templates into n8n:
  - `ops/import-templates-to-n8n.sh dev|prod`
- Export live workflow evidence:
  - `ops/export-live-from-n8n.sh dev|prod`
- Regenerate runtime env from GSM before stack start/restart:
  - `ops/render-env-from-gsm.sh dev|prod`
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
