#!/usr/bin/env bash
set -euo pipefail

# Disposable restore rehearsal. Inspects mock or local archive structure only.
# Never restores into Postgres, never starts Server01, and never mutates n8n.
#
# Usage:
#   ops/restore-drill.sh                         # mock artifact rehearsal
#   ops/restore-drill.sh --rehearse
#   ops/restore-drill.sh <db.sql.gz> <templates.tar.gz>  # local structural inspect only
# Live restore is HOLD and exit 2.

if [[ "${1:-}" == "--live" || "${LINKTREND_ALLOW_LIVE_OPS:-}" == "1" ]]; then
  echo "HOLD: live restore is not admitted by this source rehearsal. No database or n8n write was performed." >&2
  exit 2
fi

CLEANUP_DIRS=()
cleanup() {
  local dir
  for dir in "${CLEANUP_DIRS[@]+"${CLEANUP_DIRS[@]}"}"; do
    rm -rf "$dir"
  done
}
trap cleanup EXIT

inspect_archives() {
  local db_backup="$1"
  local templates_backup="$2"
  local inspect
  if [[ ! -f "$db_backup" ]]; then
    echo "DB backup not found: $db_backup" >&2
    exit 1
  fi
  if [[ ! -f "$templates_backup" ]]; then
    echo "Templates backup not found: $templates_backup" >&2
    exit 1
  fi
  inspect="$(mktemp -d)"
  CLEANUP_DIRS+=("$inspect")
  gzip -dc "$db_backup" > "$inspect/restore.sql"
  if ! grep -q "CREATE" "$inspect/restore.sql"; then
    echo "Restore drill failed: SQL backup appears invalid" >&2
    exit 1
  fi
  tar -tzf "$templates_backup" | grep -q "automations/templates" || {
    echo "Restore drill failed: templates directory missing in archive" >&2
    exit 1
  }
  tar -xzf "$templates_backup" -C "$inspect"
  echo "Restore drill passed: backup artifacts are readable and structurally valid"
  echo "No live Postgres, n8n, JetStream, or Server01 restore was performed."
}

rehearse_mock() {
  local tmp db_backup templates_backup
  tmp="$(mktemp -d)"
  CLEANUP_DIRS+=("$tmp")
  python3 - "$tmp" <<'PY'
import gzip, hashlib, tarfile, io, sys
from pathlib import Path
out = Path(sys.argv[1])
sql = b"-- rehearsal only\nCREATE TABLE linkautowork_restore_rehearsal (id int);\n"
(out / "db-backup.sql.gz").write_bytes(gzip.compress(sql))
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
    info = tarfile.TarInfo(name="automations/templates/rehearsal.json")
    payload = b'{"rehearsal":true}\n'
    info.size = len(payload)
    tar.addfile(info, io.BytesIO(payload))
(out / "templates-backup.tar.gz").write_bytes(buffer.getvalue())
print("sha256:" + hashlib.sha256(sql).hexdigest())
PY
  db_backup="$tmp/db-backup.sql.gz"
  templates_backup="$tmp/templates-backup.tar.gz"
  inspect_archives "$db_backup" "$templates_backup"
}

if [[ $# -eq 0 || "${1:-}" == "--rehearse" ]]; then
  rehearse_mock
  exit 0
fi

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 [--rehearse] | $0 <db-backup.sql.gz> <templates-backup.tar.gz>" >&2
  exit 1
fi

inspect_archives "$1" "$2"
