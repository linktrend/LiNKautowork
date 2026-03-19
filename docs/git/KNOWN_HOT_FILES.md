# Known Hot Files During Upstream Sync (`link-n8n`)

These files commonly conflict or require explicit LiNK policy retention.

## Governance-sensitive
- `.github/CODEOWNERS`
- `.github/workflows/*` (when fork-specific governance differs from upstream)
- `GIT_STRATEGY.md`
- `scripts/git/sync-upstream.sh`

## Resolution guidance
1. Preserve LiNK ownership and protection controls unless superseded by a deliberate governance change.
2. Keep upstream security fixes and CI hardening unless they break required LiNK policy.
3. Prefer minimal conflict edits; avoid broad rewrites in sync PRs.
4. Document every non-trivial conflict resolution in PR notes.

## Required check after conflict resolution

```bash
bash /Users/linktrend/Projects/LiNKautowork/scripts/git/verify-parity.sh --repo-path /Users/linktrend/Projects/LiNKautowork/link-n8n --branch master
```
