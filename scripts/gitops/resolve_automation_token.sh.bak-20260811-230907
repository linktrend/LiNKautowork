#!/usr/bin/env bash
# Resolve automation token from a minted GitHub App installation token.
# Never prints secret material. Sets AUTOMATION_TOKEN and AUTOMATION_TOKEN_SOURCE.
#
# Workflow contract:
#   1. actions/create-github-app-token receives App ID + private key (mint step only).
#   2. Subsequent shell/Python receives only:
#        - LINKTREND_GITOPS_APP_ID   (non-secret)
#        - LINKTREND_APP_TOKEN       (minted installation token from step output)
#   3. Private key must NEVER be present in consuming steps.
#
# When sourced, fail-closed uses `return` so callers can run
# `if ! source …; then` local-outcome branches. When executed, uses `exit`.
#
# See docs/contracts/GITHUB-APP-GITOPS-CREDENTIALS.md
set -euo pipefail

_automation_fail_closed() {
  echo "automation_credentials_blocked" >&2
  # EX_CONFIG — fail closed for autonomous path
  if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    return 78
  fi
  exit 78
}

AUTOMATION_TOKEN=""
AUTOMATION_TOKEN_SOURCE="none"
AUTOMATION_CREDENTIALS_STATUS="missing"

APP_ID="${LINKTREND_GITOPS_APP_ID:-${LINKTREND_GITOPS_APP_ID_VAR:-}}"
MINTED_TOKEN="${LINKTREND_APP_TOKEN:-}"

# Fail closed if a consuming step accidentally received the private key.
if [ -n "${LINKTREND_GITOPS_APP_PRIVATE_KEY:-}" ]; then
  echo "AUTOMATION_CREDENTIALS_STATUS=private_key_leaked_into_consumer" >&2
  echo "Private key must only be passed to actions/create-github-app-token." >&2
  AUTOMATION_CREDENTIALS_STATUS="private_key_leaked_into_consumer"
  export AUTOMATION_TOKEN AUTOMATION_TOKEN_SOURCE AUTOMATION_CREDENTIALS_STATUS
  echo "AUTOMATION_TOKEN_SOURCE=${AUTOMATION_TOKEN_SOURCE}"
  echo "AUTOMATION_CREDENTIALS_STATUS=${AUTOMATION_CREDENTIALS_STATUS}"
  if [ "${REQUIRE_APP_TOKEN:-1}" = "1" ]; then
    _automation_fail_closed || return $?
  fi
fi

if [ -n "${MINTED_TOKEN}" ] && [ -n "${APP_ID}" ]; then
  AUTOMATION_TOKEN="${MINTED_TOKEN}"
  AUTOMATION_TOKEN_SOURCE="github_app"
  AUTOMATION_CREDENTIALS_STATUS="configured"
elif [ -n "${MINTED_TOKEN}" ] && [ -z "${APP_ID}" ]; then
  echo "AUTOMATION_CREDENTIALS_STATUS=missing_app_id" >&2
  AUTOMATION_CREDENTIALS_STATUS="missing_app_id"
elif [ -n "${APP_ID}" ] && [ -z "${MINTED_TOKEN}" ]; then
  echo "AUTOMATION_CREDENTIALS_STATUS=missing_runtime_token" >&2
  echo "App ID present but LINKTREND_APP_TOKEN empty (mint failed or not injected)." >&2
  AUTOMATION_CREDENTIALS_STATUS="missing_runtime_token"
else
  AUTOMATION_CREDENTIALS_STATUS="missing"
fi

# No GITHUB_TOKEN fallback for autonomous mutations.
export AUTOMATION_TOKEN
export AUTOMATION_TOKEN_SOURCE
export AUTOMATION_CREDENTIALS_STATUS

echo "AUTOMATION_TOKEN_SOURCE=${AUTOMATION_TOKEN_SOURCE}"
echo "AUTOMATION_CREDENTIALS_STATUS=${AUTOMATION_CREDENTIALS_STATUS}"

if [ "${REQUIRE_APP_TOKEN:-1}" = "1" ]; then
  if [ "${AUTOMATION_TOKEN_SOURCE}" != "github_app" ] || [ -z "${AUTOMATION_TOKEN}" ]; then
    _automation_fail_closed || return $?
  fi
fi
