#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

check_env() {
  local file="$1"
  [[ -f "$file" ]] || return 0

  local violations=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" != *"="* ]] && continue

    local key="${line%%=*}"
    local value="${line#*=}"

    if [[ "$key" == *_SECRET_NAME ]]; then
      continue
    fi

    # Guard against accidental inline secret-like values in committed env files.
    if [[ "$key" =~ (TOKEN|KEY|SECRET|PASSWORD) ]] && [[ -n "$value" ]] && [[ "$value" != replace* ]] && [[ "$value" != '<'* ]]; then
      echo "violation: $file has inline secret-like value for $key"
      violations=1
    fi
  done < "$file"

  return $violations
}

check_env "$ROOT_DIR/deploy/dev/.env.example"
check_env "$ROOT_DIR/deploy/prod/.env.example"

echo "env contract check passed"
