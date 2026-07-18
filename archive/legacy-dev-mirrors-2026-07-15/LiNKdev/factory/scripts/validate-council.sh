#!/usr/bin/env bash
# Validate LiNKdev council report JSON: schema fields, all five personas, gate match, no BLOCKER (unless --allow-warn for WARN-only pass).
set -euo pipefail

REPORT=""
EXPECTED_GATE=""
ALLOW_WARN=0

usage() {
  echo "usage: validate-council.sh <report.json> [--gate G1|G2|G3|G4] [--allow-warn]" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --gate)
      [[ $# -ge 2 ]] || usage
      EXPECTED_GATE="$2"
      shift 2
      ;;
    --allow-warn)
      ALLOW_WARN=1
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      if [[ -z "$REPORT" ]]; then
        REPORT="$1"
      else
        echo "ERROR: unexpected argument: $1" >&2
        usage
      fi
      shift
      ;;
  esac
done

[[ -n "$REPORT" && -f "$REPORT" ]] || usage

exec python3 - "$REPORT" "$EXPECTED_GATE" "$ALLOW_WARN" <<'PY'
import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
expected_gate = sys.argv[2]
allow_warn = sys.argv[3] == "1"

REQUIRED_PERSONAS = [
    "security-advisor",
    "architecture-advisor",
    "dx-advisor",
    "qa-advisor",
    "product-advisor",
]
VALID_GATES = {"G1", "G2", "G3", "G4"}
VALID_VERDICTS = {"PASS", "WARN", "BLOCKER"}
VALID_EVIDENCE_TYPES = {"file", "command", "report", "narrative"}


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


try:
    data = json.loads(report_path.read_text())
except json.JSONDecodeError as exc:
    fail(f"invalid JSON in {report_path}: {exc}")

for field in ("gate", "program_id", "personas", "summary_status", "blockers"):
    if field not in data:
        fail(f"missing required field: {field}")

gate = data["gate"]
if gate not in VALID_GATES:
    fail(f"invalid gate {gate!r}; expected one of {sorted(VALID_GATES)}")

if expected_gate and gate != expected_gate:
    fail(f"gate mismatch: report has {gate}, expected {expected_gate}")

program_id = data["program_id"]
if not isinstance(program_id, str) or not program_id.strip():
    fail("program_id must be a non-empty string")

personas = data["personas"]
if not isinstance(personas, list):
    fail("personas must be an array")

seen = set()
blocker_personas = []

for idx, persona in enumerate(personas):
    if not isinstance(persona, dict):
        fail(f"personas[{idx}] must be an object")

    persona_id = persona.get("persona_id")
    if persona_id not in REQUIRED_PERSONAS:
        fail(f"personas[{idx}] has invalid persona_id {persona_id!r}")

    if persona_id in seen:
        fail(f"duplicate persona_id: {persona_id}")
    seen.add(persona_id)

    verdict = persona.get("verdict")
    if verdict not in VALID_VERDICTS:
        fail(f"{persona_id}: invalid verdict {verdict!r}")

    summary = persona.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        fail(f"{persona_id}: summary must be a non-empty string")

    evidence = persona.get("evidence")
    if not isinstance(evidence, list) or len(evidence) == 0:
        fail(f"{persona_id}: evidence must be a non-empty array")

    for eidx, item in enumerate(evidence):
        if not isinstance(item, dict):
            fail(f"{persona_id}: evidence[{eidx}] must be an object")
        for key in ("type", "ref", "finding"):
            if key not in item or not isinstance(item[key], str) or not item[key].strip():
                fail(f"{persona_id}: evidence[{eidx}] missing or empty {key}")
        if item["type"] not in VALID_EVIDENCE_TYPES:
            fail(f"{persona_id}: evidence[{eidx}] invalid type {item['type']!r}")

    if verdict == "BLOCKER":
        blocker_personas.append(persona_id)

missing = [p for p in REQUIRED_PERSONAS if p not in seen]
if missing:
    fail(f"missing required personas: {', '.join(missing)}")

if len(personas) != 5:
    fail(f"expected exactly 5 personas, found {len(personas)}")

summary_status = data["summary_status"]
if summary_status not in VALID_VERDICTS:
    fail(f"invalid summary_status {summary_status!r}")

blockers = data["blockers"]
if not isinstance(blockers, list):
    fail("blockers must be an array")

for bidx, blocker in enumerate(blockers):
    if not isinstance(blocker, dict):
        fail(f"blockers[{bidx}] must be an object")
    pid = blocker.get("persona_id")
    if pid not in REQUIRED_PERSONAS:
        fail(f"blockers[{bidx}] invalid persona_id {pid!r}")
    message = blocker.get("message")
    if not isinstance(message, str) or not message.strip():
        fail(f"blockers[{bidx}] message must be a non-empty string")

# Consistency: BLOCKER verdicts should appear in blockers[] (warn if not)
blocker_ids_in_list = {b["persona_id"] for b in blockers}
for pid in blocker_personas:
    if pid not in blocker_ids_in_list:
        print(f"WARN: {pid} verdict is BLOCKER but not listed in blockers[]", file=sys.stderr)

if summary_status == "BLOCKER" and not blockers:
    fail("summary_status is BLOCKER but blockers[] is empty")

if summary_status == "PASS" and blockers:
    fail("summary_status is PASS but blockers[] is non-empty")

if blocker_personas or summary_status == "BLOCKER" or blockers:
    fail(
        "council report has BLOCKER — progress halted "
        f"(personas: {', '.join(blocker_personas) or 'none'}; blockers: {len(blockers)})"
    )

if summary_status == "WARN" and not allow_warn:
    fail("summary_status is WARN; re-run with --allow-warn to permit WARN-only pass")

if summary_status not in {"PASS", "WARN"}:
    fail(f"summary_status {summary_status!r} does not allow progress")

print(f"OK: council report valid for {gate} program={program_id} status={summary_status} ({report_path})")
PY
