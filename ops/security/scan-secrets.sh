#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo 'Scanning tracked files for likely secret literals...'

patterns=(
  'AKIA[0-9A-Z]{16}'
  'AIza[0-9A-Za-z_-]{35}'
  'ghp_[0-9A-Za-z]{36,}'
  'xox[baprs]-[0-9A-Za-z-]{10,}'
  '-----BEGIN (RSA|EC|OPENSSH|PGP) PRIVATE KEY-----'
  'tskey-auth-[0-9A-Za-z_-]+'
)

tracked_file_list="$(mktemp)"
git ls-files ':(exclude)link-n8n/**' >"$tracked_file_list" 2>/dev/null || true
if [[ ! -s "$tracked_file_list" ]]; then
  echo 'No tracked files found to scan.'
  rm -f "$tracked_file_list"
  exit 0
fi

hit=0
for p in "${patterns[@]}"; do
  : > /tmp/linkautowork_secret_scan_hits.txt
  while IFS= read -r file; do
    grep -InE -- "$p" "$file" >> /tmp/linkautowork_secret_scan_hits.txt 2>/dev/null || true
  done < "$tracked_file_list"
  if [[ -s /tmp/linkautowork_secret_scan_hits.txt ]]; then
    echo "Pattern hit: $p"
    cat /tmp/linkautowork_secret_scan_hits.txt
    hit=1
  fi
done

rm -f "$tracked_file_list"
rm -f /tmp/linkautowork_secret_scan_hits.txt

if [[ "$hit" -ne 0 ]]; then
  echo 'Potential secret material found. Review before release.' >&2
  exit 1
fi

echo 'No obvious secret literals found in tracked workspace scan.'
