"""Deterministic continuous-utilization admission runtime.

Fills local and hosted slots from packaged config. Does not dispatch paid
models, Fast gates, or GitHub workflows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from core.execution.protocol import admit_resources, schedule_hosted_capacity

UTILIZATION_GAP = "UTILIZATION_GAP"
HOSTED_CONCURRENCY_AUTHORITY = "execution-protocol"
BACKSTOP_SECONDS = 600
UNKNOWN_PROBE_SECONDS = 600
PAID_FALLBACKS = frozenset(
    {"paid", "fast", "fast-gate", "premium", "paid-model", "Fast"}
)
LANE_LOCAL = "local"
LANE_HOSTED = "hosted"
CONFIG_RELATIVE_PATH = (
    "core/managed-core/content/config/continuous-utilization.json"
)
SCHEMA_RELATIVE_PATH = (
    "core/managed-core/schemas/continuous-utilization.schema.json"
)
EXAMPLE_RELATIVE_PATH = (
    "core/managed-core/examples/continuous-utilization.example.json"
)

COMPLETE_SNAPSHOT = {
    "cpu_percent": 10,
    "memory_percent": 10,
    "free_disk_gib": 40,
    "docker_available": True,
}


def load_continuous_utilization_schema(repo_root: Path | str) -> dict[str, Any]:
    path = Path(repo_root).resolve() / SCHEMA_RELATIVE_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def load_continuous_utilization_config(
    repo_root: Path | str,
    *,
    schema: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    document = json.loads((root / CONFIG_RELATIVE_PATH).read_text(encoding="utf-8"))
    loaded = dict(schema) if schema is not None else load_continuous_utilization_schema(root)
    errors = sorted(error.message for error in Draft202012Validator(loaded).iter_errors(document))
    if errors:
        raise ValueError("continuous_utilization_config_invalid: " + "; ".join(errors))
    if document.get("hostedConcurrencyAuthority") != HOSTED_CONCURRENCY_AUTHORITY:
        raise ValueError("hosted_concurrency_authority_required")
    return document


@dataclass(frozen=True)
class WorkItem:
    item_id: str
    lane: str
    priority: int = 0
    dependencies: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    identity: str = ""
    submitted_at: datetime = field(
        default_factory=lambda: datetime(2026, 8, 20, tzinfo=timezone.utc)
    )


@dataclass(frozen=True)
class SchedulerEvent:
    kind: str
    item_id: str | None
    at: datetime
    detail: str = ""


class ContinuousUtilizationScheduler:
    """In-process deterministic admission. Not a hosted worker runtime."""

    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        snapshot: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> None:
        self._config = dict(config)
        self._snapshot: Mapping[str, Any] | None = snapshot
        self._now = now or datetime(2026, 8, 20, tzinfo=timezone.utc)
        self._items: dict[str, WorkItem] = {}
        self._admitted: dict[str, datetime] = {}
        self._queued: list[str] = []
        self._completed: set[str] = set()
        self._delayed: dict[str, str] = {}
        self._rejected: dict[str, str] = {}
        self._probes: dict[str, datetime] = {}
        self.events: list[SchedulerEvent] = []

    @classmethod
    def from_repo(
        cls,
        repo_root: Path | str,
        *,
        snapshot: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> ContinuousUtilizationScheduler:
        return cls(
            load_continuous_utilization_config(repo_root),
            snapshot=snapshot,
            now=now,
        )

    @property
    def max_local(self) -> int:
        return int(self._config["maxAdmittedSlots"]["local"])

    @property
    def max_hosted(self) -> int:
        return int(self._config["maxAdmittedSlots"]["hosted"])

    @property
    def backstop(self) -> timedelta:
        return timedelta(seconds=int(self._config.get("backstopSeconds", BACKSTOP_SECONDS)))

    def set_snapshot(
        self,
        snapshot: Mapping[str, Any] | None,
        *,
        recompute: bool = False,
    ) -> None:
        self._snapshot = snapshot
        if recompute:
            self.recompute("admission")

    def submit(self, item: WorkItem) -> None:
        self._items[item.item_id] = item
        if item.item_id not in self._queued:
            self._queued.append(item.item_id)
        self.recompute("admission")

    def complete(self, item_id: str) -> None:
        self._admitted.pop(item_id, None)
        if item_id in self._queued:
            self._queued.remove(item_id)
        self._completed.add(item_id)
        self._emit("completion", item_id, "completed")
        self.recompute("completion")

    def invalidate(self, item_id: str, *, reason: str = "exact_candidate_changed") -> None:
        self._admitted.pop(item_id, None)
        self._delayed[item_id] = reason
        self._emit("invalidation", item_id, reason)
        self.recompute("invalidation")

    def note_api_rejection(
        self,
        item_id: str,
        *,
        fallback: str | None = None,
    ) -> str:
        if fallback is not None and fallback in PAID_FALLBACKS:
            self._rejected[item_id] = "paid_fallback_forbidden"
            self._admitted.pop(item_id, None)
            self._emit("api_rejection", item_id, "paid_fallback_forbidden")
            self.recompute("api_rejection")
            return "paid_fallback_forbidden"
        self._rejected[item_id] = "hosted_api_rejected"
        self._admitted.pop(item_id, None)
        self._emit("api_rejection", item_id, "hosted_api_rejected")
        self.recompute("api_rejection")
        return "hosted_api_rejected"

    def start_unknown_probe(self, item_id: str) -> None:
        self._probes[item_id] = self._now
        self._admitted.pop(item_id, None)
        self.recompute("admission")

    def tick(self, now: datetime) -> None:
        self._now = now
        expired = [
            item_id
            for item_id, started in self._probes.items()
            if now - started >= self.backstop
        ]
        for item_id in expired:
            del self._probes[item_id]
            self._delayed.pop(item_id, None)
            self._emit("probe_timeout", item_id, "timer_recovery")
        if expired:
            self.recompute("probe_timeout")

    def repair_utilization_gap(self) -> bool:
        before = set(self._admitted)
        admitted = admit_resources(self._snapshot)
        if admitted.admitted and not admitted.uncertain:
            self._probes.clear()
        self._emit("utilization_gap_repair", None, "recompute")
        self.recompute("utilization_gap_repair")
        return set(self._admitted) != before

    def recover_utilization_gap_once(self) -> bool:
        """Perform at most one heartbeat-bounded utilization-gap recovery."""

        if any(event.kind == "utilization_gap_recovery" for event in self.events):
            return False
        changed = self.repair_utilization_gap()
        self._emit("utilization_gap_recovery", None, "bounded_heartbeat_recovery")
        return changed

    def admitted_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._admitted, key=self._sort_key))

    def queued_ids(self) -> tuple[str, ...]:
        return tuple(
            item_id
            for item_id in self._order_ids(self._queued)
            if item_id not in self._admitted
            and item_id not in self._completed
            and item_id not in self._rejected
        )

    def delayed_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._delayed))

    def event_kinds(self) -> tuple[str, ...]:
        return tuple(event.kind for event in self.events)

    def recompute(self, event: str) -> None:
        allowed = set(self._config.get("recomputeOnEvents") or ())
        if allowed and event not in allowed and event != "admission":
            return
        self._admit_eligible()
        if self._has_utilization_gap():
            self._emit(UTILIZATION_GAP, None, "free_slots_with_eligible_work")
            if event == "utilization_gap_repair":
                self._admit_eligible()

    def _emit(self, kind: str, item_id: str | None, detail: str) -> None:
        self.events.append(SchedulerEvent(kind, item_id, self._now, detail))

    def _sort_key(self, item_id: str) -> tuple[int, datetime, str]:
        item = self._items[item_id]
        return (-item.priority, item.submitted_at, item.item_id)

    def _order_ids(self, ids: list[str]) -> list[str]:
        return sorted((item_id for item_id in ids if item_id in self._items), key=self._sort_key)

    def _admitted_in_lane(self, lane: str) -> int:
        return sum(1 for item_id in self._admitted if self._items[item_id].lane == lane)

    def _free_slots(self, lane: str) -> int:
        maximum = self.max_local if lane == LANE_LOCAL else self.max_hosted
        return maximum - self._admitted_in_lane(lane)

    def _dependency_ready(self, item: WorkItem) -> bool:
        return all(dep in self._completed for dep in item.dependencies)

    def _conflict_blocked(self, item: WorkItem) -> bool:
        admitted_conflicts = {
            conflict
            for item_id in self._admitted
            for conflict in self._items[item_id].conflicts
        }
        return any(conflict in admitted_conflicts for conflict in item.conflicts)

    def _lane_capacity_ok(self, item: WorkItem) -> bool:
        if self._free_slots(item.lane) <= 0:
            return False
        if item.lane == LANE_HOSTED:
            verdict = schedule_hosted_capacity(
                self._snapshot,
                available_slots=self._free_slots(item.lane),
            )
            return verdict.scheduled
        admitted = admit_resources(self._snapshot)
        return admitted.admitted and not admitted.uncertain

    def _eligible(self, item_id: str) -> bool:
        item = self._items[item_id]
        if item_id in self._admitted or item_id in self._completed:
            return False
        if item_id in self._delayed or item_id in self._rejected:
            return False
        if item_id in self._probes:
            return False
        if not self._dependency_ready(item):
            return False
        if self._conflict_blocked(item):
            return False
        return True

    def _waiting_for_slot(self, item_id: str) -> bool:
        item = self._items[item_id]
        if item_id in self._admitted or item_id in self._completed:
            return False
        if item_id in self._rejected or item_id in self._delayed:
            return False
        if not self._dependency_ready(item) or self._conflict_blocked(item):
            return False
        return self._free_slots(item.lane) > 0

    def _has_utilization_gap(self) -> bool:
        return any(self._waiting_for_slot(item_id) for item_id in self._items)

    def _admit_eligible(self) -> None:
        for item_id in self._order_ids(list(self._items)):
            if not self._eligible(item_id):
                continue
            item = self._items[item_id]
            if not self._lane_capacity_ok(item):
                continue
            self._admitted[item_id] = self._now
            self._emit("admission", item_id, item.lane)
