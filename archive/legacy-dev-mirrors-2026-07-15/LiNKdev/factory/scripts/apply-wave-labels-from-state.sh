#!/usr/bin/env bash
# Apply linkdev:ready + runtime:* (+ tier:*) to GitHub issues listed as ready in STATE.md.
# Uses LiNKdev/product/reports/<program_id>/github-issues.json for LTS → issue number mapping.
# Intended for privileged GitHub Actions (cloud Orchestrator tokens often get 403 on label writes).
set -euo pipefail

usage() {
  echo "Usage: apply-wave-labels-from-state.sh <program_id> [state_md_path] [--repo owner/name]" >&2
  exit 1
}

PROGRAM_ID="${1:-}"
shift || true
STATE_PATH="LiNKdev/factory/STATE.md"
REPO="${GITHUB_REPOSITORY:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --state) STATE_PATH="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    *) usage ;;
  esac
done

[[ -n "$PROGRAM_ID" ]] || usage
[[ -n "$REPO" ]] || usage
[[ -f "$STATE_PATH" ]] || { echo "STATE not found: $STATE_PATH" >&2; exit 1; }

MAPPING="LiNKdev/product/reports/${PROGRAM_ID}/github-issues.json"
[[ -f "$MAPPING" ]] || { echo "Issue mapping not found: $MAPPING" >&2; exit 1; }

export PROGRAM_ID STATE_PATH MAPPING REPO
python3 <<'PY'
import json
import os
import re
import subprocess
import sys

program_id = os.environ["PROGRAM_ID"]
state_path = os.environ["STATE_PATH"]
mapping_path = os.environ["MAPPING"]
repo = os.environ["REPO"]

text = open(state_path, encoding="utf-8").read()
m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
if not m:
    sys.exit(f"Could not parse JSON from {state_path}")
state = json.loads(m.group(1))
issues = state.get("issues") or {}
mapping = json.loads(open(mapping_path, encoding="utf-8").read()).get("issues") or {}

applied = 0
for lts_id, row in issues.items():
    if row.get("status") != "ready":
        continue
    meta = mapping.get(lts_id)
    if not meta or not meta.get("github_number"):
        print(f"skip {lts_id}: no github_number in mapping", file=sys.stderr)
        continue
    num = int(meta["github_number"])
    runtime = row.get("runtime") or "cursor"
    tier = row.get("tier") or "standard"
    labels = ["linkdev:ready", f"runtime:{runtime}", f"tier:{tier}"]
    cmd = ["gh", "issue", "edit", str(num), "--repo", repo]
    for lab in labels:
        cmd.extend(["--add-label", lab])
    subprocess.run(cmd, check=True)
    print(f"labeled issue #{num} ({lts_id}): {', '.join(labels)}")
    applied += 1

if applied == 0:
    print("No ready issues in STATE — nothing to label")
PY
