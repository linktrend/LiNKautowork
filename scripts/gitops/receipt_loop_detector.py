#!/usr/bin/env python3
"""Bounded admission and diagnosis for receipt-only successor transitions.

This module is intentionally pure.  A receipt/controller-only correction may
advance identity once when the product tree and all execution bindings stay
unchanged.  A second consecutive successor is structural evidence of a
self-invalidating receipt design and is stopped before another rebind.
"""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class LoopDecision:
    allowed: bool
    code: str
    detail: str
    successor_count: int = 0
    product_identity: str | None = None

    @property
    def stopped(self) -> bool:
        return not self.allowed

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "status": "PASS" if self.allowed else "HOLD",
            "code": self.code,
            "detail": self.detail,
            "successorCount": self.successor_count,
            "productIdentity": self.product_identity,
        }


def _document_identity(document: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in ("sourceIdentity", "candidateIdentity", "identity"):
        value = document.get(key)
        if isinstance(value, Mapping):
            return value
    return document


def _target(document: Mapping[str, Any]) -> Mapping[str, Any]:
    value = document.get("targetIdentity")
    return value if isinstance(value, Mapping) else document


def _value(document: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in document:
            return document[key]
    return None


def _identity_key(document: Mapping[str, Any]) -> tuple[str, str, str, str, str] | None:
    identity = _document_identity(document)
    values = (
        _value(identity, "repository"),
        _value(identity, "gitTree", "gitTreeSha", "tree"),
        _value(identity, "dependencyDigest", "dependencyLockDigest"),
        _value(identity, "profileDigest", "workflowProfileDigest"),
        _value(identity, "workflowDigest"),
    )
    if not isinstance(values[0], str) or not values[0] or any(not isinstance(value, str) for value in values[1:]):
        return None
    if not SHA_RE.fullmatch(values[1]) or any(not DIGEST_RE.fullmatch(value) for value in values[2:]):
        return None
    return values  # type: ignore[return-value]


def _commit(document: Mapping[str, Any]) -> str:
    identity = _document_identity(document)
    target = _target(document)
    value = _value(target, "commit", "headCommit", "sourceCommit", "targetCommit")
    if value is None:
        value = _value(identity, "headCommit", "sourceCommit", "commit")
    return str(value or "").lower()


def _paths(values: Sequence[str] | None) -> set[str] | None:
    if values is None:
        return None
    normalized = {str(value).strip() for value in values}
    if not normalized or any(not value or value.startswith(("/", "~")) or ".." in value.split("/") for value in normalized):
        return None
    return normalized


def detect_receipt_loop(
    history: Sequence[Mapping[str, Any]],
    successor: Mapping[str, Any],
    *,
    max_successors: int = 1,
) -> LoopDecision:
    """Stop when the same product identity already has one maintenance successor."""

    key = _identity_key(successor)
    rendered = None if key is None else ":".join(key)
    if key is None:
        return LoopDecision(False, "receipt_identity_invalid", "successor product identity is incomplete or malformed", product_identity=None)
    if max_successors < 1:
        return LoopDecision(False, "invalid_successor_bound", "max_successors must be positive", product_identity=rendered)
    count = sum(1 for prior in history if _identity_key(prior) == key)
    if count >= max_successors:
        return LoopDecision(
            False,
            "receipt_loop_detected",
            "second receipt-only successor for unchanged product identity; stop and diagnose the receipt structure",
            successor_count=count + 1,
            product_identity=rendered,
        )
    return LoopDecision(True, "receipt_successor_allowed", "one bounded receipt-only successor remains available", successor_count=count + 1, product_identity=rendered)


def admit_receipt_maintenance_transition(
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    *,
    history: Sequence[Mapping[str, Any]] = (),
    changed_paths: Sequence[str] | None = None,
    authorized_paths: Sequence[str] = (),
    current_protected_base: str | None = None,
    expected_protected_base: str | None = None,
    failure_contract_digest: str | None = None,
    predecessor_failure_contract_digest: str | None = None,
) -> LoopDecision:
    """Admit exactly one controller/receipt-only correction, fail closed otherwise."""

    predecessor_key = _identity_key(predecessor)
    successor_key = _identity_key(successor)
    if predecessor_key is None or successor_key is None:
        return LoopDecision(False, "receipt_identity_invalid", "predecessor or successor identity is incomplete")
    if predecessor_key != successor_key:
        return LoopDecision(False, "receipt_product_changed", "maintenance transition changed product tree or execution binding")
    previous_commit = _commit(predecessor)
    next_commit = _commit(successor)
    if not SHA_RE.fullmatch(previous_commit) or not SHA_RE.fullmatch(next_commit) or previous_commit == next_commit:
        return LoopDecision(False, "receipt_successor_invalid", "maintenance transition must create one distinct commit identity", product_identity=":".join(successor_key))
    successor_type = str(successor.get("transitionType") or successor.get("kind") or "")
    if successor_type and successor_type not in {"receipt-maintenance", "receipt-only", "maintenance"}:
        return LoopDecision(False, "maintenance_type_invalid", "successor is not a receipt-only maintenance transition", product_identity=":".join(successor_key))
    paths = _paths(changed_paths)
    authorized = _paths(authorized_paths)
    if paths is None or authorized is None or not paths <= authorized:
        return LoopDecision(False, "maintenance_scope_invalid", "changed paths must be non-empty and within exact authorized maintenance paths", product_identity=":".join(successor_key))
    if expected_protected_base is not None:
        if not SHA_RE.fullmatch(expected_protected_base.lower()) or current_protected_base != expected_protected_base:
            return LoopDecision(False, "protected_base_stale", "maintenance transition is not bound to the current protected base", product_identity=":".join(successor_key))
    if failure_contract_digest is not None or predecessor_failure_contract_digest is not None:
        if failure_contract_digest is None or predecessor_failure_contract_digest != failure_contract_digest or not DIGEST_RE.fullmatch(failure_contract_digest):
            return LoopDecision(False, "failure_contract_changed", "maintenance transition changed the inherited failure contract", product_identity=":".join(successor_key))
    decision = detect_receipt_loop(history, successor)
    if not decision.allowed:
        return decision
    return LoopDecision(True, "receipt_maintenance_allowed", "bounded receipt-maintenance transition admitted", successor_count=decision.successor_count, product_identity=decision.product_identity)


def write_loop_diagnosis(path: str | Path, decision: LoopDecision, *, predecessor: Mapping[str, Any] | None = None, successor: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Write a sanitized diagnosis atomically; callers should place it in external storage."""

    payload: dict[str, Any] = {"schemaVersion": 1, "kind": "receipt-loop-diagnosis", **decision.to_dict()}
    if predecessor is not None:
        payload["predecessorDigest"] = _document_digest(predecessor)
    if successor is not None:
        payload["successorDigest"] = _document_digest(successor)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent, delete=False) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(destination)
    return payload


def _document_digest(document: Mapping[str, Any]) -> str:
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    import hashlib

    return "sha256:" + hashlib.sha256(encoded).hexdigest()


__all__ = ["LoopDecision", "admit_receipt_maintenance_transition", "detect_receipt_loop", "write_loop_diagnosis"]
