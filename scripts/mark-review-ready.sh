#!/usr/bin/env bash
# Compatibility wrapper — authoritative path is completion_gate.py review-ready.
# Validates evidence + branch state, THEN publishes Linktrend Review Ready.
# Do not call readiness_status mark directly from agents.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "FAIL: not a git repository" >&2
  exit 1
}
cd "$ROOT"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ISSUE_ID="${1:-}"
NOTES="${2:-}"
EVIDENCE_FILE="${COMPLETION_EVIDENCE_FILE:-.linktrend/completion-evidence.json}"

if [ ! -f "${EVIDENCE_FILE}" ]; then
  echo "FAIL: missing evidence file ${EVIDENCE_FILE}" >&2
  echo "Write one via: python3 scripts/gitops/completion_gate.py write-evidence ..." >&2
  echo "Or set COMPLETION_EVIDENCE_FILE to a machine-readable JSON tied to HEAD." >&2
  exit 78
fi

ARGS=(review-ready --workdir "$ROOT" --evidence-file "$EVIDENCE_FILE")
if [ -n "$ISSUE_ID" ]; then
  ARGS+=(--issue-id "$ISSUE_ID")
fi
if [ -n "$NOTES" ]; then
  ARGS+=(--notes "$NOTES")
fi

exec python3 "${SCRIPT_DIR}/gitops/completion_gate.py" "${ARGS[@]}"
