#!/usr/bin/env bash
# Validate product INTENT.md and intent verdict PASS (LAW-02, DS-B19).
# Exit 0 only when intent verdict status is PASS and INTENT.md has required sections.
set -euo pipefail

PROGRAM_ID="${1:-}"
if [[ -z "$PROGRAM_ID" ]]; then
  echo "usage: validate-intent.sh <program-id>" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

INTENT_FILE="LiNKdev/product/grounding/INTENT.md"
SCHEMA_FILE="LiNKdev/factory/contracts/intent-verdict.schema.json"
VERDICT_REPORT="LiNKdev/product/reports/${PROGRAM_ID}/intent-verdict.json"
VERDICT_PROGRAM="LiNKdev/product/programs/${PROGRAM_ID}/intent-verdict.json"

fail() { echo "INTENT FAIL: $*" >&2; exit 1; }

if [[ ! -f "$INTENT_FILE" ]]; then
  fail "missing $INTENT_FILE"
fi

VERDICT_FILE=""
if [[ -f "$VERDICT_REPORT" && -f "$VERDICT_PROGRAM" ]]; then
  if [[ "$VERDICT_REPORT" -nt "$VERDICT_PROGRAM" ]]; then
    VERDICT_FILE="$VERDICT_REPORT"
  else
    VERDICT_FILE="$VERDICT_PROGRAM"
  fi
elif [[ -f "$VERDICT_REPORT" ]]; then
  VERDICT_FILE="$VERDICT_REPORT"
elif [[ -f "$VERDICT_PROGRAM" ]]; then
  VERDICT_FILE="$VERDICT_PROGRAM"
else
  fail "no intent verdict at $VERDICT_REPORT or $VERDICT_PROGRAM"
fi

if [[ ! -f "$SCHEMA_FILE" ]]; then
  fail "missing schema $SCHEMA_FILE"
fi

python3 - <<'PY' "$INTENT_FILE" "$VERDICT_FILE" "$SCHEMA_FILE" "$PROGRAM_ID"
import json, re, sys
from pathlib import Path

intent_path = Path(sys.argv[1])
verdict_path = Path(sys.argv[2])
schema_path = Path(sys.argv[3])
program_id = sys.argv[4]

REQUIRED_SECTIONS = [
    r"^##\s+Grounding links\s*$",
    r"^##\s+What development must accomplish\s*$",
    r"^##\s+Program scope\s*$",
    r"^##\s+Success criteria\s*$",
    r"^##\s+Constraints\s*$",
    r"^##\s+Principal approval\s*$",
]

intent_text = intent_path.read_text()
lines = intent_text.splitlines()

for pattern in REQUIRED_SECTIONS:
    if not any(re.match(pattern, line) for line in lines):
        print(f"INTENT FAIL: missing section matching /{pattern}/", file=sys.stderr)
        sys.exit(1)

if "VISION.md" not in intent_text:
    print("INTENT FAIL: INTENT.md must reference VISION.md", file=sys.stderr)
    sys.exit(1)
if "SHIP_CRITERIA.md" not in intent_text:
    print("INTENT FAIL: INTENT.md must reference SHIP_CRITERIA.md", file=sys.stderr)
    sys.exit(1)

try:
    verdict = json.loads(verdict_path.read_text())
except json.JSONDecodeError as exc:
    print(f"INTENT FAIL: invalid JSON in {verdict_path}: {exc}", file=sys.stderr)
    sys.exit(1)

schema = json.loads(schema_path.read_text())
required = schema.get("required", [])
for key in required:
    if key not in verdict:
        print(f"INTENT FAIL: verdict missing required field {key!r}", file=sys.stderr)
        sys.exit(1)

if verdict.get("program_id") != program_id:
    print(
        f"INTENT FAIL: verdict program_id {verdict.get('program_id')!r} != {program_id!r}",
        file=sys.stderr,
    )
    sys.exit(1)

status = verdict.get("status")
if status not in ("PASS", "FAIL", "BLOCKED"):
    print(f"INTENT FAIL: invalid status {status!r}", file=sys.stderr)
    sys.exit(1)

if status != "PASS":
    print(f"INTENT FAIL: verdict status is {status!r}, require PASS", file=sys.stderr)
    sys.exit(1)

laws = verdict.get("laws_checked", [])
expected_laws = {f"LAW-{i:02d}" for i in range(1, 9)}
if set(laws) != expected_laws:
    missing = sorted(expected_laws - set(laws))
    extra = sorted(set(laws) - expected_laws)
    if missing:
        print(f"INTENT FAIL: laws_checked missing {missing}", file=sys.stderr)
        sys.exit(1)
    if extra:
        print(f"INTENT FAIL: laws_checked has unexpected {extra}", file=sys.stderr)
        sys.exit(1)

reqs = verdict.get("requirements_checked", [])
if not isinstance(reqs, list) or len(reqs) < 1:
    print("INTENT FAIL: requirements_checked must be a non-empty array", file=sys.stderr)
    sys.exit(1)

blockers = verdict.get("blockers", [])
if blockers:
    print(f"INTENT FAIL: blockers present on PASS verdict: {blockers}", file=sys.stderr)
    sys.exit(1)

ts = verdict.get("timestamp", "")
if not re.match(r"^\d{4}-\d{2}-\d{2}T", ts):
    print(f"INTENT FAIL: timestamp must be ISO-8601, got {ts!r}", file=sys.stderr)
    sys.exit(1)

optional = verdict.get("planner_narrative_sha256")
if optional is not None and not re.fullmatch(r"[0-9a-f]{64}", optional):
    print("INTENT FAIL: planner_narrative_sha256 must be 64 hex chars", file=sys.stderr)
    sys.exit(1)

extra_keys = set(verdict.keys()) - set(schema.get("properties", {}).keys())
if extra_keys:
    print(f"INTENT FAIL: unexpected verdict fields {sorted(extra_keys)}", file=sys.stderr)
    sys.exit(1)

print(f"INTENT OK: {program_id} PASS ({verdict_path})")
PY

echo "INTENT OK: all checks passed for program $PROGRAM_ID"
