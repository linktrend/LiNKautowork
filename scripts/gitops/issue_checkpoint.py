#!/usr/bin/env python3
"""v2.5 token-independent lean Issue checkpoint acceptance.

V25_BOOTSTRAP_LEAN: exact pushed commit/tree + scoped diff + focused tests +
one exact-candidate independent narrow review + manifest evidence accept an
Issue checkpoint.
Review Ready, AUTOMATION_TOKEN, Issue PRs, hosted completion status, and
legacy publisher status are nonrequirements. Legacy publisher/status outcomes
are WAIVED_LEGACY_GATE, never PASS, and never bypass substantive proof.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import types
from pathlib import Path
from typing import Any, Mapping


def _load_managed_protocol() -> Any:
    """Load the installed protocol without requiring a source ``core/`` tree."""
    managed_protocol = (
        Path(__file__).resolve().parents[2]
        / ".ide-development"
        / "execution"
        / "protocol.py"
    )
    if not managed_protocol.is_file():
        raise ModuleNotFoundError(".ide-development/execution/protocol.py")

    module_name = "execution.protocol"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing

    package = sys.modules.get("execution")
    if package is None:
        package = types.ModuleType("execution")
        package.__path__ = [str(managed_protocol.parent)]
        package.__package__ = "execution"
        sys.modules["execution"] = package

    spec = importlib.util.spec_from_file_location(module_name, managed_protocol)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(f"unable to load {managed_protocol}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    setattr(package, "protocol", module)
    return module


try:
    from core.execution.protocol import (
        AMENDMENT_ID,
        ISSUE_CHECKPOINT_EVIDENCE,
        WAIVED_LEGACY_GATE,
        classify_legacy_publisher_gate,
        evaluate_issue_checkpoint,
    )
except ModuleNotFoundError:  # pragma: no cover - script-style execution
    _protocol = _load_managed_protocol()
    AMENDMENT_ID = _protocol.AMENDMENT_ID
    ISSUE_CHECKPOINT_EVIDENCE = _protocol.ISSUE_CHECKPOINT_EVIDENCE
    WAIVED_LEGACY_GATE = _protocol.WAIVED_LEGACY_GATE
    classify_legacy_publisher_gate = _protocol.classify_legacy_publisher_gate
    evaluate_issue_checkpoint = _protocol.evaluate_issue_checkpoint

try:
    from scripts.gitops.github_auth import (
        checkpoint_requires_automation_token,
        checkpoint_requires_review_ready,
        checkpoint_requires_token,
    )
except ModuleNotFoundError:  # pragma: no cover - script-style execution
    from github_auth import (  # type: ignore
        checkpoint_requires_automation_token,
        checkpoint_requires_review_ready,
        checkpoint_requires_token,
    )

PROOF_LOCAL = "local"
PROOF_HOSTED = "hosted"
PROOF_PRODUCTION = "production"
ALLOWED_PROOF_CLASSES = frozenset({PROOF_LOCAL, PROOF_HOSTED, PROOF_PRODUCTION})
MAX_EVIDENCE_JSON_BYTES = 256_000
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
CHECKPOINT_KIND = "v25-issue-checkpoint"
COMPLETION_EVIDENCE_KIND = "completion-evidence"


class IssueCheckpointError(ValueError):
    """Fail-closed Issue checkpoint rejection."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail or code
        super().__init__(self.code if not detail else f"{self.code}: {self.detail}")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


def is_sha40(value: str) -> bool:
    return bool(_SHA40.fullmatch(str(value or "").strip()))


def canonical_evidence_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def evidence_digest(payload: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_evidence_bytes(payload)).hexdigest()


def parse_immutable_evidence_payload(raw: str | Mapping[str, Any] | None) -> dict[str, Any]:
    """Parse an explicit immutable evidence payload for hosted out-of-tree proof.

    The payload is data, not a git tree file. Callers must still bind it to the
    exact SHA/tree. Local proof must not be labeled hosted or production.
    """

    if raw is None or raw == "":
        raise IssueCheckpointError("evidence_payload_missing", "explicit evidence payload is required")
    if isinstance(raw, Mapping):
        payload = dict(raw)
    else:
        text = str(raw)
        encoded = text.encode("utf-8")
        if len(encoded) > MAX_EVIDENCE_JSON_BYTES:
            raise IssueCheckpointError("evidence_json_too_large", "evidence payload exceeds size limit")
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise IssueCheckpointError("evidence_json_invalid", str(exc)) from exc
        if not isinstance(loaded, dict):
            raise IssueCheckpointError("evidence_json_not_object", "evidence payload must be a JSON object")
        payload = loaded
    encoded = canonical_evidence_bytes(payload)
    if len(encoded) > MAX_EVIDENCE_JSON_BYTES:
        raise IssueCheckpointError("evidence_json_too_large", "evidence payload exceeds size limit")
    return payload


def proof_class_of(payload: Mapping[str, Any] | None) -> str:
    raw = str((payload or {}).get("proofClass") or PROOF_LOCAL).strip().lower()
    return raw if raw in ALLOWED_PROOF_CLASSES else PROOF_LOCAL


def reject_local_as_hosted(
    *,
    actual_proof_class: str,
    claimed_proof_class: str,
) -> None:
    actual = (actual_proof_class or PROOF_LOCAL).strip().lower()
    claimed = (claimed_proof_class or "").strip().lower()
    if actual == PROOF_LOCAL and claimed in {PROOF_HOSTED, PROOF_PRODUCTION}:
        raise IssueCheckpointError(
            "local_proof_cannot_be_hosted",
            "local Issue-checkpoint proof must not be represented as hosted or production proof",
        )


def classify_legacy_status(state: str, *, publisher: str = "linktrend-review-ready-publisher") -> dict[str, object]:
    normalized = str(state or "missing").strip().lower() or "missing"
    if normalized in {"success", "passed", "pass"}:
        result = classify_legacy_publisher_gate(publisher=publisher, state="success")
    elif normalized in {"missing", "failed", "error", "failure", "neutral", "pending"}:
        result = classify_legacy_publisher_gate(
            publisher=publisher,
            state="failed" if normalized not in {"missing", "pending", "neutral"} else "missing",
        )
    else:
        result = classify_legacy_publisher_gate(publisher=publisher, state="missing")
    return {
        "publisher": publisher,
        "state": normalized,
        "classification": result.classification if result.classification == WAIVED_LEGACY_GATE else WAIVED_LEGACY_GATE,
        "isPass": False,
        "isImplementationFailure": False,
        "reason": result.reason,
        "canonicalForV25": "none",
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "passed", "pass", "success"}


def _lean_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    focused = payload.get("focusedTests")
    focused_passed = False
    if isinstance(focused, Mapping):
        focused_passed = _truthy(focused.get("passed"))
    elif isinstance(focused, bool):
        focused_passed = focused
    else:
        focused_passed = _truthy(payload.get("focusedTestsPassed"))
    return {
        "pushed": _truthy(payload.get("pushed", payload.get("originTipMatches"))),
        "commit": str(payload.get("headSha") or payload.get("commit") or "").strip(),
        "tree": str(payload.get("gitTree") or payload.get("tree") or "").strip(),
        "scoped_diff": _truthy(payload.get("scopedDiff") or payload.get("scoped_diff")),
        "focused_tests_passed": focused_passed,
        "independent_narrow_review": payload.get("independentNarrowReview")
        or payload.get("independent_narrow_review"),
        "manifest_evidence": _truthy(payload.get("manifestEvidence") or payload.get("manifest_evidence")),
    }


def validate_schema_v1_completion_evidence(payload: Mapping[str, Any], sha: str) -> list[str]:
    missing: list[str] = []
    if int(payload.get("schemaVersion") or 0) < 1:
        missing.append("evidence_schemaVersion")
    ev_sha = str(payload.get("headSha") or "")
    if not ev_sha or ev_sha != sha:
        missing.append(f"evidence_sha_mismatch:{ev_sha[:8] or 'empty'}!={sha[:8]}")
    if not str(payload.get("acceptance") or payload.get("classification") or "").strip():
        missing.append("acceptance_or_classification_missing")
    classification = str(payload.get("classification") or "").strip()
    if classification and classification not in {"tests", "docs_only"}:
        missing.append("classification_invalid")
    return missing


def evaluate_lean_payload(
    payload: Mapping[str, Any],
    *,
    expected_sha: str,
    expected_tree: str = "",
    review_ready: bool = False,
    automation_token_present: bool = False,
) -> dict[str, Any]:
    fields = _lean_fields(payload)
    commit = fields["commit"]
    tree = fields["tree"]
    if expected_sha and commit and commit != expected_sha:
        return {
            "accepted": False,
            "reason": f"exact_sha_mismatch:{commit}:{expected_sha}",
            "requiresReviewReady": False,
            "requiresToken": False,
            "requiredEvidence": list(ISSUE_CHECKPOINT_EVIDENCE),
        }
    if expected_tree and tree and tree != expected_tree:
        return {
            "accepted": False,
            "reason": f"exact_tree_mismatch:{tree}:{expected_tree}",
            "requiresReviewReady": False,
            "requiresToken": False,
            "requiredEvidence": list(ISSUE_CHECKPOINT_EVIDENCE),
        }
    decision = evaluate_issue_checkpoint(
        pushed=bool(fields["pushed"]),
        commit=commit or expected_sha,
        tree=tree or expected_tree,
        scoped_diff=bool(fields["scoped_diff"]),
        focused_tests_passed=bool(fields["focused_tests_passed"]),
        independent_narrow_review=fields["independent_narrow_review"],
        manifest_evidence=bool(fields["manifest_evidence"]),
        review_ready=review_ready,
        automation_token_present=automation_token_present,
    )
    return {
        "accepted": bool(decision.accepted),
        "reason": decision.reason,
        "requiresReviewReady": False,
        "requiresToken": False,
        "requiredEvidence": list(ISSUE_CHECKPOINT_EVIDENCE),
        "amendment": AMENDMENT_ID,
    }


def bind_issue_completion(
    *,
    sha: str,
    tree: str = "",
    evidence: Mapping[str, Any] | None,
    review_ready_state: str = "missing",
    automation_token_present: bool = False,
    claimed_proof_class: str = "",
) -> tuple[bool, str, dict[str, Any]]:
    """Accept Issue completion from lean/substantive evidence only.

    Review Ready status is classified WAIVED_LEGACY_GATE and never returns True.
    """

    legacy = classify_legacy_status(review_ready_state)
    if checkpoint_requires_token() or checkpoint_requires_review_ready() or checkpoint_requires_automation_token():
        return False, "checkpoint_auth_contract_violated", {"legacyPublisher": legacy}

    meta: dict[str, Any] = {
        "legacyPublisher": legacy,
        "legacyClassification": WAIVED_LEGACY_GATE,
        "reviewReadyRequired": False,
        "automationTokenRequired": False,
        "isPass": False,
    }
    if not is_sha40(sha):
        return False, "exact_pushed_commit_tree_required", meta
    if evidence is None:
        return False, "evidence_missing", meta

    actual_class = proof_class_of(evidence)
    if claimed_proof_class:
        reject_local_as_hosted(actual_proof_class=actual_class, claimed_proof_class=claimed_proof_class)
    meta["proofClass"] = actual_class
    meta["payloadDigest"] = evidence_digest(evidence)

    kind = str(evidence.get("kind") or "").strip()
    lean_keys = ("scopedDiff", "independentNarrowReview", "manifestEvidence")
    if kind == CHECKPOINT_KIND or any(key in evidence for key in lean_keys):
        result = evaluate_lean_payload(
            evidence,
            expected_sha=sha,
            expected_tree=tree,
            review_ready=review_ready_state.lower() == "success",
            automation_token_present=automation_token_present,
        )
        meta.update(result)
        if result["accepted"]:
            return True, "v25_bootstrap_lean_issue_checkpoint", meta
        return False, str(result["reason"]), meta

    if kind and kind != COMPLETION_EVIDENCE_KIND:
        return False, "evidence_kind_unsupported", meta
    missing = validate_schema_v1_completion_evidence(evidence, sha)
    if missing:
        return False, missing[0], meta
    meta["reason"] = "completion_evidence"
    meta["accepted"] = True
    return True, "completion_evidence", meta


def hosted_validation_record(
    *,
    sha: str,
    tree: str,
    payload: Mapping[str, Any],
    proof_class: str = PROOF_HOSTED,
) -> dict[str, Any]:
    """Record hosted validation of an explicit out-of-tree evidence payload.

    Never upgrades a local payload to hosted/production proof.
    """

    actual = proof_class_of(payload)
    reject_local_as_hosted(actual_proof_class=actual, claimed_proof_class=proof_class)
    ok, detail, meta = bind_issue_completion(
        sha=sha,
        tree=tree,
        evidence=payload,
        claimed_proof_class=proof_class,
    )
    return {
        "ok": ok,
        "detail": detail,
        "proofClass": actual,
        "payloadOrigin": "out_of_tree",
        "hostedValidation": actual == PROOF_HOSTED,
        "productionProof": False if actual != PROOF_PRODUCTION else True,
        "headSha": sha,
        "gitTree": tree,
        "payloadDigest": meta.get("payloadDigest"),
        "legacyClassification": WAIVED_LEGACY_GATE,
        **{k: v for k, v in meta.items() if k not in {"payloadDigest"}},
    }
