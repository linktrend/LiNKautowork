"""PKT-08 revision-60 transactional dispatch and design authority controls."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from jsonschema import Draft202012Validator

from core.execution.protocol import LeaseState, validate_lease


CONTROL_IDEMPOTENCY_KEY = (
    "pkt08-b44060-transactional-dispatch-and-approved-design-authority-v1"
)
CONFIG_RELATIVE_PATH = (
    "core/managed-core/content/config/transactional-dispatch.json"
)
SCHEMA_RELATIVE_PATH = (
    "core/managed-core/schemas/transactional-dispatch.schema.json"
)
MAX_COMMIT_ATTEMPTS = 3
FORBIDDEN_HEARTBEAT_ACTIONS = frozenset({"fast", "paid", "premium"})


class TransactionalDispatchError(RuntimeError):
    """Fail-closed transactional dispatch error."""

    def __init__(self, code: str, detail: str, **diagnostics: Any) -> None:
        self.code = code
        self.detail = detail
        self.diagnostics = diagnostics
        super().__init__(f"{code}: {detail}")


class DispatchInterrupted(TransactionalDispatchError):
    """The caller lost an external response after the server accepted it."""

    def __init__(self, status_code: int, idempotency_key: str) -> None:
        super().__init__(
            "external_response_interrupted",
            "external dispatch response was interrupted",
            statusCode=status_code,
            idempotencyKey=idempotency_key,
        )
        self.status_code = status_code
        self.idempotency_key = idempotency_key


@dataclass(frozen=True)
class DispatchRequest:
    packet_id: str
    repository: str
    commit: str
    tree: str
    action: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class DispatchBudget:
    remaining_seconds: int
    required_seconds: int

    def require(self) -> None:
        if self.remaining_seconds < self.required_seconds:
            raise TransactionalDispatchError(
                "deadline_budget_insufficient",
                "remaining deadline budget cannot cover the transactional turn",
                remainingSeconds=self.remaining_seconds,
                requiredSeconds=self.required_seconds,
            )


@dataclass(frozen=True)
class DispatchResult:
    status: str
    idempotency_key: str
    dispatch_id: str
    revision: int


@dataclass(frozen=True)
class DesignApprovalDecision:
    approved: bool
    suppress_executor_approval: bool
    executor_approval_required: bool
    reason: str


@dataclass(frozen=True)
class DesignResumeResult:
    resumed: bool
    resume_id: str
    reason: str


class ExternalDispatchPort(Protocol):
    def dispatch(
        self, request: DispatchRequest, idempotency_key: str
    ) -> Mapping[str, Any]:
        ...

    def read_by_idempotency_key(
        self, idempotency_key: str
    ) -> Mapping[str, Any] | None:
        ...


class DispatchIntentStore(Protocol):
    def read_by_key(self, idempotency_key: str) -> Mapping[str, Any] | None:
        ...

    def compare_and_write(
        self,
        idempotency_key: str,
        expected_revision: int,
        expected_digest: str | None,
        payload: Mapping[str, Any],
    ) -> None:
        ...


class DesignResumeStore(Protocol):
    def read(self, resume_id: str) -> Mapping[str, Any] | None:
        ...

    def write_once(self, resume_id: str, payload: Mapping[str, Any]) -> bool:
        ...


class DurableDispatchIntentStore:
    """Small durable-store-shaped implementation used by local runtimes/tests."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self.read_count = 0
        self.write_count = 0
        self.cas_attempt_count = 0
        self.collide_next_commit = False

    def read_by_key(self, idempotency_key: str) -> dict[str, Any] | None:
        self.read_count += 1
        record = self._records.get(idempotency_key)
        return copy.deepcopy(record) if record is not None else None

    def compare_and_write(
        self,
        idempotency_key: str,
        expected_revision: int,
        expected_digest: str | None,
        payload: Mapping[str, Any],
    ) -> None:
        self.cas_attempt_count += 1
        current = self._records.get(idempotency_key)
        current_revision = int(current["revision"]) if current else 0
        current_digest = str(current["digest"]) if current else None
        if (
            current_revision != expected_revision
            or current_digest != expected_digest
        ):
            raise TransactionalDispatchError(
                "cas_collision", "dispatch intent revision changed"
            )
        if self.collide_next_commit and payload.get("state") == "COMMITTED":
            self.collide_next_commit = False
            competing = copy.deepcopy(dict(current or {}))
            competing["revision"] = expected_revision + 1
            competing["digest"] = _payload_digest(competing)
            self._records[idempotency_key] = competing
            raise TransactionalDispatchError(
                "cas_collision", "simulated competing commit"
            )
        next_record = {
            "revision": expected_revision + 1,
            "digest": _payload_digest(payload),
            **copy.deepcopy(dict(payload)),
        }
        self._records[idempotency_key] = next_record
        self.write_count += 1


class DurableDesignResumeStore:
    """One-shot durable marker store for automatic design resumes."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self.write_count = 0

    def read(self, resume_id: str) -> dict[str, Any] | None:
        record = self._records.get(resume_id)
        return copy.deepcopy(record) if record is not None else None

    def write_once(self, resume_id: str, payload: Mapping[str, Any]) -> bool:
        if resume_id in self._records:
            return False
        self._records[resume_id] = copy.deepcopy(dict(payload))
        self.write_count += 1
        return True


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _payload_digest(payload: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _dispatch_id_from_authority(
    response: Mapping[str, Any], idempotency_key: str
) -> str:
    response_key = response.get("idempotencyKey")
    if response_key is not None and response_key != idempotency_key:
        raise TransactionalDispatchError(
            "external_authority_identity_mismatch",
            "external authority response is bound to another idempotency key",
        )
    dispatch_id = str(response.get("dispatchId") or "")
    if not dispatch_id:
        raise TransactionalDispatchError(
            "external_authority_invalid",
            "authoritative idempotency lookup has no dispatch id",
        )
    return dispatch_id


def deterministic_dispatch_key(request: DispatchRequest) -> str:
    identity = {
        "packetId": request.packet_id,
        "repository": request.repository,
        "commit": request.commit,
        "tree": request.tree,
        "action": request.action,
        "payload": request.payload,
    }
    digest = hashlib.sha256(_canonical_bytes(identity)).hexdigest()
    return f"{CONTROL_IDEMPOTENCY_KEY}:{digest}"


def dispatch_request_from_safe_action(
    manifest: Mapping[str, Any],
    action: Mapping[str, Any],
) -> DispatchRequest:
    """Build an exact, non-paid dispatch request from persisted manifest data."""

    identity = manifest.get("identity")
    if not isinstance(identity, Mapping):
        raise TransactionalDispatchError(
            "action_identity_missing", "safe action identity is incomplete"
        )
    repository = str(identity.get("repository") or "")
    commit = str(identity.get("commit") or "")
    tree = str(identity.get("tree") or "")
    packet_id = str(manifest.get("packetId") or manifest.get("id") or "")
    action_name = str(action.get("action") or action.get("name") or "").strip()
    if not action.get("safe") is True:
        raise TransactionalDispatchError(
            "unsafe_action", "heartbeat may dispatch only a safe persisted action"
        )
    if not packet_id or not repository or not commit or not tree or not action_name:
        raise TransactionalDispatchError(
            "action_identity_missing", "safe action identity is incomplete"
        )
    if action_name.lower() in FORBIDDEN_HEARTBEAT_ACTIONS:
        raise TransactionalDispatchError(
            "paid_fallback_forbidden",
            "heartbeat recovery cannot dispatch paid or Fast work",
        )
    payload = action.get("payload")
    if not isinstance(payload, Mapping):
        payload = {"action": action_name}
    return DispatchRequest(
        packet_id=packet_id,
        repository=repository,
        commit=commit,
        tree=tree,
        action=action_name,
        payload=dict(payload),
    )


def _readback_write(
    store: DispatchIntentStore,
    *,
    key: str,
    expected_revision: int,
    expected_digest: str | None,
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    store.compare_and_write(key, expected_revision, expected_digest, payload)
    readback = store.read_by_key(key)
    if readback is None or readback.get("digest") != _payload_digest(payload):
        raise TransactionalDispatchError(
            "cas_readback_mismatch",
            "dispatch intent commit was not read back identically",
        )
    for field, value in payload.items():
        if readback.get(field) != value:
            raise TransactionalDispatchError(
                "cas_readback_mismatch",
                "dispatch intent readback payload differs",
                field=field,
            )
    return readback


def _commit(
    store: DispatchIntentStore,
    *,
    key: str,
    dispatch_id: str,
    status: str,
    attempts: int,
) -> Mapping[str, Any]:
    for _ in range(attempts):
        current = store.read_by_key(key)
        if current is None:
            raise TransactionalDispatchError(
                "write_ahead_intent_missing",
                "cannot commit an intent that was not written ahead",
            )
        if current.get("state") == "COMMITTED":
            return current
        payload = dict(current)
        payload.pop("revision", None)
        payload.pop("digest", None)
        payload.update({
            "state": "COMMITTED",
            "dispatchId": dispatch_id,
            "status": status,
            "requestDigest": current.get("requestDigest"),
        })
        try:
            return _readback_write(
                store,
                key=key,
                expected_revision=int(current["revision"]),
                expected_digest=str(current["digest"]),
                payload=payload,
            )
        except TransactionalDispatchError as exc:
            if exc.code != "cas_collision":
                raise
    raise TransactionalDispatchError(
        "cas_attempts_exhausted",
        "bounded dispatch-intent CAS commit attempts exhausted",
    )


def dispatch_transactionally(
    request: DispatchRequest,
    store: DispatchIntentStore,
    external: ExternalDispatchPort,
    *,
    lease: LeaseState,
    holder: str,
    now,
    budget: DispatchBudget,
) -> DispatchResult:
    """Dispatch once with write-ahead intent, recovery, CAS commit, and readback."""

    if not validate_lease(
        lease,
        holder=holder,
        packet_id=request.packet_id,
        repository=request.repository,
        now=now,
    ):
        raise TransactionalDispatchError(
            "stale_or_invalid_lease",
            "a live packet-repository lease is required",
        )
    budget.require()
    key = deterministic_dispatch_key(request)
    request_digest = _payload_digest(
        {
            "packetId": request.packet_id,
            "repository": request.repository,
            "commit": request.commit,
            "tree": request.tree,
            "action": request.action,
            "payload": request.payload,
        }
    )

    current = store.read_by_key(key)
    if current is not None and current.get("state") == "COMMITTED":
        return DispatchResult(
            "duplicate",
            key,
            str(current["dispatchId"]),
            int(current["revision"]),
        )
    if current is None:
        intent = {
            "idempotencyKey": key,
            "state": "PREPARED",
            "requestDigest": request_digest,
            "packetId": request.packet_id,
            "repository": request.repository,
            "commit": request.commit,
            "tree": request.tree,
        }
        for _ in range(MAX_COMMIT_ATTEMPTS):
            try:
                current = _readback_write(
                    store,
                    key=key,
                    expected_revision=0,
                    expected_digest=None,
                    payload=intent,
                )
                break
            except TransactionalDispatchError as exc:
                if exc.code != "cas_collision":
                    raise
                current = store.read_by_key(key)
                if current is not None:
                    break
        if current is None:
            raise TransactionalDispatchError(
                "cas_attempts_exhausted",
                "write-ahead intent CAS attempts exhausted",
            )

    if current.get("requestDigest") != request_digest:
        raise TransactionalDispatchError(
            "idempotency_key_collision",
            "existing intent does not describe the canonical request",
        )

    budget.require()
    observed = external.read_by_idempotency_key(key)
    if observed is not None:
        dispatch_id = _dispatch_id_from_authority(observed, key)
        committed = _commit(
            store,
            key=key,
            dispatch_id=dispatch_id,
            status="recovered",
            attempts=MAX_COMMIT_ATTEMPTS,
        )
        return DispatchResult(
            "recovered",
            key,
            dispatch_id,
            int(committed["revision"]),
        )

    budget.require()
    try:
        response = external.dispatch(request, key)
    except DispatchInterrupted as exc:
        if exc.status_code != 201:
            raise
        budget.require()
        observed = external.read_by_idempotency_key(key)
        if observed is None:
            raise TransactionalDispatchError(
                "api_201_recovery_missing",
                "accepted dispatch was not found by its idempotency key",
            ) from exc
        _dispatch_id_from_authority(observed, key)
        response = {"statusCode": 201, **dict(observed)}
        result_status = "recovered"
    else:
        if int(response.get("statusCode", 0)) != 201:
            raise TransactionalDispatchError(
                "external_dispatch_rejected",
                "external dispatch did not return HTTP 201",
                statusCode=response.get("statusCode"),
            )
        response_key = response.get("idempotencyKey")
        if response_key is not None and response_key != key:
            raise TransactionalDispatchError(
                "external_response_identity_mismatch",
                "external response is bound to another idempotency key",
            )
        result_status = "committed"

    dispatch_id = str(response.get("dispatchId") or "")
    if not dispatch_id:
        raise TransactionalDispatchError(
            "external_response_invalid", "HTTP 201 response has no dispatch id"
        )
    budget.require()
    committed = _commit(
        store,
        key=key,
        dispatch_id=dispatch_id,
        status=result_status,
        attempts=MAX_COMMIT_ATTEMPTS,
    )
    return DispatchResult(
        result_status,
        key,
        dispatch_id,
        int(committed["revision"]),
    )


def load_transactional_dispatch_config(
    repo_root: Path | str,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    config = json.loads((root / CONFIG_RELATIVE_PATH).read_text(encoding="utf-8"))
    schema = json.loads((root / SCHEMA_RELATIVE_PATH).read_text(encoding="utf-8"))
    errors = sorted(
        error.message for error in Draft202012Validator(schema).iter_errors(config)
    )
    if errors:
        raise TransactionalDispatchError(
            "config_invalid", "; ".join(errors)
        )
    if config["controlIdempotencyKey"] != CONTROL_IDEMPOTENCY_KEY:
        raise TransactionalDispatchError(
            "config_invalid", "revision-60 control key does not match runtime"
        )
    return config


def design_approval_decision(
    manifest: Mapping[str, Any],
    *,
    conversation: Mapping[str, Any] | None = None,
) -> DesignApprovalDecision:
    del conversation
    authority = manifest.get("designAuthority")
    if (
        isinstance(authority, Mapping)
        and authority.get("status") == "APPROVED"
        and isinstance(authority.get("manifestDigest"), str)
        and authority["manifestDigest"].startswith("sha256:")
    ):
        return DesignApprovalDecision(True, True, False, "approved_manifest_authority")
    return DesignApprovalDecision(
        False, False, True, "approved_manifest_required"
    )


def deterministic_resume_id(
    manifest: Mapping[str, Any], result: Mapping[str, Any]
) -> str:
    payload = {
        "manifestDigest": manifest["designAuthority"]["manifestDigest"],
        "resultId": result["resultId"],
    }
    return "design-resume-" + hashlib.sha256(_canonical_bytes(payload)).hexdigest()[:32]


def resume_unsolicited_design_result(
    manifest: Mapping[str, Any],
    result: Mapping[str, Any],
    store: DesignResumeStore,
) -> DesignResumeResult:
    decision = design_approval_decision(manifest)
    result_id = result.get("resultId")
    resume_id = (
        deterministic_resume_id(manifest, result)
        if isinstance(result_id, str) and result_id
        and isinstance(manifest.get("designAuthority"), Mapping)
        and isinstance(manifest["designAuthority"].get("manifestDigest"), str)
        else "invalid"
    )
    if not decision.approved:
        return DesignResumeResult(False, resume_id, decision.reason)
    if (
        not isinstance(result_id, str)
        or not result_id
        or result.get("kind") != "design-only"
        or result.get("terminal") is not True
        or result.get("solicited") is not False
    ):
        return DesignResumeResult(False, resume_id, "not_unsolicited_design_terminal")
    if store.read(resume_id) is not None:
        return DesignResumeResult(False, resume_id, "duplicate_resume_suppressed")
    if not store.write_once(
        resume_id,
        {"resumeId": resume_id, "resultId": result_id, "state": "RESUMED"},
    ):
        return DesignResumeResult(False, resume_id, "duplicate_resume_suppressed")
    return DesignResumeResult(True, resume_id, "automatic_resume")
