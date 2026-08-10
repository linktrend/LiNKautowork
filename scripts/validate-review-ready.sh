#!/usr/bin/env bash
# Validate that SHA (default HEAD) has successful Linktrend Review Ready status.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "FAIL: not a git repository" >&2
  exit 1
}
cd "$ROOT"
SHA="${1:-$(git rev-parse HEAD)}"
if python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/gitops/readiness_status.py" get "$SHA"; then
  echo "PASS: review-ready status success for ${SHA}"
  exit 0
fi
echo "FAIL: ${SHA} is not review-ready" >&2
exit 1
