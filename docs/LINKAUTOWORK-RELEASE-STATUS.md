# LiNKautowork 1.0 — current release status

Checked: 2026-10-02. This file records live source-control and gate evidence;
it does not certify a production deployment.

## Repository identity

Repository: `linktrend/LiNKautowork` (`https://github.com/linktrend/LiNKautowork`).
The three protected branches have different commit IDs but the same tree:

| Branch | Commit | Tree |
|---|---|---|
| `development` | `c1eb2ae130bda7e0a55f133c60701e6fdff0ce88` | `63fe42dcd0ad8275431726ad5d09ed0f7b6db074` |
| `staging` | `c733aebe4aa0e08438cc5c7d7cc68cd7524d4748` | `63fe42dcd0ad8275431726ad5d09ed0f7b6db074` |
| `main` | `a013cbe727d3c13bc1f8b88283602c4fcfa23396` | `63fe42dcd0ad8275431726ad5d09ed0f7b6db074` |

Local branch refs were checked against the corresponding origin refs and were
at those same commits. The local checkout was clean. “Same” here means the
contents/tree are identical; promotion commits differ because they have
different parent histories.

## Release gates

- PR #219 is merged to `main`; its `Linktrend Receipt Gate` failed. The branch
  source policy passed. The three CodeQL analyses on the merge commit passed,
  but they do not replace the receipt gate.
- Ruleset `main-autonomous-release` (`20623014`) is active. Its bypass list is
  empty, and its required checks remain `Linktrend Receipt Gate` and
  `Linktrend Branch Source Policy`.
- The full LiNKautowork CI receipt has not been accepted for the current main
  tree. Do not treat historical green CI as proof for this tree.
- Existing `v1.0.0`–`v1.0.3` tags point to older trees. No current `LiNKautowork
  1.0` release tag has been created. Do not move or reuse a stale tag.
- Consequently the current source is **not release-ready for deployment**.
  A fresh exact-tree receipt must pass the protected gate before the founder /
  controller creates the annotated 1.0 tag.

## Deployment state

Server01 deployment remains **HOLD**. This repository status does not prove
that live database permissions, secrets, host images, backup/isolated restore,
network boundaries, inactive import, canary behavior, or rollback have passed.
LiNKplatform owns production migration and restore evidence. Do not apply
production SQL, change credentials, or start the stack based on this document.

The separate Server01 owner may proceed only from the exact accepted tag on
`main`, with fresh hosted receipts, current Platform acceptance, and the
founder's release approval. Record host-only evidence outside this source
packet as directed by the deployment runbooks.

## Branch and workspace cleanup

The verified local LiNKautowork checkout has only `development`, `staging`,
and `main` branches and no extra worktrees. Remote stale branch
`issue/215-add-read-only-provider-connection-health-canary` was deleted after
confirming its PR was closed and its tree had no unique content. Old `v1.0.x`
tags were retained because tags are release records and must not be rewritten.

This record covers only the LiNKautowork checkout and refs listed above. It
does not claim to clean unrelated IDE worktrees or other repositories.
