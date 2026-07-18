#!/usr/bin/env bash
# Run LiNKdev completion gates from factory/gates/catalog.json.
set -euo pipefail

TIER=""
PROGRAM=""
REPORT=""
SCOPE="${LINKDEV_SCOPE:-LiNKdev}"
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CATALOG="$ROOT/LiNKdev/factory/gates/catalog.json"

FAILURES=0
PASSED=0
SKIPPED=0

usage() {
  cat <<'EOF' >&2
usage: run-gates.sh --tier A|B|C [--program ID] [--report PATH] [--scope PATH]

Environment fallbacks: LINKDEV_PROGRAM, LINKDEV_REPORT, LINKDEV_SCOPE
EOF
  exit 2
}

log_ok()   { echo "GATE OK:   $*"; PASSED=$((PASSED + 1)); }
log_fail() { echo "GATE FAIL: $*" >&2; FAILURES=$((FAILURES + 1)); }
log_skip() { echo "GATE SKIP: $*"; SKIPPED=$((SKIPPED + 1)); }
log_na()   { echo "GATE N/A:  $*"; SKIPPED=$((SKIPPED + 1)); }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tier) TIER="${2:-}"; shift 2 ;;
    --program) PROGRAM="${2:-}"; shift 2 ;;
    --report) REPORT="${2:-}"; shift 2 ;;
    --scope) SCOPE="${2:-}"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done

PROGRAM="${PROGRAM:-${LINKDEV_PROGRAM:-}}"
REPORT="${REPORT:-${LINKDEV_REPORT:-}}"

[[ "$TIER" =~ ^[ABC]$ ]] || usage
[[ -f "$CATALOG" ]] || { echo "missing catalog: $CATALOG" >&2; exit 2; }

cd "$ROOT"

STACK_FILE="LiNKdev/product/grounding/STACK.md"
SHIP_CRITERIA="LiNKdev/product/grounding/SHIP_CRITERIA.md"

program_plan() {
  if [[ -n "$PROGRAM" ]]; then
    local plan="LiNKdev/product/programs/${PROGRAM}/PROGRAM.md"
    [[ -f "$plan" ]] && { echo "$plan"; return; }
    plan="LiNKdev/factory/programs/${PROGRAM}/PROGRAM.md"
    [[ -f "$plan" ]] && { echo "$plan"; return; }
  fi
  echo "LiNKdev/factory/programs/bootstrap/PROGRAM.md"
}

release_report() {
  if [[ -n "$REPORT" && -f "$REPORT" ]]; then
    echo "$REPORT"
    return
  fi
  if [[ -n "$PROGRAM" ]]; then
    local status="LiNKdev/product/reports/${PROGRAM}/STATUS.md"
    [[ -f "$status" ]] && { echo "$status"; return; }
  fi
  echo ""
}

council_report_path() {
  local gate="$1"
  local path=""
  if [[ -n "${LINKDEV_COUNCIL_REPORT:-}" && -f "$LINKDEV_COUNCIL_REPORT" ]]; then
    echo "$LINKDEV_COUNCIL_REPORT"
    return
  fi
  [[ -n "$PROGRAM" ]] || return 1
  case "$gate" in
    G3)
      if [[ -n "${LINKDEV_MODULE:-}" && -n "${LINKDEV_PHASE:-}" ]]; then
        path="LiNKdev/product/reports/${PROGRAM}/${LINKDEV_MODULE}/${LINKDEV_PHASE}/council-report.json"
        [[ -f "$path" ]] && { echo "$path"; return; }
      fi
      path="$(find "LiNKdev/product/reports/${PROGRAM}" -name 'council-report.json' 2>/dev/null | head -1 || true)"
      [[ -n "$path" && -f "$path" ]] && { echo "$path"; return; }
      ;;
    G4)
      path="LiNKdev/product/reports/${PROGRAM}/council/G4-release-report.json"
      [[ -f "$path" ]] && { echo "$path"; return; }
      ;;
  esac
  return 1
}

stack_languages() {
  [[ -f "$STACK_FILE" ]] || return 1
  awk '
    /^## Languages/ { in_lang=1; next }
    /^## / && in_lang { exit }
    in_lang && /^- / {
      gsub(/^- /, "")
      gsub(/[[:space:]].*$/, "")
      print tolower($0)
    }
  ' "$STACK_FILE"
}

stack_has_js_ts() {
  local langs
  langs="$(stack_languages 2>/dev/null || true)"
  [[ -z "$langs" ]] && return 1
  while IFS= read -r lang; do
    [[ -z "$lang" ]] && continue
    case "$lang" in
      node/typescript|javascript|typescript|node|ts|js) return 0 ;;
    esac
  done <<< "$langs"
  return 1
}

stack_command_for_gate() {
  local gate="$1"
  [[ -f "$STACK_FILE" ]] || return 1
  python3 - <<'PY' "$STACK_FILE" "$gate"
import re, sys
from pathlib import Path

stack = Path(sys.argv[1]).read_text()
gate = sys.argv[2]

# Architecture gate block
if gate == "architecture_gate":
    m = re.search(r"## Architecture gate.*?\n```(?:bash|sh)?\n([^`]+?)```", stack, re.S | re.I)
    if m:
        cmd = m.group(1).strip()
        if cmd and not cmd.startswith("#") and cmd.upper() != "N/A":
            print(cmd)
            raise SystemExit(0)
    for pat in (r"`(npm run typecheck)`", r"`(npm run lint)`", r"`(npx tsc[^`]+)`"):
        m = re.search(pat, stack)
        if m:
            print(m.group(1))
            raise SystemExit(0)

# Integration smoke block
if gate == "integration_smoke":
    m = re.search(r"## Integration smoke.*?\n```(?:bash|sh)?\n([^`]+?)```", stack, re.S | re.I)
    if m:
        lines = [ln.strip() for ln in m.group(1).splitlines() if ln.strip() and not ln.strip().startswith("#")]
        if lines and lines[0].upper() != "N/A":
            print(lines[0])
            raise SystemExit(0)
    m = re.search(r"integration_smoke[^\n]*\|\s*`([^`]+)`", stack, re.I)
    if m:
        cmd = m.group(1).strip()
        if cmd.upper() != "N/A":
            print(cmd)
            raise SystemExit(0)

raise SystemExit(1)
PY
}

find_issue_file() {
  local issue_id="$1"
  local f
  while IFS= read -r f; do
    if grep -q "^id: ${issue_id}$" "$f" 2>/dev/null; then
      echo "$f"
      return 0
    fi
  done < <(find LiNKdev -name "${issue_id}.md" -path '*/issues/*' 2>/dev/null)
  return 1
}

issue_id_from_report() {
  local rp="$1"
  basename "$rp" .md
}

run_script_gate() {
  local gate_id="$1"
  local script_rel="$2"
  shift 2
  local script_path="$ROOT/$script_rel"
  [[ -x "$script_path" ]] || chmod +x "$script_path" 2>/dev/null || true
  if "$script_path" "$@"; then
    log_ok "$gate_id"
  else
    log_fail "$gate_id ($script_rel $*)"
  fi
}

gate_secrets_scan() {
  local pat='(api[_-]?key|secret|password|private[_-]?key)\s*=\s*["\x27][^"\x27]{8,}'
  if rg -i "$pat" "$SCOPE" --glob '!.env' --glob '!*.example' 2>/dev/null; then
    log_fail "secrets_scan (possible secret assignment in $SCOPE)"
  else
    log_ok "secrets_scan"
  fi
}

gate_proof_block_present() {
  [[ -n "$REPORT" ]] || { log_skip "proof_block_present (no --report)"; return; }
  [[ -f "$REPORT" ]] || { log_fail "proof_block_present (missing $REPORT)"; return; }
  if python3 - <<'PY' "$REPORT"
import json, re, sys
from pathlib import Path

text = Path(sys.argv[1]).read_text()
m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
if not m:
    raise SystemExit("no proof json block")
data = json.loads(m.group(1))
acs = data.get("acceptance_criteria") or []
if not acs:
    raise SystemExit("acceptance_criteria empty")
for ac in acs:
    if not ac.get("verified"):
        raise SystemExit(f"AC not verified: {ac.get('id', '?')}")
print("proof block ok")
PY
  then
    log_ok "proof_block_present"
  else
    log_fail "proof_block_present ($REPORT)"
  fi
}

gate_allowed_files_respected() {
  [[ -n "$REPORT" ]] || { log_skip "allowed_files_respected (no --report)"; return; }
  local issue_id
  issue_id="$(issue_id_from_report "$REPORT")"
  local issue_file
  issue_file="$(find_issue_file "$issue_id" || true)"
  [[ -n "$issue_file" ]] || { log_skip "allowed_files_respected (issue file not found for $issue_id)"; return; }

  if python3 - <<'PY' "$issue_file" "$REPORT"
import fnmatch, re, subprocess, sys
from pathlib import Path

issue = Path(sys.argv[1]).read_text()
report = sys.argv[2]

def yaml_list(key):
    m = re.search(rf"^{key}:\n((?:  - .+\n)+)", issue, re.M)
    if not m:
        return []
    return [ln.strip()[2:].strip() for ln in m.group(1).splitlines()]

allowed = yaml_list("allowed_files")
prohibited = yaml_list("prohibited_files")
if not allowed:
    raise SystemExit("no allowed_files in issue")

proc = subprocess.run(["git", "diff", "--name-only", "HEAD"], capture_output=True, text=True)
files = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
proc2 = subprocess.run(["git", "diff", "--name-only", "--cached"], capture_output=True, text=True)
files += [ln.strip() for ln in proc2.stdout.splitlines() if ln.strip()]
files = sorted(set(files))

def matches(path, patterns):
    return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(path, p.lstrip("/")) for p in patterns)

violations = []
for f in files:
    if f == report:
        continue
    if prohibited and matches(f, prohibited):
        violations.append(f"prohibited: {f}")
        continue
    if not matches(f, allowed):
        violations.append(f"outside allowed_files: {f}")

if violations:
    print("\n".join(violations), file=sys.stderr)
    raise SystemExit(1)
print("allowed_files ok")
PY
  then
    log_ok "allowed_files_respected"
  else
    log_fail "allowed_files_respected"
  fi
}

gate_working_tree_clean() {
  [[ -n "$REPORT" ]] || { log_skip "working_tree_clean (no --report)"; return; }
  local dirty
  dirty="$(git status --porcelain | grep -v '^.. LiNKdev/.*/reports/' || true)"
  if [[ -n "$dirty" ]]; then
    echo "$dirty" >&2
    log_fail "working_tree_clean"
  else
    log_ok "working_tree_clean"
  fi
}

gate_integration_smoke() {
  local cmd=""
  cmd="$(stack_command_for_gate integration_smoke 2>/dev/null || true)"
  if [[ -z "$cmd" && -f package.json ]] && node -e "const p=require('./package.json'); process.exit(p.scripts&&p.scripts['test:smoke']?0:1)" 2>/dev/null; then
    cmd="npm run test:smoke"
  fi
  if [[ -z "$cmd" ]]; then
    log_skip "integration_smoke (no STACK.md command or package.json test:smoke)"
    return
  fi
  if eval "$cmd"; then
    log_ok "integration_smoke"
  else
    log_fail "integration_smoke ($cmd)"
  fi
}

gate_architecture_gate() {
  if ! stack_has_js_ts; then
    log_na "architecture_gate (STACK.md has no JS/TS languages)"
    return
  fi
  local cmd=""
  cmd="$(stack_command_for_gate architecture_gate 2>/dev/null || true)"
  if [[ -z "$cmd" && -f package.json ]] && node -e "const p=require('./package.json'); process.exit(p.scripts&&p.scripts.typecheck?0:1)" 2>/dev/null; then
    cmd="npm run typecheck"
  fi
  if [[ -z "$cmd" && -f tsconfig.json ]]; then
    cmd="npx tsc --noEmit -p tsconfig.json"
  fi
  if [[ -z "$cmd" ]]; then
    log_fail "architecture_gate (JS/TS stack but no typecheck command)"
    return
  fi
  if eval "$cmd"; then
    log_ok "architecture_gate"
  else
    log_fail "architecture_gate ($cmd)"
  fi
}

gate_ship_criteria_check() {
  [[ -f "$SHIP_CRITERIA" ]] || { log_fail "ship_criteria_check (missing $SHIP_CRITERIA)"; return; }
  if python3 - <<'PY' "$SHIP_CRITERIA"
import re, sys
from pathlib import Path

text = Path(sys.argv[1]).read_text()
open_items = []
for i, line in enumerate(text.splitlines(), 1):
    if re.match(r"^- \[ \]", line):
        if "Principal Release OK" in line:
            continue
        open_items.append(f"line {i}: {line.strip()}")
if open_items:
    print("\n".join(open_items), file=sys.stderr)
    raise SystemExit(1)
print("ship criteria ok")
PY
  then
    log_ok "ship_criteria_check"
  else
    log_fail "ship_criteria_check"
  fi
}

run_gate() {
  local gate_id="$1"
  local check_type="$2"
  local script_rel="${3:-}"
  shift 3 || true

  case "$gate_id" in
    secrets_scan) gate_secrets_scan; return ;;
    proof_block_present) gate_proof_block_present; return ;;
    allowed_files_respected) gate_allowed_files_respected; return ;;
    working_tree_clean) gate_working_tree_clean; return ;;
    integration_smoke) gate_integration_smoke; return ;;
    architecture_gate) gate_architecture_gate; return ;;
    ship_criteria_check) gate_ship_criteria_check; return ;;
  esac

  case "$check_type" in
    script)
      local args=()
      case "$gate_id" in
        validate_dag)
          args=("$(program_plan)")
          ;;
        program_proof_manifest)
          [[ -n "$PROGRAM" ]] || { log_fail "program_proof_manifest (no --program)"; return; }
          args=("$PROGRAM")
          ;;
        replay_merge_verify)
          [[ -n "$PROGRAM" ]] || { log_fail "replay_merge_verify (no --program)"; return; }
          args=("$PROGRAM")
          ;;
        council_g3_report)
          if [[ "$PROGRAM" == "bootstrap" ]]; then
            log_skip "council_g3_report (bootstrap historical program)"
            return
          fi
          local cr
          cr="$(council_report_path G3 || true)"
          [[ -n "$cr" ]] || { log_fail "council_g3_report (no G3 council-report.json found)"; return; }
          args=("$cr" --gate G3)
          ;;
        council_g4_report)
          if [[ "$PROGRAM" == "bootstrap" ]]; then
            log_skip "council_g4_report (bootstrap historical program)"
            return
          fi
          local cr
          cr="$(council_report_path G4 || true)"
          [[ -n "$cr" ]] || { log_fail "council_g4_report (no G4-release-report.json found)"; return; }
          args=("$cr" --gate G4)
          ;;
        verify_subset)
          if LINKDEV_SCOPE="$SCOPE" LINKDEV_SKIP_GATES=1 "$ROOT/$script_rel"; then
            log_ok "$gate_id"
          else
            log_fail "$gate_id ($script_rel)"
          fi
          return
          ;;
        verify_critical)
          if LINKDEV_SCOPE="." LINKDEV_TIER=critical LINKDEV_SKIP_GATES=1 "$ROOT/$script_rel"; then
            log_ok "$gate_id"
          else
            log_fail "$gate_id ($script_rel)"
          fi
          return
          ;;
        *)
          ;;
      esac
      run_script_gate "$gate_id" "$script_rel" "${args[@]}"
      ;;
    conditional|inline)
      run_gate "$gate_id" "inline" "" "$@"
      ;;
    *)
      log_fail "$gate_id (unknown check_type $check_type)"
      ;;
  esac
}

echo "== LiNKdev gates tier=$TIER scope=$SCOPE program=${PROGRAM:-—} report=${REPORT:-—} =="

GATE_IDS="$(python3 - <<'PY' "$CATALOG" "$TIER"
import json, sys
cat = json.load(open(sys.argv[1]))
tier = sys.argv[2]
for g in cat["tiers"][tier]["gates"]:
    print(g["id"] + "\t" + g["check_type"] + "\t" + g.get("script", ""))
PY
)"

while IFS=$'\t' read -r gate_id check_type script_rel; do
  [[ -n "$gate_id" ]] || continue
  run_gate "$gate_id" "$check_type" "$script_rel"
done <<< "$GATE_IDS"

echo "== gates summary tier=$TIER passed=$PASSED skipped=$SKIPPED failed=$FAILURES =="
[[ "$FAILURES" -eq 0 ]] || exit 1
exit 0
