#!/usr/bin/env bash
# Resolve Carlos user token for Packager PR-create + Bugbot comment only.
# Never prints secret material. Sets BUGBOT_USER_TOKEN / SOURCE / STATUS.
#
# Workflow contract:
#   - Secret LINKTREND_BUGBOT_USER_TOKEN is the ONLY accepted input.
#   - This script exports BUGBOT_USER_TOKEN for the two allowed Python call sites.
#   - May be the same normal GitHub automation identity when a separate Bot token is not configured.
#   - Never write the token to outputs, artifacts, summaries, or files.
#
# See docs/contracts/GITHUB-APP-GITOPS-CREDENTIALS.md (dual-credential section).
set -euo pipefail

BUGBOT_USER_TOKEN_SOURCE="none"
BUGBOT_USER_CREDENTIALS_STATUS="missing"

# Accept only the repository secret name — no BUGBOT_USER_TOKEN input fallback.
RAW="${LINKTREND_BUGBOT_USER_TOKEN:-}"

if [ -z "${RAW}" ]; then
  BUGBOT_USER_TOKEN=""
  BUGBOT_USER_TOKEN_SOURCE="none"
  BUGBOT_USER_CREDENTIALS_STATUS="missing"
else
  BUGBOT_USER_TOKEN="${RAW}"
  BUGBOT_USER_TOKEN_SOURCE="user_secret"
  BUGBOT_USER_CREDENTIALS_STATUS="configured"
fi

export BUGBOT_USER_TOKEN
export BUGBOT_USER_TOKEN_SOURCE
export BUGBOT_USER_CREDENTIALS_STATUS

# Diagnostics only — never the token value.
echo "BUGBOT_USER_TOKEN_SOURCE=${BUGBOT_USER_TOKEN_SOURCE}"
echo "BUGBOT_USER_CREDENTIALS_STATUS=${BUGBOT_USER_CREDENTIALS_STATUS}"

if [ "${REQUIRE_BUGBOT_USER_TOKEN:-1}" = "1" ]; then
  if [ "${BUGBOT_USER_TOKEN_SOURCE}" != "user_secret" ] || [ -z "${BUGBOT_USER_TOKEN}" ]; then
    echo "bugbot_user_credentials_blocked" >&2
    # When sourced, return so Packager can write local outcomes; when executed, exit.
    if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
      return 78
    fi
    exit 78
  fi
fi
