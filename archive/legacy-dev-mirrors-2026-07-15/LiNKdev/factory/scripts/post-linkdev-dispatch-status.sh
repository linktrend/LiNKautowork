#!/usr/bin/env bash
# Post LiNKdev dispatch visibility to GitHub (issue or PR comment + labels).
# Called from linkdev-dispatch.yml after dispatch-cursor-agent.mjs succeeds.
set -euo pipefail

usage() {
  echo "Usage: post-linkdev-dispatch-status.sh --role <role> --repo <owner/name> [--issue N | --pr N] --agent-id ID --agent-url URL [--run-status STATUS]" >&2
  exit 1
}

ROLE="" REPO="" ISSUE="" PR="" AGENT_ID="" AGENT_URL="" RUN_STATUS="unknown"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --role) ROLE="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --issue) ISSUE="$2"; shift 2 ;;
    --pr) PR="$2"; shift 2 ;;
    --agent-id) AGENT_ID="$2"; shift 2 ;;
    --agent-url) AGENT_URL="$2"; shift 2 ;;
    --run-status) RUN_STATUS="$2"; shift 2 ;;
    *) usage ;;
  esac
done

[[ -n "$ROLE" && -n "$REPO" && -n "$AGENT_ID" ]] || usage
[[ -n "${GH_TOKEN:-}" ]] || { echo "GH_TOKEN required" >&2; exit 1; }

MARKER="[linkdev-dispatch]"
BODY="$(cat <<EOF
${MARKER} **${ROLE}** cloud agent **started**.

| Field | Value |
|-------|-------|
| Agent | \`${AGENT_ID}\` |
| Run status | \`${RUN_STATUS}\` |
| Watch | [Open in Cursor](${AGENT_URL}) |

GitHub Actions will post **running / finished / failed** updates on this thread every ~10 minutes until the run ends. You do not need Cursor Web dashboard for LiNKdev monitoring — **watch this issue or PR**.
EOF
)"

if [[ -n "$ISSUE" ]]; then
  gh issue comment "$ISSUE" --repo "$REPO" --body "$BODY" >/dev/null
  if [[ "$ROLE" == "executor" ]]; then
    gh issue edit "$ISSUE" --repo "$REPO" --add-label "linkdev:in-progress" 2>/dev/null || true
    gh issue edit "$ISSUE" --repo "$REPO" --remove-label "linkdev:ready" 2>/dev/null || true
  fi
elif [[ -n "$PR" ]]; then
  gh pr comment "$PR" --repo "$REPO" --body "$BODY" >/dev/null
else
  gh api "repos/${REPO}/issues" -f title="LiNKdev ${ROLE} dispatch ${AGENT_ID}" -f body="$BODY" >/dev/null || true
fi

echo "Posted dispatch status for role=${ROLE}"
