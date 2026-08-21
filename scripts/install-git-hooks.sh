#!/usr/bin/env bash
# Install repo-local git hooks that enforce application-pipeline consistency.
# Usage (from any clone that vendors IDE Development core, or this repo itself):
#   bash scripts/install-git-hooks.sh
#   bash /path/to/IDE-Development/scripts/install-git-hooks.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"

if [[ -z "${TARGET_ROOT:-}" ]]; then
  echo "install-git-hooks: not inside a git repository" >&2
  exit 1
fi

HOOKS_SRC="$SOURCE_ROOT/.githooks"
if [[ ! -d "$HOOKS_SRC" ]]; then
  echo "install-git-hooks: missing $HOOKS_SRC" >&2
  exit 1
fi

HOOKS_DST="$TARGET_ROOT/.githooks"
mkdir -p "$HOOKS_DST"
if [[ "$HOOKS_SRC" != "$HOOKS_DST" ]]; then
  cp -f "$HOOKS_SRC/pre-commit" "$HOOKS_DST/pre-commit"
  cp -f "$HOOKS_SRC/pre-push" "$HOOKS_DST/pre-push"
fi
chmod +x "$HOOKS_DST/pre-commit" "$HOOKS_DST/pre-push"

git -C "$TARGET_ROOT" config core.hooksPath .githooks
echo "install-git-hooks: configured core.hooksPath=.githooks in $TARGET_ROOT"
echo "install-git-hooks: pre-commit and pre-push will reject invalid PIPELINE-STATE.json transitions"
