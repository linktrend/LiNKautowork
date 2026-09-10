# Cursor Cloud execution route for this delivery

Status: **READ-ONLY ACCESS VERIFIED / DISPATCH REQUIRES APPROVE**

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

## 2. Coordinator commands and required packet fields

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
| `owner` | LiNKautowork packet owner named in `WORK-PACKETS.md`. |
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

## 3. Transport readback versus source attestation

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

## 4. GitHub-hosted worker inputs

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

## 5. Result retrieval and repository handoff

`poll` reads `/v1/agents/{agentId}` and then
`/v1/agents/{agentId}/runs/{latestRunId}`. `watch` performs the same read with a
bounded wait. A terminal Cursor result is evidence to inspect, not acceptance.

The local orchestrator verifies the pushed branch commit/tree, scoped diff and
focused results, then uses `scripts/gitops/completion_gate.py` for the exact Issue
checkpoint. A separate provider-neutral reviewer evaluates that exact identity.
The Phase Packager/Coordinator opens the draft Phase PR; the delivery controller
performs protected integration when all gates pass. Implementers never create or
merge their own PRs.

## 6. Fallback and live work

The registered fallback is Codex CLI `gpt-5.6-luna`, effort high, Fast off. It is
used only after an explicit founder instruction; it is not an automatic response
to a Cursor failure. Privileged Server01 work in AW-08 follows the governed Luna/
server route. Neither route changes the product scope or authorises implementation
before `APPROVE`.
