#!/usr/bin/env bash
# Emit light proof manifest (DS-B7) from a single agent report directory.
set -euo pipefail

REPORT="${1:-}"
OUT="${2:-LiNKdev/product/reports/proof-manifest.json}"
if [[ -z "$REPORT" || ! -f "$REPORT" ]]; then
  echo "usage: proof-manifest.sh <report.md> [out.json]" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
export ROOT REPORT OUT
python3 - <<'PY'
import hashlib, json, os, re
from datetime import datetime, timezone
from pathlib import Path

root = Path(os.environ["ROOT"])
report = Path(os.environ["REPORT"]).resolve()
out = Path(os.environ["OUT"])

ARTIFACT_RE = re.compile(r'artifact_path["\']?\s*:\s*["\']([^"\']+)["\']')
PROOF_JSON_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)


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


def resolve_path(rel: str):
    candidate = Path(rel)
    if not candidate.is_absolute():
        candidate = (root / rel).resolve()
    else:
        candidate = candidate.resolve()
    return candidate if candidate.is_file() else None


def file_entry(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }

text = report.read_text(encoding="utf-8", errors="replace")
paths: set[Path] = {report}
for rel in artifact_paths_from_text(text):
    resolved = resolve_path(rel)
    if resolved:
        paths.add(resolved)

files = [file_entry(p) for p in sorted(paths, key=lambda p: str(p))]
manifest = {
    "report": str(report),
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "file_count": len(files),
    "files": files,
    "artifact_count": max(0, len(files) - 1),
    "artifacts": [f for f in files if f["path"] != str(report)],
}
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"wrote {out} ({len(files)} files, {manifest['artifact_count']} artifacts)")
PY
