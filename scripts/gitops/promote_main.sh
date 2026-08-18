#!/usr/bin/env bash
# Promote staging → main via temporary promote/main/* branch + PR.
# MODE=package|approve-merge|reevaluate
# approve-merge REQUIRES EXPECTED_STAGING_SHA, EXPECTED_PROMOTE_HEAD, EXPECTED_MAIN_SHA (prior main tip).
set -euo pipefail
# Note: gh 403/429 → simple retry 2x with sleep (gh_retry).

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "FAIL: not a git repository" >&2
  exit 1
}
cd "$ROOT"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=work-branch-allowlist.sh
source "${SCRIPT_DIR}/work-branch-allowlist.sh"

MODE="${MODE:-package}"
MAIN_PROMOTION_MODE="${MAIN_PROMOTION_MODE:-principal-approval}"
RELEASE_GATE_CHECKS="${RELEASE_GATE_CHECKS:-Verify IDE Development,Linktrend Branch Source Policy}"
TIMEZONE_LABEL="${TIMEZONE_LABEL:-Asia/Taipei}"
EXPECTED_STAGING_SHA="${EXPECTED_STAGING_SHA:-}"
EXPECTED_PROMOTE_HEAD="${EXPECTED_PROMOTE_HEAD:-}"
EXPECTED_MAIN_SHA="${EXPECTED_MAIN_SHA:-}"
PROMOTE_PR_NUMBER="${PROMOTE_PR_NUMBER:-}"
REPO="${GH_REPO:-${GITHUB_REPOSITORY:-}}"
TOKEN="${AUTOMATION_TOKEN:-}"
export GH_TOKEN="${TOKEN}"
export GITHUB_TOKEN="${TOKEN}"
OUTCOME="${OUTCOME_FILE:-gitops-outcome.json}"
RECEIPT_GATE="${SCRIPT_DIR}/promotion_receipt_gate.py"
RECEIPT_PATH="${RECEIPT_PATH:-${LINKTREND_RECEIPT_PATH:-}}"
RECEIPT_DEPENDENCY_FILES="${RECEIPT_DEPENDENCY_FILES:-}"
RECEIPT_IDENTITY_ARGS=()
RECEIPT_PROFILE_ARGS=()
COORDINATOR_RECEIPT_ROOT="${LINKTREND_COORDINATOR_RECEIPT_ROOT:-${HOME}/.linktrend/ide-coordinator/receipts}"

case "${MAIN_PROMOTION_MODE}" in
  principal-approval|automatic) ;;
  *) echo "FAIL: unsupported main promotion mode ${MAIN_PROMOTION_MODE}" >&2; exit 1 ;;
esac


repair_task_upsert() {
  local ec
  set +e
  python3 "${SCRIPT_DIR}/repair_task.py" upsert "$@" >/dev/null
  ec=$?
  set -e
  if [ "$ec" -ne 0 ]; then
    _gh_present="${GH_TOKEN-}"
    if [ -z "$_gh_present" ]; then
      _gh_present="${GITHUB_TOKEN-}"
    fi
    if [ -n "$_gh_present" ]; then
      echo "FAIL: repair_task.py upsert failed with GitHub token present" >&2
      unset _gh_present
      return "$ec"
    fi
    unset _gh_present
    echo "WARN: repair_task.py upsert failed without GitHub token; continuing without repair task" >&2
  fi
  return 0
}


record_usage_limit_repair_task() {
  repair_task_upsert \
    --repo "${REPO}" \
    --failure-type usage_limit \
    --severity immediate \
    --workflow "main-promote" \
    --next-action "Wait for GitHub API quota; do not ACP-repair usage limits."
}


# Rate-limit backoff: on gh 403/429, retry up to 2 times with sleep (see ACTIONS-COST-CONTROLS.md).
gh_retry() {
  local attempt=1
  local max=3
  local delay=5
  local out ec
  while true; do
    set +e
    out="$("$@" 2>&1)"
    ec=$?
    set -e
    if [ "$ec" -eq 0 ]; then
      printf '%s
' "$out"
      return 0
    fi
    if printf '%s' "$out" | grep -Eq 'HTTP 403|HTTP 429|rate limit|secondary rate'; then
      if [ "$attempt" -ge "$max" ]; then
        record_usage_limit_repair_task
        printf '%s
' "$out" >&2
        return "$ec"
      fi
      echo "WARN: gh rate-limit/403/429 — retry ${attempt}/${max} after ${delay}s" >&2
      sleep "$delay"
      delay=$((delay * 2))
      attempt=$((attempt + 1))
      continue
    fi
    printf '%s
' "$out" >&2
    return "$ec"
  done
}


write_out() {
  python3 "${SCRIPT_DIR}/write_outcome.py" --file "${OUTCOME}" --status "$1" --detail "$2"
}

receipt_identity_args() {
  local raw dep
  RECEIPT_IDENTITY_ARGS=()
  raw="$(printf '%s' "${RECEIPT_DEPENDENCY_FILES}" | tr ',' '\n')"
  while IFS= read -r dep; do
    [ -n "${dep}" ] && RECEIPT_IDENTITY_ARGS+=(--dependency "${dep}")
  done <<< "${raw}"
  return 0
}

receipt_profile_args() {
  local candidate_repo="$1"
  RECEIPT_PROFILE_ARGS=()
  if [ -f "${candidate_repo}/.github/linktrend-delivery-mode.json" ]; then
    RECEIPT_PROFILE_ARGS=(--profile-file ".github/linktrend-delivery-mode.json")
  elif [ -f "${candidate_repo}/.ide-development/config/delivery.json" ]; then
    RECEIPT_PROFILE_ARGS=(--profile-file ".ide-development/config/delivery.json")
  else
    echo "FAIL: delivery profile configuration is unavailable in promotion candidate" >&2
    return 1
  fi
  return 0
}

verify_receipt_before_mutation() {
  local candidate_repo="$1"
  local profile="${2:-full}"
  if [ -z "${RECEIPT_PATH}" ] || [ ! -f "${RECEIPT_PATH}" ]; then
    write_out "blocked" "promotion receipt missing; protected main was not mutated"
    return 1
  fi
  receipt_identity_args
  receipt_profile_args "${candidate_repo}"
  python3 "${RECEIPT_GATE}" verify \
    --receipt "${RECEIPT_PATH}" \
    --repo "${candidate_repo}" \
    --profile "${profile}" \
    --gate full-gate \
    ${RECEIPT_PROFILE_ARGS[@]+"${RECEIPT_PROFILE_ARGS[@]}"} \
    ${RECEIPT_IDENTITY_ARGS[@]+"${RECEIPT_IDENTITY_ARGS[@]}"}
}

if [ -z "${TOKEN}" ] || [ "${AUTOMATION_TOKEN_SOURCE:-}" != "github_token" ]; then
  # automation token unavailable: local outcome only — no repair/check mutation via workflow token.
  write_out "automation_credentials_blocked" "main promote requires normal GitHub automation token"
  exit 0
fi

git fetch origin main staging

STG_SHA="$(git rev-parse origin/staging)"
MAIN_SHA="$(git rev-parse origin/main)"

marker_json() {
  python3 -c 'import json,sys; print(json.dumps({
    "schemaVersion": 1,
    "stage": "main",
    "sourceBranch": "staging",
    "targetBranch": "main",
    "sourceSha": sys.argv[1],
    "targetSha": sys.argv[2],
    "candidateHead": sys.argv[3],
    "promoteBranch": sys.argv[4],
    "fullRunId": int(sys.argv[5]),
  }, separators=(",", ":")))' "$1" "$2" "$3" "$4" "$5"
}

extract_marker() {
  python3 -c '
import json,re,sys
body=sys.stdin.read()
m=re.search(r"<!-- linktrend-promote:\s*(\{.*?\})\s*-->", body, re.S)
if not m: raise SystemExit(1)
print(m.group(1))
' <<<"$1"
}

if [ "${MODE}" = "reevaluate" ]; then
  if [ -z "${PROMOTE_PR_NUMBER}" ]; then
    write_out "failed" "reevaluate requires PROMOTE_PR_NUMBER"
    exit 1
  fi
  write_out "waiting" "main reevaluate observes PR #${PROMOTE_PR_NUMBER}; merge requires approve-merge"
  exit 0
fi

if [ "${MODE}" = "package" ]; then
  if git merge-base --is-ancestor origin/staging origin/main; then
    write_out "skipped" "staging already in main"
    exit 0
  fi
  SHORT="$(echo "${STG_SHA}" | cut -c1-12)"
  PROMOTE_BRANCH="promote/main/${SHORT}"

  existing_json="$(gh_retry gh pr list --base main --state open \
    --json number,body,headRefName,headRefOid,baseRefName,state,isCrossRepository,headRepository)"
  reuse_json="$(printf '%s\n' "${existing_json}" | python3 "${SCRIPT_DIR}/main_approve_package_reuse.py" \
    --expected-source "${STG_SHA}" \
    --expected-target "${MAIN_SHA}" \
    --expected-branch "${PROMOTE_BRANCH}" \
    --repository "${REPO}")"
  reuse_action="$(printf '%s\n' "${reuse_json}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("action",""))')"
  reuse_pr="$(printf '%s\n' "${reuse_json}" | python3 -c 'import json,sys; v=json.load(sys.stdin).get("pr"); print(v if v is not None else "")')"
  reuse_reason="$(printf '%s\n' "${reuse_json}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("reason",""))')"
  if [ "${reuse_action}" = "reuse" ] && [ -n "${reuse_pr}" ]; then
    write_out "packaged" "main promote PR #${reuse_pr} already open and valid for reuse (open/same-repo/base/branch/marker/head)"
    exit 0
  fi
  if [ "${reuse_action}" = "repackage" ]; then
    python3 "${SCRIPT_DIR}/repair_task.py" upsert \
      --repo "${REPO}" --failure-type promotion_conflict \
      --stage main \
      --source-branch staging --target-branch main \
      --branch "staging->main" \
      --head-sha "${STG_SHA}" --base-sha "${MAIN_SHA}" \
      --pr "${reuse_pr:-0}" --status conflict_blocked \
      --next-action "Existing main promote package invalid (${reuse_reason}); close/repair and repackage; do not silently reuse or overwrite." \
      >/dev/null || true
    write_out "blocked" "existing main promote package invalid (${reuse_reason}); requires repackage"
    exit 0
  fi

  START_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
  START_SHA="$(git rev-parse HEAD)"
  WT="$(mktemp -d "${TMPDIR:-/tmp}/main-promote.XXXXXX")"
  RECEIPT_IDENTITY_FILE="$(mktemp "${TMPDIR:-/tmp}/main-identity.XXXXXX.json")"
  cleanup() {
    git worktree remove --force "${WT}" >/dev/null 2>&1 || rm -rf "${WT}"
    rm -f "${RECEIPT_IDENTITY_FILE}"
  }
  trap cleanup EXIT
  git worktree add --detach "${WT}" origin/main >/dev/null
  git -C "${WT}" checkout -B "${PROMOTE_BRANCH}" >/dev/null
  if ! git -C "${WT}" merge --no-ff origin/staging -m "chore(promote): merge staging ${SHORT} into main candidate"; then
    git -C "${WT}" merge --abort 2>/dev/null || true
    python3 "${SCRIPT_DIR}/repair_task.py" upsert \
      --repo "${REPO}" --failure-type promotion_conflict \
      --stage main \
      --source-branch staging --target-branch main \
      --branch "staging->main" \
      --head-sha "${STG_SHA}" --base-sha "${MAIN_SHA}" \
      --status conflict_blocked \
      --next-action "Repair promote/main/* from main@${MAIN_SHA}." \
      >/dev/null || true
    write_out "blocked" "conflict building main candidate"
    exit 0
  fi
  CANDIDATE="$(git -C "${WT}" rev-parse HEAD)"
  CANDIDATE_TREE="$(git -C "${WT}" rev-parse HEAD^{tree})"
  if [ -z "${RECEIPT_PATH}" ]; then
    RECEIPT_PATH="${COORDINATOR_RECEIPT_ROOT}/${CANDIDATE_TREE}-full-gate.json"
  fi
receipt_identity_args
receipt_profile_args "${WT}"
python3 "${SCRIPT_DIR}/gate_receipt.py" identity \
  --repo "${WT}" --profile full \
  ${RECEIPT_PROFILE_ARGS[@]+"${RECEIPT_PROFILE_ARGS[@]}"} \
  ${RECEIPT_IDENTITY_ARGS[@]+"${RECEIPT_IDENTITY_ARGS[@]}"} >"${RECEIPT_IDENTITY_FILE}"
  verify_receipt_before_mutation "${WT}" full || exit 0
  git -C "${WT}" push -u origin "HEAD:refs/heads/${PROMOTE_BRANCH}"
  FULL_RUN_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["workflowRunId"])' "${RECEIPT_PATH}")"
  MARKER="$(marker_json "${STG_SHA}" "${MAIN_SHA}" "${CANDIDATE}" "${PROMOTE_BRANCH}" "${FULL_RUN_ID}")"
  RECEIPT_DIGEST="$(python3 - "${RECEIPT_PATH}" <<'PY'
import hashlib
import json
import sys
value = json.loads(open(sys.argv[1], encoding="utf-8").read())
payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
print("sha256:" + hashlib.sha256(payload).hexdigest())
PY
)"
  MARKER="$(echo "${MARKER}" | jq --arg digest "${RECEIPT_DIGEST}" --arg mode "${MAIN_PROMOTION_MODE}" '. + {receiptDigest:$digest,approvalMode:$mode}')"
  BODY="$(cat <<EOF
## Main promote package (awaiting Principal Approve)

Approve must bind:
- expected_sha (staging source) = \`${STG_SHA}\`
- expected_main_sha (prior main target) = \`${MAIN_SHA}\`
- expected_promote_head = \`${CANDIDATE}\`

<!-- linktrend-promote: ${MARKER} -->
EOF
)"
  URL="$(gh_retry gh pr create --base main --head "${PROMOTE_BRANCH}" \
    --title "chore(promote): staging → main (awaiting Approve ${SHORT})" \
    --body "${BODY}")"
  PR="$(gh_retry gh pr view "${URL}" --json number --jq .number)"
  write_out "packaged" "opened main promote PR #${PR} head ${CANDIDATE}"
  [ "$(git rev-parse --abbrev-ref HEAD)" = "${START_BRANCH}" ]
  [ "$(git rev-parse HEAD)" = "${START_SHA}" ]
  exit 0
fi

if [ "${MODE}" = "automatic" ]; then
  MAIN_PROMOTION_MODE="automatic"
  MODE="approve-merge"
fi
if [ "${MODE}" != "approve-merge" ]; then
  write_out "failed" "unknown MODE=${MODE}"
  exit 1
fi

if [ -z "${EXPECTED_STAGING_SHA}" ] || [ -z "${EXPECTED_PROMOTE_HEAD}" ] || [ -z "${EXPECTED_MAIN_SHA}" ]; then
  write_out "failed" "approve-merge requires both EXPECTED_STAGING_SHA and EXPECTED_PROMOTE_HEAD plus EXPECTED_MAIN_SHA"
  exit 1
fi

if [ "${EXPECTED_STAGING_SHA}" != "${STG_SHA}" ]; then
  write_out "failed" "expected staging ${EXPECTED_STAGING_SHA} != tip ${STG_SHA}"
  exit 1
fi
if [ "${EXPECTED_MAIN_SHA}" != "${MAIN_SHA}" ]; then
  write_out "failed" "expected main target ${EXPECTED_MAIN_SHA} != tip ${MAIN_SHA} (target advanced)"
  exit 1
fi

if [ -z "${PROMOTE_PR_NUMBER}" ]; then
  # locate by marker
  PROMOTE_PR_NUMBER="$(gh pr list --base main --state open --json number,body \
    | python3 -c '
import json,re,sys
stg,main=sys.argv[1],sys.argv[2]
for r in json.load(sys.stdin):
    m=re.search(r"<!-- linktrend-promote:\s*(\{.*?\})\s*-->", r.get("body") or "", re.S)
    if not m: continue
    meta=json.loads(m.group(1))
    if meta.get("sourceSha")==stg and meta.get("targetSha")==main:
        print(r["number"]); break
' "${STG_SHA}" "${MAIN_SHA}" || true)"
fi
if [ -z "${PROMOTE_PR_NUMBER}" ]; then
  write_out "failed" "no open main promote PR for bound SHAs"
  exit 1
fi

meta="$(gh pr view "${PROMOTE_PR_NUMBER}" --json number,baseRefName,headRefName,headRefOid,body,state)"
echo "${meta}" | jq -e '.state=="OPEN" and .baseRefName=="main"' >/dev/null \
  || { write_out "failed" "PR not open into main"; exit 1; }
head_branch="$(echo "${meta}" | jq -r .headRefName)"
head_sha="$(echo "${meta}" | jq -r .headRefOid)"
body="$(echo "${meta}" | jq -r .body)"
is_main_promote_branch "${head_branch}" || { write_out "failed" "not promote/main/*"; exit 1; }

if [ "${head_sha}" != "${EXPECTED_PROMOTE_HEAD}" ]; then
  write_out "failed" "promote head ${head_sha} != expected ${EXPECTED_PROMOTE_HEAD}"
  exit 1
fi

marker="$(extract_marker "${body}")" || { write_out "failed" "missing promote marker"; exit 1; }
echo "${marker}" | jq -e --arg s "${STG_SHA}" --arg m "${MAIN_SHA}" --arg c "${EXPECTED_PROMOTE_HEAD}" \
  '.sourceSha==$s and .targetSha==$m and .candidateHead==$c' >/dev/null \
  || { write_out "failed" "marker SHA binding mismatch"; exit 1; }

if [ -z "${CANDIDATE_IDENTITY_PATH:-}" ] || [ ! -f "${CANDIDATE_IDENTITY_PATH}" ]; then
  IDENTITY_WORKTREE="$(mktemp -d "${TMPDIR:-/tmp}/main-identity.XXXXXX")"
  IDENTITY_FILE="$(mktemp "${TMPDIR:-/tmp}/main-identity.XXXXXX.json")"
  git fetch origin "refs/heads/${head_branch}:refs/remotes/origin/${head_branch}"
  if [ "$(git rev-parse "origin/${head_branch}")" != "${EXPECTED_PROMOTE_HEAD}" ]; then
    rm -rf "${IDENTITY_WORKTREE}"
    rm -f "${IDENTITY_FILE}"
    write_out "failed" "fetched promote branch does not match expected head"
    exit 1
  fi
  git worktree add --detach "${IDENTITY_WORKTREE}" "origin/${head_branch}" >/dev/null
  receipt_identity_args
  python3 "${SCRIPT_DIR}/gate_receipt.py" identity \
    --repo "${IDENTITY_WORKTREE}" --profile full \
    ${RECEIPT_IDENTITY_ARGS[@]+"${RECEIPT_IDENTITY_ARGS[@]}"} >"${IDENTITY_FILE}"
  git worktree remove --force "${IDENTITY_WORKTREE}" >/dev/null 2>&1 || rm -rf "${IDENTITY_WORKTREE}"
  CANDIDATE_IDENTITY_PATH="${IDENTITY_FILE}"
fi
if [ -z "${RECEIPT_PATH}" ]; then
  CANDIDATE_TREE="$(python3 - "${CANDIDATE_IDENTITY_PATH}" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["gitTreeSha"])
PY
)"
  RECEIPT_PATH="${COORDINATOR_RECEIPT_ROOT}/${CANDIDATE_TREE}-full-gate.json"
fi
if [ ! -f "${RECEIPT_PATH}" ]; then
  [ -z "${IDENTITY_FILE:-}" ] || rm -f "${IDENTITY_FILE}"
  write_out "blocked" "promotion receipt missing; principal approval cannot mutate main"
  exit 1
fi
python3 "${RECEIPT_GATE}" verify \
  --receipt "${RECEIPT_PATH}" \
  --identity "${CANDIDATE_IDENTITY_PATH}" \
  --profile full --gate full-gate || {
    [ -z "${IDENTITY_FILE:-}" ] || rm -f "${IDENTITY_FILE}"
    write_out "blocked" "promotion receipt identity does not match main candidate"
    exit 1
  }
[ -z "${IDENTITY_FILE:-}" ] || rm -f "${IDENTITY_FILE}"

marker_receipt="$(echo "${marker}" | jq -r '.receiptDigest // empty')"
marker_mode="$(echo "${marker}" | jq -r '.approvalMode // "principal-approval"')"
actual_receipt="$(python3 - "${RECEIPT_PATH}" <<'PY'
import hashlib
import json
import sys
value = json.loads(open(sys.argv[1], encoding="utf-8").read())
payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
print("sha256:" + hashlib.sha256(payload).hexdigest())
PY
)"
[ -n "${marker_receipt}" ] && [ "${marker_receipt}" = "${actual_receipt}" ] \
  || { write_out "failed" "stale main approval receipt binding"; exit 1; }
[ "${marker_mode}" = "${MAIN_PROMOTION_MODE}" ] \
  || { write_out "failed" "main approval mode is stale or mismatched"; exit 1; }

if ! python3 "${SCRIPT_DIR}/wait_named_gate.py" \
    --pr "${PROMOTE_PR_NUMBER}" \
    --required "${RELEASE_GATE_CHECKS}" \
    --timeout-seconds "${GATE_WAIT_SECONDS:-300}" \
    --poll-seconds 15 \
    --report-file release-gate-wait.json; then
  write_out "blocked" "release-gate not green"
  exit 1
fi

head_now="$(gh pr view "${PROMOTE_PR_NUMBER}" --json headRefOid --jq .headRefOid)"
if [ "${head_now}" != "${EXPECTED_PROMOTE_HEAD}" ]; then
  write_out "failed" "head changed during gate wait"
  exit 1
fi

git fetch origin main staging
if [ "$(git rev-parse origin/staging)" != "${EXPECTED_STAGING_SHA}" ] \
  || [ "$(git rev-parse origin/main)" != "${EXPECTED_MAIN_SHA}" ]; then
  write_out "failed" "source/target moved during evaluation"
  exit 1
fi

if gh_retry gh pr merge "${PROMOTE_PR_NUMBER}" --merge; then
  write_out "merged" "merged main promote PR #${PROMOTE_PR_NUMBER}"
  exit 0
fi
write_out "failed" "merge failed — no direct push"
exit 1
