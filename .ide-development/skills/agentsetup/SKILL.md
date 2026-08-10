---
name: agentsetup
description: >-
  Bootstrap a NEW agent session onto a short-lived issue/* work branch from
  latest development for the repo being touched. Use when Carlos runs
  /agentsetup or asks to start a new agent on the correct governed branch.
version: 1.3.0
status: active
tags: [git, agent, bootstrap, branching, ship-pull]
related_commands:
  - agentsetup
related_skills:
  - agentcomply
  - git-safeguard
---

# Agent Setup (NEW session)

Bootstrap a **new agent** onto a short-lived `issue/<id>-<slug>` branch for the **repo being touched**. Do not use this for already-open agents with dirty or wrong-branch work — use `agentcomply`.

## Authority

- `.cursor/rules/01-git-branching.mdc`
- `.cursor/rules/02-autonomous-ship-pull.mdc`
- `docs/AUTONOMOUS-GIT-OPERATIONS.md`
- `docs/contracts/AGENT-COMPLETION.md`

## House rules (locked)

- **`/agentsetup` is primarily for Implementers** that own work in **one repo**.
- **Orchestrators** should not use setup to invent a fake forever home repo/branch. Coordination-only → no branch. Coding in a repo → open/direct a per-repo Implementer (or run setup for **that** repo only).
- **No code/repo touch → no branch required.** Coordination-only sessions that do not edit a repo do not need `/agentsetup`.
- **Touch a repo → setup for that repo.** Any agent that will edit a repo (including an orchestrator that starts coding) runs `/agentsetup` for **that** repo.
- **One short-lived `issue/<id>-slug` per piece of governed work** — not forever `dev/*` home branches.
- Branch must match **this work package**. Do not silently adopt an unrelated open PR branch just because it exists.
- Multi-root: if which repo is being touched is ambiguous, ask (normal ambiguity ask).
- `cursor/*` for cloud/dashboard agents.
- `dev/*` rare ad-hoc only.
- Never merge own PR; never self-review; never touch `staging`/`main`. Bugbot reviews; Integrator merges.
- **Do not ask Carlos for issue id or slug.** Use `scripts/gitops/create_issue_branch.py` (creates or reuses the GitHub issue and branch).

## Use When

- Carlos invokes `/agentsetup`
- A brand-new coding agent needs a correct work branch before coding in a repo

## Scope Out

- Migrating an already-open dirty session → `agentcomply`
- Sessions that will not touch any repo (no branch work needed)
- Lisa Option A clock, doctrine rewrites, Integrator/Promoter landing
- Committing or opening PRs unless Carlos explicitly asks during setup

## Inputs (ask only if missing)

Ask Carlos only when truly missing:

1. **Task description** (title for the GitHub issue) if not already clear from the message
2. **Target repo** if multi-root / ambiguous

Do **not** ask for issue number or slug. Optional: if Carlos already named an issue number, pass `--issue-number`.

## Workflow

### 1. Detect repo context

- Identify the git repo for this session (`git rev-parse --show-toplevel`).
- Multi-root workspace: if more than one product repo is in play and Carlos did not name one, ask which repo is being touched.
- Confirm remote and that `development` exists as the integration branch.

### 2. Create issue + branch via helper

Run from the target repo (fail closed — never invent local IDs):

```bash
python3 scripts/gitops/create_issue_branch.py "<task description>" [--repo owner/name] [--prefer-worktree]
# or with known issue:
python3 scripts/gitops/create_issue_branch.py --issue-number N "<optional title override>"
```

Parse KEY=value lines: `ISSUE_NUMBER`, `BRANCH`, `WORKTREE`, `SLUG`.
`cd` into `WORKTREE` when it differs from the current checkout.

### 3. Confirm ready + hard stops

Confirm:

- current branch is `issue/<id>-<slug>`
- working tree clean (or only expected pre-existing noise Carlos knows about)
- tracking not yet required (push happens at Ship or when Carlos asks)

Remind hard stops in plain English:

- Do **not** merge into `development`
- Do **not** self-review (Bugbot reviews)
- Do **not** promote to `staging` or `main`
- Do **not** open a PR (Review Packager opens PRs)
- Ship waves: **checkpoint only** = commit → push → stop (no PR, no Bugbot)
- When finished: `scripts/gitops/completion_gate.py review-ready` after `mark-review-ready.sh`

### 4. Report

Plain English summary:

- **Repo:** path or name
- **Issue:** number from helper
- **Branch:** `issue/<id>-<slug>`
- **Worktree:** path if used
- **Base:** latest `origin/development`
- **Next:** implement; Ship = checkpoint; finish = review-ready (Packager opens PR)

## Output template

```text
Agent setup ready
- Repo: <name>
- Issue: #<n>
- Branch: issue/<id>-<slug>
- Worktree: <path|same>
- Base: origin/development (fetched)
- Hard stops: no implementer PR, no merge, no self-review, no staging/main
- Next: do the work; Ship = checkpoint commit+push; finish = completion_gate review-ready
```

## Blockers

Stop and ask when:

- multi-root and target repo is ambiguous
- task description still missing after one tight question
- `create_issue_branch.py` fails (auth / API / sync) — do not invent IDs
- working tree is dirty in a way that would risk losing work and worktree creation failed

## Progressive Disclosure

Read only this skill, the helper script help text, git status/branch/remote for the target repo, and the authority docs above if needed.
