# GitHub labels (LiNKdev)

Apply on **issues** and/or **PRs** as noted. Colors are suggestions for GitHub UI setup during wire.

## Orchestration

| Label | Meaning | Who sets | Who clears |
|-------|---------|----------|------------|
| `linkdev:planned` | Issue spec committed; not ready for execution | Planner / Integrator | Orchestrator when ready |
| `linkdev:ready` | Executor may start (automation trigger) | Orchestrator | Executor when branch work starts |
| `linkdev:in-progress` | Executor active | Executor | Executor |
| `linkdev:review-ready` | PR or report ready for Reviewer | Executor | Reviewer |
| `linkdev:merge-ready` | Verify passed; Integrator may merge to `development` | Executor (after verify) | Integrator |
| `linkdev:blocked` | Stop line; Principal or Orchestrator decision needed | Any role | Orchestrator after resolution |
| `linkdev:done` | Issue closed on `development` | Integrator | — |

## Runtime (executor selection)

| Label | Meaning |
|-------|---------|
| `runtime:cursor` | Cursor cloud or manual Cursor executor |
| `runtime:codex` | Codex automation or session |

Filter automations: fire only when `linkdev:ready` **and** matching `runtime:*`.

## Tier (optional)

| Label | Meaning |
|-------|---------|
| `tier:standard` | Default verify bundle |
| `tier:critical` | Expanded verify bundle (see `scripts/verify.sh`) |

## Program control

| Label | Meaning |
|-------|---------|
| `linkdev:program-active` | Program running (on tracking issue or STATE PR) |
| `linkdev:principal-stop` | Scheduled briefing checkpoint; automations pause new `linkdev:ready` until Continue |

## Promotion (Principal only)

| Label | Meaning |
|-------|---------|
| `linkdev:promote-staging` | Principal authorized staging promotion (informational) |
| `linkdev:promote-main` | Principal authorized main promotion (informational) |

Integrator **never** merges to `staging` or `main` without Principal action.
