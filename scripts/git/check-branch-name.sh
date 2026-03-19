#!/usr/bin/env bash
set -euo pipefail

branch_name="${1:-}"
if [[ -z "$branch_name" ]]; then
  echo "Usage: $(basename "$0") <branch-name>" >&2
  exit 2
fi

pattern='^(sync/upstream-[0-9]{6}(-[0-9]{4})?|feat/.+|fix/.+|chore/.+|docs/.+|ops/.+|codex/.+|hotfix/.+)$'
if [[ ! "$branch_name" =~ $pattern ]]; then
  echo "ERROR: invalid branch name '$branch_name'" >&2
  echo "Expected patterns: sync/upstream-YYMMDD, feat/*, fix/*, chore/*, docs/*, ops/*, codex/*, hotfix/*" >&2
  exit 1
fi

echo "PASS: branch name is policy-compliant."
