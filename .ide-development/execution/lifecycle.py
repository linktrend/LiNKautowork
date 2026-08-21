"""Semantic lifecycle validation for execution-manifest runtime states.

Rejects inconsistent packet/attempt/evidence/lease/lock/archive records.
Does not silently normalize. Diagnostics always name packet and attempt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.execution.protocol import (
    EXHAUSTION_REASONS,
    ValidationResult,
    evaluate_verification_receipt,
    candidate_identity,
    validate_execution_manifest,
)

_SHA40 = frozenset("0123456789abcdef")

COMPLETED_STATES = frozenset({"COMPLETE", "ARCHIVE_CONFIRMED"})
RUNNING_STATE = "RUNNING"
PLAN_STATE = "PLAN"
TERMINAL_LIFECYCLE = "TERMINAL"
NONTERMINAL_LIFECYCLE = "RUNNING"
TERMINAL_RAW = frozenset({"succeeded", "failed", "cancelled", "archived"})
NONTERMINAL_RAW = frozenset({"running", "queued"})
PACKET_COMPLETION_KIND = "packet_completion"
EVENT_KIND = "event"


def _is_sha40(value: str) -> bool:
    return len(value) == 40 and all(char in _SHA40 for char in value)


@dataclass(frozen=True)
class LifecycleDiagnostic:
    packet_id: str
    attempt_id: str | None
    code: str

    def format(self) -> str:
        attempt = self.attempt_id if self.attempt_id else "-"
        return f"packet={self.packet_id} attempt={attempt}: {self.code}"


def _diag(
    packet_id: str,
    code: str,
    *,
    attempt_id: str | None = None,
) -> LifecycleDiagnostic:
    return LifecycleDiagnostic(packet_id, attempt_id, code)


def _attempts(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = packet.get("attempts")
    if raw is None:
        return []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_terminal_attempt(attempt: Mapping[str, Any]) -> bool:
    return (
        attempt.get("lifecycle") == TERMINAL_LIFECYCLE
        and attempt.get("rawStatus") in TERMINAL_RAW
        and _nonempty(attempt.get("endedAt"))
        and (_nonempty(attempt.get("result")) or _nonempty(attempt.get("reason")))
    )


def _is_nonterminal_attempt(attempt: Mapping[str, Any]) -> bool:
    return (
        attempt.get("lifecycle") == NONTERMINAL_LIFECYCLE
        and attempt.get("rawStatus") in NONTERMINAL_RAW
        and not _nonempty(attempt.get("endedAt"))
    )


def _lock_active(packet: Mapping[str, Any]) -> bool:
    lock = packet.get("writeLock")
    return isinstance(lock, dict) and lock.get("active") is True


def _heartbeat_ok(
    packet: Mapping[str, Any],
    diagnostics: list[LifecycleDiagnostic],
    *,
    attempt_id: str,
) -> None:
    packet_id = str(packet.get("id") or "-")
    heartbeat = packet.get("heartbeat")
    if not isinstance(heartbeat, dict):
        diagnostics.append(
            _diag(packet_id, "heartbeat_write_missing", attempt_id=attempt_id)
        )
        return
    if heartbeat.get("readback") is not True:
        diagnostics.append(
            _diag(packet_id, "heartbeat_readback_missing", attempt_id=attempt_id)
        )
        return
    if not _is_sha40(str(heartbeat.get("commit") or "")) or not _is_sha40(
        str(heartbeat.get("tree") or "")
    ):
        diagnostics.append(
            _diag(packet_id, "heartbeat_identity_unbound", attempt_id=attempt_id)
        )


def _verification_receipt_ok(
    packet: Mapping[str, Any],
    diagnostics: list[LifecycleDiagnostic],
) -> None:
    packet_id = str(packet.get("id") or "-")
    receipt = packet.get("verificationReceipt")
    if not isinstance(receipt, dict):
        diagnostics.append(_diag(packet_id, "missing_checkout_bound_receipt"))
        return
    lease = packet.get("orchestrationLease")
    repository = ""
    if isinstance(lease, dict):
        repository = str(lease.get("repository") or "")
    decision = evaluate_verification_receipt(
        receipt,
        checkout=candidate_identity(
            repository=repository,
            commit=str(packet.get("acceptedCommit") or ""),
            tree=str(packet.get("acceptedTree") or ""),
        ),
    )
    if not decision.accepted:
        diagnostics.append(_diag(packet_id, decision.reason))


def _retry_exhaustion_ok(
    packet: Mapping[str, Any],
    diagnostics: list[LifecycleDiagnostic],
    *,
    running: bool,
) -> None:
    packet_id = str(packet.get("id") or "-")
    attempts = _attempts(packet)
    exhausted_attempts = [
        attempt
        for attempt in attempts
        if str(attempt.get("reason") or "") in EXHAUSTION_REASONS
    ]
    record = packet.get("retryExhaustion")
    if not exhausted_attempts:
        return
    latest = exhausted_attempts[-1]
    attempt_id = str(latest.get("id") or "-")
    if not isinstance(record, dict) or record.get("exhausted") is not True:
        diagnostics.append(
            _diag(packet_id, "retry_exhaustion_undiagnosed", attempt_id=attempt_id)
        )
        return
    if running and record.get("recovery") == "continue":
        diagnostics.append(
            _diag(packet_id, "silent_retry_after_exhaustion", attempt_id=attempt_id)
        )


def _completion_evidence_ok(packet: Mapping[str, Any], diagnostics: list[LifecycleDiagnostic]) -> None:
    packet_id = str(packet.get("id") or "-")
    evidence = packet.get("completionEvidence")
    accepted_commit = packet.get("acceptedCommit")
    accepted_tree = packet.get("acceptedTree")
    if not _is_sha40(str(accepted_commit or "")) or not _is_sha40(str(accepted_tree or "")):
        diagnostics.append(_diag(packet_id, "missing_accepted_commit_tree"))
        return
    if not isinstance(evidence, dict) or not evidence:
        diagnostics.append(_diag(packet_id, "empty_completion_evidence"))
        return
    kind = evidence.get("kind")
    if kind == EVENT_KIND:
        diagnostics.append(_diag(packet_id, "event_only_completion_evidence"))
        return
    if kind != PACKET_COMPLETION_KIND:
        diagnostics.append(_diag(packet_id, "empty_completion_evidence"))
        return
    if not _nonempty(evidence.get("summary")):
        diagnostics.append(_diag(packet_id, "empty_completion_evidence"))
        return
    if evidence.get("commit") != accepted_commit or evidence.get("tree") != accepted_tree:
        diagnostics.append(_diag(packet_id, "completion_evidence_identity_mismatch"))
        return
    if not _is_sha40(str(evidence.get("commit") or "")) or not _is_sha40(
        str(evidence.get("tree") or "")
    ):
        diagnostics.append(_diag(packet_id, "completion_evidence_identity_mismatch"))


def _archive_evidence_ok(packet: Mapping[str, Any], diagnostics: list[LifecycleDiagnostic]) -> None:
    packet_id = str(packet.get("id") or "-")
    evidence = packet.get("archiveEvidence")
    if not isinstance(evidence, dict):
        diagnostics.append(_diag(packet_id, "missing_archive_readback"))
        return
    readback = evidence.get("readback")
    if evidence.get("apiReadback") is not True or readback in (None, "", {}, []):
        diagnostics.append(_diag(packet_id, "missing_archive_readback"))


def _validate_completed_packet(
    packet: Mapping[str, Any],
    diagnostics: list[LifecycleDiagnostic],
) -> None:
    packet_id = str(packet.get("id") or "-")
    _completion_evidence_ok(packet, diagnostics)
    _verification_receipt_ok(packet, diagnostics)
    _retry_exhaustion_ok(packet, diagnostics, running=False)
    if packet.get("executionState") == "ARCHIVE_CONFIRMED":
        _archive_evidence_ok(packet, diagnostics)
    if _lock_active(packet):
        lock = packet.get("writeLock") if isinstance(packet.get("writeLock"), dict) else {}
        diagnostics.append(
            _diag(
                packet_id,
                "completed_packet_has_active_lock",
                attempt_id=str(lock.get("attemptId") or "-"),
            )
        )
    attempts = _attempts(packet)
    if not attempts:
        diagnostics.append(_diag(packet_id, "completed_packet_missing_terminal_attempts"))
        return
    for attempt in attempts:
        attempt_id = str(attempt.get("id") or "-")
        if _is_nonterminal_attempt(attempt) or attempt.get("lifecycle") == NONTERMINAL_LIFECYCLE:
            diagnostics.append(
                _diag(packet_id, "complete_packet_has_running_attempt", attempt_id=attempt_id)
            )
            continue
        if not _is_terminal_attempt(attempt):
            diagnostics.append(
                _diag(packet_id, "completed_attempt_not_terminal", attempt_id=attempt_id)
            )


def _validate_running_packet(
    packet: Mapping[str, Any],
    diagnostics: list[LifecycleDiagnostic],
) -> None:
    packet_id = str(packet.get("id") or "-")
    attempts = _attempts(packet)
    for attempt in attempts:
        if _is_terminal_attempt(attempt) or _is_nonterminal_attempt(attempt):
            continue
        diagnostics.append(
            _diag(
                packet_id,
                "attempt_neither_terminal_nor_nonterminal",
                attempt_id=str(attempt.get("id") or "-"),
            )
        )
    current = [
        attempt
        for attempt in attempts
        if attempt.get("authoritative") is True and _is_nonterminal_attempt(attempt)
    ]
    if len(current) != 1:
        diagnostics.append(
            _diag(
                packet_id,
                "running_packet_requires_one_authoritative_nonterminal_attempt",
                attempt_id="-",
            )
        )
        current_id = "-"
        current_attempt = None
    else:
        current_attempt = current[0]
        current_id = str(current_attempt.get("id") or "-")
    lock = packet.get("writeLock")
    expected_lock_id = current_id if current_attempt is not None else None
    if (
        not isinstance(lock, dict)
        or lock.get("active") is not True
        or (expected_lock_id is not None and lock.get("attemptId") != expected_lock_id)
        or expected_lock_id is None
    ):
        diagnostics.append(
            _diag(packet_id, "running_packet_missing_active_write_lock", attempt_id=current_id)
        )
    lease = packet.get("orchestrationLease")
    if (
        not isinstance(lease, dict)
        or not _nonempty(lease.get("holder"))
        or not _nonempty(lease.get("nonce"))
        or not _nonempty(lease.get("expiresAt"))
    ):
        diagnostics.append(
            _diag(packet_id, "running_packet_missing_orchestration_lease", attempt_id=current_id)
        )
    _heartbeat_ok(packet, diagnostics, attempt_id=current_id)
    _retry_exhaustion_ok(packet, diagnostics, running=True)


def _heartbeat_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return None


def heartbeat_progress_requirements(
    manifest: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    now: datetime | None = None,
    no_progress_wakes: int = 0,
    elapsed_seconds: int = 0,
) -> tuple[dict[str, Any], ...]:
    """Return deterministic reasons a heartbeat may not be silent.

    This is a lifecycle read-only contract. It deliberately does not dispatch
    or mutate state; the manifest heartbeat controller consumes its result.
    """

    requirements: list[dict[str, Any]] = []
    clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    lease = manifest.get("orchestrationLease")
    if not isinstance(lease, Mapping):
        lease = snapshot.get("lease")
    if isinstance(lease, Mapping):
        expires_at = _heartbeat_timestamp(lease.get("expiresAt"))
        if expires_at is not None and expires_at <= clock:
            requirements.append({"code": "expired_lease"})

    transitions = manifest.get("transitions")
    transition_rows = (
        [item for item in transitions if isinstance(item, Mapping)]
        if isinstance(transitions, list)
        else []
    )
    transition_kinds = {str(item.get("kind") or "") for item in transition_rows}
    processed_action_ids = {
        str(item.get("actionId"))
        for item in transition_rows
        if item.get("kind") == "dispatch" and item.get("actionId")
    }

    action_candidates: list[Mapping[str, Any]] = []
    for key in ("safeAction", "requiredAction", "repairAction", "pendingAction"):
        value = manifest.get(key)
        if isinstance(value, Mapping):
            action_candidates.append(value)
    for item in transition_rows:
        if str(item.get("kind") or "") in {
            "action_persisted",
            "dispatch_intent",
            "repair_requested",
        }:
            action_candidates.append(item)
    for action in action_candidates:
        state = str(action.get("state") or action.get("status") or "").upper()
        action_id = str(action.get("id") or "")
        if action_id and action_id in processed_action_ids:
            continue
        if action.get("safe") is True and state not in {"DISPATCHED", "COMMITTED", "COMPLETED"}:
            requirements.append(
                {"code": "persisted_undispatched_safe_intent", "action": dict(action)}
            )
            break

    cursor = snapshot.get("cursor")
    cursor = cursor if isinstance(cursor, Mapping) else {}
    github = snapshot.get("github")
    github = github if isinstance(github, Mapping) else {}
    status = str(cursor.get("status") or snapshot.get("status") or "").upper()
    run_id = cursor.get("runId") or github.get("workflowRunId")
    heartbeat_repair_dispatched = any(
        item.get("kind") == "dispatch"
        and item.get("reconstructedOnHeartbeat") is True
        for item in transition_rows
    )
    if status == "REPAIR_REQUESTED" and not run_id and not heartbeat_repair_dispatched:
        requirements.append({"code": "repair_requested_without_run"})

    if status in {"COMPLETED", "SUCCESS", "FAILED", "CANCELLED"} and "run" not in transition_kinds:
        requirements.append({"code": "completed_transition_unprocessed"})

    check = github.get("check")
    checks = github.get("checks")
    failed_check = (
        isinstance(check, Mapping)
        and str(check.get("conclusion") or check.get("status") or "").upper()
        in {"FAILURE", "FAILED", "TIMED_OUT", "CANCELLED"}
    ) or (
        isinstance(checks, list)
        and any(
            isinstance(item, Mapping)
            and str(item.get("conclusion") or item.get("status") or "").upper()
            in {"FAILURE", "FAILED", "TIMED_OUT", "CANCELLED"}
            for item in checks
        )
    )
    if failed_check:
        requirements.append({"code": "failed_check_repair"})

    ready_work = snapshot.get("readyWork") or cursor.get("readyWork")
    if ready_work:
        requirements.append({"code": "compatible_ready_work", "readyWork": ready_work})

    heartbeat = manifest.get("heartbeat")
    if isinstance(heartbeat, Mapping):
        no_progress_wakes = max(
            no_progress_wakes, int(heartbeat.get("noProgressWakes") or 0)
        )
        elapsed_seconds = max(
            elapsed_seconds, int(heartbeat.get("elapsedSeconds") or 0)
        )
    if no_progress_wakes >= 2:
        requirements.append({"code": "two_no_progress_wakes"})
    elif elapsed_seconds >= 20 * 60:
        requirements.append({"code": "heartbeat_timeout"})
    return tuple(requirements)


def validate_execution_lifecycle(document: Mapping[str, Any]) -> ValidationResult:
    packets = document.get("packets")
    if not isinstance(packets, list):
        return ValidationResult(ok=False, errors=("packets_missing",))
    diagnostics: list[LifecycleDiagnostic] = []
    for packet in packets:
        if not isinstance(packet, dict):
            diagnostics.append(_diag("-", "packet_not_object"))
            continue
        packet_id = str(packet.get("id") or "-")
        state = packet.get("executionState")
        if state in (None, PLAN_STATE):
            continue
        if state == RUNNING_STATE:
            _validate_running_packet(packet, diagnostics)
            continue
        if state in COMPLETED_STATES:
            _validate_completed_packet(packet, diagnostics)
            continue
        diagnostics.append(_diag(packet_id, "unknown_execution_state"))
    if diagnostics:
        return ValidationResult(
            ok=False,
            errors=tuple(item.format() for item in diagnostics),
        )
    return ValidationResult(ok=True)


def validate_plan_or_runtime(
    document: Mapping[str, Any],
    *,
    schema: Mapping[str, Any] | None = None,
    repo_root: Path | str | None = None,
) -> ValidationResult:
    schema_result = validate_execution_manifest(
        document, schema=schema, repo_root=repo_root
    )
    if not schema_result.ok:
        return schema_result
    return validate_execution_lifecycle(document)
