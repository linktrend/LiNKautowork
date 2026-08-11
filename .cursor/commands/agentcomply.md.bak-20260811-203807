# Agent Comply

Use in an **ALREADY-OPEN** session to migrate onto a proper short-lived `issue/*` branch for **this repo**, and move uncommitted/wrong-branch work safely.

Simple model: no repo touch → no branch. Touch this repo → run agentcomply for this repo. Never silently adopt an unrelated open PR branch.

Operational summary:

- inspect git status, branch, dirty files, remotes
- ask only if needed for **task description** (helper creates issue id/slug) or target repo if ambiguous
- run `python3 scripts/gitops/create_issue_branch.py` when filing/reusing an issue branch from latest `development`
- move dirty work safely (stash/checkout/pop, worktree, or equivalent); never dump onto development/staging/main
- push the branch as a **checkpoint** (no PR). When finished, mark review-ready via completion gate — Review Packager opens the PR
- plain English summary of what was done

For a brand-new clean session, use agentsetup instead.

Read and execute `.cursor/skills/agentcomply/SKILL.md`.
