# Executor (Cursor) role

Implement one **issue spec** on a branch. Triggered by `linkdev:ready` + `runtime:cursor` (automation or manual bootstrap).

## Before edit

1. `git status --short --branch` — stop if unrelated dirty files
2. Read issue spec + `LiNKdev/factory/SPEC.md`
3. **Branch only (LAW-05, DS-B25):** checkout `issue/<issue-id>-<slug>` from `development`. No git worktrees. If active wave > 1, never run two executors on this same checkout at once — use another machine/IDE or wait for the prior issue to push.

## During

- Edit only `allowed_files`
- Never commit `.env` or secrets
- Commit incrementally with conventional commits; include `(<issue-id>)` in subject when required (DS-B18)

## Before handoff

1. Run proof commands from issue spec
2. Set tier from issue frontmatter and run verify:

```bash
export LINKDEV_TIER=<standard|critical>   # critical for release-phase issues
LiNKdev/factory/scripts/verify.sh
```

3. Tier **A** gates run via `verify.sh` → `run-gates.sh --tier A`. If tier A fails, fix before merge-ready.
4. Update report with proof block (DS-B5) and **Trajectory / debug** section (DS-B10)
5. **Critical tier:** run per-issue manifest (required):

```bash
LiNKdev/factory/scripts/proof-manifest.sh <report-path>
```

6. Open PR; label `linkdev:review-ready`; only set `linkdev:merge-ready` if verify and tier A passed (DS-B9)

## Skills

See `LiNKdev/factory/install/SKILLS-ALLOWLIST.md` → Executor (Cursor).
