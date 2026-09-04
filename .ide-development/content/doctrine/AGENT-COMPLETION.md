# Agent Completion Contract

**Status:** Active. Amended `V25_BOOTSTRAP_LEAN` 2026-08-20.
**Date:** 2026-08-01
**Owner:** IDE Development (GitOps)

## Purpose

Define how Implementers finish a work session without opening PRs or claiming hosted/production proof they do not have.

## Authority (`V25_BOOTSTRAP_LEAN`)

A v2.5 **Issue checkpoint** is accepted when all of the following are present:

1. exact pushed commit and tree
2. scoped diff
3. focused tests
4. one provider-independent narrow review bound to the exact commit and tree
5. manifest evidence

Review Ready publication, `AUTOMATION_TOKEN`, an Issue PR, hosted completion status, and legacy publisher status are **nonrequirements**. They must not block checkpoint acceptance.

`python3 scripts/gitops/completion_gate.py checkpoint` is the implementer entrypoint. `review-ready` remains a compatibility mode that **never publishes** and classifies the legacy publisher as **`WAIVED_LEGACY_GATE`** (never PASS, never an implementation failure). That waived outcome must never bypass substantive proof, security, exact identity, scope, review, or rollback.

There is **no** `.linktrend/review-ready.json` readiness file. Do not create, discover, or consult that path. Local proof must never be represented as hosted or production proof. When hosted validation needs out-of-tree evidence, pass an explicit immutable evidence payload (`--evidence-json`) bound to the exact SHA/tree.

## Modes (`scripts/gitops/completion_gate.py`)

| Mode | Meaning | Exit |
|---|---|---|
| `checkpoint` | Save point, or v2.5 Issue-checkpoint acceptance when lean evidence is present | `0` ok, `78` incomplete |
| `review-ready` | Validate evidence, then waive legacy Review Ready publication (`WAIVED_LEGACY_GATE`, never PASS) | `0` waived, `78` incomplete |
| `blocked` | Write durable blocker JSON | `2` blocked |
| `status` | Report current completion state | `0` ok |
| `write-evidence` | Write schema-versioned completion / lean checkpoint evidence for current `HEAD` | `0` ok |

Without an explicit `--evidence-file` or `COMPLETION_EVIDENCE_FILE`, evidence is
written under the repository git-common-dir, keyed by branch and exact `HEAD`.
It is never written into the tracked candidate tree. Explicit legacy evidence
paths remain readable for compatibility, but new checkpoints must not create
self-referential `.linktrend/completion-evidence.json` changes.

Exit codes: `0` ok, `78` incomplete, `2` blocked, `1` failed.

## States

- `checkpointed_unfinished`
- `checkpoint_accepted`
- `waived_legacy_gate`
- `blocked`
- `failed`

## v2.5 Issue checkpoint requirements

1. `HEAD` resolves to a SHA and matching git tree.
2. Working tree is clean; branch is not `development`, `staging`, `main`, or detached.
3. `HEAD == origin/<branch>` after fetch (exact pushed identity).
4. Machine-readable evidence bound to that exact SHA/tree covering scoped diff, focused tests, one provider-independent narrow review, and manifest evidence.
5. No GitHub token, Review Ready status, Issue PR, or hosted completion status is required.

Bare `--tests-ok`, `COMPLETION_TESTS_OK=1`, and arbitrary text in `COMPLETION_EVIDENCE` are not sufficient.

## Phase delivery (not Issue checkpoint)

One Phase PR into `development`, exact review, conditional Full, and the founder gate for `main` remain the protected delivery path. The delivery controller merges through GitHub protection. Administrator recovery is a named exception after replacement proof: freeze the exact Phase head, snapshot protections, prefer `gh pr merge --admin --match-head-commit`, apply a minimum temporary exception only if needed, merge only that exact authorized head, restore immediately, read back, and record obsolete publisher/status as waived not passed.

## Hard rules

- Implementers **never** open or update PRs. The Phase Packager/Coordinator (`scripts/gitops/packager_coordinator.py`) opens the Phase PR. Retained `packager_discover.py` is not that component.
- Ship waves = checkpoint only.
- Do **not** attempt the Review Ready publisher or a hosted publisher fallback from implementer sessions.
- Do **not** create or use `.linktrend/review-ready.json`.
- Never represent local proof as hosted/production proof.

## Related

- `docs/AUTONOMOUS-GIT-OPERATIONS.md`
- `core/execution/CODING-EXECUTION-PROTOCOL.md`
- `core/contracts/EXECUTION-CONTROL-CONTRACT.md`
- `scripts/gitops/issue_checkpoint.py`
- `scripts/gitops/administrator_recovery.py`
