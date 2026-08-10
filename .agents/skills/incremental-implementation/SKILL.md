---
name: incremental-implementation
description: Implement changes in small verified slices instead of large unreviewable batches.
version: 1.0.0
status: active
tags: [implementation, slices, verification, scope]
source_adapted_from:
  - addyosmani/agent-skills/skills/incremental-implementation
---

# Incremental Implementation

Use this skill when implementing a change that is larger than one trivial edit.

## Use When

- a change touches multiple files
- a feature has several behaviors
- refactoring could affect working code
- the task feels too large to prove in one step

## Slice Cycle

For each slice:

1. Choose the smallest coherent behavior or structural change.
2. Implement only that slice.
3. Run focused verification.
4. Record evidence.
5. Reassess the next slice from current state.

## Slicing Rules

- Prefer vertical slices that produce working behavior.
- Keep each slice independently testable.
- Avoid speculative abstractions.
- Do not mix cleanup with behavior unless required.
- Stop if a slice reveals the plan is wrong.

## Proof Expectations

Each slice should leave evidence:

- test command and result
- build or lint result
- manual verification note
- changed artifact reference
- known remaining work

## Completion

The issue is not `done` when slices are implemented. It is `done` only after the final proof, passing review, and integration.

## Progressive Disclosure

Read the active issue and current slice context. Do not load future unrelated slices until the current slice is verified.
