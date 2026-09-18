# LiNKautowork 1.0 — superseded development-only index

Prepared: 2026-09-18 with issue 166. This index classifies documents that
**must not** be used as the 1.0 agent entrypoint. Original files that sit
outside this packet’s allowed write paths were **not physically moved**;
pointer files under `development-only/` record the replacement.

`npm run release:check` still requires `docs/LINKAUTOWORK-INTENT.md`,
`docs/LINKAUTOWORK-TECHNICAL-PRD.md`, `docs/LINKAUTOWORK-OPERATIONS-MANUAL.md`,
and `docs/OPEN-ISSUES.md` to exist on those paths.

## Replacement set

| Use | Replacement |
|---|---|
| Agent bootstrap / identity / toolchain / HOLDs | [`../LINKAUTOWORK-AI-AGENT-GUIDE.md`](../LINKAUTOWORK-AI-AGENT-GUIDE.md) |
| Source receipts | [`../end-to-end-delivery/evidence/source-release/`](../end-to-end-delivery/evidence/source-release/) |
| Later Server01 install | [`../end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md`](../end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md) |
| Compose topology | [`../runbooks/OPERATIONS.md`](../runbooks/OPERATIONS.md) |
| SQL package | [`../contracts/server01/MIGRATION-PACKAGE.json`](../contracts/server01/MIGRATION-PACKAGE.json) |

## Development-only (do not execute as live 1.0 procedure)

| Original path | Why superseded for 1.0 agents | Replacement |
|---|---|---|
| `docs/end-to-end-delivery/CURSOR-CLOUD-EXECUTION-ROUTE.md` | Planning-era dispatcher/Keychain route; nested workers forbidden in this packet | AI agent guide §6 |
| `docs/end-to-end-delivery/README.md` | 2026-09-10 “implementation not authorised” planning banner | source-release README + AI agent guide |
| `docs/end-to-end-delivery/READINESS-REPORT.md` | Advisor-acceptance planning report | source-release VALIDATION-RECORD.json |
| `docs/end-to-end-delivery/WORK-PACKETS.md` | PLAN-state packet table; AW-01–07 source work is already on `development` | AI agent guide §9–11 |
| `docs/handoffs/*` | Dated session notes | AI agent guide + this issue’s source-release files |
| `docs/planning/*` | PKT-03 hold analyses | Technical PRD + provider contracts |
| `docs/OPEN-ISSUES.md` | Append-only MVO build log | AI agent guide for procedure; keep file as history |
| `docs/production-roadmap/evidence/*` | Pre-VPS wave evidence | source-release IMAGE-CONFIG-MIGRATION-REFERENCES.json (pins only) |
| `docs/archive/root-docs/*` | Original PRD / git notes | Intent + Technical PRD + AGENTS.md |
| `docs/archive/BRANCHING_AND_DEPLOYMENT_POLICY.md` | Prose snapshot | `.github/workflows/branch-source-policy.yml` + AI agent guide §6 |
| `docs/archive/RELEASE_GATE_CHECKLIST.md` | Early checklist | `docs/runbooks/PRODUCTION_RELEASE_GATES.md` (live still HOLD) |
| `docs/archive/UPSTREAM.md` | Fork policy | Technical PRD §5 (stock n8n only) |
| `docs/archive/AUTOMATION_LIFECYCLE.md` | Contract snippet | Technical PRD §§7–10 |
| `docs/archive/CONTRACTS.md` | Contract snippet | `docs/contracts/` |
| `docs/archive/DOCUMENTATION_GOVERNANCE.md` | Old docs process | this index + AI agent guide §3 |

## Still current (not archived)

Intent, Technical PRD, Operations Manual, production PRD / PROD packets,
runbooks, Server01 contracts, `deploy/prod` Compose, and the source-release
packet itself.

## Bulk mirror (untouched)

`archive/legacy-dev-mirrors-2026-07-15/` at the repository root is not part of
this docs archive and must not be rewritten by documentation cleanups.
