#!/usr/bin/env bash
set -euo pipefail

: "${PGHOST:?PGHOST required}"
: "${PGPORT:?PGPORT required}"
: "${PGDATABASE:?PGDATABASE required}"
: "${PGUSER:?PGUSER required}"
: "${PGPASSWORD:?PGPASSWORD required}"

BACKUP_DIR="/Users/linktrend/Projects/LiNKautowork/ops/backups"
mkdir -p "$BACKUP_DIR"
TS="$(date '+%Y%m%d-%H%M%S')"
DB_FILE="$BACKUP_DIR/supabase-${TS}.sql.gz"
TEMPLATES_FILE="$BACKUP_DIR/templates-${TS}.tar.gz"

pg_dump --no-owner --no-privileges | gzip > "$DB_FILE"
tar -czf "$TEMPLATES_FILE" -C /Users/linktrend/Projects/LiNKautowork automations/templates automations/evals

echo "Created DB backup: $DB_FILE"
echo "Created templates/evals backup: $TEMPLATES_FILE"
