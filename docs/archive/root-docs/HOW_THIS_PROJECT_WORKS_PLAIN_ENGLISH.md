# How LiNKautowork Works (Plain English)

This document explains the project for operators and the Principal.

## 1) What this project is

LiNKautowork is the internal automation engine: a self-hosted n8n runtime plus a policy gateway.

1. Define workflow templates once in this repo.
2. Deploy them to n8n.
3. Run them safely with contract checks, logging, and governance.

## 2) The most important rule

`automations/templates` is the authority for what n8n should run.

## 3) Internal-only tenant (MVO)

Machine contract tenant ID:

- `00000000-0000-0000-0000-000000000001` (`linktrend_internal`)

Wrong tenant UUID → rejected.

## 4) High-level architecture

1. **Templates** (`automations/templates`) — governance workflows (rituals, promotion, restore, kill-switch helpers).
2. **Gateway** (`gateway/`) — signed ingress, tenant checks, GSM secrets, audit + kill-switch persistence, NATS events.
3. **n8n runtime** (`deploy/dev` and `deploy/prod`) — executes workflows; DB schema `lautowork_n8n` on `linkplatform-stage` / `linkplatform-prod`.
4. **Control data** — Supabase schema `lautowork` (`audit_runs`, `lifecycle_transitions`, `killswitch_events`).

The n8n engine is **stock upstream** (Compose pins the official Docker image). LiNKautowork customizations live in this repo's gateway, templates, and ops — not in a forked n8n core. See live `docs/LINKAUTOWORK-TECHNICAL-PRD.md` §5 (this archived plain-English doc previously referred to a `link-n8n` submodule that has been removed).

## 5) Request flow

1. Caller hits gateway `/v1/ingress/:workflowId` with signed headers.
2. Gateway validates signature, tenant, kill-switch, lineage.
3. Gateway fetches secrets from GSM if needed.
4. Gateway dispatches to n8n webhook.
5. Gateway writes audit to Supabase and publishes NATS events.

## 6) Ritual windows (Taipei)

- `08:00` strategic
- `10:45` operational
- `14:45` quality

## 7) Governance

`draft → dev_tested → qa_approved → ops_approved → prod_deployed → deprecated → archived`

Protected actions need Principal approval.

## 8) Kill switch

- **Scoped:** stop one workflow.
- **Global:** deactivate all active workflows.

State is **persisted in Supabase** and restored if the gateway restarts.

## 9) What is deliberately not here

- No LiNKaios / LiNKtrend-System invoke path (shelved).
- No live CRM/outreach/site-factory shells until a current Program owns a real handler.

## 10) Daily ops pointers

See `README.md` and `docs/runbooks/OPERATIONS.md`.
