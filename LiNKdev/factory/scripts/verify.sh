#!/usr/bin/env bash
# LiNKdev mechanical verify (subset of UBS — DS-B1, B6).
set -euo pipefail

TIER="${LINKDEV_TIER:-standard}"
SCOPE="${LINKDEV_SCOPE:-LiNKdev}"
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

fail() { echo "VERIFY FAIL: $*" >&2; exit 1; }
ok() { echo "VERIFY OK: $*"; }

echo "== LiNKdev verify (tier=$TIER scope=$SCOPE) =="

# 1. STATE JSON valid if present
STATE_FILE="LiNKdev/factory/STATE.md"
if [[ -f "$STATE_FILE" ]]; then
  python3 - <<'PY' "$STATE_FILE" || fail "STATE.md JSON invalid"
import json, re, sys
text = open(sys.argv[1]).read()
m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
if not m:
    sys.exit("no json block")
json.loads(m.group(1))
print("state json ok")
PY
fi

# 2. Secret patterns in scope (staged + scope tree)
SECRET_PAT='(api[_-]?key|secret|password|private[_-]?key)\s*=\s*["\x27][^"\x27]{8,}'
if rg -i "$SECRET_PAT" "$SCOPE" --glob '!.env' --glob '!*.example' 2>/dev/null; then
  fail "possible secret assignment in $SCOPE"
fi
ok "no obvious secret assignments in $SCOPE"

# 3. Scripts executable and shellcheck if available
for s in LiNKdev/factory/scripts/*.sh; do
  [[ -f "$s" ]] || continue
  [[ -x "$s" ]] || fail "$s not executable"
  if command -v shellcheck >/dev/null 2>&1; then
    shellcheck -x "$s" || fail "shellcheck $s"
  fi
done
DISPATCH_MJS="LiNKdev/factory/scripts/dispatch-cursor-agent.mjs"
[[ -f "$DISPATCH_MJS" ]] || fail "missing $DISPATCH_MJS"
if command -v node >/dev/null 2>&1; then
  node --check "$DISPATCH_MJS" || fail "dispatch-cursor-agent.mjs syntax"
fi
ok "scripts present"

# 3b. Dispatch workflow templates
for wf in linkdev-dispatch.yml linkdev-guard.yml branch-source-policy.yml linkdev-planner-bootstrap.yml linkdev-orchestrator-bootstrap.yml; do
  [[ -f "LiNKdev/factory/install/github/${wf}" ]] || fail "missing workflow template ${wf}"
done
if command -v python3 >/dev/null 2>&1; then
  python3 - <<'PY' || fail "workflow YAML parse"
import pathlib, sys
try:
    import yaml
except ImportError:
    print("workflow yaml: skip (no PyYAML)")
    sys.exit(0)
for p in pathlib.Path("LiNKdev/factory/install/github").glob("*.yml"):
    yaml.safe_load(p.read_text())
print("workflow yaml ok")
PY
fi
ok "dispatch workflow templates"

# 4. JSON schemas parse
for j in LiNKdev/factory/contracts/*.json LiNKdev/factory/gates/catalog.json; do
  [[ -f "$j" ]] || continue
  python3 -c "import json; json.load(open('$j'))" || fail "invalid json $j"
done
ok "contracts json valid"

# 5. Critical tier extras
if [[ "$TIER" == "critical" ]]; then
  if ! LiNKdev/factory/scripts/validate-dag.sh LiNKdev/factory/programs/bootstrap/PROGRAM.md 2>/dev/null; then
    fail "DAG validation failed (critical tier)"
  fi
  ok "critical: DAG re-validated"
fi

echo "== verify passed =="

# Optional tier-A gates (package B) — skip when invoked from run-gates verify_subset
if [[ "${LINKDEV_SKIP_GATES:-}" != "1" ]]; then
  if [[ -n "${LINKDEV_RUN_GATES:-}" ]] || [[ "$TIER" == "standard" ]]; then
    GATE_ARGS=(--tier A --scope "$SCOPE")
    [[ -n "${LINKDEV_REPORT:-}" ]] && GATE_ARGS+=(--report "$LINKDEV_REPORT")
    [[ -n "${LINKDEV_PROGRAM:-}" ]] && GATE_ARGS+=(--program "$LINKDEV_PROGRAM")
    if ! LiNKdev/factory/scripts/run-gates.sh "${GATE_ARGS[@]}"; then
      fail "tier A gates failed"
    fi
    ok "tier A gates passed"
  fi
fi

exit 0
