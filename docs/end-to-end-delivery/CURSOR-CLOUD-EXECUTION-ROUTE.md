# Cursor Cloud execution route for this delivery

Status: **ACCESS VERIFIED / SUBMIT REQUIRES APPROVE AND OWNER-SCOPE TRANSITION**

This is the sanitised, repository-hosted execution instruction for the local
coordinator and every LiNKautowork cloud worker. Workers must use the GitHub-hosted
files listed below; they do not depend on a Mac-only document, conversation memory,
secret, receipt directory or saved Cursor environment.

## 1. Verified operational transport

The established local coordinator transport is:

`/Users/linktrend/Documents/Codex/2026-09-09/files-pasted-by-the-user-i/outputs/cursor-cloud/cursor_cloud.py`

Observed SHA-256 on 2026-09-10:
`0cf61dc9b2f6b7f6c6b34ddf94a7c751229e9838d50ed9c1b468f5327e39e2e8`.

It is a standard-library REST client for `https://api.cursor.com/v1`. It retrieves
the credential from macOS Keychain service `Cursor-Codex-001`, account
`cursor-001@linktrend.one`, and holds it only in process memory. The credential is
never copied into Git, a packet, a worker prompt, a receipt or this document.

At 2026-09-10 14:17 Asia/Taipei, direct read-only GETs through this client proved:

- `/v1/me`: exact account `cursor-001@linktrend.one`;
- `/v1/models`: `grok-4.6`, effort `medium`, `fast=false` is supported;
- `/v1/repositories`: `linktrend/LiNKautowork` is visible.

This is the operational route. The repository's installed
`core/execution/cursor_cloud_dispatch.py` and managed-core policy describe
governance requirements but are not a prerequisite client for this delivery. An
absent `CURSOR_API_KEY`, absent `cursor-sdk`, or logged-out `cursor-agent` CLI does
not invalidate the verified Keychain-backed REST route.

## 2. Suspension and exact owner transition

The dispatcher currently sees:

- control root
  `/Users/linktrend/Documents/Codex/2026-09-09/files-pasted-by-the-user-i/outputs/queue-control`;
- `SUSPENDED` present;
- `RESUME-SCOPE.json` SHA-256
  `1c0883412cb8ac585c019ca2be35e6491d9f5a50c0672132389fcb12ef6c34d1`;
- schema `{"authorized_at", "target_review_at", "objective", "owners"}`, where
  `owners` maps exact coordinator task IDs to repository arrays;
- previous Server01 owner `01a0843c-0df9-74e2-907a-05c5f736d6ed`
  authorised for LiNKautowork; and
- this coordinator `01a089cb-ef0d-75a2-b87f-4f3dd8163b24` absent, so its
  `submit` is currently rejected even though API GET access succeeds.

Provider GET readback found every recorded LiNKautowork cloud writer/reviewer
terminal (`FINISHED` or `CANCELLED`). The Server01 queue still recorded non-cloud
`autowork-phase-admission-015` as running, and PR #125 plus issue #126 worktrees
remain present and clean. Do not take over, delete or rewrite that work.

The first coordinator action after founder `APPROVE` is:

1. GET-readback all prior LiNKautowork cloud receipts again and read the Server01
   queue; require no active cloud writer and a terminal/handoff state for
   `autowork-phase-admission-015`.
2. Refresh protected `development` commit/tree and reconcile only AW-01 paths or
   interfaces changed by the prior lane.
3. Preserve `SUSPENDED` and every existing owner grant. Atomically add exactly
   `"01a089cb-ef0d-75a2-b87f-4f3dd8163b24": ["linktrend/LiNKautowork"]` to the
   existing `owners` object. Do not impersonate the previous owner, broaden the
   repository list, remove suspension or enable another server.
4. Validate shape, read back the new pair, and record preimage/postimage SHA-256
   before preparing AW-01.

The coordinator performs this narrow local transition; it is not product code or
cloud-worker work. Use a same-directory temporary file, preserve mode, and
`os.replace` only after verifying the unchanged preimage digest. Rollback removes
only this coordinator's entry after a current-file digest comparison. If the file
changed, stop and reconcile with the current owner instead of overwriting it. No
policy conflict was found: the existing schema supports exact per-owner,
per-repository grants while preserving global suspension.

## 3. Coordinator commands and required packet fields

Run the dispatcher by absolute path. `check` is read-only. `validate` is offline.
`submit` creates a paid worker and is prohibited until the founder records
`APPROVE` for the final manifest digest.

```text
python3 <dispatcher> check
python3 <dispatcher> validate <packet.json>
python3 <dispatcher> submit <packet.json>
python3 <dispatcher> poll <packet_id>
python3 <dispatcher> watch <packet_id> --seconds 45
```

Every packet JSON must provide:

| Field | Required value for this delivery |
|---|---|
| `packet_id` | Stable unique ID, for example `linkautowork-aw01-<short-commit>`. Reuse it for reconciliation; never delete its receipt to force redispatch. |
| `owner` | Exact coordinator task ID `01a089cb-ef0d-75a2-b87f-4f3dd8163b24`; the implementer role is prompt content, not the admission identity. |
| `repository` | Exact `linktrend/LiNKautowork`. |
| `ref` | Precreated pushed `issue/<number>-<slug>` writer branch; never a SHA-only ref or saved environment. |
| `commit`, `tree` | Exact 40-character GitHub readback for that branch before dispatch. |
| `role` | `implementation` for AW-01 through AW-07; use `independent-review` only for the separate reviewer. Server operations in AW-08 use the governed Luna/server route, not this cloud writer. |
| `prompt` | The packet-specific instruction below plus the exact GitHub input paths. |
| `allowed_paths` | Exact owned paths from the matching manifest packet; no broader path. |
| `acceptance_commands` | Matching minimum verification commands from the manifest and work-packet document. |
| `admitted` | `true` only after the founder approval and local owner/resource checks. |
| `admission_evidence` | Reference to the final approved manifest digest and local ownership decision; never a secret value. |

The dispatcher validates the GitHub branch commit/tree before POST, sends explicit
`repos: [{url, startingRef}]`, `grok-4.6` with medium effort and Fast disabled,
`autoCreatePR=false`, and `workOnCurrentBranch=false`. It serialises cloud writers
per repository and retains four of twenty global slots for review/downstream work.

Complete non-secret AW-01 template before runtime identity substitution:

```json
{
  "packet_id": "linkautowork-aw01-<stable-short-id>",
  "owner": "01a089cb-ef0d-75a2-b87f-4f3dd8163b24",
  "repository": "linktrend/LiNKautowork",
  "ref": "issue/<number>-<slug>",
  "commit": "<40-character-pushed-branch-commit>",
  "tree": "<40-character-tree>",
  "prompt": "Execute AW-01 only. Read every GitHub-hosted input in section 5 at this exact commit. Implement AW-01 Required work only within manifest ownedPaths; run verificationCommands and report starting/final repository, ref, commit, tree, changed paths, results and HOLDs. Do not edit Platform, deploy, IDE managed core, other packets or protected branches; do not open or merge a PR.",
  "allowed_paths": [
    "supabase/migrations/",
    "docs/contracts/server01/",
    "packages/automation-contracts/tests/server01-"
  ],
  "acceptance_commands": [
    "npm --prefix packages/automation-contracts run verify:db",
    "npm --prefix packages/automation-contracts run test",
    "git diff --check"
  ],
  "role": "implementation",
  "admitted": false,
  "admission_evidence": "HOLD until APPROVE for the final manifest digest"
}
```

After approval and the owner transition, the coordinator creates the new GitHub
Issue/branch with existing `create_issue_branch.py`, pushes it, reads fresh
identities, replaces only the placeholders, changes `admitted` to `true`, and sets
`admission_evidence` to the approval reference plus manifest digest.

```text
python3 scripts/gitops/create_issue_branch.py --repo linktrend/LiNKautowork --prefer-worktree "AW-01 freeze Server01 live interfaces and migration identity package"
git push -u origin HEAD
git rev-parse HEAD^{commit}
git rev-parse HEAD^{tree}
gh api repos/linktrend/LiNKautowork/git/ref/heads/<issue-branch>
gh api repos/linktrend/LiNKautowork/git/commits/<commit>
python3 <dispatcher> validate <aw01-packet.json>
python3 <dispatcher> submit <aw01-packet.json>
```

## 4. Transport readback versus source attestation

After POST, the coordinator reads `/v1/agents/{agentId}` and validates agent ID,
cloud hosting, repository URL when returned, optional starting ref when returned,
and both no-auto-PR flags. Cursor agent GET may omit the starting branch. It does
not supply authoritative worker HEAD/tree/model fields, so those must not be
invented as transport readback.

The cloud worker must instead attest from its checkout before product work:

1. origin is exactly `https://github.com/linktrend/LiNKautowork`;
2. the supplied issue branch resolves to the packet commit/tree;
3. its checked-out starting HEAD/tree match those identities;
4. the worktree is clean except for scoped worker changes;
5. installed repository instructions and the exact GitHub inputs below were read.

Mismatch stops the packet. The worker must not substitute `main`, `development`, a
cached checkout, a saved environment or a newer branch tip.

## 5. GitHub-hosted worker inputs

Every writer receives these exact repository paths at its packet commit:

- `AGENTS.md`
- `.ide-development/VERSION`
- `.ide-development/execution/CODING-EXECUTION-PROTOCOL.md`
- `docs/end-to-end-delivery/README.md`
- `docs/end-to-end-delivery/LINKAUTOWORK-SERVER01-DELIVERY-PLAN.md`
- `docs/end-to-end-delivery/WORK-PACKETS.md`
- `docs/end-to-end-delivery/EXECUTION-MANIFEST.json`
- `docs/end-to-end-delivery/READINESS-REPORT.md`
- this file, `docs/end-to-end-delivery/CURSOR-CLOUD-EXECUTION-ROUTE.md`

The packet prompt identifies its AW packet and instructs the worker to implement
only that packet's `Required work`, within its manifest `ownedPaths`, using its
declared `Authority/inputs`, and to run its `Minimum validation`. The worker must
report changed paths, command results, unresolved HOLDs, and starting/final
repository/ref/commit/tree. It may not open a PR, self-review, merge, deploy,
change credentials, mutate another repository, or add an unspecified Program
automation.

AW-01 is the first executable content packet. Its inputs are the protected
LiNKautowork baseline, the protected Platform revision and the exact contracts
named in `WORK-PACKETS.md`. PR #125/#126 are reconciled only if they change an
AW-01-owned path or settled interface before the issue branch is created.

The dispatcher binds exactly one repository. AW-01 receives no second repository.
Section 5.1 of `LINKAUTOWORK-SERVER01-DELIVERY-PLAN.md` is the permitted versioned,
non-secret Platform contract handoff and pins its upstream commit/tree. The worker
must not read Platform's local checkout or copy its implementation. Later packet
inputs, contracts and fixtures must first be committed and pushed by their accepted
predecessor; each new packet pins that GitHub commit/tree. No worker is dispatched
against an input that exists only on the Mac or in task history.

## 6. Cloud runtime, permissions and dependency bootstrap

Protected CI uses `ubuntu-24.04-arm`, Node.js `22`, and `npm ci` against committed
`package-lock.json`. Production Node images are pinned to
`node:22.13.1-alpine`. No Git submodule is configured and the lockfile uses the
public npm registry; no private package token is an initial source prerequisite.

After approval, the disposable cloud worker reports OS/architecture, selects Node
22 explicitly (`nvm install 22` then `nvm use 22` where nvm is present), runs
`npm ci`, and then only the packet's focused commands. A stale cached dependency
tree is not proof. Python 3 is required only by repository governance scripts; the
local dispatcher uses coordinator system Python standard library plus `gh`. No
production credentials or data enter the cloud VM.

Current Keychain retrieval and API GETs completed without an interactive prompt.
Enforced permissions are issue-branch Git access, network access to GitHub/Cursor/
public npm, `autoCreatePR=false`, and no protected-branch, check-publication,
issue-creation, merge or deployment authority. The local coordinator performs
privileged GitHub actions through repository tooling. An implementation worker may
edit/commit/push only `allowed_paths`; its prompt prohibits nested workers and
production access. These controls, not a UI label, define unattended feasibility.

## 7. Result retrieval and repository handoff

`poll` reads `/v1/agents/{agentId}` and then
`/v1/agents/{agentId}/runs/{latestRunId}`. `watch` performs the same read with a
bounded wait. A terminal Cursor result is evidence to inspect, not acceptance.

The local orchestrator verifies the pushed branch commit/tree, scoped diff and
focused results, then uses `scripts/gitops/completion_gate.py` for the exact Issue
checkpoint. A separate provider-neutral reviewer evaluates that exact identity.
The Phase Packager/Coordinator opens the draft Phase PR; the delivery controller
performs protected integration when all gates pass. Implementers never create or
merge their own PRs.

## 8. Fallback and live work

The registered fallback is Codex CLI `gpt-5.6-luna`, effort high, Fast off. It is
used only after an explicit founder instruction; it is not an automatic response
to a Cursor failure. Privileged Server01 work in AW-08 follows the governed Luna/
server route. Neither route changes the product scope or authorises implementation
before `APPROVE`.
