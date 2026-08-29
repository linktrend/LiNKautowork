"""Pure exact-content identities and FullSuiteReceipt handling.

Receipt creation and verification are deliberately local and side-effect free:
they do not call GitHub, read credentials, mint installation tokens, or depend
on a custom GitHub App.  The later workflow boundary may use GitHub's built-in
``GITHUB_TOKEN`` with explicit least-privilege permissions; that boundary is not
part of this module.

The receipt schema is versioned independently of older W1-P2 receipts.  A
schemaVersion 1 receipt is rejected explicitly and is never silently trusted.
If a later workflow boundary needs GitHub metadata, its built-in
``GITHUB_TOKEN`` may be granted only the least privilege needed there (for
example ``actions: read``, ``checks: read``, and ``contents: read``).  This
pure module never consumes that token or any custom-App credential.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
SEMVER_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
GATES = frozenset({"fast-gate", "full-gate", "staging-gate", "release-gate"})
PROFILES = frozenset({"fast", "full", "release"})
RECOGNIZED_RUNNER_LABELS = frozenset({"ubuntu-24.04-arm"})
RECEIPT_SCHEMA_VERSION = 2
TRANSITION_RECEIPT_SCHEMA_VERSION = 1
REJECTION_CODES = frozenset(
    {
        "repository_mismatch",
        "head_mismatch",
        "gate_mismatch",
        "tree_mismatch",
        "dependency_mismatch",
        "profile_mismatch",
        "workflow_mismatch",
        "command_mismatch",
        "receipt_not_passed",
        "conclusion_not_success",
        "evidence_mismatch",
        "receipt_digest_mismatch",
        "run_mismatch",
        "attempt_mismatch",
        "superseded_head",
        "unknown_runner",
        "invalid_sha",
        "invalid_path",
        "invalid_receipt",
        "unsupported_version",
        "invalid_branch",
        "invalid_gate",
        "transition_invalid",
        "transition_digest_mismatch",
        "transition_identity_mismatch",
        "transition_tree_mismatch",
        "transition_target_mismatch",
        "transition_run_mismatch",
        "receipt_store_invalid",
    }
)


class ReceiptError(ValueError):
    """A fail-closed receipt or identity input error."""

    def __init__(self, code: str, message: str) -> None:
        if code not in REJECTION_CODES:
            raise ValueError(f"Unknown receipt error code: {code}")
        super().__init__(message)
        self.code = code


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _is_sha(value: Any) -> bool:
    candidate = _string(value)
    return bool(SHA_RE.fullmatch(candidate)) and set(candidate) != {"0"}


def _is_digest(value: Any) -> bool:
    return bool(SHA256_RE.fullmatch(_string(value)))


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    """Return the one canonical byte representation used for all digests."""

    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
        + b"\n"
    )


def canonical_digest(payload: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        converted = value.to_dict()
        if isinstance(converted, Mapping):
            return dict(converted)
    raise ReceiptError("invalid_receipt", "expected a JSON object")


def _git(repo: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", *args], cwd=str(repo), check=False, capture_output=True, text=True
    )
    if process.returncode != 0:
        detail = (process.stderr or "").strip().replace("\n", " ")[:300]
        raise ReceiptError("invalid_receipt", f"git command failed: {detail}")
    return (process.stdout or "").strip()


def _repository_name(repo: Path) -> str:
    try:
        remote = _git(repo, "config", "--get", "remote.origin.url")
    except ReceiptError:
        remote = ""
    if remote:
        candidate = remote.strip()
        if ":" in candidate and "//" not in candidate:
            candidate = candidate.rsplit(":", 1)[1]
        else:
            parsed = urlparse(candidate)
            candidate = parsed.path if parsed.path else candidate
        candidate = candidate.strip("/")
        if candidate.endswith(".git"):
            candidate = candidate[:-4]
        parts = [part for part in candidate.split("/") if part]
        if len(parts) >= 2 and all(re.fullmatch(r"[A-Za-z0-9_.-]+", item) for item in parts[-2:]):
            return f"{parts[-2]}/{parts[-1]}"
    name = repo.name or "repository"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ReceiptError("invalid_receipt", "repository name is not representable")
    return f"local/{name}"


def _repo_root(repo_path: str | os.PathLike[str] | Path) -> Path:
    repo = Path(repo_path)
    if not repo.exists() or not repo.is_dir() or repo.is_symlink():
        raise ReceiptError("invalid_path", "repository path must be a real directory")
    try:
        root = repo.resolve(strict=True)
    except OSError as exc:
        raise ReceiptError("invalid_path", "repository path cannot be resolved") from exc
    if not (root / ".git").exists():
        raise ReceiptError("invalid_path", "path is not a Git repository")
    return root


def _normal_relative_path(raw: Any) -> str:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise ReceiptError("invalid_path", "path must be a non-empty POSIX relative path")
    path = PurePosixPath(raw)
    if raw.startswith(("/", "~")) or ":" in raw or ".." in path.parts:
        raise ReceiptError("invalid_path", f"path is not relative: {raw!r}")
    if not path.parts or path == PurePosixPath(".") or any(part in {"", "."} for part in path.parts):
        raise ReceiptError("invalid_path", f"path is not canonical: {raw!r}")
    normalized = path.as_posix()
    if normalized != raw:
        raise ReceiptError("invalid_path", f"path is not canonical: {raw!r}")
    return normalized


def _file_bytes(repo: Path, relative: str) -> bytes:
    candidate = repo.joinpath(*PurePosixPath(relative).parts)
    current = repo
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ReceiptError("invalid_path", f"path contains a symlink: {relative}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(repo)
        mode = os.stat(candidate, follow_symlinks=False).st_mode
    except (OSError, ValueError) as exc:
        raise ReceiptError("invalid_path", f"file is unavailable or escapes repository: {relative}") from exc
    if not stat.S_ISREG(mode):
        raise ReceiptError("invalid_path", f"path is not a regular file: {relative}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(candidate), flags)
    except OSError as exc:
        raise ReceiptError("invalid_path", f"file cannot be opened: {relative}") from exc
    try:
        if os.path.islink(candidate):
            raise ReceiptError("invalid_path", f"file became a symlink: {relative}")
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            return handle.read()
    finally:
        if fd >= 0:
            os.close(fd)


def _normalized_files(files: Sequence[str] | str | None) -> list[str]:
    if files is None:
        return []
    if isinstance(files, str):
        files = (files,)
    normalized = [_normal_relative_path(value) for value in files]
    if len(set(normalized)) != len(normalized):
        raise ReceiptError("invalid_path", "declared paths must be unique")
    return sorted(normalized)


def _file_digest_map(repo: Path, files: Sequence[str] | str | None) -> dict[str, str]:
    return {
        relative: "sha256:" + hashlib.sha256(_file_bytes(repo, relative)).hexdigest()
        for relative in _normalized_files(files)
    }


def _declared_workflows(repo: Path) -> list[str]:
    try:
        paths = _git(repo, "ls-tree", "-r", "--name-only", "HEAD", "--", ".github/workflows").splitlines()
    except ReceiptError:
        return []
    return sorted(path for path in paths if path.endswith((".yml", ".yaml")))


def _profile_digest(
    repo: Path,
    profile: str,
    profile_files: Sequence[str] | str | None,
    profile_bytes: bytes | str | Mapping[str, Any] | None,
) -> str:
    files = _file_digest_map(repo, profile_files)
    if profile_bytes is None:
        value: Any = {"profile": profile, "files": files}
    elif isinstance(profile_bytes, bytes):
        value = {"profile": profile, "bytesDigest": "sha256:" + hashlib.sha256(profile_bytes).hexdigest(), "files": files}
    elif isinstance(profile_bytes, str):
        value = {"profile": profile, "bytesDigest": "sha256:" + hashlib.sha256(profile_bytes.encode("utf-8")).hexdigest(), "files": files}
    else:
        value = {"profile": profile, "definition": dict(profile_bytes), "files": files}
    return canonical_digest(value)


def _workflow_digest(
    repo: Path,
    workflow_files: Sequence[str] | str | None,
    workflow_bytes: bytes | str | Mapping[str, Any] | None,
) -> str:
    files = _declared_workflows(repo) if workflow_files is None else _normalized_files(workflow_files)
    file_digests = _file_digest_map(repo, files)
    if workflow_bytes is None:
        value: Any = {"files": file_digests}
    elif isinstance(workflow_bytes, bytes):
        value = {"bytesDigest": "sha256:" + hashlib.sha256(workflow_bytes).hexdigest(), "files": file_digests}
    elif isinstance(workflow_bytes, str):
        value = {"bytesDigest": "sha256:" + hashlib.sha256(workflow_bytes.encode("utf-8")).hexdigest(), "files": file_digests}
    else:
        value = {"definition": dict(workflow_bytes), "files": file_digests}
    return canonical_digest(value)


@dataclass(frozen=True)
class CandidateIdentity:
    repository: str
    source_branch: str
    head_commit: str
    git_tree: str
    dependency_digest: str
    profile_digest: str
    workflow_digest: str
    _dependency_files: dict[str, str] = field(default_factory=dict, repr=False, compare=False)
    _test_profile: str = field(default="full", repr=False, compare=False)

    @property
    def source_sha(self) -> str:
        return self.head_commit

    @property
    def git_tree_sha(self) -> str:
        return self.git_tree

    @property
    def dependency_digests(self) -> dict[str, str]:
        """Return declared file digests for callers of the W1-P2 API.

        The v2 wire shape stores the canonical aggregate ``dependencyDigest``
        in the receipt identity.  Computed identities retain the individual
        entries as a compatibility view for older coordinator callers.
        """

        return dict(self._dependency_files) or {"declared": self.dependency_digest}

    @property
    def test_profile(self) -> str:
        return self._test_profile

    def to_dict(self) -> dict[str, Any]:
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
    def from_dict(cls, value: Any) -> "CandidateIdentity":
        data = _mapping(value)
        expected = {"repository", "sourceBranch", "headCommit", "gitTree", "dependencyDigest", "profileDigest", "workflowDigest"}
        if set(data) != expected:
            raise ReceiptError("invalid_receipt", "candidate identity fields are incomplete or unknown")
        repository = data["repository"]
        branch = data["sourceBranch"]
        if not isinstance(repository, str) or not re.fullmatch(r"[^/\s]+/[^/\s]+", repository):
            raise ReceiptError("invalid_receipt", "repository must be owner/name")
        if not isinstance(branch, str) or not branch or not BRANCH_RE.fullmatch(branch) or ".." in branch:
            raise ReceiptError("invalid_branch", "candidate sourceBranch is invalid")
        if not _is_sha(data["headCommit"]) or not _is_sha(data["gitTree"]):
            raise ReceiptError("invalid_sha", "candidate identity contains a malformed commit or tree SHA")
        for field in ("dependencyDigest", "profileDigest", "workflowDigest"):
            if not _is_digest(data[field]):
                raise ReceiptError("invalid_receipt", f"candidate identity {field} is invalid")
        return cls(
            repository,
            branch,
            data["headCommit"],
            data["gitTree"],
            data["dependencyDigest"],
            data["profileDigest"],
            data["workflowDigest"],
        )


def compute_candidate_identity(
    repo_path: str | os.PathLike[str] | Path,
    dependency_files: Sequence[str] | str | None = None,
    test_profile: str = "full",
    *,
    profile_files: Sequence[str] | str | None = None,
    workflow_files: Sequence[str] | str | None = None,
    profile_bytes: bytes | str | Mapping[str, Any] | None = None,
    workflow_bytes: bytes | str | Mapping[str, Any] | None = None,
    source_branch: str | None = None,
) -> CandidateIdentity:
    """Compute the frozen identity from Git and canonical declared bytes."""

    if test_profile not in PROFILES:
        raise ReceiptError("profile_mismatch", f"unknown test profile: {test_profile!r}")
    repo = _repo_root(repo_path)
    head = _git(repo, "rev-parse", "HEAD").lower()
    tree = _git(repo, "rev-parse", "HEAD^{tree}").lower()
    if not _is_sha(head) or not _is_sha(tree):
        raise ReceiptError("invalid_sha", "Git returned a malformed commit or tree SHA")
    branch = source_branch or _git(repo, "branch", "--show-current") or "detached"
    if not isinstance(branch, str) or not BRANCH_RE.fullmatch(branch) or ".." in branch:
        raise ReceiptError("invalid_branch", "Git source branch is invalid")
    dependency_map = _file_digest_map(repo, dependency_files)
    dependency_digest = canonical_digest({"files": dependency_map})
    return CandidateIdentity(
        repository=_repository_name(repo),
        source_branch=branch,
        head_commit=head,
        git_tree=tree,
        dependency_digest=dependency_digest,
        profile_digest=_profile_digest(repo, test_profile, profile_files, profile_bytes),
        workflow_digest=_workflow_digest(repo, workflow_files, workflow_bytes),
        _dependency_files=dependency_map,
        _test_profile=test_profile,
    )


CANDIDATE_IDENTITY_FIELDS = frozenset({"repository", "sourceBranch", "headCommit", "gitTree", "dependencyDigest", "profileDigest", "workflowDigest"})
RECEIPT_FIELDS = frozenset({
    "schemaVersion", "candidateIdentity", "workflowRunId", "workflowRunAttempt", "runnerLabel",
    "startedAt", "completedAt", "conclusion", "commandDigest", "evidenceDigests", "receiptDigest",
})


def _parse_digest_map(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ReceiptError("invalid_receipt", "evidenceDigests must be an object")
    result: dict[str, str] = {}
    for raw_path, digest in value.items():
        try:
            path = _normal_relative_path(raw_path)
        except ReceiptError as exc:
            raise ReceiptError("evidence_mismatch", "evidence path is invalid") from exc
        if not _is_digest(digest):
            raise ReceiptError("evidence_mismatch", "invalid evidence digest")
        result[path] = digest
    if len(result) != len(value):
        raise ReceiptError("evidence_mismatch", "evidence paths must be unique")
    return dict(sorted(result.items()))


@dataclass(frozen=True)
class FullSuiteReceipt:
    schema_version: int
    candidate_identity: CandidateIdentity
    workflow_run_id: int
    workflow_run_attempt: int
    runner_label: str
    started_at: str
    completed_at: str
    conclusion: str
    command_digest: str
    evidence_digests: dict[str, str]
    receipt_digest: str

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schemaVersion": self.schema_version,
            "candidateIdentity": self.candidate_identity.to_dict(),
            "workflowRunId": self.workflow_run_id,
            "workflowRunAttempt": self.workflow_run_attempt,
            "runnerLabel": self.runner_label,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "conclusion": self.conclusion,
            "commandDigest": self.command_digest,
            "evidenceDigests": dict(sorted(self.evidence_digests.items())),
        }
        if include_digest:
            result["receiptDigest"] = self.receipt_digest
        return result

    @classmethod
    def from_dict(cls, value: Any, *, allow_missing_digest: bool = False) -> "FullSuiteReceipt":
        data = _mapping(value)
        version = data.get("schemaVersion")
        if version != RECEIPT_SCHEMA_VERSION:
            if version == 1:
                raise ReceiptError("unsupported_version", "schemaVersion 1 receipts are unsupported; migrate to FullSuiteReceipt schemaVersion 2")
            raise ReceiptError("unsupported_version", "unsupported FullSuiteReceipt schemaVersion")
        expected = set(RECEIPT_FIELDS)
        if allow_missing_digest:
            expected.remove("receiptDigest")
        if set(data) != expected and not (allow_missing_digest and set(data) == expected | {"receiptDigest"}):
            raise ReceiptError("invalid_receipt", "receipt fields are incomplete or unknown")
        identity = CandidateIdentity.from_dict(data.get("candidateIdentity"))
        run_id = data.get("workflowRunId")
        attempt = data.get("workflowRunAttempt")
        if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id < 1:
            raise ReceiptError("run_mismatch", "workflowRunId must be a positive integer")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise ReceiptError("attempt_mismatch", "workflowRunAttempt must be a positive integer")
        runner = data.get("runnerLabel")
        if runner not in RECOGNIZED_RUNNER_LABELS:
            raise ReceiptError("unknown_runner", "runnerLabel is not recognized")
        for field in ("startedAt", "completedAt"):
            if not isinstance(data.get(field), str) or not TIMESTAMP_RE.fullmatch(data[field]):
                raise ReceiptError("invalid_receipt", f"{field} must be RFC3339 UTC")
        conclusion = data.get("conclusion")
        if conclusion != "success":
            raise ReceiptError("conclusion_not_success", "only successful workflow conclusions are reusable")
        if not _is_digest(data.get("commandDigest")):
            raise ReceiptError("invalid_receipt", "commandDigest is invalid")
        evidence = _parse_digest_map(data.get("evidenceDigests"))
        digest = data.get("receiptDigest", "")
        if digest and not _is_digest(digest):
            raise ReceiptError("receipt_digest_mismatch", "receiptDigest is invalid")
        return cls(RECEIPT_SCHEMA_VERSION, identity, run_id, attempt, runner, data["startedAt"], data["completedAt"], conclusion, data["commandDigest"], evidence, digest)


TRANSITION_TYPES = frozenset({"protected-merge", "receipt-maintenance"})


@dataclass(frozen=True)
class TransitionReceipt:
    """Digest-bound bridge from an audited candidate to a protected ref.

    The FullSuiteReceipt remains bound to the exact workflow head.  This
    separate, externally retainable object is the only authority that permits
    a protected merge to change the commit identity while retaining the exact
    audited tree and execution identity.
    """

    schema_version: int
    kind: str
    transition_type: str
    repository: str
    source_identity: CandidateIdentity
    source_receipt_digest: str
    source_workflow_run_id: int
    source_workflow_run_attempt: int
    target_branch: str
    target_commit: str
    target_tree: str
    authenticated_by: str
    maintenance_paths: tuple[str, ...] = ()
    failure_contract_digest: str | None = None
    protected_base_commit: str | None = None
    receipt_digest: str = ""

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schemaVersion": self.schema_version,
            "kind": self.kind,
            "transitionType": self.transition_type,
            "repository": self.repository,
            "sourceIdentity": self.source_identity.to_dict(),
            "sourceReceiptDigest": self.source_receipt_digest,
            "sourceWorkflowRunId": self.source_workflow_run_id,
            "sourceWorkflowRunAttempt": self.source_workflow_run_attempt,
            "targetBranch": self.target_branch,
            "targetCommit": self.target_commit,
            "targetTree": self.target_tree,
            "authenticatedBy": self.authenticated_by,
            "maintenancePaths": list(self.maintenance_paths),
            "failureContractDigest": self.failure_contract_digest,
            "protectedBaseCommit": self.protected_base_commit,
        }
        if include_digest:
            result["receiptDigest"] = self.receipt_digest
        return result

    @classmethod
    def from_dict(cls, value: Any, *, allow_missing_digest: bool = False) -> "TransitionReceipt":
        data = _mapping(value)
        expected = {
            "schemaVersion", "kind", "transitionType", "repository", "sourceIdentity",
            "sourceReceiptDigest", "sourceWorkflowRunId", "sourceWorkflowRunAttempt",
            "targetBranch", "targetCommit", "targetTree", "authenticatedBy",
            "maintenancePaths", "failureContractDigest", "protectedBaseCommit", "receiptDigest",
        }
        allowed = expected - {"receiptDigest"} if allow_missing_digest else expected
        if set(data) != allowed and set(data) != expected:
            raise ReceiptError("transition_invalid", "transition receipt fields are incomplete or unknown")
        if data.get("schemaVersion") != TRANSITION_RECEIPT_SCHEMA_VERSION:
            raise ReceiptError("transition_invalid", "unsupported transition receipt schemaVersion")
        if data.get("kind") != "transition-receipt":
            raise ReceiptError("transition_invalid", "transition receipt kind is invalid")
        transition_type = data.get("transitionType")
        if transition_type not in TRANSITION_TYPES:
            raise ReceiptError("transition_invalid", "transitionType is invalid")
        source_identity = CandidateIdentity.from_dict(data.get("sourceIdentity"))
        repository = data.get("repository")
        if repository != source_identity.repository:
            raise ReceiptError("transition_identity_mismatch", "transition repository differs from source identity")
        source_digest = data.get("sourceReceiptDigest")
        if not _is_digest(source_digest):
            raise ReceiptError("transition_invalid", "sourceReceiptDigest is invalid")
        for name in ("sourceWorkflowRunId", "sourceWorkflowRunAttempt"):
            raw = data.get(name)
            if not isinstance(raw, int) or isinstance(raw, bool) or raw < 1:
                raise ReceiptError("transition_run_mismatch", f"{name} must be a positive integer")
        target_branch = data.get("targetBranch")
        if not isinstance(target_branch, str) or not target_branch or not BRANCH_RE.fullmatch(target_branch) or ".." in target_branch:
            raise ReceiptError("invalid_branch", "targetBranch is invalid")
        target_commit = data.get("targetCommit")
        target_tree = data.get("targetTree")
        if not _is_sha(target_commit) or not _is_sha(target_tree):
            raise ReceiptError("invalid_sha", "transition target commit/tree is invalid")
        if data.get("authenticatedBy") != "delivery-controller":
            raise ReceiptError("transition_invalid", "authenticatedBy must be delivery-controller")
        paths = data.get("maintenancePaths")
        if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
            raise ReceiptError("transition_invalid", "maintenancePaths must be an array of paths")
        normalized_paths = tuple(_normal_relative_path(path) for path in paths)
        if len(set(normalized_paths)) != len(normalized_paths):
            raise ReceiptError("transition_invalid", "maintenancePaths must be unique")
        failure_digest = data.get("failureContractDigest")
        if failure_digest is not None and not _is_digest(failure_digest):
            raise ReceiptError("transition_invalid", "failureContractDigest is invalid")
        base_commit = data.get("protectedBaseCommit")
        if base_commit is not None and not _is_sha(base_commit):
            raise ReceiptError("invalid_sha", "protectedBaseCommit is invalid")
        digest = data.get("receiptDigest", "")
        if digest and not _is_digest(digest):
            raise ReceiptError("transition_digest_mismatch", "transition receiptDigest is invalid")
        return cls(
            TRANSITION_RECEIPT_SCHEMA_VERSION,
            "transition-receipt",
            transition_type,
            repository,
            source_identity,
            source_digest,
            data["sourceWorkflowRunId"],
            data["sourceWorkflowRunAttempt"],
            target_branch,
            target_commit,
            target_tree,
            data["authenticatedBy"],
            normalized_paths,
            failure_digest,
            base_commit,
            digest,
        )


GateReceipt = FullSuiteReceipt


def compute_receipt_digest(receipt: FullSuiteReceipt | Mapping[str, Any]) -> str:
    parsed = receipt if isinstance(receipt, FullSuiteReceipt) else FullSuiteReceipt.from_dict(receipt, allow_missing_digest=True)
    return canonical_digest(parsed.to_dict(include_digest=False))


def compute_transition_digest(receipt: TransitionReceipt | Mapping[str, Any]) -> str:
    parsed = receipt if isinstance(receipt, TransitionReceipt) else TransitionReceipt.from_dict(receipt, allow_missing_digest=True)
    return canonical_digest(parsed.to_dict(include_digest=False))


def create_transition_receipt(
    source_receipt: FullSuiteReceipt | Mapping[str, Any],
    *,
    target_branch: str,
    target_commit: str,
    target_tree: str,
    transition_type: str = "protected-merge",
    authenticated_by: str = "delivery-controller",
    maintenance_paths: Sequence[str] = (),
    failure_contract_digest: str | None = None,
    protected_base_commit: str | None = None,
) -> TransitionReceipt:
    """Create the sole commit-changing bridge for an accepted Full receipt."""

    parsed = source_receipt if isinstance(source_receipt, FullSuiteReceipt) else FullSuiteReceipt.from_dict(source_receipt)
    _validate_receipt_digest(parsed)
    if transition_type not in TRANSITION_TYPES:
        raise ReceiptError("transition_invalid", "transitionType is invalid")
    if not isinstance(target_branch, str) or not target_branch or not BRANCH_RE.fullmatch(target_branch) or ".." in target_branch:
        raise ReceiptError("invalid_branch", "targetBranch is invalid")
    if not _is_sha(target_commit) or not _is_sha(target_tree):
        raise ReceiptError("invalid_sha", "transition target commit/tree is invalid")
    if target_tree != parsed.candidate_identity.git_tree:
        raise ReceiptError("transition_tree_mismatch", "protected target tree differs from audited tree")
    if authenticated_by != "delivery-controller":
        raise ReceiptError("transition_invalid", "authenticatedBy must be delivery-controller")
    paths = tuple(_normal_relative_path(path) for path in maintenance_paths)
    if len(set(paths)) != len(paths):
        raise ReceiptError("transition_invalid", "maintenancePaths must be unique")
    if failure_contract_digest is not None and not _is_digest(failure_contract_digest):
        raise ReceiptError("transition_invalid", "failureContractDigest is invalid")
    if protected_base_commit is not None and not _is_sha(protected_base_commit):
        raise ReceiptError("invalid_sha", "protectedBaseCommit is invalid")
    unsigned = TransitionReceipt(
        TRANSITION_RECEIPT_SCHEMA_VERSION,
        "transition-receipt",
        transition_type,
        parsed.candidate_identity.repository,
        parsed.candidate_identity,
        parsed.receipt_digest,
        parsed.workflow_run_id,
        parsed.workflow_run_attempt,
        target_branch,
        target_commit,
        target_tree,
        authenticated_by,
        tuple(sorted(paths)),
        failure_contract_digest,
        protected_base_commit,
        "",
    )
    return TransitionReceipt(**{**unsigned.__dict__, "receipt_digest": compute_transition_digest(unsigned)})


def verify_transition_receipt(
    transition_receipt: TransitionReceipt | Mapping[str, Any],
    source_receipt: FullSuiteReceipt | Mapping[str, Any],
    target_identity: CandidateIdentity | Mapping[str, Any],
    *,
    expected_workflow_run_id: int | None = None,
    expected_workflow_run_attempt: int | None = None,
    expected_base_commit: str | None = None,
) -> ReceiptVerdict:
    """Verify an authenticated same-tree transition and its current run."""

    try:
        transition = transition_receipt if isinstance(transition_receipt, TransitionReceipt) else TransitionReceipt.from_dict(transition_receipt)
        source = source_receipt if isinstance(source_receipt, FullSuiteReceipt) else FullSuiteReceipt.from_dict(source_receipt)
        target = target_identity if isinstance(target_identity, CandidateIdentity) else CandidateIdentity.from_dict(target_identity)
        _validate_receipt_digest(source)
        if transition.receipt_digest != compute_transition_digest(transition):
            raise ReceiptError("transition_digest_mismatch", "transition receiptDigest does not match canonical bytes")
        if transition.source_receipt_digest != source.receipt_digest:
            raise ReceiptError("transition_identity_mismatch", "transition does not reference the supplied Full receipt")
        if transition.source_workflow_run_id != source.workflow_run_id or transition.source_workflow_run_attempt != source.workflow_run_attempt:
            raise ReceiptError("transition_run_mismatch", "transition workflow run differs from the Full receipt")
        if expected_workflow_run_id is not None and source.workflow_run_id != expected_workflow_run_id:
            raise ReceiptError("run_mismatch", "transition workflow run does not match expected run")
        if expected_workflow_run_attempt is not None and source.workflow_run_attempt != expected_workflow_run_attempt:
            raise ReceiptError("attempt_mismatch", "transition workflow run attempt does not match expected attempt")
        if transition.repository != target.repository or transition.repository != source.candidate_identity.repository:
            raise ReceiptError("transition_identity_mismatch", "transition repository identity differs")
        if transition.source_identity.to_dict() != source.candidate_identity.to_dict():
            raise ReceiptError("transition_identity_mismatch", "transition source identity differs from Full receipt")
        if target.source_branch != transition.target_branch:
            raise ReceiptError("transition_target_mismatch", "transition target branch is not current protected ref")
        if target.head_commit != transition.target_commit or target.git_tree != transition.target_tree:
            raise ReceiptError("transition_target_mismatch", "transition target does not match current protected identity")
        if transition.target_tree != source.candidate_identity.git_tree:
            raise ReceiptError("transition_tree_mismatch", "transition changes the audited Git tree")
        if target.dependency_digest != source.candidate_identity.dependency_digest:
            raise ReceiptError("dependency_mismatch", "transition dependency identity changed")
        if target.profile_digest != source.candidate_identity.profile_digest:
            raise ReceiptError("profile_mismatch", "transition profile identity changed")
        if target.workflow_digest != source.candidate_identity.workflow_digest:
            raise ReceiptError("workflow_mismatch", "transition workflow identity changed")
        if expected_base_commit is not None and transition.protected_base_commit != expected_base_commit:
            raise ReceiptError("transition_target_mismatch", "transition protected base is stale")
        return ReceiptVerdict(True, message="authenticated same-tree transition matches", source_commit=source.candidate_identity.head_commit, promotion_commit=target.head_commit)
    except ReceiptError as error:
        return _reject(error)


def _validate_receipt_digest(receipt: FullSuiteReceipt) -> None:
    if receipt.receipt_digest != compute_receipt_digest(receipt):
        raise ReceiptError("receipt_digest_mismatch", "receiptDigest does not match canonical receipt bytes")


def create_full_suite_receipt(result: Mapping[str, Any]) -> FullSuiteReceipt:
    """Validate a successful workflow result and fill its deterministic digest."""

    data = dict(result)
    if data.get("schemaVersion") == 1:
        raise ReceiptError("unsupported_version", "schemaVersion 1 receipts are unsupported; migrate to FullSuiteReceipt schemaVersion 2")
    data.setdefault("schemaVersion", RECEIPT_SCHEMA_VERSION)
    data.pop("receiptDigest", None)
    parsed = FullSuiteReceipt.from_dict(data, allow_missing_digest=True)
    receipt = FullSuiteReceipt(**{**parsed.__dict__, "receipt_digest": compute_receipt_digest(parsed)})
    supplied = result.get("receiptDigest")
    if supplied is not None and supplied != receipt.receipt_digest:
        raise ReceiptError("receipt_digest_mismatch", "supplied receiptDigest does not match canonical receipt bytes")
    return receipt


def _atomic_write(path: Path, payload: bytes) -> None:
    if path.is_symlink():
        raise ReceiptError("invalid_path", "receipt destination must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if path.is_symlink():
            raise ReceiptError("invalid_path", "receipt destination became a symlink")
        os.replace(temporary_path, path)
    except Exception:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def write_receipt(result: Any, output_path: str | os.PathLike[str] | Path) -> FullSuiteReceipt:
    receipt = create_full_suite_receipt(_mapping(result))
    _atomic_write(Path(output_path), canonical_json_bytes(receipt.to_dict()))
    return receipt


def _git_common_dir(repo_path: str | os.PathLike[str] | Path) -> Path:
    repo = _repo_root(repo_path)
    value = _git(repo, "rev-parse", "--git-common-dir")
    common = Path(value)
    return common.resolve() if common.is_absolute() else (repo / common).resolve()


def validate_receipt_store_root(
    repo_path: str | os.PathLike[str] | Path,
    store_root: str | os.PathLike[str] | Path,
) -> Path:
    """Ensure evidence cannot be written into the candidate or Git metadata."""

    repo = _repo_root(repo_path)
    root = Path(store_root).expanduser().resolve()
    common = _git_common_dir(repo)
    if root == repo or repo in root.parents or root == common or common in root.parents:
        raise ReceiptError("receipt_store_invalid", "receipt store must be outside candidate and Git common directories")
    return root


def default_receipt_store_root(repo_path: str | os.PathLike[str] | Path) -> Path:
    """Return the external store used when a caller does not provide one."""

    configured = os.environ.get("LINKTREND_RECEIPT_STORE", "").strip()
    root = Path(configured).expanduser() if configured else Path.home() / ".linktrend" / "ide-coordinator" / "receipts"
    return validate_receipt_store_root(repo_path, root)


def store_receipt(
    receipt: FullSuiteReceipt | Mapping[str, Any],
    *,
    repo_path: str | os.PathLike[str] | Path,
    store_root: str | os.PathLike[str] | Path | None = None,
) -> Path:
    """Persist a Full receipt by immutable digest in an external store."""

    parsed = receipt if isinstance(receipt, FullSuiteReceipt) else FullSuiteReceipt.from_dict(receipt)
    _validate_receipt_digest(parsed)
    if parsed.candidate_identity.repository != _repository_name(_repo_root(repo_path)):
        raise ReceiptError("repository_mismatch", "receipt repository does not match evidence store repository")
    root = validate_receipt_store_root(repo_path, store_root or default_receipt_store_root(repo_path))
    destination = root / "full-suite" / f"{parsed.receipt_digest.removeprefix('sha256:')}.json"
    _atomic_write(destination, canonical_json_bytes(parsed.to_dict()))
    return destination


def store_transition_receipt(
    transition_receipt: TransitionReceipt | Mapping[str, Any],
    *,
    repo_path: str | os.PathLike[str] | Path,
    store_root: str | os.PathLike[str] | Path | None = None,
) -> Path:
    """Persist a transition receipt by immutable digest in an external store."""

    parsed = transition_receipt if isinstance(transition_receipt, TransitionReceipt) else TransitionReceipt.from_dict(transition_receipt)
    if parsed.receipt_digest != compute_transition_digest(parsed):
        raise ReceiptError("transition_digest_mismatch", "transition receiptDigest does not match canonical bytes")
    if parsed.repository != _repository_name(_repo_root(repo_path)):
        raise ReceiptError("repository_mismatch", "transition repository does not match evidence store repository")
    root = validate_receipt_store_root(repo_path, store_root or default_receipt_store_root(repo_path))
    destination = root / "transitions" / f"{parsed.receipt_digest.removeprefix('sha256:')}.json"
    _atomic_write(destination, canonical_json_bytes(parsed.to_dict()))
    return destination


@dataclass(frozen=True)
class ReceiptVerdict:
    accepted: bool
    rejection_code: str | None = None
    message: str = ""
    source_commit: str | None = None
    promotion_commit: str | None = None

    @property
    def ok(self) -> bool:
        return self.accepted

    @property
    def code(self) -> str:
        return "accepted" if self.accepted else (self.rejection_code or "invalid_receipt")

    def __bool__(self) -> bool:
        return self.accepted


def _reject(error: ReceiptError) -> ReceiptVerdict:
    return ReceiptVerdict(False, error.code, str(error))


def verify_receipt(
    receipt: Any,
    candidate_identity: Any,
    required_gate: str = "full-gate",
    *,
    workflow_run_id: int | None = None,
    workflow_run_attempt: int | None = None,
    workflow_head_commit: str | None = None,
    runner_label: str | None = None,
    expected_command_digest: str | None = None,
    expected_workflow_digest: str | None = None,
    expected_evidence_digests: Mapping[str, str] | None = None,
    transition_receipt: TransitionReceipt | Mapping[str, Any] | None = None,
) -> ReceiptVerdict:
    """Verify reusable identity without privileged credentials or network calls."""

    try:
        candidate = candidate_identity if isinstance(candidate_identity, CandidateIdentity) else CandidateIdentity.from_dict(candidate_identity)
        parsed = receipt if isinstance(receipt, FullSuiteReceipt) else FullSuiteReceipt.from_dict(receipt)
        _validate_receipt_digest(parsed)
        if required_gate != "full-gate":
            raise ReceiptError("gate_mismatch", "FullSuiteReceipt is reusable only for full-gate")
        if parsed.candidate_identity.repository != candidate.repository:
            raise ReceiptError("repository_mismatch", "receipt repository does not match candidate")
        receipt_identity = parsed.candidate_identity
        if receipt_identity.git_tree != candidate.git_tree:
            raise ReceiptError("tree_mismatch", "receipt Git tree does not match candidate")
        if receipt_identity.dependency_digest != candidate.dependency_digest:
            raise ReceiptError("dependency_mismatch", "receipt dependency identity does not match candidate")
        if receipt_identity.profile_digest != candidate.profile_digest:
            raise ReceiptError("profile_mismatch", "receipt profile identity does not match candidate")
        if receipt_identity.workflow_digest != candidate.workflow_digest:
            raise ReceiptError("workflow_mismatch", "receipt workflow identity does not match candidate")
        if transition_receipt is not None:
            transition_verdict = verify_transition_receipt(
                transition_receipt,
                parsed,
                candidate,
                expected_workflow_run_id=workflow_run_id,
                expected_workflow_run_attempt=workflow_run_attempt,
            )
            if not transition_verdict.accepted:
                rejection = transition_verdict.rejection_code or "transition_invalid"
                raise ReceiptError(rejection, transition_verdict.message or rejection)
        elif receipt_identity.head_commit != candidate.head_commit:
            raise ReceiptError("head_mismatch", "receipt commit does not match candidate")
        if workflow_run_id is not None and parsed.workflow_run_id != workflow_run_id:
            raise ReceiptError("run_mismatch", "receipt workflow run does not match expected run")
        if workflow_run_attempt is not None and parsed.workflow_run_attempt != workflow_run_attempt:
            raise ReceiptError("attempt_mismatch", "receipt workflow run attempt does not match expected attempt")
        if workflow_head_commit is not None:
            if not _is_sha(workflow_head_commit):
                raise ReceiptError("invalid_sha", "workflow head commit is malformed")
            if receipt_identity.head_commit != workflow_head_commit:
                raise ReceiptError("superseded_head", "workflow run head is superseded")
        if runner_label is not None and parsed.runner_label != runner_label:
            raise ReceiptError("unknown_runner", "receipt runner label does not match expected runner")
        if expected_command_digest is not None and parsed.command_digest != expected_command_digest:
            raise ReceiptError("command_mismatch", "receipt command identity does not match expected command")
        if expected_workflow_digest is not None and candidate.workflow_digest != expected_workflow_digest:
            raise ReceiptError("workflow_mismatch", "candidate workflow identity is not recognized")
        if expected_evidence_digests is not None:
            expected_evidence = _parse_digest_map(expected_evidence_digests)
            if parsed.evidence_digests != expected_evidence:
                raise ReceiptError("evidence_mismatch", "receipt evidence does not match expected evidence")
        return ReceiptVerdict(
            True,
            message="full-suite receipt identity matches",
            source_commit=receipt_identity.head_commit,
            promotion_commit=candidate.head_commit,
        )
    except ReceiptError as error:
        return _reject(error)


def receipt_lookup_key(receipt: FullSuiteReceipt | Mapping[str, Any]) -> str:
    """Return stable retention/lookup metadata needed through main promotion."""

    parsed = receipt if isinstance(receipt, FullSuiteReceipt) else FullSuiteReceipt.from_dict(receipt)
    _validate_receipt_digest(parsed)
    return f"{parsed.candidate_identity.repository}/{parsed.workflow_run_id}/{parsed.workflow_run_attempt}/{parsed.receipt_digest}"


def load_json(path: str | os.PathLike[str] | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReceiptError("invalid_receipt", f"invalid JSON input: {path}") from exc


__all__ = [
    "CANDIDATE_IDENTITY_FIELDS",
    "CandidateIdentity",
    "FullSuiteReceipt",
    "GateReceipt",
    "TransitionReceipt",
    "RECOGNIZED_RUNNER_LABELS",
    "TRANSITION_RECEIPT_SCHEMA_VERSION",
    "ReceiptError",
    "ReceiptVerdict",
    "canonical_digest",
    "canonical_json_bytes",
    "compute_candidate_identity",
    "compute_receipt_digest",
    "compute_transition_digest",
    "create_full_suite_receipt",
    "create_transition_receipt",
    "default_receipt_store_root",
    "load_json",
    "receipt_lookup_key",
    "store_receipt",
    "store_transition_receipt",
    "validate_receipt_store_root",
    "verify_receipt",
    "verify_transition_receipt",
    "write_receipt",
]
