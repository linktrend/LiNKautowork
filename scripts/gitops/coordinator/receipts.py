"""Exact-content candidate identities and gate receipts.

This module deliberately has no GitHub, container, or workflow dependency.  A
receipt is useful only when its content identity is independently recomputed
from the checkout that is about to be promoted.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SEMVER_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
GATES = frozenset({"fast-gate", "full-gate", "staging-gate", "release-gate"})
PROFILES = frozenset({"fast", "full", "release"})
REJECTION_CODES = frozenset(
    {
        "repository_mismatch",
        "gate_mismatch",
        "tree_mismatch",
        "dependency_mismatch",
        "profile_mismatch",
        "receipt_not_passed",
        "evidence_mismatch",
        "invalid_sha",
        "invalid_path",
        "invalid_receipt",
    }
)


class ReceiptError(ValueError):
    """A fail-closed receipt or identity input error."""

    def __init__(self, code: str, message: str) -> None:
        if code not in REJECTION_CODES:
            raise ValueError(f"Unknown receipt error code: {code}")
        super().__init__(message)
        self.code = code


def _sha(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _is_sha(value: Any) -> bool:
    return bool(SHA_RE.fullmatch(_sha(value))) and set(_sha(value)) != {"0"}


def _is_digest(value: Any) -> bool:
    return bool(SHA256_RE.fullmatch(_sha(value)))


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _mapping(value: Any, *, code: str = "invalid_receipt") -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        converted = value.to_dict()
        if isinstance(converted, Mapping):
            return dict(converted)
    if hasattr(value, "__dict__"):
        converted = dict(vars(value))
        if converted:
            return converted
    raise ReceiptError(code, "expected a JSON object")


def _git(repo: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        detail = (process.stderr or "").strip().replace("\n", " ")[:300]
        raise ReceiptError("invalid_receipt", f"git command failed: {detail}")
    return (process.stdout or "").strip()


def _repository_name(repo: Path) -> str:
    """Return a stable owner/name from origin, with a local-only fallback."""

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
        if len(parts) >= 2 and all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) for p in parts[-2:]):
            return f"{parts[-2]}/{parts[-1]}"
    # A local checkout without an origin is still useful in tests and in a
    # pre-registration coordinator flow.  It remains unambiguous locally.
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
        raise ReceiptError("invalid_path", "dependency path must be a non-empty POSIX relative path")
    path = PurePosixPath(raw)
    if raw.startswith("/") or raw.startswith("~") or ":" in raw or ".." in path.parts:
        raise ReceiptError("invalid_path", f"dependency path is not relative: {raw!r}")
    if not path.parts or path == PurePosixPath(".") or any(part in {"", "."} for part in path.parts):
        raise ReceiptError("invalid_path", f"dependency path is not canonical: {raw!r}")
    normalized = path.as_posix()
    if normalized != raw:
        raise ReceiptError("invalid_path", f"dependency path is not canonical: {raw!r}")
    return normalized


def _dependency_bytes(repo: Path, relative: str) -> bytes:
    candidate = repo.joinpath(*PurePosixPath(relative).parts)
    current = repo
    # Refuse both escaping symlinks and symlink aliases.  This makes the bytes
    # being measured the bytes named by the checkout, not an external target.
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ReceiptError("invalid_path", f"dependency path contains a symlink: {relative}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(repo)
    except (OSError, ValueError) as exc:
        raise ReceiptError("invalid_path", f"dependency path escapes repository: {relative}") from exc
    try:
        mode = os.stat(candidate, follow_symlinks=False).st_mode
    except OSError as exc:
        raise ReceiptError("invalid_path", f"dependency file is unavailable: {relative}") from exc
    if not stat.S_ISREG(mode):
        raise ReceiptError("invalid_path", f"dependency is not a regular file: {relative}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(candidate), flags)
    except OSError as exc:
        raise ReceiptError("invalid_path", f"dependency cannot be opened: {relative}") from exc
    try:
        if os.path.islink(candidate):
            raise ReceiptError("invalid_path", f"dependency became a symlink: {relative}")
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            return handle.read()
    finally:
        if fd >= 0:
            os.close(fd)


def _dependency_digests(repo: Path, dependency_files: Sequence[str] | None) -> dict[str, str]:
    if dependency_files is None:
        dependency_files = ()
    normalized = [_normal_relative_path(value) for value in dependency_files]
    if len(set(normalized)) != len(normalized):
        raise ReceiptError("invalid_path", "dependency paths must be unique")
    return {
        relative: "sha256:" + hashlib.sha256(_dependency_bytes(repo, relative)).hexdigest()
        for relative in sorted(normalized)
    }


@dataclass(frozen=True)
class CandidateIdentity:
    repository: str
    source_sha: str
    git_tree_sha: str
    dependency_digests: dict[str, str]
    test_profile: str

    @property
    def sourceSha(self) -> str:  # compatibility with the frozen JSON names
        return self.source_sha

    @property
    def gitTreeSha(self) -> str:
        return self.git_tree_sha

    @property
    def dependencyDigests(self) -> dict[str, str]:
        return dict(self.dependency_digests)

    @property
    def testProfile(self) -> str:
        return self.test_profile

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "sourceSha": self.source_sha,
            "gitTreeSha": self.git_tree_sha,
            "dependencyDigests": dict(sorted(self.dependency_digests.items())),
            "testProfile": self.test_profile,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "CandidateIdentity":
        data = _mapping(value)
        expected = {"repository", "sourceSha", "gitTreeSha", "dependencyDigests", "testProfile"}
        if set(data) != expected:
            raise ReceiptError("invalid_receipt", "candidate identity fields are incomplete or unknown")
        deps = data["dependencyDigests"]
        if not isinstance(deps, Mapping):
            raise ReceiptError("invalid_receipt", "dependencyDigests must be an object")
        normalized: dict[str, str] = {}
        for path, digest in deps.items():
            relative = _normal_relative_path(path)
            if not _is_digest(digest):
                raise ReceiptError("dependency_mismatch", f"invalid dependency digest: {relative}")
            normalized[relative] = digest
        if len(normalized) != len(deps):
            raise ReceiptError("invalid_path", "dependency paths must be unique")
        profile = data["testProfile"]
        if not isinstance(profile, str) or profile not in PROFILES:
            raise ReceiptError("profile_mismatch", "unknown test profile")
        for field in ("sourceSha", "gitTreeSha"):
            if not _is_sha(data[field]):
                raise ReceiptError("invalid_sha", f"invalid {field}")
        repository = data["repository"]
        if not isinstance(repository, str) or not repository or "/" not in repository:
            raise ReceiptError("invalid_receipt", "repository must be owner/name")
        return cls(repository, data["sourceSha"], data["gitTreeSha"], dict(sorted(normalized.items())), profile)


def compute_candidate_identity(
    repo_path: str | os.PathLike[str] | Path,
    dependency_files: Sequence[str] | None,
    test_profile: str = "full",
) -> CandidateIdentity:
    """Compute identity from the checked-out commit and physical dependencies."""

    if test_profile not in PROFILES:
        raise ReceiptError("profile_mismatch", f"unknown test profile: {test_profile!r}")
    repo = _repo_root(repo_path)
    source_sha = _git(repo, "rev-parse", "HEAD").lower()
    tree_sha = _git(repo, "rev-parse", "HEAD^{tree}").lower()
    if not _is_sha(source_sha) or not _is_sha(tree_sha):
        raise ReceiptError("invalid_sha", "Git returned a malformed commit or tree SHA")
    return CandidateIdentity(
        repository=_repository_name(repo),
        source_sha=source_sha,
        git_tree_sha=tree_sha,
        dependency_digests=_dependency_digests(repo, dependency_files),
        test_profile=test_profile,
    )


RECEIPT_FIELDS = {
    "schemaVersion",
    "status",
    "repository",
    "gate",
    "sourceSha",
    "testedCheckoutSha",
    "gitTreeSha",
    "dependencyDigests",
    "testProfile",
    "attempt",
    "coordinatorVersion",
    "startedAt",
    "completedAt",
    "evidenceDigests",
    "github",
    "workerId",
    "workerCapabilities",
    "workerTrust",
    "coordinatorIdentity",
    "executionEnvironment",
}
LEGACY_RECEIPT_FIELDS = RECEIPT_FIELDS - {
    "workerId", "workerCapabilities", "workerTrust", "coordinatorIdentity", "executionEnvironment"
}


@dataclass(frozen=True)
class GateReceipt:
    schema_version: int
    status: str
    repository: str
    gate: str
    source_sha: str
    tested_checkout_sha: str
    git_tree_sha: str
    dependency_digests: dict[str, str]
    test_profile: str
    attempt: int
    coordinator_version: str
    started_at: str
    completed_at: str
    evidence_digests: dict[str, str]
    github: dict[str, Any]
    worker_id: str | None = None
    worker_capabilities: tuple[str, ...] = ()
    worker_trust: str | None = None
    coordinator_identity: str | None = None
    execution_environment: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "status": self.status,
            "repository": self.repository,
            "gate": self.gate,
            "sourceSha": self.source_sha,
            "testedCheckoutSha": self.tested_checkout_sha,
            "gitTreeSha": self.git_tree_sha,
            "dependencyDigests": dict(sorted(self.dependency_digests.items())),
            "testProfile": self.test_profile,
            "attempt": self.attempt,
            "coordinatorVersion": self.coordinator_version,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "evidenceDigests": dict(sorted(self.evidence_digests.items())),
            "github": self.github,
            "workerId": self.worker_id,
            "workerCapabilities": list(self.worker_capabilities),
            "workerTrust": self.worker_trust,
            "coordinatorIdentity": self.coordinator_identity,
            "executionEnvironment": self.execution_environment or {},
        }

    @classmethod
    def from_dict(cls, value: Any) -> "GateReceipt":
        data = _mapping(value)
        if set(data) != LEGACY_RECEIPT_FIELDS and set(data) != RECEIPT_FIELDS:
            raise ReceiptError("invalid_receipt", "receipt fields are incomplete or unknown")
        if data["schemaVersion"] != 1 or not isinstance(data["schemaVersion"], int):
            raise ReceiptError("invalid_receipt", "unsupported receipt schema")
        deps = _parse_digest_map(data["dependencyDigests"], dependency=True)
        evidence = _parse_digest_map(data["evidenceDigests"], dependency=False)
        github = data["github"]
        if not isinstance(github, Mapping) or set(github) != {"pullRequest", "runUrl"}:
            raise ReceiptError("invalid_receipt", "github receipt metadata is invalid")
        if github["pullRequest"] is not None and (
            not isinstance(github["pullRequest"], int) or isinstance(github["pullRequest"], bool)
        ):
            raise ReceiptError("invalid_receipt", "pullRequest must be an integer or null")
        if github["runUrl"] is not None and not isinstance(github["runUrl"], str):
            raise ReceiptError("invalid_receipt", "runUrl must be a string or null")
        worker_capabilities = tuple(data.get("workerCapabilities", ()))
        if any(not isinstance(item, str) or item not in {"fast", "heavy", "nestedDocker"} for item in worker_capabilities):
            raise ReceiptError("invalid_receipt", "workerCapabilities is invalid")
        worker_trust = data.get("workerTrust")
        if worker_trust is not None and worker_trust != "isolated-candidate":
            raise ReceiptError("trust_boundary", "receipt worker trust is not isolated-candidate")
        if data.get("workerId") is not None and (not isinstance(data["workerId"], str) or not data["workerId"]):
            raise ReceiptError("invalid_receipt", "workerId is invalid")
        if data.get("coordinatorIdentity") is not None and (not isinstance(data["coordinatorIdentity"], str) or not data["coordinatorIdentity"]):
            raise ReceiptError("invalid_receipt", "coordinatorIdentity is invalid")
        environment = data.get("executionEnvironment", {})
        if not isinstance(environment, Mapping):
            raise ReceiptError("invalid_receipt", "executionEnvironment must be an object")
        return cls(
            schema_version=1,
            status=data["status"],
            repository=data["repository"],
            gate=data["gate"],
            source_sha=data["sourceSha"],
            tested_checkout_sha=data["testedCheckoutSha"],
            git_tree_sha=data["gitTreeSha"],
            dependency_digests=deps,
            test_profile=data["testProfile"],
            attempt=data["attempt"],
            coordinator_version=data["coordinatorVersion"],
            started_at=data["startedAt"],
            completed_at=data["completedAt"],
            evidence_digests=evidence,
            github=dict(github),
            worker_id=data.get("workerId"),
            worker_capabilities=worker_capabilities,
            worker_trust=worker_trust,
            coordinator_identity=data.get("coordinatorIdentity"),
            execution_environment=dict(environment),
        )


def _parse_digest_map(value: Any, *, dependency: bool) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ReceiptError("invalid_receipt", "digest fields must be objects")
    result: dict[str, str] = {}
    for raw_path, digest in value.items():
        try:
            path = _normal_relative_path(raw_path)
        except ReceiptError:
            if dependency:
                raise
            raise ReceiptError("evidence_mismatch", "evidence path is invalid")
        if not _is_digest(digest):
            raise ReceiptError("dependency_mismatch" if dependency else "evidence_mismatch", "invalid digest")
        result[path] = digest
    if len(result) != len(value):
        raise ReceiptError("invalid_path", "digest paths must be unique")
    return dict(sorted(result.items()))


def _validate_completed_receipt(receipt: GateReceipt) -> None:
    for field in (receipt.source_sha, receipt.tested_checkout_sha, receipt.git_tree_sha):
        if not _is_sha(field):
            raise ReceiptError("invalid_sha", "receipt contains a malformed SHA")
    if receipt.status != "passed":
        raise ReceiptError("receipt_not_passed", "only completed passed results can be written")
    if not isinstance(receipt.gate, str) or receipt.gate not in GATES:
        raise ReceiptError("invalid_receipt", "unknown gate")
    if not isinstance(receipt.test_profile, str) or receipt.test_profile not in PROFILES:
        raise ReceiptError("profile_mismatch", "unknown test profile")
    if not isinstance(receipt.repository, str) or not receipt.repository or "/" not in receipt.repository:
        raise ReceiptError("invalid_receipt", "repository must be owner/name")
    if not isinstance(receipt.attempt, int) or isinstance(receipt.attempt, bool) or receipt.attempt < 1:
        raise ReceiptError("invalid_receipt", "attempt must be a positive integer")
    if not isinstance(receipt.coordinator_version, str) or not SEMVER_RE.fullmatch(receipt.coordinator_version):
        raise ReceiptError("invalid_receipt", "coordinatorVersion must be released semver")
    if receipt.worker_id is not None and receipt.worker_trust != "isolated-candidate":
        raise ReceiptError("trust_boundary", "worker receipt metadata must identify an isolated candidate worker")
    if receipt.worker_id is not None and not receipt.worker_capabilities:
        raise ReceiptError("invalid_receipt", "worker receipt metadata must include capabilities")
    timestamp_re = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
    if (
        not isinstance(receipt.started_at, str)
        or not isinstance(receipt.completed_at, str)
        or not timestamp_re.fullmatch(receipt.started_at)
        or not timestamp_re.fullmatch(receipt.completed_at)
    ):
        raise ReceiptError("invalid_receipt", "timestamps must be RFC3339 UTC")


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


def write_receipt(result: Any, output_path: str | os.PathLike[str] | Path) -> GateReceipt:
    """Validate a completed result and atomically write its canonical receipt."""

    receipt = result if isinstance(result, GateReceipt) else GateReceipt.from_dict(result)
    _validate_completed_receipt(receipt)
    _atomic_write(Path(output_path), _canonical_json(receipt.to_dict()))
    return receipt


@dataclass(frozen=True)
class ReceiptVerdict:
    accepted: bool
    rejection_code: str | None = None
    message: str = ""

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
    required_gate: str,
) -> ReceiptVerdict:
    """Verify receipt reuse against a freshly computed candidate identity."""

    try:
        candidate = candidate_identity if isinstance(candidate_identity, CandidateIdentity) else CandidateIdentity.from_dict(candidate_identity)
        parsed = receipt if isinstance(receipt, GateReceipt) else GateReceipt.from_dict(receipt)
        _validate_completed_receipt(parsed)
        if not isinstance(required_gate, str) or required_gate not in GATES:
            raise ReceiptError("gate_mismatch", "unknown required gate")
        if parsed.gate != required_gate:
            raise ReceiptError("gate_mismatch", "receipt gate does not match required gate")
        if parsed.repository != candidate.repository:
            raise ReceiptError("repository_mismatch", "receipt repository does not match candidate")
        if parsed.git_tree_sha != candidate.git_tree_sha:
            raise ReceiptError("tree_mismatch", "receipt Git tree does not match candidate")
        if parsed.dependency_digests != candidate.dependency_digests:
            raise ReceiptError("dependency_mismatch", "receipt dependencies do not match candidate")
        if parsed.test_profile != candidate.test_profile:
            raise ReceiptError("profile_mismatch", "receipt test profile does not match candidate")
        return ReceiptVerdict(True, message="receipt identity matches")
    except ReceiptError as error:
        return _reject(error)


def load_json(path: str | os.PathLike[str] | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReceiptError("invalid_receipt", f"invalid JSON input: {path}") from exc


__all__ = [
    "CandidateIdentity",
    "GateReceipt",
    "ReceiptError",
    "ReceiptVerdict",
    "compute_candidate_identity",
    "load_json",
    "verify_receipt",
    "write_receipt",
]
