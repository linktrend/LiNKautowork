# Archive — historical and superseded documents

Everything under `docs/archive/` is retained for history. It is **not** the
entrypoint for a 1.0 implementer, reviewer, packager, or Server01 deploy
agent.

**Do not confuse this folder with** `archive/legacy-dev-mirrors-2026-07-15/`
at the repo root — that tree is a separate bulk archive and stays untouched.

Current entrypoints:

- [AI agent guide](../LINKAUTOWORK-AI-AGENT-GUIDE.md)
- [Current release status](../LINKAUTOWORK-RELEASE-STATUS.md)
- [Deployment handoff](../end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md)
- [Archived development history](./development-history/README.md)

**1.0 replacements:**

- [`../LINKAUTOWORK-AI-AGENT-GUIDE.md`](../LINKAUTOWORK-AI-AGENT-GUIDE.md)
- [`../end-to-end-delivery/evidence/source-release/README.md`](../end-to-end-delivery/evidence/source-release/README.md)
- [`../end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md`](../end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md)
- Full classification: [`LINKAUTOWORK-1.0-SUPERSEDED-INDEX.md`](./LINKAUTOWORK-1.0-SUPERSEDED-INDEX.md)

**Product description (still live, not this folder):**

- [`../LINKAUTOWORK-INTENT.md`](../LINKAUTOWORK-INTENT.md)
- [`../LINKAUTOWORK-TECHNICAL-PRD.md`](../LINKAUTOWORK-TECHNICAL-PRD.md)
- [`../LINKAUTOWORK-OPERATIONS-MANUAL.md`](../LINKAUTOWORK-OPERATIONS-MANUAL.md)

**Still live operational procedures:** `../runbooks/*`, `../DEPLOY_READINESS.md`,
`../SLO.md`. Live Server01 start remains HOLD until AW-08 on a tagged main
candidate.

## Archived development history

- [`development-history/`](./development-history/) — moved planning packets,
  completed session handoffs, the old engineering build log, and completed
  production-roadmap evidence. These are historical records, not current
  execution instructions.

## Older items already in this folder

- `root-docs/` — original root PRD, plain-English explainer, git-strategy note.
- `UPSTREAM.md` — retired fork policy (stock upstream n8n only).
- `AUTOMATION_LIFECYCLE.md` / `CONTRACTS.md` — former contract snippets (Technical PRD §§7–10).
- `DOCUMENTATION_GOVERNANCE.md` — former docs process.
- `RELEASE_GATE_CHECKLIST.md` — former first-bring-up checklist.
- `BRANCHING_AND_DEPLOYMENT_POLICY.md` — former branching prose (rules live in
  `.cursor/rules/01-git-branching.mdc`, `AGENTS.md`,
  `.github/workflows/branch-source-policy.yml`).
- `adr/0001-adopt-shared-platform-org-model.md` — historical ADR.
- `LEGACY-DOCUMENT-REGISTER.md` — 2026-09-04 production-PRD supersession note.
- `development-only/` — pointer files created by the earlier 2026-09 cleanup.

If something here conflicts with the AI agent guide or Technical PRD, **those
win.**
