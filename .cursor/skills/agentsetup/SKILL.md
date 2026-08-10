---
name: agentsetup
description: >-
  Bootstrap a NEW agent session onto a short-lived issue/* work branch from
  latest development for this consumer repo. Use for /agentsetup or equivalent
  "start on the correct governed branch" requests.
version: 2.0.0-managed
status: active
tags: [git, agent, bootstrap, branching]
related_commands:
  - agentsetup
related_skills:
  - agentcomply
---

# Agent Setup (NEW session) — Cursor managed adapter

Bootstrap a **new agent** onto `issue/<id>-<slug>` for **this repository**.
Do not use for already-open dirty/wrong-branch work — use `agentcomply`.

## Authority (installed locally in this repo)

- `.cursor/rules/cursor-gitops-bootstrap.mdc`
- `.cursor/rules/linktrend-git-branching.mdc`
- `.cursor/commands/agentsetup.md`
- `.cursor/skills/agentsetup/SKILL.md` (this file)
- `scripts/gitops/create_issue_branch.py`
- `scripts/gitops/completion_gate.py`
- Managed core (optional deeper doctrine): `.ide-development/`

Do **not** require the IDE Development checkout path.

## House rules

- One short-lived `issue/<id>-slug` per governed work package — not forever `dev/*`.
- **Never ask the human for issue id or slug.** The helper creates/reuses them.
- Never open a PR yourself; Review Packager opens PRs.
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
