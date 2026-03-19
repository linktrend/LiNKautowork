#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <db-backup.sql.gz> <templates-backup.tar.gz>"
  exit 1
fi

DB_BACKUP="$1"
TEMPLATES_BACKUP="$2"

if [[ ! -f "$DB_BACKUP" ]]; then
  echo "DB backup not found: $DB_BACKUP"
  exit 1
fi
if [[ ! -f "$TEMPLATES_BACKUP" ]]; then
  echo "Templates backup not found: $TEMPLATES_BACKUP"
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

gzip -dc "$DB_BACKUP" > "$TMP_DIR/restore.sql"
if ! grep -q "CREATE" "$TMP_DIR/restore.sql"; then
  echo "Restore drill failed: SQL backup appears invalid"
  exit 1
fi

tar -xzf "$TEMPLATES_BACKUP" -C "$TMP_DIR"

if [[ ! -d "$TMP_DIR/automations/templates" ]]; then
  echo "Restore drill failed: templates directory missing in archive"
  exit 1
fi

echo "Restore drill passed: backup artifacts are readable and structurally valid"
