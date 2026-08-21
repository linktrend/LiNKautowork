#!/usr/bin/env python3
"""Narrow administrator-recovery contract for exact Phase delivery.

Named exception only, after substantive replacement proof. Sequence:

1. Freeze the exact Phase head (commit + tree).
2. Snapshot branch protections.
3. Prefer ``gh pr merge --admin --match-head-commit`` first.
4. Apply a minimum temporary protection exception only if that merge is still
   blocked and the named exception authorizes it.
5. Merge only the exact authorized Phase PR head.
6. Restore the snapshot immediately and read it back.
7. Record obsolete publisher/status outcomes as WAIVED_LEGACY_GATE, never PASS.

This path never bypasses substantive proof, security, exact identity, scope,
review, or rollback. Direct pushes to protected branches remain forbidden.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

try:
    from core.execution.protocol import (
        ADMIN_RECOVERY_OPERATIONS,
        WAIVED_LEGACY_GATE,
        administrator_recovery as protocol_administrator_recovery,
    )
except ModuleNotFoundError:  # pragma: no cover - script-style execution
    from execution.protocol import (  # type: ignore
        ADMIN_RECOVERY_OPERATIONS,
        WAIVED_LEGACY_GATE,
        administrator_recovery as protocol_administrator_recovery,
    )

try:
    from scripts.gitops.delivery_modes import is_phase_branch, is_valid_sha, normalize_sha
    from scripts.gitops.issue_checkpoint import classify_legacy_status
except ModuleNotFoundError:  # pragma: no cover - script-style execution
    from delivery_modes import is_phase_branch, is_valid_sha, normalize_sha  # type: ignore
    from issue_checkpoint import classify_legacy_status  # type: ignore

PROTECTED_BRANCHES = frozenset({"development", "staging", "main"})
RECOVERY_STEPS = (
    "phase_head_freeze",
    "protection_snapshot",
    "admin_match_head_commit",
    "minimum_temporary_exception",
    "exact_authorized_merge",
    "restore",
    "readback",
)


class RecoveryError(ValueError):
    """Fail-closed administrator-recovery rejection."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail or code
        super().__init__(self.code if not detail else f"{self.code}: {self.detail}")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


class MergePort(Protocol):
    def merge_pull_request(
        self,
        *,
        repository: str,
        number: int,
        expected_head: str,
        method: str = "merge",
        admin: bool = False,
        match_head_commit: bool = True,
    ) -> dict[str, Any]:
        ...

    def push_protected(self, *, repository: str, branch: str, sha: str) -> None:
        ...


class ProtectionPort(Protocol):
    def snapshot(self, *, repository: str, branches: tuple[str, ...] | list[str]) -> dict[str, Any]:
        ...

    def apply_minimum_exception(
        self,
        *,
        repository: str,
        snapshot: Mapping[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        ...

    def restore(self, *, repository: str, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        ...

    def readback(self, *, repository: str, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        ...


@dataclass
class MemoryProtection:
    """In-memory protection adapter for disposable tests. Never talks to GitHub."""

    repository: str
    snapshots: list[dict[str, Any]] = field(default_factory=list)
    exceptions: list[dict[str, Any]] = field(default_factory=list)
    restores: list[dict[str, Any]] = field(default_factory=list)
    readbacks: list[dict[str, Any]] = field(default_factory=list)
    current: dict[str, Any] = field(default_factory=dict)
    drift: bool = False

    def snapshot(self, *, repository: str, branches: tuple[str, ...] | list[str]) -> dict[str, Any]:
        if repository != self.repository:
            raise RecoveryError("wrong_repository", repository)
        payload = {
            "repository": repository,
            "branches": {name: dict(self.current.get(name) or {"required": True}) for name in branches},
            "operation": "protection_snapshot",
        }
        self.snapshots.append(payload)
        return dict(payload)

    def apply_minimum_exception(
        self,
        *,
        repository: str,
        snapshot: Mapping[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        if repository != self.repository:
            raise RecoveryError("wrong_repository", repository)
        record = {
            "repository": repository,
            "reason": reason,
            "minimum": True,
            "temporary": True,
            "snapshotDigest": snapshot.get("repository"),
        }
        self.exceptions.append(record)
        return dict(record)

    def restore(self, *, repository: str, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        if repository != self.repository:
            raise RecoveryError("wrong_repository", repository)
        record = {"repository": repository, "restored": True, "operation": "restore"}
        self.restores.append(record)
        self.current = {
            name: dict(detail) for name, detail in (snapshot.get("branches") or {}).items()
        }
        return dict(record)

    def readback(self, *, repository: str, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        if repository != self.repository:
            raise RecoveryError("wrong_repository", repository)
        matches = not self.drift and self.current == (snapshot.get("branches") or {})
        record = {
            "repository": repository,
            "matchesSnapshot": matches,
            "operation": "readback",
        }
        self.readbacks.append(record)
        if not matches:
            raise RecoveryError("protection_readback_mismatch", "restored protections do not match snapshot")
        return dict(record)


def freeze_phase_head(
    *,
    phase_branch: str,
    head: str,
    tree: str,
    live_head: str,
    live_tree: str,
    pr_head: str = "",
) -> dict[str, str]:
    """Bind recovery to one exact Phase head. A later head invalidates it."""

    if not is_phase_branch(phase_branch):
        raise RecoveryError("wrong_source", phase_branch)
    frozen_head = normalize_sha(head)
    frozen_tree = normalize_sha(tree)
    observed_head = normalize_sha(live_head)
    observed_tree = normalize_sha(live_tree)
    if not is_valid_sha(frozen_head) or not is_valid_sha(frozen_tree):
        raise RecoveryError("exact_head_required", "phase head freeze requires commit and tree")
    if frozen_head != observed_head or frozen_tree != observed_tree:
        raise RecoveryError(
            "phase_head_changed",
            f"frozen={frozen_head}/{frozen_tree}:live={observed_head}/{observed_tree}",
        )
    if pr_head and normalize_sha(pr_head) != frozen_head:
        raise RecoveryError("stale_pr_head", f"pr={normalize_sha(pr_head)}:frozen={frozen_head}")
    return {
        "phaseBranch": phase_branch,
        "headCommit": frozen_head,
        "gitTree": frozen_tree,
        "frozen": "true",
    }


def authorize_named_recovery(
    *,
    named_exception: str,
    exact_head: str,
    replacement_proof: bool,
    operations: tuple[str, ...] | list[str],
) -> None:
    decision = protocol_administrator_recovery(
        named_exception=named_exception,
        exact_head=exact_head,
        replacement_proof=replacement_proof,
        operations=operations,
    )
    if not decision.allowed:
        raise RecoveryError(decision.reason, named_exception or "unnamed")


def recover_phase_merge(
    *,
    github: MergePort,
    protections: ProtectionPort,
    repository: str,
    pr_number: int,
    phase_branch: str,
    expected_head: str,
    expected_tree: str,
    live_head: str,
    live_tree: str,
    named_exception: str,
    replacement_proof: bool,
    allow_temporary_exception: bool = False,
    target_branch: str = "development",
    obsolete_status_state: str = "missing",
) -> dict[str, Any]:
    """Execute the exact-head administrator recovery sequence."""

    if target_branch not in PROTECTED_BRANCHES:
        raise RecoveryError("ungoverned_target", target_branch)
    authorize_named_recovery(
        named_exception=named_exception,
        exact_head=normalize_sha(expected_head),
        replacement_proof=replacement_proof,
        operations=("protection_snapshot", "restore", "readback"),
    )
    freeze = freeze_phase_head(
        phase_branch=phase_branch,
        head=expected_head,
        tree=expected_tree,
        live_head=live_head,
        live_tree=live_tree,
    )
    try:
        github.push_protected(repository=repository, branch=target_branch, sha=expected_head)
    except Exception as exc:
        if getattr(exc, "code", "") != "direct_push_forbidden":
            raise
    else:
        raise RecoveryError("direct_push_forbidden", target_branch)

    snapshot = protections.snapshot(repository=repository, branches=(target_branch,))
    exception_applied = False
    merged: dict[str, Any] | None = None
    merge_path = "admin_match_head_commit"
    try:
        try:
            merged = github.merge_pull_request(
                repository=repository,
                number=pr_number,
                expected_head=expected_head,
                method="merge",
                admin=True,
                match_head_commit=True,
            )
        except Exception as exc:
            merge_code = getattr(exc, "code", "") or "protected_merge_rejected"
            if not allow_temporary_exception:
                raise RecoveryError(
                    "admin_match_head_commit_failed",
                    f"{merge_code}:{exc}",
                ) from exc
            protections.apply_minimum_exception(
                repository=repository,
                snapshot=snapshot,
                reason=named_exception,
            )
            exception_applied = True
            merge_path = "minimum_temporary_exception"
            merged = github.merge_pull_request(
                repository=repository,
                number=pr_number,
                expected_head=expected_head,
                method="merge",
                admin=True,
                match_head_commit=True,
            )
    finally:
        protections.restore(repository=repository, snapshot=snapshot)
        protections.readback(repository=repository, snapshot=snapshot)

    if not merged:
        raise RecoveryError("exact_authorized_merge_missing", str(pr_number))
    if normalize_sha(str(merged.get("headSha") or expected_head)) != normalize_sha(expected_head):
        raise RecoveryError("exact_authorized_merge_mismatch", str(merged.get("headSha")))

    legacy = classify_legacy_status(obsolete_status_state)
    return {
        "status": "merged",
        "recovery": True,
        "namedException": named_exception,
        "phaseBranch": freeze["phaseBranch"],
        "testedHead": freeze["headCommit"],
        "gitTree": freeze["gitTree"],
        "pr": pr_number,
        "target": target_branch,
        "directPush": False,
        "mergePath": merge_path,
        "temporaryExceptionApplied": exception_applied,
        "operations": list(ADMIN_RECOVERY_OPERATIONS),
        "steps": list(RECOVERY_STEPS),
        "mergeCommitSha": normalize_sha(str(merged.get("mergeCommitSha") or "")),
        "obsoleteStatus": legacy,
        "legacyClassification": WAIVED_LEGACY_GATE,
        "obsoleteStatusIsPass": False,
        "replacementProof": True,
    }
