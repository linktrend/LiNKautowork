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


_HANDOFF_REPOSITORY = re.compile(r"^[^/\s]+/[^/\s]+$")
_HANDOFF_STATES = frozenset({"prepared", "accepted", "integrated", "blocked", "stale"})
_HANDOFF_VERDICTS = frozenset({"accepted", "blocked", "rejected"})


def _handoff_identity(value: Any) -> dict[str, str] | None:
    """Normalize the small identity vocabulary used by provider receipts."""

    if not isinstance(value, Mapping):
        return None
    nested = value.get("provider") or value.get("producer")
    if isinstance(nested, Mapping):
        value = nested
    repository = value.get("repository")
    commit = value.get("commit", value.get("headCommit"))
    tree = value.get("tree", value.get("gitTree"))
    if (
        not isinstance(repository, str)
        or _HANDOFF_REPOSITORY.fullmatch(repository) is None
        or not isinstance(commit, str)
        or not re.fullmatch(r"[0-9a-f]{40}", commit)
        or not isinstance(tree, str)
        or not re.fullmatch(r"[0-9a-f]{40}", tree)
    ):
        return None
    return {"repository": repository, "commit": commit, "tree": tree}


def _handoff_blocker(
    handoff: Mapping[str, Any] | None,
    *,
    provider: Mapping[str, str] | None = None,
    receipt: Mapping[str, Any] | None = None,
    reason: str = "provider_handoff_required",
) -> dict[str, Any]:
    source = handoff.get("blocker") if isinstance(handoff, Mapping) else None
    source = source if isinstance(source, Mapping) else {}
    blocking_repository = source.get("blockingRepository")
    if not isinstance(blocking_repository, str) or not blocking_repository:
        blocking_repository = (provider or {}).get("repository")
    owner = source.get("owner") or (receipt or {}).get("owner")
    next_action = source.get("nextAction")
    if not isinstance(next_action, str) or not next_action:
        next_action = "obtain the accepted protected provider receipt"
    return {
        "blockingRepository": blocking_repository or "unknown/unknown",
        "handoffClass": source.get("handoffClass", "provider-consumer"),
        "owner": owner if isinstance(owner, str) and owner else "owner_missing",
        "nextAction": next_action,
        "reason": reason,
    }


def _receipt_identity(receipt: Mapping[str, Any]) -> dict[str, str] | None:
    identity = _handoff_identity(receipt)
    if identity is not None:
        return identity
    for key in ("provider", "producer", "candidateIdentity", "providerIdentity"):
        identity = _handoff_identity(receipt.get(key))
        if identity is not None:
            return identity
    provider = {
        "repository": receipt.get("providerRepository"),
        "commit": receipt.get("providerCommit"),
        "tree": receipt.get("providerTree"),
    }
    return _handoff_identity(provider)


def _receipt_is_accepted(receipt: Mapping[str, Any]) -> bool:
    status = receipt.get("status")
    accepted = receipt.get("accepted") is True or receipt.get("verdict") == "accepted"
    return (isinstance(status, str) and status.lower() in {"accepted", "protected-integrated"}) or accepted


def evaluate_provider_consumer_handoff(
    handoff: Mapping[str, Any] | None,
    *,
    protected_provider_identity: Mapping[str, Any] | None = None,
    accepted_receipt: Mapping[str, Any] | None = None,
    consumer_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the fail-closed admission decision for a typed handoff.

    The protected provider identity and accepted receipt are deliberately
    separate inputs. A receipt copied into a consumer branch is not authority.
    """

    typed = handoff if isinstance(handoff, Mapping) else None
    provider = _handoff_identity(typed.get("provider") if typed else None)
    producer = _handoff_identity(typed.get("producer") if typed else None)
    if provider is not None and producer is not None and provider != producer:
        return {
            "admitted": False,
            "status": "BLOCKED",
            "reason": "handoff_provider_identity_mismatch",
            "integrationClaimed": False,
            "preparationAllowed": True,
            "blocker": _handoff_blocker(typed, provider=provider),
        }
    if provider is None:
        provider = producer
    consumer = _handoff_identity(typed.get("consumer") if typed else None)
    expected_provider = _handoff_identity(protected_provider_identity)
    expected_consumer = _handoff_identity(consumer_identity) if consumer_identity is not None else None
    receipt = accepted_receipt if isinstance(accepted_receipt, Mapping) else None
    blocker = _handoff_blocker(typed, provider=expected_provider or provider, receipt=receipt)

    def blocked(reason: str, *, block: Mapping[str, Any] | None = None) -> dict[str, Any]:
        details = dict(block or blocker)
        details.setdefault("reason", reason)
        return {
            "admitted": False,
            "status": "BLOCKED",
            "reason": reason,
            "integrationClaimed": False,
            "preparationAllowed": True,
            "blocker": details,
        }

    if typed is None:
        return blocked("handoff_missing")
    if typed.get("schemaVersion") != 1 or typed.get("kind") != "provider-consumer-handoff":
        return blocked("handoff_schema_invalid")
    if provider is None or consumer is None:
        return blocked("handoff_identity_invalid")
    if not _valid_digest(typed.get("artifactDigest")) or not _valid_digest(typed.get("contractDigest")):
        return blocked("handoff_digest_invalid")
    verdict = typed.get("verdict")
    lifecycle = typed.get("lifecycleState")
    if verdict not in _HANDOFF_VERDICTS or lifecycle not in _HANDOFF_STATES:
        return blocked("handoff_lifecycle_invalid")
    if typed.get("independentPreparationAllowed") is not True:
        return blocked("handoff_preparation_contract_invalid")
    if expected_provider is None:
        return blocked("protected_provider_identity_missing")
    if provider != expected_provider:
        return blocked("stale_provider_pin")
    if expected_consumer is not None and consumer != expected_consumer:
        return blocked("consumer_identity_mismatch")
    if receipt is None:
        return blocked("accepted_receipt_missing")
    if not _receipt_is_accepted(receipt):
        return blocked("accepted_receipt_required")
    if receipt.get("protected") is not True and receipt.get("protectedIntegrated") is not True:
        return blocked("accepted_receipt_not_protected")
    receipt_identity = _receipt_identity(receipt)
    if receipt_identity != expected_provider:
        return blocked("accepted_receipt_provider_mismatch")
    receipt_digest = receipt.get("receiptDigest")
    embedded = typed.get("acceptedReceipt")
    if not _valid_digest(receipt_digest):
        return blocked("accepted_receipt_digest_invalid")
    if not isinstance(embedded, Mapping) or embedded.get("receiptDigest") != receipt_digest:
        return blocked("accepted_receipt_identity_mismatch")
    if embedded.get("status") != "accepted" or embedded.get("protected") is not True:
        return blocked("accepted_receipt_not_protected")
    embedded_provider = _handoff_identity(embedded.get("provider"))
    embedded_producer = _handoff_identity(embedded.get("producer"))
    if embedded_provider is not None and embedded_producer is not None and embedded_provider != embedded_producer:
        return blocked("accepted_receipt_provider_mismatch")
    if (embedded_provider or embedded_producer) != expected_provider:
        return blocked("accepted_receipt_provider_mismatch")
    if verdict != "accepted" or lifecycle not in {"accepted", "integrated"}:
        return blocked("provider_handoff_not_accepted")
    if lifecycle == "integrated" and typed.get("integrationClaimed") is not True:
        return blocked("integration_claim_invalid")
    return {
        "admitted": True,
        "status": "ADMITTED",
        "reason": "accepted_protected_provider_receipt",
        "integrationClaimed": lifecycle == "integrated",
        "preparationAllowed": True,
        "blocker": None,
        "provider": provider,
        "consumer": consumer,
        "receiptDigest": receipt_digest,
    }


def consume_provider_consumer_handoff(
    handoff: Mapping[str, Any] | None,
    *,
    protected_provider_identity: Mapping[str, Any] | None = None,
    accepted_receipt: Mapping[str, Any] | None = None,
    consumer_identity: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    """Consume a handoff only after exact protected identity and receipt checks."""

    decision = evaluate_provider_consumer_handoff(
        handoff,
        protected_provider_identity=protected_provider_identity,
        accepted_receipt=accepted_receipt,
        consumer_identity=consumer_identity,
    )
    return bool(decision["admitted"]), str(decision["reason"])


def admit_provider_consumer_handoff(
    handoff: Mapping[str, Any] | None,
    *,
    protected_provider_identity: Mapping[str, Any] | None = None,
    accepted_receipt: Mapping[str, Any] | None = None,
    consumer_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the complete admission/blocker projection for status consumers."""

    return evaluate_provider_consumer_handoff(
        handoff,
        protected_provider_identity=protected_provider_identity,
        accepted_receipt=accepted_receipt,
        consumer_identity=consumer_identity,
    )


def build_provider_consumer_handoff(
    *,
    provider: Mapping[str, Any] | None = None,
    producer: Mapping[str, Any] | None = None,
    consumer: Mapping[str, Any] | None = None,
    provider_repository: str | None = None,
    provider_commit: str | None = None,
    provider_tree: str | None = None,
    consumer_repository: str | None = None,
    consumer_commit: str | None = None,
    consumer_tree: str | None = None,
    artifact_digest: str,
    contract_digest: str,
    verdict: str = "blocked",
    lifecycle_state: str = "prepared",
    accepted_receipt: Mapping[str, Any] | None = None,
    blocker: Mapping[str, Any] | None = None,
    integration_claimed: bool = False,
) -> dict[str, Any]:
    """Create the sanitized, versioned handoff representation."""

    provider_value = provider or producer or {
        "repository": provider_repository,
        "commit": provider_commit,
        "tree": provider_tree,
    }
    consumer_value = consumer or {
        "repository": consumer_repository,
        "commit": consumer_commit,
        "tree": consumer_tree,
    }
    provider_identity = _handoff_identity(provider_value)
    consumer_identity_value = _handoff_identity(consumer_value)
    if provider_identity is None or consumer_identity_value is None:
        raise RolloutError("handoff_identity_invalid")
    if not _valid_digest(artifact_digest) or not _valid_digest(contract_digest):
        raise RolloutError("handoff_digest_invalid")
    if verdict not in _HANDOFF_VERDICTS or lifecycle_state not in _HANDOFF_STATES:
        raise RolloutError("handoff_lifecycle_invalid")
    if verdict == "accepted" and lifecycle_state not in {"accepted", "integrated"}:
        raise RolloutError("handoff_lifecycle_invalid")
    if lifecycle_state == "integrated" and not integration_claimed:
        raise RolloutError("integration_claim_invalid")
    if verdict == "accepted" and not isinstance(accepted_receipt, Mapping):
        raise RolloutError("accepted_receipt_missing")
    if verdict != "accepted" and integration_claimed:
        raise RolloutError("integration_claim_invalid")
    if verdict != "accepted" and not isinstance(blocker, Mapping):
        raise RolloutError("handoff_blocker_missing")
    if isinstance(blocker, Mapping):
        required = ("blockingRepository", "handoffClass", "owner", "nextAction")
        if any(not isinstance(blocker.get(key), str) or not blocker.get(key) for key in required):
            raise RolloutError("handoff_blocker_invalid")
        if blocker.get("handoffClass") != "provider-consumer":
            raise RolloutError("handoff_blocker_invalid")
    sanitized_receipt = None
    if isinstance(accepted_receipt, Mapping):
        receipt_identity = _receipt_identity(accepted_receipt)
        digest = accepted_receipt.get("receiptDigest")
        if (
            not _receipt_is_accepted(accepted_receipt)
            or (
                accepted_receipt.get("protected") is not True
                and accepted_receipt.get("protectedIntegrated") is not True
            )
            or receipt_identity != provider_identity
            or not _valid_digest(digest)
        ):
            raise RolloutError("accepted_receipt_invalid")
        sanitized_receipt = {
            "receiptDigest": digest,
            "status": "accepted",
            "protected": True,
            "provider": provider_identity,
        }
    return {
        "schemaVersion": 1,
        "kind": "provider-consumer-handoff",
        "producer": provider_identity,
        "provider": provider_identity,
        "consumer": consumer_identity_value,
        "artifactDigest": artifact_digest,
        "contractDigest": contract_digest,
        "verdict": verdict,
        "lifecycleState": lifecycle_state,
        "acceptedReceipt": sanitized_receipt,
        "blocker": dict(blocker) if isinstance(blocker, Mapping) else None,
        "independentPreparationAllowed": True,
        "integrationClaimed": bool(integration_claimed),
    }


# Explicit alias used by packager callers.
create_provider_consumer_handoff = build_provider_consumer_handoff


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
    handoff: Mapping[str, Any] | None = None,
    provider_handoff: Mapping[str, Any] | None = None,
    protected_provider_identity: Mapping[str, Any] | None = None,
    protected_provider: Mapping[str, Any] | None = None,
    accepted_receipt: Mapping[str, Any] | None = None,
    provider_receipt: Mapping[str, Any] | None = None,
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

    typed_handoff = handoff if handoff is not None else provider_handoff
    if typed_handoff is not None:
        handoff_decision = evaluate_provider_consumer_handoff(
            typed_handoff,
            protected_provider_identity=protected_provider_identity or protected_provider,
            accepted_receipt=accepted_receipt or provider_receipt,
        )
        if not handoff_decision["admitted"]:
            preparation_actions = [
                _action("PREPARE", name, reason="provider_handoff_pending", mutating=False)
                for name in config.targets
                if rows[name]["status"] == "PENDING"
                and (
                    rows[name].get("independentPreparation") is True
                    or rows[name].get("preparationOnly") is True
                    or rows[name].get("consumerPreparation") is True
                )
            ]
            return {
                "status": "BLOCKED",
                "halted": False,
                "systemicFailureTargets": [],
                "isolatedTargets": [],
                "reusedEvidence": [],
                "availableMutationSlots": 0,
                "actions": preparation_actions,
                "criticalPath": ["provider_acceptance", "consumer_integration"],
                "integrationAdmitted": False,
                "integrationClaimed": False,
                "providerHandoff": handoff_decision,
                "blocker": handoff_decision["blocker"],
            }

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

    result = {
        "status": "ACTIVE" if actions or active else "COMPLETE",
        "halted": False,
        "systemicFailureTargets": [],
        "isolatedTargets": isolated,
        "reusedEvidence": reusable,
        "availableMutationSlots": slots,
        "actions": actions,
        "criticalPath": critical,
    }
    if typed_handoff is not None:
        result["integrationAdmitted"] = True
        result["integrationClaimed"] = bool(handoff_decision["integrationClaimed"])
        result["providerHandoff"] = handoff_decision
    return result
