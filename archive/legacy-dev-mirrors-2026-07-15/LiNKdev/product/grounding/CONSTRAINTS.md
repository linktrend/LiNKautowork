# Product constraints — LiNKautowork

Stack, boundaries, and non-goals for **this execution-target repository**.

## In scope (this repo)

- Canonical n8n templates under `automations/templates/`
- Policy gateway (`gateway/`) — HMAC ingress, service tokens, tenant lineage, GSM JIT secrets
- Deploy/ops for self-hosted n8n stacks (`deploy/`, `ops/`)
- Nested `link-n8n/` fork boundary (upstream sync per `docs/UPSTREAM.md`)
- Audit RPC writes and dual event publish (`aios.*`, optional `linkautowork.v1.*`)
- Internal tenant UUID: `00000000-0000-0000-0000-000000000001`

## Out of scope (belongs elsewhere)

| Concern | Owner |
|---------|-------|
| LiNKdev program, issues, Planner | **LiNKtrend-System** (`linktrend-system` program) |
| LiNKaios UI, kernel, project orchestration | **LiNKtrend-System** (`LiNKaios/`) |
| SDK gateway integration for suites | **LiNKtrend-System** (`LiNKautowork/`) |
| Capability leases, skills, kill switches | **LinkSkills** (System repo) |
| Memory, audit union, event ledger | **LiNKbrain** (System repo) |
| Suite business workflows (LinkSites loop, etc.) | **LiNKtrend-System** `suites/` + external LiNKsites |

## Security and cost

- All secrets in **Google Secret Manager** — never commit `.env` runtime values
- Use `ops/render-env-from-gsm.sh` and `ops/render-runtime-env-from-gsm.sh` before stack start
- Protected promotion/restore actions require **Principal** approval
- Do not push to upstream n8n or other `link-*` fork remotes you do not own

## Terminology (May 2026)

Use **Project** (not Mission), **Phase** (not Workflow for LiNKaios stage groups), **Automation** (not n8n workflow in user-facing copy), **Capability** (not Connector in LiNKaios UI).

Issues link here only when `read_first` requires boundary context.
