"""Generic receipt-bound canary and downstream rollout planning.

The module is deliberately side-effect free.  It converts manifest-declared
cohorts and durable target state into the complete set of safe actions for one
controller turn.  Repository mutation remains behind the caller's protected
Git adapter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_STATUSES = frozenset(
    {"PENDING", "PRESTAGED", "MUTATING", "VERIFYING", "VERIFIED", "FAILED", "ROLLED_BACK"}
)


class RolloutError(ValueError):
    """A rollout declaration or state snapshot is unsafe or inconsistent."""


@dataclass(frozen=True)
class RolloutConfig:
    canary_targets: tuple[str, ...]
    downstream_targets: tuple[str, ...]
    max_parallel: int

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RolloutConfig":
        if not isinstance(payload, Mapping):
            raise RolloutError("rollout_config_invalid")
        allowed = {"canaryTargets", "downstreamTargets", "maxParallel"}
        if set(payload) - allowed:
            raise RolloutError("rollout_config_unknown_field")
        canaries = _target_names(payload.get("canaryTargets", ()), "canaryTargets")
        downstream = _target_names(payload.get("downstreamTargets", ()), "downstreamTargets")
        if set(canaries) & set(downstream):
            raise RolloutError("rollout_target_in_multiple_cohorts")
        if not canaries and not downstream:
            raise RolloutError("rollout_has_no_targets")
        maximum = payload.get("maxParallel")
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
            raise RolloutError("rollout_parallelism_invalid")
        return cls(canaries, downstream, maximum)

    @property
    def targets(self) -> tuple[str, ...]:
        return self.canary_targets + self.downstream_targets


def _target_names(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise RolloutError(f"{field}_invalid")
    names = tuple(value)
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise RolloutError(f"{field}_invalid")
    if len(set(names)) != len(names):
        raise RolloutError(f"{field}_duplicate")
    return names


def _valid_digest(value: str) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _receipt_reusable(
    state: Mapping[str, Any], package_digest: str, environment_digest: str
) -> bool:
    receipt = state.get("receipt")
    return bool(
        isinstance(receipt, Mapping)
        and receipt.get("status") == "PASSED"
        and receipt.get("packageDigest") == package_digest
        and receipt.get("environmentDigest") == environment_digest
        and isinstance(state.get("afterTree"), str)
        and receipt.get("afterTree") == state.get("afterTree")
    )


def _action(kind: str, target: str, *, reason: str, mutating: bool) -> dict[str, Any]:
    return {"kind": kind, "target": target, "reason": reason, "mutating": mutating}


def plan_rollout(
    config: RolloutConfig,
    targets: Iterable[Mapping[str, Any]],
    *,
    package_digest: str,
    environment_digest: str,
) -> dict[str, Any]:
    """Return every action that is safe to begin in this controller turn."""

    if not _valid_digest(package_digest) or not _valid_digest(environment_digest):
        raise RolloutError("rollout_identity_invalid")
    rows: dict[str, Mapping[str, Any]] = {}
    for raw in targets:
        if not isinstance(raw, Mapping):
            raise RolloutError("rollout_target_state_invalid")
        name = raw.get("name")
        status = raw.get("status")
        if not isinstance(name, str) or name not in config.targets or name in rows:
            raise RolloutError("rollout_target_identity_invalid")
        if status not in _STATUSES:
            raise RolloutError("rollout_target_status_invalid")
        rows[name] = raw
    if set(rows) != set(config.targets):
        raise RolloutError("rollout_target_state_incomplete")

    systemic = [
        name
        for name, row in rows.items()
        if row["status"] == "FAILED" and row.get("failureScope") == "SYSTEMIC"
    ]
    if systemic:
        rollback = [
            _action("ROLLBACK", name, reason="systemic_failure", mutating=True)
            for name in config.targets
            if rows[name]["status"] in {"MUTATING", "VERIFYING", "VERIFIED"}
            and isinstance(rows[name].get("beforeTree"), str)
        ]
        return {
            "status": "SYSTEMIC_STOP",
            "halted": True,
            "systemicFailureTargets": systemic,
            "isolatedTargets": [],
            "reusedEvidence": [],
            "availableMutationSlots": 0,
            "actions": rollback,
            "criticalPath": ["rollback", "repair_package", "restart_canary"],
        }

    reusable = [
        name
        for name in config.targets
        if rows[name]["status"] == "VERIFIED"
        and _receipt_reusable(rows[name], package_digest, environment_digest)
    ]
    active = {
        name for name in config.targets if rows[name]["status"] in {"MUTATING", "VERIFYING"}
    }
    isolated = [
        name
        for name in config.targets
        if rows[name]["status"] == "FAILED" and rows[name].get("failureScope") == "REPOSITORY"
    ]
    slots = max(0, config.max_parallel - len(active))
    actions: list[dict[str, Any]] = []

    canary_complete = all(name in reusable for name in config.canary_targets)
    invalidated_canaries = [
        name
        for name in config.canary_targets
        if rows[name]["status"] == "VERIFIED" and name not in reusable
    ]
    canary_candidates = [
        name
        for name in config.canary_targets
        if name not in active
        and name not in isolated
        and name not in reusable
        and rows[name]["status"] not in {"ROLLED_BACK"}
    ]

    if not canary_complete:
        for name in canary_candidates[:slots]:
            reason = "receipt_identity_changed" if name in invalidated_canaries else "canary_required"
            actions.append(_action("UPDATE", name, reason=reason, mutating=True))
        for name in config.downstream_targets:
            if rows[name]["status"] == "PENDING":
                actions.append(
                    _action("PRESTAGE", name, reason="read_only_before_canary", mutating=False)
                )
        critical = ["canary_update", "canary_verify", "downstream_fan_out"]
    else:
        candidates = [
            name
            for name in config.downstream_targets
            if name not in active
            and name not in isolated
            and name not in reusable
            and rows[name]["status"] not in {"ROLLED_BACK"}
        ]
        for name in candidates[:slots]:
            reason = (
                "receipt_identity_changed"
                if rows[name]["status"] == "VERIFIED"
                else "canary_passed"
            )
            actions.append(_action("UPDATE", name, reason=reason, mutating=True))
        critical = ["downstream_fan_out", "portfolio_verify", "closure"]

    return {
        "status": "ACTIVE" if actions or active else "COMPLETE",
        "halted": False,
        "systemicFailureTargets": [],
        "isolatedTargets": isolated,
        "reusedEvidence": reusable,
        "availableMutationSlots": slots,
        "actions": actions,
        "criticalPath": critical,
    }
