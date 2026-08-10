---
name: git-safeguard
description: Apply repository safety checks before staging, committing, pushing, or publishing branches.
version: 1.0.0
status: active
tags: [git, safety, release, repository]
source_adapted_from:
  - LiNKskills/skills/git-safeguard
---

# Git Safeguard

Use this skill before any git operation that changes shared repository state.

## Use When

- staging files
- committing changes
- pushing a branch
- resolving merge conflicts
- preparing a release or pull request

## Safety Checklist

1. Run `git status`.
2. Identify files changed by the current task.
3. Separate unrelated user changes from agent-made changes.
4. Review the diff for every file to be staged.
5. Confirm no secrets, local credentials, generated junk, or disposable test artifacts are included.
6. Confirm branch name and remote target before push.
7. Confirm tests or verification evidence are recorded when work changes behavior.

## Rules

- Never stage unrelated user changes without explicit instruction.
- Never use destructive git commands unless explicitly requested.
- Never push without knowing the current branch and remote.
- Prefer narrow staging over broad `git add .`.
- Preserve compatibility files unless the task explicitly removes them.
- Record any skipped test or verification gap before declaring work ready.

## Blockers

Stop and ask or report blocked when:

- repository state is ambiguous
- merge conflicts affect task files
- changed files include secrets or credentials
- unrelated user changes cannot be separated safely
- a push target is unclear

## Output

- intended staged files
- safety checks performed
- verification status
- blockers or residual risk

## Progressive Disclosure

Read only repository state, changed files, and task-relevant artifacts. Do not inspect unrelated history unless needed to resolve a conflict or ownership question.
