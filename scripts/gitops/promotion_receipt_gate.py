#!/usr/bin/env python3
"""Fail-closed receipt and promotion decisions for the thin GitHub fallback.

This module is deliberately side-effect free for receipt, gate, approval, and
duplicate-candidate decisions.  The only mutating helper is ``cancel_obsolete``;
it sends non-blocking GitHub run-cancel requests and never waits for completion.
No command in this file creates a PR, merges, promotes, or applies a ruleset.
Receipt verification itself requires no credential.  A later trusted workflow
boundary may use GitHub's built-in ``GITHUB_TOKEN`` only with explicit
least-privilege read permissions; it must not mint or consume the former
custom-App token here.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from coordinator.receipts import (  # noqa: E402
    CandidateIdentity,
    ReceiptError,
    canonical_digest as receipt_canonical_digest,
    compute_candidate_identity,
    compute_receipt_digest,
    load_json,
    receipt_lookup_key,
    verify_receipt,
)


SHA40 = set("0123456789abcdef")
PROMOTION_STATES = {"queued", "in_progress", "waiting", "requested"}


@dataclass(frozen=True)
class Decision:
    accepted: bool
    code: str
    detail: str
    source_commit: str | None = None
    promotion_commit: str | None = None
    receipt_lookup_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "accepted": self.accepted,
            "status": "PASS" if self.accepted else "HOLD",
            "code": self.code,
            "detail": self.detail,
        }
        if self.source_commit is not None:
            result["sourceCommit"] = self.source_commit
        if self.promotion_commit is not None:
            result["promotionCommit"] = self.promotion_commit
        if self.receipt_lookup_key is not None:
            result["receiptLookupKey"] = self.receipt_lookup_key
        return result


def _sha(value: Any) -> str:
    value = str(value or "").strip().lower()
    return value if len(value) == 40 and set(value) <= SHA40 else ""


def _field(payload: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in payload:
            return payload[name]
    return None


def canonical_digest(payload: Mapping[str, Any]) -> str:
    """Return the receipt-compatible canonical SHA-256 binding.

    Receipt and promotion code must hash identical canonical bytes.  Keeping
    this compatibility export avoids changing callers while preventing the
    old promotion-only JSON encoding from producing a different digest.
    """

    return receipt_canonical_digest(payload)


def verify_receipt_payload(
    receipt: Mapping[str, Any],
    candidate_identity: Mapping[str, Any] | CandidateIdentity,
    required_gate: str,
    **verification: Any,
) -> Decision:
    verdict = verify_receipt(receipt, candidate_identity, required_gate, **verification)
    detail = verdict.message or verdict.code
    if verdict.accepted and verdict.source_commit and verdict.promotion_commit:
        detail = f"{detail}; sourceCommit={verdict.source_commit}; promotionCommit={verdict.promotion_commit}"
    lookup_key = None
    if verdict.accepted:
        lookup_key = receipt_lookup_key(receipt)
    return Decision(
        bool(verdict),
        verdict.code,
        detail,
        source_commit=verdict.source_commit,
        promotion_commit=verdict.promotion_commit,
        receipt_lookup_key=lookup_key,
    )


def verify_receipt_file(
    receipt_path: str | Path,
    *,
    identity_path: str | Path | None = None,
    repo_path: str | Path | None = None,
    dependencies: Sequence[str] = (),
    profile: str = "full",
    required_gate: str = "full-gate",
    profile_files: Sequence[str] = (),
    workflow_files: Sequence[str] | None = None,
    workflow_run_id: int | None = None,
    workflow_run_attempt: int | None = None,
    workflow_head_commit: str | None = None,
    runner_label: str | None = None,
    expected_command_digest: str | None = None,
    expected_workflow_digest: str | None = None,
    expected_evidence_digests: Mapping[str, str] | None = None,
) -> Decision:
    try:
        receipt = load_json(receipt_path)
        if identity_path is not None:
            identity = load_json(identity_path)
        elif repo_path is not None:
            identity = compute_candidate_identity(
                repo_path,
                dependencies,
                profile,
                profile_files=profile_files,
                workflow_files=workflow_files,
            )
        else:
            return Decision(False, "identity_missing", "candidate identity or checkout is required")
        return verify_receipt_payload(
            receipt,
            identity,
            required_gate,
            workflow_run_id=workflow_run_id,
            workflow_run_attempt=workflow_run_attempt,
            workflow_head_commit=workflow_head_commit,
            runner_label=runner_label,
            expected_command_digest=expected_command_digest,
            expected_workflow_digest=expected_workflow_digest,
            expected_evidence_digests=expected_evidence_digests,
        )
    except (ReceiptError, OSError, ValueError) as exc:
        code = getattr(exc, "code", "invalid_receipt")
        return Decision(False, str(code), str(exc))


def evaluate_development_gates(payload: Mapping[str, Any], expected_head_sha: str) -> Decision:
    """Require exact seal, fast, Bugbot, and full/not-required on one head."""
    head = _sha(expected_head_sha)
    if not head:
        return Decision(False, "invalid_head", "expected development head SHA is invalid")
    aliases = {
        "seal": ("seal", "sealed", "phaseReady"),
        "fast": ("fast", "fastGate", "fast-gate"),
        "bugbot": ("bugbot", "cursorBugbot", "Cursor Bugbot"),
        "full": ("full", "fullSuite", "full-gate"),
    }
    for name, keys in aliases.items():
        row = next((payload[key] for key in keys if key in payload), None)
        if not isinstance(row, Mapping):
            return Decision(False, f"{name}_missing", f"{name} result is missing")
        status = str(_field(row, "status", "state", "conclusion") or "").strip().lower()
        if name == "full" and status in {"not-required", "not_required", "not required"}:
            continue
        if status not in {"passed", "success", "successful", "green"}:
            return Decision(False, f"{name}_not_passed", f"{name} result is {status or 'missing'}")
        observed = _sha(_field(row, "sha", "headSha", "sourceSha"))
        if not observed or observed != head:
            return Decision(False, f"{name}_stale", f"{name} is not bound to the exact sealed head")
    return Decision(True, "accepted", "exact seal, fast, Bugbot, and full/not-required gates passed")


def evaluate_main_approval(
    approval: Mapping[str, Any],
    *,
    source_sha: str,
    base_sha: str,
    pr_head_sha: str,
    receipt: Mapping[str, Any] | None = None,
) -> Decision:
    """Bind principal approval to source, base, PR head, and exact receipt."""
    expected = {
        "sourceSha": _sha(source_sha),
        "baseSha": _sha(base_sha),
        "prHeadSha": _sha(pr_head_sha),
    }
    if not all(expected.values()):
        return Decision(False, "invalid_binding", "approval binding SHA is malformed")
    for key, names in {
        "sourceSha": ("sourceSha", "stagingSha", "expectedStagingSha"),
        "baseSha": ("baseSha", "mainSha", "expectedMainSha"),
        "prHeadSha": ("prHeadSha", "promotionHeadSha", "expectedPromoteHead"),
    }.items():
        if _sha(_field(approval, *names)) != expected[key]:
            return Decision(False, f"stale_{key}", f"approval is not bound to current {key}")

    if receipt is None:
        return Decision(False, "receipt_missing", "main approval must include a receipt binding")
    try:
        receipt_digest = compute_receipt_digest(receipt)
        lookup_key = receipt_lookup_key(receipt)
    except ReceiptError as exc:
        return Decision(False, "receipt_mismatch", str(exc))
    bound_digest = str(_field(approval, "receiptDigest", "receiptSha256") or "").strip()
    if bound_digest and bound_digest != receipt_digest:
        return Decision(False, "receipt_mismatch", "approval receipt digest does not match")
    bound_identity = _field(approval, "receiptIdentity")
    if bound_identity is not None and bound_identity != receipt.get("candidateIdentity"):
        return Decision(False, "receipt_mismatch", "approval receipt identity does not match")
    if not bound_digest and bound_identity is None:
        return Decision(False, "receipt_unbound", "approval has no exact receipt digest or identity binding")
    return Decision(True, "accepted", f"approval is bound to source, base, PR head, and receipt {lookup_key}")


def evaluate_release_path(payload: Mapping[str, Any]) -> Decision:
    """Require a short release gate and explicitly prohibit a full-suite rerun."""
    if bool(payload.get("fullSuiteInvoked")):
        return Decision(False, "full_suite_reentered", "staging/main promotion must reuse the matching receipt")
    status = str(_field(payload, "status", "state", "conclusion") or "").strip().lower()
    if status not in {"passed", "success", "successful", "green"}:
        return Decision(False, "release_gate_not_passed", "short release checks did not pass")
    profile = str(payload.get("testProfile") or "release").strip().lower()
    if profile != "release":
        return Decision(False, "release_profile_required", "promotion release checks must use the release profile")
    return Decision(True, "accepted", "short release checks passed without a full-suite rerun")


def evaluate_automatic_main(
    *,
    release: Mapping[str, Any],
    required_receipt: Mapping[str, Any],
    candidate_identity: Mapping[str, Any] | CandidateIdentity,
    workflow_run_id: int | None = None,
    workflow_run_attempt: int | None = None,
    workflow_head_commit: str | None = None,
    runner_label: str | None = None,
) -> Decision:
    """Automatic main is still gate- and receipt-bound; mode changes no gates."""
    release_decision = evaluate_release_path(release)
    if not release_decision.accepted:
        return release_decision
    receipt_decision = verify_receipt_payload(
        required_receipt,
        candidate_identity,
        "full-gate",
        workflow_run_id=workflow_run_id,
        workflow_run_attempt=workflow_run_attempt,
        workflow_head_commit=workflow_head_commit,
        runner_label=runner_label,
    )
    if not receipt_decision.accepted:
        return receipt_decision
    return Decision(
        True,
        "accepted",
        f"automatic main passed release gate and exact receipt verification; {receipt_decision.detail}",
        source_commit=receipt_decision.source_commit,
        promotion_commit=receipt_decision.promotion_commit,
        receipt_lookup_key=receipt_decision.receipt_lookup_key,
    )


def select_promotion_candidate(
    candidates: Sequence[Mapping[str, Any]], *, source_sha: str, target_sha: str, branch: str
) -> dict[str, Any]:
    """Select one exact open candidate; duplicates are an explicit block."""
    source = _sha(source_sha)
    target = _sha(target_sha)
    matches = []
    for candidate in candidates:
        if (
            _sha(_field(candidate, "sourceSha")) == source
            and _sha(_field(candidate, "targetSha")) == target
            and str(_field(candidate, "promoteBranch", "headRefName") or "") == branch
            and str(_field(candidate, "state") or "OPEN").upper() == "OPEN"
        ):
            matches.append(candidate)
    matches.sort(key=lambda item: int(item.get("number") or 0))
    if len(matches) > 1:
        return {"action": "blocked", "reason": "duplicate_promotion_candidates", "prs": [m.get("number") for m in matches]}
    if len(matches) == 1:
        return {"action": "reuse", "pr": matches[0].get("number")}
    return {"action": "create"}


def cancel_obsolete(repository: str, branch: str, live_sha: str) -> list[str]:
    """Cancel obsolete queued/running runs without polling or waiting."""
    live = _sha(live_sha)
    if not live:
        raise ValueError("live SHA is invalid")
    result = subprocess.run(
        ["gh", "run", "list", "--repo", repository, "--branch", branch,
         "--limit", "100", "--json", "databaseId,headSha,status"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("unable to list GitHub runs")
    rows = json.loads(result.stdout or "[]")
    cancelled: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping) or _sha(row.get("headSha")) in {"", live}:
            continue
        if str(row.get("status") or "").lower() not in PROMOTION_STATES:
            continue
        run_id = str(row.get("databaseId") or "")
        if not run_id:
            continue
        # Do not wait for the cancellation result; the API request is the only
        # supported mutation and the next observer reconciles eventual state.
        subprocess.run(["gh", "run", "cancel", run_id, "--repo", repository], check=False, capture_output=True, text=True)
        cancelled.append(run_id)
    return cancelled


def _print(value: Any) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--receipt", required=True, type=Path)
    verify.add_argument("--identity", type=Path)
    verify.add_argument("--repo", type=Path)
    verify.add_argument("--dependency", action="append", default=[])
    verify.add_argument("--profile", choices=("fast", "full", "release"), default="full")
    verify.add_argument("--profile-file", action="append", default=[])
    verify.add_argument("--workflow-file", action="append", default=[])
    verify.add_argument("--workflow-run-id", type=int)
    verify.add_argument("--workflow-run-attempt", type=int)
    verify.add_argument("--workflow-head-commit")
    verify.add_argument("--runner-label")
    verify.add_argument("--command-digest")
    verify.add_argument("--expected-workflow-digest")
    verify.add_argument("--gate", required=True)

    development = commands.add_parser("development")
    development.add_argument("--input", required=True, type=Path)
    development.add_argument("--head-sha", required=True)

    approval = commands.add_parser("main-approval")
    approval.add_argument("--input", required=True, type=Path)
    approval.add_argument("--source-sha", required=True)
    approval.add_argument("--base-sha", required=True)
    approval.add_argument("--pr-head-sha", required=True)
    approval.add_argument("--receipt", type=Path)

    cancel = commands.add_parser("cancel-obsolete")
    cancel.add_argument("--repository", required=True)
    cancel.add_argument("--branch", required=True)
    cancel.add_argument("--live-sha", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            decision = verify_receipt_file(
                args.receipt, identity_path=args.identity, repo_path=args.repo,
                dependencies=args.dependency,
                profile=args.profile,
                required_gate=args.gate,
                profile_files=args.profile_file,
                workflow_files=args.workflow_file or None,
                workflow_run_id=args.workflow_run_id,
                workflow_run_attempt=args.workflow_run_attempt,
                workflow_head_commit=args.workflow_head_commit,
                runner_label=args.runner_label,
                expected_command_digest=args.command_digest,
                expected_workflow_digest=args.expected_workflow_digest,
            )
        elif args.command == "development":
            decision = evaluate_development_gates(load_json(args.input), args.head_sha)
        elif args.command == "main-approval":
            approval_payload = load_json(args.input)
            receipt_payload = load_json(args.receipt) if args.receipt else None
            decision = evaluate_main_approval(
                approval_payload, source_sha=args.source_sha, base_sha=args.base_sha,
                pr_head_sha=args.pr_head_sha, receipt=receipt_payload,
            )
        else:
            cancelled = cancel_obsolete(args.repository, args.branch, args.live_sha)
            _print({"accepted": True, "code": "cancel_requested", "cancelled": cancelled})
            return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        decision = Decision(False, "blocked", str(exc))
    _print(decision.to_dict())
    return 0 if decision.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
