# LiNKdev — Principal monitoring (plain English)

Version: 1.0 · Status: active (2026-06-01)

**Do not use the Cursor Web home dashboard as your LiNKdev control panel.** API-dispatched factory agents often do not appear there the same way as agents you typed into the Composer box.

## Your one place to watch: GitHub Issues

For program host **LiNKtrend-System**, open the wave issues (example wave 1):

- [#20 LTS-001](https://github.com/linktrend/LiNKtrend-System/issues/20)
- [#44 LTS-010](https://github.com/linktrend/LiNKtrend-System/issues/44)
- [#30 LTS-020](https://github.com/linktrend/LiNKtrend-System/issues/30)

Each issue gets **automatic bot comments** from GitHub Actions:

| Marker | Meaning |
|--------|---------|
| `[linkdev-dispatch]` | Agent **started** — includes link to open in Cursor (optional) |
| `[linkdev-agent-watch]` | **Still running**, **finished**, or **failed** (every ~10 min while active) |

**Subscribe to notifications:** click **Subscribe** on each active issue (or watch the repo) — GitHub emails you when status comments arrive. You do not need to stare at a screen.

## Label meanings (at a glance)

| Label | Meaning |
|-------|---------|
| `linkdev:ready` | Waiting for executor to start |
| `linkdev:in-progress` | Executor dispatched / working |
| `linkdev:review-ready` | PR ready for reviewer (executor done coding) |
| `linkdev:merge-ready` | Integrator may merge to `development` |
| `linkdev:done` | Issue closed on `development` |
| `linkdev:blocked` | **Stopped — needs agent or Principal decision** |
| `linkdev:principal-stop` | Scheduled briefing — you say Continue |

## How you know each stage is done

| Stage | Done when |
|-------|-----------|
| **Executor** | Issue comment says **FINISHED** *and* a PR exists with `linkdev:review-ready` |
| **Reviewer** | PR gets `linkdev:merge-ready` |
| **Integrator** | PR merged to `development`; issue moves toward `linkdev:done` |
| **Orchestrator** | Next wave issues get `linkdev:ready` (or `STATE.md` on `development` shows `ready`) |
| **Something broke** | `[linkdev-agent-watch]` comment with ❌, or label `linkdev:blocked`, or red **LiNKdev agent watch** / **LiNKdev dispatch** in Actions |

## Optional checks (not required every day)

1. **Actions** → `LiNKdev agent watch` (scheduled) and `LiNKdev dispatch` (on label events)
2. **`LiNKdev/factory/STATE.md`** on branch `development` — program wave status (JSON)
3. **Cursor agent link** in the dispatch comment — only if you want live detail; not required for pass/fail

## If nothing updates for 30+ minutes

Tell your LiNKdev agent (Cursor chat): *"LiNKdev stalled — check issue #N and agent watch."*  
Do **not** manually merge, label, or re-run Go unless you see `linkdev:principal-stop` or `linkdev:blocked`.

See also: [DISPATCH.md](./DISPATCH.md)
