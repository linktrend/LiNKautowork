#!/usr/bin/env bash
# Planner → Orchestrator handoff after G2 PASS.
# Cloud agents: push handoff marker only — merge/label/dispatch runs in linkdev-planner-bootstrap.yml.
set -euo pipefail

PROGRAM_ID="${1:-}"
if [[ -z "$PROGRAM_ID" ]]; then
  echo "usage: planner-handoff.sh <program-id>" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

STATE_FILE="LiNKdev/factory/STATE.md"
HANDOFF_DIR=".linkdev/handoff"
HANDOFF_FILE="${HANDOFF_DIR}/planner-complete.json"
INTEGRATION_BRANCH="${LINKDEV_INTEGRATION_BRANCH:-development}"

fail() { echo "HANDOFF FAIL: $*" >&2; exit 1; }
info() { echo "HANDOFF: $*"; }

read_state_field() {
  local field="$1"
  python3 - <<'PY' "$STATE_FILE" "$field"
import json, re, sys
text = open(sys.argv[1]).read()
m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
if not m:
    sys.exit("STATE.md missing json block")
state = json.loads(m.group(1))
print(state.get(sys.argv[2], ""))
PY
}

optional_pr_number() {
  local branch="$1"
  if ! command -v gh >/dev/null 2>&1; then
    return 0
  fi
  gh auth status >/dev/null 2>&1 || return 0
  local repo pr
  repo="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)"
  [[ -n "$repo" ]] || return 0
  pr="$(gh pr list --repo "$repo" --head "$branch" --state open --json number -q '.[0].number' 2>/dev/null || true)"
  if [[ -n "$pr" && "$pr" != "null" ]]; then
    echo "$pr"
  fi
}

main() {
  [[ -f "$STATE_FILE" ]] || fail "missing $STATE_FILE"

  LiNKdev/factory/scripts/validate-intent.sh "$PROGRAM_ID"
  LiNKdev/factory/scripts/verify.sh

  local phase trigger state_program branch head_sha pr_number created_at
  phase="$(read_state_field phase)"
  trigger="$(read_state_field next_orchestrator_trigger)"
  state_program="$(read_state_field program_id)"

  [[ "$state_program" == "$PROGRAM_ID" ]] || fail "STATE program_id ${state_program!r} != ${PROGRAM_ID!r}"
  [[ "$phase" == "running" ]] || fail "STATE phase must be running (got ${phase!r})"
  [[ "$trigger" == "go" || "$trigger" == "merge_to_development" ]] || {
    if [[ "$trigger" == "none" ]]; then
      info "orchestrator trigger already cleared — handoff may be complete"
      exit 0
    fi
    fail "STATE next_orchestrator_trigger must be go (got ${trigger!r})"
  }

  branch="$(git rev-parse --abbrev-ref HEAD)"
  head_sha="$(git rev-parse HEAD)"
  created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  pr_number="$(optional_pr_number "$branch" || true)"

  mkdir -p "$HANDOFF_DIR"
  python3 - <<'PY' "$HANDOFF_FILE" "$PROGRAM_ID" "$branch" "$head_sha" "$created_at" "${pr_number:-}"
import json, sys
from pathlib import Path
path, program_id, branch, head_sha, created_at = sys.argv[1:6]
pr = sys.argv[6] if len(sys.argv) > 6 and sys.argv[6] else ""
payload = {
    "program_id": program_id,
    "branch": branch,
    "head_sha": head_sha,
    "created_at": created_at,
}
if pr.isdigit():
    payload["pr_number"] = int(pr)
Path(path).write_text(json.dumps(payload, indent=2) + "\n")
PY

  git add "$HANDOFF_FILE" "$STATE_FILE"
  if ! git diff --cached --quiet; then
    git commit -m "chore(linkdev): planner handoff marker (${PROGRAM_ID})"
  else
    info "handoff marker unchanged — ensuring push"
  fi

  info "pushing branch ${branch} (marker ${HANDOFF_FILE})"
  git push -u origin "HEAD"

  if [[ "$branch" != "$INTEGRATION_BRANCH" ]]; then
    info "bootstrap PR base must be ${INTEGRATION_BRANCH} — never main (workflow retargets if needed)"
  fi

  echo ""
  echo "Handoff delegated to GitHub Actions linkdev-planner-bootstrap"
  echo "Wait for workflow green before telling Principal handoff is complete."
}

main "$@"
