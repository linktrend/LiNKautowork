#!/usr/bin/env bash
# Validate issue dependency DAG in a program plan markdown file.
set -euo pipefail

PLAN="${1:-}"
if [[ -z "$PLAN" || ! -f "$PLAN" ]]; then
  echo "usage: validate-dag.sh <path-to-PROGRAM.md>" >&2
  exit 2
fi

exec python3 - "$PLAN" <<'PY'
import json, re, sys
from pathlib import Path

plan = Path(sys.argv[1])
text = plan.read_text()
depends = {}
for line in text.splitlines():
    m = re.match(r"\|\s*([A-Z][A-Z0-9]*-\d{3})\s*\|", line)
    if not m:
        continue
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 6:
        continue
    issue_id = parts[1]
    depcol = parts[5]
    if not depcol or depcol == "[]":
        depends[issue_id] = []
    else:
        depends[issue_id] = [d.strip() for d in depcol.split(",") if d.strip()]

if not depends:
    print(f"WARN: no issue rows (ID-###) in {plan}")
    sys.exit(0)

VIS, MARK, cycle = set(), set(), False

def dfs(node, stack):
    global cycle
    if node in MARK:
        cycle = True
        print(f"ERROR: cycle involving {node}", file=sys.stderr)
        return
    if node in VIS:
        return
    VIS.add(node)
    MARK.add(node)
    for d in depends.get(node, []):
        if d not in depends:
            print(f"ERROR: unknown dependency {d} from {node}", file=sys.stderr)
            sys.exit(1)
        dfs(d, stack + [node])
    MARK.remove(node)

for n in depends:
    if n not in VIS:
        dfs(n, [])

if cycle:
    sys.exit(1)
print(f"OK: DAG valid for {len(depends)} issues in {plan}")
PY
