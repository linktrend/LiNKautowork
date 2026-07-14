#!/usr/bin/env bash
# Program-level proof manifest (completion package D): SHA256 of reports + proof artifacts.
set -euo pipefail

PROGRAM="${1:-}"
OUT="${2:-}"
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

if [[ -z "$PROGRAM" ]]; then
  echo "usage: program-proof-manifest.sh <program-id> [out.json]" >&2
  exit 2
fi

REPORTS_DIR="$ROOT/LiNKdev/product/reports/$PROGRAM"
if [[ ! -d "$REPORTS_DIR" ]]; then
  FACTORY_REPORTS="$ROOT/LiNKdev/factory/reports/$PROGRAM"
  if [[ -d "$FACTORY_REPORTS" ]]; then
    REPORTS_DIR="$FACTORY_REPORTS"
  else
    echo "program-proof-manifest: missing reports dir: $REPORTS_DIR (and $FACTORY_REPORTS)" >&2
    exit 2
  fi
fi

if [[ -z "$OUT" ]]; then
  OUT="$REPORTS_DIR/proof-manifest.json"
fi

export ROOT PROGRAM OUT REPORTS_DIR
python3 - <<'PY'
import hashlib, json, os, re
from datetime import datetime, timezone
from pathlib import Path

root = Path(os.environ["ROOT"])
program = os.environ["PROGRAM"]
reports_dir = Path(os.environ["REPORTS_DIR"])
out = Path(os.environ["OUT"])

ARTIFACT_RE = re.compile(r'artifact_path["\']?\s*:\s*["\']([^"\']+)["\']')
PROOF_JSON_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)
ISSUE_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d{3}$")


def artifact_paths_from_text(text: str) -> set[str]:
    found: set[str] = set()
    for m in ARTIFACT_RE.finditer(text):
        found.add(m.group(1))
    for block in PROOF_JSON_RE.finditer(text):
        try:
            data = json.loads(block.group(1))
        except json.JSONDecodeError:
            continue
        for cmd in data.get("commands") or []:
            if isinstance(cmd, dict):
                ap = cmd.get("artifact_path")
                if ap:
                    found.add(str(ap))
    return found


def file_entry(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


paths_to_hash: set[Path] = set()

for md in sorted(reports_dir.rglob("*.md")):
    paths_to_hash.add(md.resolve())
    text = md.read_text(encoding="utf-8", errors="replace")
    for rel in artifact_paths_from_text(text):
        candidate = Path(rel)
        if not candidate.is_absolute():
            candidate = (root / rel).resolve()
        else:
            candidate = candidate.resolve()
        if candidate.is_file():
            paths_to_hash.add(candidate)

files = [file_entry(p) for p in sorted(paths_to_hash, key=lambda p: str(p))]
manifest = {
    "program_id": program,
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "files": files,
}
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"wrote {out} ({len(files)} files)")
PY
