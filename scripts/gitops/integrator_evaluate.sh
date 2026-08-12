#!/usr/bin/env bash
# Integrator evaluate/merge for PRs into development.
# Requires GitHub normal automation token (fail closed).
# Emits integrator-result.json + gitops-outcome.json with honest status.
# Posts commit status "Linktrend Integrator Result" (success only when merged).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PR_NUMBER="${PR_NUMBER:-}"
HEAD_SHA="${HEAD_SHA:-}"
REQUIRED_CHECKS="${REQUIRED_CHECKS:-Verify IDE Development}"
BUGBOT_SUCCESS_CHECK_NAME="${BUGBOT_SUCCESS_CHECK_NAME:-Cursor Bugbot}"
GATE_WAIT_SECONDS="${GATE_WAIT_SECONDS:-120}"
GATE_POLL_SECONDS="${GATE_POLL_SECONDS:-15}"
GH_REPO="${GH_REPO:-${GITHUB_REPOSITORY:-}}"

TOKEN="${AUTOMATION_TOKEN:-}"
if [ -z "${TOKEN}" ] || [ "${AUTOMATION_TOKEN_SOURCE:-}" != "github_token" ]; then
  # automation token unavailable: local outcome only — no repair/check mutation via workflow token.
  python3 "${SCRIPT_DIR}/write_outcome.py" \
    --file integrator-result.json \
    --status automation_credentials_blocked \
    --detail "Integrator requires normal GitHub automation token for autonomous merge"
  cp integrator-result.json gitops-outcome.json 2>/dev/null || true
  exit 0
fi
export GH_TOKEN="${TOKEN}"
export GITHUB_TOKEN="${TOKEN}"

write_result() {
  local status="$1"
  local detail="$2"
  local pr="${3:-}"
  local sha="${4:-}"
  python3 - "$status" "$detail" "$pr" "$sha" <<'PY'
import json, sys
status, detail, pr, sha = sys.argv[1:5]
payload = {"status": status, "detail": detail, "pr": pr or None, "headSha": sha or None}
text = json.dumps(payload, indent=2) + "\n"
open("integrator-result.json", "w", encoding="utf-8").write(text)
open("gitops-outcome.json", "w", encoding="utf-8").write(text)
print(f"INTEGRATOR_STATUS={status}")
print(f"INTEGRATOR_DETAIL={detail}")
PY
}

post_check() {
  local status="$1"
  local detail="$2"
  local sha="$3"
  python3 "${SCRIPT_DIR}/write_outcome.py" \
    --file gitops-outcome.json \
    --status "$status" \
    --detail "$detail" \
    --check-name "Linktrend Integrator Result" \
    --head-sha "${sha}" \
    --repo "${GH_REPO}" \
    --token-env AUTOMATION_TOKEN >/dev/null || true
}

bugbot_state_from_checks() {
  echo "$1" | jq -r --arg n "${BUGBOT_SUCCESS_CHECK_NAME}" '
    [.[] | select(.name==$n)] as $b
    | if ($b|length)==0 then "missing"
      else
        ($b | sort_by(.completedAt // .startedAt // "") | last | .state) as $s
        | if ($s=="PENDING" or $s=="QUEUED" or $s=="IN_PROGRESS") then "pending"
          elif ($s=="SUCCESS") then "success"
          else "not_success"
          end
      end'
}

resolve_reviewed_sha() {
  local pr="$1"
  local body comments
  body="$(gh pr view "${pr}" --json body --jq .body 2>/dev/null || true)"
  comments="$(gh api "repos/${GH_REPO}/issues/${pr}/comments" --paginate --jq '.[].body' 2>/dev/null || true)"
  printf '%s\n%s\n' "${body}" "${comments}" \
    | grep -oE '<!-- linktrend-bugbot-requested:[[:space:]]*[0-9a-fA-F]+[[:space:]]*-->' \
    | tail -n1 \
    | sed -E 's/.*linktrend-bugbot-requested:[[:space:]]*([0-9a-fA-F]+).*/\1/' \
    | tr 'A-F' 'a-f' || true
}

collect_pr() {
  if [ -n "${PR_NUMBER}" ]; then
    echo "${PR_NUMBER}"
  elif [ -n "${HEAD_SHA}" ]; then
    gh pr list --base development --state open \
      --json number,isDraft,headRefOid \
      --jq "[.[] | select(.isDraft==false and .headRefOid==\"${HEAD_SHA}\") | .number] | .[0] // empty"
  fi
}

pr="$(collect_pr || true)"
if [ -z "${pr}" ]; then
  write_result "waiting" "No candidate development PR to evaluate" "" "${HEAD_SHA}"
  post_check "waiting" "No candidate PR" "${HEAD_SHA}"
  exit 0
fi

meta="$(gh pr view "${pr}" --json baseRefName,isDraft,state,headRefOid,mergeable)"
echo "${meta}" | jq -e '.baseRefName=="development" and .isDraft==false and .state=="OPEN"' >/dev/null \
  || {
    write_result "blocked" "PR #${pr} is not an open non-draft development PR" "${pr}" "$(echo "${meta}" | jq -r .headRefOid)"
    post_check "blocked" "invalid PR state" "$(echo "${meta}" | jq -r .headRefOid)"
    exit 0
  }

# Event may carry a stale SHA — always reread live head before acting
head_sha="$(echo "${meta}" | jq -r .headRefOid)"
if [ -n "${HEAD_SHA}" ] && [ "${HEAD_SHA}" != "${head_sha}" ]; then
  write_result "skipped" "stale event: event head ${HEAD_SHA} != live ${head_sha}" "${pr}" "${head_sha}"
  post_check "skipped" "stale event head" "${head_sha}"
  exit 0
fi

reviewed="$(resolve_reviewed_sha "${pr}")"
if [ -z "${reviewed}" ]; then
  write_result "waiting" "PR #${pr}: no Bugbot-requested marker yet for a reviewed SHA" "${pr}" "${head_sha}"
  post_check "waiting" "awaiting Bugbot request marker" "${head_sha}"
  exit 0
fi
if [ "${head_sha}" != "${reviewed}" ]; then
  write_result "blocked" "PR #${pr}: head ${head_sha} != reviewed ${reviewed}" "${pr}" "${head_sha}"
  post_check "blocked" "head drifted from reviewed SHA" "${head_sha}"
  exit 0
fi

mergeable="$(echo "${meta}" | jq -r .mergeable)"
if [ "${mergeable}" = "CONFLICTING" ]; then
  head_ref="$(echo "${meta}" | jq -r .headRefName)"
  python3 "${SCRIPT_DIR}/repair_task.py" upsert \
    --repo "${GH_REPO}" \
    --failure-type merge_conflict \
    --pr "${pr}" \
    --branch "${head_ref}" \
    --head-sha "${head_sha}" \
    --next-action "Resolve merge conflict on PR #${pr}; Lisa may dispatch ordinary repair." \
    >/dev/null || true
  write_result "blocked" "PR #${pr}: conflict_blocked" "${pr}" "${head_sha}"
  post_check "blocked" "merge conflict" "${head_sha}"
  exit 0
fi

deadline=$((SECONDS + GATE_WAIT_SECONDS))
while true; do
  # Reread live head each loop — old events must not merge a new tip
  live_head="$(gh pr view "${pr}" --json headRefOid --jq .headRefOid)"
  if [ "${live_head}" != "${head_sha}" ]; then
    write_result "skipped" "head changed during evaluate ${live_head}" "${pr}" "${live_head}"
    post_check "skipped" "head changed" "${live_head}"
    exit 0
  fi

  if ! checks_raw="$(gh pr checks "${pr}" --json name,state,completedAt,startedAt 2>/tmp/gh-pr-checks.err)"; then
    if [ "${SECONDS}" -ge "${deadline}" ]; then
      write_result "waiting" "PR #${pr}: could not read checks before timeout" "${pr}" "${head_sha}"
      post_check "waiting" "checks unreadable" "${head_sha}"
      exit 0
    fi
    sleep "${GATE_POLL_SECONDS}"
    continue
  fi

  bugbot="$(bugbot_state_from_checks "${checks_raw}")"
  gate_json="$(printf '%s' "${checks_raw}" | REQUIRED_CHECKS="${REQUIRED_CHECKS}" python3 -c '
import json,sys,os
sys.path.insert(0,"scripts/gitops")
from packager_logic import fast_gate_status, parse_required_checks
checks=json.load(sys.stdin)
status,detail=fast_gate_status(checks, parse_required_checks(os.environ["REQUIRED_CHECKS"]))
print(json.dumps({"status":status,"detail":detail}))
')"
  gate_status="$(echo "${gate_json}" | jq -r .status)"
  gate_detail="$(echo "${gate_json}" | jq -r .detail)"

  if [ "${bugbot}" = "success" ] && [ "${gate_status}" = "success" ]; then
    live_head="$(gh pr view "${pr}" --json headRefOid --jq .headRefOid)"
    if [ "${live_head}" != "${head_sha}" ] || [ "${live_head}" != "${reviewed}" ]; then
      write_result "skipped" "head changed before merge" "${pr}" "${live_head}"
      post_check "skipped" "head changed before merge" "${live_head}"
      exit 0
    fi
    if gh pr merge "${pr}" --squash --auto || gh pr merge "${pr}" --squash; then
      write_result "merged" "PR #${pr} merged at ${head_sha}" "${pr}" "${head_sha}"
      post_check "merged" "merged ${head_sha}" "${head_sha}"
      exit 0
    fi
    head_ref="$(gh pr view "${pr}" --json headRefName --jq .headRefName 2>/dev/null || true)"
    python3 "${SCRIPT_DIR}/repair_task.py" upsert \
      --repo "${GH_REPO}" \
      --failure-type merge_conflict \
      --pr "${pr}" \
      --branch "${head_ref}" \
      --head-sha "${head_sha}" \
      --next-action "Merge failed on PR #${pr} after green gates; inspect policy/conflict." \
      >/dev/null || true
    write_result "blocked" "PR #${pr}: gates green but merge failed (policy/conflict)" "${pr}" "${head_sha}"
    post_check "blocked" "merge failed" "${head_sha}"
    exit 0
  fi

  if [ "${bugbot}" = "not_success" ]; then
    write_result "blocked" "PR #${pr}: ${BUGBOT_SUCCESS_CHECK_NAME} not success" "${pr}" "${head_sha}"
    post_check "blocked" "Bugbot not success" "${head_sha}"
    exit 0
  fi
  if [ "${gate_status}" = "failed" ]; then
    write_result "blocked" "PR #${pr}: fast-gate failed (${gate_detail})" "${pr}" "${head_sha}"
    post_check "blocked" "fast-gate failed: ${gate_detail}" "${head_sha}"
    exit 0
  fi

  if [ "${SECONDS}" -ge "${deadline}" ]; then
    write_result "waiting" "PR #${pr}: still waiting (bugbot=${bugbot} gate=${gate_status}:${gate_detail})" "${pr}" "${head_sha}"
    post_check "waiting" "timeout waiting for gates" "${head_sha}"
    exit 0
  fi
  sleep "${GATE_POLL_SECONDS}"
done
