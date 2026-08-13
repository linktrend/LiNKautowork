"""Deterministic delivery lifecycle state and candidate identity primitives."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
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


# W1-P2 candidate lifecycle -------------------------------------------------
#
# The W1-P1 DeliveryState above is retained for compatibility with the
# existing phase-integrator and receipt consumers.  CandidateLifecycle is the
# narrower reducer used by the compute-consuming Phase candidate flow.  It has
# its own schema so that an old phase record cannot accidentally be interpreted
# as a sealed candidate record.

P2_CHECKS = ("fast", "full", "review")
P2_ACTIVE_STATES = frozenset({
    "checkpointed", "integrating", "draft-phase-pr", "sealed-candidate",
    "fast-checking", "full-checking", "review-checking",
    "review-complete", "development-eligible", "staging-eligible", "main-eligible",
    "infrastructure-retry", "code-failed",
})
P2_TERMINAL_CANDIDATE_STATES = frozenset({"superseded", "code-failed", "stopped-alert", "cancelled"})
P2_PHASE_TERMINAL_STATES = frozenset({"stopped-alert"})

OUTCOME_CHECKPOINT_RECORDED = "checkpoint_recorded"
OUTCOME_NO_DISPATCH = "no_dispatch"
OUTCOME_DUPLICATE_IGNORED = "duplicate_ignored"
OUTCOME_CANDIDATE_SEALED = "candidate_sealed"
OUTCOME_CANDIDATE_SUPERSEDED = "candidate_superseded"
OUTCOME_LATE_RESULT_REJECTED = "late_result_rejected"
OUTCOME_INFRASTRUCTURE_RETRY = "infrastructure_retry"
OUTCOME_STOPPED_ALERT = "stopped_alert"
OUTCOME_CODE_FAILURE = "code_failure"
OUTCOME_HOLD_SEALED_CANDIDATE_LIMIT = "hold_sealed_candidate_limit"
OUTCOME_CHECK_PASSED = "check_passed"
OUTCOME_ELIGIBILITY_RECORDED = "eligibility_recorded"
OUTCOME_CANCELLED = "cancelled"
OUTCOME_OUT_OF_ORDER = "out_of_order_event"


def _p2_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise StateError("invalid_candidate_field", f"{field_name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class PhaseCandidateIdentity:
    """The immutable W1-P2 candidate identity from FROZEN-INTERFACES.md."""

    repository: str
    source_branch: str
    head_commit: str
    git_tree: str
    dependency_digest: str
    profile_digest: str
    workflow_digest: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[^/\s]+/[^/\s]+", self.repository):
            raise StateError("invalid_repository", "repository must be owner/name")
        _p2_text(self.source_branch, "sourceBranch")
        _sha(self.head_commit, field_name="headCommit")
        _sha(self.git_tree, field_name="gitTree")
        for name, value in (
            ("dependencyDigest", self.dependency_digest),
            ("profileDigest", self.profile_digest),
            ("workflowDigest", self.workflow_digest),
        ):
            _p2_text(value, name)

    def to_dict(self) -> dict[str, str]:
        return {
            "repository": self.repository,
            "sourceBranch": self.source_branch,
            "headCommit": self.head_commit,
            "gitTree": self.git_tree,
            "dependencyDigest": self.dependency_digest,
            "profileDigest": self.profile_digest,
            "workflowDigest": self.workflow_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PhaseCandidateIdentity":
        expected = {"repository", "sourceBranch", "headCommit", "gitTree", "dependencyDigest", "profileDigest", "workflowDigest"}
        if set(payload) != expected:
            raise StateError("invalid_candidate_identity", "candidate identity fields are incomplete or unknown")
        return cls(
            repository=payload["repository"],
            source_branch=payload["sourceBranch"],
            head_commit=payload["headCommit"],
            git_tree=payload["gitTree"],
            dependency_digest=payload["dependencyDigest"],
            profile_digest=payload["profileDigest"],
            workflow_digest=payload["workflowDigest"],
        )

    def canonical(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class CandidateSeal:
    """A seal binding a candidate identity to the PR and exact head."""

    repository: str
    pr_number: int
    source_branch: str
    head_commit: str
    identity: PhaseCandidateIdentity

    def __post_init__(self) -> None:
        if self.repository != self.identity.repository:
            raise StateError("seal_identity_mismatch", "seal repository differs from candidate identity")
        if isinstance(self.pr_number, bool) or not isinstance(self.pr_number, int) or self.pr_number < 1:
            raise StateError("invalid_pr_number", "prNumber must be a positive integer")
        _p2_text(self.source_branch, "sourceBranch")
        _sha(self.head_commit, field_name="headCommit")
        if self.source_branch != self.identity.source_branch or self.head_commit != self.identity.head_commit:
            raise StateError("seal_identity_mismatch", "seal branch and head must match candidate identity")

    @property
    def candidate_id(self) -> str:
        payload = {
            "repository": self.repository,
            "prNumber": self.pr_number,
            "sourceBranch": self.source_branch,
            "headCommit": self.head_commit,
            "candidateIdentity": self.identity.to_dict(),
        }
        return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def concurrency_key(self, workflow: str) -> str:
        return concurrency_key(self.repository, workflow, self.pr_number)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "prNumber": self.pr_number,
            "sourceBranch": self.source_branch,
            "headCommit": self.head_commit,
            "candidateId": self.candidate_id,
            "candidateIdentity": self.identity.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CandidateSeal":
        expected = {"repository", "prNumber", "sourceBranch", "headCommit", "candidateIdentity"}
        # candidateId is derived and accepted only as a checked redundant field.
        if set(payload) not in (expected, expected | {"candidateId"}):
            raise StateError("invalid_seal", "seal fields are incomplete or unknown")
        seal = cls(
            repository=payload["repository"],
            pr_number=payload["prNumber"],
            source_branch=payload["sourceBranch"],
            head_commit=payload["headCommit"],
            identity=PhaseCandidateIdentity.from_dict(payload["candidateIdentity"]),
        )
        if "candidateId" in payload and payload["candidateId"] != seal.candidate_id:
            raise StateError("invalid_seal", "candidateId does not match seal contents")
        return seal


@dataclass(frozen=True)
class CandidateRecord:
    seal: CandidateSeal
    status: str = "sealed-candidate"
    attempts: int = 0
    checks: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    invalidated: bool = False
    stop_reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in P2_ACTIVE_STATES | P2_TERMINAL_CANDIDATE_STATES:
            raise StateError("invalid_candidate_state", self.status)
        if not isinstance(self.attempts, int) or not 0 <= self.attempts <= 2:
            raise StateError("invalid_candidate_attempts", "attempts must be from zero through two")
        if not isinstance(self.invalidated, bool):
            raise StateError("invalid_candidate_record", "invalidated must be boolean")
        if not isinstance(self.checks, Mapping):
            raise StateError("invalid_candidate_record", "checks must be an object")

    @property
    def candidate_id(self) -> str:
        return self.seal.candidate_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "seal": self.seal.to_dict(),
            "status": self.status,
            "attempts": self.attempts,
            "checks": {name: dict(self.checks[name]) for name in sorted(self.checks)},
            "invalidated": self.invalidated,
            "stopReason": self.stop_reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CandidateRecord":
        expected = {"seal", "status", "attempts", "checks", "invalidated", "stopReason"}
        if set(payload) != expected:
            raise StateError("invalid_candidate_record", "candidate record fields are incomplete or unknown")
        return cls(
            seal=CandidateSeal.from_dict(payload["seal"]),
            status=payload["status"],
            attempts=payload["attempts"],
            checks={name: dict(value) for name, value in payload["checks"].items()},
            invalidated=payload["invalidated"],
            stop_reason=payload["stopReason"],
        )


@dataclass(frozen=True)
class CandidateLifecycleState:
    repository: str
    phase_id: str
    phase_branch: str
    immutable_base_sha: str
    status: str = "checkpointed"
    current_head: str | None = None
    sealed_revisions: int = 0
    candidates: Mapping[str, CandidateRecord] = field(default_factory=dict)
    seen_events: tuple[str, ...] = ()
    stop_reason: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[^/\s]+/[^/\s]+", self.repository):
            raise StateError("invalid_repository", "repository must be owner/name")
        _p2_text(self.phase_id, "phaseId")
        _p2_text(self.phase_branch, "phaseBranch")
        _sha(self.immutable_base_sha, field_name="immutableBaseSha")
        if self.status not in P2_ACTIVE_STATES | P2_PHASE_TERMINAL_STATES:
            raise StateError("invalid_lifecycle_state", self.status)
        if self.current_head is not None:
            _sha(self.current_head, field_name="currentHead")
        if not isinstance(self.sealed_revisions, int) or not 0 <= self.sealed_revisions <= 2:
            raise StateError("invalid_sealed_revisions", "sealed revisions must be from zero through two")
        if not isinstance(self.candidates, Mapping):
            raise StateError("invalid_lifecycle_state", "candidates must be an object")
        if not isinstance(self.seen_events, tuple) or any(not isinstance(event, str) or not event for event in self.seen_events):
            raise StateError("invalid_lifecycle_state", "seenEvents must contain non-empty strings")

    @classmethod
    def new(cls, repository: str, phase_id: str, phase_branch: str, immutable_base_sha: str) -> "CandidateLifecycleState":
        return cls(repository, phase_id, phase_branch, immutable_base_sha)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": 2,
            "repository": self.repository,
            "phaseId": self.phase_id,
            "phaseBranch": self.phase_branch,
            "immutableBaseSha": self.immutable_base_sha,
            "status": self.status,
            "currentHead": self.current_head,
            "sealedRevisions": self.sealed_revisions,
            "candidates": {key: self.candidates[key].to_dict() for key in sorted(self.candidates)},
            "seenEvents": list(self.seen_events),
            "stopReason": self.stop_reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CandidateLifecycleState":
        expected = {"schemaVersion", "repository", "phaseId", "phaseBranch", "immutableBaseSha", "status", "currentHead", "sealedRevisions", "candidates", "seenEvents", "stopReason"}
        if set(payload) != expected or payload.get("schemaVersion") != 2:
            raise StateError("invalid_lifecycle_serialization", "lifecycle schema is incomplete or has unknown fields")
        return cls(
            repository=payload["repository"], phase_id=payload["phaseId"], phase_branch=payload["phaseBranch"],
            immutable_base_sha=payload["immutableBaseSha"], status=payload["status"], current_head=payload["currentHead"],
            sealed_revisions=payload["sealedRevisions"],
            candidates={key: CandidateRecord.from_dict(value) for key, value in payload["candidates"].items()},
            seen_events=tuple(payload["seenEvents"]), stop_reason=payload["stopReason"],
        )


@dataclass(frozen=True)
class LifecycleOutcome:
    code: str
    status: str
    candidate_id: str | None = None
    dispatch: Mapping[str, Any] | None = None
    detail: str = ""
    changed: bool = False

    @property
    def outcome_code(self) -> str:
        return self.code

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code, "status": self.status, "candidateId": self.candidate_id,
            "dispatch": dict(self.dispatch) if self.dispatch is not None else None,
            "detail": self.detail, "changed": self.changed,
        }


def concurrency_key(repository: str, workflow: str, pr_number: int) -> str:
    """Return a readable, deterministic key whose cancellation scope is one PR."""
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", repository):
        raise StateError("invalid_repository", "repository must be owner/name")
    if not isinstance(workflow, str) or not workflow.strip() or "/" in workflow or "\\" in workflow:
        raise StateError("invalid_workflow", "workflow must be a non-empty name")
    if isinstance(pr_number, bool) or not isinstance(pr_number, int) or pr_number < 1:
        raise StateError("invalid_pr_number", "prNumber must be a positive integer")
    return f"{repository}|{workflow.strip()}|pr-{pr_number}"


def _p2_event_name(event: Mapping[str, Any]) -> str:
    name = event.get("type", event.get("event", event.get("name")))
    if not isinstance(name, str) or not name.strip():
        raise StateError("invalid_event", "event object requires type")
    return name.strip().lower().replace("_", "-")


def _p2_event_id(event: Mapping[str, Any]) -> str:
    supplied = event.get("eventId", event.get("id"))
    if supplied is not None:
        return _p2_text(supplied, "eventId")
    payload = {key: event[key] for key in sorted(event) if key not in {"eventId", "id"}}
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _p2_candidate(state: CandidateLifecycleState, event: Mapping[str, Any]) -> CandidateRecord | None:
    candidate_id = event.get("candidateId")
    if not isinstance(candidate_id, str):
        return None
    return state.candidates.get(candidate_id)


def _p2_replace_candidate(state: CandidateLifecycleState, record: CandidateRecord) -> CandidateLifecycleState:
    candidates = dict(state.candidates)
    candidates[record.candidate_id] = record
    return replace(state, candidates=candidates)


def _p2_supersede_for_pr(state: CandidateLifecycleState, *, pr_number: int, source_branch: str, except_id: str | None = None) -> CandidateLifecycleState:
    """Supersede older work for one PR without affecting another PR's key."""
    candidates = dict(state.candidates)
    for candidate_id, record in candidates.items():
        if candidate_id == except_id or record.seal.pr_number != pr_number or record.seal.source_branch != source_branch:
            continue
        if record.status in P2_TERMINAL_CANDIDATE_STATES:
            continue
        checks = {name: {**value, "status": "invalidated"} for name, value in record.checks.items()}
        candidates[candidate_id] = replace(record, status="superseded", invalidated=True, checks=checks, stop_reason="newer_head_commit")
    return replace(state, candidates=candidates)


def _p2_invalidate_older_candidates(state: CandidateLifecycleState, *, head_commit: str) -> CandidateLifecycleState:
    """Invalidate every non-terminal candidate whose exact head is older.

    The state reducer owns candidate validity for the Phase.  Workflow
    cancellation remains scoped by ``repository|workflow|PR`` through
    ``concurrency_key``; invalidating a stale candidate here does not cancel a
    different PR's workflow key.
    """
    candidates = dict(state.candidates)
    for candidate_id, record in candidates.items():
        if record.seal.head_commit == head_commit or record.status in P2_TERMINAL_CANDIDATE_STATES:
            continue
        checks = {name: {**value, "status": "invalidated"} for name, value in record.checks.items()}
        candidates[candidate_id] = replace(
            record,
            status="superseded",
            invalidated=True,
            checks=checks,
            stop_reason="newer_head_commit",
        )
    return replace(state, candidates=candidates)


def _p2_assert_event_identity(state: CandidateLifecycleState, event: Mapping[str, Any]) -> None:
    """Reject an event addressed to another repository, phase, or branch."""
    for key, expected in (
        ("repository", state.repository),
        ("phaseId", state.phase_id),
        ("phaseBranch", state.phase_branch),
        ("sourceBranch", state.phase_branch),
        ("branch", state.phase_branch),
        ("immutableBaseSha", state.immutable_base_sha),
        ("baseSha", state.immutable_base_sha),
    ):
        if key in event and event[key] != expected:
            raise StateError("stale_identity", f"{key} does not match current lifecycle")


class CandidateLifecycle:
    """Pure W1-P2 event reducer; no GitHub or workflow side effects."""

    def __init__(self, state: CandidateLifecycleState):
        self.state = state

    @classmethod
    def new(cls, repository: str, phase_id: str, phase_branch: str, immutable_base_sha: str) -> "CandidateLifecycle":
        return cls(CandidateLifecycleState.new(repository, phase_id, phase_branch, immutable_base_sha))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CandidateLifecycle":
        return cls(CandidateLifecycleState.from_dict(payload))

    def to_dict(self) -> dict[str, Any]:
        return self.state.to_dict()

    def _outcome(self, code: str, *, candidate_id: str | None = None, dispatch: Mapping[str, Any] | None = None, detail: str = "", changed: bool = False) -> LifecycleOutcome:
        return LifecycleOutcome(code, self.state.status, candidate_id, dispatch, detail, changed)

    def apply(self, event: Mapping[str, Any]) -> LifecycleOutcome:
        """Apply an event exactly once and return a plain, workflow-safe outcome."""
        if not isinstance(event, Mapping):
            raise StateError("invalid_event", "event must be an object")
        name = _p2_event_name(event)
        event_id = _p2_event_id(event)
        if event_id in self.state.seen_events:
            return self._outcome(OUTCOME_DUPLICATE_IGNORED, candidate_id=event.get("candidateId"), detail="event already applied")
        if self.state.status in P2_PHASE_TERMINAL_STATES:
            self.state = replace(self.state, seen_events=self.state.seen_events + (event_id,))
            return self._outcome(OUTCOME_STOPPED_ALERT, detail=self.state.stop_reason or "phase is terminal")

        _p2_assert_event_identity(self.state, event)
        old_state = self.state
        candidate = _p2_candidate(old_state, event)
        if name in {"checkpoint", "checkpoint-pushed", "head-updated"}:
            head = event.get("headCommit", event.get("head"))
            _sha(head, field_name="headCommit")
            branch = event.get("sourceBranch", event.get("branch"),)
            if branch is not None and not isinstance(branch, str):
                raise StateError("invalid_event", "sourceBranch must be a string")
            state = replace(old_state, current_head=head, status="checkpointed", seen_events=old_state.seen_events + (event_id,))
            superseded_ids = {
                candidate_id
                for candidate_id, record in old_state.candidates.items()
                if record.seal.head_commit != head and record.status not in P2_TERMINAL_CANDIDATE_STATES
            }
            if head != old_state.current_head:
                state = _p2_invalidate_older_candidates(state, head_commit=head)
            self.state = state
            code = OUTCOME_CANDIDATE_SUPERSEDED if superseded_ids else OUTCOME_CHECKPOINT_RECORDED
            candidate_id = sorted(superseded_ids)[-1] if superseded_ids else None
            return self._outcome(code, candidate_id=candidate_id, detail=OUTCOME_NO_DISPATCH, changed=state != old_state)

        if name in {"integrating", "phase-integrating"}:
            self.state = replace(old_state, status="integrating", seen_events=old_state.seen_events + (event_id,))
            return self._outcome(OUTCOME_NO_DISPATCH, detail="integration state recorded", changed=True)
        if name in {"draft-phase-pr", "draft-pr-created", "phase-pr-opened"}:
            self.state = replace(old_state, status="draft-phase-pr", seen_events=old_state.seen_events + (event_id,))
            return self._outcome(OUTCOME_NO_DISPATCH, detail="draft Phase PR recorded", changed=True)

        if name in {"seal", "sealed-candidate", "candidate-sealed"}:
            identity_payload = event.get("candidateIdentity", event.get("identity"))
            if not isinstance(identity_payload, Mapping):
                raise StateError("invalid_seal", "seal requires candidateIdentity")
            identity = PhaseCandidateIdentity.from_dict(identity_payload)
            seal = CandidateSeal(
                repository=event.get("repository", old_state.repository),
                pr_number=event.get("prNumber"),
                source_branch=event.get("sourceBranch", identity.source_branch),
                head_commit=event.get("headCommit", identity.head_commit),
                identity=identity,
            )
            if identity.repository != old_state.repository or identity.source_branch != old_state.phase_branch:
                raise StateError("stale_identity", "candidate identity does not match lifecycle repository or branch")
            if old_state.current_head != seal.head_commit:
                raise StateError("stale_seal", "seal must bind to current Phase head")
            if seal.candidate_id in old_state.candidates:
                self.state = replace(old_state, seen_events=old_state.seen_events + (event_id,))
                return self._outcome(OUTCOME_DUPLICATE_IGNORED, candidate_id=seal.candidate_id, detail="candidate already sealed")
            if old_state.sealed_revisions >= 2:
                self.state = replace(old_state, status="stopped-alert", stop_reason="maximum sealed candidate revisions reached", seen_events=old_state.seen_events + (event_id,))
                return self._outcome(OUTCOME_HOLD_SEALED_CANDIDATE_LIMIT, candidate_id=seal.candidate_id, detail="third sealed candidate requires HOLD/Principal decision", changed=True)
            state = _p2_supersede_for_pr(old_state, pr_number=seal.pr_number, source_branch=seal.source_branch)
            record = CandidateRecord(seal=seal)
            candidates = dict(state.candidates)
            candidates[seal.candidate_id] = record
            self.state = replace(state, status="sealed-candidate", sealed_revisions=state.sealed_revisions + 1, candidates=candidates, seen_events=state.seen_events + (event_id,))
            return self._outcome(OUTCOME_CANDIDATE_SEALED, candidate_id=seal.candidate_id, detail="sealed candidate is compute-eligible", changed=True)

        if name in {"cancel", "cancelled", "candidate-cancelled"}:
            if candidate is None:
                self.state = replace(old_state, seen_events=old_state.seen_events + (event_id,))
                return self._outcome(OUTCOME_OUT_OF_ORDER, detail="candidate is not known")
            if candidate.status in P2_TERMINAL_CANDIDATE_STATES:
                self.state = replace(old_state, seen_events=old_state.seen_events + (event_id,))
                return self._outcome(OUTCOME_DUPLICATE_IGNORED, candidate_id=candidate.candidate_id, detail="candidate already terminal")
            self.state = _p2_replace_candidate(replace(old_state, seen_events=old_state.seen_events + (event_id,)), replace(candidate, status="cancelled", stop_reason="cancelled"))
            return self._outcome(OUTCOME_CANCELLED, candidate_id=candidate.candidate_id, changed=True)

        if name in {"check-started", "job-started", "execution-started"}:
            if candidate is None or candidate.invalidated or candidate.status in P2_TERMINAL_CANDIDATE_STATES:
                self.state = replace(old_state, seen_events=old_state.seen_events + (event_id,))
                return self._outcome(OUTCOME_LATE_RESULT_REJECTED, candidate_id=event.get("candidateId"), detail="candidate is no longer active")
            check = event.get("check", event.get("gate", "fast"))
            if check == "fast-gate":
                check = "fast"
            if check not in P2_CHECKS:
                raise StateError("invalid_check", "check must be fast, full, or review")
            if candidate.seal.head_commit != old_state.current_head:
                self.state = replace(old_state, seen_events=old_state.seen_events + (event_id,))
                return self._outcome(OUTCOME_LATE_RESULT_REJECTED, candidate_id=candidate.candidate_id, detail="candidate head is stale")
            current_check = candidate.checks.get(check, {})
            if current_check.get("status") in {"running", "success"}:
                self.state = replace(old_state, seen_events=old_state.seen_events + (event_id,))
                return self._outcome(OUTCOME_OUT_OF_ORDER, candidate_id=candidate.candidate_id, detail="check has already started or passed")
            if candidate.attempts >= 2:
                self.state = replace(old_state, seen_events=old_state.seen_events + (event_id,))
                return self._outcome(OUTCOME_STOPPED_ALERT, candidate_id=candidate.candidate_id, detail="candidate attempt limit reached")
            if candidate.status == "infrastructure-retry":
                failed_checks = [
                    name for name, result in candidate.checks.items()
                    if result.get("status") == "failed" and result.get("failureClass") == "infrastructure"
                ]
                if failed_checks != [check]:
                    self.state = replace(old_state, seen_events=old_state.seen_events + (event_id,))
                    return self._outcome(OUTCOME_OUT_OF_ORDER, candidate_id=candidate.candidate_id, detail="retry must resume the failed check")
                attempt = candidate.attempts + 1
            elif candidate.attempts == 0:
                attempt = 1
            else:
                # Fast, full, and review checks share one exact candidate
                # attempt.  A later gate in the same run must not consume a
                # second retry budget.
                attempt = candidate.attempts
            if check == "full" and candidate.checks.get("fast", {}).get("status") != "success":
                self.state = replace(old_state, seen_events=old_state.seen_events + (event_id,))
                return self._outcome(OUTCOME_OUT_OF_ORDER, candidate_id=candidate.candidate_id, detail="full check requires fast success")
            if check == "review" and candidate.checks.get("full", {}).get("status") != "success":
                self.state = replace(old_state, seen_events=old_state.seen_events + (event_id,))
                return self._outcome(OUTCOME_OUT_OF_ORDER, candidate_id=candidate.candidate_id, detail="review requires full success")
            next_status = {"fast": "fast-checking", "full": "full-checking", "review": "review-checking"}[check]
            checks = dict(candidate.checks)
            checks[check] = {"status": "running", "attempt": attempt}
            self.state = _p2_replace_candidate(replace(old_state, status=next_status, seen_events=old_state.seen_events + (event_id,)), replace(candidate, status=next_status, attempts=attempt, checks=checks, stop_reason=None))
            return self._outcome(OUTCOME_NO_DISPATCH, candidate_id=candidate.candidate_id, detail=f"{check} check started", changed=True)

        if name in {"check-completed", "check-result", "gate-result", "job-result", "execution-completed"}:
            if candidate is None or candidate.invalidated or candidate.status in P2_TERMINAL_CANDIDATE_STATES:
                self.state = replace(old_state, seen_events=old_state.seen_events + (event_id,))
                return self._outcome(OUTCOME_LATE_RESULT_REJECTED, candidate_id=event.get("candidateId"), detail="late result for superseded candidate")
            if candidate.seal.head_commit != old_state.current_head:
                self.state = replace(old_state, seen_events=old_state.seen_events + (event_id,))
                return self._outcome(OUTCOME_LATE_RESULT_REJECTED, candidate_id=candidate.candidate_id, detail="result head is stale")
            check = event.get("check", event.get("gate", "fast"))
            if check == "fast-gate":
                check = "fast"
            if check not in P2_CHECKS:
                raise StateError("invalid_check", "check must be fast, full, or review")
            current_check = candidate.checks.get(check, {})
            if current_check.get("status") != "running":
                self.state = replace(old_state, seen_events=old_state.seen_events + (event_id,))
                return self._outcome(OUTCOME_OUT_OF_ORDER, candidate_id=candidate.candidate_id, detail="result arrived before matching start")
            conclusion = str(event.get("conclusion", event.get("result", ""))).lower()
            failure_class = str(event.get("failureClass", event.get("failureType", ""))).lower()
            if failure_class in {"code", "test", "code-failure", "test-failure"} or conclusion in {"failure-code", "code-failure", "test-failure", "failed-code"}:
                checks = dict(candidate.checks)
                checks[check] = {**current_check, "status": "failed", "failureClass": "code"}
                updated = replace(candidate, status="code-failed", checks=checks, stop_reason="code/test failure returns to development")
                self.state = _p2_replace_candidate(replace(old_state, status="code-failed", seen_events=old_state.seen_events + (event_id,)), updated)
                return self._outcome(OUTCOME_CODE_FAILURE, candidate_id=candidate.candidate_id, detail="no automatic retry; return to development", changed=True)
            if failure_class in {"infrastructure", "infra", "infrastructure-failure"} or conclusion in {"failure-infrastructure", "infrastructure-failure", "infra-failure"}:
                checks = dict(candidate.checks)
                checks[check] = {**current_check, "status": "failed", "failureClass": "infrastructure"}
                if candidate.attempts >= 2:
                    updated = replace(candidate, status="stopped-alert", checks=checks, stop_reason="two infrastructure attempts exhausted")
                    self.state = _p2_replace_candidate(replace(old_state, status="stopped-alert", stop_reason="two infrastructure attempts exhausted", seen_events=old_state.seen_events + (event_id,)), updated)
                    return self._outcome(OUTCOME_STOPPED_ALERT, candidate_id=candidate.candidate_id, detail="second infrastructure failure stops candidate", changed=True)
                updated = replace(candidate, status="infrastructure-retry", checks=checks, stop_reason="infrastructure failure; one retry available")
                self.state = _p2_replace_candidate(replace(old_state, status="infrastructure-retry", seen_events=old_state.seen_events + (event_id,)), updated)
                return self._outcome(OUTCOME_INFRASTRUCTURE_RETRY, candidate_id=candidate.candidate_id, dispatch={"action": "retry", "candidateId": candidate.candidate_id, "attempt": candidate.attempts + 1}, detail="exactly one retry remains", changed=True)
            if conclusion in {"failure", "failed"}:
                checks = dict(candidate.checks)
                checks[check] = {**current_check, "status": "failed", "failureClass": "code"}
                updated = replace(candidate, status="code-failed", checks=checks, stop_reason="code/test failure returns to development")
                self.state = _p2_replace_candidate(replace(old_state, status="code-failed", seen_events=old_state.seen_events + (event_id,)), updated)
                return self._outcome(OUTCOME_CODE_FAILURE, candidate_id=candidate.candidate_id, detail="no automatic retry; return to development", changed=True)
            if conclusion not in {"success", "passed", "successful"}:
                raise StateError("invalid_conclusion", "conclusion must be success, code-failure, or infrastructure-failure")
            checks = dict(candidate.checks)
            checks[check] = {**current_check, "status": "success"}
            next_status = "review-complete" if check == "review" else ("sealed-candidate" if check == "fast" else "sealed-candidate")
            updated = replace(candidate, status=next_status, checks=checks, stop_reason=None)
            self.state = _p2_replace_candidate(replace(old_state, status=next_status, seen_events=old_state.seen_events + (event_id,)), updated)
            return self._outcome(OUTCOME_CHECK_PASSED, candidate_id=candidate.candidate_id, detail=f"{check} check passed", changed=True)

        if name in {"eligibility", "eligibility-evaluated", "eligible"}:
            if candidate is None or candidate.status in P2_TERMINAL_CANDIDATE_STATES:
                self.state = replace(old_state, seen_events=old_state.seen_events + (event_id,))
                return self._outcome(OUTCOME_LATE_RESULT_REJECTED, candidate_id=event.get("candidateId"), detail="candidate is no longer eligible")
            target = str(event.get("target", "development")).lower()
            next_status = {"development": "development-eligible", "staging": "staging-eligible", "main": "main-eligible"}.get(target)
            if next_status is None or candidate.checks.get("review", {}).get("status") != "success":
                self.state = replace(old_state, seen_events=old_state.seen_events + (event_id,))
                return self._outcome(OUTCOME_OUT_OF_ORDER, candidate_id=candidate.candidate_id, detail="eligibility requires successful review")
            updated = replace(candidate, status=next_status)
            self.state = _p2_replace_candidate(replace(old_state, status=next_status, seen_events=old_state.seen_events + (event_id,)), updated)
            return self._outcome(OUTCOME_ELIGIBILITY_RECORDED, candidate_id=candidate.candidate_id, detail=target, changed=True)

        self.state = replace(old_state, seen_events=old_state.seen_events + (event_id,))
        return self._outcome(OUTCOME_OUT_OF_ORDER, detail=f"unsupported or out-of-order event: {name}")


class CandidateLifecycleStore:
    """Atomic, durable lifecycle persistence with a local advisory lock."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    def load(self) -> CandidateLifecycle:
        if not self.path.exists():
            raise StateError("state_missing", f"lifecycle state does not exist: {self.path}")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StateError("state_unreadable", str(exc)) from exc
        if not isinstance(payload, Mapping):
            raise StateError("state_unreadable", "lifecycle state JSON must be an object")
        return CandidateLifecycle.from_dict(payload)

    def save(self, lifecycle: CandidateLifecycle) -> Path:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(lifecycle.to_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8")
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        temp_path = Path(temporary)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            try:
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return path

    def apply(self, event: Mapping[str, Any]) -> LifecycleOutcome:
        try:
            import fcntl
        except ImportError:  # pragma: no cover - Windows has no fcntl
            fcntl = None
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            if fcntl is not None:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                lifecycle = self.load()
                outcome = lifecycle.apply(event)
                self.save(lifecycle)
                return outcome
            finally:
                if fcntl is not None:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
