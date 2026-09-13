#!/usr/bin/env bash
set -euo pipefail

# Source-only backup rehearsal. Never dumps Postgres, never writes production backups,
# and never contacts Server01, NATS, n8n, or GSM.
#
# Usage:
#   ops/run-backup.sh              # rehearsal (default)
#   ops/run-backup.sh --rehearse   # explicit rehearsal
# Live dumps are HOLD and exit 2.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-rehearse}"

if [[ "$MODE" == "--live" || "$MODE" == "live" || "${LINKTREND_ALLOW_LIVE_OPS:-}" == "1" ]]; then
  echo "HOLD: live backup is not admitted by this source rehearsal. No pg_dump or remote write was performed." >&2
  exit 2
fi
if [[ "$MODE" != "rehearse" && "$MODE" != "--rehearse" ]]; then
  echo "Usage: $0 [--rehearse]" >&2
  exit 1
fi

STAMP="rehearse-static"
OUT_DIR="${TMPDIR:-/tmp}/linkautowork-backup-rehearsal-${STAMP}"
mkdir -p "$OUT_DIR"

python3 - "$OUT_DIR" "$ROOT_DIR" <<'PY'
import hashlib, json, sys
from pathlib import Path
out, root = Path(sys.argv[1]), Path(sys.argv[2])
kinds = {
    "control_records": {"kind": "control_records", "reference": "lautowork-control-rehearsal-only"},
    "catalogue_receipts": {"kind": "catalogue_receipts", "reference": "catalogue-receipts-rehearsal-only"},
    "workflow_configuration": {"kind": "workflow_configuration", "reference": "n8n-workflow-config-rehearsal-only"},
}
manifest = {"mode": "rehearse", "live": False, "root": str(root), "artifacts": []}
for kind, content in kinds.items():
    encoded = json.dumps(content, separators=(",", ":"), sort_keys=True).encode()
    digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    path = out / f"{kind}.json"
    path.write_bytes(encoded)
    (out / f"{kind}.digest").write_text(digest + "\n")
    manifest["artifacts"].append({"kind": kind, "path": str(path), "digest": digest})
(out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest, indent=2))
PY

echo "Backup rehearsal wrote mock artifacts under $OUT_DIR"
echo "No live database, n8n, or Server01 target was contacted."
