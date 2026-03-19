#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [--repo-path <path>] [--allow-unsigned]

Checks commit-signing prerequisites for a git repository.
- Fails if commit signing is not configured.
- Performs an active signing probe unless --allow-unsigned is set.
USAGE
}

repo_path="link-n8n"
allow_unsigned="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-path)
      repo_path="$2"
      shift 2
      ;;
    --allow-unsigned)
      allow_unsigned="true"
      shift 1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -d "$repo_path/.git" ]]; then
  echo "ERROR: Not a git repository: $repo_path" >&2
  exit 1
fi

if [[ "$allow_unsigned" == "true" ]]; then
  echo "WARN: --allow-unsigned enabled. Signing preflight bypassed for CI/bot mode."
  exit 0
fi

if [[ "$(git -C "$repo_path" config --get commit.gpgsign || true)" != "true" ]]; then
  echo "ERROR: commit signing is not enabled (commit.gpgsign=true required)." >&2
  exit 1
fi

gpg_format="$(git -C "$repo_path" config --get gpg.format || echo openpgp)"
signing_key="$(git -C "$repo_path" config --get user.signingkey || true)"

if [[ -z "$signing_key" ]]; then
  echo "ERROR: user.signingkey is not configured." >&2
  exit 1
fi

if [[ "$gpg_format" == "openpgp" ]]; then
  if ! command -v gpg >/dev/null 2>&1; then
    echo "ERROR: gpg not found in PATH." >&2
    exit 1
  fi
  if ! gpg --list-secret-keys "$signing_key" >/dev/null 2>&1; then
    echo "ERROR: configured OpenPGP key not available in local secret keyring." >&2
    exit 1
  fi
fi

# Active signing probe: create an unreachable signed commit object to confirm signing works.
# This does not modify branch history.
tree_hash="$(git -C "$repo_path" write-tree)"
if ! printf "signing probe\n" | git -C "$repo_path" commit-tree -S "$tree_hash" >/dev/null 2>&1; then
  echo "ERROR: signing probe failed. Key agent/pinentry may be unavailable." >&2
  exit 1
fi

echo "PASS: commit signing prerequisites and active signing probe succeeded."
