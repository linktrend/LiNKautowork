# Upstream Sync Runbook (`link-n8n`)

This runbook performs upstream sync **only through PR flow** to protect `master`.

## Preconditions
1. Working tree clean in `link-n8n`.
2. Signed-commit prerequisites configured locally.
3. `origin` and `upstream` remotes present in `link-n8n`.
4. `upstream` push URL must be `no_push`.

## Normal upstream sync (one command sequence)
Run from `/Users/linktrend/Projects/LiNKautowork`:

```bash
bash scripts/git/check-signing-prereqs.sh --repo-path link-n8n
bash scripts/git/branch-hygiene.sh --repo-path link-n8n
bash scripts/git/upstream-sync-pr.sh --repo-path link-n8n --base-branch master --upstream-branch master
```

Result:
1. Fetches `origin` + `upstream`.
2. Creates `sync/upstream-YYMMDD` (or `-HHMM` if needed).
3. Merges `upstream/master` into sync branch.
4. Pushes sync branch to origin.
5. Opens PR to `master`.

## Conflict resolution (preserve LiNK behavior)
If merge conflicts occur, use:
- `/Users/linktrend/Projects/LiNKautowork/docs/git/KNOWN_HOT_FILES.md`
- `/Users/linktrend/Projects/LiNKautowork/BRANCH_PROTECTION_COMPATIBILITY.md`

Manual sequence:

```bash
cd /Users/linktrend/Projects/LiNKautowork/link-n8n
git status
# resolve files
git add <resolved files>
git commit -S -m "chore(sync): resolve upstream conflicts preserving LiNK customizations"
git push -u origin <sync-branch>
gh pr create --repo linktrend/link-n8n --base master --head <sync-branch> --title "chore(sync): upstream merge"
```

Resolution policy:
1. Keep security/governance guardrails from LiNK custom files.
2. Keep upstream fixes unless they break documented LiNK behavior.
3. Do not silently drop upstream security patches.
4. If uncertain, stop and escalate with diff notes in PR.

## Merge policy
1. Merge via PR only.
2. Respect branch protection on `linktrend/link-n8n:master`.
3. Prefer merge style that satisfies signed-commit enforcement in protected branch policy.

## Rollback / recovery
If sync branch is wrong:

```bash
cd /Users/linktrend/Projects/LiNKautowork/link-n8n
git checkout master
git pull --ff-only origin master
git branch -D <bad-sync-branch>
git push origin --delete <bad-sync-branch>
```

If local repo is dirty/broken before sync:

```bash
cd /Users/linktrend/Projects/LiNKautowork/link-n8n
git status
# stash or commit explicitly, then rerun runbook
```

## Post-merge cleanup and parity verification

```bash
bash /Users/linktrend/Projects/LiNKautowork/scripts/git/post-merge-cleanup.sh --repo-path /Users/linktrend/Projects/LiNKautowork/link-n8n --delete-remote --apply
bash /Users/linktrend/Projects/LiNKautowork/scripts/git/verify-parity.sh --repo-path /Users/linktrend/Projects/LiNKautowork/link-n8n --branch master
```

Expected parity condition:
- `local master hash == origin/master hash`
