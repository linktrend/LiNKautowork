#!/usr/bin/env bash
# Create or update LiNKdev GitHub labels (idempotent). Used by wire session.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
REPO="${GITHUB_REPOSITORY:-$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)}"
if [[ -z "$REPO" ]]; then
  echo "ERROR: cannot resolve GitHub repo. Set GITHUB_REPOSITORY or run from a git repo with gh auth." >&2
  exit 1
fi
# name|color|description (pipe delimiter — label names contain colons)
labels=(
  "linkdev:planned|cfd3d7|Issue planned, not ready"
  "linkdev:ready|0e8a16|Ready for executor automation"
  "linkdev:in-progress|fbca04|Executor active"
  "linkdev:review-ready|1d76db|Ready for reviewer"
  "linkdev:merge-ready|2da44e|Verify passed, integrator may merge"
  "linkdev:blocked|d73a4a|Blocked — principal/orchestrator"
  "linkdev:done|0e8a16|Issue complete on development"
  "runtime:cursor|5319e7|Cursor executor runtime"
  "runtime:codex|1f6feb|Codex executor runtime"
  "tier:standard|c5def5|Standard verify tier"
  "tier:critical|b60205|Critical verify tier"
  "linkdev:program-active|0366d6|Program running"
  "linkdev:principal-stop|e99695|Scheduled principal checkpoint"
  "linkdev:promote-staging|FBCA04|Principal authorized staging promotion"
  "linkdev:promote-main|B60205|Principal authorized main promotion"
)
for entry in "${labels[@]}"; do
  IFS='|' read -r name color desc <<< "$entry"
  gh label create "$name" --repo "$REPO" --color "$color" --description "$desc" --force >/dev/null
done
echo "OK: labels ensured on $REPO (${#labels[@]} definitions)"
gh label list --repo "$REPO" --limit 200 | grep -E 'linkdev:|runtime:|tier:' || true
