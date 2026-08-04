#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${LINKAUTOWORK_MIGRATION_MODE:-dry-run}"

if [[ "$MODE" != "dry-run" && "$MODE" != "apply-authorized" ]]; then
  echo "LINKAUTOWORK_MIGRATION_MODE must be dry-run or apply-authorized" >&2
  exit 1
fi

mapfile -t migrations < <(find "$ROOT_DIR/supabase/migrations" -maxdepth 1 -type f -name '*.sql' -print | sort)
[[ ${#migrations[@]} -gt 0 ]] || { echo "No migrations found" >&2; exit 1; }

for migration in "${migrations[@]}"; do
  shasum -a 256 "$migration"
done

if [[ "$MODE" == "dry-run" ]]; then
  echo "Migration preflight passed: checksums recorded; no database connection or apply attempted."
  exit 0
fi

: "${LINKAUTOWORK_APPROVED_MIGRATION_COMMAND:?authorised migration command required}"
echo "Applying migration through authorised deployment command."
exec sh -c "$LINKAUTOWORK_APPROVED_MIGRATION_COMMAND"
