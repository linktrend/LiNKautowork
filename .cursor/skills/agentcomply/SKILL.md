---
name: agentcomply
description: >-
  Migrate an ALREADY-OPEN agent onto a proper short-lived issue/* branch for
  this consumer repo, safely moving dirty work. Use for /agentcomply or
  equivalent compliance requests.
version: 2.0.0-managed
status: active
tags: [git, agent, migration, compliance, branching]
related_commands:
  - agentcomply
related_skills:
  - agentsetup
---

# Agent Comply (ALREADY-OPEN session) — Cursor managed adapter

Migrate an **already-open agent** onto `issue/<id>-<slug>` for **this repository**, preserving dirty work.

## Authority (installed locally in this repo)

- `.cursor/rules/cursor-gitops-bootstrap.mdc`
- `.cursor/rules/linktrend-git-branching.mdc`
- `.cursor/commands/agentcomply.md`
- `.cursor/skills/agentcomply/SKILL.md` (this file)
- `scripts/gitops/create_issue_branch.py`
- `scripts/gitops/completion_gate.py`
- Managed core (optional deeper doctrine): `.ide-development/`

Do **not** require the IDE Development checkout path.

## House rules

- Never dump work onto `development` / `staging` / `main`.
- Never silently adopt an unrelated open PR branch.
- **Never ask for issue id/slug** — helper creates/reuses them from the task description.
- Never open a PR yourself; Review Packager opens PRs.
- Never commit secrets.

## Inputs (ask only if needed)

1. **Task description** if missing
2. **Target repo** if multi-root / ambiguous
3. Whether to commit/push a checkpoint (ask if ambiguous)

## Workflow

1. Inspect: `git status`, `git branch --show-current`, remotes
2. If already on a matching clean `issue/<id>-slug` for this work package, confirm and stop
3. Otherwise create/reuse branch:

```bash
python3 scripts/gitops/create_issue_branch.py "<task description>" --prefer-worktree
```

4. Move dirty work safely (stash → checkout/worktree → pop). Never force onto protected branches.
5. Push checkpoint only when asked or clearly ready
6. When the issue is finished later: `completion_gate.py write-evidence` then `review-ready` (normal-token publisher if local privileged publish fails closed; never write `.linktrend/review-ready.json`)
7. Summarize what moved and the active branch/issue

## Fail closed

If helper or git moves fail, stop with the error. Do not invent IDs or force-push.
