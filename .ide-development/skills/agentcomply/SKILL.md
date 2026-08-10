---
name: agentcomply
description: >-
  Migrate an ALREADY-OPEN agent from wrong or long-lived branches onto a proper
  short-lived issue/* (or cleanup) branch for the repo being touched, safely
  moving dirty work. Use when Carlos runs /agentcomply or asks to comply with
  studio branching rules.
version: 1.3.0
status: active
tags: [git, agent, migration, compliance, branching, ship-pull]
related_commands:
  - agentcomply
related_skills:
  - agentsetup
  - git-safeguard
---

# Agent Comply (ALREADY-OPEN session)

Migrate an **already-open agent** onto a proper short-lived `issue/*` branch for the **repo being touched**. Prefer this over starting fresh when there is uncommitted or wrong-branch work to preserve.

## Authority

- `.cursor/rules/01-git-branching.mdc`
- `.cursor/rules/02-autonomous-ship-pull.mdc`
- `docs/AUTONOMOUS-GIT-OPERATIONS.md`
- Pair with `git-safeguard` before any commit or push

## House rules (locked)

- **`/agentcomply` is primarily for Implementers** that own work in **one repo**.
- **Orchestrator (workspace-wide coordination):** do **not** invent or steal a forever “session home” `issue/*` branch. If the session is only coordinating (no repo edits), stop — no branch required. If it has accidental dirty edits, hand off to that repo’s Implementer + `/agentcomply` there, or open a **correctly named** `issue/<id>-slug` for that specific change — never adopt an unrelated open PR (e.g. Lisa doctrine) as this chat’s identity.
- **No code/repo touch → no branch required.** Coordination-only sessions that do not edit a repo do not need `/agentcomply`.
- **Touch a repo → comply for that repo.** Any agent that edits a repo (including an orchestrator that starts coding) runs `/agentcomply` or `/agentsetup` for **that** repo and uses `issue/<id>-slug` for the work package.
- One short-lived `issue/<id>-slug` per piece of governed work — no forever `dev/*` home.
- Branch must match **this work package**. Do not silently adopt an unrelated open PR branch just because it exists.
- Multi-root: if which repo is being touched is ambiguous, ask (normal ambiguity ask). Detect or ask once if role is Orchestrator vs Implementer when unclear.
- `cursor/*` for cloud; `dev/*` rare ad-hoc only.
- Never dump work onto `development` / `staging` / `main`.
- Never merge own PR; never self-review; Bugbot reviews; Integrator merges.

## Use When

- Carlos invokes `/agentcomply`
- Session is on `dev/*`, `development`, detached, stale, or otherwise non-compliant **and** this session is touching (or about to touch) a repo
- Dirty files or commits need to move onto a proper `issue/*` branch

## Scope Out

- Brand-new clean bootstrap → `agentsetup`
- Sessions that will not touch any repo (no branch work needed)
- Lisa Option A clock, doctrine rewrites, Integrator/Promoter landing
- Force-push, hard reset, or rewriting shared history unless Carlos explicitly authorizes

## Inputs (ask only if needed)

1. **Task description** if missing (helper creates/reuses the GitHub issue — do not ask Carlos for id/slug)
2. Or allow **`issue/cleanup-<topic>`** only when a cleanup branch is explicitly appropriate and no issue should be filed
3. **Target repo** if multi-root / ambiguous
4. Whether to **commit/push a checkpoint** and/or **mark review-ready** (ask if commit message or readiness is ambiguous). Do not open a PR yourself — Review Packager does that. Prefer `scripts/gitops/completion_gate.py`.

## Workflow

### 0. Role / touch gate (do this first)

If this looks like a **workspace Orchestrator** (multi-root coordinator; UI title/role says Orchestrator) and it is **not** about to edit a specific repo:

1. Do **not** create/checkout/claim an `issue/*` as session home.
2. Optionally report a brief multi-repo status.
3. Tell Carlos: orchestrators don’t get a forever session-home issue branch; implementer work happens in per-repo agents (or this orchestrator may spawn/direct those).
4. If accidental dirty edits exist in a repo: hand off to that repo’s Implementer + `/agentcomply` there, or open a correctly named issue for that change.
5. Stop (Orchestrator output below).

If the session **will touch a repo**, continue as Implementer for **that** repo only.

### 1. Inspect current state

In the target repo, gather:

```bash
git status --short --branch
git branch --show-current
git remote -v
git stash list
```

Note: current branch, dirty files, unpushed commits, whether HEAD is `development`/`staging`/`main`/`dev/*`/`cursor/*`/`issue/*`.

### 2. Resolve branch name

Prefer:

```bash
python3 scripts/gitops/create_issue_branch.py "<task description>" [--prefer-worktree]
```

Use returned `BRANCH` / `WORKTREE`. Else `issue/cleanup-<topic>` only when cleanup is explicit.
Never invent local issue IDs. Never adopt an unrelated open branch just because it exists.

### 3. Park dirty work safely

Never checkout shared branches with uncommitted governed work in a way that could land it there.

Preferred pattern when dirty:

```bash
git stash push -u -m "agentcomply: park before issue branch"
git fetch origin
git checkout development
git pull --ff-only origin development
git checkout -b issue/<id>-<slug>   # or issue/cleanup-<topic>
git stash pop
```

If already on a usable `issue/*` that matches this work package, skip recreate; still confirm base is recent `development` (merge/rebase per repo rule — default merge from `origin/development` on Pull waves).

If stash pop conflicts: stop, report conflicted paths, help resolve — do not abort onto `development`.

### 4. Commits (ask when ambiguous)

- **Do not commit secrets** (`.env`, credentials, tokens). Use `git-safeguard`.
- Commit **only** if Carlos wants it, or staged work is clearly ready with an unambiguous conventional message.
- If message/content is ambiguous: ask once, then proceed.
- Do not commit unrelated pre-existing dirty files without Carlos confirmation.

### 5. Checkpoint push (no PR)

Prefer this order:

1. Get onto the correct `issue/*` (or cleanup) branch.
2. **Push** the branch (`git push -u origin HEAD`) as a **checkpoint** once there is at least one commit to share, or Carlos asks to publish the branch tip.
3. If the issue is **finished**: mark review-ready (`scripts/mark-review-ready.sh` / completion gate). Do **not** open a PR — the **Review Packager** opens the PR.
4. If work is unfinished: leave the checkpoint on the issue branch; state clearly that no PR was opened and review-ready was not claimed.

Never open a PR yourself. Never open a PR from `development`/`staging`/`main`. Never merge.

### 6. Session contract

Tell the session explicitly:

- Work branch for this package is now `issue/…` (name it).
- Do not return to forever `dev/*` as home for this work.
- Hard stops: no self-merge, no self-review, no staging/main.

### 7. Report

Plain English summary of exactly what was done:

- previous branch → new branch
- stash/move outcome
- commits created (yes/no + message)
- checkpoint push (yes/no)
- review-ready (yes / no — Packager opens PR when ready)
- remaining dirty files, if any
- next step for this session

## Output template

```text
Agent comply done
- Role: Implementer (repo touch)
- Repo: <name>
- Was: <old-branch> (dirty: yes/no)
- Now: issue/<id>-<slug>   # branch for this work package
- Moved: stash pop / cherry-pick / already clean
- Commit: <none | conventional message>
- Checkpoint push: <yes | no>
- Review-ready: <yes | no — unfinished / Packager opens PR>
- Hard stops: no implementer PR, no merge, no self-review, no staging/main
- Reminder: work package lives on issue/… — not forever dev/*
```

## Output template (Orchestrator — no rehome)

```text
Agent comply — Orchestrator (no rehome)
- Role: Orchestrator (workspace-wide)
- Session home issue branch: none (by design)
- Multi-repo snapshot: <brief or “coordination only / clean”>
- Action: do not associate this chat with an unrelated issue/* branch
- If dirty edits exist: hand off to that repo’s Implementer + /agentcomply there,
  or open a correctly named issue/* for that specific change
- Next: keep coordinating; spawn/direct per-repo Implementers for coding
```

## Blockers

Stop and ask when:

- role is ambiguous (Orchestrator vs Implementer) after one question
- multi-root and target repo is ambiguous
- moving work would require destructive history rewrite
- secrets appear in the dirty set
- stash pop / rebase conflicts cannot be resolved safely
- Carlos has not confirmed commit when the diff is mixed or unclear

## Progressive Disclosure

Read only this skill, `git-safeguard` when committing/pushing, live git state for the target repo, and the authority docs above if needed.
