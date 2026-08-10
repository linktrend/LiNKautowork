#!/usr/bin/env bash
# Plan / verify / apply managed protections for development, staging, and main.
# Default operator intent is plan (no mutation). Apply requires --apply.
#
# Usage:
#   ./scripts/manage-repository-protections.sh plan
#   ./scripts/manage-repository-protections.sh --repo linktrend/LiNKskills verify
#   ./scripts/manage-repository-protections.sh --repo linktrend/LiNKskills apply --apply
#   ./scripts/manage-repository-protections.sh --fixture-dir /tmp/fx plan
#
# See docs/contracts/REPOSITORY-PROTECTION.md

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MODE=""
ARGS=()
i=1
while [ "$i" -le "$#" ]; do
  eval "arg=\${$i}"
  case "$arg" in
    plan|verify|apply|rollback)
      if [ -z "$MODE" ]; then
        MODE="$arg"
      else
        ARGS+=("$arg")
      fi
      ;;
    *)
      ARGS+=("$arg")
      ;;
  esac
  i=$((i + 1))
done

if [ -z "$MODE" ]; then
  MODE="plan"
fi

exec python3 "${ROOT}/scripts/gitops/repository_protection.py" "$MODE" "${ARGS[@]}"
