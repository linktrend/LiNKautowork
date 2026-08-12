#!/usr/bin/env bash
# Withdraw Linktrend Review Ready for the current tip (or given SHA).
#
# Privileged status writes require AUTOMATION_TOKEN. Ordinary GH_TOKEN / GITHUB_TOKEN
# must never authorize withdraw. Without normal automation credentials this script
# fails closed and prints the normal-token workflow_dispatch route
# (action=withdraw) for operators/agents to run.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "FAIL: not a git repository" >&2
  exit 1
}
cd "$ROOT"
SHA="${1:-$(git rev-parse HEAD)}"
REASON="${2:-withdrawn}"
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set +e
OUT="$(
  python3 "${SCRIPT_DIR}/gitops/readiness_status.py" withdraw "$SHA" "$REASON" --branch "$BRANCH"
)"
RC=$?
set -e
printf '%s\n' "$OUT"
if [ "$RC" -ne 0 ]; then
  echo "FAIL: withdrawing Linktrend Review Ready requires AUTOMATION_TOKEN; use the normal-token route above (never GH_TOKEN/GITHUB_TOKEN)." >&2
  exit "$RC"
fi
echo "PASS: withdrew Linktrend Review Ready for ${SHA}"
