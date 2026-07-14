# LiNKautowork MVO role (repo boundary)

LiNKautowork spans **two repositories**. Agents must not confuse program ownership with runtime ownership.

## Three surfaces

| Surface | Location | Owns |
|---------|----------|------|
| **Outer repo (this checkout)** | `LiNKautowork` | Runtime, ops, gateway, deploy, canonical n8n templates |
| **System SDK** | `LiNKtrend-System/LiNKautowork/` | Gateway integration code, template registry, workflow handles, LiNKaios contract surface |
| **n8n fork** | `LiNKautowork/link-n8n/` | Upstream n8n fork boundary — sync policy in [docs/UPSTREAM.md](../../../docs/UPSTREAM.md) |

## Outer repo (runtime / ops / gateway / templates)

**This repository** is the self-hosted automation engine:

- `automations/templates/` — canonical n8n workflow templates (source of truth)
- `automations/live/dev|prod/` — exported deployed snapshots
- `gateway/` — Node.js/TypeScript policy gateway (signed ingress, GSM JIT secrets, audit RPC, kill switches)
- `deploy/` — Docker Compose stacks for dev/prod
- `ops/` — GSM render, template sync/import/export, backup, eval, security scripts
- `docs/` — contracts, lifecycle, SLOs, runbooks

Templates mirror **to** LiNKtrend-System SDK path (`LiNKautowork/templates/`) for LiNKaios integration — not the reverse.

## System LiNKautowork/ (SDK)

**LiNKtrend-System** hosts the SDK and contract surface LiNKaios calls:

- Workflow gateway package and TypeScript workflow runners
- Template JSON declarations consumed by the control plane
- Audit/event/idempotency contracts aligned to MVO (`CONTRACTS_MVO.md` in System grounding)

Do **not** duplicate SDK logic in the outer repo gateway unless the change belongs to runtime policy (ingress, GSM, n8n bridge).

## link-n8n/ (n8n fork)

Nested fork of [n8n](https://github.com/n8n-io/n8n):

- Gitignored at repo root — independent boundary inside LiNKautowork
- Never push upstream
- LiNKtrend-specific gateway, templates, and ops stay **outside** `link-n8n/` unless explicitly vendored

## LiNKdev program ownership

| Question | Answer |
|----------|--------|
| Where is the canonical program? | `linktrend-system` in **LiNKtrend-System** only |
| Where do issues live? | `LiNKdev/product/programs/linktrend-system/issues/` |
| What is this repo's PROGRAM.md? | Execution-target pointer — **no Planner here** |

## MVO proof (every side-effecting step)

Even in dev/shadow modes, governed steps must produce:

- LinkSkills capability lease/run (when side-effecting)
- LiNKautowork workflow run record
- LiNKbrain event/audit write
- LiNKaios trace/status visibility
- LiNKguard session cleanup on bot-adjacent runs

See LiNKtrend-System `LiNKdev/product/grounding/CONTRACTS_MVO.md` for platform-wide stubs and capability tables.
