# LiNKdev automation manifest — **deprecated for wire**

> **Dispatch v2** replaces this manifest. See [../../docs/DISPATCH.md](../../docs/DISPATCH.md) and `.github/workflows/linkdev-dispatch.yml`. Legacy UI rows below are reference only.

---

# LiNKdev automation manifest

Principal previously registered these using **Codex computer use** ([CURSOR-CREATE-AUTOMATIONS.md](CURSOR-CREATE-AUTOMATIONS.md), [CODEX-CREATE-AUTOMATIONS.md](CODEX-CREATE-AUTOMATIONS.md)) — **do not use for new installs**.

## Cursor cloud automations

| Name | Role | Trigger | Reads |
|------|------|---------|-------|
| `LiNKdev-orchestrator` | Orchestrator | Push/merge to `development` | `factory/prompts/orchestrator/ROLE.md`, `factory/STATE.md`, active `product/programs/*/PROGRAM.md` |
| `LiNKdev-reviewer` | Reviewer | Label `linkdev:review-ready` | `factory/prompts/reviewer/ROLE.md`, issue + `report_path` |
| `LiNKdev-integrator` | Integrator | Label `linkdev:merge-ready` | `factory/prompts/integrator/ROLE.md`, issue + report |
| `LiNKdev-executor-cursor` | Executor | Labels `linkdev:ready` + `runtime:cursor` | `factory/prompts/executor-cursor/ROLE.md`, issue spec only |

## Codex cloud automations

| Name | Role | Trigger | Reads |
|------|------|---------|-------|
| `LiNKdev-executor-codex` | Executor | Labels `linkdev:ready` + `runtime:codex` | `factory/prompts/executor-codex/ROLE.md`, issue spec only |

Create additional Codex automations per rows in `product/programs/*/PROGRAM.md` Codex checklist.

## Planner (Go)

Not a standing automation on virgin repo. Principal starts **cloud Cursor** with command **linkdev Go** (`.cursor/commands/linkdev-go.md`) → `factory/prompts/planner/ROLE.md`.

After program exists, Orchestrator runs **automatically** on merge to `development`.
