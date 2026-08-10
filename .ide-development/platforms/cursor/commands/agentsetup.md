# Agent Setup

Use at the **start of a NEW** session that will code in this repo to bootstrap onto a short-lived `issue/<id>-<slug>` branch from latest `development`.

Simple model: no repo touch → no branch. Touch this repo → run agentsetup for this repo.

Operational summary:

- detect current repo context
- ask only for missing **task description** (and target repo if multi-root/ambiguous) — **never** ask for issue id/slug
- run `python3 scripts/gitops/create_issue_branch.py` (creates/reuses GitHub issue + `issue/<n>-<slug>` from `origin/development`; prefer worktree when dirty)
- confirm ready; remember Ship = checkpoint only (no implementer PR, no merge, no self-review, no staging/main)
- when finished later: `python3 scripts/gitops/completion_gate.py write-evidence` then `review-ready`; Packager opens the PR
- report branch, issue, repo, and next steps in plain English

For an already-open dirty or wrong-branch session, use agentcomply instead.

Read and execute `.cursor/skills/agentsetup/SKILL.md`.
