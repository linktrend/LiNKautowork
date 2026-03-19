#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [--repo-path <path>] [--branch <name>]

Verifies local branch commit hash equals origin/<branch>.
USAGE
}

repo_path="link-n8n"
branch=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-path)
      repo_path="$2"
      shift 2
      ;;
    --branch)
      branch="$2"
      shift 2
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

git -C "$repo_path" fetch origin --prune

if [[ -z "$branch" ]]; then
  branch="$(git -C "$repo_path" remote show origin | sed -n 's/.*HEAD branch: //p')"
fi

local_hash="$(git -C "$repo_path" rev-parse "$branch")"
remote_hash="$(git -C "$repo_path" rev-parse "origin/$branch")"

echo "local  $branch: $local_hash"
echo "origin $branch: $remote_hash"

if [[ "$local_hash" != "$remote_hash" ]]; then
  echo "ERROR: local and origin are not in parity." >&2
  exit 1
fi

echo "PASS: local and origin are exactly in parity."
