#!/usr/bin/env bash
set -euo pipefail

repo_path="${1:-link-n8n}"

bash "$(dirname "$0")/check-signing-prereqs.sh" --repo-path "$repo_path"
bash "$(dirname "$0")/branch-hygiene.sh" --repo-path "$repo_path"
bash "$(dirname "$0")/upstream-sync-pr.sh" --repo-path "$repo_path" --base-branch master --upstream-branch master
