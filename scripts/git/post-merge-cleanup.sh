#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [--repo-path <path>] [--approved <csv>] [--apply] [--delete-remote]

Safely deletes merged branches.
Default mode is dry-run; add --apply to execute deletions.
USAGE
}

repo_path="link-n8n"
approved_csv=""
apply="false"
delete_remote="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-path)
      repo_path="$2"
      shift 2
      ;;
    --approved)
      approved_csv="$2"
      shift 2
      ;;
    --apply)
      apply="true"
      shift 1
      ;;
    --delete-remote)
      delete_remote="true"
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

if [[ ! -d "$repo_path/.git" ]]; then
  echo "ERROR: Not a git repository: $repo_path" >&2
  exit 1
fi

if [[ -n "$(git -C "$repo_path" status --porcelain)" ]]; then
  echo "ERROR: working tree is not clean in $repo_path" >&2
  exit 1
fi

# Always prune first
git -C "$repo_path" fetch origin --prune

default_branch="$(git -C "$repo_path" remote show origin | sed -n 's/.*HEAD branch: //p')"
[[ -n "$default_branch" ]] || { echo "ERROR: could not determine default branch" >&2; exit 1; }

approved_file="$(mktemp)"
{
  echo "$default_branch"
  echo "main"
  echo "master"
  if [[ -n "$approved_csv" ]]; then
    echo "$approved_csv" | tr ',' '\n'
  fi
} | sed '/^$/d' | sort -u > "$approved_file"

safe_local=()
while IFS= read -r b; do
  [[ -z "$b" ]] && continue
  if grep -qx "$b" "$approved_file"; then
    continue
  fi
  safe_local+=("$b")
done <<LOCAL_MERGED
$(git -C "$repo_path" branch --format='%(refname:short)' --merged "origin/$default_branch" | sed 's/^* //')
LOCAL_MERGED

echo "Local merged branches eligible for cleanup:"
for b in "${safe_local[@]-}"; do
  [[ -z "$b" ]] && continue
  echo "  - $b"
done

if [[ "$apply" == "true" ]]; then
  for b in "${safe_local[@]-}"; do
    [[ -z "$b" ]] && continue
    git -C "$repo_path" branch -d "$b"
  done
fi

if [[ "$delete_remote" == "true" ]]; then
  safe_remote=()
  while IFS= read -r b; do
    [[ "$b" == "HEAD" ]] && continue
    [[ -z "$b" ]] && continue
    if grep -qx "$b" "$approved_file"; then
      continue
    fi
    safe_remote+=("$b")
  done <<REMOTE_MERGED
$(git -C "$repo_path" branch -r --merged "origin/$default_branch" | sed 's/^ *//' | rg '^origin/' | rg -v ' -> ' | sed 's#^origin/##')
REMOTE_MERGED

  echo "Remote merged branches eligible for cleanup:"
  for b in "${safe_remote[@]-}"; do
    [[ -z "$b" ]] && continue
    echo "  - $b"
  done

  if [[ "$apply" == "true" ]]; then
    for b in "${safe_remote[@]-}"; do
      [[ -z "$b" ]] && continue
      git -C "$repo_path" push origin --delete "$b"
    done
  fi
fi

if [[ "$apply" == "true" ]]; then
  echo "Cleanup completed."
else
  echo "Dry-run only. Re-run with --apply to execute deletions."
fi
