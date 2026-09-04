"""Fail-closed Cursor Cloud SDK/API dispatch contract.

Cursor Cloud routing is repository-bound. The direct REST shape uses ``repos``
and the SDK adapter uses the equivalent ``CloudAgentOptions.repos`` value. A
named saved environment is deliberately not part of this contract.

Gate 0 Luna High work is owned by the Codex CLI route; ordinary post-Gate-0
Cursor work is the only model policy admitted by this direct dispatcher.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlsplit, urlunsplit


CONTROL_ID = "cursor-cloud-dispatch-v2"
API_BASE_URL = "https://api.cursor.com"
API_PATH = "/v1/agents"
MAX_API_ATTEMPTS = 2

# Import-compatible empty aliases for older adapters. They are not selectors
# and are never sent to Cursor.
ENV_NAME = ""
ENV_PUBLIC_ID = ""
SAVED_REPOSITORY_ROOT = ""

DIRECT_PROVIDER = "cursor"
ORDINARY_ROUTE = "ordinary-development"
DIRECT_MODEL = "grok-4.6"
DIRECT_EFFORT = "medium"
DIRECT_FAST = "false"
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class CursorCloudDispatchError(RuntimeError):
    """A Cursor Cloud request was rejected before or after external I/O."""

    def __init__(self, code: str, detail: str, **diagnostics: Any) -> None:
        self.code = code
        self.detail = detail
        self.diagnostics = diagnostics
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class CursorCloudDispatchRequest:
    repository: str
    target_remote: str
    ref: str
    commit: str
    tree: str
    model: str
    expected_build_id: str
    toolchain: Mapping[str, str]
    setup_receipt_digest: str
    provider: str = DIRECT_PROVIDER
    route_id: str = ORDINARY_ROUTE
    model_parameters: Mapping[str, str] = field(default_factory=dict)
    explicit_scope_repositories: tuple[str, ...] = ()
    explicit_scope_remotes: Mapping[str, str] = field(default_factory=dict)
    governed_setup: bool = False
    principal_authorized: bool = False

    def validate(self) -> None:
        if not self.repository.strip() or not self.ref.strip():
            raise CursorCloudDispatchError(
                "cursor_cloud_identity_missing", "repository and ref are required"
            )
        parts = self.repository.split("/")
        if len(parts) != 2 or any(part in {"", ".", ".."} or "\\" in part for part in parts):
            raise CursorCloudDispatchError(
                "cursor_cloud_repository_invalid",
                "repository must be an owner/name identity without traversal",
            )
        normalized_remote = normalize_repository_remote(self.target_remote)
        if normalized_remote != f"https://github.com/{self.repository}":
            raise CursorCloudDispatchError(
                "cursor_cloud_repository_remote_mismatch",
                "repository URL does not match the requested repository identity",
            )
        if not _GIT_SHA.fullmatch(self.commit) or not _GIT_SHA.fullmatch(self.tree):
            raise CursorCloudDispatchError(
                "cursor_cloud_identity_invalid",
                "commit and tree must be exact 40-character hexadecimal git identities",
            )
        if not self.governed_setup:
            raise CursorCloudDispatchError(
                "cursor_cloud_governed_setup_required",
                "target checkout setup must be explicitly governed before dispatch",
            )
        if not _SHA256.fullmatch(self.setup_receipt_digest):
            raise CursorCloudDispatchError(
                "cursor_cloud_setup_receipt_invalid",
                "an exact governed setup receipt digest is required",
            )
        if not self.expected_build_id.strip():
            raise CursorCloudDispatchError(
                "cursor_cloud_build_provenance_missing",
                "expected build ID is required as provenance",
            )
        if self.provider != DIRECT_PROVIDER:
            raise CursorCloudDispatchError(
                "cursor_cloud_provider_unsupported",
                "direct Cursor dispatch only admits provider=cursor; Luna uses Codex CLI",
            )
        if self.route_id != ORDINARY_ROUTE:
            raise CursorCloudDispatchError(
                "cursor_cloud_route_unsupported",
                "direct Cursor dispatch only admits the ordinary-development route",
            )
        if self.model != DIRECT_MODEL:
            raise CursorCloudDispatchError(
                "cursor_cloud_model_unsupported",
                "ordinary Cursor development requires the exact grok-4.6 model",
            )
        parameters = {str(key): str(value) for key, value in self.model_parameters.items()}
        if parameters != {"effort": DIRECT_EFFORT, "fast": DIRECT_FAST}:
            raise CursorCloudDispatchError(
                "cursor_cloud_model_parameters_unsupported",
                "ordinary Cursor development requires effort=medium and fast=false",
            )
        if not self.toolchain or any(
            not str(key).strip() or not str(value).strip()
            for key, value in self.toolchain.items()
        ):
            raise CursorCloudDispatchError(
                "cursor_cloud_toolchain_missing", "toolchain attestation data is required"
            )
        validate_repository_scope(self)

    @property
    def normalized_remote(self) -> str:
        return normalize_repository_remote(self.target_remote)

    @property
    def repository_bindings(self) -> list[dict[str, str]]:
        bindings = [{"url": self.normalized_remote, "startingRef": self.ref}]
        seen = {(self.normalized_remote, self.ref)}
        for repository in self.explicit_scope_repositories:
            remote = normalize_repository_remote(self.explicit_scope_remotes[repository])
            item = (remote, self.ref)
            if item not in seen:
                bindings.append({"url": remote, "startingRef": self.ref})
                seen.add(item)
        return bindings


def normalize_repository_remote(remote: str) -> str:
    """Normalize a repository URL without accepting credentials or ambiguity."""

    value = str(remote or "").strip()
    parsed = urlsplit(value)
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise CursorCloudDispatchError(
            "cursor_cloud_remote_invalid",
            "remote must be an HTTP(S) URL without credentials",
        )
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not path or "//" in path or ".." in path.split("/"):
        raise CursorCloudDispatchError(
            "cursor_cloud_remote_invalid", "remote path is not canonical"
        )
    return urlunsplit((parsed.scheme.casefold(), parsed.hostname.casefold(), path, "", ""))


def canonical_saved_repository_path(repository: str, target_path: str) -> str:
    """Reject the retired saved-environment path API."""

    del repository, target_path
    raise CursorCloudDispatchError(
        "cursor_cloud_saved_environment_forbidden",
        "saved environment paths are unsupported; use an explicit repos binding",
    )


def validate_repository_scope(request: CursorCloudDispatchRequest) -> None:
    """Allow one repository by default and extras only when explicitly listed."""

    extras = tuple(request.explicit_scope_repositories)
    if not extras and request.explicit_scope_remotes:
        raise CursorCloudDispatchError(
            "cursor_cloud_explicit_scope_remote_without_repositories",
            "explicit scope remotes require coordinated repository identities",
        )
    seen = {request.repository}
    for repository in extras:
        parts = repository.split("/")
        if (
            len(parts) != 2
            or any(part in {"", ".", ".."} or "\\" in part for part in parts)
            or repository in seen
        ):
            raise CursorCloudDispatchError(
                "cursor_cloud_explicit_scope_repository_invalid",
                "explicit-scope repository identity is invalid or duplicated",
            )
        seen.add(repository)
        remote = request.explicit_scope_remotes.get(repository)
        if not remote:
            raise CursorCloudDispatchError(
                "cursor_cloud_explicit_scope_remote_missing",
                "each explicit-scope repository requires a governed remote",
                repository=repository,
            )
        if normalize_repository_remote(remote) != f"https://github.com/{repository}":
            raise CursorCloudDispatchError(
                "cursor_cloud_explicit_scope_remote_mismatch",
                "explicit-scope remote does not match its repository identity",
                repository=repository,
            )


@dataclass(frozen=True)
class CursorCloudDispatchResult:
    status: str
    idempotency_key: str
    client_agent_id: str
    agent_id: str
    run_id: str
    repository: str
    ref: str
    commit: str
    tree: str
    provider: str
    model: str
    effort: str
    fast: bool
    revision: int
    attestation_prompt: str


class CursorCloudIntentStore(Protocol):
    def read(self, idempotency_key: str) -> Mapping[str, Any] | None: ...

    def compare_and_write(
        self,
        idempotency_key: str,
        expected_revision: int,
        expected_digest: str | None,
        payload: Mapping[str, Any],
    ) -> None: ...

    def list_intents(self) -> list[Mapping[str, Any]]: ...


class CursorCloudHTTPPort(Protocol):
    def post(
        self, path: str, *, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def get(self, path: str, *, headers: Mapping[str, str]) -> Mapping[str, Any]: ...


class CursorCloudSDKPort(Protocol):
    def create_agent(
        self,
        *,
        api_key: str,
        model: str,
        model_parameters: Mapping[str, str],
        repository_bindings: Sequence[Mapping[str, str]],
        prompt: str,
        name: str,
        agent_id: str,
        idempotency_key: str,
    ) -> Mapping[str, Any]: ...

    def get_agent(self, agent_id: str) -> Mapping[str, Any]: ...

    def archive_agent(self, agent_id: str) -> Mapping[str, Any]: ...


class CursorPythonSDKPort:
    """Lazy official SDK adapter with create/readback/archive semantics."""

    def __init__(self) -> None:
        self._agents: dict[str, Any] = {}

    def create_agent(self, **kwargs: Any) -> Mapping[str, Any]:
        try:
            from cursor_sdk import (
                Agent,
                CloudAgentOptions,
                CloudRepository,
                ModelParameterValue,
                ModelSelection,
            )
        except ImportError as exc:  # pragma: no cover - host dependency
            raise CursorCloudDispatchError(
                "cursor_cloud_sdk_unavailable", "cursor-sdk is not installed"
            ) from exc
        agent = Agent.create(
            model=ModelSelection(
                id=kwargs["model"],
                params=[
                    ModelParameterValue(id=key, value=value)
                    for key, value in sorted(kwargs["model_parameters"].items())
                ],
            ),
            api_key=kwargs["api_key"],
            name=kwargs["name"],
            agent_id=kwargs["agent_id"],
            idempotency_key=kwargs["idempotency_key"],
            cloud=CloudAgentOptions(
                repos=[
                    CloudRepository(url=item["url"], starting_ref=item["startingRef"])
                    for item in kwargs["repository_bindings"]
                ],
                auto_create_pr=False,
            ),
        )
        agent_id = str(getattr(agent, "agent_id", "") or kwargs["agent_id"])
        self._agents[agent_id] = agent
        run = agent.send(kwargs["prompt"])
        run_id = str(getattr(run, "run_id", None) or getattr(run, "id", "") or "")
        if not run_id:
            raise CursorCloudDispatchError(
                "cursor_cloud_sdk_identity_missing", "SDK create/send did not return a run identity"
            )
        return {"statusCode": 201, "agentId": agent_id, "runId": run_id}

    def get_agent(self, agent_id: str) -> Mapping[str, Any]:
        agent = self._agents.get(agent_id)
        status = getattr(agent, "status", None) or getattr(agent, "get_status", None)
        if agent is None or not callable(status):
            raise CursorCloudDispatchError(
                "cursor_cloud_sdk_readback_unavailable", "SDK adapter must expose status readback"
            )
        result = status()
        if not isinstance(result, Mapping):
            raise CursorCloudDispatchError(
                "cursor_cloud_sdk_readback_invalid", "SDK status readback must be an object"
            )
        return result

    def archive_agent(self, agent_id: str) -> Mapping[str, Any]:
        agent = self._agents.get(agent_id)
        archive = getattr(agent, "archive", None)
        if agent is None or not callable(archive):
            raise CursorCloudDispatchError(
                "cursor_cloud_sdk_archive_unavailable", "SDK adapter must expose archive"
            )
        result = archive()
        return dict(result) if isinstance(result, Mapping) else {"status": "archived"}


class _SDKAsHTTPPort:
    def __init__(self, request: CursorCloudDispatchRequest, sdk: CursorCloudSDKPort) -> None:
        self.request = request
        self.sdk = sdk

    def post(self, path: str, *, headers: Mapping[str, str], body: Mapping[str, Any]) -> Mapping[str, Any]:
        if path != API_PATH:
            raise CursorCloudDispatchError("cursor_cloud_sdk_path_invalid", "unexpected SDK create path")
        return dict(
            self.sdk.create_agent(
                api_key=str(headers["Authorization"]).removeprefix("Bearer "),
                model=self.request.model,
                model_parameters={key: str(value) for key, value in self.request.model_parameters.items()},
                repository_bindings=self.request.repository_bindings,
                prompt=str(body["prompt"]),
                name=f"{self.request.repository}:{self.request.ref}",
                agent_id=str(body["agentId"]),
                idempotency_key=str(headers["Idempotency-Key"]),
            )
        )

    def get(self, path: str, *, headers: Mapping[str, str]) -> Mapping[str, Any]:
        del headers
        prefix = API_PATH + "/"
        if not path.startswith(prefix):
            raise CursorCloudDispatchError("cursor_cloud_sdk_path_invalid", "unexpected SDK status path")
        return self.sdk.get_agent(path[len(prefix):])

    def archive(self, agent_id: str, *, headers: Mapping[str, str]) -> Mapping[str, Any]:
        del headers
        return self.sdk.archive_agent(agent_id)


class DurableCursorCloudIntentStore:
    """Minimal durable-store-shaped implementation for local runtimes/tests."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self.read_count = 0
        self.write_count = 0

    def read(self, idempotency_key: str) -> dict[str, Any] | None:
        self.read_count += 1
        value = self._records.get(idempotency_key)
        return copy.deepcopy(value) if value is not None else None

    def list_intents(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(value) for value in self._records.values()]

    def compare_and_write(
        self,
        idempotency_key: str,
        expected_revision: int,
        expected_digest: str | None,
        payload: Mapping[str, Any],
    ) -> None:
        current = self._records.get(idempotency_key)
        current_revision = int(current["revision"]) if current else 0
        current_digest = str(current["digest"]) if current else None
        if (current_revision, current_digest) != (expected_revision, expected_digest):
            raise CursorCloudDispatchError(
                "cursor_cloud_intent_cas_collision", "dispatch intent changed concurrently"
            )
        stored = {"revision": expected_revision + 1, **copy.deepcopy(dict(payload))}
        stored["digest"] = _stored_digest(stored)
        self._records[idempotency_key] = stored
        self.write_count += 1


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _stored_digest(value: Mapping[str, Any]) -> str:
    return _digest({key: item for key, item in value.items() if key != "digest"})


def cursor_cloud_idempotency_key(request: CursorCloudDispatchRequest) -> str:
    request.validate()
    identity = {
        "control": CONTROL_ID,
        "repository": request.repository,
        "targetRemote": request.normalized_remote,
        "ref": request.ref,
        "commit": request.commit,
        "tree": request.tree,
        "provider": request.provider,
        "routeId": request.route_id,
        "model": request.model,
        "modelParameters": dict(request.model_parameters),
        "explicitScopeRepositories": list(request.explicit_scope_repositories),
        "explicitScopeRemotes": dict(sorted(request.explicit_scope_remotes.items())),
        "expectedBuildId": request.expected_build_id,
        "toolchain": dict(request.toolchain),
        "setupReceiptDigest": request.setup_receipt_digest,
    }
    return CONTROL_ID + ":" + hashlib.sha256(_canonical(identity)).hexdigest()


def cursor_cloud_client_agent_id(request: CursorCloudDispatchRequest) -> str:
    return "ide-" + hashlib.sha256(cursor_cloud_idempotency_key(request).encode()).hexdigest()[:32]


def build_attestation_prompt(request: CursorCloudDispatchRequest) -> str:
    request.validate()
    matrix = (
        f"repository={request.repository}; remote={request.normalized_remote}; ref={request.ref}; "
        f"commit={request.commit}; tree={request.tree}"
    )
    toolchain = ", ".join(f"{key}={value}" for key, value in sorted(request.toolchain.items()))
    return (
        "ATTESTATION ONLY. Do not mutate, commit, push, migrate, or invoke side effects. "
        "Use the explicit repository binding in repos[] and verify the requested starting ref. "
        f"Report PASS/FAIL for repository identity matrix ({matrix}), exact HEAD commit/tree, "
        f"toolchain ({toolchain}), and workspace cleanliness. Expected build ID "
        f"{request.expected_build_id} and setup receipt {request.setup_receipt_digest} are provenance only. "
        "Any repository, ref, commit, tree, model, effort, or Fast mismatch is a hard stop."
    )


def require_cursor_cloud_api_key(
    environment: Mapping[str, str] | None = None, *, cursor_cli_authenticated: bool = False
) -> str:
    """Resolve the API key without exposing its value in diagnostics."""

    env = os.environ if environment is None else environment
    value = str(env.get("CURSOR_API_KEY") or "")
    if not value.strip():
        detail = "CURSOR_API_KEY is required for Cursor Cloud API authority"
        if cursor_cli_authenticated:
            detail += "; cursor-agent CLI login/local workspace is not Cloud API authority"
        raise CursorCloudDispatchError("cursor_cloud_api_key_required", detail)
    if any(char.isspace() for char in value):
        raise CursorCloudDispatchError("cursor_cloud_api_key_invalid", "CURSOR_API_KEY is malformed")
    return value


def _readback_write(
    store: CursorCloudIntentStore,
    key: str,
    payload: Mapping[str, Any],
    *,
    expected_revision: int,
    expected_digest: str | None,
) -> Mapping[str, Any]:
    store.compare_and_write(key, expected_revision, expected_digest, payload)
    readback = store.read(key)
    if readback is None or readback.get("digest") != _stored_digest(readback):
        raise CursorCloudDispatchError(
            "cursor_cloud_intent_readback_failed", "dispatch intent was not read back"
        )
    for field, value in payload.items():
        if readback.get(field) != value:
            raise CursorCloudDispatchError(
                "cursor_cloud_intent_readback_failed", "intent readback differs", field=field
            )
    return readback


def supersede_obsolete_prepared_intents(
    store: CursorCloudIntentStore,
    *,
    current_idempotency_key: str | None = None,
    repository: str | None = None,
    ownership_evidence: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[str]:
    """Supersede only fixed-capacity records proven stale by an owner authority.

    A capacity marker identifies a record that may need migration; it does not
    prove that the record is safe to supersede.  The caller must supply an
    authoritative ownership decision bound to the exact record revision and
    digest.  With no such evidence, this function is deliberately a no-op.
    """

    if ownership_evidence is None:
        return []
    if not isinstance(ownership_evidence, Mapping):
        raise CursorCloudDispatchError(
            "cursor_cloud_intent_supersession_ambiguous",
            "authoritative ownership evidence must be a keyed mapping",
        )

    list_intents = getattr(store, "list_intents", None)
    if not callable(list_intents):
        raise CursorCloudDispatchError(
            "cursor_cloud_intent_supersession_unavailable",
            "intent store cannot enumerate PREPARED records",
        )
    records: dict[str, Mapping[str, Any]] = {}
    for record in list_intents():
        if not isinstance(record, Mapping) or record.get("state") != "PREPARED":
            continue
        key = str(record.get("idempotencyKey") or "")
        if not key or key in records:
            raise CursorCloudDispatchError(
                "cursor_cloud_intent_supersession_ambiguous",
                "PREPARED intent enumeration contains an invalid or duplicate idempotency key",
            )
        records[key] = dict(record)

    evidence_keys = {str(key) for key in ownership_evidence}
    if current_idempotency_key:
        evidence_keys.discard(current_idempotency_key)
    for key in evidence_keys:
        if key not in records:
            raise CursorCloudDispatchError(
                "cursor_cloud_intent_supersession_unrelated",
                "ownership evidence does not bind an enumerated PREPARED intent",
                idempotencyKey=key,
            )

    superseded: list[str] = []
    for key, snapshot in records.items():
        if key == current_idempotency_key:
            continue
        if snapshot.get("concurrencyPolicy") not in {
            "fixed_hosted_2", "fixed_hosted_worker_cap", "max_hosted_2"
        } and snapshot.get("maxHostedWorkers") != 2:
            continue

        evidence = ownership_evidence.get(key)
        if not isinstance(evidence, Mapping):
            raise CursorCloudDispatchError(
                "cursor_cloud_intent_supersession_ambiguous",
                "fixed-capacity PREPARED intent lacks authoritative ownership evidence",
                idempotencyKey=key,
            )

        status = str(evidence.get("status") or "").casefold()
        if evidence.get("authoritative") is not True or status not in {"stale", "expired"}:
            raise CursorCloudDispatchError(
                "cursor_cloud_intent_supersession_ownership_not_stale",
                "only authoritative stale or expired ownership evidence may supersede an intent",
                idempotencyKey=key,
            )
        if evidence.get("idempotencyKey") != key:
            raise CursorCloudDispatchError(
                "cursor_cloud_intent_supersession_unrelated",
                "ownership evidence idempotency key does not match the intent",
                idempotencyKey=key,
            )
        record_repository = str(snapshot.get("repository") or "")
        evidence_repository = str(evidence.get("repository") or "")
        if not record_repository or evidence_repository != record_repository or (
            repository is not None and record_repository != repository
        ):
            raise CursorCloudDispatchError(
                "cursor_cloud_intent_supersession_unrelated",
                "ownership evidence repository is unrelated to the intent",
                idempotencyKey=key,
            )
        record_owner = snapshot.get("ownerId", snapshot.get("owner"))
        evidence_owner = evidence.get("ownerId", evidence.get("owner"))
        if (
            not isinstance(record_owner, str)
            or not record_owner.strip()
            or evidence_owner != record_owner
        ):
            raise CursorCloudDispatchError(
                "cursor_cloud_intent_supersession_ambiguous",
                "ownership evidence does not identify the current owner",
                idempotencyKey=key,
            )
        try:
            revision = int(snapshot["revision"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CursorCloudDispatchError(
                "cursor_cloud_intent_supersession_ambiguous",
                "PREPARED intent has no valid revision for ownership binding",
                idempotencyKey=key,
            ) from exc
        expected_digest = str(snapshot.get("digest") or "")
        if (
            not expected_digest
            or evidence.get("recordRevision") != revision
            or evidence.get("recordDigest") != expected_digest
        ):
            raise CursorCloudDispatchError(
                "cursor_cloud_intent_supersession_ambiguous",
                "ownership evidence is not bound to the current intent revision and digest",
                idempotencyKey=key,
            )
        run_status = str(evidence.get("runStatus") or snapshot.get("runStatus") or "").casefold()
        if run_status in {"active", "live", "running"} or evidence.get("readback") is False:
            raise CursorCloudDispatchError(
                "cursor_cloud_intent_supersession_live",
                "live or failed-readback ownership cannot be superseded",
                idempotencyKey=key,
            )

        current = store.read(key)
        if not isinstance(current, Mapping) or dict(current) != dict(snapshot):
            raise CursorCloudDispatchError(
                "cursor_cloud_intent_supersession_changed",
                "PREPARED intent changed after enumeration",
                idempotencyKey=key,
            )
        payload = dict(current)
        payload.pop("revision", None)
        payload.pop("digest", None)
        payload.update(
            {
                "state": "SUPERSEDED",
                "supersessionReason": "authoritative_stale_or_expired_ownership",
            }
        )
        _readback_write(
            store,
            key,
            payload,
            expected_revision=revision,
            expected_digest=expected_digest,
        )
        superseded.append(key)
    return superseded


def _response_value(response: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if response.get(key) is not None:
            return response[key]
    return None


def _archive_rejected_agent(http: CursorCloudHTTPPort, agent_id: str, headers: Mapping[str, str]) -> str:
    archive = getattr(http, "archive", None)
    try:
        if callable(archive):
            archive(agent_id, headers=headers)
        else:
            response = http.post(f"{API_PATH}/{agent_id}/archive", headers=headers, body={})
            status = int(response.get("statusCode", response.get("status", 0)) or 0)
            if status not in {200, 202, 204}:
                return f"archive_rejected_http_{status}"
        return "archived"
    except Exception as exc:  # preserve identity mismatch as primary failure
        return f"archive_failed:{type(exc).__name__}"


def _mark_rejected(
    store: CursorCloudIntentStore,
    key: str,
    current: Mapping[str, Any] | None,
    reason: str,
) -> None:
    if current is None or current.get("state") != "PREPARED":
        return
    payload = dict(current)
    revision = int(payload.pop("revision", 0))
    expected_digest = str(payload.pop("digest", "") or "") or None
    payload.update({"state": "REJECTED", "rejectionReason": reason})
    try:
        store.compare_and_write(key, revision, expected_digest, payload)
    except CursorCloudDispatchError:
        pass


def validate_cursor_cloud_run_readback(
    request: CursorCloudDispatchRequest, readback: Mapping[str, Any]
) -> None:
    """Require exact provider and repository identity readback before credit."""

    request.validate()
    observed_repository = _response_value(readback, "repository", "repositoryUrl", "remote")
    if not isinstance(observed_repository, str) or normalize_repository_remote(observed_repository) != request.normalized_remote:
        raise CursorCloudDispatchError(
            "cursor_cloud_run_repository_mismatch",
            "run readback repository does not match the explicit repository binding",
        )
    observed_ref = _response_value(readback, "ref", "startingRef", "branch")
    observed_commit = _response_value(readback, "commit", "headCommit", "head")
    observed_tree = _response_value(readback, "tree", "headTree")
    for field_name, observed, expected in (
        ("ref", observed_ref, request.ref),
        ("commit", observed_commit, request.commit),
        ("tree", observed_tree, request.tree),
    ):
        if observed != expected:
            raise CursorCloudDispatchError(
                f"cursor_cloud_run_{field_name}_mismatch",
                f"run readback {field_name} does not match the requested starting identity",
            )
    install_status = _response_value(readback, "installStatus", "setupStatus")
    if install_status is not None and str(install_status).casefold() not in {
        "success", "succeeded", "complete", "completed", "ready"
    }:
        raise CursorCloudDispatchError(
            "cursor_cloud_run_install_failed", "run readback reports failed repository setup"
        )
    if readback.get("provider") != request.provider:
        raise CursorCloudDispatchError(
            "cursor_cloud_run_provider_mismatch", "run readback provider is not exact"
        )
    if readback.get("model") != request.model or readback.get("effectiveModel", request.model) != request.model:
        raise CursorCloudDispatchError(
            "cursor_cloud_run_model_mismatch", "run readback model is not exact"
        )
    if readback.get("effort", readback.get("reasoningEffort")) != DIRECT_EFFORT:
        raise CursorCloudDispatchError(
            "cursor_cloud_run_effort_mismatch", "run readback reasoning effort is not exact"
        )
    if readback.get("fast") is not False:
        raise CursorCloudDispatchError(
            "cursor_cloud_run_fast_readback_mismatch", "run readback must explicitly prove Fast is false"
        )


def _rest_get_run_readback(
    http: CursorCloudHTTPPort,
    agent_id: str,
    headers: Mapping[str, str],
    request: CursorCloudDispatchRequest,
) -> Mapping[str, Any]:
    response = http.get(f"{API_PATH}/{agent_id}", headers=headers)
    status = int(response.get("statusCode", response.get("status", 0)) or 0)
    if status != 200:
        raise CursorCloudDispatchError(
            "cursor_cloud_rest_readback_rejected", "run readback did not return HTTP 200", statusCode=status
        )
    validate_cursor_cloud_run_readback(request, response)
    return response


def dispatch_cursor_cloud(
    request: CursorCloudDispatchRequest,
    store: CursorCloudIntentStore,
    http: CursorCloudHTTPPort,
    *,
    environment: Mapping[str, str] | None = None,
    cursor_cli_authenticated: bool = False,
    readback: CursorCloudHTTPPort | None = None,
    ownership_evidence: Mapping[str, Mapping[str, Any]] | None = None,
) -> CursorCloudDispatchResult:
    """Create, read back, and durably commit one explicit repository-bound run."""

    # Model/provider validation precedes API-key and HTTP work.
    request.validate()
    key = cursor_cloud_idempotency_key(request)
    api_key = require_cursor_cloud_api_key(
        environment, cursor_cli_authenticated=cursor_cli_authenticated
    )
    supersede_obsolete_prepared_intents(
        store,
        current_idempotency_key=key,
        repository=request.repository,
        ownership_evidence=ownership_evidence,
    )
    client_agent_id = cursor_cloud_client_agent_id(request)
    prompt = build_attestation_prompt(request)
    current = store.read(key)
    if current is not None and current.get("state") == "COMMITTED":
        return CursorCloudDispatchResult(
            "duplicate", key, client_agent_id, str(current["agentId"]), str(current["runId"]),
            request.repository, request.ref, request.commit, request.tree, request.provider,
            request.model, DIRECT_EFFORT, False, int(current["revision"]), prompt,
        )
    if current is None:
        intent = {
            "state": "PREPARED", "idempotencyKey": key, "clientAgentId": client_agent_id,
            "repository": request.repository, "repositoryUrl": request.normalized_remote,
            "ref": request.ref, "commit": request.commit, "tree": request.tree,
            "provider": request.provider, "routeId": request.route_id, "model": request.model,
            "effort": DIRECT_EFFORT, "fast": False, "modelParameters": dict(request.model_parameters),
            "repositoryBindings": request.repository_bindings,
            "expectedBuildId": request.expected_build_id, "toolchain": dict(request.toolchain),
            "governedSetup": request.governed_setup, "setupReceiptDigest": request.setup_receipt_digest,
        }
        current = _readback_write(store, key, intent, expected_revision=0, expected_digest=None)
    if current.get("clientAgentId") != client_agent_id:
        raise CursorCloudDispatchError(
            "cursor_cloud_idempotency_collision", "existing intent has another client agent id"
        )
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
        "Idempotency-Key": key,
    }
    body = {
        "agentId": client_agent_id,
        "repos": request.repository_bindings,
        "model": request.model,
        "modelParameters": dict(request.model_parameters),
        "prompt": prompt,
    }
    response: Mapping[str, Any] | None = None
    for attempt in range(MAX_API_ATTEMPTS):
        try:
            response = http.post(API_PATH, headers=headers, body=body)
            break
        except CursorCloudDispatchError:
            raise
        except Exception as exc:
            if attempt + 1 == MAX_API_ATTEMPTS:
                raise CursorCloudDispatchError(
                    "cursor_cloud_api_interrupted",
                    "Cloud API call did not produce an authoritative response after one retry",
                ) from exc
    if response is None:  # pragma: no cover
        raise CursorCloudDispatchError("cursor_cloud_api_interrupted", "Cloud API response was unavailable")
    status = int(response.get("statusCode", response.get("status", 0)) or 0)
    if status != 201:
        raise CursorCloudDispatchError(
            "cursor_cloud_api_rejected", "Cursor Cloud API did not return HTTP 201", statusCode=status
        )
    agent_id = str(_response_value(response, "agentId", "id") or "")
    run = response.get("run")
    run_id = str(_response_value(response, "runId") or (run.get("id") if isinstance(run, Mapping) else "") or "")
    if not agent_id or not run_id:
        raise CursorCloudDispatchError(
            "cursor_cloud_response_identity_missing", "response must include agent and run identity"
        )
    if agent_id != client_agent_id:
        archive_status = _archive_rejected_agent(http, agent_id, headers)
        _mark_rejected(store, key, current, "agent_identity_mismatch")
        raise CursorCloudDispatchError(
            "cursor_cloud_agent_identity_mismatch", "Cloud response did not preserve the client identity", archive=archive_status
        )
    readback_http = readback or http
    try:
        observed = _rest_get_run_readback(readback_http, agent_id, headers, request)
    except CursorCloudDispatchError as exc:
        archive_status = _archive_rejected_agent(http, agent_id, headers)
        _mark_rejected(store, key, current, exc.code)
        raise CursorCloudDispatchError(
            "cursor_cloud_identity_mismatch_archived",
            f"run readback rejected: {exc.detail}",
            cause=exc.code,
            archive=archive_status,
        ) from exc
    committed_payload = dict(current)
    committed_payload.update({"state": "COMMITTED", "agentId": agent_id, "runId": run_id, "readback": dict(observed)})
    committed = _readback_write(
        store,
        key,
        {field: value for field, value in committed_payload.items() if field not in {"revision", "digest"}},
        expected_revision=int(current["revision"]),
        expected_digest=str(current["digest"]),
    )
    return CursorCloudDispatchResult(
        "committed", key, client_agent_id, agent_id, run_id, request.repository, request.ref,
        request.commit, request.tree, request.provider, request.model, DIRECT_EFFORT, False,
        int(committed["revision"]), prompt,
    )


def dispatch_cursor_cloud_sdk(
    request: CursorCloudDispatchRequest,
    store: CursorCloudIntentStore,
    sdk: CursorCloudSDKPort,
    *,
    environment: Mapping[str, str] | None = None,
    cursor_cli_authenticated: bool = False,
    ownership_evidence: Mapping[str, Mapping[str, Any]] | None = None,
) -> CursorCloudDispatchResult:
    """Preferred SDK path sharing REST create/readback/archive semantics."""

    sdk_http = _SDKAsHTTPPort(request, sdk)
    return dispatch_cursor_cloud(
        request, store, sdk_http,
        environment=environment,
        cursor_cli_authenticated=cursor_cli_authenticated,
        ownership_evidence=ownership_evidence,
    )


def validate_cursor_cloud_attestation(
    request: CursorCloudDispatchRequest, attestation: Mapping[str, Any]
) -> None:
    """Permit later mutation only after exact read-only attestation."""

    request.validate()
    if attestation.get("status") != "PASS" or attestation.get("noMutation") is not True:
        raise CursorCloudDispatchError(
            "cursor_cloud_attestation_required", "mutation requires a PASS no-mutation attestation"
        )
    if attestation.get("workspaceClean") is not True:
        raise CursorCloudDispatchError(
            "cursor_cloud_attestation_required", "mutation requires a clean workspace attestation"
        )
    expected = {
        "repository": request.repository,
        "remote": request.normalized_remote,
        "ref": request.ref,
        "commit": request.commit,
        "tree": request.tree,
        "toolchain": dict(request.toolchain),
        "workspaceClean": True,
    }
    for field_name, expected_value in expected.items():
        observed = attestation.get(field_name)
        if field_name == "remote":
            observed = normalize_repository_remote(str(observed or ""))
        if field_name == "toolchain" and isinstance(observed, Mapping):
            observed = dict(observed)
        if observed != expected_value:
            raise CursorCloudDispatchError(
                "cursor_cloud_attestation_mismatch",
                "mutation blocked because Cloud attestation does not match",
                field=field_name,
            )


def load_cursor_cloud_dispatch_config(repo_root: str) -> dict[str, Any]:
    import jsonschema

    root = Path(repo_root).resolve()
    config = json.loads((root / "core/managed-core/content/config/cursor-cloud-dispatch.json").read_text())
    schema = json.loads((root / "core/managed-core/schemas/cursor-cloud-dispatch.schema.json").read_text())
    errors = sorted(error.message for error in jsonschema.Draft202012Validator(schema).iter_errors(config))
    if errors:
        raise CursorCloudDispatchError("cursor_cloud_config_invalid", "; ".join(errors))
    return config

def load_routing_registry(repo_root: str) -> dict[str, Any]:
    import jsonschema

    root = Path(repo_root).resolve()
    config = json.loads((root / "core/managed-core/content/config/routing-registry.json").read_text())
    schema = json.loads((root / "core/managed-core/schemas/routing-registry.schema.json").read_text())
    errors = sorted(error.message for error in jsonschema.Draft202012Validator(schema).iter_errors(config))
    if errors:
        raise CursorCloudDispatchError("cursor_cloud_routing_registry_invalid", "; ".join(errors))
    return config
