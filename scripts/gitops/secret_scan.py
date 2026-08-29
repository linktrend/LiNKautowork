#!/usr/bin/env python3
"""Fixture-aware secret scanner for managed Fast/Full.

Scans every tracked regular blob from git index/object identities. Synthetic
fixtures pass only through an exact versioned non-production declaration bound
to path, line/field, digest, optional bytes, candidate content tree, and
scanner policy. Realistic credential formats can never be approved.
Repository-owned scanners stay additive and blocking.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

try:
    from scripts.gitops.generated_output_closure import (
        ClosureError,
        candidate_source_tree as closure_candidate_source_tree,
        load_graph as load_generated_output_graph,
    )
    from scripts.gitops.mutation_guard import MutationGuardError, validate_argv
except ModuleNotFoundError:  # pragma: no cover - script-style execution
    from generated_output_closure import (  # type: ignore
        ClosureError,
        candidate_source_tree as closure_candidate_source_tree,
        load_graph as load_generated_output_graph,
    )
    from mutation_guard import MutationGuardError, validate_argv  # type: ignore

SCANNER_POLICY_VERSION = "secret-scan-policy/v1"
CHANGE_SCOPED_SCHEMA_VERSION = 1
CHANGE_SCOPED_KIND = "change-scoped-secret-scan-evidence"
POLICY_SHAPE_RE = re.compile(r"^secret-scan-policy/[A-Za-z0-9._-]+$")
SYNTHETIC_PREFIX = "ltfx."
DECLARATION_REL = ".github/linktrend-secret-scan-fixtures.json"
REPO_SCANNERS_REL = ".github/linktrend-repository-secret-scanners.json"
REPO_SCANNER_TIMEOUT_SEC = 30.0
EMPTY_TREE = "0" * 40

KIND_CREDENTIAL = "credential_finding"
KIND_APPROVED = "approved_synthetic_fixture"
KIND_STALE = "stale_fixture_declaration"
KIND_SCOPE = "fixture_scope_violation"
KIND_SKIPPED = "skipped_input"
BLOCKING_KINDS = frozenset({KIND_CREDENTIAL, KIND_STALE, KIND_SCOPE})

RULE_ASSIGNMENT = "assignment.secret"
RULE_FORMAT_GITHUB = "format.github"
RULE_FORMAT_CLOUD = "format.cloud"
RULE_FORMAT_SK = "format.token"
RULE_FORMAT_DATABASE = "format.database"
RULE_FORMAT_PEM = "format.private_key"
RULE_FORMAT_HIGH_ENTROPY = "format.high_entropy"
RULE_BINDING_TREE = "binding.candidate_tree"
RULE_BINDING_POLICY = "binding.scanner_policy"
RULE_UNKNOWN = "declaration.unknown_rule"
RULE_MALFORMED = "declaration.malformed"
RULE_REPO_SCANNER = "repository_scanner.failure"
RULE_REPO_TIMEOUT = "repository_scanner.timeout"
RULE_REPO_MALFORMED = "repository_scanner.malformed"
RULE_REPO_CREDENTIAL_DISCOVERY = "repository_scanner.credential_discovery"
RULE_INPUT_UNDECODABLE = "input.undecodable"
RULE_INPUT_TOO_LARGE = "input.too_large"
RULE_GIT_FAILED = "git.failed"
RULE_CHANGE_SCOPE = "change_scope.invalid"
RULE_CHANGE_IDENTITY = "change_scope.identity"
RULE_CHANGE_CONFIG = "change_scope.config"
RULE_CHANGE_PATHS = "change_scope.paths"
GENERATED_PACKAGE_MANIFEST_REL = ".ide-development/MANIFEST.json"
GENERATED_CLOSURE_CONTRACT_SOURCE_REL = "core/managed-core/content/config/generated-output-closure.consumer.json"
GENERATED_CLOSURE_CONTRACT_DEST_REL = ".ide-development/config/generated-output-closure.json"
MIGRATION_CATALOG_RELS = (
    ".ide-development/migrations/catalog.json",
    "core/managed-core/migrations/catalog.json",
)

KNOWN_RULES = frozenset(
    {
        RULE_ASSIGNMENT,
        RULE_FORMAT_GITHUB,
        RULE_FORMAT_CLOUD,
        RULE_FORMAT_SK,
        RULE_FORMAT_DATABASE,
        RULE_FORMAT_PEM,
        RULE_FORMAT_HIGH_ENTROPY,
    }
)

CREDENTIAL_FIELDS = (
    "secret",
    "token",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "api-key",
    "private_key",
    "private-key",
)
GENERIC_REFERENCE_FIELDS = frozenset({"key", "url"})
ANY_FIELD_RE = re.compile(r"(?i)\b(?P<field>[A-Za-z_][A-Za-z0-9_]*)\b")
FIELD_RE = re.compile(
    r"(?i)\b(?P<field>"
    + "|".join(re.escape(name) for name in CREDENTIAL_FIELDS)
    + r"|[A-Za-z_][A-Za-z0-9_]*(?:secret|token|password|passwd|api[_-]?key|private[_-]?key|apikey)"
    + r")\b"
)
MIN_ASSIGNMENT_LEN = 8
GITHUB_RE = re.compile(r"\b(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|gho_[A-Za-z0-9]{20,})\b")
CLOUD_RE = re.compile(r"\b(AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[0-9A-Za-z\-_]{20,})\b")
TOKEN_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b")
DATABASE_RE = re.compile(
    r"\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?)://[^\s'\"\\]+",
    re.IGNORECASE,
)
PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----")
OID_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ROOT_KEYS = frozenset(
    {"schemaVersion", "kind", "scannerPolicyVersion", "candidateTree", "fixtures"}
)
FIXTURE_REQUIRED = (
    "id",
    "path",
    "line",
    "field",
    "rule",
    "digest",
    "purpose",
    "production",
)
FIXTURE_OPTIONAL = frozenset({"bytes"})
REGULAR_MODES = frozenset({"100644", "100755"})
SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# These are the only files whose policy/scanner bytes can affect a managed
# scan.  A change-scoped run always scans them even when the source diff is
# otherwise small.  Keep this set explicit: broad path exclusions are unsafe.
MANAGED_SCANNER_POLICY_PATHS = (
    DECLARATION_REL,
    REPO_SCANNERS_REL,
    "scripts/gitops/secret_scan.py",
    "scripts/gitops/secret_scan_migrate.py",
    "core/managed-core/config/delivery.json",
    ".github/linktrend-delivery-mode.json",
    ".github/linktrend-repository-ci-contract.json",
    "core/managed-core/schemas/secret-scan-fixtures.schema.json",
    "core/managed-core/schemas/secret-scan-result.schema.json",
    "core/managed-core/schemas/change-scoped-secret-scan.schema.json",
)


def managed_scanner_policy_paths(root: Path) -> tuple[str, ...]:
    """Return source or extracted-package policy paths for this repository."""
    managed_root = "core/managed-core"
    if (root / ".ide-development").is_dir() and not (root / managed_root).is_dir():
        managed_root = ".ide-development"
    return tuple(
        path.replace("core/managed-core", managed_root)
        for path in MANAGED_SCANNER_POLICY_PATHS
    )


class SecretScanError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class IndexEntry:
    mode: str
    oid: str
    stage: str
    path: str

    @property
    def is_regular(self) -> bool:
        return self.mode in REGULAR_MODES


def digest_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _git(root: Path, *args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        input=input_text,
    )
    if result.returncode:
        raise SecretScanError("git_failed", (result.stderr or result.stdout).strip())
    return result.stdout


def _git_bytes(root: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        check=False,
        input=input_bytes,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise SecretScanError("git_failed", detail)
    return result.stdout


def _git_identity(root: Path) -> tuple[str, str, str]:
    """Return the exact candidate commit, full Git tree, and repository name."""
    commit = _git(root, "rev-parse", "--verify", "HEAD^{commit}").strip()
    tree = _git(root, "rev-parse", "--verify", "HEAD^{tree}").strip()
    if not OID_RE.fullmatch(commit) or not OID_RE.fullmatch(tree):
        raise SecretScanError("change_scope_identity", "candidate commit/tree")
    try:
        remote = _git(root, "remote", "get-url", "origin").strip()
    except SecretScanError as exc:
        raise SecretScanError("change_scope_identity", "origin remote is required") from exc
    remote = remote.removesuffix("/").removesuffix(".git")
    if remote.startswith("git@") and ":" in remote:
        repository = remote.split(":", 1)[1]
    else:
        repository = remote.rsplit("/", 2)[-2:]
        repository = "/".join(repository) if isinstance(repository, list) else str(repository)
    if not repository or "/" not in repository or repository.startswith("/"):
        raise SecretScanError("change_scope_identity", "repository identity")
    return commit, tree, repository


def config_digest(root: Path, paths: tuple[str, ...] | None = None) -> str:
    """Digest policy/scanner paths, including explicit missing-file markers."""
    digest = hashlib.sha256()
    for rel in sorted(paths or managed_scanner_policy_paths(root)):
        path = root / rel
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        try:
            raw = path.read_bytes() if path.is_file() else b"<missing>"
        except OSError as exc:
            raise SecretScanError("change_scope_config", rel) from exc
        digest.update(raw)
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _remote_ref_name(ref: str) -> str:
    if ref.startswith("refs/remotes/"):
        return ref
    if re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+", ref):
        return "refs/remotes/" + ref
    raise SecretScanError("change_scope_identity", "authoritative remote ref")


def changed_paths(root: Path, baseline_commit: str, candidate_commit: str) -> set[str]:
    """Resolve a conservative baseline-to-candidate path set.

    Deletes are allowed only for exact migration-catalog removal destinations;
    all other deletes, malformed statuses, or path ambiguity are hard failures.
    Git rename/copy records contribute both source and destination paths so
    neither side becomes an accidental blind spot in a large fork.
    """
    raw = _git_bytes(
        root,
        "diff",
        "--name-status",
        "--find-renames=50%",
        "--find-copies=50%",
        "-z",
        f"{baseline_commit}..{candidate_commit}",
        "--",
    )
    tokens = raw.split(b"\0")
    paths: set[str] = set()
    managed_migrations = _managed_migration_paths(root)
    index = 0
    while index < len(tokens):
        status_raw = tokens[index]
        index += 1
        if not status_raw:
            continue
        try:
            status = status_raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise SecretScanError("change_scope_paths", "non-ascii diff status") from exc
        if not status or status[0] not in "ADMUTRC" or (len(status) > 1 and not status[1:].isdigit()):
            raise SecretScanError("change_scope_paths", f"ambiguous status {status}")
        if status[0] == "D" and len(status) != 1:
            raise SecretScanError("change_scope_paths", f"ambiguous status {status}")
        if index >= len(tokens) or not tokens[index]:
            raise SecretScanError("change_scope_paths", "missing changed path")
        path_raw = tokens[index]
        index += 1
        path = path_raw.decode("utf-8", errors="strict")
        if not _valid_relpath(path):
            raise SecretScanError("change_scope_paths", "invalid changed path")
        if status[0] == "D" and path not in managed_migrations:
            raise SecretScanError("change_scope_paths", "undeclared migration deletion")
        paths.add(path)
        if status[0] in "RC":
            if len(status) == 1 or not status[1:].isdigit():
                raise SecretScanError("change_scope_paths", f"ambiguous status {status}")
            if index >= len(tokens) or not tokens[index]:
                raise SecretScanError("change_scope_paths", "missing rename/copy destination")
            destination = tokens[index].decode("utf-8", errors="strict")
            index += 1
            if not _valid_relpath(destination):
                raise SecretScanError("change_scope_paths", "invalid rename/copy destination")
            paths.add(destination)
    return paths


def _validate_change_scoped_evidence(
    root: Path, evidence: Any
) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        raise SecretScanError("change_scope_identity", "evidence must be an object")
    required = {
        "schemaVersion", "kind", "repository", "authoritativeRemoteRef",
        "baselineCommit", "baselineTree", "candidateCommit", "candidateGitTree",
        "scannerPolicyVersion", "managedPaths", "configDigest", "findings",
    }
    if evidence.get("schemaVersion") != CHANGE_SCOPED_SCHEMA_VERSION or evidence.get("kind") != CHANGE_SCOPED_KIND:
        raise SecretScanError("change_scope_identity", "schema or kind")
    # candidateTree was the name used by early acceptance packets for the
    # full Git tree. Accept it as a one-way compatibility alias, while output
    # remains unambiguous (`candidateGitTree` versus the result's source tree.
    candidate_git_tree = evidence.get("candidateGitTree", evidence.get("candidateTree"))
    allowed = required | {"candidateTree"}
    if set(evidence) - allowed:
        raise SecretScanError("change_scope_identity", "unknown evidence field")
    if required - set(evidence) - {"candidateGitTree"} or candidate_git_tree is None:
        raise SecretScanError("change_scope_identity", "missing evidence identity")
    commit, tree, repository = _git_identity(root)
    if evidence["repository"] != repository:
        raise SecretScanError("change_scope_identity", "repository")
    remote_ref = _remote_ref_name(str(evidence["authoritativeRemoteRef"]))
    baseline = str(evidence["baselineCommit"])
    baseline_tree = str(evidence["baselineTree"])
    if not OID_RE.fullmatch(baseline) or not OID_RE.fullmatch(baseline_tree):
        raise SecretScanError("change_scope_identity", "baseline commit/tree")
    if evidence["candidateCommit"] != commit or candidate_git_tree != tree:
        raise SecretScanError("change_scope_identity", "candidate commit/tree")
    if evidence["scannerPolicyVersion"] != SCANNER_POLICY_VERSION:
        raise SecretScanError("change_scope_policy", "scannerPolicyVersion")
    if not isinstance(evidence["managedPaths"], list) or any(
        not isinstance(path, str) or not _valid_relpath(path) for path in evidence["managedPaths"]
    ):
        raise SecretScanError("change_scope_paths", "managed scanner/policy path set")
    expected_paths = managed_scanner_policy_paths(root)
    if sorted(evidence["managedPaths"]) != sorted(expected_paths):
        raise SecretScanError("change_scope_paths", "managed scanner/policy path set")
    if not isinstance(evidence["findings"], list):
        raise SecretScanError("change_scope_identity", "findings")
    for finding in evidence["findings"]:
        if not isinstance(finding, dict) or not _valid_relpath(str(finding.get("path", ""))):
            raise SecretScanError("change_scope_identity", "finding path")
    if not SHA256_DIGEST_RE.fullmatch(str(evidence["configDigest"])):
        raise SecretScanError("change_scope_config", "configDigest shape")
    if config_digest(root, expected_paths) != evidence["configDigest"]:
        raise SecretScanError("change_scope_config", "configDigest")
    try:
        remote_tip = _git(root, "rev-parse", "--verify", remote_ref + "^{commit}").strip()
        resolved_baseline_tree = _git(root, "rev-parse", "--verify", baseline + "^{tree}").strip()
    except SecretScanError as exc:
        raise SecretScanError("change_scope_identity", "baseline or authoritative ref unavailable") from exc
    if remote_tip != baseline or resolved_baseline_tree != baseline_tree:
        raise SecretScanError("change_scope_identity", "stale baseline commit/tree")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", baseline, commit], cwd=root, check=False)
    if ancestor.returncode:
        raise SecretScanError("change_scope_identity", "baseline is not an ancestor")
    # The transaction may dirty only the exact managed scanner/policy paths.
    # Any unrelated edit, type change, delete, rename, or copy remains an
    # ambiguous candidate and fails closed.
    expected_managed = set(managed_scanner_policy_paths(root))
    expected_transaction = _managed_transaction_paths(root)
    expected_migrations = _managed_migration_paths(root)
    for status, path in _worktree_diff_statuses(root, commit):
        if status[0] == "D":
            if path not in expected_migrations:
                raise SecretScanError("change_scope_paths", "candidate worktree differs outside managed paths")
            continue
        if path in expected_migrations:
            raise SecretScanError("change_scope_paths", "migration destination must be removed")
        if (
            status[0] not in {"M", "A", "T", "U"}
            or path not in expected_managed | expected_transaction
            or (status[0] in {"A", "T", "U"} and path not in expected_transaction)
        ):
            raise SecretScanError("change_scope_paths", "candidate worktree differs outside managed paths")
        if not (root / path).is_file() or (root / path).is_symlink():
            raise SecretScanError("change_scope_paths", "managed path is deleted or symlinked")
    untracked = _untracked_worktree_paths(root)
    if any(path not in expected_transaction for path in untracked):
        raise SecretScanError("change_scope_paths", "untracked candidate paths are ambiguous")
    for path in untracked:
        if not (root / path).is_file() or (root / path).is_symlink():
            raise SecretScanError("change_scope_paths", "managed transaction path is deleted or symlinked")
    return {
        "repository": repository,
        "authoritativeRemoteRef": str(evidence["authoritativeRemoteRef"]),
        "baselineCommit": baseline,
        "baselineTree": baseline_tree,
        "candidateCommit": commit,
        "candidateGitTree": tree,
        "findings": evidence["findings"],
        "changedPaths": changed_paths(root, baseline, commit),
    }


def tracked_entries(root: Path) -> list[IndexEntry]:
    """Index identities from `git ls-files -s`. Does not follow symlinks/gitlinks."""
    raw = _git_bytes(root, "ls-files", "-s", "-z", "--")
    entries: list[IndexEntry] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            meta, path_b = item.split(b"\t", 1)
            mode_b, oid_b, stage_b = meta.split(b" ", 2)
        except ValueError as exc:
            raise SecretScanError("git_failed", "ls-files parse") from exc
        path = path_b.decode("utf-8").replace("\\", "/")
        oid = oid_b.decode("ascii")
        if not OID_RE.fullmatch(oid):
            raise SecretScanError("git_failed", f"invalid oid {oid}")
        entries.append(
            IndexEntry(
                mode=mode_b.decode("ascii"),
                oid=oid,
                stage=stage_b.decode("ascii"),
                path=path,
            )
        )
    return entries


def tracked_files(root: Path) -> list[str]:
    return [entry.path for entry in tracked_entries(root)]


def candidate_content_tree(root: Path) -> str:
    """40-hex identity excluding every declaratively generated output."""
    graph_paths = (
        root / "core/managed-core/config/generated-output-closure.json",
        root / ".ide-development/config/generated-output-closure.json",
        root / ".ide-development/content/config/generated-output-closure.json",
    )
    if any(path.is_file() for path in graph_paths):
        try:
            return closure_candidate_source_tree(root)
        except ClosureError as exc:
            raise SecretScanError("generated_output_graph_invalid", str(exc)) from exc
    return closure_candidate_source_tree(root, graph_path=None)


def _shannon(value: str) -> float:
    counts: dict[str, int] = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    length = len(value)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


def _is_reference_value(value: str) -> bool:
    stripped = value.strip()
    if not stripped or stripped == SYNTHETIC_PREFIX:
        return True
    if stripped.startswith(("(", "[", "{")):
        return True
    if stripped.startswith(("$", "<")):
        return True
    if re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", stripped):
        return True
    if re.search(r"[A-Za-z_][A-Za-z0-9_]*\(", stripped):
        return True
    if re.match(r"(?i)(?:https?|git|ssh|file)://", stripped) and not DATABASE_RE.search(stripped):
        return True
    if stripped.startswith(("f\"", "f'", 'rf"', "fr\"", "F\"", "F'")):
        return True
    if stripped.startswith("`") or stripped.endswith("`"):
        return True
    expression = stripped.rstrip(",;:)}]")
    if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*(?:\?\.)[A-Za-z_$][A-Za-z0-9_$?.]*", expression):
        return True
    if expression.endswith(("...", "…")):
        return True
    if ".md`" in stripped or (".md" in stripped and "/" in stripped):
        return True
    if len(stripped.split()) >= 4:
        return True
    return False


def is_realistic_value(value: str) -> bool:
    if GITHUB_RE.search(value) or CLOUD_RE.search(value) or TOKEN_RE.search(value):
        return True
    if DATABASE_RE.search(value) or PRIVATE_KEY_RE.search(value):
        return True
    if _is_reference_value(value):
        return False
    compact = re.sub(r"\s+", "", value)
    if len(compact) >= 40 and _shannon(compact) >= 3.5 and not compact.startswith(SYNTHETIC_PREFIX):
        return True
    return False


def is_synthetic_value(value: str) -> bool:
    return (
        value.startswith(SYNTHETIC_PREFIX)
        and len(value) > len(SYNTHETIC_PREFIX)
        and not is_realistic_value(value)
    )


def _rule_for_value(value: str, *, assigned: bool) -> str:
    if GITHUB_RE.search(value):
        return RULE_FORMAT_GITHUB
    if CLOUD_RE.search(value):
        return RULE_FORMAT_CLOUD
    if TOKEN_RE.search(value):
        return RULE_FORMAT_SK
    if DATABASE_RE.search(value):
        return RULE_FORMAT_DATABASE
    if PRIVATE_KEY_RE.search(value):
        return RULE_FORMAT_PEM
    if len(value) >= 40 and _shannon(value) >= 3.5 and not value.startswith(SYNTHETIC_PREFIX):
        return RULE_FORMAT_HIGH_ENTROPY
    return RULE_ASSIGNMENT if assigned else RULE_FORMAT_HIGH_ENTROPY


def _add_detection(
    detections: list[dict[str, Any]],
    *,
    path: str,
    line: int,
    field: str,
    rule: str,
    value: str,
) -> None:
    key = (path, line, field, rule, value)
    if any((row["path"], row["line"], row["field"], row["rule"], row["value"]) == key for row in detections):
        return
    detections.append(
        {
            "path": path,
            "line": line,
            "field": field,
            "rule": rule,
            "value": value,
            "digest": digest_bytes(value.encode("utf-8")),
            "realistic": is_realistic_value(value),
        }
    )


def _skip_ws(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t":
        index += 1
    return index


def _read_quoted(text: str, index: int) -> tuple[str, int] | None:
    if index >= len(text) or text[index] not in {"'", '"'}:
        return None
    quote = text[index]
    index += 1
    chars: list[str] = []
    while index < len(text) and text[index] != "\n":
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            nxt = text[index + 1]
            mapped = {"\\": "\\", '"': '"', "'": "'", "n": "\n", "r": "\r", "t": "\t", "0": "\0"}
            chars.append(mapped.get(nxt, nxt))
            index += 2
            continue
        if char == quote:
            return "".join(chars), index + 1
        chars.append(char)
        index += 1
    return None


def _read_concat_quoted(text: str, index: int) -> tuple[str, int] | None:
    first = _read_quoted(text, index)
    if first is None:
        return None
    value, index = first
    while True:
        cursor = _skip_ws(text, index)
        if cursor < len(text) and text[cursor] == "+":
            cursor = _skip_ws(text, cursor + 1)
            nxt = _read_quoted(text, cursor)
            if nxt is None:
                break
            piece, index = nxt
            value += piece
            continue
        if cursor < len(text) and text[cursor] in {"'", '"'}:
            nxt = _read_quoted(text, cursor)
            if nxt is None:
                break
            piece, index = nxt
            value += piece
            continue
        break
    return value, index


def _read_unquoted(text: str, index: int) -> tuple[str, int]:
    cursor = index
    while cursor < len(text) and text[cursor] not in " \t\n,#;}]":
        cursor += 1
    return text[index:cursor], cursor


def _is_credential_field(name: str) -> bool:
    return FIELD_RE.fullmatch(name) is not None


def _is_generic_reference_field(name: str) -> bool:
    return name.lower().replace("-", "_") in GENERIC_REFERENCE_FIELDS


def _is_code_expression(value: str) -> bool:
    stripped = value.strip().rstrip(",;:)}]")
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", stripped):
        return True
    if re.search(r"[\[\]+]|::|\?\.|\?\?|=>|->", stripped):
        return True
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", stripped) and "." in stripped:
        return True
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*(?:\([^)]*\)|\))+", stripped):
        return True
    # A multiline call can end the physical source line immediately after its
    # opening parenthesis. Treat that syntactic reference as code, while the
    # realistic-value check above still blocks credential literals.
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*\(", stripped):
        return True
    return False


def extract_assignments(line: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for match in ANY_FIELD_RE.finditer(line):
        raw_field = match.group("field")
        field = raw_field.lower().replace("-", "_")
        index = _skip_ws(line, match.end())
        if index < len(line) and line[index] in {"'", '"'}:
            index = _skip_ws(line, index + 1)
        if index >= len(line) or line[index] not in ":=":
            continue
        assignment_index = index
        index += 1
        if (
            line[assignment_index] == ":"
            and index < len(line)
            and line[index] in "-=+?"
            and line[max(0, match.start() - 2) : match.start()] == "${"
        ):
            # Bash parameter expansion (`${NAME:-default}`, and its =/+/?
            # variants) uses the second character as an operator, not as part
            # of the effective value. Keep ordinary YAML/shell values that
            # genuinely begin with `-` unchanged.
            index += 1
        index = _skip_ws(line, index)
        if index >= len(line):
            continue
        quoted = line[index] in {"'", '"'}
        if quoted:
            read = _read_concat_quoted(line, index)
            if read is None:
                continue
            value, _ = read
        else:
            value, _ = _read_unquoted(line, index)
            if not value:
                continue
        credential_field = _is_credential_field(raw_field)
        generic_reference_field = _is_generic_reference_field(raw_field)
        if not credential_field and not generic_reference_field and not is_synthetic_value(value):
            continue
        if generic_reference_field and not is_realistic_value(value) and not is_synthetic_value(value):
            continue
        if _is_reference_value(value) and not is_realistic_value(value) and not is_synthetic_value(value):
            continue
        if (
            _is_code_expression(value)
            and not is_realistic_value(value)
            and not is_synthetic_value(value)
        ):
            continue
        found.append((field, value))
    return found


def scan_text(path: str, text: str) -> list[dict[str, Any]]:
    detections: list[dict[str, Any]] = []
    for index, raw_line in enumerate(text.splitlines(), start=1):
        for field, value in extract_assignments(raw_line):
            if len(value) < MIN_ASSIGNMENT_LEN and not value.startswith(SYNTHETIC_PREFIX):
                continue
            _add_detection(
                detections,
                path=path,
                line=index,
                field=field,
                rule=_rule_for_value(value, assigned=True),
                value=value,
            )
        for match in GITHUB_RE.finditer(raw_line):
            _add_detection(
                detections,
                path=path,
                line=index,
                field="token",
                rule=RULE_FORMAT_GITHUB,
                value=match.group(0),
            )
        for match in CLOUD_RE.finditer(raw_line):
            _add_detection(
                detections,
                path=path,
                line=index,
                field="key",
                rule=RULE_FORMAT_CLOUD,
                value=match.group(0),
            )
        for match in TOKEN_RE.finditer(raw_line):
            _add_detection(
                detections,
                path=path,
                line=index,
                field="token",
                rule=RULE_FORMAT_SK,
                value=match.group(0),
            )
        for match in DATABASE_RE.finditer(raw_line):
            _add_detection(
                detections,
                path=path,
                line=index,
                field="url",
                rule=RULE_FORMAT_DATABASE,
                value=match.group(0),
            )
        if PRIVATE_KEY_RE.search(raw_line):
            _add_detection(
                detections,
                path=path,
                line=index,
                field="private_key",
                rule=RULE_FORMAT_PEM,
                value=raw_line.strip(),
            )
    return detections


def _nul_ratio(raw: bytes, offset: int) -> float:
    if len(raw) < 2:
        return 0.0
    pairs = (len(raw) - offset) // 2
    if pairs <= 0:
        return 0.0
    nuls = sum(1 for index in range(offset, len(raw), 2) if raw[index] == 0)
    return nuls / pairs


def _looks_binary(raw: bytes) -> bool:
    sample = raw[:8192]
    if not sample:
        return False
    controls = sum(byte < 9 or 13 < byte < 32 for byte in sample)
    return controls / len(sample) > 0.01


def decode_tracked_text(raw: bytes) -> tuple[str | None, str]:
    """Decode UTF-8 / UTF-16 / UTF-16LE / UTF-16BE. Never uses errors=ignore."""
    if raw.startswith(b"\xff\xfe"):
        try:
            return raw.decode("utf-16-le"), "utf-16-le"
        except UnicodeDecodeError:
            return None, "undecodable"
    if raw.startswith(b"\xfe\xff"):
        try:
            return raw.decode("utf-16-be"), "utf-16-be"
        except UnicodeDecodeError:
            return None, "undecodable"
    if raw.startswith(b"\xef\xbb\xbf"):
        try:
            return raw.decode("utf-8-sig"), "utf-8"
        except UnicodeDecodeError:
            return None, "undecodable"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    else:
        if "\x00" not in text:
            if _looks_binary(raw):
                return None, "binary"
            return text, "utf-8"
    if len(raw) >= 4 and len(raw) % 2 == 0:
        if _nul_ratio(raw, 1) >= 0.25:
            try:
                return raw.decode("utf-16-le"), "utf-16-le"
            except UnicodeDecodeError:
                return None, "undecodable"
        if _nul_ratio(raw, 0) >= 0.25:
            try:
                return raw.decode("utf-16-be"), "utf-16-be"
            except UnicodeDecodeError:
                return None, "undecodable"
    if b"\x00" in raw:
        return None, "undecodable"
    if _looks_binary(raw):
        return None, "binary"
    return raw.decode("latin-1"), "latin-1"


def _valid_relpath(path: str) -> bool:
    if not path or path.startswith("/") or "\\" in path or "\x00" in path:
        return False
    parts = path.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def _load_json_bytes(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SecretScanError("declaration_malformed", str(exc)) from exc


def _validate_declaration(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SecretScanError("declaration_malformed", "root must be an object")
    extra = set(payload) - ROOT_KEYS
    if extra:
        raise SecretScanError("declaration_malformed", f"extra {sorted(extra)}")
    missing = ROOT_KEYS - set(payload)
    if missing:
        raise SecretScanError("declaration_malformed", f"missing {sorted(missing)}")
    if payload.get("schemaVersion") != 1 or payload.get("kind") != "secret-scan-fixtures":
        raise SecretScanError("declaration_malformed", "schema or kind")
    if not isinstance(payload.get("scannerPolicyVersion"), str) or not POLICY_SHAPE_RE.fullmatch(
        payload["scannerPolicyVersion"]
    ):
        raise SecretScanError("declaration_malformed", "scannerPolicyVersion")
    if not isinstance(payload.get("candidateTree"), str) or not OID_RE.fullmatch(payload["candidateTree"]):
        raise SecretScanError("declaration_malformed", "candidateTree")
    fixtures = payload.get("fixtures")
    if not isinstance(fixtures, list):
        raise SecretScanError("declaration_malformed", "fixtures")
    seen_ids: set[str] = set()
    for row in fixtures:
        if not isinstance(row, dict):
            raise SecretScanError("declaration_malformed", "fixture")
        extra_row = set(row) - set(FIXTURE_REQUIRED) - FIXTURE_OPTIONAL
        if extra_row:
            raise SecretScanError("declaration_malformed", f"extra {sorted(extra_row)}")
        for key in FIXTURE_REQUIRED:
            if key not in row:
                raise SecretScanError("declaration_malformed", f"fixture.{key}")
        if row.get("production") is not False:
            raise SecretScanError("declaration_malformed", "production must be false")
        if not isinstance(row.get("purpose"), str) or not row["purpose"].strip():
            raise SecretScanError("declaration_malformed", "purpose")
        if not isinstance(row.get("id"), str) or not row["id"].strip():
            raise SecretScanError("declaration_malformed", "id")
        fixture_id = row["id"]
        if fixture_id in seen_ids:
            raise SecretScanError("declaration_malformed", "duplicate id")
        seen_ids.add(fixture_id)
        if not isinstance(row.get("field"), str) or not row["field"].strip():
            raise SecretScanError("declaration_malformed", "field")
        if not isinstance(row.get("rule"), str) or not row["rule"].strip():
            raise SecretScanError("declaration_malformed", "rule")
        if not isinstance(row.get("path"), str) or not _valid_relpath(row["path"]):
            raise SecretScanError("declaration_malformed", "path")
        if not isinstance(row.get("digest"), str) or not DIGEST_RE.fullmatch(row["digest"]):
            raise SecretScanError("declaration_malformed", "digest")
        if not isinstance(row.get("line"), int) or isinstance(row.get("line"), bool) or row["line"] < 1:
            raise SecretScanError("declaration_malformed", "line")
        if "bytes" in row and (not isinstance(row["bytes"], str) or not row["bytes"]):
            raise SecretScanError("declaration_malformed", "bytes")
    return payload


def _finding(
    *,
    kind: str,
    path: str,
    line: int | None,
    field: str | None,
    rule: str,
    digest: str | None,
    fixture_id: str | None = None,
    scanner_id: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"kind": kind, "path": path, "rule": rule}
    if line is not None:
        row["line"] = line
    if field is not None:
        row["field"] = field
    if digest is not None:
        row["digest"] = digest
    if fixture_id is not None:
        row["fixtureId"] = fixture_id
    if scanner_id is not None:
        row["scannerId"] = scanner_id
    if detail is not None:
        row["detail"] = detail
    return row


def _error_result(exc: SecretScanError, content_tree: str = EMPTY_TREE) -> dict[str, Any]:
    rule = {
        "git_failed": RULE_GIT_FAILED,
        "declaration_malformed": RULE_MALFORMED,
        "repository_scanners_malformed": RULE_REPO_MALFORMED,
    }.get(exc.code, exc.code.replace("_", "."))
    path = DECLARATION_REL if exc.code == "declaration_malformed" else (
        REPO_SCANNERS_REL if exc.code == "repository_scanners_malformed" else "."
    )
    return make_result(
        content_tree=content_tree,
        findings=[
            _finding(
                kind=KIND_CREDENTIAL,
                path=path,
                line=None,
                field=None,
                rule=rule,
                digest=None,
                detail=exc.detail or exc.code,
            )
        ],
    )


def make_result(
    *, content_tree: str, findings: list[dict[str, Any]], scan_mode: str | None = None, **metadata: Any
) -> dict[str, Any]:
    ok = not any(row["kind"] in BLOCKING_KINDS for row in findings)
    result = {
        "schemaVersion": 1,
        "kind": "secret-scan-result",
        "scannerPolicyVersion": SCANNER_POLICY_VERSION,
        "candidateTree": content_tree if OID_RE.fullmatch(content_tree) else EMPTY_TREE,
        "ok": ok,
        "findings": findings,
    }
    if scan_mode is not None:
        result["scanMode"] = scan_mode
    metadata_keys = {
        "authoritative_remote_ref": "authoritativeRemoteRef",
        "baseline_commit": "baselineCommit",
        "baseline_tree": "baselineTree",
        "candidate_commit": "candidateCommit",
        "candidate_git_tree": "candidateGitTree",
        "managed_paths": "managedPaths",
        "config_digest": "configDigest",
        "scanned_paths": "scannedPaths",
        "inherited_finding_count": "inheritedFindingCount",
    }
    result.update(
        {metadata_keys.get(key, key): value for key, value in metadata.items() if value is not None}
    )
    return result


def _evaluate_declarations(
    detections: list[dict[str, Any]],
    declaration: dict[str, Any] | None,
    content_tree: str,
    inherited_fixture_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    fixtures = list((declaration or {}).get("fixtures") or [])
    bindings_valid = True
    if declaration is not None:
        if declaration.get("scannerPolicyVersion") != SCANNER_POLICY_VERSION:
            bindings_valid = False
            findings.append(
                _finding(
                    kind=KIND_STALE,
                    path=DECLARATION_REL,
                    line=None,
                    field=None,
                    rule=RULE_BINDING_POLICY,
                    digest=None,
                    detail="scannerPolicyVersion",
                )
            )
        if declaration.get("candidateTree") != content_tree:
            bindings_valid = False
            findings.append(
                _finding(
                    kind=KIND_STALE,
                    path=DECLARATION_REL,
                    line=None,
                    field=None,
                    rule=RULE_BINDING_TREE,
                    digest=None,
                    detail="candidateTree",
                )
            )
        for row in fixtures:
            if row["rule"] not in KNOWN_RULES:
                bindings_valid = False
                findings.append(
                    _finding(
                        kind=KIND_SCOPE,
                        path=str(row["path"]),
                        line=int(row["line"]),
                        field=str(row["field"]),
                        rule=RULE_UNKNOWN,
                        digest=str(row["digest"]),
                        fixture_id=str(row["id"]),
                    )
                )

    # Change-scoped scans intentionally do not rescan unchanged source files.
    # Rows for synthetic values in those files therefore have no current
    # detection to mark them as used.  The caller supplies only exact rows
    # inherited from the trusted baseline declaration; all other rows still
    # have to be observed and remain fail-closed when unused or stale.
    used: set[str] = set(inherited_fixture_ids or ())
    for detection in detections:
        if (
            detection["path"] == DECLARATION_REL
            and is_synthetic_value(detection["value"])
            and not detection["realistic"]
        ):
            continue
        match = None
        if bindings_valid and detection["path"] != DECLARATION_REL:
            for row in fixtures:
                declared_bytes = row.get("bytes")
                bytes_ok = declared_bytes is None or declared_bytes == detection["value"]
                if (
                    bytes_ok
                    and row["path"] == detection["path"]
                    and int(row["line"]) == detection["line"]
                    and str(row["field"]) == detection["field"]
                    and str(row["rule"]) == detection["rule"]
                    and str(row["digest"]) == detection["digest"]
                ):
                    match = row
                    break
        if (
            match is not None
            and detection["path"] != DECLARATION_REL
            and not detection["realistic"]
            and is_synthetic_value(detection["value"])
        ):
            used.add(str(match["id"]))
            findings.append(
                _finding(
                    kind=KIND_APPROVED,
                    path=detection["path"],
                    line=detection["line"],
                    field=detection["field"],
                    rule=detection["rule"],
                    digest=detection["digest"],
                    fixture_id=str(match["id"]),
                )
            )
            continue
        kind = KIND_CREDENTIAL
        fixture_id = None
        if detection["path"] == DECLARATION_REL:
            kind = KIND_CREDENTIAL
        elif detection["realistic"]:
            kind = KIND_CREDENTIAL
            if match is not None:
                fixture_id = str(match["id"])
        elif match is not None and not is_synthetic_value(detection["value"]):
            kind = KIND_CREDENTIAL
            fixture_id = str(match["id"])
        elif declaration is not None and not bindings_valid:
            kind = KIND_STALE
        else:
            near = [
                row
                for row in fixtures
                if row["path"] == detection["path"] or str(row["digest"]) == detection["digest"]
            ]
            if near:
                kind = KIND_STALE if any(str(row["digest"]) != detection["digest"] for row in near) else KIND_SCOPE
                fixture_id = str(near[0]["id"])
        findings.append(
            _finding(
                kind=kind,
                path=detection["path"],
                line=detection["line"],
                field=detection["field"],
                rule=detection["rule"],
                digest=detection["digest"],
                fixture_id=fixture_id,
            )
        )

    if bindings_valid:
        for row in fixtures:
            if str(row["id"]) in used:
                continue
            findings.append(
                _finding(
                    kind=KIND_STALE,
                    path=str(row["path"]),
                    line=int(row["line"]),
                    field=str(row["field"]),
                    rule=str(row["rule"]),
                    digest=str(row["digest"]),
                    fixture_id=str(row["id"]),
                    detail="unused_or_stale_declaration",
                )
            )
    return findings


def _inherited_fixture_ids(
    root: Path,
    baseline_commit: str,
    changed_paths: set[str],
    declaration: dict[str, Any] | None,
) -> set[str]:
    """Return exact fixture rows whose source was unchanged from baseline.

    This is deliberately conservative: a row is inherited only when the
    baseline declaration is readable/valid, its complete row is byte-for-
    byte equivalent to the candidate row, and the referenced source path is
    outside the candidate diff.  Changed, added, missing, duplicate, or
    altered rows are never rescued by this path.
    """
    if declaration is None:
        return set()
    try:
        raw = _git_bytes(root, "show", f"{baseline_commit}:{DECLARATION_REL}")
        baseline_declaration = _validate_declaration(_load_json_bytes(raw))
    except SecretScanError:
        # A trusted baseline scan may predate a declaration or use a package
        # that cannot be read here.  Do not infer inheritance in that case.
        return set()
    baseline_rows = {
        str(row["id"]): row for row in baseline_declaration["fixtures"]
    }
    return {
        str(row["id"])
        for row in declaration["fixtures"]
        if str(row["id"]) in baseline_rows
        and row["path"] not in changed_paths
        and row == baseline_rows[str(row["id"])]
    }


def _blob_types_and_sizes(root: Path, oids: list[str]) -> dict[str, tuple[str, int]]:
    if not oids:
        return {}
    payload = "".join(f"{oid}\n" for oid in oids)
    text = _git(root, "cat-file", "--batch-check", input_text=payload)
    info: dict[str, tuple[str, int]] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            raise SecretScanError("git_failed", f"cat-file check {line}")
        oid = parts[0]
        if parts[1] == "missing":
            raise SecretScanError("git_failed", f"missing {oid}")
        if len(parts) < 3:
            raise SecretScanError("git_failed", f"cat-file check {line}")
        info[oid] = (parts[1], int(parts[2]))
    return info


def _read_blobs(root: Path, oids: list[str]) -> dict[str, bytes]:
    if not oids:
        return {}
    payload = "".join(f"{oid}\n" for oid in oids).encode("ascii")
    raw = _git_bytes(root, "cat-file", "--batch", input_bytes=payload)
    out: dict[str, bytes] = {}
    cursor = 0
    while cursor < len(raw):
        newline = raw.find(b"\n", cursor)
        if newline < 0:
            break
        header = raw[cursor:newline].decode("ascii")
        parts = header.split()
        if len(parts) < 2:
            raise SecretScanError("git_failed", f"cat-file batch {header}")
        if parts[1] == "missing":
            raise SecretScanError("git_failed", f"missing {parts[0]}")
        if len(parts) < 3:
            raise SecretScanError("git_failed", f"cat-file batch {header}")
        oid, _kind, size_s = parts[0], parts[1], parts[2]
        size = int(size_s)
        start = newline + 1
        out[oid] = raw[start : start + size]
        cursor = start + size
        if cursor < len(raw) and raw[cursor : cursor + 1] == b"\n":
            cursor += 1
    return out


def _scan_declaration_values(payload: Any, detections: list[dict[str, Any]]) -> None:
    if not isinstance(payload, dict) or not isinstance(payload.get("fixtures"), list):
        return
    for row in payload["fixtures"]:
        if not isinstance(row, dict):
            continue
        for key in ("bytes", "purpose", "id"):
            value = row.get(key)
            if isinstance(value, str) and value:
                detections.extend(scan_text(DECLARATION_REL, f'{key}="{value}"'))


def _run_repository_scanners(root: Path) -> list[dict[str, Any]]:
    path = root / REPO_SCANNERS_REL
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SecretScanError("repository_scanners_malformed", str(exc)) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("scanners"), list):
        raise SecretScanError("repository_scanners_malformed", REPO_SCANNERS_REL)
    findings: list[dict[str, Any]] = []
    for row in payload["scanners"]:
        if not isinstance(row, dict) or not row.get("id") or not isinstance(row.get("command"), list):
            raise SecretScanError("repository_scanners_malformed", "scanner")
        command = [str(part) for part in row["command"]]
        if not command:
            raise SecretScanError("repository_scanners_malformed", "empty command")
        try:
            # Repository-owned scanners are untrusted children.  They may
            # inspect repository input, but cannot be used as a credential
            # discovery side channel.  The error is deliberately reduced to a
            # rule and scanner id; command arguments and child output never
            # enter secret-scan evidence.
            validate_argv(command)
        except MutationGuardError:
            findings.append(
                _finding(
                    kind=KIND_CREDENTIAL,
                    path=REPO_SCANNERS_REL,
                    line=None,
                    field=None,
                    rule=RULE_REPO_CREDENTIAL_DISCOVERY,
                    digest=None,
                    scanner_id=str(row["id"]),
                )
            )
            continue
        try:
            result = subprocess.run(
                command,
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
                timeout=REPO_SCANNER_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired:
            findings.append(
                _finding(
                    kind=KIND_CREDENTIAL,
                    path=REPO_SCANNERS_REL,
                    line=None,
                    field=None,
                    rule=RULE_REPO_TIMEOUT,
                    digest=None,
                    scanner_id=str(row["id"]),
                    detail=f"timeout={REPO_SCANNER_TIMEOUT_SEC}",
                )
            )
            continue
        if result.returncode != 0:
            findings.append(
                _finding(
                    kind=KIND_CREDENTIAL,
                    path=REPO_SCANNERS_REL,
                    line=None,
                    field=None,
                    rule=RULE_REPO_SCANNER,
                    digest=None,
                    scanner_id=str(row["id"]),
                    detail=f"exit={result.returncode}",
                )
            )
    return findings


def _scan_regular_blobs(
    root: Path,
    entries: list[IndexEntry],
    paths: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    detections: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    regular = [entry for entry in entries if entry.is_regular and (paths is None or entry.path in paths)]
    sizes = _blob_types_and_sizes(root, [entry.oid for entry in regular])
    readable: list[IndexEntry] = []
    for entry in regular:
        info = sizes.get(entry.oid)
        if info is None:
            findings.append(
                _finding(
                    kind=KIND_CREDENTIAL,
                    path=entry.path,
                    line=None,
                    field=None,
                    rule=RULE_GIT_FAILED,
                    digest=None,
                    detail="missing blob",
                )
            )
            continue
        _kind, size = info
        if _kind != "blob":
            continue
        readable.append(entry)
    blobs = _read_blobs(root, [entry.oid for entry in readable])
    for entry in readable:
        raw = blobs.get(entry.oid)
        if raw is None:
            findings.append(
                _finding(
                    kind=KIND_CREDENTIAL,
                    path=entry.path,
                    line=None,
                    field=None,
                    rule=RULE_GIT_FAILED,
                    digest=None,
                    detail="unread blob",
                )
            )
            continue
        text, encoding = decode_tracked_text(raw)
        if text is None:
            findings.append(
                _finding(
                    kind=KIND_SKIPPED,
                    path=entry.path,
                    line=None,
                    field=None,
                    rule=RULE_INPUT_UNDECODABLE if encoding != "binary" else "input.binary",
                    digest=None,
                    detail=encoding,
                )
            )
            continue
        detections.extend(scan_text(entry.path, text))
    return detections, findings


def _scan_worktree_managed_blobs(
    root: Path, entries: list[IndexEntry], paths: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Scan installed managed policy bytes, including expected tracked edits."""
    detections: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    tracked = {entry.path for entry in entries}
    for rel in sorted(paths):
        path = root / rel
        if not path.exists() or path.is_symlink():
            if rel in tracked:
                raise SecretScanError("change_scope_paths", f"managed path is deleted or symlinked: {rel}")
            continue
        if not path.is_file():
            raise SecretScanError("change_scope_paths", f"managed path is not a regular file: {rel}")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise SecretScanError("change_scope_paths", f"managed path is unreadable: {rel}") from exc
        text, encoding = decode_tracked_text(raw)
        if text is None:
            findings.append(
                _finding(
                    kind=KIND_SKIPPED,
                    path=rel,
                    line=None,
                    field=None,
                    rule=RULE_INPUT_UNDECODABLE if encoding != "binary" else "input.binary",
                    digest=None,
                    detail=encoding,
                )
            )
            continue
        detections.extend(scan_text(rel, text))
    return detections, findings


def _worktree_diff_statuses(root: Path, commit: str) -> list[tuple[str, str]]:
    raw = _git_bytes(
        root, "diff", "--name-status", "--find-renames=50%", "--find-copies=50%", "-z", commit, "--"
    )
    tokens = raw.split(b"\0")
    statuses: list[tuple[str, str]] = []
    index = 0
    while index < len(tokens):
        status_raw = tokens[index]
        index += 1
        if not status_raw:
            continue
        status = status_raw.decode("ascii", errors="strict")
        if index >= len(tokens) or not tokens[index]:
            raise SecretScanError("change_scope_paths", "missing worktree diff path")
        path = tokens[index].decode("utf-8", errors="strict")
        index += 1
        statuses.append((status, path))
        if status.startswith(("R", "C")):
            if index >= len(tokens) or not tokens[index]:
                raise SecretScanError("change_scope_paths", "missing rename/copy destination")
            statuses.append((status, tokens[index].decode("utf-8", errors="strict")))
            index += 1
    return statuses


def _untracked_worktree_paths(root: Path) -> list[str]:
    raw = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    return [line[3:] for line in raw.splitlines() if line.startswith("?? ")]


def _matches_declared_output(path: str, pattern: str) -> bool:
    """Match one source path against a generated-output declaration."""
    normalized = pattern.replace("\\", "/")
    if normalized in {"**", "**/*"}:
        return True
    if normalized.endswith("/**"):
        prefix = normalized[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    if normalized.startswith("**/"):
        normalized = normalized[3:]
    return fnmatch.fnmatchcase(path, normalized) or PurePosixPath(path).match(normalized)


def _package_manifest_entries(root: Path) -> list[dict[str, Any]]:
    """Read exact package entries from the source or extracted package."""
    for rel in (".ide-development/MANIFEST.json", "core/managed-core/MANIFEST.json"):
        manifest = root / rel
        if not manifest.is_file() or manifest.is_symlink():
            continue
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        entries = payload.get("files") if isinstance(payload, dict) else None
        if isinstance(entries, list):
            return [entry for entry in entries if isinstance(entry, dict)]
    return []


def _generated_manifest_contract_declared(entries: list[dict[str, Any]]) -> bool:
    """Require the package's exact generated-closure contract before allowing its manifest."""
    return any(
        entry.get("source") == GENERATED_CLOSURE_CONTRACT_SOURCE_REL
        and entry.get("destination") == GENERATED_CLOSURE_CONTRACT_DEST_REL
        for entry in entries
    )


def _generated_transaction_paths(root: Path, entries: list[dict[str, Any]]) -> set[str]:
    """Resolve generated destinations from the package manifest and closure graph.

    The package MANIFEST and generated-output closure are the only authorities
    for generated destinations.  Patterns are expanded only against declared
    manifest sources; no path prefix is ignored implicitly.
    """
    graph_paths = (
        root / "core/managed-core/config/generated-output-closure.json",
        root / ".ide-development/config/generated-output-closure.json",
        root / ".ide-development/content/config/generated-output-closure.json",
    )
    graph_path = next((path for path in graph_paths if path.is_file()), None)
    if graph_path is None:
        return set()
    try:
        graph = load_generated_output_graph(root, graph_path.relative_to(root).as_posix())
    except (ClosureError, OSError, ValueError):
        return set()

    sources = {
        str(entry.get("source")): str(entry.get("destination"))
        for entry in entries
        if isinstance(entry.get("source"), str)
        and isinstance(entry.get("destination"), str)
        and _valid_relpath(str(entry.get("destination")))
    }
    allowed: set[str] = set()
    for output in graph.outputs:
        patterns = (output.output, *output.additional_outputs)
        for source, destination in sources.items():
            if any(_matches_declared_output(source, pattern) for pattern in patterns):
                allowed.add(destination)
        # The installer writes this package identity after applying entries;
        # the closure graph declares the source-side generated MANIFEST.
        if output.output == "core/managed-core/MANIFEST.json" or _generated_manifest_contract_declared(entries):
            allowed.add(GENERATED_PACKAGE_MANIFEST_REL)
    return allowed


def _managed_migration_paths(root: Path) -> set[str]:
    """Return exact removal destinations declared by the migration catalog."""
    for rel in MIGRATION_CATALOG_RELS:
        catalog = root / rel
        if not catalog.is_file() or catalog.is_symlink():
            continue
        try:
            payload = json.loads(catalog.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            continue
        return {
            str(entry["path"])
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("action") == "remove"
            and isinstance(entry.get("path"), str)
            and _valid_relpath(str(entry["path"]))
        }
    return set()


def _managed_transaction_paths(root: Path) -> set[str]:
    """Return exact managed destinations written by an installer transaction."""
    paths = {".ide-development/installed-state.json"}
    entries = _package_manifest_entries(root)
    for entry in entries:
        destination = entry.get("destination")
        if isinstance(destination, str) and _valid_relpath(destination):
            paths.add(destination)
    paths.update(_generated_transaction_paths(root, entries))
    paths.update(_managed_migration_paths(root))
    return paths


def _change_scope_error_result(exc: SecretScanError, content_tree: str = EMPTY_TREE) -> dict[str, Any]:
    rule = {
        "change_scope_identity": RULE_CHANGE_IDENTITY,
        "change_scope_config": RULE_CHANGE_CONFIG,
        "change_scope_policy": RULE_CHANGE_CONFIG,
        "change_scope_paths": RULE_CHANGE_PATHS,
    }.get(exc.code, RULE_CHANGE_SCOPE)
    return make_result(
        content_tree=content_tree,
        findings=[
            _finding(
                kind=KIND_CREDENTIAL,
                path=".",
                line=None,
                field=None,
                rule=rule,
                digest=None,
                detail=exc.detail or exc.code,
            )
        ],
        scan_mode="change-scoped",
    )


def _scan_repository(
    root: Path,
    baseline_evidence: Any | None = None,
    requested_paths: set[str] | None = None,
) -> dict[str, Any]:
    entries = tracked_entries(root)
    if requested_paths is not None:
        entries = [entry for entry in entries if entry.path in requested_paths]
    content_tree = candidate_content_tree(root)
    scope: dict[str, Any] | None = None
    scan_paths: set[str] | None = None
    inherited: list[dict[str, Any]] = []
    if baseline_evidence is not None:
        scope = _validate_change_scoped_evidence(root, baseline_evidence)
        scan_paths = set(scope["changedPaths"]) | set(managed_scanner_policy_paths(root))
        current_paths = {entry.path for entry in entries}
        migration_paths = _managed_migration_paths(root)
        if any(
            path not in current_paths and path not in migration_paths
            for path in scope["changedPaths"]
        ):
            raise SecretScanError("change_scope_paths", "changed path is absent from candidate")
        inherited = [
            dict(row)
            for row in scope["findings"]
            if isinstance(row, dict)
            and isinstance(row.get("path"), str)
            and row["path"] not in scan_paths
        ]
    managed_paths = set(managed_scanner_policy_paths(root)) if scope is not None else set()
    index_scan_paths = (
        (scan_paths - managed_paths)
        if scan_paths is not None
        else requested_paths
    )
    detections, findings = _scan_regular_blobs(root, entries, index_scan_paths)
    if scope is not None:
        managed_detections, managed_findings = _scan_worktree_managed_blobs(root, entries, managed_paths)
        detections.extend(managed_detections)
        findings.extend(managed_findings)
    declaration = None
    decl_entry = next((entry for entry in entries if entry.path == DECLARATION_REL), None)
    if decl_entry is not None and decl_entry.is_regular:
        decl_blobs = _read_blobs(root, [decl_entry.oid])
        raw = decl_blobs.get(decl_entry.oid, b"")
        try:
            payload = _load_json_bytes(raw)
            _scan_declaration_values(payload, detections)
            declaration = _validate_declaration(payload)
        except SecretScanError as exc:
            findings.extend(_error_result(exc, content_tree)["findings"])
            declaration = None
    findings = inherited + findings
    inherited_fixture_ids = set()
    if scope is not None:
        inherited_fixture_ids = _inherited_fixture_ids(
            root,
            scope["baselineCommit"],
            scope["changedPaths"],
            declaration,
        )
    findings.extend(
        _evaluate_declarations(
            detections,
            declaration,
            content_tree,
            inherited_fixture_ids=inherited_fixture_ids,
        )
    )
    findings.extend(_run_repository_scanners(root))
    if scope is None:
        return make_result(content_tree=content_tree, findings=findings)
    return make_result(
        content_tree=content_tree,
        findings=findings,
        scan_mode="change-scoped",
        repository=scope["repository"],
        authoritative_remote_ref=scope["authoritativeRemoteRef"],
        baseline_commit=scope["baselineCommit"],
        baseline_tree=scope["baselineTree"],
        candidate_commit=scope["candidateCommit"],
        candidate_git_tree=scope["candidateGitTree"],
        managed_paths=sorted(managed_scanner_policy_paths(root)),
        config_digest=config_digest(root, tuple(managed_scanner_policy_paths(root))),
        scanned_paths=sorted(scan_paths or set()),
        inherited_finding_count=len(inherited),
    )


def scan_repository(
    root: Path,
    *,
    baseline_evidence: Any | None = None,
    baseline_evidence_path: Path | str | None = None,
    paths: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    try:
        if baseline_evidence is not None and baseline_evidence_path is not None:
            raise SecretScanError("change_scope_identity", "two baseline evidence inputs")
        if baseline_evidence_path is not None:
            try:
                baseline_evidence = json.loads(Path(baseline_evidence_path).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SecretScanError("change_scope_identity", "unreadable baseline evidence") from exc
        requested_paths = set(paths) if paths is not None else None
        return _scan_repository(root, baseline_evidence, requested_paths)
    except SecretScanError as exc:
        if baseline_evidence is not None or baseline_evidence_path is not None:
            return _change_scope_error_result(exc)
        return _error_result(exc)


def identify_synthetic_candidates(root: Path) -> list[dict[str, Any]]:
    """Identify likely synthetic fixtures. Never writes an approval."""
    root = root.resolve()
    candidates: list[dict[str, Any]] = []
    try:
        entries = tracked_entries(root)
        detections, _findings = _scan_regular_blobs(root, entries)
    except SecretScanError:
        return []
    for detection in detections:
        if detection["path"] == DECLARATION_REL or detection["realistic"]:
            continue
        if is_synthetic_value(detection["value"]) or detection["rule"] == RULE_ASSIGNMENT:
            candidates.append(
                {
                    "path": detection["path"],
                    "line": detection["line"],
                    "field": detection["field"],
                    "rule": detection["rule"],
                    "digest": detection["digest"],
                }
            )
    return candidates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--json-output")
    parser.add_argument(
        "--baseline-evidence",
        help="reuse exact trusted baseline findings from this change-scoped evidence JSON",
    )
    args = parser.parse_args(argv)
    result = scan_repository(Path(args.repo), baseline_evidence_path=args.baseline_evidence)
    text = json.dumps(result, indent=2) + "\n"
    if args.json_output:
        Path(args.json_output).write_text(text, encoding="utf-8")
    print(text, end="")
    if result["ok"]:
        return 0
    if any(row["rule"] in {RULE_GIT_FAILED, RULE_MALFORMED, RULE_REPO_MALFORMED} for row in result["findings"]):
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
