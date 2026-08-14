#!/usr/bin/env bash
# Shared allowlist for short-lived work branches (Packager + branch-source-policy).
# Sourced by other scripts. Do not execute directly for side effects.

# Allowed PR heads into development (must stay in sync with
# core/github/managed-workflows/branch-source-policy.yml).
# phaseBranchPrefix comes from .github/linktrend-delivery-mode.json (default phase/).

_linktrend_delivery_mode_config() {
  local cfg="${LINKTREND_DELIVERY_MODE_CONFIG:-.github/linktrend-delivery-mode.json}"
  printf '%s' "${cfg}"
}

resolve_phase_branch_prefix() {
  # Env override for tests / automation (must end with /).
  if [[ -n "${LINKTREND_PHASE_BRANCH_PREFIX:-}" ]]; then
    local env_prefix="${LINKTREND_PHASE_BRANCH_PREFIX}"
    [[ "${env_prefix}" == */ ]] || env_prefix="${env_prefix}/"
    printf '%s' "${env_prefix}"
    return 0
  fi

  local cfg
  cfg="$(_linktrend_delivery_mode_config)"
  local prefix="phase/"
  if [[ -f "${cfg}" ]]; then
    local parsed
    parsed="$(
      python3 -c '
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    print("phase/")
    raise SystemExit(0)
p = str((data or {}).get("phaseBranchPrefix") or "phase/").strip() or "phase/"
if not p.endswith("/"):
    p = p + "/"
print(p)
' "${cfg}" 2>/dev/null || echo "phase/"
    )"
    if [[ -n "${parsed}" ]]; then
      prefix="${parsed}"
    fi
  fi
  printf '%s' "${prefix}"
}

is_allowed_work_branch() {
  local name="${1:-}"
  case "${name}" in
    issue/*|dev/*)
      return 0
      ;;
  esac
  local phase_prefix
  phase_prefix="$(resolve_phase_branch_prefix)"
  case "${name}" in
    "${phase_prefix}"*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

# Temporary promotion branches (staging target).
is_staging_promote_branch() {
  local name="${1:-}"
  case "${name}" in
    promote/staging/*) return 0 ;;
    *) return 1 ;;
  esac
}

# Temporary promotion branches (main target).
is_main_promote_branch() {
  local name="${1:-}"
  case "${name}" in
    promote/main/*) return 0 ;;
    *) return 1 ;;
  esac
}

allowed_work_branch_globs() {
  local phase_prefix
  phase_prefix="$(resolve_phase_branch_prefix)"
  printf '%s\n' \
    'issue/*' "${phase_prefix}*" 'dev/*'
}
