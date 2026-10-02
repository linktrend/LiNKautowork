# LiNKautowork 1.0 — superseded development-only index

Prepared: 2026-09-18; archive consolidation updated 2026-10-02. This index
classifies documents that **must not** be used as the 1.0 agent entrypoint.
Superseded plans, dated handoffs, the old build log, and production-roadmap
development records have been physically moved under
`docs/archive/development-history/`. Historical source-release receipts remain
in their original directory and are not current status evidence.

`npm run release:check` still requires `docs/LINKAUTOWORK-INTENT.md`,
`docs/LINKAUTOWORK-TECHNICAL-PRD.md`, `docs/LINKAUTOWORK-OPERATIONS-MANUAL.md`,
and the small `docs/OPEN-ISSUES.md` archive pointer to exist on those paths.

## Replacement set

| Use | Replacement |
|---|---|
| Agent bootstrap / identity / toolchain / HOLDs | [`../LINKAUTOWORK-AI-AGENT-GUIDE.md`](../LINKAUTOWORK-AI-AGENT-GUIDE.md) |
| Current protected refs, receipt, tag, deployment state | [`../LINKAUTOWORK-RELEASE-STATUS.md`](../LINKAUTOWORK-RELEASE-STATUS.md) |
| Source receipts | [`../end-to-end-delivery/evidence/source-release/`](../end-to-end-delivery/evidence/source-release/) |
| Later Server01 install | [`../end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md`](../end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md) |
| Compose topology | [`../runbooks/OPERATIONS.md`](../runbooks/OPERATIONS.md) |
| SQL package | [`../contracts/server01/MIGRATION-PACKAGE.json`](../contracts/server01/MIGRATION-PACKAGE.json) |

## Development-only (do not execute as live 1.0 procedure)

| Original path | Why superseded for 1.0 agents | Replacement |
|---|---|---|
| `docs/archive/development-history/end-to-end-delivery/*` | Superseded planning and execution documents | AI agent guide + current release status |
| `docs/archive/development-history/handoffs/*` | Dated session notes | AI agent guide + current release status |
| `docs/archive/development-history/planning/*` | Historical provider/consumer hold analyses | Technical PRD + current provider contracts |
| `docs/archive/development-history/OPEN-ISSUES.md` | Append-only engineering build log | Current release status and runbooks |
| `docs/archive/development-history/production-roadmap/*` | Completed development roadmap and pre-VPS evidence | Current release status + deployment runbooks |
| `docs/archive/root-docs/*` | Original PRD / git notes | Intent + Technical PRD + AGENTS.md |
| `docs/archive/BRANCHING_AND_DEPLOYMENT_POLICY.md` | Prose snapshot | `.github/workflows/branch-source-policy.yml` + AI agent guide §6 |
| `docs/archive/RELEASE_GATE_CHECKLIST.md` | Early checklist | `docs/runbooks/PRODUCTION_RELEASE_GATES.md` (live still HOLD) |
| `docs/archive/UPSTREAM.md` | Fork policy | Technical PRD §5 (stock n8n only) |
| `docs/archive/AUTOMATION_LIFECYCLE.md` | Contract snippet | Technical PRD §§7–10 |
| `docs/archive/CONTRACTS.md` | Contract snippet | `docs/contracts/` |
| `docs/archive/DOCUMENTATION_GOVERNANCE.md` | Old docs process | this index + AI agent guide §3 |

## Still current (not archived)

Intent, Technical PRD, Operations Manual, production PRD / PROD packets,
runbooks, Server01 contracts, `deploy/prod` Compose, source-release historical
receipts, current release status, and the AI agent guide.

## Bulk mirror (untouched)

`archive/legacy-dev-mirrors-2026-07-15/` at the repository root is not part of
this docs archive and must not be rewritten by documentation cleanups.
