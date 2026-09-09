#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd "$(dirname "$0")/.." && pwd)"
MODE="${LINKAUTOWORK_MIGRATION_MODE:-dry-run}"

if [ "$MODE" != "dry-run" ] && [ "$MODE" != "apply-authorized" ]; then
  echo "LINKAUTOWORK_MIGRATION_MODE must be dry-run or apply-authorized" >&2
  exit 1
fi

migration_list="$(find "$ROOT_DIR/supabase/migrations" -maxdepth 1 -type f -name '*.sql' -print | sort)"
[ -n "$migration_list" ] || { echo "No migrations found" >&2; exit 1; }

hash_migration() {
  migration="$1"
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$migration"
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$migration"
  else
    echo "Migration preflight requires shasum or sha256sum" >&2
    exit 1
  fi
}

printf '%s\n' "$migration_list" | while IFS= read -r migration; do
  [ -n "$migration" ] || continue
  hash_migration "$migration"
done

if [ "$MODE" = "dry-run" ]; then
  echo "Migration preflight passed: checksums recorded; no database connection or apply attempted."
  exit 0
fi

: "${LINKAUTOWORK_APPROVED_MIGRATION_COMMAND:?authorised migration command required}"
echo "Applying migration through authorised deployment command."
exec sh -c "$LINKAUTOWORK_APPROVED_MIGRATION_COMMAND"
