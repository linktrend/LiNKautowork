#!/usr/bin/env bash
# Automatic Planner → Orchestrator handoff after G2 PASS (zero Principal action).
# Ensures program setup is on development, then triggers Orchestrator dispatch.
set -euo pipefail

PROGRAM_ID="${1:-}"
if [[ -z "$PROGRAM_ID" ]]; then
  echo "usage: planner-handoff.sh <program-id>" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

STATE_FILE="LiNKdev/factory/STATE.md"
INTEGRATION_BRANCH="${LINKDEV_INTEGRATION_BRANCH:-development}"
BOOTSTRAP_MARKER="[linkdev-bootstrap]"

fail() { echo "HANDOFF FAIL: $*" >&2; exit 1; }
info() { echo "HANDOFF: $*"; }

require_gh() {
  command -v gh >/dev/null 2>&1 || fail "gh CLI required"
  gh auth status >/dev/null 2>&1 || fail "gh not authenticated"
}

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

state_on_development() {
  local branch="$1"
  if [[ "$branch" == "$INTEGRATION_BRANCH" ]]; then
    return 0
  fi
  git fetch origin "$INTEGRATION_BRANCH" >/dev/null 2>&1 || true
  git show "origin/${INTEGRATION_BRANCH}:${STATE_FILE}" >/dev/null 2>&1 || return 1
  local remote_phase remote_trigger remote_program
  remote_phase="$(git show "origin/${INTEGRATION_BRANCH}:${STATE_FILE}" | python3 - <<'PY'
import json, re, sys
text = sys.stdin.read()
m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
if not m:
    sys.exit(1)
print(json.loads(m.group(1)).get("phase", ""))
PY
)"
  remote_trigger="$(git show "origin/${INTEGRATION_BRANCH}:${STATE_FILE}" | python3 - <<'PY'
import json, re, sys
text = sys.stdin.read()
m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
if not m:
    sys.exit(1)
print(json.loads(m.group(1)).get("next_orchestrator_trigger", ""))
PY
)"
  remote_program="$(git show "origin/${INTEGRATION_BRANCH}:${STATE_FILE}" | python3 - <<'PY'
import json, re, sys
text = sys.stdin.read()
m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
if not m:
    sys.exit(1)
print(json.loads(m.group(1)).get("program_id", ""))
PY
)"
  [[ "$remote_phase" == "running" && "$remote_trigger" == "go" && "$remote_program" == "$PROGRAM_ID" ]]
}

ensure_bootstrap_pr() {
  local branch="$1"
  local repo pr body title
  repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
  info "pushing branch ${branch}"
  git push -u origin "HEAD" >/dev/null

  pr="$(gh pr list --repo "$repo" --head "$branch" --base "$INTEGRATION_BRANCH" --state open --json number -q '.[0].number' 2>/dev/null || true)"
  title="Program setup: ${PROGRAM_ID} (${BOOTSTRAP_MARKER})"
  body="${BOOTSTRAP_MARKER}

Planner G2 PASS — bootstrap program merge to \`${INTEGRATION_BRANCH}\`.
Reviewer skipped per bootstrap merge rule; \`verify.sh\` required.

Program: \`${PROGRAM_ID}\`
"

  if [[ -z "$pr" || "$pr" == "null" ]]; then
    info "opening PR to ${INTEGRATION_BRANCH}"
    pr="$(gh pr create --repo "$repo" --base "$INTEGRATION_BRANCH" --head "$branch" --title "$title" --body "$body" --json number -q .number)"
  else
    info "updating existing PR #${pr}"
    gh pr edit "$pr" --repo "$repo" --title "$title" --body "$body" >/dev/null
  fi

  LiNKdev/factory/scripts/verify.sh

  gh pr edit "$pr" --repo "$repo" --add-label "linkdev:bootstrap-merge" --add-label "linkdev:merge-ready" 2>/dev/null || {
    info "labels missing on repo — run install-labels.sh during wire"
    gh pr edit "$pr" --repo "$repo" --add-label "linkdev:merge-ready" >/dev/null || true
  }

  if gh pr view "$pr" --repo "$repo" --json mergeable,mergeStateStatus -q '.mergeable' | grep -q true; then
    info "attempting bootstrap merge for PR #${pr}"
    if gh pr merge "$pr" --repo "$repo" --merge --delete-branch=false >/dev/null 2>&1; then
      info "merged PR #${pr} to ${INTEGRATION_BRANCH}"
      git fetch origin "$INTEGRATION_BRANCH" >/dev/null 2>&1 || true
      return 0
    fi
    info "direct merge unavailable — integrator dispatch will merge PR #${pr}"
  fi
}

trigger_orchestrator_fallback() {
  local repo="$1"
  info "fallback: triggering orchestrator dispatch"
  if gh workflow run "LiNKdev dispatch" --repo "$repo" --ref "$INTEGRATION_BRANCH" -f role=orchestrator >/dev/null 2>&1; then
    info "workflow_dispatch orchestrator queued"
    return 0
  fi
  info "workflow_dispatch unavailable — sending repository_dispatch fallback"
  gh api "repos/${repo}/dispatches" \
    -f event_type=linkdev-planner-complete \
    -f "client_payload[program_id]=${PROGRAM_ID}" >/dev/null
}

main() {
  require_gh
  [[ -f "$STATE_FILE" ]] || fail "missing $STATE_FILE"

  LiNKdev/factory/scripts/validate-intent.sh "$PROGRAM_ID"

  local phase trigger state_program branch repo
  phase="$(read_state_field phase)"
  trigger="$(read_state_field next_orchestrator_trigger)"
  state_program="$(read_state_field program_id)"

  [[ "$state_program" == "$PROGRAM_ID" ]] || fail "STATE program_id ${state_program!r} != ${PROGRAM_ID!r}"
  [[ "$phase" == "running" ]] || fail "STATE phase must be running (got ${phase!r})"
  [[ "$trigger" == "go" || "$trigger" == "merge_to_development" ]] || {
    if [[ "$trigger" == "none" ]]; then
      info "orchestrator trigger already cleared — handoff complete"
      exit 0
    fi
    fail "STATE next_orchestrator_trigger must be go (got ${trigger!r})"
  }

  branch="$(git rev-parse --abbrev-ref HEAD)"
  repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
  local merged_to_development=false

  if [[ "$branch" != "$INTEGRATION_BRANCH" ]]; then
    ensure_bootstrap_pr "$branch"
    if state_on_development "$branch"; then
      merged_to_development=true
      git fetch origin "$INTEGRATION_BRANCH" >/dev/null 2>&1 || true
      git checkout "$INTEGRATION_BRANCH" >/dev/null 2>&1 || git checkout -B "$INTEGRATION_BRANCH" "origin/${INTEGRATION_BRANCH}"
      git pull --rebase origin "$INTEGRATION_BRANCH" >/dev/null 2>&1 || true
    else
      info "STATE not yet on ${INTEGRATION_BRANCH} — integrator merge will dispatch orchestrator"
      exit 0
    fi
  else
    info "on ${INTEGRATION_BRANCH} — pushing STATE (push trigger dispatches orchestrator)"
    git push origin "$INTEGRATION_BRANCH" >/dev/null 2>&1 || true
  fi

  chmod +x LiNKdev/factory/scripts/check-labels-for-dispatch.sh
  if ! LiNKdev/factory/scripts/check-labels-for-dispatch.sh state-requests-orchestrator "$STATE_FILE" "$PROGRAM_ID"; then
    if [[ "$merged_to_development" == true ]]; then
      info "merge closed event will dispatch orchestrator"
    else
      trigger_orchestrator_fallback "$repo"
    fi
  fi

  info "handoff complete for program ${PROGRAM_ID} (orchestrator clears next_orchestrator_trigger on start)"
}

main "$@"
