#!/usr/bin/env bash
# Pull/update unfinished work branches from origin/development using isolated worktrees.
# Never checks out branches in the caller's worktree. Never force-pushes / resets / discards.
#
# Usage:
#   pull-update-work-branches.sh [--branch NAME]...
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "FAIL: not a git repository" >&2
  exit 1
}
cd "$ROOT"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=gitops/work-branch-allowlist.sh
source "${SCRIPT_DIR}/gitops/work-branch-allowlist.sh"

ONLY_BRANCHES=()
while [ $# -gt 0 ]; do
  case "$1" in
    --branch) ONLY_BRANCHES+=("$2"); shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

START_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
START_SHA="$(git rev-parse HEAD)"
START_STATUS="$(git status --porcelain)"
START_WORKTREES="$(git worktree list --porcelain)"

CREATED_WORKTREES=()
cleanup_temp_worktrees() {
  local wt
  for wt in "${CREATED_WORKTREES[@]:-}"; do
    [ -n "$wt" ] || continue
    git worktree remove --force "$wt" >/dev/null 2>&1 || rm -rf "$wt"
  done
}
trap cleanup_temp_worktrees EXIT

if git remote get-url origin >/dev/null 2>&1; then
  git fetch origin development
elif ! git show-ref --verify --quiet refs/remotes/origin/development; then
  echo "FAIL: no origin remote and no refs/remotes/origin/development" >&2
  exit 1
fi

# Map branch -> existing worktree path (if any)
existing_worktree_for_branch() {
  local branch="$1"
  git worktree list --porcelain | python3 -c '
import sys
branch=sys.argv[1]
path=None
cur_path=None
for line in sys.stdin.read().splitlines():
    if line.startswith("worktree "):
        cur_path=line.split(" ",1)[1]
    elif line == f"branch refs/heads/{branch}":
        print(cur_path or "")
        break
' "$branch"
}

is_frozen() {
  local branch="$1"
  local tip
  tip="$(git rev-parse "refs/heads/${branch}" 2>/dev/null || git rev-parse "refs/remotes/origin/${branch}" 2>/dev/null || true)"
  [ -n "$tip" ] || return 1
  # readiness status on tip
  if python3 "${SCRIPT_DIR}/gitops/readiness_status.py" get "$tip" >/dev/null 2>&1; then
    echo "ready_status" >&2
    return 0
  fi
  # open review PR at tip
  if command -v gh >/dev/null 2>&1; then
    local out
    out="$(gh pr list --head "$branch" --base development --state open --json headRefOid 2>/dev/null || echo '[]')"
    if echo "$out" | python3 -c 'import json,sys; tip=sys.argv[1].lower(); rows=json.load(sys.stdin); sys.exit(0 if any((r.get("headRefOid") or "").lower()==tip for r in rows) else 1)' "$tip" 2>/dev/null; then
      echo "open_review_pr" >&2
      return 0
    fi
  fi
  return 1
}

branch_is_dirty_at() {
  local path="$1"
  [ -n "$(git -C "$path" status --porcelain 2>/dev/null || true)" ]
}

update_branch() {
  local branch="$1"
  local tip path tmp created=0

  if ! is_allowed_work_branch "$branch"; then
    echo "SKIP $branch — not an allowed work branch"
    return 0
  fi

  if [ "$branch" = "$START_BRANCH" ]; then
    echo "SKIP $branch — active caller checkout (owned session)"
    return 0
  fi

  if ! git show-ref --verify --quiet "refs/heads/${branch}"; then
    if git show-ref --verify --quiet "refs/remotes/origin/${branch}"; then
      git branch --track "$branch" "origin/${branch}" >/dev/null
    else
      echo "SKIP $branch — not found locally or on origin"
      return 0
    fi
  fi

  tip="$(git rev-parse "refs/heads/${branch}")"

  if is_frozen "$branch" 2>/dev/null; then
    echo "SKIP $branch — review freeze active"
    return 0
  fi

  path="$(existing_worktree_for_branch "$branch")"
  if [ -n "$path" ]; then
    if branch_is_dirty_at "$path"; then
      echo "SKIP $branch — dirty worktree (active session)"
      return 0
    fi
  else
    tmp="$(mktemp -d "${TMPDIR:-/tmp}/pull-wt.XXXXXX")"
    git worktree add --detach "$tmp" "$tip" >/dev/null
    CREATED_WORKTREES+=("$tmp")
    created=1
    path="$tmp"
    git -C "$path" checkout -B "$branch" "$tip" >/dev/null
  fi

  if branch_is_dirty_at "$path"; then
    echo "SKIP $branch — dirty working tree (refusing to discard)"
    return 0
  fi

  if git -C "$path" merge-base --is-ancestor origin/development HEAD; then
    echo "OK $branch — already contains origin/development"
    return 0
  fi

  if git -C "$path" merge --no-edit origin/development; then
    if [ "$created" -eq 1 ]; then
      newsha="$(git -C "$path" rev-parse HEAD)"
      # Only update-ref when no worktree currently has this branch checked out
      if [ -z "$(existing_worktree_for_branch "$branch")" ]; then
        git update-ref "refs/heads/${branch}" "$newsha"
      fi
    fi
    echo "UPDATED $branch — merged origin/development"
  else
    git -C "$path" merge --abort 2>/dev/null || true
    echo "BLOCKED $branch — merge conflict with development (left unchanged)"
  fi
}

if [ "${#ONLY_BRANCHES[@]}" -gt 0 ]; then
  for b in "${ONLY_BRANCHES[@]}"; do
    update_branch "$b"
  done
else
  while IFS= read -r b || [ -n "$b" ]; do
    is_allowed_work_branch "$b" || continue
    update_branch "$b"
  done < <(git for-each-ref --format='%(refname:short)' refs/heads)
fi

# Prove caller checkout unchanged
END_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
END_SHA="$(git rev-parse HEAD)"
END_STATUS="$(git status --porcelain)"
if [ "$START_BRANCH" != "$END_BRANCH" ] || [ "$START_SHA" != "$END_SHA" ] || [ "$START_STATUS" != "$END_STATUS" ]; then
  echo "FAIL: caller checkout changed during pull (branch/sha/status)" >&2
  echo " start: ${START_BRANCH} ${START_SHA}" >&2
  echo " end:   ${END_BRANCH} ${END_SHA}" >&2
  exit 1
fi
# Existing (non-temp) worktrees must still be listed
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    worktree\ *)
      wt="${line#worktree }"
      # skip temps we created
      skip=0
      for t in "${CREATED_WORKTREES[@]:-}"; do
        [ "$wt" = "$t" ] && skip=1 && break
      done
      [ "$skip" -eq 1 ] && continue
      echo "$START_WORKTREES" | grep -F "worktree ${wt}" >/dev/null \
        || { echo "FAIL: pre-existing worktree missing after pull: $wt" >&2; exit 1; }
      ;;
  esac
done <<< "$START_WORKTREES"

echo "PULL_CALLER_UNCHANGED=1"
