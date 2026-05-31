#!/usr/bin/env bash
# LiNKdev dispatch v2 — gh helpers for AND label logic (GitHub Actions + local wire proof).
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  check-labels-for-dispatch.sh issue-has-all <owner/repo> <issue_number> <label> [<label>...]
  check-labels-for-dispatch.sh pr-has <owner/repo> <pr_number> <label>
  check-labels-for-dispatch.sh pr-merged-to <owner/repo> <pr_number> <base_branch>

Exit 0 when the condition holds; exit 1 otherwise.
EOF
}

require_gh() {
  command -v gh >/dev/null 2>&1 || {
    echo "check-labels: gh CLI required" >&2
    exit 1
  }
}

issue_has_all() {
  local repo="$1" issue="$2"
  shift 2
  local labels=("$@")
  local present want
  present="$(gh issue view "$issue" --repo "$repo" --json labels -q '.labels[].name')"
  for want in "${labels[@]}"; do
    if ! echo "$present" | grep -Fxq "$want"; then
      echo "check-labels: issue #${issue} missing label: ${want}" >&2
      return 1
    fi
  done
  echo "check-labels: issue #${issue} has all: ${labels[*]}"
}

pr_has() {
  local repo="$1" pr="$2" want="$3"
  if gh pr view "$pr" --repo "$repo" --json labels -q '.labels[].name' | grep -Fxq "$want"; then
    echo "check-labels: PR #${pr} has ${want}"
    return 0
  fi
  echo "check-labels: PR #${pr} missing label: ${want}" >&2
  return 1
}

pr_merged_to() {
  local repo="$1" pr="$2" base="$3"
  local merged base_ref
  merged="$(gh pr view "$pr" --repo "$repo" --json merged -q '.merged')"
  base_ref="$(gh pr view "$pr" --repo "$repo" --json baseRefName -q '.baseRefName')"
  if [[ "$merged" != "true" ]]; then
    echo "check-labels: PR #${pr} not merged" >&2
    return 1
  fi
  if [[ "$base_ref" != "$base" ]]; then
    echo "check-labels: PR #${pr} base is ${base_ref}, expected ${base}" >&2
    return 1
  fi
  echo "check-labels: PR #${pr} merged to ${base}"
}

main() {
  require_gh
  local cmd="${1:-}"
  shift || true
  case "$cmd" in
    issue-has-all)
      [[ $# -ge 3 ]] || {
        usage >&2
        exit 2
      }
      issue_has_all "$@"
      ;;
    pr-has)
      [[ $# -eq 3 ]] || {
        usage >&2
        exit 2
      }
      pr_has "$@"
      ;;
    pr-merged-to)
      [[ $# -eq 3 ]] || {
        usage >&2
        exit 2
      }
      pr_merged_to "$@"
      ;;
    -h | --help | "")
      usage
      exit 0
      ;;
    *)
      echo "check-labels: unknown command: ${cmd}" >&2
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
