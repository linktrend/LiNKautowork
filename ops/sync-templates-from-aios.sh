#!/usr/bin/env bash
set -euo pipefail

# Backwards-compatible entrypoint kept by filename, but source-of-truth now flows
# from LiNKautowork templates to AIOS mirror copies.
SOURCE_DIR="/Users/linktrend/Projects/LiNKautowork/automations/templates"
AIOS_WORKFLOWS="/Users/linktrend/Projects/LiNKaios/apps/LiNKautowork/workflows"

mkdir -p "$AIOS_WORKFLOWS"
find "$SOURCE_DIR" -maxdepth 1 -name '*.json' ! -name 'manifest.json' -print0 | while IFS= read -r -d '' file; do
  cp -f "$file" "$AIOS_WORKFLOWS/"
done

echo "Mirrored templates from LiNKautowork (source of truth) to AIOS: $AIOS_WORKFLOWS"
