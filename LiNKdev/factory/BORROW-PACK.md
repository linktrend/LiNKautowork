# LiNKdev Borrow Pack

Quality and verification patterns borrowed from UBS and peer factories. **Not full UBS.** No second orchestration stack (CrewAI/LangGraph/n8n brain). No mandatory gstack `/ship` on every issue.

| ID | Item | Status |
|----|------|--------|
| DS-B1 | Mechanical verify (`factory/scripts/verify.sh`) | Active |
| DS-B2 | No vacuous PASS (Reviewer) | Active |
| DS-B3 | Testable acceptance criteria | Active |
| DS-B4 | DAG validation (`validate-dag.sh`) | Active |
| DS-B5 | Structured proof block in reports | Active |
| DS-B6 | Issue tiers (`standard`, `critical`) | Active |
| DS-B7 | Light proof manifest (`proof-manifest.sh`) | Active |
| DS-B8 | Portable `LiNKdev/AGENTS.md` | Active |
| DS-B9 | Git + verify before `linkdev:merge-ready` | Active |
| DS-B10 | Trajectory / debug in reports | Active |
| DS-B11 | Merge replay traceability (`replay-merge-verify.sh`) | Active |
| DS-B12 | Isolation decision (branches only; no worktrees; no container v1) | `factory/docs/LINKDEV_SANDBOX.md` |
| DS-B13 | Per-issue `runtime` field | Active |
| DS-B14 | **Program Definition of Done** in every `PROGRAM.md` | Required for new programs |
| DS-B15 | **Release phase** with ≥1 `critical` issue | Required for new programs |
| DS-B16 | `LINKDEV_SCOPE=.` on release verify | Release issues |
| DS-B17 | No vacuous program complete (Integrator) | Active |
| DS-B18 | Commit traceability `(<issue-id>)` | Integrator + Executor |
| DS-B19 | **LiNKdev laws** (`laws/LINKDEV_LAWS.md`, LAW-01 … LAW-08) | All roles; intent + release |
| DS-B20 | **Intent verdict gate** (`validate-intent.sh`; blocks `linkdev:ready`) | Orchestrator + Planner G2 |
| DS-B21 | **Tier gates A/B/C** (`gates/catalog.json` + `run-gates.sh`) | Executor A; Integrator B/C |
| DS-B22 | **Council G1–G4** (five personas; BLOCKER stops progress) | Planner, Orchestrator, Integrator |
| DS-B23 | **Program SHA256 manifest** (`program-proof-manifest.sh`; no cosign) | Release critical tier |
| DS-B24 | **Product intent** (`product/grounding/INTENT.md` + verdict JSON) | Planner after Principal OK |
| DS-B25 | **Branch-per-issue enforcement** (no worktrees; no container v1) | All executors |

**Not adopted from UBS:** full 28-gate per-issue bundle, mandatory cosign, container sandbox v1.

See [PEER-REPO-BORROW-REVIEW.md](PEER-REPO-BORROW-REVIEW.md) for tiered peer-repo rationale.
