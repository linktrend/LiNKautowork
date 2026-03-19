#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [--repo-path <path>] [--approved <csv>]

Performs branch hygiene checks:
- clean working tree
- valid upstream tracking for current branch
- pruned remotes
- only approved long-lived branches exist on origin
USAGE
}

repo_path="link-n8n"
approved_csv=""

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

git -C "$repo_path" fetch origin --prune

current_branch="$(git -C "$repo_path" rev-parse --abbrev-ref HEAD)"
if ! git -C "$repo_path" rev-parse --abbrev-ref --symbolic-full-name "${current_branch}@{upstream}" >/dev/null 2>&1; then
  echo "ERROR: current branch '$current_branch' has no upstream tracking branch." >&2
  exit 1
fi

default_branch="$(git -C "$repo_path" remote show origin | sed -n 's/.*HEAD branch: //p')"
if [[ -z "$default_branch" ]]; then
  echo "ERROR: could not determine origin default branch." >&2
  exit 1
fi

origin_heads="$(git -C "$repo_path" ls-remote --heads origin | awk '{print $2}' | sed 's#refs/heads/##' | sort)"

approved_file="$(mktemp)"
{
  echo "$default_branch"
  if [[ -n "$approved_csv" ]]; then
    echo "$approved_csv" | tr ',' '\n'
  fi
} | sed '/^$/d' | sort -u > "$approved_file"

extra_file="$(mktemp)"
comm -23 <(echo "$origin_heads") "$approved_file" > "$extra_file"

if [[ -s "$extra_file" ]]; then
  echo "ERROR: unexpected long-lived branches found on origin:" >&2
  sed 's/^/  - /' "$extra_file" >&2
  echo "Use post-merge cleanup or adjust approved list with --approved." >&2
  exit 1
fi

echo "PASS: branch hygiene checks succeeded."
echo "- current branch: $current_branch"
echo "- default branch: $default_branch"
