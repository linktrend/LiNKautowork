#!/usr/bin/env python3
"""One-time fail-closed bootstrap for the defective v2.3.8 Review Ready publisher.

Replaces a predecessor whose trusted flag sat on input validation instead of the
publish/withdraw step. Must not call that defective publisher, create a new PR,
push directly to a protected branch, weaken a ruleset, permit Worker self-merge,
or reuse stale evidence.

Positive path: an already-open exact-head PR owned by an authorized Integrator
installs the correction through normal protected checks. When ``Linktrend Review
Ready`` is a live required context, founder authorization is required and the
before/after rule state is recorded. This module is a planner/validator only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from typing import Any

TRUSTED_FLAG = "LINKTREND_TRUSTED_REVIEW_READY_PUBLISHER"
REVIEW_READY_CONTEXT = "Linktrend Review Ready"
PROTECTED_BRANCHES = frozenset({"development", "staging", "main"})
INTEGRATOR_ROLES = frozenset({"integrator"})
WORKER_ROLES = frozenset({"worker", "implementer"})
PUBLISH_MARKERS = (
    "publish_review_ready",
    "withdraw_sha",
    "readiness_status as rs",
    "Verify remote tip equals immutable SHA",
)
STEP_SPLIT = re.compile(r"\n(?=      - name:)")
FLAG_RE = re.compile(
    r"LINKTREND_TRUSTED_REVIEW_READY_PUBLISHER:\s*[\"']?1[\"']?"
)
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class BootstrapError(ValueError):
    """Fail-closed bootstrap rejection with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PublisherStep:
    name: str
    has_trusted_flag: bool
    is_publish_step: bool


@dataclass
class BootstrapRequest:
    actor_role: str
    requested_head_sha: str
    evidence_head_sha: str
    installed_workflow: str
    corrected_workflow: str
    pr: dict[str, Any] | None = None
    create_new_pr: bool = False
    direct_protected_push: bool = False
    required_checks: list[str] = field(default_factory=list)
    passing_checks: list[str] = field(default_factory=list)
    required_contexts: list[str] = field(default_factory=list)
    founder_authorized: bool = False
    call_publisher: bool = False
    reuse_stale_evidence: bool = False
    weaken_ruleset: bool = False
    worker_self_merge: bool = False


def inspect_publisher_steps(workflow_text: str) -> list[PublisherStep]:
    """Split workflow YAML on step names and classify trusted-flag placement."""
    steps: list[PublisherStep] = []
    if not workflow_text:
        return steps
    for block in STEP_SPLIT.split(workflow_text):
        match = re.search(r"- name:\s*(.+)", block)
        if not match:
            continue
        name = match.group(1).strip()
        has_flag = bool(FLAG_RE.search(block))
        publishes = "run:" in block and any(marker in block for marker in PUBLISH_MARKERS)
        steps.append(
            PublisherStep(
                name=name, has_trusted_flag=has_flag, is_publish_step=publishes
            )
        )
    return steps


def publisher_defect(workflow_text: str) -> dict[str, Any]:
    """Describe whether the installed workflow is the defective v2.3.8 publisher."""
    steps = inspect_publisher_steps(workflow_text)
    flag_on_publish = any(s.is_publish_step and s.has_trusted_flag for s in steps)
    flag_on_other = any((not s.is_publish_step) and s.has_trusted_flag for s in steps)
    publish_steps = [s.name for s in steps if s.is_publish_step]
    flagged = [s.name for s in steps if s.has_trusted_flag]
    defective = bool(flag_on_other and not flag_on_publish)
    corrected = bool(flag_on_publish and not flag_on_other)
    return {
        "defective": defective,
        "corrected": corrected,
        "flagOnPublish": flag_on_publish,
        "flagOnUnrelatedSteps": flag_on_other,
        "publishSteps": publish_steps,
        "flaggedSteps": flagged,
        "stepCount": len(steps),
    }


def _reject(code: str, message: str) -> None:
    raise BootstrapError(code, message)


def _normalize_sha(raw: str, *, field: str) -> str:
    tip = (raw or "").strip().lower()
    if not tip or not FULL_SHA_RE.fullmatch(tip):
        _reject(f"{field}_not_immutable", f"{field} must be a 40-char SHA")
    return tip


def evaluate_bootstrap(req: BootstrapRequest) -> dict[str, Any]:
    """Validate a one-time bootstrap plan. Raises BootstrapError on reject."""
    role = (req.actor_role or "").strip().lower()
    if role in WORKER_ROLES or req.worker_self_merge:
        _reject("worker_self_use", "bootstrap rejects Worker self-use and self-merge")
    if role not in INTEGRATOR_ROLES:
        _reject("actor_not_integrator", "bootstrap requires an authorized Integrator")
    if req.create_new_pr or req.pr is None:
        _reject("new_pr_forbidden", "bootstrap rejects a newly invented PR")
    if req.direct_protected_push:
        _reject(
            "direct_protected_push",
            "bootstrap rejects a direct push to a protected branch",
        )
    if req.weaken_ruleset:
        _reject("ruleset_weaken_forbidden", "bootstrap must not weaken a ruleset")
    if req.call_publisher:
        _reject(
            "defective_publisher_forbidden",
            "bootstrap must not call the defective v2.3.8 publisher",
        )

    sha = _normalize_sha(req.requested_head_sha, field="requested_head_sha")
    evidence_sha = _normalize_sha(req.evidence_head_sha, field="evidence_head_sha")
    if req.reuse_stale_evidence or evidence_sha != sha:
        _reject(
            "stale_evidence",
            "bootstrap rejects stale evidence; evidence headSha must equal the PR head",
        )

    pr = req.pr or {}
    head = _normalize_sha(str(pr.get("head_sha") or ""), field="pr_head_sha")
    if head != sha:
        _reject("changed_head", "bootstrap rejects a changed PR head")
    branch = str(pr.get("head_branch") or "").strip()
    if not branch:
        _reject("pr_branch_missing", "existing PR must name a head branch")
    if branch in PROTECTED_BRANCHES or branch.split("/", 1)[0] in PROTECTED_BRANCHES:
        _reject("pr_protected_head", "bootstrap PR head must not be a protected branch")
    state = str(pr.get("state") or "open").strip().lower()
    if state != "open":
        _reject("pr_not_open", "bootstrap requires an already-open PR")

    required = [str(c) for c in req.required_checks]
    passing = set(str(c) for c in req.passing_checks)
    missing_checks = [c for c in required if c not in passing]
    if missing_checks:
        _reject(
            "missing_required_checks",
            "bootstrap rejects missing required checks: " + ",".join(missing_checks),
        )

    defect = publisher_defect(req.installed_workflow)
    if not defect["defective"]:
        _reject(
            "predecessor_not_defective",
            "bootstrap is only for the defective v2.3.8 publisher placement",
        )
    corrected = publisher_defect(req.corrected_workflow)
    if not corrected["corrected"]:
        _reject(
            "correction_invalid",
            "corrected workflow must place the trusted flag only on publish/withdraw",
        )

    contexts = [str(c) for c in req.required_contexts]
    review_ready_required = REVIEW_READY_CONTEXT in contexts
    rule_before = list(contexts)
    rule_after = list(contexts)
    if review_ready_required and not req.founder_authorized:
        _reject(
            "founder_authorization_required",
            "live required Linktrend Review Ready context needs founder authorization",
        )

    mark_ready = not review_ready_required
    return {
        "ok": True,
        "action": "use_existing_pr",
        "callPublisher": False,
        "directProtectedPush": False,
        "workerSelfMerge": False,
        "markDraftReady": mark_ready,
        "installViaExistingPr": True,
        "rerunUnchangedFull": False,
        "reviewReadyRequired": review_ready_required,
        "founderAuthorized": bool(req.founder_authorized) if review_ready_required else False,
        "ruleStateBefore": rule_before,
        "ruleStateAfter": rule_after,
        "headSha": sha,
        "headBranch": branch,
        "prNumber": pr.get("number"),
        "defect": defect,
    }


def request_from_dict(raw: dict[str, Any]) -> BootstrapRequest:
    return BootstrapRequest(
        actor_role=str(raw.get("actor_role") or ""),
        requested_head_sha=str(raw.get("requested_head_sha") or ""),
        evidence_head_sha=str(raw.get("evidence_head_sha") or ""),
        installed_workflow=str(raw.get("installed_workflow") or ""),
        corrected_workflow=str(raw.get("corrected_workflow") or ""),
        pr=raw.get("pr") if isinstance(raw.get("pr"), dict) else None,
        create_new_pr=bool(raw.get("create_new_pr")),
        direct_protected_push=bool(raw.get("direct_protected_push")),
        required_checks=list(raw.get("required_checks") or []),
        passing_checks=list(raw.get("passing_checks") or []),
        required_contexts=list(raw.get("required_contexts") or []),
        founder_authorized=bool(raw.get("founder_authorized")),
        call_publisher=bool(raw.get("call_publisher")),
        reuse_stale_evidence=bool(raw.get("reuse_stale_evidence")),
        weaken_ruleset=bool(raw.get("weaken_ruleset")),
        worker_self_merge=bool(raw.get("worker_self_merge")),
    )


def cmd_evaluate(args: argparse.Namespace) -> int:
    payload = json.loads(Path_read(args.state_json))
    try:
        result = evaluate_bootstrap(request_from_dict(payload))
    except BootstrapError as exc:
        print(json.dumps({"ok": False, "error": exc.code, "detail": exc.message}, indent=2))
        return 78
    print(json.dumps(result, indent=2))
    return 0


def Path_read(path: str) -> str:
    from pathlib import Path

    return Path(path).read_text(encoding="utf-8")


def _self_test() -> int:
    defective = """
jobs:
  publish:
    steps:
      - name: Validate dispatch inputs
        env:
          LINKTREND_TRUSTED_REVIEW_READY_PUBLISHER: "1"
        run: python3 scripts/gitops/review_ready_dispatch.py validate
      - name: Verify remote tip equals immutable SHA; publish or withdraw
        run: |
          import readiness_status as rs
          rs.publish_review_ready(sha, "1")
"""
    corrected = """
jobs:
  publish:
    steps:
      - name: Validate dispatch inputs
        run: python3 scripts/gitops/review_ready_dispatch.py validate
      - name: Verify remote tip equals immutable SHA; publish or withdraw
        env:
          LINKTREND_TRUSTED_REVIEW_READY_PUBLISHER: "1"
        run: |
          import readiness_status as rs
          rs.publish_review_ready(sha, "1")
          rs.withdraw_sha(sha)
"""
    sha = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    base = BootstrapRequest(
        actor_role="integrator",
        requested_head_sha=sha,
        evidence_head_sha=sha,
        installed_workflow=defective,
        corrected_workflow=corrected,
        pr={"number": 12, "head_sha": sha, "head_branch": "issue/12-fix", "state": "open"},
        required_checks=["Linktrend Fast Checks"],
        passing_checks=["Linktrend Fast Checks"],
        required_contexts=["Linktrend Fast Checks"],
    )
    ok = evaluate_bootstrap(base)
    assert ok["ok"] is True
    assert ok["callPublisher"] is False
    assert ok["markDraftReady"] is True

    failures: list[str] = []

    def expect(code: str, **updates: Any) -> None:
        data = asdict(base)
        data.update(updates)
        try:
            evaluate_bootstrap(BootstrapRequest(**data))
            failures.append(f"expected {code}")
        except BootstrapError as exc:
            if exc.code != code:
                failures.append(f"expected {code}, got {exc.code}")

    expect("worker_self_use", actor_role="worker")
    expect("new_pr_forbidden", create_new_pr=True)
    expect(
        "changed_head",
        pr={
            "number": 12,
            "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "head_branch": "issue/12-fix",
            "state": "open",
        },
    )
    expect("missing_required_checks", passing_checks=[])
    expect("direct_protected_push", direct_protected_push=True)
    expect(
        "founder_authorization_required",
        required_contexts=[REVIEW_READY_CONTEXT, "Linktrend Fast Checks"],
        founder_authorized=False,
    )
    expect("stale_evidence", evidence_head_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    expect("defective_publisher_forbidden", call_publisher=True)

    founder = asdict(base)
    founder["required_contexts"] = [REVIEW_READY_CONTEXT]
    founder["founder_authorized"] = True
    plan = evaluate_bootstrap(BootstrapRequest(**founder))
    if plan["markDraftReady"] is not False:
        failures.append("required Review Ready must not auto mark-ready")
    if plan["ruleStateBefore"] != [REVIEW_READY_CONTEXT]:
        failures.append("missing before rule state")

    if failures:
        print(json.dumps({"ok": False, "failures": failures}, indent=2))
        return 1
    print(json.dumps({"ok": True, "tests": "review_ready_publisher_bootstrap.self_test"}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ev = sub.add_parser("evaluate", help="Evaluate a bootstrap state JSON file")
    ev.add_argument("--state-json", required=True)
    sub.add_parser("self-test", help="Run built-in unit checks")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "self-test":
        return _self_test()
    if args.cmd == "evaluate":
        return cmd_evaluate(args)
    print(f"unknown command {args.cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
