#!/usr/bin/env python3
"""Durable portfolio orchestration, automation, and finite handover.

This module is deliberately provider-neutral.  Provider adapters supply worker
read, archive, dispatch, and replacement callbacks; all ownership, lease,
idempotency, dependency, and reporting decisions are reconstructed from the
durable state document.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from jsonschema import Draft202012Validator

from core.execution.manifest_persistence import (
    ManifestPersistenceError,
    canonical_state_digest,
    persist_durable_state,
    read_durable_state,
)
from core.execution.protocol import (
    PORTFOLIO_CONTROL_LOOP_PROTOCOL,
    PORTFOLIO_CONTROL_LOOP_VERSION,
    PORTFOLIO_LANE_STATES,
    control_loop_invocation_key,
    validate_control_loop_lease,
)
from core.execution.verification_liveness import (
    DEFAULT_STALE_AFTER_SECONDS,
    is_worker_stalled,
    replace_stalled_worker,
)
from scripts.gitops.readiness_status import build_portfolio_status

CONFIG_RELATIVE_PATH = "core/managed-core/content/config/portfolio-control-loop.json"
SCHEMA_RELATIVE_PATH = "core/managed-core/schemas/portfolio-control-loop.schema.json"
CONTROL_LOOP_STATES = frozenset({"LIVE", "READ_ONLY", "RETIRED"})
TERMINAL_WORKER_STATES = frozenset(
    {"COMPLETED", "SUCCEEDED", "FAILED", "CANCELLED", "TERMINAL", "ARCHIVED"}
)
ACTIVE_WORKER_STATES = frozenset({"RUNNING", "STARTED", "LIVE", "RESTARTED"})
ALLOWED_TRIGGERS = frozenset({"hourly", "PULSE"})
MAX_STATE_EVENTS = 500
HEARTBEAT_PENDING = "PENDING"
HEARTBEAT_ACTIVE = "ACTIVE"
HEARTBEAT_PROVEN = "PROVEN"
UTILIZATION_GAP = "UTILIZATION_GAP"
CURSOR_PROVIDERS = frozenset({"cursor", "cursor-sdk", "ordinary-development"})
LUNA_PROVIDERS = frozenset({"luna", "codex-cli", "luna-fallback"})


class ControlLoopStore(Protocol):
    def read(self) -> Mapping[str, Any] | None:
        ...

    def compare_and_write(
        self,
        expected_revision: int,
        expected_digest: str | None,
        payload: Mapping[str, Any],
    ) -> None:
        ...


def _utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _now(value: datetime | None) -> datetime:
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc)


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _event_id(kind: str, value: object) -> str:
    return f"{kind}-" + _digest(value).split(":", 1)[1][:24]


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _durable_store_lock(store: ControlLoopStore):
    """Serialize turns across processes when the store has a filesystem path."""

    path = getattr(store, "path", None)
    if path is None:
        yield
        return
    lock_path = Path(path).with_name(Path(path).name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    acquired = False
    try:
        if os.name == "nt":  # pragma: no cover - Windows compatibility
            import msvcrt

            if os.lseek(descriptor, 0, os.SEEK_END) < 1:
                os.write(descriptor, b"\0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        acquired = True
        yield
    finally:
        if acquired and os.name != "nt":
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


class MemoryControlLoopStore:
    """Small CAS store for focused tests and offline rehearsals."""

    def __init__(self, state: Mapping[str, Any] | None = None) -> None:
        self._record: dict[str, Any] | None = None
        if state is not None:
            persist_durable_state(dict(state), self)

    def read(self) -> dict[str, Any] | None:
        return copy.deepcopy(self._record)

    def compare_and_write(
        self,
        expected_revision: int,
        expected_digest: str | None,
        payload: Mapping[str, Any],
    ) -> None:
        current = self._record
        revision = 0 if current is None else current["revision"]
        digest = None if current is None else current["digest"]
        if revision != expected_revision or digest != expected_digest:
            raise ManifestPersistenceError("revision_conflict", "control-loop state CAS collision")
        state = copy.deepcopy(dict(payload["state"]))
        self._record = {"revision": revision + 1, "digest": payload["digest"], "state": state}


class JsonFileControlLoopStore:
    """Atomic JSON state envelope used by the scheduled controller."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def read(self) -> dict[str, Any] | None:
        if not self.path.is_file():
            return None
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ManifestPersistenceError("durable_state_invalid", "control-loop state is not an object")
        return value

    def compare_and_write(
        self,
        expected_revision: int,
        expected_digest: str | None,
        payload: Mapping[str, Any],
    ) -> None:
        current = self.read()
        revision = 0 if current is None else current.get("revision")
        digest = None if current is None else current.get("digest")
        if revision != expected_revision or digest != expected_digest:
            raise ManifestPersistenceError("revision_conflict", "control-loop state CAS collision")
        _atomic_json(
            self.path,
            {
                "revision": revision + 1,
                "digest": payload["digest"],
                "state": copy.deepcopy(dict(payload["state"])),
            },
        )


def load_control_loop_schema(repo_root: Path | str) -> dict[str, Any]:
    return json.loads((Path(repo_root).resolve() / SCHEMA_RELATIVE_PATH).read_text(encoding="utf-8"))


def load_control_loop_config(
    repo_root: Path | str,
    *,
    schema: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    document = json.loads((root / CONFIG_RELATIVE_PATH).read_text(encoding="utf-8"))
    loaded = dict(schema) if schema is not None else load_control_loop_schema(root)
    errors = sorted(error.message for error in Draft202012Validator(loaded).iter_errors(document))
    if errors:
        raise ValueError("portfolio_control_loop_config_invalid: " + "; ".join(errors))
    return document


def validate_control_loop_state(state: Mapping[str, Any]) -> tuple[str, ...]:
    """Validate semantic invariants that JSON Schema cannot express."""

    errors: list[str] = []
    controller = state.get("controller")
    if not isinstance(controller, Mapping) or not controller.get("taskId"):
        errors.append("controller_task_id_missing")
    if state.get("protocol") != {
        "id": PORTFOLIO_CONTROL_LOOP_PROTOCOL,
        "version": PORTFOLIO_CONTROL_LOOP_VERSION,
    }:
        errors.append("control_loop_protocol_mismatch")
    lease = state.get("lease")
    if not isinstance(lease, Mapping) or not lease.get("holder") or not lease.get("nonce"):
        errors.append("controller_lease_missing")
    lanes = state.get("lanes")
    if not isinstance(lanes, Mapping):
        errors.append("lanes_missing")
    else:
        for lane_id, lane in lanes.items():
            if not isinstance(lane, Mapping) or lane.get("state") not in PORTFOLIO_LANE_STATES:
                errors.append(f"lane={lane_id}:invalid_state")
    return tuple(errors)


def new_control_loop_state(
    *,
    coordinator_task_id: str,
    owner_id: str,
    now: datetime | None = None,
    lease_seconds: int = 180,
    capacity: int | Mapping[str, Any] | None = None,
    stage: int = 1,
    stage_verification: str = "baseline",
    protected_refs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    clock = _now(now)
    nonce = _digest({"task": coordinator_task_id, "owner": owner_id, "at": _utc(clock)})[7:31]
    return {
        "schemaVersion": 1,
        "protocol": {
            "id": PORTFOLIO_CONTROL_LOOP_PROTOCOL,
            "version": PORTFOLIO_CONTROL_LOOP_VERSION,
        },
        "controller": {
            "taskId": coordinator_task_id,
            "ownerId": owner_id,
            "state": "LIVE",
            "generation": 1,
        },
        "lease": {
            "holder": owner_id,
            "coordinatorTaskId": coordinator_task_id,
            "nonce": nonce,
            "acquiredAt": _utc(clock),
            "expiresAt": _utc(clock + timedelta(seconds=lease_seconds)),
        },
        "stage": stage,
        "stageVerification": stage_verification,
        "capacity": copy.deepcopy(capacity),
        "protectedRefs": dict(protected_refs or {}),
        "lanes": {},
        "workers": {},
        "dependencyGraph": {},
        "automations": {},
        "invocations": {},
        "transferredTerminalEvents": [],
        "controllerHistory": [],
        "events": [],
        "blockers": [],
        "activeTurn": None,
        "lastReport": None,
        "heartbeatAcceptance": {
            "status": HEARTBEAT_PENDING,
            "automationId": None,
            "confirmedScheduledInvocations": 0,
            "consecutiveScheduledInvocations": 0,
            "terminalWorkerReconciled": False,
            "dependencyReadyPacketDispatched": False,
            "requirements": ["consecutive_scheduled_invocations"],
        },
    }


def calculate_safe_capacity(
    config: Mapping[str, Any], state: Mapping[str, Any]
) -> dict[str, Any]:
    """Calculate stage/provider limits from live capacity and Mac memory.

    A provider-capacity mapping is required for provider-specific dispatch. An
    integer remains a compatibility capacity for the in-memory generic loop;
    it is not a replacement for the staged Cursor/Luna policy.
    """

    policy = config.get("stagedCapacityPolicy") or {}
    stages = policy.get("stages") if isinstance(policy, Mapping) else None
    stage_number = int(state.get("stage") or 1)
    stage = next(
        (row for row in (stages or ()) if isinstance(row, Mapping) and row.get("stage") == stage_number),
        None,
    )
    if stage is None:
        raise ValueError(f"staged_capacity_policy_missing_stage:{stage_number}")
    required_verification = str(stage.get("afterVerification") or "baseline")
    if required_verification != "baseline" and state.get("stageVerification") != required_verification:
        return {
            "stage": stage_number,
            "cursor": 0,
            "luna": 0,
            "underfillLuna": int(stage["underfillLuna"]),
            "macMemoryAvailable": False,
            "source": "stage_verification_required",
            "requiredVerification": required_verification,
        }
    raw = state.get("capacity")
    if isinstance(raw, Mapping):
        memory_ok = raw.get("macMemoryAvailable", raw.get("macMemory")) is True
        cursor_raw = raw.get("cursor", raw.get("cursorCapacity"))
        luna_raw = raw.get("luna", raw.get("lunaCapacity"))
        cursor = min(int(stage["cursor"]), max(0, int(cursor_raw or 0))) if memory_ok else 0
        luna = min(int(stage["luna"]), max(0, int(luna_raw or 0))) if memory_ok else 0
        return {
            "stage": stage_number,
            "cursor": cursor,
            "luna": luna,
            "underfillLuna": int(stage["underfillLuna"]),
            "macMemoryAvailable": memory_ok,
            "source": "live_provider_capacity",
        }
    if isinstance(raw, int) and not isinstance(raw, bool):
        return {
            "stage": stage_number,
            "total": max(0, raw),
            "underfillLuna": int(stage["underfillLuna"]),
            "macMemoryAvailable": True,
            "source": "generic_test_capacity",
        }
    return {
        "stage": stage_number,
        "cursor": 0,
        "luna": 0,
        "underfillLuna": int(stage["underfillLuna"]),
        "macMemoryAvailable": False,
        "source": "capacity_unavailable",
    }


def _append_unique(rows: list[Any], value: Any, *, key: str = "id") -> None:
    identity = value.get(key) if isinstance(value, Mapping) else value
    if not any((row.get(key) if isinstance(row, Mapping) else row) == identity for row in rows):
        rows.append(copy.deepcopy(value))


def _worker_terminal(worker: Mapping[str, Any], observation: Mapping[str, Any]) -> bool:
    status = str(observation.get("status") or observation.get("state") or worker.get("state") or "").upper()
    return status in TERMINAL_WORKER_STATES or observation.get("terminal") is True


def _accepted(observation: Mapping[str, Any], worker: Mapping[str, Any]) -> bool:
    result = str(
        observation.get("result")
        or observation.get("conclusion")
        or worker.get("result")
        or worker.get("conclusion")
        or observation.get("status")
        or ""
    ).upper()
    return result in {"SUCCESS", "SUCCEEDED", "ACCEPT", "ACCEPTED", "PASS", "PASSED", "COMPLETED"}


def _heartbeat_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _consecutive_scheduled_deliveries(automation: Mapping[str, Any]) -> tuple[int, int]:
    """Return (confirmed receipt count, latest cadence-consecutive streak)."""

    receipts = automation.get("deliveryReceipts")
    if not isinstance(receipts, list):
        return 0, 0
    cadence = int(automation.get("cadenceSeconds") or 0)
    confirmed_count = 0
    streak = 0
    previous_scheduled: datetime | None = None
    previous_actual: datetime | None = None
    for receipt in receipts:
        if not isinstance(receipt, Mapping):
            streak = 0
            previous_scheduled = previous_actual = None
            continue
        scheduled = _heartbeat_timestamp(receipt.get("scheduledAt"))
        actual = _heartbeat_timestamp(receipt.get("actualDeliveryAt"))
        confirmed = (
            scheduled is not None
            and actual is not None
            and str(receipt.get("result") or "").upper()
            in {"DELIVERED", "SUCCESS", "CONFIRMED"}
            and receipt.get("targetTaskId") == automation.get("targetTaskId")
        )
        if not confirmed:
            streak = 0
            previous_scheduled = previous_actual = None
            continue
        confirmed_count += 1
        consecutive = (
            previous_scheduled is not None
            and previous_actual is not None
            and cadence > 0
            and scheduled - previous_scheduled == timedelta(seconds=cadence)
            and actual > previous_actual
        )
        streak = streak + 1 if consecutive else 1
        previous_scheduled, previous_actual = scheduled, actual
    return confirmed_count, streak


def _worker_continuity_evidence(state: Mapping[str, Any]) -> tuple[bool, bool]:
    """Prove accepted terminal reconciliation followed by dependent dispatch."""

    events = state.get("events")
    workers = state.get("workers")
    lanes = state.get("lanes")
    if not all(isinstance(value, Mapping) for value in (workers, lanes)):
        return False, False
    rows = list(events) if isinstance(events, list) else []
    for index, event in enumerate(rows):
        if not isinstance(event, Mapping) or event.get("kind") != "terminal_archived":
            continue
        worker_id = str(event.get("workerId") or "")
        worker = workers.get(worker_id)
        reconciled = (
            event.get("reconciled") is True
            and event.get("accepted") is True
            and isinstance(worker, Mapping)
            and worker.get("state") == "ARCHIVED"
            and worker.get("terminalState") == "TERMINAL_ACCEPT"
            and isinstance(worker.get("archive"), Mapping)
            and worker["archive"].get("readback") is True
        )
        if not reconciled:
            continue
        terminal_lane = str(event.get("laneId") or "")
        for later in rows[index + 1 :]:
            if not isinstance(later, Mapping) or later.get("kind") != "worker_dispatched":
                continue
            if later.get("dependencyReady") is not True:
                continue
            dispatched_lane = str(later.get("laneId") or "")
            lane = lanes.get(dispatched_lane)
            dependencies = lane.get("dependencies") if isinstance(lane, Mapping) else None
            if (
                terminal_lane in (dependencies or ())
                and all(
                    isinstance(lanes.get(str(dependency)), Mapping)
                    and lanes[str(dependency)].get("state") == "COMPLETE"
                    for dependency in dependencies or ()
                )
            ):
                return True, True
        return True, False
    return False, False


def heartbeat_continuity_evidence(state: Mapping[str, Any]) -> dict[str, Any]:
    """Derive fail-closed heartbeat acceptance from durable evidence only."""

    automations = state.get("automations")
    records = automations.values() if isinstance(automations, Mapping) else ()
    best_automation: Mapping[str, Any] | None = None
    best_confirmed = 0
    best_streak = 0
    controller = state.get("controller")
    target_task_id = controller.get("taskId") if isinstance(controller, Mapping) else None
    for automation in records:
        if not isinstance(automation, Mapping):
            continue
        if target_task_id and automation.get("targetTaskId") != target_task_id:
            continue
        confirmed, streak = _consecutive_scheduled_deliveries(automation)
        if (streak, confirmed) > (best_streak, best_confirmed):
            best_automation = automation
            best_confirmed, best_streak = confirmed, streak

    terminal_reconciled, dependency_dispatched = _worker_continuity_evidence(state)
    if best_streak < 2:
        status = HEARTBEAT_PENDING
        requirements = ["consecutive_scheduled_invocations"]
    elif not terminal_reconciled or not dependency_dispatched:
        status = HEARTBEAT_ACTIVE
        requirements = []
        if not terminal_reconciled:
            requirements.append("terminal_worker_reconciliation")
        if not dependency_dispatched:
            requirements.append("dependency_ready_dispatch")
    else:
        status = HEARTBEAT_PROVEN
        requirements = []
    return {
        "status": status,
        "automationId": best_automation.get("automationId") if best_automation else None,
        "confirmedScheduledInvocations": best_confirmed,
        "consecutiveScheduledInvocations": best_streak,
        "terminalWorkerReconciled": terminal_reconciled,
        "dependencyReadyPacketDispatched": dependency_dispatched,
        "requirements": requirements,
    }


def _refresh_heartbeat_acceptance(state: dict[str, Any]) -> None:
    state["heartbeatAcceptance"] = heartbeat_continuity_evidence(state)


def _invoke_hook(hook: Callable[..., Any] | None, value: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if hook is None:
        return None
    result = hook(copy.deepcopy(dict(value)))
    if result is None:
        return {}
    if not isinstance(result, Mapping):
        raise ValueError("control_loop_hook_must_return_object")
    return dict(result)


class PortfolioControlLoop:
    """Single-owner controller whose durable document is the source of truth."""

    def __init__(
        self,
        store: ControlLoopStore,
        *,
        repo_root: Path | str | None = None,
        config: Mapping[str, Any] | None = None,
    ) -> None:
        self.store = store
        self.repo_root = Path(repo_root).resolve() if repo_root is not None else None
        self.config = dict(config or (load_control_loop_config(self.repo_root) if self.repo_root else {}))
        self._lock = threading.RLock()

    def state(self) -> dict[str, Any]:
        record = read_durable_state(self.store)
        if record is None:
            raise ManifestPersistenceError("durable_state_missing", "portfolio control-loop state is missing")
        errors = validate_control_loop_state(record.state)
        if errors:
            raise ManifestPersistenceError("durable_state_invalid", "; ".join(errors))
        return copy.deepcopy(dict(record.state))

    def initialize(
        self,
        *,
        coordinator_task_id: str,
        owner_id: str,
        now: datetime | None = None,
        capacity: int | Mapping[str, Any] | None = None,
        stage: int = 1,
        stage_verification: str = "baseline",
        protected_refs: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock, _durable_store_lock(self.store):
            existing = read_durable_state(self.store)
            if existing is not None:
                state = dict(existing.state)
                if state.get("controller", {}).get("taskId") != coordinator_task_id:
                    raise ValueError("coordinator_task_identity_mismatch")
                return state
            state = new_control_loop_state(
                coordinator_task_id=coordinator_task_id,
                owner_id=owner_id,
                now=now,
                lease_seconds=int(self.config.get("leaseSeconds", 180)),
                capacity=capacity,
                stage=stage,
                stage_verification=stage_verification,
                protected_refs=protected_refs,
            )
            persist_durable_state(state, self.store)
            return state

    def register_lane(
        self,
        lane_id: str,
        *,
        packet_id: str | None = None,
        dependencies: Sequence[str] = (),
        conflicts: Sequence[str] = (),
        priority: int = 0,
        provider: str = "unknown",
    ) -> dict[str, Any]:
        with self._lock, _durable_store_lock(self.store):
            state = self.state()
            if lane_id in state["lanes"]:
                return state["lanes"][lane_id]
            lane = {
                "laneId": lane_id,
                "packetId": packet_id or lane_id,
                "state": "PREPARED" if not dependencies else "WAITING_DEPENDENCY",
                "dependencies": list(dependencies),
                "conflicts": list(conflicts),
                "priority": priority,
                "provider": provider,
                "workerId": None,
            }
            state["lanes"][lane_id] = lane
            state["dependencyGraph"][lane_id] = list(dependencies)
            persist_durable_state(state, self.store)
            return copy.deepcopy(lane)

    def _lease_or_raise(self, state: dict[str, Any], *, holder: str, task_id: str, now: datetime) -> None:
        controller = state["controller"]
        if controller.get("taskId") != task_id or controller.get("state") != "LIVE":
            raise PermissionError("coordinator_retired")
        lease = state.get("lease") or {}
        if validate_control_loop_lease(lease, holder=holder, coordinator_task_id=task_id, now=now):
            return
        try:
            expires = datetime.fromisoformat(str(lease["expiresAt"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            expires = now
        if expires > now and lease.get("holder") != holder:
            raise PermissionError("controller_lease_held")
        state["lease"] = {
            "holder": holder,
            "coordinatorTaskId": task_id,
            "nonce": _digest({"task": task_id, "holder": holder, "at": _utc(now)})[7:31],
            "acquiredAt": _utc(now),
            "expiresAt": _utc(now + timedelta(seconds=int(self.config.get("leaseSeconds", 180)))),
        }

    def _process_terminal_workers(
        self,
        state: dict[str, Any],
        observations: Mapping[str, Mapping[str, Any]],
        *,
        archive_worker: Callable[..., Any] | None,
        now: datetime,
    ) -> None:
        for worker_id, original in list(state["workers"].items()):
            worker = dict(original)
            if worker.get("state") not in ACTIVE_WORKER_STATES:
                continue
            observation = dict(observations.get(worker_id) or {})
            if not _worker_terminal(worker, observation):
                continue
            archive = _invoke_hook(archive_worker, {**worker, "observation": observation})
            if archive is None:
                archive = {
                    "archived": True,
                    "readback": True,
                    "archiveId": _event_id("archive", {"workerId": worker_id, "observation": observation}),
                }
            if archive.get("archived") is not True or archive.get("readback") is not True:
                state["blockers"].append(f"worker={worker_id}:archive_readback_missing")
                continue
            accepted = _accepted(observation, worker)
            worker.update(
                {
                    "state": "ARCHIVED",
                    "terminalState": "TERMINAL_ACCEPT" if accepted else "TERMINAL_REJECT",
                    "result": observation.get("result") or observation.get("conclusion") or observation.get("status"),
                    "archive": dict(archive),
                    "archivedAt": _utc(now),
                }
            )
            state["workers"][worker_id] = worker
            lane_id = str(worker.get("laneId") or "")
            lane = state["lanes"].get(lane_id)
            if isinstance(lane, dict):
                lane["state"] = "COMPLETE" if accepted else "TERMINAL_REJECT"
                lane["workerId"] = None
            _append_unique(
                state["events"],
                {
                    "id": _event_id("terminal", {"workerId": worker_id, "result": worker.get("result")}),
                    "kind": "terminal_archived",
                    "workerId": worker_id,
                    "laneId": lane_id,
                    "accepted": accepted,
                    "archiveId": archive.get("archiveId"),
                    "reconciled": True,
                    "result": worker.get("result"),
                },
            )

    def _replace_stalled(
        self,
        state: dict[str, Any],
        *,
        now: datetime,
        replace_worker: Callable[..., Any] | None,
    ) -> None:
        stale_after = int(self.config.get("stalledAfterSeconds", DEFAULT_STALE_AFTER_SECONDS))
        for worker_id, original in list(state["workers"].items()):
            worker = dict(original)
            if worker.get("state") not in ACTIVE_WORKER_STATES or not is_worker_stalled(
                worker, now=now, stale_after_seconds=stale_after
            ):
                continue
            replacement_id = f"{worker_id}-replacement-{int(worker.get('replacementCount') or 0) + 1}"
            try:
                replacement = replace_stalled_worker(
                    worker,
                    replacement_id=replacement_id,
                    now=now,
                    stale_after_seconds=stale_after,
                    replacement_limit=int(self.config.get("replacementLimit", 1)),
                )
            except ValueError as exc:
                state["blockers"].append(f"worker={worker_id}:{exc}")
                continue
            supplied = _invoke_hook(replace_worker, {**worker, "replacement": replacement})
            if supplied:
                replacement.update(supplied)
            state["workers"][worker_id] = {
                **worker,
                "state": "REPLACED",
                "replacedAt": _utc(now),
                "replacementCount": replacement.get("replacementCount", 1),
                "replacementId": replacement_id,
            }
            state["workers"][replacement_id] = replacement
            lane = state["lanes"].get(str(worker.get("laneId") or ""))
            if isinstance(lane, dict):
                lane["workerId"] = replacement_id
                lane["state"] = "RUNNING"
            _append_unique(
                state["events"],
                {"id": _event_id("replacement", replacement), "kind": "worker_replaced", "workerId": worker_id, "replacementId": replacement_id},
            )

    def _dispatch_ready(
        self,
        state: dict[str, Any],
        *,
        dispatch_worker: Callable[..., Any] | None,
        now: datetime,
    ) -> list[str]:
        safe_capacity = calculate_safe_capacity(self.config, state)
        active_workers = [
            worker
            for worker in state["workers"].values()
            if worker.get("state") in ACTIVE_WORKER_STATES
        ]
        active = len(active_workers)
        active_by_provider = {"cursor": 0, "luna": 0, "generic": 0}
        for worker in active_workers:
            provider = str(worker.get("provider") or "").strip().lower()
            bucket = "cursor" if provider in CURSOR_PROVIDERS else "luna" if provider in LUNA_PROVIDERS else "generic"
            active_by_provider[bucket] += 1
        dispatched: list[str] = []
        capacity = int(safe_capacity.get("total") or 0)
        occupied_conflicts = {
            conflict
            for worker in state["workers"].values()
            if worker.get("state") in ACTIVE_WORKER_STATES
            for conflict in state["lanes"].get(str(worker.get("laneId") or ""), {}).get("conflicts", [])
        }
        ordered = sorted(
            state["lanes"].items(),
            key=lambda row: (-int(row[1].get("priority") or 0), row[0]),
        )
        for lane_id, lane in ordered:
            if lane.get("state") not in {"PREPARED", "WAITING_DEPENDENCY"}:
                continue
            dependencies = lane.get("dependencies") or []
            missing = [dependency for dependency in dependencies if dependency not in state["lanes"]]
            if missing:
                lane["state"] = "BLOCKED"
                state["blockers"].append(
                    f"lane={lane_id}:missing_dependency={','.join(str(item) for item in missing)}"
                )
                continue
            if any(state["lanes"].get(dep, {}).get("state") != "COMPLETE" for dep in dependencies):
                lane["state"] = "WAITING_DEPENDENCY"
                continue
            conflicts = set(lane.get("conflicts") or [])
            if conflicts & occupied_conflicts:
                continue
            lane_provider = str(lane.get("provider") or "").strip().lower()
            provider_bucket = (
                "cursor" if lane_provider in CURSOR_PROVIDERS
                else "luna" if lane_provider in LUNA_PROVIDERS
                else "generic"
            )
            provider_limit = (
                int(safe_capacity.get(provider_bucket) or 0)
                if provider_bucket != "generic"
                else capacity
            )
            if active_by_provider[provider_bucket] >= provider_limit:
                continue
            default_id = f"{lane_id}-worker-{_digest({'lane': lane_id, 'events': len(state['events'])})[7:19]}"
            supplied = _invoke_hook(dispatch_worker, lane) if dispatch_worker else None
            if supplied and supplied.get("accepted") is False:
                state["blockers"].append(f"lane={lane_id}:dispatch_not_accepted")
                continue
            if supplied and supplied.get("readback") is False:
                state["blockers"].append(f"lane={lane_id}:dispatch_readback_missing")
                continue
            requested_id = str((supplied or {}).get("workerId") or default_id)
            existing_worker = state["workers"].get(requested_id)
            if isinstance(existing_worker, Mapping) and existing_worker.get("state") in ACTIVE_WORKER_STATES:
                state["blockers"].append(f"lane={lane_id}:duplicate_worker_identity={requested_id}")
                continue
            worker = {
                "workerId": requested_id,
                "laneId": lane_id,
                "state": "RUNNING",
                "provider": (supplied or {}).get("provider") or lane.get("provider") or "controller",
                "startedAt": _utc(now),
                "lastHeartbeatAt": _utc(now),
                "lastMaterialProgressAt": _utc(now),
                "replacementCount": 0,
            }
            worker.update(supplied or {})
            worker["dispatch"] = {
                "accepted": True,
                "readback": True,
                "provider": provider_bucket,
            }
            state["workers"][worker["workerId"]] = worker
            lane["state"] = "RUNNING"
            lane["workerId"] = worker["workerId"]
            active += 1
            active_by_provider[provider_bucket] += 1
            dispatched.append(lane_id)
            occupied_conflicts.update(conflicts)
            _append_unique(
                state["events"],
                {
                    "id": _event_id("dispatch", worker),
                    "kind": "worker_dispatched",
                    "workerId": worker["workerId"],
                    "laneId": lane_id,
                    "dependencyReady": bool(dependencies),
                    "dependencies": list(dependencies),
                    "dispatchReadback": True,
                    "provider": provider_bucket,
                },
            )
        return dispatched

    @staticmethod
    def _safe_ready_lanes(state: Mapping[str, Any]) -> list[str]:
        lanes = state.get("lanes") if isinstance(state.get("lanes"), Mapping) else {}
        workers = state.get("workers") if isinstance(state.get("workers"), Mapping) else {}
        active_lanes = {
            str(worker.get("laneId"))
            for worker in workers.values()
            if isinstance(worker, Mapping) and worker.get("state") in ACTIVE_WORKER_STATES
        }
        ready: list[str] = []
        for lane_id, lane in lanes.items():
            if not isinstance(lane, Mapping) or lane.get("state") not in {"PREPARED", "WAITING_DEPENDENCY"}:
                continue
            dependencies = lane.get("dependencies") or []
            if any(
                not isinstance(lanes.get(str(dep)), Mapping)
                or lanes[str(dep)].get("state") != "COMPLETE"
                for dep in dependencies
            ):
                continue
            conflicts = set(lane.get("conflicts") or [])
            if any(
                conflicts & set((lanes.get(active_lane) or {}).get("conflicts") or [])
                for active_lane in active_lanes
            ):
                continue
            ready.append(str(lane_id))
        return sorted(ready)

    def invoke(
        self,
        *,
        coordinator_task_id: str,
        holder: str,
        trigger: str = "hourly",
        invocation_id: str | None = None,
        now: datetime | None = None,
        observations: Mapping[str, Mapping[str, Any]] | None = None,
        archive_worker: Callable[..., Any] | None = None,
        replace_worker: Callable[..., Any] | None = None,
        dispatch_worker: Callable[..., Any] | None = None,
        protected_truth: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if trigger not in ALLOWED_TRIGGERS:
            raise ValueError("control_loop_trigger_invalid")
        clock = _now(now)
        key = control_loop_invocation_key(
            coordinator_task_id=coordinator_task_id,
            trigger=trigger,
            invocation_id=invocation_id or _utc(clock),
        )
        with self._lock, _durable_store_lock(self.store):
            state = self.state()
            prior = state["invocations"].get(key)
            if isinstance(prior, Mapping):
                return copy.deepcopy(dict(prior))
            if state.get("activeTurn") and state.get("activeTurn", {}).get("key") != key:
                return {
                    "invocationKey": key,
                    "status": "RUNNING",
                    "language": "RUNNING",
                    "blocker": "control_loop_turn_in_progress",
                    "coalesced": True,
                }
            try:
                self._lease_or_raise(state, holder=holder, task_id=coordinator_task_id, now=clock)
            except PermissionError as exc:
                return {
                    "invocationKey": key,
                    "status": "HOLD",
                    "language": "NOT ISSUED",
                    "blocker": str(exc),
                    "coalesced": False,
                }
            state["activeTurn"] = {"key": key, "startedAt": _utc(clock), "trigger": trigger}
            persist_durable_state(state, self.store)
            try:
                self._process_terminal_workers(
                    state, observations or {}, archive_worker=archive_worker, now=clock
                )
                self._replace_stalled(state, now=clock, replace_worker=replace_worker)
                dispatched = self._dispatch_ready(
                    state, dispatch_worker=dispatch_worker, now=clock
                )
                safe_capacity = calculate_safe_capacity(self.config, state)
                state["safeCapacity"] = safe_capacity
                safe_ready = self._safe_ready_lanes(state)
                if safe_ready:
                    state["utilizationGap"] = {
                        "code": UTILIZATION_GAP,
                        "readyLanes": safe_ready,
                        "dispatchedLanes": dispatched,
                        "safeCapacity": safe_capacity,
                    }
                    state["blockers"].append(UTILIZATION_GAP)
                else:
                    state.pop("utilizationGap", None)
                    state["blockers"] = [
                        item for item in state.get("blockers", []) if item != UTILIZATION_GAP
                    ]
                _refresh_heartbeat_acceptance(state)
                if protected_truth and protected_truth.get("valid") is False:
                    state["blockers"].append(str(protected_truth.get("blocker") or "protected_truth_unverified"))
                state["blockers"] = list(dict.fromkeys(str(item) for item in state.get("blockers", []) if str(item)))
                report = build_portfolio_status(state, protected_truth=protected_truth)
                report["safeCapacity"] = safe_capacity
                report["dispatchedLanes"] = dispatched
                report["utilizationGap"] = copy.deepcopy(state.get("utilizationGap"))
                state["lastReport"] = report
                state["activeTurn"] = None
                state["events"] = state["events"][-MAX_STATE_EVENTS:]
                result = {
                    "invocationKey": key,
                    "trigger": trigger,
                    "status": report["status"],
                    "language": report["language"],
                    "report": report,
                    "dispatchedLanes": dispatched,
                    "utilizationGap": copy.deepcopy(state.get("utilizationGap")),
                    "coalesced": False,
                }
                state["invocations"][key] = copy.deepcopy(result)
                persist_durable_state(state, self.store)
                return result
            except Exception:
                state["activeTurn"] = None
                persist_durable_state(state, self.store)
                raise

    def recover(self, **kwargs: Any) -> dict[str, Any]:
        """Run the same idempotent turn after reading durable state."""
        read_worker = kwargs.pop("read_worker", None)
        read_protected_refs = kwargs.pop("read_protected_refs", None)
        if read_worker is not None:
            observations = dict(kwargs.get("observations") or {})
            for worker_id, worker in self.state().get("workers", {}).items():
                if worker.get("state") in ACTIVE_WORKER_STATES and worker_id not in observations:
                    observed = read_worker(copy.deepcopy(worker))
                    if isinstance(observed, Mapping):
                        observations[worker_id] = dict(observed)
            kwargs["observations"] = observations
        if read_protected_refs is not None:
            truth = read_protected_refs()
            if isinstance(truth, Mapping):
                kwargs["protected_truth"] = dict(truth)
        return self.invoke(**kwargs)

    def handover(
        self,
        *,
        predecessor_task_id: str,
        successor_task_id: str,
        successor_owner_id: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        with self._lock, _durable_store_lock(self.store):
            state = self.state()
            controller = state["controller"]
            if controller.get("taskId") != predecessor_task_id or controller.get("state") != "LIVE":
                raise PermissionError("predecessor_not_live_owner")
            if state.get("activeTurn"):
                raise PermissionError("handover_in_progress")
            clock = _now(now)
            handoff = create_handover(
                state,
                predecessor_task_id=predecessor_task_id,
                successor_task_id=successor_task_id,
                successor_owner_id=successor_owner_id,
                now=clock,
                lease_seconds=int(self.config.get("leaseSeconds", 180)),
            )
            persist_durable_state(handoff, self.store)
            return handoff


def configure_automation(
    state: dict[str, Any],
    *,
    automation_id: str,
    target_task_id: str,
    cadence_seconds: int = 3600,
    remaining_runs: int,
    now: datetime | None = None,
    protocol_version: str = PORTFOLIO_CONTROL_LOOP_VERSION,
) -> dict[str, Any]:
    if cadence_seconds not in {3600, 7200}:
        raise ValueError("automation_cadence_must_be_one_or_two_hours")
    if remaining_runs < 0:
        raise ValueError("automation_remaining_runs_invalid")
    clock = _now(now)
    existing = state.setdefault("automations", {}).get(automation_id)
    if isinstance(existing, dict):
        existing.update(
            {
                "targetTaskId": target_task_id,
                "cadenceSeconds": cadence_seconds,
                "protocolVersion": protocol_version,
                "enabled": existing.get("remainingRuns", remaining_runs) > 0,
                "nextDueAt": _utc(clock + timedelta(seconds=cadence_seconds))
                if not existing.get("lastDeliveredAt")
                else _utc(datetime.fromisoformat(str(existing["lastDeliveredAt"]).replace("Z", "+00:00")) + timedelta(seconds=cadence_seconds)),
            }
        )
        if "remainingRuns" not in existing:
            existing["remainingRuns"] = remaining_runs
        _refresh_heartbeat_acceptance(state)
        return copy.deepcopy(existing)
    record = {
        "automationId": automation_id,
        "targetTaskId": target_task_id,
        "cadenceSeconds": cadence_seconds,
        "remainingRuns": remaining_runs,
        "deliveredRuns": 0,
        "retryCount": 0,
        "protocolVersion": protocol_version,
        "enabled": remaining_runs > 0,
        "createdAt": _utc(clock),
        "nextDueAt": _utc(clock + timedelta(seconds=cadence_seconds)),
        "deliveryReceipts": [],
    }
    state["automations"][automation_id] = record
    _refresh_heartbeat_acceptance(state)
    return copy.deepcopy(record)


def record_automation_delivery(
    state: dict[str, Any],
    *,
    automation_id: str,
    delivery_id: str,
    scheduled_at: datetime,
    actual_delivery_at: datetime | None,
    result: str,
    target_task_id: str,
    retry_count: int = 0,
    max_retries: int = 1,
) -> dict[str, Any]:
    automation = state.get("automations", {}).get(automation_id)
    if not isinstance(automation, dict) or automation.get("targetTaskId") != target_task_id:
        raise ValueError("automation_target_identity_mismatch")
    receipts = automation.setdefault("deliveryReceipts", [])
    existing = next((row for row in receipts if row.get("deliveryId") == delivery_id), None)
    if existing is not None:
        _refresh_heartbeat_acceptance(state)
        return copy.deepcopy(automation)
    confirmed = actual_delivery_at is not None and str(result).upper() in {"DELIVERED", "SUCCESS", "CONFIRMED"}
    receipt = {
        "deliveryId": delivery_id,
        "scheduledAt": _utc(scheduled_at),
        "actualDeliveryAt": _utc(actual_delivery_at) if actual_delivery_at else None,
        "targetTaskId": target_task_id,
        "result": result,
        "retryCount": retry_count,
        "remainingRuns": automation.get("remainingRuns", 0),
    }
    receipts.append(receipt)
    if confirmed:
        automation["remainingRuns"] = max(0, int(automation.get("remainingRuns") or 0) - 1)
        automation["deliveredRuns"] = int(automation.get("deliveredRuns") or 0) + 1
        automation["lastDeliveredAt"] = _utc(actual_delivery_at)
        automation["nextDueAt"] = _utc(actual_delivery_at + timedelta(seconds=int(automation["cadenceSeconds"])))
        automation["retryCount"] = 0
        automation["enabled"] = automation["remainingRuns"] > 0
    else:
        automation["retryCount"] = max(int(automation.get("retryCount") or 0), retry_count + 1)
        if automation["retryCount"] > max_retries:
            automation["enabled"] = False
            automation["permanentFailure"] = "automation_delivery_failed"
    receipt["remainingRuns"] = automation.get("remainingRuns", 0)
    _refresh_heartbeat_acceptance(state)
    return copy.deepcopy(automation)


def due_automations(state: Mapping[str, Any], *, now: datetime) -> tuple[dict[str, Any], ...]:
    due: list[dict[str, Any]] = []
    for value in (state.get("automations") or {}).values():
        if not isinstance(value, Mapping) or value.get("enabled") is not True:
            continue
        try:
            if now.astimezone(timezone.utc) >= datetime.fromisoformat(str(value["nextDueAt"]).replace("Z", "+00:00")):
                due.append(dict(value))
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(sorted(due, key=lambda row: str(row.get("automationId"))))


def create_handover(
    state: Mapping[str, Any],
    *,
    predecessor_task_id: str,
    successor_task_id: str,
    successor_owner_id: str,
    now: datetime | None = None,
    lease_seconds: int = 180,
) -> dict[str, Any]:
    updated = copy.deepcopy(dict(state))
    controller = updated.get("controller") or {}
    if controller.get("taskId") != predecessor_task_id or controller.get("state") != "LIVE":
        raise PermissionError("predecessor_not_live_owner")
    clock = _now(now)
    handover = {
        "handoverId": _event_id("handover", {"from": predecessor_task_id, "to": successor_task_id, "at": _utc(clock)}),
        "predecessorTaskId": predecessor_task_id,
        "predecessorState": "READ_ONLY",
        "successorTaskId": successor_task_id,
        "successorOwnerId": successor_owner_id,
        "completedAt": _utc(clock),
        "finite": True,
        "reverificationRequired": True,
        "protectedRefs": copy.deepcopy(updated.get("protectedRefs") or {}),
        "canonicalPacketLedger": [
            {"laneId": lane_id, "state": lane.get("state"), "packetId": lane.get("packetId")}
            for lane_id, lane in (updated.get("lanes") or {}).items()
        ],
        "activeWorkers": [
            {"workerId": worker_id, "laneId": worker.get("laneId"), "state": worker.get("state")}
            for worker_id, worker in (updated.get("workers") or {}).items()
            if worker.get("state") in ACTIVE_WORKER_STATES
        ],
        "blockers": list(updated.get("blockers") or []),
        "dependencyGraph": copy.deepcopy(updated.get("dependencyGraph") or {}),
        "authorizations": copy.deepcopy(updated.get("authorizations") or {}),
        "routingRegistryVersion": updated.get("routingRegistryVersion"),
        "outstandingAutomation": copy.deepcopy(updated.get("automations") or {}),
    }
    updated["handover"] = handover
    updated.setdefault("controllerHistory", []).append(
        {
            "taskId": predecessor_task_id,
            "ownerId": controller.get("ownerId"),
            "state": "READ_ONLY",
            "retiredAt": _utc(clock),
            "handoverId": handover["handoverId"],
        }
    )
    updated["controller"] = {
        "taskId": successor_task_id,
        "ownerId": successor_owner_id,
        "state": "LIVE",
        "generation": int(controller.get("generation") or 0) + 1,
    }
    updated["lease"] = {
        "holder": successor_owner_id,
        "coordinatorTaskId": successor_task_id,
        "nonce": _digest({"handoverId": handover["handoverId"], "owner": successor_owner_id})[7:31],
        "acquiredAt": _utc(clock),
        "expiresAt": _utc(clock + timedelta(seconds=lease_seconds)),
    }
    for automation in (updated.get("automations") or {}).values():
        if isinstance(automation, dict):
            automation["targetTaskId"] = successor_task_id
            automation["protocolVersion"] = PORTFOLIO_CONTROL_LOOP_VERSION
    _append_unique(
        updated.setdefault("events", []),
        {"id": handover["handoverId"], "kind": "handover_complete", "predecessorTaskId": predecessor_task_id, "successorTaskId": successor_task_id},
    )
    return updated


def transfer_terminal_event(state: dict[str, Any], event: Mapping[str, Any], *, successor_task_id: str) -> bool:
    """Forward one terminal event once; retired owners cannot restart work."""

    if (state.get("controller") or {}).get("taskId") != successor_task_id:
        return False
    event_id = str(event.get("id") or "")
    if not event_id or event_id in state.setdefault("transferredTerminalEvents", []):
        return False
    state["transferredTerminalEvents"].append(event_id)
    _append_unique(state.setdefault("events", []), {**dict(event), "kind": "terminal_event_transferred", "transferredTo": successor_task_id})
    return True


def run_portfolio_control_loop(loop: PortfolioControlLoop, **kwargs: Any) -> dict[str, Any]:
    return loop.invoke(**kwargs)


run_control_loop = run_portfolio_control_loop
upsert_automation = configure_automation
handover_control_loop = create_handover


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--holder", required=True)
    parser.add_argument("--trigger", choices=sorted(ALLOWED_TRIGGERS), default="hourly")
    parser.add_argument("--invocation-id")
    args = parser.parse_args(argv)
    store = JsonFileControlLoopStore(args.state)
    loop = PortfolioControlLoop(store, repo_root=Path(__file__).resolve().parents[2])
    if store.read() is None:
        loop.initialize(coordinator_task_id=args.task_id, owner_id=args.holder)
    result = loop.invoke(
        coordinator_task_id=args.task_id,
        holder=args.holder,
        trigger=args.trigger,
        invocation_id=args.invocation_id,
    )
    print(json.dumps(result, sort_keys=True))
    return 20 if result.get("utilizationGap") else (0 if result.get("status") != "HOLD" else 20)


if __name__ == "__main__":
    raise SystemExit(main())
