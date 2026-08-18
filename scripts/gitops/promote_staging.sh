#!/usr/bin/env bash
# Promote development → staging via temporary promote/staging/* branch + PR.
#
# MODE:
#   build          — schedule/manual only
#   reevaluate     — exact PR (+ optional expected head); never rebuilds
#   repair-resume  — same as reevaluate
#
# Candidate marker in PR body (machine-readable):
#   <!-- linktrend-promote: {...json...} -->
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

MODE="${MODE:-build}"
STAGING_GATE_CHECKS="${STAGING_GATE_CHECKS:-Verify IDE Development}"
TIMEZONE_LABEL="${TIMEZONE_LABEL:-Asia/Taipei}"
REPO="${GH_REPO:-${GITHUB_REPOSITORY:-}}"
TOKEN="${AUTOMATION_TOKEN:-}"
export GH_TOKEN="${TOKEN}"
export GITHUB_TOKEN="${TOKEN}"

PROMOTE_PR_NUMBER="${PROMOTE_PR_NUMBER:-}"
EXPECTED_PROMOTE_HEAD="${EXPECTED_PROMOTE_HEAD:-}"

OUTCOME="${OUTCOME_FILE:-gitops-outcome.json}"
RECEIPT_GATE="${SCRIPT_DIR}/promotion_receipt_gate.py"
RECEIPT_PATH="${RECEIPT_PATH:-${LINKTREND_RECEIPT_PATH:-}}"
RECEIPT_DEPENDENCY_FILES="${RECEIPT_DEPENDENCY_FILES:-}"
RECEIPT_IDENTITY_ARGS=()
RECEIPT_PROFILE_ARGS=()
COORDINATOR_RECEIPT_ROOT="${LINKTREND_COORDINATOR_RECEIPT_ROOT:-${HOME}/.linktrend/ide-coordinator/receipts}"


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
    --workflow "staging-promote" \
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
    write_out "blocked" "promotion receipt missing; protected staging was not mutated"
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
  write_out "automation_credentials_blocked" "staging promote requires normal GitHub automation token"
  exit 0
fi

# Fail closed on fetch
git fetch origin development staging

DEV_SHA="$(git rev-parse origin/development)"
STG_SHA="$(git rev-parse origin/staging)"

marker_json() {
  python3 -c 'import json,sys; print(json.dumps({
    "schemaVersion": 1,
    "stage": "staging",
    "sourceBranch": "development",
    "targetBranch": "staging",
    "sourceSha": sys.argv[1],
    "targetSha": sys.argv[2],
    "candidateHead": sys.argv[3],
    "promoteBranch": sys.argv[4],
    "fullRunId": int(sys.argv[5]),
  }, separators=(",", ":")))' "$1" "$2" "$3" "$4" "$5"
}

extract_marker() {
  local body="$1"
  python3 -c '
import json,re,sys
body=sys.stdin.read()
m=re.search(r"<!-- linktrend-promote:\s*(\{.*?\})\s*-->", body, re.S)
if not m:
    raise SystemExit(1)
print(m.group(1))
' <<<"${body}"
}

reevaluate_exact() {
  local pr="$1"
  local meta body marker src tgt cand base head_branch head_sha mergeable

  meta="$(gh_retry gh pr view "${pr}" --json number,baseRefName,headRefName,headRefOid,body,mergeable,state)"
  echo "${meta}" | jq -e '.state=="OPEN" and .baseRefName=="staging"' >/dev/null \
    || { write_out "skipped" "PR #${pr} not open into staging"; exit 0; }

  head_branch="$(echo "${meta}" | jq -r .headRefName)"
  head_sha="$(echo "${meta}" | jq -r .headRefOid)"
  body="$(echo "${meta}" | jq -r .body)"
  mergeable="$(echo "${meta}" | jq -r .mergeable)"

  if ! is_staging_promote_branch "${head_branch}"; then
    write_out "blocked" "PR #${pr} head branch not promote/staging/*"
    exit 0
  fi

  if [ -n "${EXPECTED_PROMOTE_HEAD}" ] && [ "${EXPECTED_PROMOTE_HEAD}" != "${head_sha}" ]; then
    write_out "skipped" "stale event: expected head ${EXPECTED_PROMOTE_HEAD} != ${head_sha}"
    exit 0
  fi

  if ! marker="$(extract_marker "${body}")"; then
    write_out "blocked" "PR #${pr} missing linktrend-promote marker"
    exit 0
  fi
  src="$(echo "${marker}" | jq -r .sourceSha)"
  tgt="$(echo "${marker}" | jq -r .targetSha)"
  cand="$(echo "${marker}" | jq -r .candidateHead)"

  # Live target tip — if staging advanced, old gate is invalid
  live_tgt="$(git rev-parse origin/staging)"
  if [ "${tgt}" != "${live_tgt}" ]; then
    write_out "blocked" "target staging advanced (${tgt} -> ${live_tgt}); old candidate invalidated"
    python3 "${SCRIPT_DIR}/repair_task.py" upsert \
      --repo "${REPO}" --failure-type promotion_conflict \
      --stage staging \
      --source-branch development --target-branch staging \
      --branch "development->staging" \
      --head-sha "${src}" --base-sha "${live_tgt}" \
      --pr "${pr}" --status conflict_blocked \
      --next-action "Target advanced; build a new candidate from current staging tip." \
      >/dev/null || true
    exit 0
  fi

  if [ "${cand}" != "${head_sha}" ]; then
    write_out "blocked" "marker candidateHead ${cand} != PR head ${head_sha}"
    exit 0
  fi

  # Reread head immediately before gate/merge decisions
  head_now="$(gh_retry gh pr view "${pr}" --json headRefOid --jq .headRefOid)"
  if [ "${head_now}" != "${head_sha}" ]; then
    write_out "skipped" "head changed before gate ${head_now}"
    exit 0
  fi

  if [ "${mergeable}" = "CONFLICTING" ]; then
    python3 "${SCRIPT_DIR}/repair_task.py" upsert \
      --repo "${REPO}" --failure-type promotion_conflict \
      --stage staging \
      --source-branch development --target-branch staging \
      --branch "development->staging" \
      --head-sha "${src}" --base-sha "${tgt}" \
      --pr "${pr}" --status conflict_blocked \
      --next-action "Repair existing promote PR #${pr} without replacing branch tip randomly." \
      >/dev/null || true
    write_out "blocked" "conflict_blocked on PR #${pr}"
    exit 0
  fi

  if ! python3 "${SCRIPT_DIR}/wait_named_gate.py" \
      --pr "${pr}" \
      --required "${STAGING_GATE_CHECKS}" \
      --timeout-seconds "${GATE_WAIT_SECONDS:-120}" \
      --poll-seconds 10 \
      --report-file staging-gate-wait.json; then
    write_out "waiting" "staging-gate not green on PR #${pr} head ${head_sha}"
    exit 0
  fi

  head_now="$(gh_retry gh pr view "${pr}" --json headRefOid --jq .headRefOid)"
  if [ "${head_now}" != "${head_sha}" ]; then
    write_out "skipped" "head changed during gate wait"
    exit 0
  fi

  # Re-validate target tip unchanged
  git fetch origin staging
  live_tgt="$(git rev-parse origin/staging)"
  if [ "${tgt}" != "${live_tgt}" ]; then
    write_out "blocked" "staging moved during gate evaluation"
    exit 0
  fi

  if gh_retry gh pr merge "${pr}" --merge; then
    write_out "merged" "merged staging promote PR #${pr} at ${head_sha}"
    exit 0
  fi
  write_out "blocked" "merge failed for PR #${pr}"
  exit 0
}

if [ "${MODE}" = "reevaluate" ] || [ "${MODE}" = "repair-resume" ]; then
  if [ -z "${PROMOTE_PR_NUMBER}" ]; then
    write_out "failed" "reevaluate requires PROMOTE_PR_NUMBER"
    exit 1
  fi
  reevaluate_exact "${PROMOTE_PR_NUMBER}"
fi

if [ "${MODE}" != "build" ]; then
  write_out "failed" "unknown MODE=${MODE}"
  exit 1
fi

if git merge-base --is-ancestor origin/development origin/staging; then
  write_out "skipped" "development already contained in staging"
  exit 0
fi

SHORT="$(echo "${DEV_SHA}" | cut -c1-12)"
PROMOTE_BRANCH="promote/staging/${SHORT}"

# If open PR already exists for this exact source/target pair, reevaluate it — do not rebuild
existing_json="$(gh_retry gh pr list --base staging --state open --json number,headRefName,headRefOid,body)"
existing_prs="$(echo "${existing_json}" | python3 -c '
import json,re,sys
dev,stg=sys.argv[1],sys.argv[2]
for r in json.load(sys.stdin):
    m=re.search(r"<!-- linktrend-promote:\s*(\{.*?\})\s*-->", r.get("body") or "", re.S)
    if not m: continue
    meta=json.loads(m.group(1))
    if meta.get("sourceSha")==dev and meta.get("targetSha")==stg:
        print(r["number"])
' "${DEV_SHA}" "${STG_SHA}" || true)"
existing_count="$(printf '%s\n' "${existing_prs}" | sed '/^$/d' | wc -l | tr -d ' ')"
if [ "${existing_count}" -gt 1 ]; then
  write_out "blocked" "duplicate staging promotion candidates: ${existing_prs//$'\n'/, }"
  exit 0
fi
if [ "${existing_count}" -eq 1 ]; then
  PROMOTE_PR_NUMBER="$(printf '%s\n' "${existing_prs}" | sed -n '1p')"
  MODE=reevaluate
  reevaluate_exact "${PROMOTE_PR_NUMBER}"
fi

START_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
START_SHA="$(git rev-parse HEAD)"
WT="$(mktemp -d "${TMPDIR:-/tmp}/stg-promote.XXXXXX")"
RECEIPT_IDENTITY_FILE="$(mktemp "${TMPDIR:-/tmp}/staging-identity.XXXXXX.json")"
cleanup() {
  git worktree remove --force "${WT}" >/dev/null 2>&1 || rm -rf "${WT}"
  rm -f "${RECEIPT_IDENTITY_FILE}"
}
trap cleanup EXIT

git worktree add --detach "${WT}" origin/staging >/dev/null
git -C "${WT}" checkout -B "${PROMOTE_BRANCH}" >/dev/null

if ! git -C "${WT}" merge --no-ff origin/development -m "chore(promote): merge development ${SHORT} into staging candidate"; then
  git -C "${WT}" merge --abort 2>/dev/null || true
  python3 "${SCRIPT_DIR}/repair_task.py" upsert \
    --repo "${REPO}" --failure-type promotion_conflict \
    --stage staging \
    --source-branch development --target-branch staging \
    --branch "development->staging" \
    --head-sha "${DEV_SHA}" --base-sha "${STG_SHA}" \
    --status conflict_blocked \
    --next-action "Repair merge onto promote/staging/* from staging@${STG_SHA}." \
    >/dev/null || true
  write_out "blocked" "conflict building staging candidate; protected branches unchanged"
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
MARKER="$(marker_json "${DEV_SHA}" "${STG_SHA}" "${CANDIDATE}" "${PROMOTE_BRANCH}" "${FULL_RUN_ID}")"
BODY="$(cat <<EOF
## Staging promote candidate

Temporary promotion branch (never a direct push to staging).

- Schedule window: Tue/Fri 10:00 ${TIMEZONE_LABEL}
- staging-gate must pass on **this PR head** (combined result).

<!-- linktrend-promote: ${MARKER} -->
EOF
)"

URL="$(gh_retry gh pr create --base staging --head "${PROMOTE_BRANCH}" \
  --title "chore(promote): development → staging (${SHORT})" \
  --body "${BODY}")"
PR="$(gh_retry gh pr view "${URL}" --json number --jq .number)"
write_out "packaged" "opened staging promote PR #${PR} head ${CANDIDATE}"
[ "$(git rev-parse --abbrev-ref HEAD)" = "${START_BRANCH}" ]
[ "$(git rev-parse HEAD)" = "${START_SHA}" ]
exit 0
