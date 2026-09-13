#!/usr/bin/env bash
set -euo pipefail

# Source-only n8n export planner. Never calls n8n, GSM, or gcloud, and never writes live snapshots.
#
# Usage:
#   ops/export-live-from-n8n.sh [dev|prod|rehearse]
# Live export is HOLD and exit 2.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENVIRONMENT="${1:-rehearse}"

if [[ "$ENVIRONMENT" == "--live" || "${LINKTREND_ALLOW_LIVE_OPS:-}" == "1" ]]; then
  echo "HOLD: live n8n export is not admitted by this source rehearsal. No API key or workflow JSON was fetched." >&2
  exit 2
fi

if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" && "$ENVIRONMENT" != "rehearse" ]]; then
  echo "Usage: $0 [dev|prod|rehearse]" >&2
  exit 1
fi

python3 - "$ROOT_DIR" "$ENVIRONMENT" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
environment = sys.argv[2]
manifest_path = root / "automations" / "templates" / "manifest.json"
entries = []
if manifest_path.is_file():
    payload = json.loads(manifest_path.read_text())
    for item in payload.get("templates") or []:
        if isinstance(item, dict):
            entries.append({
                "id": item.get("workflow_id") or item.get("file"),
                "name": item.get("file") or item.get("workflow_id"),
                "state": item.get("state"),
                "source": "automations/templates/manifest.json",
            })
plan = {
    "mode": "rehearse",
    "environment": environment,
    "live": False,
    "targetDir": f"automations/live/{environment}",
    "requiredSecretNames": ["N8N_API_KEY_SECRET_NAME"],
    "requiredConfig": ["N8N_BASE_URL"],
    "workflowsPlanned": entries,
    "note": "This is a local export plan. Authorised live export remains HOLD.",
}
print(json.dumps(plan, indent=2))
print(f"Planned {len(entries)} local template reference(s) for {environment}; no n8n contact.", file=sys.stderr)
PY
