#!/usr/bin/env bash
# Safe cleanup for merged/abandoned work + promotion branches.
# Default: dry-run. Never deletes by name alone. Preserves caller checkout.
#
# Usage:
#   cleanup-merged-branches.sh [--apply] [--remote] [--local] [--repo OWNER/NAME]
# Preserve (KEEP before delete) comes from scripts/gitops/cleanup_controls.py
#   (export-preserve, with deterministic --repo). Overlays:
#   .linktrend/cleanup-preserve.json and/or LINKTREND_CLEANUP_PRESERVE=branch,...
#   Set "defaults": false in an overlay to disable committed defaults via that
#   helper. Fail-closed: if preserve PR heads cannot be resolved
#   (preserveResolutionOk=false / unresolvedPrNumbers), never delete candidates.
# Explicit --repo OWNER/NAME is highest precedence for cleanup scope; empty or
#   invalid values fail closed (no fallthrough to env/remotes/implicit gh).
# --apply deletes branches only; never closes PRs/issues.
set -euo pipefail

APPLY=0
DO_REMOTE=1
DO_LOCAL=1
ROOT=""
PRESERVE_POLICY='{"branches":[],"issueNumbers":[],"prHeads":[]}'
CLEANUP_REPO=""
EXPLICIT_CLEANUP_REPO=""
EXPLICIT_REPO_SET=0
PRESERVE_UNRESOLVED=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1; shift ;;
    --remote) DO_REMOTE=1; DO_LOCAL=0; shift ;;
    --local) DO_LOCAL=1; DO_REMOTE=0; shift ;;
    --repo)
      EXPLICIT_REPO_SET=1
      if [ $# -lt 2 ]; then
        echo "FAIL: --repo requires OWNER/NAME" >&2
        exit 1
      fi
      EXPLICIT_CLEANUP_REPO="$2"
      shift 2
      ;;
    --repo-root) ROOT="$2"; shift 2 ;;
    -h|--help) sed -n '1,30p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$ROOT" ]; then
  ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "FAIL: not a git repository" >&2
    exit 1
  }
fi
cd "$ROOT"
# shellcheck source=gitops/work-branch-allowlist.sh
source "${SCRIPT_DIR}/gitops/work-branch-allowlist.sh"

START_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
START_SHA="$(git rev-parse HEAD)"
START_STATUS="$(git status --porcelain)"

MODE="dry-run"
[ "$APPLY" -eq 1 ] && MODE="apply"
echo "cleanup mode=${MODE} remote=${DO_REMOTE} local=${DO_LOCAL}"

is_protected_permanent() {
  case "$1" in
    main|staging|development|HEAD) return 0 ;;
    *) return 1 ;;
  esac
}

decide() { echo "$1: $2 — $3"; }

# True when slug matches Python REPO_SLUG_RE (non-empty owner AND name).
# Same shape as cleanup_controls.REPO_SLUG_RE / normalize_caller_repo.
_cleanup_repo_slug_ok() {
  [[ "$1" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]
}

# Resolve owner/repo for export-preserve gh resolution (deterministic order).
# Precedence: explicit --repo (authoritative) → GITHUB_REPOSITORY → GH_REPO →
# (ambiguous origin+upstream fail-closed) → gh repo view → origin URL parse.
# Empty/invalid explicit --repo fails closed (exit 1; no env/remote fallthrough).
# Ambiguity without --repo leaves CLEANUP_REPO empty so export-preserve runs
# without --repo and Python fail-closes.
resolve_cleanup_repo() {
  CLEANUP_REPO=""
  if [ "${EXPLICIT_REPO_SET:-0}" -eq 1 ]; then
    if [ -z "$EXPLICIT_CLEANUP_REPO" ] || ! _cleanup_repo_slug_ok "$EXPLICIT_CLEANUP_REPO"; then
      echo "FAIL: empty or invalid --repo '${EXPLICIT_CLEANUP_REPO}' (expected OWNER/NAME)" >&2
      exit 1
    fi
    CLEANUP_REPO="$EXPLICIT_CLEANUP_REPO"
    return 0
  fi
  if [ -n "${GITHUB_REPOSITORY:-}" ] && _cleanup_repo_slug_ok "${GITHUB_REPOSITORY}"; then
    CLEANUP_REPO="$GITHUB_REPOSITORY"
    return 0
  fi
  if [ -n "${GH_REPO:-}" ] && _cleanup_repo_slug_ok "${GH_REPO}"; then
    CLEANUP_REPO="$GH_REPO"
    return 0
  fi
  # Both remotes present: do not call gh repo view or parse origin.
  # Leave CLEANUP_REPO empty so load_preserve_policy calls export-preserve without --repo.
  if git remote get-url origin >/dev/null 2>&1 \
    && git remote get-url upstream >/dev/null 2>&1; then
    CLEANUP_REPO=""
    return 0
  fi
  local viewed
  viewed="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)"
  if _cleanup_repo_slug_ok "$viewed"; then
    CLEANUP_REPO="$viewed"
    return 0
  fi
  local url
  url="$(git remote get-url origin 2>/dev/null || true)"
  if [ -n "$url" ]; then
    viewed="$(python3 -c '
import re, sys
u = sys.argv[1].strip()
if u.endswith(".git"):
    u = u[:-4]
m = re.search(r"github\.com[:/]([^/]+)/([^/]+)", u)
print(f"{m.group(1)}/{m.group(2)}" if m else "")
' "$url" 2>/dev/null || true)"
    if _cleanup_repo_slug_ok "$viewed"; then
      CLEANUP_REPO="$viewed"
    fi
  fi
}

# Load preserve policy via shared helper (scripts/gitops/cleanup_controls.py).
# Shape consumed by is_preserved_branch: branches / issueNumbers / prHeads.
# Also consumes preserveResolutionOk / unresolvedPrNumbers for fail-closed gate.
# "defaults": false in an overlay disables committed defaults inside that helper.
load_preserve_policy() {
  local export_rc
  resolve_cleanup_repo
  set +e
  if [ -n "$CLEANUP_REPO" ]; then
    PRESERVE_POLICY="$(
      python3 "${SCRIPT_DIR}/gitops/cleanup_controls.py" export-preserve --repo "$CLEANUP_REPO" 2>/dev/null
    )"
  else
    PRESERVE_POLICY="$(
      python3 "${SCRIPT_DIR}/gitops/cleanup_controls.py" export-preserve 2>/dev/null
    )"
  fi
  export_rc=$?
  set -e

  if ! python3 -c 'import json, sys; json.loads(sys.argv[1])' "$PRESERVE_POLICY" 2>/dev/null; then
    echo "FAIL: export-preserve returned invalid JSON (rc=${export_rc})" >&2
    exit 1
  fi

  PRESERVE_UNRESOLVED=0
  # Fail-closed when exporter reports unresolved preserve PR heads
  # (preserveResolutionOk=false and/or unresolvedPrNumbers non-empty).
  # Python may also exit non-zero in that case; JSON fields are authoritative.
  if python3 -c '
import json, sys
policy = json.loads(sys.argv[1])
ok = policy.get("preserveResolutionOk")
unresolved = policy.get("unresolvedPrNumbers") or []
if ok is False or unresolved:
    raise SystemExit(0)
raise SystemExit(1)
' "$PRESERVE_POLICY"; then
    PRESERVE_UNRESOLVED=1
  fi
}

is_preserved_branch() {
  local branch="$1"
  # Issue-number regex must match cleanup_controls.ISSUE_BRANCH_RE
  # (^issue/(\d+)(?:-|$)) so bare issue/<n> and issue/<n>-slug both preserve.
  python3 -c '
import json, re, sys
branch = sys.argv[1]
policy = json.loads(sys.argv[2])
if branch in (policy.get("branches") or []):
    raise SystemExit(0)
if branch in (policy.get("prHeads") or []):
    raise SystemExit(0)
m = re.match(r"^issue/(\d+)(?:-|$)", branch)
if m and int(m.group(1)) in (policy.get("issueNumbers") or []):
    raise SystemExit(0)
raise SystemExit(1)
' "$branch" "$PRESERVE_POLICY"
}

pr_evidence_for_branch() {
  # prints: OPEN|MERGED|ABANDONED|NONE <headOid or empty>
  # OPEN wins over any historical MERGED/CLOSED for the same head branch.
  local branch="$1"
  local json
  # Fail-closed: without a resolved repo, do not query implicit gh context
  # (cross-repo PR evidence could wrongly allow deletion).
  if [ -z "$CLEANUP_REPO" ]; then
    echo "NONE "
    return 0
  fi
  json="$(gh pr list --repo "$CLEANUP_REPO" --head "$branch" --state all --json number,state,mergedAt,labels,headRefOid --limit 10 2>/dev/null || echo '[]')"
  python3 -c '
import json,sys
rows=json.load(sys.stdin)
for r in rows:
    if r.get("state")=="OPEN":
        print("OPEN", r.get("headRefOid") or "")
        raise SystemExit
for r in rows:
    if r.get("state")=="MERGED" or r.get("mergedAt"):
        print("MERGED", r.get("headRefOid") or "")
        raise SystemExit
for r in rows:
    labels=[(l.get("name") if isinstance(l,dict) else l) for l in (r.get("labels") or [])]
    if r.get("state")=="CLOSED" and "abandoned" in labels:
        print("ABANDONED", r.get("headRefOid") or "")
        raise SystemExit
print("NONE", "")
' <<<"$json"
}

branch_tip() {
  local branch="$1"
  if git show-ref --verify --quiet "refs/remotes/origin/${branch}"; then
    git rev-parse "refs/remotes/origin/${branch}"
  elif git show-ref --verify --quiet "refs/heads/${branch}"; then
    git rev-parse "refs/heads/${branch}"
  else
    echo ""
  fi
}

worktree_path_for() {
  local branch="$1"
  git worktree list --porcelain | python3 -c '
import sys
branch=sys.argv[1]
cur=None
for line in sys.stdin.read().splitlines():
    if line.startswith("worktree "):
        cur=line.split(" ",1)[1]
    elif line==f"branch refs/heads/{branch}":
        print(cur or ""); break
' "$branch"
}

# Optional session ownership via .linktrend/session-owners.json
# { "issue/foo": { "owner": "agent-1", "active": true } }
session_owns() {
  local branch="$1"
  local f=".linktrend/session-owners.json"
  [ -f "$f" ] || return 1
  python3 -c '
import json,sys
branch=sys.argv[1]
data=json.load(open(sys.argv[2]))
row=data.get(branch) or {}
sys.exit(0 if row.get("active") else 1)
' "$branch" "$f"
}

maybe_delete_remote() {
  local branch="$1"
  local evidence head_oid tip
  if is_protected_permanent "$branch"; then
    decide "KEEP" "$branch" "protected"
    return 0
  fi
  if ! is_allowed_work_branch "$branch" && ! is_staging_promote_branch "$branch" && ! is_main_promote_branch "$branch"; then
    decide "KEEP" "$branch" "not a cleanup candidate form"
    return 0
  fi
  if is_preserved_branch "$branch"; then
    decide "KEEP" "$branch" "preserve policy"
    return 0
  fi
  if [ "${PRESERVE_UNRESOLVED:-0}" -eq 1 ]; then
    decide "KEEP" "$branch" "preserve PR head unresolved (fail-closed)"
    return 0
  fi
  read -r evidence head_oid <<<"$(pr_evidence_for_branch "$branch")"
  if [ "$evidence" = "OPEN" ]; then
    decide "KEEP" "$branch" "open PR"
    return 0
  fi
  if [ "$evidence" = "NONE" ]; then
    decide "KEEP" "$branch" "no merged/abandoned PR evidence"
    return 0
  fi
  tip="$(branch_tip "$branch")"
  if [ -n "$head_oid" ] && [ -n "$tip" ] && [ "$head_oid" != "$tip" ]; then
    decide "KEEP" "$branch" "PR head ${head_oid} != branch tip ${tip}"
    return 0
  fi
  if [ "$branch" = "$START_BRANCH" ]; then
    decide "KEEP" "$branch" "currently checked out by caller"
    return 0
  fi
  wt="$(worktree_path_for "$branch")"
  if [ -n "$wt" ]; then
    decide "KEEP" "$branch" "active worktree attached (${wt})"
    return 0
  fi
  if session_owns "$branch"; then
    decide "KEEP" "$branch" "active session ownership record"
    return 0
  fi
  if [ "$APPLY" -eq 1 ]; then
    # Prefer non-force; force only with exact merged/abandoned evidence (already verified)
    if git push origin --delete "$branch"; then
      decide "DELETED_REMOTE" "$branch" "${evidence} evidence"
    else
      decide "KEEP" "$branch" "remote delete failed"
    fi
  else
    decide "WOULD_DELETE_REMOTE" "$branch" "${evidence} evidence"
  fi
}

maybe_delete_local() {
  local branch="$1"
  local evidence head_oid tip
  if is_protected_permanent "$branch"; then
    decide "KEEP" "local:$branch" "protected"
    return 0
  fi
  if ! is_allowed_work_branch "$branch" && ! is_staging_promote_branch "$branch" && ! is_main_promote_branch "$branch"; then
    decide "KEEP" "local:$branch" "not candidate"
    return 0
  fi
  if is_preserved_branch "$branch"; then
    decide "KEEP" "local:$branch" "preserve policy"
    return 0
  fi
  if [ "${PRESERVE_UNRESOLVED:-0}" -eq 1 ]; then
    decide "KEEP" "local:$branch" "preserve PR head unresolved (fail-closed)"
    return 0
  fi
  if [ "$branch" = "$START_BRANCH" ]; then
    decide "KEEP" "local:$branch" "caller checkout"
    return 0
  fi
  wt="$(worktree_path_for "$branch")"
  # Match remote: any attached worktree is active agent checkout — never auto-remove.
  if [ -n "$wt" ]; then
    decide "KEEP" "local:$branch" "active worktree attached (${wt})"
    return 0
  fi
  if session_owns "$branch"; then
    decide "KEEP" "local:$branch" "active session ownership"
    return 0
  fi
  read -r evidence head_oid <<<"$(pr_evidence_for_branch "$branch")"
  if [ "$evidence" = "OPEN" ]; then
    decide "KEEP" "local:$branch" "open PR"
    return 0
  fi
  if [ "$evidence" = "NONE" ]; then
    decide "KEEP" "local:$branch" "PR not merged/abandoned"
    return 0
  fi
  tip="$(git rev-parse "refs/heads/${branch}" 2>/dev/null || true)"
  if [ -n "$head_oid" ] && [ -n "$tip" ] && [ "$head_oid" != "$tip" ]; then
    decide "KEEP" "local:$branch" "exact-head mismatch"
    return 0
  fi
  if [ "$APPLY" -eq 1 ]; then
    if git branch -d "$branch" 2>/dev/null; then
      decide "DELETED_LOCAL" "$branch" "${evidence}"
    else
      # force only after exact merged evidence (no worktree attached)
      git branch -D "$branch"
      decide "DELETED_LOCAL_FORCE" "$branch" "${evidence} after exact evidence"
    fi
  else
    decide "WOULD_DELETE_LOCAL" "$branch" "${evidence}"
  fi
}

load_preserve_policy

if [ "$DO_REMOTE" -eq 1 ]; then
  git fetch origin --prune >/dev/null 2>&1 || true
  while IFS= read -r ref || [ -n "$ref" ]; do
    [ -z "$ref" ] && continue
    branch="${ref#refs/heads/}"
    maybe_delete_remote "$branch"
  done < <(git for-each-ref --format='%(refname)' refs/remotes/origin | sed 's#refs/remotes/origin/#refs/heads/#' | grep -v 'refs/heads/HEAD' || true)
fi

if [ "$DO_LOCAL" -eq 1 ]; then
  while IFS= read -r branch || [ -n "$branch" ]; do
    [ -z "$branch" ] && continue
    maybe_delete_local "$branch"
  done < <(git for-each-ref --format='%(refname:short)' refs/heads)
fi

END_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
END_SHA="$(git rev-parse HEAD)"
END_STATUS="$(git status --porcelain)"
if [ "$START_BRANCH" != "$END_BRANCH" ] || [ "$START_SHA" != "$END_SHA" ] || [ "$START_STATUS" != "$END_STATUS" ]; then
  echo "FAIL: caller checkout changed during cleanup" >&2
  exit 1
fi
echo "CLEANUP_CALLER_UNCHANGED=1"
