#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [--repo <owner/name>] [--branch <name>]

Validates branch protection compatibility for PR-only and signed-commit policy.
USAGE
}

repo="linktrend/link-n8n"
branch="master"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      repo="$2"
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

for cmd in gh jq; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: $cmd is required." >&2; exit 1; }
done

json="$(gh api "repos/$repo/branches/$branch/protection")"

checks=(
  '.required_signatures.enabled == true'
  '.required_pull_request_reviews.required_approving_review_count >= 1'
  '.required_pull_request_reviews.require_code_owner_reviews == true'
  '.required_conversation_resolution.enabled == true'
  '.allow_force_pushes.enabled == false'
  '.allow_deletions.enabled == false'
)

for expr in "${checks[@]}"; do
  if ! jq -e "$expr" >/dev/null <<<"$json"; then
    echo "ERROR: branch protection check failed: $expr" >&2
    exit 1
  fi
done

echo "PASS: branch protection policy is compatible with PR-only + signed-commit governance."
