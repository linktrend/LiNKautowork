# Branch Protection Compatibility

This document maps automation behavior to protected-branch constraints on `linktrend/link-n8n:master`.

## Current protected-branch assumptions
Validation command:

```bash
bash scripts/git/validate-branch-protection.sh --repo linktrend/link-n8n --branch master
```

Expected controls:
1. Signed commits required.
2. PR reviews required.
3. Code owner reviews required.
4. Conversation resolution required.
5. Force push disabled.
6. Branch deletion disabled.

## Why direct push is forbidden
`upstream-sync-pr.sh` intentionally never pushes to protected branch. It only:
1. creates a sync branch,
2. pushes the sync branch,
3. opens a PR.

This guarantees compatibility with PR-required branch protection.

## Signed-commit compatibility
Local requirement:

```bash
bash scripts/git/check-signing-prereqs.sh --repo-path link-n8n
```

If signing is not ready, sync is blocked before branch creation.

CI/bot strategy:
1. Use a dedicated bot token with least required scopes.
2. Configure bot commit signing (GPG or SSH signing) in the runner.
3. If bot signing is not yet configured, run in check-only mode and require human-signed sync.

## Branch naming compatibility
Enforced naming policy:

```bash
bash scripts/git/check-branch-name.sh sync/upstream-260319
```

This keeps automation-generated branches predictable for review and cleanup tooling.

## Failure modes and operator actions
1. `required_signatures` violation:
- Reconfigure signing keys, rerun signing precheck, recreate sync branch.

2. PR merge blocked by review policy:
- Request required approvals/code owner review, do not bypass by direct push.

3. Unexpected long-lived branches:
- Run cleanup tool and keep only approved long-lived branches.

```bash
bash scripts/git/post-merge-cleanup.sh --repo-path link-n8n --delete-remote --apply
```
