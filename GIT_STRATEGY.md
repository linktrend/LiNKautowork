# LiNKautowork Git Strategy

## Scope and authority
- Root repository: `LiNKautowork` (this folder)
- Upstream fork boundary: `link-n8n/`
- Root `origin` (source of truth): `https://github.com/linktrend/LiNKautowork.git`
- `link-n8n` origin (fork source of truth): `https://github.com/linktrend/link-n8n.git`
- `link-n8n` upstream (read-only): `https://github.com/n8n-io/n8n.git`

## Topology decision
`link-n8n` is managed as an **independent nested repository** (not submodule, not subtree).

Reasoning:
1. Preserves the fork’s native branch protection and PR policy directly on `linktrend/link-n8n`.
2. Avoids accidental superproject pointer-only updates that can hide real fork changes.
3. Keeps upstream sync operations explicit and auditable in the actual fork repository.
4. Allows LiNKautowork governance scripts/docs to evolve without touching n8n runtime history.

Implementation rule:
- Root repo ignores `link-n8n/` in `.gitignore`.
- All fork sync operations run against the nested repo path via governance scripts.

## Non-negotiable controls
1. Never push directly to protected `origin/master` on `link-n8n`.
2. Always create sync branches (`sync/upstream-YYMMDD`) and merge via PR.
3. Keep `upstream` push hard-blocked (`no_push`).
4. Require commit-signing prerequisites before sync branch generation.

## Core command set
Run from root:

```bash
# 1) Signing + hygiene preflight
bash scripts/git/check-signing-prereqs.sh --repo-path link-n8n
bash scripts/git/branch-hygiene.sh --repo-path link-n8n

# 2) Create and push upstream sync branch + PR
bash scripts/git/upstream-sync-pr.sh --repo-path link-n8n --base-branch master --upstream-branch master

# 3) After PR merge, clean branches and verify parity
bash scripts/git/post-merge-cleanup.sh --repo-path link-n8n --delete-remote --apply
bash scripts/git/verify-parity.sh --repo-path link-n8n --branch master
```

## Branch naming standard
Allowed branch patterns:
- `sync/upstream-YYMMDD`
- `feat/*`
- `fix/*`
- `chore/*`
- `docs/*`
- `ops/*`
- `codex/*`
- `hotfix/*`

Validation command:

```bash
bash scripts/git/check-branch-name.sh sync/upstream-260319
```

## Source-of-truth verification
- Root meta repo parity:

```bash
git fetch origin --prune
git rev-parse main
git rev-parse origin/main
```

- `link-n8n` parity:

```bash
bash scripts/git/verify-parity.sh --repo-path link-n8n --branch master
```
