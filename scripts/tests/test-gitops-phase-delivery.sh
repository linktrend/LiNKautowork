#!/usr/bin/env bash
# WP-01 Phase-delivery fixtures: checkpoint-only, phase PR rollup, risk exception,
# named-gate fail-closed (missing/zero/wrong-SHA/stale/neutral).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
fail() { echo "FAIL: $1" >&2; exit 1; }
pass() { echo "PASS: $1"; PASS=$((PASS + 1)); }

python3 - "$ROOT" <<'PY'
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT / "scripts" / "gitops"))

from delivery_modes import (
    DeliveryConfig,
    MODE_ISSUE_PR,
    MODE_PHASE_INTEGRATION,
    build_phase_delivery_record,
    checkpoint_opens_pr,
    load_delivery_config,
    named_gate_evidence,
    phase_ready_for_pr,
    should_open_pr_for_branch,
    validate_risk_class,
)
from packager_logic import is_allowed_work_branch

assert checkpoint_opens_pr() is False

# The shipped hosted profile defaults to Phase integration.
cfg = load_delivery_config(None, env={})
assert cfg.delivery_mode == MODE_PHASE_INTEGRATION

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    cfg_path = root / ".github" / "linktrend-delivery-mode.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "deliveryMode": "phase-integration",
                "phaseBranchPrefix": "phase/",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    phase_cfg = load_delivery_config(root, env={})
    assert phase_cfg.delivery_mode == MODE_PHASE_INTEGRATION
    # Environment variables cannot switch the frozen hosted profile.
    overridden = load_delivery_config(
        root, env={"LINKTREND_DELIVERY_MODE": "issue-pr"}
    )
    assert overridden.delivery_mode == MODE_PHASE_INTEGRATION

phase_cfg = DeliveryConfig(
    delivery_mode=MODE_PHASE_INTEGRATION, phase_branch_prefix="phase/"
)

# (b) Checkpoint never creates PR
d = should_open_pr_for_branch(
    "issue/1-alpha", phase_cfg, review_ready=False
)
assert d.open_pr is False and d.reason == "skipped_not_ready"

# Accepted Issue under phase mode without exception → no PR
d = should_open_pr_for_branch(
    "issue/1-alpha", phase_cfg, review_ready=True, risk_class=None
)
assert d.open_pr is False
assert d.reason == "skipped_phase_mode_issue_without_exception"

# (c) Explicit risk exception allows Issue PR without changing default mode
assert validate_risk_class("security") == "security"
assert validate_risk_class("not-a-class") is None
d = should_open_pr_for_branch(
    "issue/9-auth", phase_cfg, review_ready=True, risk_class="authentication"
)
assert d.open_pr is True and d.reason == "issue_pr_risk_exception"
assert d.risk_class == "authentication"

# Phase branch opens the single Phase PR
assert is_allowed_work_branch("phase/wp-01-demo")
d = should_open_pr_for_branch(
    "phase/wp-01-demo", phase_cfg, review_ready=True
)
assert d.open_pr is True and d.reason == "phase_branch_pr"

# Configurable phaseBranchPrefix must pass packager allow-filter (Bugbot #1)
custom_prefix = "wave/"
assert is_allowed_work_branch("wave/wp-01-demo", phase_branch_prefix=custom_prefix)
assert not is_allowed_work_branch("wave/wp-01-demo")  # default still phase/
custom_cfg = DeliveryConfig(
    delivery_mode=MODE_PHASE_INTEGRATION, phase_branch_prefix=custom_prefix
)
d = should_open_pr_for_branch("wave/wp-01-demo", custom_cfg, review_ready=True)
assert d.open_pr is True and d.reason == "phase_branch_pr"

# issue-pr mode unchanged
issue_cfg = DeliveryConfig(delivery_mode=MODE_ISSUE_PR)
d = should_open_pr_for_branch("issue/1-alpha", issue_cfg, review_ready=True)
assert d.open_pr is True and d.reason == "issue_pr_mode"

# (a) Two+ accepted Issue SHAs feed one Phase record / one Phase PR
sha_a = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
sha_b = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
base = "cccccccccccccccccccccccccccccccccccccccc"
head = "dddddddddddddddddddddddddddddddddddddddd"
accepted = [
    {"branch": "issue/1-alpha", "sha": sha_a, "accepted": True, "included": True},
    {"branch": "issue/2-beta", "sha": sha_b, "accepted": True, "included": True},
]
ok, detail = phase_ready_for_pr(accepted)
assert ok, detail

# Not ready when one SHA not included
ok2, _ = phase_ready_for_pr(
    [
        accepted[0],
        {"branch": "issue/2-beta", "sha": sha_b, "accepted": True, "included": False},
    ]
)
assert ok2 is False

from delivery_modes import validate_phase_delivery_record
import review_ready_dispatch as rrd

# Bugbot: Packager must validate Phase delivery record before Phase PR
ok_rec, det_rec = validate_phase_delivery_record(
    {
        "schemaVersion": 1,
        "deliveryMode": "phase-integration",
        "phaseBranch": "phase/wp-01-demo",
        "baseSha": base,
        "headSha": head,
        "mergeSha": None,
        "acceptedIssues": accepted,
        "namedGateEvidence": {
            "gate": "fast-gate",
            "sha": head,
            "status": "success",
            "detail": "ok",
            "checks": [],
        },
    },
    branch="phase/wp-01-demo",
    head_sha=head,
)
assert ok_rec, det_rec
ok_miss, det_miss = validate_phase_delivery_record(
    None, branch="phase/wp-01-demo", head_sha=head
)
assert ok_miss is False and det_miss == "phase_delivery_record_missing"
ok_inc, det_inc = validate_phase_delivery_record(
    {
        "schemaVersion": 1,
        "deliveryMode": "phase-integration",
        "phaseBranch": "phase/wp-01-demo",
        "baseSha": base,
        "headSha": head,
        "mergeSha": None,
        "acceptedIssues": [
            accepted[0],
            {
                "branch": "issue/2-beta",
                "sha": sha_b,
                "accepted": True,
                "included": False,
            },
        ],
        "namedGateEvidence": {
            "gate": "fast-gate",
            "sha": head,
            "status": "success",
            "detail": "ok",
            "checks": [],
        },
    },
    branch="phase/wp-01-demo",
    head_sha=head,
)
assert ok_inc is False and "issue_not_included" in det_inc

disc_src = (ROOT / "scripts" / "gitops" / "packager_discover.py").read_text(
    encoding="utf-8"
)
assert "validate_phase_delivery_record" in disc_src
assert "fetch_phase_delivery_record" in disc_src
assert "skipped_phase_delivery" in disc_src

# App-backed Phase tip eligibility without weakening issue safeguards
assert rrd.is_app_backed_issue_branch("issue/81-wp-01-demo")
assert not rrd.is_app_backed_issue_branch("phase/wp-01-demo")
assert rrd.is_app_backed_phase_branch("phase/wp-01-demo")
assert rrd.is_app_backed_publish_branch("phase/wp-01-demo")
assert not rrd.is_app_backed_publish_branch("feature/81-x")
assert rrd.is_app_backed_phase_branch("wave/wp-01-demo", phase_prefix="wave/")
phase_dispatch = rrd.validate_dispatch_inputs(
    branch="phase/wp-01-demo",
    sha=head,
    github_repository="linktrend/IDE-Development",
)
assert phase_dispatch.branch_kind == "phase"
assert phase_dispatch.issue_number == 0

gate = named_gate_evidence(
    gate="fast-gate",
    sha=head,
    checks=[
        {"name": "Verify IDE Development", "state": "SUCCESS", "completedAt": "t1"},
        {
            "name": "Enforce allowed PR source branches",
            "state": "SUCCESS",
            "completedAt": "t2",
        },
    ],
    required=["Verify IDE Development", "Enforce allowed PR source branches"],
    expected_sha=head,
)
assert gate["status"] == "success"

record = build_phase_delivery_record(
    phase_branch="phase/wp-01-demo",
    base_sha=base,
    head_sha=head,
    accepted_issues=accepted,
    named_gate=gate,
    merge_sha=None,
    phase_pr={
        "number": 101,
        "url": "https://example.test/pr/101",
        "base": "development",
    },
)
assert record["deliveryMode"] == "phase-integration"
assert record["phasePr"]["number"] == 101
assert len(record["acceptedIssues"]) == 2
assert record["mergeSha"] is None

# Exactly one Phase PR represented (fixture invariant)
assert "phasePr" in record and isinstance(record["phasePr"]["number"], int)

# (d) Named-gate fail-closed cases
def assert_fail(evidence, needle):
    assert evidence["status"] != "success", evidence
    assert needle in evidence["detail"], evidence

assert_fail(
    named_gate_evidence(
        gate="fast-gate",
        sha=head,
        checks=[],
        required=["Verify IDE Development"],
    ),
    "missing",
)
assert_fail(
    named_gate_evidence(
        gate="fast-gate",
        sha=head,
        checks=[{"name": "Verify IDE Development", "state": "SUCCESS"}],
        required=[],
    ),
    "empty",
)
assert_fail(
    named_gate_evidence(
        gate="fast-gate",
        sha="0" * 40,
        checks=[{"name": "Verify IDE Development", "state": "SUCCESS"}],
        required=["Verify IDE Development"],
    ),
    "invalid_or_zero_sha",
)
assert_fail(
    named_gate_evidence(
        gate="fast-gate",
        sha=head,
        checks=[{"name": "Verify IDE Development", "state": "SUCCESS"}],
        required=["Verify IDE Development"],
        expected_sha=sha_a,
    ),
    "wrong_sha",
)
assert_fail(
    named_gate_evidence(
        gate="fast-gate",
        sha=head,
        checks=[{"name": "Verify IDE Development", "state": "SUCCESS"}],
        required=["Verify IDE Development"],
        expected_sha=head,
        stale_event=True,
    ),
    "stale_event_head",
)
assert_fail(
    named_gate_evidence(
        gate="fast-gate",
        sha=head,
        checks=[{"name": "Verify IDE Development", "state": "NEUTRAL"}],
        required=["Verify IDE Development"],
        expected_sha=head,
    ),
    "NEUTRAL",
)
assert_fail(
    named_gate_evidence(
        gate="fast-gate",
        sha=head,
        checks=[{"name": "Verify IDE Development", "state": "SKIPPED"}],
        required=["Verify IDE Development"],
        expected_sha=head,
    ),
    "SKIPPED",
)

# allowNeutral=True: NEUTRAL/SKIPPED count as success (Bugbot #2)
neutral_ok = named_gate_evidence(
    gate="fast-gate",
    sha=head,
    checks=[{"name": "Verify IDE Development", "state": "NEUTRAL"}],
    required=["Verify IDE Development"],
    expected_sha=head,
    allow_neutral=True,
)
assert neutral_ok["status"] == "success", neutral_ok
skipped_ok = named_gate_evidence(
    gate="fast-gate",
    sha=head,
    checks=[{"name": "Verify IDE Development", "state": "SKIPPED"}],
    required=["Verify IDE Development"],
    expected_sha=head,
    allow_neutral=True,
)
assert skipped_ok["status"] == "success", skipped_ok
# allowNeutral must not open the door to hard failures
assert_fail(
    named_gate_evidence(
        gate="fast-gate",
        sha=head,
        checks=[{"name": "Verify IDE Development", "state": "FAILURE"}],
        required=["Verify IDE Development"],
        expected_sha=head,
        allow_neutral=True,
    ),
    "FAILURE",
)

# Persist fixture evidence artifact for verifier focus
out = ROOT / "docs" / "validation" / "wp01-phase-delivery"
out.mkdir(parents=True, exist_ok=True)
(out / "phase-delivery-record.json").write_text(
    json.dumps(record, indent=2) + "\n", encoding="utf-8"
)
(out / "named-gate-fail-closed.json").write_text(
    json.dumps(
        {
            "missing": named_gate_evidence(
                gate="fast-gate",
                sha=head,
                checks=[],
                required=["Verify IDE Development"],
            ),
            "zero_sha": named_gate_evidence(
                gate="fast-gate",
                sha="0" * 40,
                checks=[{"name": "Verify IDE Development", "state": "SUCCESS"}],
                required=["Verify IDE Development"],
            ),
            "wrong_sha": named_gate_evidence(
                gate="fast-gate",
                sha=head,
                checks=[{"name": "Verify IDE Development", "state": "SUCCESS"}],
                required=["Verify IDE Development"],
                expected_sha=sha_a,
            ),
            "stale": named_gate_evidence(
                gate="fast-gate",
                sha=head,
                checks=[{"name": "Verify IDE Development", "state": "SUCCESS"}],
                required=["Verify IDE Development"],
                expected_sha=head,
                stale_event=True,
            ),
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print("phase-delivery unit fixtures ok")
PY
pass "phase delivery unit fixtures (checkpoint/phase/risk/gates)"

# Allowlist accepts phase/* and custom phaseBranchPrefix (Bugbot #3)
# shellcheck source=scripts/gitops/work-branch-allowlist.sh
source "$ROOT/scripts/gitops/work-branch-allowlist.sh"
is_allowed_work_branch "phase/wp-01-demo" || fail "phase/* must be allowed"
is_allowed_work_branch "issue/1-x" || fail "issue/* must remain allowed"
! is_allowed_work_branch "development" || fail "development must stay disallowed"
pass "work-branch allowlist includes phase/*"

# Custom prefix via env (same helper used by branch-source-policy CI)
(
  export LINKTREND_PHASE_BRANCH_PREFIX="wave/"
  # shellcheck source=scripts/gitops/work-branch-allowlist.sh
  source "$ROOT/scripts/gitops/work-branch-allowlist.sh"
  is_allowed_work_branch "wave/wp-01-demo" || fail "custom wave/* must be allowed when configured"
  ! is_allowed_work_branch "phase/wp-01-demo" || fail "default phase/* must not pass when prefix is wave/"
)
pass "work-branch allowlist honors custom phaseBranchPrefix"

# Contract + schema present
[ -f "$ROOT/docs/contracts/DELIVERY-MODES.md" ] || fail "missing DELIVERY-MODES.md"
[ -f "$ROOT/core/managed-core/schemas/delivery-modes.schema.json" ] || fail "missing schema"
grep -q 'phase-integration' "$ROOT/docs/contracts/DELIVERY-MODES.md" || fail "contract missing mode"
grep -q 'Linktrend Full Suite' "$ROOT/docs/contracts/DELIVERY-MODES.md" || fail "contract missing full-suite path"
grep -q 'Linktrend Branch Source Policy' "$ROOT/.github/workflows/branch-source-policy.yml" || fail "missing branch-source-policy workflow"
pass "delivery-mode contract and schema present"

echo "test-gitops-phase-delivery: OK ($PASS checks)"
