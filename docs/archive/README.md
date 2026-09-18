# Archive — superseded by the 1.0 agent authority

Everything under `docs/archive/` is retained for history. It is **not** the
entrypoint for a 1.0 implementer, reviewer, packager, or Server01 deploy
agent.

**Do not confuse this folder with** `archive/legacy-dev-mirrors-2026-07-15/`
at the repo root — that tree is a separate bulk archive and stays untouched.

**1.0 replacements (2026-09-18):**

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

## What's already in this folder

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
- `development-only/` — 1.0 pointer files for documents that remain on their
  original paths because this packet cannot move `release:check`-required files.

If something here conflicts with the AI agent guide or Technical PRD, **those
win.**
