# Agent Completion Contract

**Status:** Active
**Date:** 2026-08-01
**Owner:** IDE Development (GitOps)

## Purpose

Define how Implementers finish a work session without opening PRs or falsely claiming review-ready.

## Authority

`review-ready` is the authoritative, fail-closed completion path. The gate validates the exact pushed branch state and machine-readable evidence before **`Linktrend Review Ready`** may be published.

**Production publisher:** only the GitHub App, from the trusted App-backed publisher workflow on the protected default branch (`linktrend-review-ready-publisher.yml`). Local `completion_gate.py review-ready` remains the implementer entrypoint: it validates first, then either publishes when a privileged App token is already present in a trusted context, or **fails closed** and explains the App-backed dispatch route when local privileged credentials are unavailable. It must never substitute Carlos's user token, ambient `GITHUB_TOKEN`, or any other human credential to publish the status.

Bare `--tests-ok`, `COMPLETION_TESTS_OK=1`, and arbitrary text in `COMPLETION_EVIDENCE` are not sufficient production proof.

There is **no** `.linktrend/review-ready.json` readiness file and no readiness marker commit in the feature diff. Do not create, discover, or consult that path.

## Modes (`scripts/gitops/completion_gate.py`)

| Mode | Meaning | Exit |
|---|---|---|
| `checkpoint` | Commit+push save; work unfinished | `0` ok |
| `review-ready` | Validate finished work, then publish **`Linktrend Review Ready`** (or fail closed with App-backed route diagnostics) | `0` ok, `78` incomplete, `1` failed |
| `blocked` | Write durable blocker JSON | `2` blocked |
| `status` | Report current completion state | `0` ok |
| `write-evidence` | Write schema-versioned completion evidence for current `HEAD` | `0` ok |

Exit codes: `0` ok, `78` incomplete, `2` blocked, `1` failed.

## States

- `checkpointed_unfinished`
- `review_ready`
- `blocked`
- `failed`

## `review_ready` requirements (all required)

Order is part of the contract:

1. Verify exact pushed SHA and branch state:
   - `HEAD` resolves to a SHA.
   - working tree is clean.
   - branch is not `development`, `staging`, `main`, or detached.
   - **App-backed publication requires** verified `issue/<number>-<slug>` (digits + lowercase slug) **or** a configured Phase tip matching `phaseBranchPrefix` + lowercase slug (default `phase/<slug>`). Ordinary allowlist prefixes (`feature/`, `dev/`, `cursor/`, …) may still exist for work/Pull, but `review-ready` on the production GitHub backend fails closed with an actionable migration path — it must never advertise a doomed `gh workflow run … -f branch=feature/…` command. Phase eligibility does not weaken issue-branch slug safeguards.
   - `HEAD == origin/<branch>` after fetch.
2. Require machine-readable evidence JSON tied to that exact `HEAD` SHA.
3. Only after those checks pass, publish **`Linktrend Review Ready`** through the privileged App path (`scripts/gitops/readiness_status.py` only with App automation token, or via the App-backed publisher workflow). Never publish with a user PAT / restricted Carlos identity / ordinary `GITHUB_TOKEN` fallback.

The successful status is an output of completion, not an input prerequisite.

## App-backed route (when local publish cannot proceed)

When `completion_gate.py review-ready` validates successfully but cannot publish because no privileged App token is available locally (normal implementer machine):

1. Leave evidence on the pushed tip (do not invent a readiness file).
2. Dispatch **`linktrend-review-ready-publisher`** (`workflow_dispatch`) from the **protected default branch** workflow source.
3. Bind only this repository's exact `issue/<number>-<slug>` **or** configured `phase/<slug>` branch and immutable tip SHA (plus any inputs the workflow schema requires). Dry-run when testing.
4. The workflow re-validates branch naming, exact remote SHA, evidence schema, clean/pushed tip, and (for Issue tips) issue/branch relationship from trusted scripts; the untrusted branch supplies data only.
5. On success it posts commit status context **`Linktrend Review Ready`** = `success` on that exact SHA so Review Packager discovery is unchanged.

If the current branch is still a legacy allowed name (`feature/`, `dev/`, …) rather than `issue/<number>-<slug>` or a configured Phase tip, the gate **does not** emit an App dispatch command. It fails truthfully with `app_publish_requires_issue_branch` and a remediation path: migrate via `python3 scripts/gitops/create_issue_branch.py` or `/agentcomply`, move the tip, push, rewrite evidence for the new HEAD SHA, then re-run `review-ready`.

See `core/github/REVIEW-READY.md` for the dispatch contract and rollback (withdraw is App-backed `action=withdraw` on the same trusted publisher workflow; local `clear-review-ready.sh` fails closed without App credentials).

## Evidence schema (`schemaVersion: 1`)

Completion evidence must be JSON and must be tied to the exact `HEAD` being marked:

```json
{
  "schemaVersion": 1,
  "headSha": "<exact HEAD SHA>",
  "classification": "tests",
  "acceptance": "Acceptance criteria summary",
  "commands": [
    {
      "cmd": "scripts/tests/test-gitops-lifecycle.sh",
      "exitCode": 0,
      "evidencePath": ".linktrend/test-gitops-lifecycle.out"
    }
  ]
}
```

Allowed `classification` values:

- `tests`: normal implementation proof. Every command must have `exitCode: 0`.
- `docs_only`: documentation-only proof. It still records validation commands and must include `docsOnlyJustification` with at least 20 characters.

## Hard rules

- Implementers **never** open or update PRs. Review Packager opens PRs.
- Ship waves = checkpoint only (no Bugbot, no review-ready unless truly finished).
- Incomplete review-ready claims must fail closed (exit `78`), not soft-succeed.
- Agents call `python3 scripts/gitops/completion_gate.py review-ready` directly, or call `write-evidence` first and then `review-ready`.
- `scripts/mark-review-ready.sh` is only a compatibility wrapper. It requires an evidence file and delegates to the gate. It must never be used as a pre-gate publisher.
- Do **not** create or use `.linktrend/review-ready.json`.
- Carlos's restricted user identity must not publish statuses (its Packager/Bugbot scope is unchanged).

## Automatic completion behavior for agents

When an issue appears complete:

1. Run the appropriate tests/checks for the touched surface.
2. Repair ordinary failures automatically, with at most **3** bounded repair cycles.
3. Write machine-readable evidence with `completion_gate.py write-evidence` or an equivalent schema-versioned JSON file under `.linktrend/`.
4. Call `python3 scripts/gitops/completion_gate.py review-ready` only after validation succeeds.
5. If the gate fails closed for missing privileged publish credentials, follow the App-backed route diagnostics (dispatch the publisher for this repo/branch/SHA). Do not invent a local status publish with a user token.
6. If validation or repair cannot complete, leave the branch ineligible and write a durable blocker:

```bash
python3 scripts/gitops/completion_gate.py blocked \
  --reason "why completion is blocked" \
  --attempted-repairs 3
```

## Related

System repository paths:

- `docs/AUTONOMOUS-GIT-OPERATIONS.md`
- `core/github/REVIEW-READY.md`
- `docs/contracts/GITHUB-APP-GITOPS-CREDENTIALS.md`
- `docs/contracts/REPAIR-DISPATCHER.md`
- `docs/archive/work-packets/2026-08-01-wave-2-app-backed-completion.md` (stub remains at historical `docs/work-packets/` path)

Consumer installs (packaged doctrine under `.ide-development/content/doctrine/`): use sibling `AUTONOMOUS-GIT-OPERATIONS.md` in the same directory. Root `docs/` and `core/github/` paths above are system-source contracts and are not assumed present at those locations in every consumer.

## Blocked completion (local cache + durable record)

`completion_gate.py blocked` writes `.linktrend/completion-blocker.json` under the workdir.
`.linktrend/` is **gitignored**, so that file is only a **machine-local cache** — it is not by itself a durable cross-machine blocker.

The same `blocked` mode resolves the current repository from the checkout (`gh repo view` or validated `origin`, never `upstream`-only / ambiguous forks) and upserts a durable **repair task** (`immediate_approval_required`) via `repair_task.py` when authenticated access exists.

If repository resolution or durable write fails, the command still exits `2` with `durableRecord=false` and `warning=LOCAL_CACHE_ONLY...`. Agents must **not** claim the blocker was durably registered on GitHub in that case.

Do not force-add or commit `.linktrend/`.
