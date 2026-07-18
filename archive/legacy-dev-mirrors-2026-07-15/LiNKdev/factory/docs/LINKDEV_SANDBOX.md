# LiNKdev isolation decision (DS-B12)

## Decision

**MVO factory isolation is branch-based on a single repo checkout.** No git worktrees. No container sandbox in v1.

| Mechanism | Required? |
|-----------|-----------|
| **Issue branch** `issue/<issue-id>-<slug>` from `development` | **Yes** — every executor issue |
| **Host dev branch** `dev/<machine><ide>` when not using issue branches | Optional per host SOP |
| **Git worktrees** under `.worktrees/` | **No** — not part of LiNKdev |
| **Container sandbox** | **No** in v1 (DS-B12) |

## Executor rules (deterministic)

1. Before edit: `git status --short --branch` must be clean except documented exclusions.
2. Create or checkout **only** the issue branch for this assignment.
3. When STATE active wave > 1: **never** run two executors on the same checkout at the same time. Schedule parallel issues on **different machines/IDEs** (separate `dev/*` branches) or run waves sequentially.
4. Handoff = commit + push on the issue branch + report with proof block. Uncommitted local-only work is incomplete.

## Rationale

- Branch-per-issue keeps GitHub PRs, Integrator merges, and `replay-merge-verify.sh` traceable.
- Worktrees caused handover failures (wrong tree, lost commits, path confusion).
- `verify.sh` + `allowed_files` + tier A `working_tree_clean` gate provide sufficient isolation without worktrees.
- Containers add ops cost before the first program ships.

## Future: containers only

Revisit when executors run untrusted multi-tenant code or live side effects without capability leases. Document in `factory/install/automations/README.md` and add a `critical` tier flag if adopted.

## Normative references

- LAW-05, DS-B25: `factory/laws/LINKDEV_LAWS.md`, `factory/BORROW-PACK.md`
- Coordination: `factory/rules/03-agent-swarm-coordination.mdc`
- SPEC §22: `factory/SPEC.md`
