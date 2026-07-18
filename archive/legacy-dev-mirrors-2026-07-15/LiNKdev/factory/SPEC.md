# LiNKdev Specification

Version: 2.2  
Status: active (2026-05-31)

## 1. What LiNKdev is

LiNKdev is a **portable AI software factory**: Programs → Modules → Phases → **Issues**, coordinated through **GitHub + files**, with **Cursor-primary** dispatch (GitHub Actions + Cloud Agents API) and **Codex** as a future peer executor path.

Copy **only** **`.cursor/`** and **`LiNKdev/`** into a new repository. Do **not** add a root `AGENTS.md` — Cursor enters via `.cursor/rules/00-linkdev-bootstrap.mdc` → `LiNKdev/AGENTS.md`. The **product** subtree starts empty (except grounding stubs). **Factory** subtree is complete.

## 2. Layout

| Path | Purpose |
|------|---------|
| `LiNKdev/factory/` | Portable factory: SPEC, STATE, contracts, templates, scripts, install, prompts, bootstrap program |
| `LiNKdev/product/` | This repo only: grounding, programs, reports |
| `LiNKdev/skills/gstack/` | Universal product-development workflows (required in every template) |
| `LiNKdev/skills/host/` | This repository only (empty in virgin template) |

There is no `skills/factory/`. Factory roles use **gstack** and **host** via `LiNKdev/skills/SKILLS_CATALOG.md`. On conflict: **host wins** over gstack.

## 3. Coordination

Agents do not share one chat session. Coordination is:

- GitHub **labels**
- **`LiNKdev/factory/STATE.md`** (active wave only; Orchestrator is authoritative writer)
- Issue specs, **report_path**, branches, commits

## 4. Hierarchy

| Level | Name | Meaning |
|-------|------|---------|
| 1 | **Program** | Body of work |
| 2 | **Module** | Major area inside program |
| 3 | **Phase** | Stage group inside module |
| 4 | **Issue** | Single agent assignment |

Filesystem (new work):

`LiNKdev/product/programs/<program-id>/modules/<module-id>/phases/<phase-id>/issues/<issue-id>.md`

`PROGRAM.md` at program root is the DAG source of truth.

Reports mirror issues:

`LiNKdev/product/reports/<program-id>/<module-id>/<phase-id>/<issue-id>.md`

Integrator maintains `LiNKdev/product/reports/<program-id>/STATUS.md`.

## 5. Roles and runtimes

| Role | Runtime | Responsibility |
|------|---------|----------------|
| **Planner** | Cursor cloud (on **Go**) | Q&A with Principal → finished-product narrative → OK → create program + issues |
| **Orchestrator** | Cursor dispatch (GitHub Actions) | Advance STATE, set `linkdev:ready` (active wave cap in PROGRAM.md) |
| **Executor** | Cursor dispatch (`runtime:cursor`) | Implement issue on branch |
| **Reviewer** | Cursor dispatch | Spec + proof; reject vacuous PASS |
| **Integrator** | Cursor dispatch | Merge to `development`; program STATUS |
| **Principal** | Human | Go, Continue, staging/main, Release OK, optional pilot wave |

**Dispatch v2:** `.github/workflows/linkdev-dispatch.yml` calls the Cursor Cloud Agents API when labels/events match. Canonical doc: [docs/DISPATCH.md](docs/DISPATCH.md).

**Codex** executors (`linkdev:ready` + `runtime:codex`): documented for future dispatch; **not** wired in v1.

**Cursor Automations UI:** deprecated optional legacy — same labels, no AND logic on issues; do not require for wire.

## 6. Virgin repo → wire → dispatch → Go

1. Copy `.cursor/` + `LiNKdev/` (product/programs empty; product/grounding stubs; skills/host empty).
2. **Wire Step A (Cursor):** labels, guard workflow, copy dispatch workflows — [install/EXECUTE-WIRE-LINKDEV.md](install/EXECUTE-WIRE-LINKDEV.md).
3. **Wire Step B (Cursor):** confirm `CURSOR_API_KEY` GitHub secret + workflows on `development` — [install/EXECUTE-LINKDEV-DISPATCH-INSTALL.md](install/EXECUTE-LINKDEV-DISPATCH-INSTALL.md).
4. **Wire Step C (Cursor):** post-dispatch proof — [install/EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md](install/EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md).
5. **Principal Go — cloud Cursor Planner:** Q&A until ≥95% clarity → plain-English **finished product** description → Principal OK → Planner **creates** `product/programs/<program-id>/` (no program exists before Go).
6. **Planner handoff (automatic):** G2 PASS → STATE `phase: running`, `next_orchestrator_trigger: go` → `planner-handoff.sh` writes `.linkdev/handoff/planner-complete.json` and pushes → **`linkdev-planner-bootstrap`** workflow merges to `development` and dispatches **Orchestrator** (zero Principal merge).
7. **Loop:** Orchestrator → Executor → Reviewer → Integrator → … until program complete or `linkdev:principal-stop`.

**Principal Continue** clears chairman stop and resumes Orchestrator.

Repos with an existing program (e.g. LiNKtrend migration) may run Planner without Go to update the plan.

Launch lines: [install/PRINCIPAL-LAUNCH.md](install/PRINCIPAL-LAUNCH.md).

## 7. Bootstrap program

`LiNKdev/factory/programs/bootstrap/` — frozen history of building the factory (DS-001…046). Not re-run after wire. Reports under `LiNKdev/factory/reports/bootstrap/`.

## 8. Branches

- Integration: **`development`**
- Issue work: `issue/<id>-<slug>` or `dev/<machine><ide>` per host SOP
- Principal only: **`staging`**, **`main`**

## 9. Labels

See [contracts/labels.md](contracts/labels.md).

Executor sets `linkdev:merge-ready` only when `LiNKdev/factory/scripts/verify.sh` exits 0 (tier-aware). Release-phase **critical** issues may set `LINKDEV_SCOPE=.` (repo root).

## 10. Issue contract

Frontmatter: [contracts/issue-frontmatter.schema.json](contracts/issue-frontmatter.schema.json).

Planner **copies** `factory/templates/issue.md` — fill fields; do not invent structure.

- `read_first`: exact paths only
- `read_forbidden`: includes `LiNKdev/archive/**`, `LiNKdev/product/reports/**` (except own `report_path`), glob reads of `grounding/**`

## 11. Product grounding (anti-drift)

`LiNKdev/product/grounding/` — stable product truth for **this repo**. Planner fills after Go OK. Issues link specific files; agents do not list the whole tree.

## 12. Program Definition of Done

Every `PROGRAM.md` includes **Program Definition of Done** and a **release** module/phase with **critical** issues: verify, proof manifest, `grounding/SHIP_CRITERIA.md`, demo evidence. Principal **Release OK** before staging/main.

See [BORROW-PACK.md](BORROW-PACK.md) B14–B18.

## 13. Borrow pack

[BORROW-PACK.md](BORROW-PACK.md) — UBS-inspired gates (DS-B1 … DS-B25); not full UBS. Peer review: [PEER-REPO-BORROW-REVIEW.md](PEER-REPO-BORROW-REVIEW.md). No second orchestration stack. No mandatory gstack `/ship` on every issue (release phase only). Laws, intent, tiers, council, manifest, and worktree: §17–22.

## 14. Skills

- Catalog: `LiNKdev/skills/SKILLS_CATALOG.md`
- Routing: `LiNKdev/factory/install/SKILLS-ALLOWLIST.md`
- Merge history: `LiNKdev/skills/MERGE-LOG.md`

## 15. Wire

[install/WIRE-PROMPT.md](install/WIRE-PROMPT.md) → [install/CHECKLIST.md](install/CHECKLIST.md).

## 16. LiNKtrend hosting

Legacy work packets: `LiNKdev/product/programs/linktrend-system/issues/legacy/`. Migration: [../product/programs/linktrend-system/MIGRATION.md](../product/programs/linktrend-system/MIGRATION.md).

## 17. Laws

Eight enforceable laws: [laws/LINKDEV_LAWS.md](laws/LINKDEV_LAWS.md) (DS-B19).

- **LAW-01** — No vacuous proof (Reviewer + Integrator).
- **LAW-02** — Intent PASS before execution (`validate-intent.sh`).
- **LAW-03** — Tier gates mandatory (`LINKDEV_TIER=critical` on release issues).
- **LAW-04** — No secrets in repo (`verify.sh` scan).
- **LAW-05** — One branch per issue; no worktrees (see §22).
- **LAW-06** — No merge to `staging`/`main` without Principal Release OK.
- **LAW-07** — Council BLOCKER stops progress until resolved or waived.
- **LAW-08** — Program release requires SHA256 manifest; **no cosign witness**.

## 18. Intent verdict

Product intent lives in `LiNKdev/product/grounding/INTENT.md` (from [templates/INTENT.md](templates/INTENT.md)). Planner writes after Principal OK; links `VISION.md` and `SHIP_CRITERIA.md` (DS-B24).

Machine verdict:

- Schema: [contracts/intent-verdict.schema.json](contracts/intent-verdict.schema.json)
- Template: [templates/intent-verdict.json](templates/intent-verdict.json)
- Paths (newest wins): `LiNKdev/product/reports/<program-id>/intent-verdict.json` or `LiNKdev/product/programs/<program-id>/intent-verdict.json`

**Orchestrator must not set `linkdev:ready` until:**

1. Council **G2** has no BLOCKER (LAW-07).
2. `LiNKdev/factory/scripts/validate-intent.sh <program-id>` exits 0 (LAW-02, DS-B20).

## 19. Tier gates A / B / C

Catalog: [gates/catalog.json](gates/catalog.json). Runner: [scripts/run-gates.sh](scripts/run-gates.sh) (DS-B21).

| Tier | When | Key gates |
|------|------|-----------|
| **A** | Per issue — merge-ready | `verify_subset`, secrets, proof block, allowed files, working tree clean |
| **B** | Module phase complete | DAG, integration smoke, architecture gate (JS/TS), council G3 |
| **C** | Program release (critical) | Full verify, program proof manifest, replay merge, ship criteria, council G4 |

`verify.sh` invokes tier **A** unless `LINKDEV_SKIP_GATES=1`. Release **critical** issues set `LINKDEV_TIER=critical` and `LINKDEV_SCOPE=.` (DS-B16). Stack-driven smoke/typecheck reads `LiNKdev/product/grounding/STACK.md`.

## 20. Council G1–G4

Multi-advisor gate: [prompts/council/ROLE.md](prompts/council/ROLE.md) (DS-B22). All five personas run every time; any **BLOCKER** halts progress (LAW-07).

| Gate | Trigger | Proceed when |
|------|---------|--------------|
| **G1** | Planner — after Principal OK on finished-product narrative | PASS or WARN (no BLOCKER) |
| **G2** | Planner — after `PROGRAM.md` + intent verdict | PASS or WARN; intent script must pass before Orchestrator runs |
| **G3** | Orchestrator — module phase complete | PASS or WARN; validated by tier B `council_g3_report` |
| **G4** | Integrator — before Principal Release OK | **PASS** only (WARN needs Principal ack) |

Reports: [contracts/council-report.schema.json](contracts/council-report.schema.json). Validate: [scripts/validate-council.sh](scripts/validate-council.sh).

## 21. Program proof manifest

Release phase emits SHA256 manifest over reports and proof artifacts (LAW-08, DS-B23):

```bash
LiNKdev/factory/scripts/program-proof-manifest.sh <program-id>
```

Output default: `LiNKdev/product/reports/<program-id>/proof-manifest.json`.

Per-issue manifest (`proof-manifest.sh`) remains required for **critical** tier issues. **Cosign witness is explicitly rejected** — hash manifest only. See [PEER-REPO-BORROW-REVIEW.md](PEER-REPO-BORROW-REVIEW.md).

## 22. Branch isolation (no worktrees; no container v1)

Every executor issue **must** use branch `issue/<issue-id>-<slug>` from `development` on **one repo checkout** (LAW-05, DS-B25). Git worktrees are **forbidden** in LiNKdev — they break handoffs.

When the active wave has more than one `linkdev:ready` issue, **never** run two executors on the same checkout simultaneously. Run issues sequentially, or assign parallel issues to **different machines/IDEs** (separate `dev/<machine><ide>` branches).

Container sandbox v1 is **not** required. Decision: [docs/LINKDEV_SANDBOX.md](docs/LINKDEV_SANDBOX.md).
