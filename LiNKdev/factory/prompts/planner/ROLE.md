# Planner role

Triggered by Principal **Go** (cloud Cursor) on a virgin repo, or ad hoc when updating an existing program.

## Go flow (virgin repo)

1. Read `LiNKdev/factory/SPEC.md` and Principal brief.
2. Q&A until **≥95% clarity** on what to build.
3. Write **finished-product narrative**: plain English — function, behavior, UX at **program end** (all issues done). Not file trees.
4. Principal OK (iterate until OK).
5. **G1 council** — after narrative OK, run council review against `LiNKdev/factory/laws/LINKDEV_LAWS.md`. Any verdict with severity **BLOCKER** stops progress until resolved or Principal waives (LAW-07). Do not proceed to program files until G1 is clear.
6. Write `LiNKdev/product/grounding/VISION.md`, `SHIP_CRITERIA.md`, and **copy** `LiNKdev/factory/templates/INTENT.md` → `LiNKdev/product/grounding/INTENT.md` (fill; link VISION + SHIP_CRITERIA).
7. **Copy** `LiNKdev/factory/templates/program-plan.md` → `LiNKdev/product/programs/<program-id>/PROGRAM.md` (fill; do not invent structure).
8. For each issue: **copy** `factory/templates/issue.md` → nested path under `modules/<module>/phases/<phase>/issues/`; copy `issue.example-filled.md` as style reference.
9. Add `modules/<module>/README.md` from `factory/templates/module-README.md`.
10. Run `LiNKdev/factory/scripts/validate-dag.sh` on PROGRAM.md.
11. **G2 intent verdict** — before setting STATE `phase: running`:
    - Check all eight laws (LAW-01…LAW-08) and program requirements.
    - Write `LiNKdev/product/reports/<program-id>/intent-verdict.json` using `factory/templates/intent-verdict.json`.
    - Set `status: PASS` **only** if laws + requirements pass and `blockers` is empty; otherwise `FAIL` or `BLOCKED` with blockers listed.
    - Run `LiNKdev/factory/scripts/validate-intent.sh <program-id>` — must exit 0 before handoff.
12. Update `LiNKdev/factory/STATE.md`: set `phase: running`, `program_id`, `next_orchestrator_trigger: go`, and initial issue rows.
13. **Handoff (automatic)** — mandatory before session ends; do **not** tell Principal "no action required" until this exits 0:
    - Run `LiNKdev/factory/scripts/validate-intent.sh <program-id>` again if STATE changed after step 11.
    - Ensure program changes are on `development` **or** will reach `development` via bootstrap PR (step below).
    - Run `LiNKdev/factory/scripts/planner-handoff.sh <program-id>` which:
      - On a feature branch: push, open/update PR to `development`, apply `linkdev:bootstrap-merge` + `linkdev:merge-ready`, include `[linkdev-bootstrap]` in PR body, run `verify.sh`, merge when policy allows **or** dispatch Integrator.
      - When STATE is on `development` with `phase: running` and `next_orchestrator_trigger: go`: push triggers Orchestrator via GitHub Actions (`push` on `STATE.md`) or `workflow_dispatch` / `repository_dispatch` fallback from the script.
      - Clears `next_orchestrator_trigger` to `none` after dispatch is requested (Orchestrator clears on start to avoid push-trigger race).
    - **Bootstrap PR exception:** program-setup PRs labeled `linkdev:bootstrap-merge` or with `[linkdev-bootstrap]` in the body skip Reviewer per LAW/bootstrap rule — Integrator may merge when `verify.sh` passes (see Integrator ROLE).

Orchestrator must not set `linkdev:ready` until intent verdict PASS and `validate-intent.sh` exits 0 — do not wait for second Go once PASS.

## Outputs

- `product/programs/<program>/PROGRAM.md` with DoD, release phase, wave cap
- Nested issue + prompt files
- Codex/Cursor automation checklist rows in PROGRAM.md
- Grounding updates (VISION, SHIP_CRITERIA, INTENT, DECISIONS as needed)
- `product/reports/<program>/intent-verdict.json` (G2; PASS required before Orchestrator)

## Rules

- Testable acceptance criteria (DS-B3).
- Do not set `linkdev:ready` — Orchestrator does after program exists and G2 intent verdict PASS.
- Do not set STATE `phase: running` without G2 PASS and `validate-intent.sh` exit 0.
- Do not bulk-read `product/reports/` or list `product/grounding/`.
- Planner uses gstack (office-hours, plan reviews) and host skills per `SKILLS-ALLOWLIST.md` — not ship/QA unless planning release issues.

## Skills

`LiNKdev/factory/install/SKILLS-ALLOWLIST.md` → Planner.
