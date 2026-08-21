"""PKT-08 canonical manifest persistence and heartbeat self-recovery."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from core.execution.lifecycle import heartbeat_progress_requirements
from core.execution.scheduler import ContinuousUtilizationScheduler, UTILIZATION_GAP
from core.execution.transactional_dispatch import (
    DispatchBudget,
    DispatchIntentStore,
    DispatchResult,
    ExternalDispatchPort,
    dispatch_request_from_safe_action,
    dispatch_transactionally,
)


MAX_PERSISTENCE_ATTEMPTS = 3
HEARTBEAT_RECOVERY_SECONDS = 20 * 60
TRANSITION_KINDS = ("dispatch", "run", "integration", "archive", UTILIZATION_GAP)
CONFIG_RELATIVE_PATH = "core/managed-core/content/config/manifest-persistence.json"
SCHEMA_RELATIVE_PATH = "core/managed-core/schemas/manifest-persistence.schema.json"
MANIFEST_PERSISTENCE_FAILURE = "MANIFEST_PERSISTENCE_FAILURE"


def load_manifest_persistence_config(repo_root: Path | str) -> dict[str, Any]:
    """Load the packaged bounded recovery policy without ambient checkout state."""
    root = Path(repo_root).resolve()
    payload = json.loads((root / CONFIG_RELATIVE_PATH).read_text(encoding="utf-8"))
    if (
        payload.get("schemaVersion") != 1
        or payload.get("amendment") != "V25_PKT08_MANIFEST_PERSISTENCE_RECOVERY"
        or payload.get("maxCompareAndRetryAttempts") != MAX_PERSISTENCE_ATTEMPTS
        or payload.get("requiredAuthorities") != ["cursor", "github", "git"]
        or payload.get("conversationIsAuthority") is not False
        or payload.get("duplicateDispatch") != "suppress"
    ):
        raise ManifestPersistenceError("config_invalid", "manifest persistence policy is not the packaged contract")
    return payload


class ManifestPersistenceError(RuntimeError):
    """Bounded persistence or authority failure."""

    def __init__(self, code: str, detail: str, **diagnostics: Any) -> None:
        self.code = code
        self.detail = detail
        self.diagnostics = diagnostics
        super().__init__(f"{code}: {detail}")


class AuthorityFailure(ManifestPersistenceError):
    """Transient failure reading an external authority."""

    def __init__(self, detail: str, **diagnostics: Any) -> None:
        super().__init__("authority_unavailable", detail, **diagnostics)


class DurableManifestStore(Protocol):
    def read(self) -> Mapping[str, Any] | None:
        ...

    def compare_and_write(
        self,
        expected_revision: int,
        expected_digest: str | None,
        payload: Mapping[str, Any],
    ) -> None:
        ...


class AuthorityPort(Protocol):
    def read_authoritative_state(self, identity: Mapping[str, str]) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class ManifestRead:
    revision: int
    digest: str | None
    manifest: Mapping[str, Any]
    updated_at: str | int | float | None = None
    transition_event: Mapping[str, Any] | None = None


def canonical_manifest_digest(manifest: Mapping[str, Any]) -> str:
    data = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _read_record(store: DurableManifestStore) -> ManifestRead | None:
    raw = store.read()
    if raw is None:
        return None
    if not isinstance(raw, Mapping) or not isinstance(raw.get("revision"), int):
        raise ManifestPersistenceError("storage_invalid", "durable manifest record is malformed")
    manifest = raw.get("manifest")
    if not isinstance(manifest, Mapping):
        raise ManifestPersistenceError("storage_invalid", "durable manifest payload is missing")
    digest = raw.get("digest")
    if digest is not None and not isinstance(digest, str):
        raise ManifestPersistenceError("storage_invalid", "durable manifest digest is malformed")
    observed = canonical_manifest_digest(manifest)
    if digest is not None and digest != observed:
        raise ManifestPersistenceError(
            MANIFEST_PERSISTENCE_FAILURE,
            "durable manifest digest does not match payload",
            expectedDigest=digest,
            observedDigest=observed,
        )
    updated_at = raw.get("updated_at")
    if updated_at is not None and (
        isinstance(updated_at, bool)
        or not isinstance(updated_at, (str, int, float))
    ):
        raise ManifestPersistenceError(
            MANIFEST_PERSISTENCE_FAILURE,
            "durable manifest updated_at is malformed",
        )
    transition_event = raw.get("transition_event")
    if transition_event is not None and not isinstance(transition_event, Mapping):
        raise ManifestPersistenceError(
            MANIFEST_PERSISTENCE_FAILURE,
            "durable manifest transition event is malformed",
        )
    if transition_event is not None:
        if (
            transition_event.get("revision") != int(raw["revision"])
            or transition_event.get("digest") != digest
            or transition_event.get("updated_at") != updated_at
        ):
            raise ManifestPersistenceError(
                MANIFEST_PERSISTENCE_FAILURE,
                "durable manifest transition event is not bound to its record",
            )
    return ManifestRead(
        int(raw["revision"]),
        digest,
        copy.deepcopy(dict(manifest)),
        updated_at,
        copy.deepcopy(dict(transition_event)) if transition_event is not None else None,
    )


def _updated_at_advanced(
    previous: str | int | float | None,
    current: str | int | float,
) -> bool:
    if previous is None:
        return True
    if type(previous) is type(current) and isinstance(current, (int, float, str)):
        return current > previous
    return False


def _validate_transition_event(
    transition_event: Mapping[str, Any],
    *,
    revision: int,
    digest: str,
    updated_at: str | int | float | None,
) -> dict[str, Any]:
    event = copy.deepcopy(dict(transition_event))
    if (
        event.get("revision") != revision
        or event.get("digest") != digest
        or event.get("updated_at") != updated_at
    ):
        raise ManifestPersistenceError(
            MANIFEST_PERSISTENCE_FAILURE,
            "manifest transition event is not bound to the CAS write",
            expectedRevision=revision,
            expectedDigest=digest,
            expectedUpdatedAt=updated_at,
        )
    return event


def persist_manifest(
    manifest: Mapping[str, Any],
    store: DurableManifestStore,
    *,
    max_attempts: int = MAX_PERSISTENCE_ATTEMPTS,
    updated_at: str | int | float | None = None,
    transition_event: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare-and-retry a canonical write, with a fresh read after every write."""

    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    candidate = copy.deepcopy(dict(manifest))
    candidate_digest = canonical_manifest_digest(candidate)
    if updated_at is not None and (
        isinstance(updated_at, bool)
        or not isinstance(updated_at, (str, int, float))
    ):
        raise ManifestPersistenceError(
            MANIFEST_PERSISTENCE_FAILURE,
            "manifest updated_at is malformed",
        )
    if transition_event is not None and not isinstance(transition_event, Mapping):
        raise ManifestPersistenceError(
            MANIFEST_PERSISTENCE_FAILURE,
            "manifest transition event is malformed",
        )
    metadata_requested = updated_at is not None or transition_event is not None
    last_error: ManifestPersistenceError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            current = _read_record(store)
            if (
                current is not None
                and current.digest == candidate_digest
                and current.manifest == candidate
                and not metadata_requested
            ):
                return {
                    "revision": current.revision,
                    "digest": current.digest,
                    "manifest": copy.deepcopy(dict(current.manifest)),
                    "attempts": attempt,
                }
            expected_revision = current.revision if current is not None else 0
            expected_digest = current.digest if current is not None else None
            next_revision = expected_revision + 1
            if (
                updated_at is not None
                and current is not None
                and not _updated_at_advanced(current.updated_at, updated_at)
            ):
                raise ManifestPersistenceError(
                    MANIFEST_PERSISTENCE_FAILURE,
                    "manifest updated_at did not advance monotonically",
                    previousUpdatedAt=current.updated_at,
                    observedUpdatedAt=updated_at,
                )
            event = (
                _validate_transition_event(
                    transition_event,
                    revision=next_revision,
                    digest=candidate_digest,
                    updated_at=updated_at,
                )
                if transition_event is not None
                else None
            )
            payload = {
                "digest": candidate_digest,
                "manifest": candidate,
            }
            if updated_at is not None:
                payload["updated_at"] = updated_at
            if event is not None:
                payload["transition_event"] = event
            store.compare_and_write(expected_revision, expected_digest, payload)
            readback = _read_record(store)
            if (
                readback is not None
                and readback.revision == next_revision
                and readback.digest == candidate_digest
                and readback.manifest == candidate
                and (updated_at is None or readback.updated_at == updated_at)
                and (event is None or readback.transition_event == event)
            ):
                result = {
                    "revision": readback.revision,
                    "digest": readback.digest,
                    "manifest": copy.deepcopy(dict(readback.manifest)),
                    "attempts": attempt,
                }
                if readback.updated_at is not None:
                    result["updated_at"] = readback.updated_at
                if readback.transition_event is not None:
                    result["transition_event"] = copy.deepcopy(
                        dict(readback.transition_event)
                    )
                return result
            last_error = ManifestPersistenceError(
                "readback_mismatch",
                "fresh manifest readback did not match the write",
                expectedRevision=expected_revision + 1,
                observedRevision=readback.revision if readback else None,
                expectedDigest=candidate_digest,
                observedDigest=readback.digest if readback else None,
            )
        except ManifestPersistenceError as exc:
            last_error = exc
            if exc.code not in {"revision_conflict", "readback_mismatch", "storage_unavailable"}:
                raise
    raise ManifestPersistenceError(
        "durable_storage_exhausted",
        "bounded canonical manifest persistence attempts exhausted",
        attempts=max_attempts,
        lastCode=last_error.code if last_error else "unknown",
        lastDetail=last_error.detail if last_error else "unknown",
    )


def _transition_id(kind: str, identity: Mapping[str, str], authority: Mapping[str, Any]) -> str:
    payload = {"kind": kind, "identity": dict(identity), "authority": authority}
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "recovered-" + hashlib.sha256(data).hexdigest()[:24]


def _identity_matches(expected: Mapping[str, str], observed: Mapping[str, Any]) -> bool:
    return all(observed.get(key) == value for key, value in expected.items())


def _authoritative_transitions(
    identity: Mapping[str, str],
    snapshot: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not _identity_matches(identity, snapshot.get("identity") or {}):
        raise ManifestPersistenceError(
            "authority_identity_mismatch",
            "Cursor/GitHub/Git authority does not bind to the canonical identity",
            expectedIdentity=dict(identity),
            observedIdentity=dict(snapshot.get("identity") or {}),
        )
    cursor = snapshot.get("cursor")
    github = snapshot.get("github")
    git = snapshot.get("git")
    if not all(isinstance(value, Mapping) for value in (cursor, github, git)):
        raise AuthorityFailure("authority_incomplete", "Cursor, GitHub, and Git identities are all required")
    transitions: list[dict[str, Any]] = []
    dispatch_id = cursor.get("dispatchId") or github.get("dispatchId")
    if dispatch_id:
        transitions.append({"kind": "dispatch", "authorityId": str(dispatch_id)})
    run_id = cursor.get("runId") or github.get("workflowRunId")
    if run_id and str(cursor.get("status") or github.get("status") or "").lower() in {
        "queued",
        "running",
        "completed",
        "success",
        "failure",
    }:
        transitions.append({"kind": "run", "authorityId": str(run_id)})
    pr = github.get("pr")
    if (
        isinstance(pr, Mapping)
        and pr.get("merged") is True
        and pr.get("head") == identity.get("commit")
        and git.get("head") == identity.get("commit")
        and git.get("tree") == identity.get("tree")
    ):
        transitions.append({"kind": "integration", "authorityId": str(pr.get("number") or "")})
    archive = github.get("archive")
    if isinstance(archive, Mapping) and archive.get("readback") is True and archive.get("id"):
        transitions.append({"kind": "archive", "authorityId": str(archive["id"])})
    return transitions


def _failure_manifest(current: Mapping[str, Any], *, count: int, code: str) -> dict[str, Any]:
    updated = copy.deepcopy(dict(current))
    updated["authorityFailures"] = count
    updated["lastAuthorityFailure"] = code
    return updated


def _heartbeat_action_id(
    kind: str,
    identity: Mapping[str, str],
    payload: Mapping[str, Any],
) -> str:
    data = json.dumps(
        {"kind": kind, "identity": dict(identity), "payload": dict(payload)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "heartbeat-" + hashlib.sha256(data).hexdigest()[:24]


def _safe_action_from(
    manifest: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    transitions = manifest.get("transitions")
    processed_ids = {
        str(item.get("actionId"))
        for item in transitions
        if isinstance(item, Mapping)
        and item.get("kind") == "dispatch"
        and item.get("actionId")
    } if isinstance(transitions, list) else set()

    def pending(value: Any) -> Mapping[str, Any] | None:
        if not isinstance(value, Mapping) or value.get("safe") is not True:
            return None
        action_id = str(value.get("id") or "")
        state = str(value.get("state") or value.get("status") or "").upper()
        if action_id in processed_ids or state in {"DISPATCHED", "COMMITTED", "COMPLETED"}:
            return None
        return value

    for key in ("safeAction", "requiredAction", "repairAction", "pendingAction"):
        value = pending(manifest.get(key))
        if value is not None:
            return value
    cursor = snapshot.get("cursor")
    if isinstance(cursor, Mapping):
        value = pending(cursor.get("safeAction") or cursor.get("repairAction"))
        if value is not None:
            return value
    value = pending(snapshot.get("safeAction") or snapshot.get("repairAction"))
    if value is not None:
        return value
    return None


def _completed_action(
    requirement: Mapping[str, Any],
    *,
    identity: Mapping[str, str],
) -> dict[str, Any]:
    code = str(requirement["code"])
    action_names = {
        "expired_lease": "LEASE_RENEWAL_REQUIRED",
        "repair_requested_without_run": "REPAIR_REQUESTED",
        "completed_transition_unprocessed": "PROCESS_COMPLETED_TRANSITION",
        "failed_check_repair": "REPAIR_FAILED_CHECK",
        "compatible_ready_work": "ADMIT_READY_WORK",
    }
    name = action_names.get(code, code.upper())
    return {
        "id": _heartbeat_action_id(code, identity, requirement),
        "kind": "ACTION_REQUIRED",
        "code": code,
        "action": name,
        "identity": dict(identity),
        "dispatchable": False,
    }


def _no_action_receipt(
    record: ManifestRead,
    snapshot: Mapping[str, Any],
    *,
    identity: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "kind": "heartbeat_no_action",
        "manifestRevision": record.revision,
        "manifestDigest": record.digest or canonical_manifest_digest(record.manifest),
        "snapshotDigest": canonical_manifest_digest(snapshot),
        "identity": dict(identity),
        "decision": "DONT_NOTIFY",
        "requirements": [],
        "readback": True,
    }


def verify_no_action_receipt(
    receipt: Mapping[str, Any],
    *,
    record: ManifestRead,
    identity: Mapping[str, str],
    snapshot: Mapping[str, Any] | None = None,
) -> bool:
    """Verify the durable identity binding required before DONT_NOTIFY."""

    expected_manifest_digest = record.digest or canonical_manifest_digest(record.manifest)
    if (
        receipt.get("schemaVersion") != 1
        or receipt.get("kind") != "heartbeat_no_action"
        or receipt.get("decision") != "DONT_NOTIFY"
        or receipt.get("readback") is not True
        or receipt.get("requirements") != []
        or receipt.get("manifestRevision") != record.revision
        or receipt.get("manifestDigest") != expected_manifest_digest
        or receipt.get("identity") != dict(identity)
    ):
        return False
    if snapshot is not None and receipt.get("snapshotDigest") != canonical_manifest_digest(snapshot):
        return False
    return True


def _append_heartbeat_transition(
    current: Mapping[str, Any],
    transition: Mapping[str, Any],
) -> dict[str, Any]:
    updated = copy.deepcopy(dict(current))
    transitions = updated.get("transitions")
    if not isinstance(transitions, list):
        raise ManifestPersistenceError(
            "manifest_transitions_invalid",
            "canonical transitions must be an array",
        )
    transition_id = transition.get("id")
    if transition_id and any(
        isinstance(item, Mapping) and item.get("id") == transition_id
        for item in transitions
    ):
        return updated
    transitions.append(copy.deepcopy(dict(transition)))
    updated["transitions"] = transitions
    return updated


def reconcile_manifest_heartbeat(
    store: DurableManifestStore,
    authority: AuthorityPort,
    *,
    max_attempts: int = MAX_PERSISTENCE_ATTEMPTS,
    scheduler: ContinuousUtilizationScheduler | None = None,
    now: datetime | None = None,
    no_progress_wakes: int = 0,
    elapsed_seconds: int = 0,
) -> dict[str, Any]:
    """Reconcile authorities and produce one deterministic heartbeat action.

    This function owns the read/decide/persist portion of the heartbeat turn.
    ``run_heartbeat_controller`` is the packaged entrypoint that consumes a
    dispatchable action before the process exits.
    """

    current_record = _read_record(store)
    if current_record is None:
        raise ManifestPersistenceError("manifest_missing", "canonical manifest is missing")
    current = dict(current_record.manifest)
    identity = current.get("identity")
    if not isinstance(identity, Mapping) or not all(
        isinstance(identity.get(key), str) and identity.get(key)
        for key in ("repository", "commit", "tree")
    ):
        raise ManifestPersistenceError("manifest_identity_missing", "canonical manifest identity is incomplete")

    try:
        snapshot = authority.read_authoritative_state(dict(identity))
        transitions = _authoritative_transitions(dict(identity), snapshot)
    except AuthorityFailure as exc:
        failures = int(current.get("authorityFailures") or 0) + 1
        notify = failures >= max_attempts
        updated = _failure_manifest(current, count=failures, code=exc.code)
        try:
            persist_manifest(updated, store, max_attempts=max_attempts)
        except ManifestPersistenceError:
            pass
        return {
            "status": "blocked" if notify else "retry",
            "notify": notify,
            "reconstructed": [],
            "dispatchPerformed": False,
            "failureCode": exc.code,
            "requiredAction": {
                "kind": "ACTION_REQUIRED",
                "code": exc.code,
                "action": "RETRY_HEARTBEAT_AUTHORITY",
                "dispatchable": False,
            },
        }
    except ManifestPersistenceError:
        raise

    existing = current.get("transitions")
    if not isinstance(existing, list):
        raise ManifestPersistenceError("manifest_transitions_invalid", "canonical transitions must be an array")
    existing_ids = {
        str(item.get("id"))
        for item in existing
        if isinstance(item, Mapping) and item.get("id")
    }
    recovered: list[dict[str, Any]] = []
    for transition in transitions:
        event_id = _transition_id(str(transition["kind"]), dict(identity), transition)
        if event_id in existing_ids:
            continue
        recovered.append({
            "id": event_id,
            "kind": transition["kind"],
            "authorityId": transition["authorityId"],
            "identity": dict(identity),
            "reconstructedOnHeartbeat": True,
        })
        existing_ids.add(event_id)
    updated = copy.deepcopy(current)
    updated["transitions"] = existing + recovered
    updated.pop("authorityFailures", None)
    updated.pop("lastAuthorityFailure", None)
    persisted = persist_manifest(updated, store, max_attempts=max_attempts)
    current_record = _read_record(store)
    if current_record is None:  # pragma: no cover - persist_manifest readback guarantees this
        raise ManifestPersistenceError("readback_missing", "heartbeat manifest readback is missing")
    current = dict(current_record.manifest)
    requirements = heartbeat_progress_requirements(
        current,
        snapshot,
        now=now,
        no_progress_wakes=no_progress_wakes,
        elapsed_seconds=elapsed_seconds,
    )

    gap_required = any(
        item.get("code") in {"two_no_progress_wakes", "heartbeat_timeout"}
        for item in requirements
    )
    existing_gap = any(
        isinstance(item, Mapping)
        and item.get("kind") == UTILIZATION_GAP
        and item.get("recoveryPerformed") is True
        for item in current.get("transitions", [])
    )
    recovery_performed = False
    if gap_required and not existing_gap:
        if scheduler is not None:
            scheduler.recover_utilization_gap_once()
        gap_transition = {
            "id": _heartbeat_action_id(
                UTILIZATION_GAP,
                dict(identity),
                {"reason": "heartbeat_no_progress"},
            ),
            "kind": UTILIZATION_GAP,
            "identity": dict(identity),
            "reason": "heartbeat_no_progress",
            "recovery": "bounded_recompute",
            "recoveryPerformed": True,
        }
        updated = _append_heartbeat_transition(current, gap_transition)
        persisted = persist_manifest(updated, store, max_attempts=max_attempts)
        recovery_performed = True
        requirements = tuple(
            item
            for item in requirements
            if item.get("code") not in {"two_no_progress_wakes", "heartbeat_timeout"}
        )
        if not requirements:
            requirements = (
                {
                    "code": UTILIZATION_GAP,
                    "recoveryPerformed": True,
                },
            )
        current_record = _read_record(store)
        if current_record is None:  # pragma: no cover
            raise ManifestPersistenceError(
                "readback_missing", "heartbeat recovery readback is missing"
            )
    elif existing_gap:
        requirements = tuple(
            item
            for item in requirements
            if item.get("code") not in {"two_no_progress_wakes", "heartbeat_timeout"}
        )

    if requirements:
        requirement = requirements[0]
        action = _safe_action_from(current, snapshot)
        if action is not None and requirement.get("code") in {
            "expired_lease",
            "persisted_undispatched_safe_intent",
            "repair_requested_without_run",
            "failed_check_repair",
            "compatible_ready_work",
        }:
            required_action = {
                "id": _heartbeat_action_id(
                    "dispatch", dict(identity), dict(action)
                ),
                "kind": "DISPATCH_SAFE_ACTION",
                "code": str(requirement["code"]),
                "action": str(action.get("action") or action.get("name") or ""),
                "safeAction": copy.deepcopy(dict(action)),
                "identity": dict(identity),
                "dispatchable": True,
            }
        elif requirement.get("code") == UTILIZATION_GAP:
            required_action = {
                "id": _heartbeat_action_id(
                    UTILIZATION_GAP, dict(identity), dict(requirement)
                ),
                "kind": UTILIZATION_GAP,
                "code": UTILIZATION_GAP,
                "identity": dict(identity),
                "dispatchable": False,
                "recoveryPerformed": recovery_performed
                or bool(requirement.get("recoveryPerformed")),
            }
        else:
            required_action = _completed_action(requirement, identity=dict(identity))
        return {
            "status": "action_required",
            "notify": True,
            "reconstructed": recovered,
            "dispatchPerformed": False,
            "requiredAction": required_action,
            "revision": persisted["revision"],
            "digest": persisted["digest"],
            "recoveryPerformed": recovery_performed,
        }

    receipt = _no_action_receipt(current_record, snapshot, identity=dict(identity))
    if not verify_no_action_receipt(
        receipt,
        record=current_record,
        identity=dict(identity),
        snapshot=snapshot,
    ):
        raise ManifestPersistenceError(
            "no_action_receipt_invalid",
            "heartbeat controller could not verify its no-action receipt",
        )
    return {
        "status": "reconciled",
        "notify": False,
        "reconstructed": recovered,
        "dispatchPerformed": False,
        "revision": persisted["revision"],
        "digest": persisted["digest"],
        "requiredAction": {
            "kind": "DONT_NOTIFY",
            "id": _heartbeat_action_id("DONT_NOTIFY", dict(identity), receipt),
            "dispatchable": False,
            "receipt": receipt,
        },
        "noActionReceipt": receipt,
        "recoveryPerformed": recovery_performed,
    }


def run_heartbeat_controller(
    store: DurableManifestStore,
    authority: AuthorityPort,
    *,
    dispatch_store: DispatchIntentStore | None = None,
    external_dispatch: ExternalDispatchPort | None = None,
    lease=None,
    holder: str | None = None,
    budget: DispatchBudget | None = None,
    scheduler: ContinuousUtilizationScheduler | None = None,
    now: datetime | None = None,
    no_progress_wakes: int = 0,
    elapsed_seconds: int = 0,
    max_attempts: int = MAX_PERSISTENCE_ATTEMPTS,
) -> dict[str, Any]:
    """Run one complete packaged heartbeat turn, including safe dispatch."""

    result = reconcile_manifest_heartbeat(
        store,
        authority,
        max_attempts=max_attempts,
        scheduler=scheduler,
        now=now,
        no_progress_wakes=no_progress_wakes,
        elapsed_seconds=elapsed_seconds,
    )
    action = result.get("requiredAction")
    if not isinstance(action, Mapping):
        return result
    if action.get("kind") == "DONT_NOTIFY":
        record = _read_record(store)
        receipt = action.get("receipt")
        if (
            record is None
            or not isinstance(receipt, Mapping)
            or not verify_no_action_receipt(
                receipt,
                record=record,
                identity=dict(record.manifest.get("identity") or {}),
            )
        ):
            return {
                **result,
                "status": "action_required",
                "notify": True,
                "requiredAction": {
                    "kind": "ACTION_REQUIRED",
                    "code": "no_action_receipt_invalid",
                    "action": "RECONCILE_HEARTBEAT_RECEIPT",
                    "dispatchable": False,
                },
            }
        return result
    if action.get("kind") != "DISPATCH_SAFE_ACTION":
        return result
    if (
        dispatch_store is None
        or external_dispatch is None
        or lease is None
        or not holder
        or budget is None
    ):
        return {
            **result,
            "status": "action_required",
            "actionable": True,
            "dispatchBlocked": "heartbeat_controller_dependencies_missing",
        }

    record = _read_record(store)
    if record is None:  # pragma: no cover
        raise ManifestPersistenceError("manifest_missing", "heartbeat manifest disappeared")
    safe_action = action.get("safeAction")
    if not isinstance(safe_action, Mapping):
        raise ManifestPersistenceError(
            "safe_action_missing", "dispatch action did not contain its persisted intent"
        )
    request = dispatch_request_from_safe_action(record.manifest, safe_action)
    dispatched: DispatchResult = dispatch_transactionally(
        request,
        dispatch_store,
        external_dispatch,
        lease=lease,
        holder=holder,
        now=now or datetime.now(timezone.utc),
        budget=budget,
    )
    dispatch_transition = {
        "id": action["id"],
        "kind": "dispatch",
        "actionId": action["id"],
        "authorityId": dispatched.dispatch_id,
        "identity": dict(record.manifest["identity"]),
        "reconstructedOnHeartbeat": True,
        "dispatchStatus": dispatched.status,
    }
    updated = _append_heartbeat_transition(record.manifest, dispatch_transition)
    if hasattr(lease, "expires_at"):
        updated["orchestrationLease"] = {
            "holder": str(getattr(lease, "holder")),
            "nonce": str(getattr(lease, "nonce")),
            "expiresAt": getattr(lease, "expires_at").astimezone(timezone.utc).isoformat(),
            "repository": str(getattr(lease, "repository")),
        }
    for key in ("safeAction", "requiredAction", "repairAction", "pendingAction"):
        value = updated.get(key)
        if isinstance(value, Mapping) and value.get("safe") is True:
            completed = copy.deepcopy(dict(value))
            completed.update(
                {
                    "status": "COMMITTED",
                    "dispatchId": dispatched.dispatch_id,
                    "idempotencyKey": dispatched.idempotency_key,
                }
            )
            updated[key] = completed
    persisted = persist_manifest(updated, store, max_attempts=max_attempts)
    receipt = {
        "schemaVersion": 1,
        "kind": "heartbeat_dispatch_receipt",
        "actionId": action["id"],
        "idempotencyKey": dispatched.idempotency_key,
        "dispatchId": dispatched.dispatch_id,
        "dispatchStatus": dispatched.status,
        "manifestRevision": persisted["revision"],
        "manifestDigest": persisted["digest"],
        "readback": True,
    }
    return {
        **result,
        "status": "dispatched",
        "notify": True,
        "dispatchPerformed": True,
        "dispatch": {
            "status": dispatched.status,
            "idempotencyKey": dispatched.idempotency_key,
            "dispatchId": dispatched.dispatch_id,
            "revision": dispatched.revision,
        },
        "receipt": receipt,
        "requiredAction": {
            **dict(action),
            "executed": True,
            "receipt": receipt,
        },
        "revision": persisted["revision"],
        "digest": persisted["digest"],
    }
