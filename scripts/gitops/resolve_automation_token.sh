#!/usr/bin/env bash
# Resolve automation token from the repository's normal GitHub automation token.
# Never prints secret material. Sets AUTOMATION_TOKEN and AUTOMATION_TOKEN_SOURCE.
#
# Workflow contract:
#   1. A repository secret supplies LINKTREND_AUTOMATION_TOKEN.
#   2. The secret is exposed only to trusted Mac Mini jobs.
#   3. No GitHub App ID or private key is used.
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

NORMAL_TOKEN="${LINKTREND_AUTOMATION_TOKEN:-}"

if [ -n "${NORMAL_TOKEN}" ]; then
  AUTOMATION_TOKEN="${NORMAL_TOKEN}"
  AUTOMATION_TOKEN_SOURCE="github_token"
  AUTOMATION_CREDENTIALS_STATUS="configured"
else
  AUTOMATION_CREDENTIALS_STATUS="missing"
fi

export AUTOMATION_TOKEN
export AUTOMATION_TOKEN_SOURCE
export AUTOMATION_CREDENTIALS_STATUS

echo "AUTOMATION_TOKEN_SOURCE=${AUTOMATION_TOKEN_SOURCE}"
echo "AUTOMATION_CREDENTIALS_STATUS=${AUTOMATION_CREDENTIALS_STATUS}"

if [ "${REQUIRE_AUTOMATION_TOKEN:-1}" = "1" ]; then
  if [ "${AUTOMATION_TOKEN_SOURCE}" != "github_token" ] || [ -z "${AUTOMATION_TOKEN}" ]; then
    _automation_fail_closed || return $?
  fi
fi
