#!/usr/bin/env bash
set -euo pipefail

# Mirror canonical templates from this repo (source of truth) to LiNKtrend-System SDK path.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE_DIR="${REPO_ROOT}/automations/templates"
SYSTEM_ROOT="${LINKTREND_SYSTEM_ROOT:-/Users/linktrend/Projects/LiNKtrend-System}"
SYSTEM_TEMPLATES="${SYSTEM_ROOT}/LiNKautowork/templates"

mkdir -p "$SYSTEM_TEMPLATES"
find "$SOURCE_DIR" -maxdepth 1 -name '*.json' ! -name 'manifest.json' -print0 | while IFS= read -r -d '' file; do
  cp -f "$file" "$SYSTEM_TEMPLATES/"
done

echo "Mirrored templates from LiNKautowork (source of truth) to LiNKtrend-System SDK: ${SYSTEM_TEMPLATES}"
