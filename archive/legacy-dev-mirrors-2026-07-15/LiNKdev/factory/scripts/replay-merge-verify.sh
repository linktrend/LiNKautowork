#!/usr/bin/env bash
# DS-B11 benchmark hook: merge-commit traceability for done issues on development.
set -euo pipefail

PROGRAM="${1:-}"
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

if [[ -z "$PROGRAM" ]]; then
  echo "usage: replay-merge-verify.sh <program-id>" >&2
  exit 2
fi

if [[ "$PROGRAM" == "bootstrap" ]]; then
  echo "replay-merge-verify: bootstrap — traceability check skipped"
  exit 0
fi

BRANCH="${LINKDEV_INTEGRATION_BRANCH:-development}"
if ! git rev-parse --verify "$BRANCH" >/dev/null 2>&1; then
  echo "replay-merge-verify: branch '$BRANCH' not found" >&2
  exit 1
fi

export ROOT PROGRAM BRANCH
python3 - <<'PY'
import json, os, re, subprocess, sys
from pathlib import Path

root = Path(os.environ["ROOT"])
program = os.environ["PROGRAM"]
branch = os.environ["BRANCH"]
issue_re = re.compile(r"^[A-Z][A-Z0-9]*-\d{3}$")


def load_state_json(path: Path):
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if not m:
        return None
    data = json.loads(m.group(1))
    if data.get("program_id") != program:
        return None
    return data


def state_candidates() -> list[Path]:
    return [
        root / "LiNKdev/factory/STATE.md",
        root / f"LiNKdev/product/programs/{program}/STATE.md",
    ]


def issues_from_program(plan: Path) -> list[str]:
    if not plan.is_file():
        return []
    text = plan.read_text(encoding="utf-8")
    fm = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    status = ""
    if fm:
        for line in fm.group(1).splitlines():
            if line.strip().startswith("status:"):
                status = line.split(":", 1)[1].strip().lower()
    if status not in ("complete", "done"):
        return []
    ids: list[str] = []
    for line in text.splitlines():
        m = re.match(r"\|\s*([A-Z][A-Z0-9]*-\d{3})\s*\|", line)
        if m and issue_re.match(m.group(1)):
            ids.append(m.group(1))
    return sorted(set(ids))


def done_issues() -> list[str]:
    for path in state_candidates():
        state = load_state_json(path)
        if not state:
            continue
        done = [
            iid
            for iid, meta in (state.get("issues") or {}).items()
            if isinstance(meta, dict) and meta.get("status") == "done"
        ]
        if done:
            return sorted(done)
    plan = root / f"LiNKdev/product/programs/{program}/PROGRAM.md"
    if not plan.is_file():
        plan = root / f"LiNKdev/factory/programs/{program}/PROGRAM.md"
    return issues_from_program(plan)


done = done_issues()
if not done:
    print(f"replay-merge-verify: no done issues for program '{program}' (STATE/PROGRAM)")
    sys.exit(0)

log = subprocess.run(
    ["git", "log", branch, "--merges", "--oneline", "--no-decorate"],
    capture_output=True,
    text=True,
    check=True,
).stdout
if not log.strip():
    log = subprocess.run(
        ["git", "log", branch, "--oneline", "--no-decorate"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

missing = [iid for iid in done if iid not in log]
if missing:
    print(f"replay-merge-verify FAIL: {len(missing)} issue id(s) not in {branch} log:")
    for iid in missing:
        print(f"  - {iid}")
    sys.exit(1)

print(f"replay-merge-verify OK: {len(done)} done issue(s) traced on {branch}")
PY
