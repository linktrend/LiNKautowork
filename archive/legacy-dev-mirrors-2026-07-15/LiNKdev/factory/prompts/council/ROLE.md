# Council role

Multi-advisor gate review for LiNKdev programs. Default runtime: **Cursor cloud** (Planner/Orchestrator handoff) or **Cursor automation** at phase boundaries.

Council runs at **four gates**. **All five advisors participate every time.** Any single **BLOCKER** verdict stops progress until resolved and re-run.

## Advisors (always all five)

| Persona | File |
|---------|------|
| Security | `personas/security-advisor.md` |
| Architecture | `personas/architecture-advisor.md` |
| Developer experience | `personas/dx-advisor.md` |
| Quality assurance | `personas/qa-advisor.md` |
| Product | `personas/product-advisor.md` |

## Gates

| Gate | When | Subject under review | Proceed on |
|------|------|----------------------|------------|
| **G1** | After finished-product narrative; **before** `PROGRAM.md` | Principal-approved finished-product narrative, draft `VISION.md` / `SHIP_CRITERIA.md` | Combined summary **PASS** or **WARN** (no BLOCKER) |
| **G2** | After `PROGRAM.md` drafted; **intent verdict** | Program plan, module map, issue DAG, DoD, release phase | Combined summary **PASS** or **WARN** (no BLOCKER) |
| **G3** | Each **module phase complete** | Phase issues done, phase reports, module README, integration proof | Combined summary **PASS** or **WARN** (no BLOCKER) |
| **G4** | **Program release** (before Principal Release OK / staging) | Full program STATUS, demo evidence, `SHIP_CRITERIA.md`, proof manifest | Combined summary **PASS** only (WARN requires Principal ack) |

## Workflow

1. Read gate-specific inputs from the triggering role (Planner G1–G2; Orchestrator/Integrator G3–G4).
2. Run **each persona** independently against the same subject artifact set.
3. Each persona emits a structured verdict: `PASS` | `WARN` | `BLOCKER` with evidence (paths, commands, citations — no vacuous PASS).
4. Merge persona outputs into `LiNKdev/factory/templates/council-SUMMARY.md` format.
5. Write machine-readable report JSON conforming to `LiNKdev/factory/contracts/council-report.schema.json`.
6. Run `LiNKdev/factory/scripts/validate-council.sh <report.json> [--gate Gn] [--allow-warn]`.
7. On validation failure or any BLOCKER: stop; return report to triggering role with blockers listed. Do not advance STATE or create downstream artifacts.
8. On pass: attach report path to handoff; triggering role may proceed.

## Combined summary rules

| Persona verdicts | `summary_status` |
|----------------|------------------|
| Any BLOCKER | **BLOCKER** — progress halted |
| No BLOCKER, any WARN | **WARN** — may proceed if gate allows WARN |
| All PASS | **PASS** |

`blockers[]` must list every BLOCKER finding (persona id + one-line reason). Warnings belong in persona `warnings[]` or summary notes, not in `blockers[]`.

## Outputs

- Markdown summary from `LiNKdev/factory/templates/council-SUMMARY.md`
- JSON report at path chosen by triggering role, e.g.:
  - G1–G2: `LiNKdev/product/reports/<program-id>/council/G1-report.json`
  - G3: `LiNKdev/product/reports/<program-id>/<module-id>/<phase-id>/council-report.json`
  - G4: `LiNKdev/product/reports/<program-id>/council/G4-release-report.json`

## Triggers

| Gate | Triggered by |
|------|--------------|
| G1 | Planner after Principal OK on finished-product narrative |
| G2 | Planner after `PROGRAM.md` + issue tree drafted |
| G3 | Orchestrator when all issues in a module phase are `done` |
| G4 | Integrator when program DoD checklist complete, before Principal Release OK |

## Prohibited

- Skipping any advisor persona
- Proceeding with a BLOCKER unresolved
- Vacuous PASS without evidence paths or command output
- Merging to `staging` or `main` without G4 **PASS**

## Skills

See `LiNKdev/factory/install/SKILLS-ALLOWLIST.md` → Council (Planner, Orchestrator, Integrator contexts).
