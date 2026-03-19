#!/usr/bin/env bash
set -euo pipefail

repo_path="${1:-link-n8n}"

bash "$(dirname "$0")/post-merge-cleanup.sh" --repo-path "$repo_path" --delete-remote --apply
bash "$(dirname "$0")/verify-parity.sh" --repo-path "$repo_path" --branch master
