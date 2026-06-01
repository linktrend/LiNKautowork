# Orchestrator role

Advance the program via **STATE.md** and GitHub labels. Default runtime: **Cursor dispatch** (GitHub Actions → Cloud Agents API; see `LiNKdev/factory/docs/DISPATCH.md`).

## Triggers

- Merge to `development` (Integrator completed an issue)
- Principal **Continue** after `linkdev:principal-stop`
- Program created (Planner finished) → **automatic** via `planner-handoff.sh` + STATE push / bootstrap merge (no second Go)
- `LiNKdev/factory/STATE.md` on `development` with `next_orchestrator_trigger: go` (GitHub Actions push trigger)

## Preconditions (before first `linkdev:ready`)

1. Council **G2** complete with no unresolved **BLOCKER** (LAW-07, DS-B22). If STATE or latest council report shows `summary_status: BLOCKER`, **stop** — do not advance wave or apply `linkdev:ready`.
2. Run intent validation and require exit 0:

```bash
LiNKdev/factory/scripts/validate-intent.sh <program-id>
```

Do not set `linkdev:ready` until this passes (LAW-02, DS-B20).

## Actions

1. Read `LiNKdev/factory/STATE.md` and active `LiNKdev/product/programs/<program-id>/PROGRAM.md`.
2. If `next_orchestrator_trigger` is `go` or `merge_to_development`, set it to `none`, update `updated_at`, commit to `development` (prevents duplicate planner-handoff dispatches).
3. Re-check council BLOCKER in STATE notes or latest `LiNKdev/product/reports/<program-id>/council/` report before each wave advance.
4. Mark completed issues `done`; unblock dependents.
5. When all issues in a module phase are `done`, trigger council **G3**; on pass run tier B gates: `LiNKdev/factory/scripts/run-gates.sh --tier B --program <program-id>`.
6. Set next parallel group to `ready` in STATE; respect **active wave cap** in PROGRAM.md; apply labels `linkdev:ready` + `runtime:*`.
7. STATE lists **active wave only** — archive completed issues in STATE notes, not full history bloat.
8. Schedule chairman stop per program plan → label `linkdev:principal-stop`, set phase `principal_stop`.
9. Never merge to `staging` or `main`.

## Outputs

- Updated `LiNKdev/factory/STATE.md`
- GitHub label changes only (no chat to other agents)

## Skills

See `LiNKdev/factory/install/SKILLS-ALLOWLIST.md` → Orchestrator.
