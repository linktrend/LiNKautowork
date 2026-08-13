"""Deterministic delivery lifecycle state and candidate identity primitives."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlparse

_SHA40 = 40
TERMINAL_STATES = frozenset({"main-promoted", "stopped", "blocked", "cancelled"})
LIFECYCLE_STATES = frozenset(
    {
        "created", "collecting", "draft", "sealed", "candidate-failed",
        "fast-running", "fast-passed", "bugbot-running", "bugbot-passed",
        "full-running", "full-passed", "candidate-ready", "merged",
        "staging-running", "staging-passed", "staging-promoted",
        "release-running", "release-passed", "main-awaiting-approval",
        *TERMINAL_STATES,
    }
)
_GATE_TO_RUNNING = {
    "fast-gate": "fast-running",
    "bugbot": "bugbot-running",
    "full-gate": "full-running",
    "staging-gate": "staging-running",
    "release-gate": "release-running",
}
_GATE_TO_PASSED = {
    "fast-gate": "fast-passed",
    "bugbot": "bugbot-passed",
    "full-gate": "full-passed",
    "staging-gate": "staging-passed",
    "release-gate": "release-passed",
}
_GATE_ORDER = ("fast-gate", "bugbot", "full-gate", "staging-gate", "release-gate")


class StateError(ValueError):
    """Structured fail-closed lifecycle error."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


def _sha(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or len(value) != _SHA40 or any(c not in "0123456789abcdef" for c in value):
        raise StateError("invalid_sha", f"{field_name} must be 40 lowercase hexadecimal characters")
    return value


@dataclass(frozen=True)
class CandidateIdentity:
    repository: str
    source_sha: str
    git_tree_sha: str
    dependency_digests: Mapping[str, str]
    test_profile: str

    def __post_init__(self) -> None:
        if not self.repository or "/" not in self.repository:
            raise StateError("invalid_repository", "repository must be owner/name")
        _sha(self.source_sha, field_name="sourceSha")
        _sha(self.git_tree_sha, field_name="gitTreeSha")
        if self.test_profile not in {"fast", "full", "release"}:
            raise StateError("invalid_test_profile", "testProfile must be fast, full, or release")
        if not isinstance(self.dependency_digests, Mapping):
            raise StateError("invalid_dependency_digests", "dependencyDigests must be an object")
        for path, digest in self.dependency_digests.items():
            if not isinstance(path, str) or not path or PurePosixPath(path).is_absolute() or path.startswith("../"):
                raise StateError("invalid_dependency_path", "dependency digest path must be relative")
            if not isinstance(digest, str) or len(digest) != 71 or not digest.startswith("sha256:") or any(c not in "0123456789abcdef" for c in digest[7:]):
                raise StateError("invalid_dependency_digest", f"invalid digest for {path}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "sourceSha": self.source_sha,
            "gitTreeSha": self.git_tree_sha,
            "dependencyDigests": {key: self.dependency_digests[key] for key in sorted(self.dependency_digests)},
            "testProfile": self.test_profile,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CandidateIdentity":
        if set(payload) != {"repository", "sourceSha", "gitTreeSha", "dependencyDigests", "testProfile"}:
            raise StateError("invalid_candidate_identity", "candidate identity fields are incomplete or unknown")
        return cls(
            repository=payload["repository"], source_sha=payload["sourceSha"],
            git_tree_sha=payload["gitTreeSha"], dependency_digests=dict(payload["dependencyDigests"]),
            test_profile=payload["testProfile"],
        )

    def canonical(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)
    if result.returncode:
        raise StateError("git_identity_failed", (result.stderr or "git command failed").strip())
    return result.stdout.strip()


def _repository_name(repo: Path) -> str:
    remote = _git(repo, "config", "--get", "remote.origin.url")
    if remote:
        if remote.startswith("git@") and ":" in remote:
            path = remote.split(":", 1)[1]
        else:
            path = urlparse(remote).path.lstrip("/")
        path = path.removesuffix(".git").strip("/")
        if "/" in path:
            return path
    raise StateError("repository_identity_unavailable", "origin must identify owner/name")


def _safe_dependency(repo: Path, raw: str) -> tuple[str, Path]:
    if not isinstance(raw, str) or not raw or "\\" in raw or raw.startswith(("/", "~")):
        raise StateError("unsafe_dependency_path", "dependency path must be relative")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or str(relative) in {".", ".."} or str(relative).startswith("../"):
        raise StateError("dependency_path_escape", "dependency path escapes repository")
    normalized = str(relative)
    candidate = repo / Path(*relative.parts)
    if candidate.is_symlink() or not candidate.is_file():
        raise StateError("dependency_unavailable", f"dependency file is not a regular file: {normalized}")
    return normalized, candidate


def compute_candidate_identity(repo_path: str | os.PathLike[str], dependency_files: list[str] | tuple[str, ...]) -> CandidateIdentity:
    """Compute exact Git and dependency identity without executing candidate code."""
    repo = Path(repo_path).resolve()
    if not (repo / ".git").exists():
        raise StateError("not_a_repository", str(repo))
    source = _sha(_git(repo, "rev-parse", "HEAD"), field_name="sourceSha")
    tree = _sha(_git(repo, "rev-parse", "HEAD^{tree}"), field_name="gitTreeSha")
    digests: dict[str, str] = {}
    for raw in dependency_files:
        normalized, path = _safe_dependency(repo, raw)
        digests[normalized] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return CandidateIdentity(_repository_name(repo), source, tree, digests, "fast")


@dataclass(frozen=True)
class DeliveryState:
    repository: str
    phase_branch: str
    phase_id: str
    immutable_base_sha: str
    status: str = "created"
    accepted_issues: tuple[Mapping[str, Any], ...] = ()
    candidate_identity: CandidateIdentity | None = None
    sealed_candidate_revisions: int = 0
    attempts: int = 0
    gate_results: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    draft_pr: Mapping[str, Any] | None = None
    merge_sha: str | None = None
    staging_sha: str | None = None
    stop_reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in LIFECYCLE_STATES:
            raise StateError("invalid_state", f"unknown lifecycle state: {self.status}")
        _sha(self.immutable_base_sha, field_name="immutableBaseSha")
        if not self.repository or not self.phase_branch or not self.phase_id:
            raise StateError("invalid_state_identity", "repository, phase branch, and phase id are required")
        if not 0 <= self.sealed_candidate_revisions <= 2 or not 0 <= self.attempts <= 2:
            raise StateError("invalid_counters", "attempts and sealed revisions must be from zero through two")

    @property
    def state_id(self) -> str:
        return f"{self.repository}|{self.phase_branch}|{self.phase_id}"

    @classmethod
    def new(cls, repository: str, phase_branch: str, phase_id: str, immutable_base_sha: str) -> "DeliveryState":
        return cls(repository, phase_branch, phase_id, immutable_base_sha)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schemaVersion": 1,
            "repository": self.repository,
            "phaseBranch": self.phase_branch,
            "phaseId": self.phase_id,
            "immutableBaseSha": self.immutable_base_sha,
            "status": self.status,
            "acceptedIssues": [dict(item) for item in self.accepted_issues],
            "candidateIdentity": self.candidate_identity.to_dict() if self.candidate_identity else None,
            "sealedCandidateRevisions": self.sealed_candidate_revisions,
            "attempts": self.attempts,
            "gateResults": {key: dict(self.gate_results[key]) for key in sorted(self.gate_results)},
            "draftPr": dict(self.draft_pr) if self.draft_pr else None,
            "mergeSha": self.merge_sha,
            "stagingSha": self.staging_sha,
            "stopReason": self.stop_reason,
        }
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DeliveryState":
        required = {"schemaVersion", "repository", "phaseBranch", "phaseId", "immutableBaseSha", "status", "acceptedIssues", "candidateIdentity", "sealedCandidateRevisions", "attempts", "gateResults", "draftPr", "mergeSha", "stagingSha", "stopReason"}
        if set(payload) != required or payload.get("schemaVersion") != 1:
            raise StateError("invalid_state_serialization", "state schema is incomplete or has unknown fields")
        candidate = payload["candidateIdentity"]
        return cls(
            repository=payload["repository"], phase_branch=payload["phaseBranch"], phase_id=payload["phaseId"],
            immutable_base_sha=payload["immutableBaseSha"], status=payload["status"],
            accepted_issues=tuple(dict(item) for item in payload["acceptedIssues"]),
            candidate_identity=CandidateIdentity.from_dict(candidate) if candidate is not None else None,
            sealed_candidate_revisions=payload["sealedCandidateRevisions"], attempts=payload["attempts"],
            gate_results={key: dict(value) for key, value in payload["gateResults"].items()},
            draft_pr=dict(payload["draftPr"]) if payload["draftPr"] is not None else None,
            merge_sha=payload["mergeSha"], staging_sha=payload["stagingSha"], stop_reason=payload["stopReason"],
        )


def _event_parts(event: str | Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    if isinstance(event, str):
        return event.strip().lower().replace("_", "-"), {}
    if not isinstance(event, Mapping):
        raise StateError("invalid_event", "event must be a string or object")
    name = event.get("type", event.get("event", event.get("name")))
    if not isinstance(name, str) or not name.strip():
        raise StateError("invalid_event", "event object requires type")
    return name.strip().lower().replace("_", "-"), dict(event)


def _assert_event_identity(state: DeliveryState, data: Mapping[str, Any]) -> None:
    mappings = (("repository", state.repository), ("phaseBranch", state.phase_branch), ("phaseId", state.phase_id), ("baseSha", state.immutable_base_sha), ("immutableBaseSha", state.immutable_base_sha))
    for key, expected in mappings:
        if key in data and data[key] != expected:
            raise StateError("stale_identity", f"{key} does not match current state")
    if state.candidate_identity is not None:
        supplied = data.get("candidateIdentity", data.get("candidate"))
        if supplied is not None:
            candidate = supplied if isinstance(supplied, CandidateIdentity) else CandidateIdentity.from_dict(supplied)
            if candidate.canonical() != state.candidate_identity.canonical():
                raise StateError("stale_identity", "candidate identity does not match sealed candidate")
        for key, expected in (("sourceSha", state.candidate_identity.source_sha), ("gitTreeSha", state.candidate_identity.git_tree_sha)):
            if key in data and data[key] != expected:
                raise StateError("stale_identity", f"{key} does not match sealed candidate")


def _record_gate(state: DeliveryState, gate: str, status: str, data: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    results = {key: dict(value) for key, value in state.gate_results.items()}
    results[gate] = {
        "status": status,
        "attempt": state.attempts,
        "detail": str(data.get("detail") or ""),
    }
    return results


def transition(state: DeliveryState, event: str | Mapping[str, Any]) -> DeliveryState:
    """Apply one structured lifecycle event, rejecting stale or illegal changes."""
    name, data = _event_parts(event)
    if state.status in TERMINAL_STATES:
        raise StateError("terminal_state", f"{state.status} cannot transition")
    if name not in {"sealed", "seal", "candidate-sealed"}:
        _assert_event_identity(state, data)
    if name in {"observe", "passive-observation", "deduplicate", "dedup", "queue-observation", "cancel-before-start", "pre-start-cancellation"}:
        if name in {"cancel-before-start", "pre-start-cancellation"}:
            return replace(state, status="cancelled", stop_reason="cancelled-before-execution")
        return state
    if name in {"phase-created", "phase-opened"}:
        if state.status != "created":
            raise StateError("illegal_order", "phase can only be opened once")
        return replace(state, status="collecting")
    if name in {"issue-accepted", "issue-included"}:
        if state.status not in {"created", "collecting", "draft"}:
            raise StateError("illegal_order", "Issue work cannot be added after sealing")
        issue = data.get("issue", data)
        if not isinstance(issue, Mapping) or not issue.get("branch") or not issue.get("sha"):
            raise StateError("invalid_event", "Issue acceptance requires branch and sha")
        rows = [dict(item) for item in state.accepted_issues]
        existing = next((row for row in rows if row.get("branch") == issue["branch"]), None)
        if existing is not None:
            if existing.get("sha") != issue["sha"]:
                raise StateError("stale_identity", "Issue branch tip changed after acceptance")
            if name == "issue-included" and existing.get("accepted"):
                existing["included"] = True
                return replace(state, accepted_issues=tuple(rows))
            return state
        row = {"branch": issue["branch"], "sha": issue["sha"], "accepted": name == "issue-accepted", "included": name == "issue-included"}
        rows.append(row)
        return replace(state, status="collecting", accepted_issues=tuple(rows))
    if name in {"draft-pr-created", "draft-created"}:
        if state.status not in {"collecting", "draft"}:
            raise StateError("illegal_order", "draft PR requires collected Issue work")
        pr = data.get("draftPr", data.get("pr"))
        if not isinstance(pr, Mapping):
            raise StateError("invalid_event", "draft PR event requires structured draftPr")
        if state.draft_pr is not None and dict(state.draft_pr) != dict(pr):
            raise StateError("stale_identity", "draft PR identity changed")
        return replace(state, status="draft", draft_pr=dict(pr))
    if name in {"sealed", "seal", "candidate-sealed"}:
        if state.sealed_candidate_revisions >= 2:
            raise StateError("third_seal", "a third sealed candidate requires principal authorization")
        if state.status not in {"collecting", "draft", "candidate-failed"}:
            raise StateError("illegal_order", "candidate can only be sealed after collection or one failed attempt")
        supplied = data.get("candidateIdentity", data.get("candidate"))
        if not isinstance(supplied, CandidateIdentity) and not isinstance(supplied, Mapping):
            raise StateError("invalid_event", "seal requires candidateIdentity")
        candidate = supplied if isinstance(supplied, CandidateIdentity) else CandidateIdentity.from_dict(supplied)
        if candidate.repository != state.repository:
            raise StateError("stale_identity", "candidate repository does not match state")
        return replace(state, status="sealed", candidate_identity=candidate, sealed_candidate_revisions=state.sealed_candidate_revisions + 1)
    if name in {"execution-started", "job-started", "start-execution"}:
        gate = str(data.get("gate", "fast-gate"))
        if gate not in _GATE_TO_RUNNING:
            raise StateError("invalid_gate", "unknown execution gate")
        if gate == "staging-gate" and state.status == "merged":
            return replace(state, status="staging-running")
        if gate == "release-gate" and state.status == "staging-promoted":
            return replace(state, status="release-running")
        if state.status != "sealed" or state.candidate_identity is None:
            raise StateError("illegal_order", "candidate execution requires a sealed candidate")
        if state.attempts >= 2:
            raise StateError("attempt_limit", "candidate already used two execution attempts")
        return replace(state, status=_GATE_TO_RUNNING[gate], attempts=state.attempts + 1)
    if name in {"execution-failed", "job-failed", "gate-failed"}:
        if state.status not in set(_GATE_TO_RUNNING.values()):
            raise StateError("illegal_order", "failure requires a running gate")
        gate = str(data.get("gate", next((key for key, value in _GATE_TO_RUNNING.items() if value == state.status), "fast-gate")))
        results = _record_gate(state, gate, "failed", data)
        if state.attempts >= 2:
            return replace(state, status="stopped", gate_results=results, stop_reason="two-execution-attempts-failed")
        return replace(state, status="candidate-failed", gate_results=results)
    if name in {"gate-passed", "execution-passed", "fast-gate-passed", "bugbot-passed", "full-gate-passed", "staging-gate-passed", "release-gate-passed"}:
        gate = str(data.get("gate", ""))
        if not gate and name.endswith("-passed"):
            gate = "bugbot" if name == "bugbot-passed" else name.removesuffix("-passed")
        if gate not in _GATE_TO_PASSED:
            raise StateError("invalid_gate", "gate-passed requires a known gate")
        required_before = {
            "fast-gate": {"sealed", "fast-running"}, "bugbot": {"fast-passed", "bugbot-running"},
            "full-gate": {"bugbot-passed", "full-running", "fast-passed"},
            "staging-gate": {"merged", "staging-running"},
            "release-gate": {"staging-promoted", "release-running", "staging-passed"},
        }
        if state.status not in required_before[gate]:
            raise StateError("illegal_order", f"{gate} cannot pass from {state.status}")
        next_status = _GATE_TO_PASSED[gate]
        if gate == "full-gate":
            next_status = "candidate-ready"
        return replace(state, status=next_status, gate_results=_record_gate(state, gate, "passed", data))
    if name in {"merge-development", "development-merged", "merged"}:
        if state.status != "candidate-ready":
            raise StateError("illegal_order", "development merge requires all candidate gates")
        merge_sha = data.get("mergeSha")
        _sha(merge_sha, field_name="mergeSha")
        return replace(state, status="merged", merge_sha=merge_sha)
    if name in {"staging-promoted", "promote-staging"}:
        if state.status not in {"merged", "staging-passed"} or "staging-gate" not in state.gate_results or state.gate_results["staging-gate"].get("status") != "passed":
            raise StateError("illegal_order", "staging promotion requires merged state and staging gate")
        staging_sha = data.get("stagingSha", data.get("sha"))
        _sha(staging_sha, field_name="stagingSha")
        return replace(state, status="staging-promoted", staging_sha=staging_sha)
    if name in {"await-main-approval", "main-approval-requested"}:
        if state.status not in {"staging-promoted", "release-passed"}:
            raise StateError("illegal_order", "main approval requires staging promotion")
        return replace(state, status="main-awaiting-approval")
    if name in {"main-promoted", "promote-main"}:
        if state.status not in {"staging-promoted", "release-passed", "main-awaiting-approval"} or "release-gate" not in state.gate_results or state.gate_results["release-gate"].get("status") != "passed":
            raise StateError("illegal_order", "main promotion requires exact release gate")
        return replace(state, status="main-promoted")
    if name in {"blocked", "stop", "stopped", "cancelled", "cancel"}:
        status = "blocked" if name == "blocked" else "stopped" if name in {"stop", "stopped"} else "cancelled"
        return replace(state, status=status, stop_reason=str(data.get("reason") or name))
    raise StateError("unknown_event", f"unsupported lifecycle event: {name}")


def _state_path(state_id: str | os.PathLike[str]) -> Path:
    return Path(state_id)


def save_state(state: DeliveryState, state_id: str | os.PathLike[str]) -> Path:
    """Atomically serialize state; an interrupted replacement leaves old JSON intact."""
    path = _state_path(state_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return path


def load_state(state_id: str | os.PathLike[str]) -> DeliveryState | None:
    path = _state_path(state_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError("state_unreadable", str(exc)) from exc
    if not isinstance(payload, Mapping):
        raise StateError("state_unreadable", "state JSON must be an object")
    return DeliveryState.from_dict(payload)
