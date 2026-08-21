"""Deterministic PKT-08 verification-run binding and liveness reconciliation."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

VERIFICATION_AMENDMENT = "V25_PKT08_VERIFICATION_LIVENESS"
VERIFICATION_PROFILE = "Full"
VERIFICATION_STATES = frozenset(
    {"STARTED", "LIVE", "TERMINAL", "ORPHANED", "TIMED_OUT", "RESTARTED"}
)
DEFAULT_TIMEOUT_SECONDS = 7200
DEFAULT_STALE_AFTER_SECONDS = 120
DEFAULT_MAX_AUTOMATIC_RESTARTS = 1
SCHEMA_RELATIVE_PATH = "core/managed-core/schemas/verification-run.schema.json"
CONFIG_RELATIVE_PATH = "core/managed-core/content/config/verification-liveness.json"
CONFIG_SCHEMA_RELATIVE_PATH = (
    "core/managed-core/schemas/verification-liveness.schema.json"
)
EXAMPLE_RELATIVE_PATH = "core/managed-core/examples/verification-run.example.json"
CONTRACT_RELATIVE_PATH = "core/contracts/VERIFICATION-LIVENESS-CONTRACT.md"
CANONICAL_SCHEMA_RELATIVE_PATH = "core/contracts/VERIFICATION-RUN.schema.json"
DOCTRINE_RELATIVE_PATH = "core/managed-core/content/doctrine/VERIFICATION-LIVENESS.md"
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class VerificationValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReconciliationResult:
    ok: bool
    state: str
    reason: str
    restart_allowed: bool = False


def _repo_root(repo_root: Path | str | None) -> Path:
    if repo_root is not None:
        return Path(_canonical_path(repo_root))
    return Path(_canonical_path(Path(__file__).resolve().parents[2]))


def _canonical_path(value: Path | str) -> str:
    """Return the physical absolute path used for durable identity binding."""
    return os.path.realpath(os.path.abspath(os.path.expanduser(os.fspath(value))))


def _paths_equivalent(left: Path | str, right: Path | str) -> bool:
    return _canonical_path(left) == _canonical_path(right)


def load_verification_schema(repo_root: Path | str | None = None) -> dict[str, Any]:
    path = _repo_root(repo_root) / SCHEMA_RELATIVE_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def load_verification_liveness_config(
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    path = _repo_root(repo_root) / CONFIG_RELATIVE_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def _utc(value: datetime) -> str:
    instant = value.astimezone(timezone.utc).replace(microsecond=0)
    return instant.isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _digest(value: object) -> str:
    payload = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _is_sha40(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(
        character in "0123456789abcdef" for character in value
    )


def verification_command_digest(command: Sequence[str]) -> str:
    return _digest(list(command))


def deterministic_artifact_paths(
    canonical_checkout: Path | str,
    run_id: str,
) -> tuple[str, str]:
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("invalid_verification_run_id")
    root = Path(_canonical_path(canonical_checkout))
    base = root / ".linktrend" / "verification"
    return str(base / f"{run_id}.log"), str(base / f"{run_id}.receipt.json")


def _identity_matches(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return all(left.get(field) == right.get(field) for field in ("repository", "commit", "tree"))


def ensure_no_duplicate_full_execution(
    candidate: Mapping[str, Any],
    existing_runs: Sequence[Mapping[str, Any]],
) -> None:
    if candidate.get("profile") != VERIFICATION_PROFILE:
        return
    for existing in existing_runs:
        if existing.get("runId") == candidate.get("runId"):
            continue
        if (
            existing.get("profile") == VERIFICATION_PROFILE
            and _identity_matches(candidate, existing)
        ):
            raise ValueError("duplicate_same_tree_full_execution")


def start_verification_run(
    *,
    run_id: str,
    packet_id: str,
    repository: str,
    canonical_checkout: Path | str,
    cwd: Path | str,
    commit: str,
    tree: str,
    command: Sequence[str],
    started_at: datetime,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    durable_handle: Mapping[str, Any],
    profile: str = VERIFICATION_PROFILE,
    active_runs: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    root = Path(_canonical_path(canonical_checkout))
    working = Path(_canonical_path(cwd))
    if not _paths_equivalent(root, working):
        raise ValueError("canonical_checkout_cwd_mismatch")
    if profile != VERIFICATION_PROFILE:
        raise ValueError("verification_profile_must_be_Full")
    if not _is_sha40(commit) or not _is_sha40(tree):
        raise ValueError("exact_commit_tree_required")
    if not command or any(not isinstance(item, str) or not item for item in command):
        raise ValueError("verification_command_required")
    if not isinstance(durable_handle.get("id"), str) or not durable_handle.get("id"):
        raise ValueError("durable_handle_required")
    if not isinstance(durable_handle.get("kind"), str) or not durable_handle.get("kind"):
        raise ValueError("durable_handle_kind_required")
    log_path, receipt_path = deterministic_artifact_paths(root, run_id)
    run = {
        "schemaVersion": 1,
        "amendment": VERIFICATION_AMENDMENT,
        "runId": run_id,
        "packetId": packet_id,
        "profile": profile,
        "repository": repository,
        "canonicalCheckout": str(root),
        "cwd": str(working),
        "commit": commit,
        "tree": tree,
        "command": list(command),
        "commandDigest": verification_command_digest(command),
        "logPath": log_path,
        "receiptPath": receipt_path,
        "startedAt": _utc(started_at),
        "lastHeartbeatAt": _utc(started_at),
        "timeoutSeconds": timeout_seconds,
        "durableHandle": dict(durable_handle),
        "state": "STARTED",
        "restartCount": 0,
    }
    ensure_no_duplicate_full_execution(run, active_runs)
    return run


def _binding_error(run: Mapping[str, Any], observation: Mapping[str, Any]) -> str | None:
    fields = (
        ("commandDigest", "command_digest_mismatch"),
        ("logPath", "log_path_mismatch"),
        ("receiptPath", "receipt_path_mismatch"),
        ("repository", "repository_mismatch"),
        ("canonicalCheckout", "canonical_checkout_mismatch"),
        ("cwd", "cwd_mismatch"),
        ("commit", "commit_mismatch"),
        ("tree", "tree_mismatch"),
    )
    for field, reason in fields:
        if field in {"logPath", "receiptPath", "canonicalCheckout", "cwd"}:
            if field in observation and not _paths_equivalent(
                str(observation[field]), str(run.get(field))
            ):
                return reason
            continue
        if field in observation and observation[field] != run.get(field):
            return reason
    return None


def reconcile_verification_run(
    run: Mapping[str, Any],
    *,
    now: datetime,
    observation: Mapping[str, Any],
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
) -> ReconciliationResult:
    binding_error = _binding_error(run, observation)
    if binding_error:
        return ReconciliationResult(False, str(run.get("state") or ""), binding_error)

    state = str(run.get("state") or "")
    if state not in VERIFICATION_STATES:
        return ReconciliationResult(False, state, "unknown_verification_state")
    started = _parse_utc(str(run["startedAt"]))
    if now.astimezone(timezone.utc) >= started + timedelta(seconds=int(run["timeoutSeconds"])):
        return ReconciliationResult(False, "TIMED_OUT", "verification_timeout")

    handle = observation.get("handle")
    if not isinstance(handle, Mapping) or not handle.get("id"):
        return ReconciliationResult(
            False,
            "ORPHANED",
            "missing_durable_handle",
            state not in {"TERMINAL", "TIMED_OUT"},
        )
    durable = run.get("durableHandle") or {}
    if handle.get("id") != durable.get("id") or handle.get("kind") != durable.get("kind"):
        return ReconciliationResult(False, state, "durable_handle_mismatch")
    status = str(handle.get("status") or "").upper()
    if status in {"COMPLETED", "SUCCEEDED", "FAILED", "CANCELLED"}:
        if state in {"STARTED", "LIVE", "RESTARTED"}:
            reason = (
                "completed_hosted_check_marked_running"
                if handle.get("kind") == "hosted_check"
                else "completed_handle_marked_running"
            )
            return ReconciliationResult(False, state, reason)
        if state == "TERMINAL" and observation.get("receiptPresent") is not True:
            return ReconciliationResult(False, state, "terminal_receipt_missing")
        return ReconciliationResult(True, "TERMINAL", "terminal_receipt_reconciled")
    if handle.get("alive") is False:
        return ReconciliationResult(
            False,
            "ORPHANED",
            "dead_durable_handle",
            state not in {"TERMINAL", "TIMED_OUT"},
        )

    if status != "RUNNING":
        return ReconciliationResult(
            False,
            "ORPHANED",
            "unusable_durable_handle",
            state not in {"TERMINAL", "TIMED_OUT"},
        )
    if state == "ORPHANED":
        return ReconciliationResult(False, state, "orphan_requires_restart")

    last_heartbeat = _parse_utc(str(run.get("lastHeartbeatAt") or run["startedAt"]))
    if now.astimezone(timezone.utc) > last_heartbeat + timedelta(seconds=stale_after_seconds):
        return ReconciliationResult(
            False,
            "ORPHANED",
            "stale_running_state",
            state not in {"TERMINAL", "TIMED_OUT"},
        )
    if state == "TERMINAL":
        return ReconciliationResult(False, state, "terminal_handle_still_running")
    return ReconciliationResult(True, "LIVE", "heartbeat_live")


def restart_orphaned_verification(
    run: Mapping[str, Any],
    *,
    now: datetime,
    durable_handle: Mapping[str, Any],
    max_automatic_restarts: int = DEFAULT_MAX_AUTOMATIC_RESTARTS,
) -> dict[str, Any]:
    if run.get("state") != "ORPHANED" or run.get("completionEvidence"):
        raise ValueError("restart_requires_incomplete_orphan")
    restart_count = int(run.get("restartCount", 0))
    if restart_count >= max_automatic_restarts:
        raise ValueError("automatic_restart_limit_reached")
    if not durable_handle.get("id") or not durable_handle.get("kind"):
        raise ValueError("durable_handle_required")
    restarted = dict(run)
    restarted["durableHandle"] = dict(durable_handle)
    restarted["startedAt"] = _utc(now)
    restarted["lastHeartbeatAt"] = _utc(now)
    restarted["state"] = "RESTARTED"
    restarted["restartCount"] = restart_count + 1
    return restarted


def heartbeat_verification_run(
    run: Mapping[str, Any],
    *,
    now: datetime,
    durable_handle: Mapping[str, Any],
) -> dict[str, Any]:
    if run.get("state") not in {"STARTED", "LIVE", "RESTARTED"}:
        raise ValueError("heartbeat_requires_nonterminal_run")
    expected = run.get("durableHandle") or {}
    if (
        durable_handle.get("kind") != expected.get("kind")
        or durable_handle.get("id") != expected.get("id")
    ):
        raise ValueError("durable_handle_mismatch")
    updated = dict(run)
    updated["lastHeartbeatAt"] = _utc(now)
    updated["state"] = "LIVE"
    return updated


def validate_verification_run(
    document: Mapping[str, Any],
    *,
    schema: Mapping[str, Any] | None = None,
    repo_root: Path | str | None = None,
) -> VerificationValidationResult:
    loaded = dict(schema) if schema is not None else load_verification_schema(repo_root)
    errors = tuple(
        sorted(error.message for error in Draft202012Validator(loaded).iter_errors(document))
    )
    if errors:
        return VerificationValidationResult(False, errors)
    expected_log, expected_receipt = deterministic_artifact_paths(
        str(document["canonicalCheckout"]), str(document["runId"])
    )
    semantic_errors: list[str] = []
    if not _paths_equivalent(document["cwd"], document["canonicalCheckout"]):
        semantic_errors.append("canonical_checkout_cwd_mismatch")
    if document["commandDigest"] != verification_command_digest(document["command"]):
        semantic_errors.append("command_digest_mismatch")
    if not _paths_equivalent(document["logPath"], expected_log):
        semantic_errors.append("log_path_mismatch")
    if not _paths_equivalent(document["receiptPath"], expected_receipt):
        semantic_errors.append("receipt_path_mismatch")
    if not _SHA256.fullmatch(document["commandDigest"]):
        semantic_errors.append("command_digest_invalid")
    return VerificationValidationResult(not semantic_errors, tuple(semantic_errors))
