#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --repo-path <path>         Path to link-n8n repo (default: link-n8n)
  --base-branch <name>       Base branch on origin (default: master)
  --upstream-branch <name>   Upstream branch to merge (default: master)
  --branch-prefix <prefix>   Sync branch prefix (default: sync/upstream)
  --allow-unsigned           Skip active signing probe (CI/bot bootstrap only)
  --no-pr                    Do not open PR automatically
  -h, --help                 Show help

This script never pushes to protected base branch directly.
It creates and pushes a sync branch, then opens a PR.
USAGE
}

repo_path="link-n8n"
base_branch="master"
upstream_branch="master"
branch_prefix="sync/upstream"
allow_unsigned="false"
open_pr="true"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-path)
      repo_path="$2"
      shift 2
      ;;
    --base-branch)
      base_branch="$2"
      shift 2
      ;;
    --upstream-branch)
      upstream_branch="$2"
      shift 2
      ;;
    --branch-prefix)
      branch_prefix="$2"
      shift 2
      ;;
    --allow-unsigned)
      allow_unsigned="true"
      shift 1
      ;;
    --no-pr)
      open_pr="false"
      shift 1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

for cmd in git gh; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: $cmd is required." >&2; exit 1; }
done

if [[ ! -d "$repo_path/.git" ]]; then
  echo "ERROR: Repository path not found: $repo_path" >&2
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$script_dir/check-signing-prereqs.sh" --repo-path "$repo_path" $([[ "$allow_unsigned" == "true" ]] && echo "--allow-unsigned")

if [[ -n "$(git -C "$repo_path" status --porcelain)" ]]; then
  echo "ERROR: working tree is not clean in $repo_path" >&2
  exit 1
fi

if ! git -C "$repo_path" remote get-url origin >/dev/null 2>&1; then
  echo "ERROR: origin remote missing." >&2
  exit 1
fi
if ! git -C "$repo_path" remote get-url upstream >/dev/null 2>&1; then
  echo "ERROR: upstream remote missing." >&2
  exit 1
fi

# Hard-block upstream pushes on every run.
git -C "$repo_path" remote set-url --push upstream no_push

echo "[1/8] Fetching remotes"
git -C "$repo_path" fetch origin --prune --tags
git -C "$repo_path" fetch upstream --prune --tags

echo "[2/8] Preparing base branch $base_branch"
git -C "$repo_path" checkout "$base_branch" >/dev/null 2>&1
git -C "$repo_path" pull --ff-only origin "$base_branch"

branch_suffix="$(date +%y%m%d)"
branch_name="${branch_prefix}-${branch_suffix}"
if git -C "$repo_path" show-ref --quiet "refs/heads/$branch_name"; then
  branch_name="${branch_name}-$(date +%H%M)"
fi

echo "[3/8] Creating sync branch $branch_name"
git -C "$repo_path" checkout -b "$branch_name"

echo "[4/8] Enabling rerere for repeatable conflict resolutions"
git -C "$repo_path" config rerere.enabled true

echo "[5/8] Merging upstream/$upstream_branch"
set +e
git -C "$repo_path" merge --no-ff "upstream/$upstream_branch" -m "chore(sync): merge upstream/$upstream_branch into $branch_name"
merge_exit=$?
set -e

if [[ $merge_exit -ne 0 ]]; then
  echo ""
  echo "Merge conflict detected. Preserve LiNK customizations using runbook guidance:"
  echo "- /Users/linktrend/Projects/LiNKautowork/UPSTREAM_SYNC_RUNBOOK.md"
  echo "- /Users/linktrend/Projects/LiNKautowork/docs/git/KNOWN_HOT_FILES.md"
  echo ""
  echo "After resolving conflicts and committing, run:"
  echo "  git -C $repo_path push -u origin $branch_name"
  echo "  gh pr create --repo linktrend/link-n8n --base $base_branch --head $branch_name --title \"chore(sync): upstream merge $branch_suffix\""
  exit 3
fi

echo "[6/8] Pushing sync branch"
git -C "$repo_path" push -u origin "$branch_name"

if [[ "$open_pr" == "false" ]]; then
  echo "[7/8] PR creation skipped (--no-pr)."
  echo "Branch pushed: $branch_name"
  exit 0
fi

origin_url="$(git -C "$repo_path" remote get-url origin)"
repo_slug="$(echo "$origin_url" | sed -E 's#^https://github.com/##; s#\.git$##')"

echo "[7/8] Creating PR in $repo_slug"
pr_title="chore(sync): upstream merge $branch_suffix"
pr_body=$(cat <<PRBODY
## Automated upstream sync
- Source: \\`upstream/$upstream_branch\\`
- Target: \\`$base_branch\\`
- Sync branch: \\`$branch_name\\`

## Safety checks
- Upstream push remains blocked (\\`upstream -> no_push\\`).
- Direct push to protected branch is not used.
- Signed-commit preflight passed before merge commit creation.

## Operator checklist
1. Validate conflict-sensitive files from runbook.
2. Confirm LiNK custom behavior is preserved.
3. Merge via PR flow only.
PRBODY
)

pr_url="$(gh pr create --repo "$repo_slug" --base "$base_branch" --head "$branch_name" --title "$pr_title" --body "$pr_body")"

echo "[8/8] Done"
echo "PR URL: $pr_url"
