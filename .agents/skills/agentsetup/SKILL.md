---
name: agentsetup
description: >-
  Bootstrap a NEW agent session onto a short-lived issue/* work branch from
  latest development for this consumer repo. Use for agentsetup or equivalent
  "start on the correct governed branch" requests.
version: 2.0.0-managed
status: active
tags: [git, agent, bootstrap, branching]
related_skills:
  - agentcomply
discovery:
  - .agents/skills/agentsetup/SKILL.md
---

# Agent Setup (NEW session) — Codex managed adapter

Bootstrap a **new agent** onto `issue/<id>-<slug>` for **this repository**.
Do not use for already-open dirty/wrong-branch work — use `agentcomply`.

## Authority (local; no `.cursor` required)

- This file: `.agents/skills/agentsetup/SKILL.md`
- Peer skill: `.agents/skills/agentcomply/SKILL.md`
- `scripts/gitops/create_issue_branch.py`
- `scripts/gitops/completion_gate.py`
- Managed core (optional deeper doctrine): `.ide-development/`
- Root `AGENTS.md` managed section (`BEGIN/END LINKTREND-IDE-MANAGED`)

Do **not** require the IDE Development checkout path. Do **not** require `.cursor` to be loaded.

## House rules

- One short-lived `issue/<id>-slug` per governed work package — not forever `dev/*`.
- **Never ask the human for issue id or slug.** The helper creates/reuses them.
- Never open a PR yourself. The Phase Packager/Coordinator (`scripts/gitops/packager_coordinator.py`) opens the Phase PR; retained `packager_discover.py` is not that component.
- Never merge your own PR; never promote to staging/main.
- Ship = checkpoint (commit + push) only.

## Inputs (ask only if missing)

1. **Task description** (GitHub issue title) if not already clear
2. **Target repo** only if multi-root / ambiguous

## Workflow

1. Identify repo root: `git rev-parse --show-toplevel`
2. Create/reuse issue + branch:

```bash
python3 scripts/gitops/create_issue_branch.py "<task description>" --prefer-worktree
# or:
python3 scripts/gitops/create_issue_branch.py --issue-number N
```

3. Confirm on the printed `BRANCH=` / `WORKTREE=` / `ISSUE_NUMBER=`
4. Remind: no implementer PR; when finished use `completion_gate.py write-evidence` then `review-ready`
5. Report branch, issue, and next step in plain English

## Fail closed

If `create_issue_branch.py` fails (auth, closed issue, collision), stop and report the error. Do not invent local issue numbers.
