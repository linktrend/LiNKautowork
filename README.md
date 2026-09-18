# LiNKautowork

LiNKtrend’s self-hosted automation engine: pinned stock n8n `2.30.0`, a policy
gateway, canonical governance templates, durable kill-switch/lifecycle data,
and `linkautowork.v1.*` events on the shared platform database.

**1.0 source status:** engineering candidate is sealed; live Server01 install
is a later packet. Protected `main` is not yet this line. Do not treat tag
`v1.0.0` as this candidate (it peels to an older commit).

## Start here

| Role | Document |
|---|---|
| **Any AI agent** | [`docs/LINKAUTOWORK-AI-AGENT-GUIDE.md`](docs/LINKAUTOWORK-AI-AGENT-GUIDE.md) |
| **Server01 deploy agent (later)** | [`docs/end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md`](docs/end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md) |
| Product “why / how / Principal handbook” | [`docs/LINKAUTOWORK-INTENT.md`](docs/LINKAUTOWORK-INTENT.md), [`docs/LINKAUTOWORK-TECHNICAL-PRD.md`](docs/LINKAUTOWORK-TECHNICAL-PRD.md), [`docs/LINKAUTOWORK-OPERATIONS-MANUAL.md`](docs/LINKAUTOWORK-OPERATIONS-MANUAL.md) |
| Remaining live configuration work | [`docs/PRD.md`](docs/PRD.md), [`docs/WORK-PACKETS.md`](docs/WORK-PACKETS.md) |
| Historical / superseded | [`docs/archive/LINKAUTOWORK-1.0-SUPERSEDED-INDEX.md`](docs/archive/LINKAUTOWORK-1.0-SUPERSEDED-INDEX.md) |

If older prose (including `docs/archive/` and dated handoffs) disagrees with
the AI agent guide plus the source-release packet, **those two win for 1.0
procedure**.

## Layout

- `automations/templates/` — live governance templates (authority for n8n)
- `gateway/` — policy gateway (signed ingress, tokens, GSM names, audit, NATS)
- `deploy/prod` — production Compose (unpublished protected ports)
- `supabase/migrations/` — `lautowork` + `lautowork_n8n` (Platform applies live)
- `ops/` — import/export/backup/GSM/deploy scripts (many refuse `--live`)
- `docs/runbooks/` — operator procedures for source topology and later bring-up
- `docs/archive/` — superseded documentation
- `archive/legacy-dev-mirrors-2026-07-15/` — bulk archive; leave untouched

## Constants

- Internal org UUID: `00000000-0000-0000-0000-000000000001` (`linktrend_internal`)
- Ritual windows (Taipei): `08:00` / `10:45` / `14:45`
- Control schema: `lautowork` · n8n schema: `lautowork_n8n`
- Compose project: `linkautowork-prod`

## Source checks (no live host)

From a clean checkout bound to the intended commit/tree:

```bash
# Prefix nvm Node 22 if PATH still has /exec-daemon/node
npm ci
git diff --check
python3 -m json.tool docs/end-to-end-delivery/EXECUTION-MANIFEST.json
npm run release:check
```

Hosted `npm run ci` is the full proof. Local writer VMs without Docker cannot
complete disposable Postgres / eval:full / restore / durable browser steps;
do not start Docker from a docs packet.

## Live template inventory

Governance-only. Historical program-shell archives are non-authoritative.

| Template | Purpose |
|----------|---------|
| `ritual-gates-unified.json` | Strategic / operational / quality ritual gates |
| `urgent-event-ingestion.json` | Urgent event intake → gateway publish |
| `promotion-review-governance.json` | Lifecycle promotion approvals |
| `restore-authorization-governance.json` | Restore auth + scoped kill-switch |

## Integration

Implementers commit and push `issue/<n>-<slug>` checkpoints only. The Phase
Packager opens the Phase PR; the delivery controller merges to `development`.
Promotion to `staging` / `main` and tagging are not implementer actions.
