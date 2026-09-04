#!/usr/bin/env python3
"""Fail-closed declarations and checks for repository mutation.

The guard is intentionally local and provider-free.  A declaration binds the
operation kind to the real Git checkout before a tool runs.  After the tool
returns, the guard compares the observed worktree with that bound identity and
scope.  Errors and evidence contain counts and identities only; file contents,
command output, and environment values are never returned.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit


SCHEMA_VERSION = 1
DECLARATION_KIND = "mutation-declaration"
EVIDENCE_KIND = "mutation-guard-evidence"
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
MODES = frozenset({"read-only", "mutating"})
EVIDENCE_VERDICTS = frozenset({"PASS", "FAIL", "HOLD"})
EVIDENCE_RUN_STATUSES = frozenset({"issued", "running", "finished", "not-issued"})
MAX_AUTHORIZED_PATHS = 1024


class MutationGuardError(ValueError):
    """A typed, sanitized declaration or post-execution failure."""

    def __init__(self, code: str, detail: str = "", *, last_known_good: "RepositoryIdentity | None" = None) -> None:
        super().__init__(code if not detail else f"{code}:{detail}")
        self.code = code
        self.detail = detail
        self.last_known_good = last_known_good

    def evidence(self, *, observed: "WorktreeSnapshot | None" = None) -> dict[str, Any]:
        """Return safe evidence without paths, values, command output, or env."""
        payload: dict[str, Any] = {
            "schemaVersion": SCHEMA_VERSION,
            "kind": EVIDENCE_KIND,
            "ok": False,
            "code": self.code,
            "lastKnownGood": self.last_known_good.to_dict() if self.last_known_good else None,
        }
        if observed is not None:
            payload["observed"] = {
                "changedPathCount": len(observed.changed_paths),
                "changedBytes": observed.changed_bytes,
            }
        return payload


@dataclass(frozen=True)
class RepositoryIdentity:
    repository: str
    ref: str
    commit: str
    tree: str
    source: str = "git"

    def to_dict(self) -> dict[str, str]:
        return {
            "repository": self.repository,
            "ref": self.ref,
            "commit": self.commit,
            "tree": self.tree,
            "source": self.source,
        }


@dataclass(frozen=True)
class MutationDeclaration:
    mode: str
    tool: str
    identity: RepositoryIdentity
    authorized_paths: tuple[str, ...]
    max_changed_files: int
    max_changed_bytes: int
    credential_discovery: bool = False
    evidence: Mapping[str, Any] | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "MutationDeclaration":
        if not isinstance(payload, Mapping):
            raise MutationGuardError("declaration_malformed", "object")
        allowed = {
            "schemaVersion", "kind", "mode", "tool", "identity", "authorizedPaths",
            "maxChangedFiles", "maxChangedBytes", "credentialDiscovery", "evidence",
        }
        if set(payload) - allowed:
            raise MutationGuardError("declaration_malformed", "unknown_field")
        if payload.get("schemaVersion") != SCHEMA_VERSION or payload.get("kind") != DECLARATION_KIND:
            raise MutationGuardError("declaration_malformed", "schema_or_kind")
        mode = payload.get("mode")
        if mode not in MODES:
            raise MutationGuardError("declaration_malformed", "mode")
        tool = payload.get("tool")
        if not isinstance(tool, str) or not tool.strip() or len(tool) > 200:
            raise MutationGuardError("declaration_malformed", "tool")

        raw_identity = payload.get("identity")
        if not isinstance(raw_identity, Mapping):
            raise MutationGuardError("declaration_malformed", "identity")
        if set(raw_identity) != {"repository", "ref", "commit", "tree", "source"}:
            raise MutationGuardError("declaration_malformed", "identity_fields")
        identity_values = {key: raw_identity.get(key) for key in raw_identity}
        if identity_values["source"] != "git":
            raise MutationGuardError("identity_untrusted", "source")
        if not isinstance(identity_values["repository"], str) or not _is_remote_repository(identity_values["repository"]):
            raise MutationGuardError("identity_untrusted", "repository")
        if not isinstance(identity_values["ref"], str) or not _valid_ref(identity_values["ref"]):
            raise MutationGuardError("declaration_malformed", "identity_ref")
        if not all(isinstance(identity_values[key], str) and SHA40_RE.fullmatch(identity_values[key]) for key in ("commit", "tree")):
            raise MutationGuardError("declaration_malformed", "identity_commit_tree")
        identity = RepositoryIdentity(**identity_values)  # type: ignore[arg-type]

        paths = payload.get("authorizedPaths")
        if not isinstance(paths, list) or len(paths) > MAX_AUTHORIZED_PATHS:
            raise MutationGuardError("declaration_malformed", "authorized_paths")
        normalized_paths: list[str] = []
        for path in paths:
            if not isinstance(path, str) or not _valid_path(path) or path in {".", "**", "*"}:
                raise MutationGuardError("scope_invalid", "authorized_paths")
            normalized_paths.append(path)
        if len(set(normalized_paths)) != len(normalized_paths):
            raise MutationGuardError("scope_invalid", "duplicate_authorized_path")

        max_files = payload.get("maxChangedFiles")
        max_bytes = payload.get("maxChangedBytes")
        if not _nonnegative_int(max_files) or not _nonnegative_int(max_bytes):
            raise MutationGuardError("declaration_malformed", "mutation_limits")
        if mode == "read-only" and (normalized_paths or max_files != 0 or max_bytes != 0):
            raise MutationGuardError("scope_invalid", "read_only_must_have_zero_scope")
        if mode == "mutating" and (not normalized_paths or max_files == 0 or max_bytes == 0):
            raise MutationGuardError("scope_invalid", "mutating_scope_required")

        discovery = payload.get("credentialDiscovery")
        if discovery is not False:
            raise MutationGuardError("credential_discovery_forbidden", "credentialDiscovery")
        evidence = payload.get("evidence")
        if evidence is not None:
            validate_worker_evidence(evidence, identity=identity)
        return cls(
            mode=mode,
            tool=tool.strip(),
            identity=identity,
            authorized_paths=tuple(normalized_paths),
            max_changed_files=max_files,
            max_changed_bytes=max_bytes,
            credential_discovery=False,
            evidence=evidence,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schemaVersion": SCHEMA_VERSION,
            "kind": DECLARATION_KIND,
            "mode": self.mode,
            "tool": self.tool,
            "identity": self.identity.to_dict(),
            "authorizedPaths": list(self.authorized_paths),
            "maxChangedFiles": self.max_changed_files,
            "maxChangedBytes": self.max_changed_bytes,
            "credentialDiscovery": False,
        }
        if self.evidence is not None:
            payload["evidence"] = dict(self.evidence)
        return payload


@dataclass(frozen=True)
class WorktreeSnapshot:
    identity: RepositoryIdentity
    changed_paths: frozenset[str]
    changed_bytes: int


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _valid_path(path: str) -> bool:
    if not path or path.startswith(("/", "~")) or "\\" in path or "\x00" in path:
        return False
    parts = path.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def _valid_ref(ref: str) -> bool:
    return bool(ref) and not ref.startswith(("-", "/")) and ".." not in ref and "\\" not in ref and "\x00" not in ref


def _is_remote_repository(value: str) -> bool:
    if not value or len(value) > 500 or any(marker in value.lower() for marker in ("mock://", "local://", "localhost")):
        return False
    if value.startswith("git@") and ":" in value:
        return bool(value.split(":", 1)[1].strip("/"))
    parts = urlsplit(value)
    return (
        parts.scheme in {"http", "https", "ssh"}
        and bool(parts.hostname)
        and not parts.username
        and not parts.password
        and bool(parts.path.strip("/"))
    )


def _sanitized_remote(value: str) -> str:
    """Normalize remote identity while removing userinfo and trailing .git."""
    if value.startswith("git@") and ":" in value:
        host, path = value.split(":", 1)
        return f"ssh://{host.split('@', 1)[-1]}/{path.removesuffix('.git').strip('/')}"
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https", "ssh"} or not parsed.hostname:
        raise MutationGuardError("identity_untrusted", "remote")
    netloc = parsed.hostname
    try:
        port = parsed.port
    except ValueError as exc:
        raise MutationGuardError("identity_untrusted", "remote") from exc
    if port:
        netloc += f":{port}"
    path = parsed.path.removesuffix(".git").rstrip("/")
    return urlunsplit((parsed.scheme, netloc, path, "", ""))


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=False
        )
    except OSError as exc:
        raise MutationGuardError("git_identity_unavailable", "git") from exc
    if result.returncode:
        raise MutationGuardError("git_identity_unavailable", "git")
    return result.stdout.strip()


def capture_identity(root: Path) -> RepositoryIdentity:
    root = root.resolve()
    remote = _sanitized_remote(_git(root, "remote", "get-url", "origin"))
    try:
        ref = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    except MutationGuardError as exc:
        if exc.code != "git_identity_unavailable":
            raise
        ref = "HEAD"
    commit = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
    tree = _git(root, "rev-parse", "--verify", "HEAD^{tree}")
    if not SHA40_RE.fullmatch(commit) or not SHA40_RE.fullmatch(tree):
        raise MutationGuardError("identity_untrusted", "git_identity")
    return RepositoryIdentity(repository=remote, ref=ref, commit=commit, tree=tree)


def _tracked_sizes(root: Path) -> dict[str, int]:
    raw = _git_bytes(root, "ls-tree", "-r", "-l", "-z", "HEAD")
    sizes: dict[str, int] = {}
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            meta, path_raw = item.split(b"\t", 1)
            fields = meta.split()
            size = 0 if fields[3] == b"-" else int(fields[3])
            path = path_raw.decode("utf-8", errors="strict")
        except (IndexError, ValueError, UnicodeDecodeError) as exc:
            raise MutationGuardError("git_state_unavailable", "tree_sizes") from exc
        if _valid_path(path):
            sizes[path] = size
    return sizes


def _git_bytes(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)
    except OSError as exc:
        raise MutationGuardError("git_state_unavailable", "git") from exc
    if result.returncode:
        raise MutationGuardError("git_state_unavailable", "git")
    return result.stdout


def _changed_paths(root: Path) -> frozenset[str]:
    raw = _git_bytes(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    paths: set[str] = set()
    tokens = raw.split(b"\0")
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        if len(token) < 4 or token[2:3] != b" ":
            raise MutationGuardError("git_state_ambiguous", "status")
        path = token[3:].decode("utf-8", errors="strict")
        if not _valid_path(path):
            raise MutationGuardError("scope_invalid", "worktree_path")
        paths.add(path)
        status = token[:2].decode("ascii", errors="strict")
        if status[0] in {"R", "C"} or status[1] in {"R", "C"}:
            if index >= len(tokens) or not tokens[index]:
                raise MutationGuardError("git_state_ambiguous", "rename")
            other = tokens[index].decode("utf-8", errors="strict")
            index += 1
            if not _valid_path(other):
                raise MutationGuardError("scope_invalid", "rename_path")
            paths.add(other)
    return frozenset(paths)


def capture_snapshot(root: Path) -> WorktreeSnapshot:
    root = root.resolve()
    identity = capture_identity(root)
    changed = _changed_paths(root)
    old_sizes = _tracked_sizes(root)
    changed_bytes = 0
    for path in changed:
        old_size = old_sizes.get(path, 0)
        candidate = root / path
        if candidate.is_symlink():
            new_size = os.lstat(candidate).st_size
        elif candidate.is_file():
            try:
                new_size = candidate.stat().st_size
            except OSError as exc:
                raise MutationGuardError("git_state_unavailable", "worktree_size") from exc
        else:
            new_size = 0
        changed_bytes += max(old_size, new_size)
    return WorktreeSnapshot(identity=identity, changed_paths=changed, changed_bytes=changed_bytes)


def validate_declaration(payload: Mapping[str, Any], root: Path | None = None) -> MutationDeclaration:
    declaration = MutationDeclaration.from_mapping(payload)
    if root is not None:
        actual = capture_identity(root)
        _assert_identity(declaration.identity, actual)
    return declaration


def _assert_identity(expected: RepositoryIdentity, actual: RepositoryIdentity) -> None:
    if expected != actual:
        raise MutationGuardError("identity_mismatch", "declaration_vs_checkout", last_known_good=actual)


def validate_argv(argv: Sequence[str], *, allow_mutation: bool = False) -> None:
    """Reject common credential-discovery probes before a child process runs."""
    words = [str(value).strip().lower() for value in argv if str(value).strip()]
    joined = " ".join(words)
    discovery = (
        re.search(r"\b(printenv|env|set)\b", joined)
        or re.search(r"\b(security\s+find-(generic|internet)-password)\b", joined)
        or re.search(r"\b(cat|head|tail|less|more|sed|awk|jq)\b[^\n]*(\.env|credentials?|passwords?|private[-_ ]?keys?)", joined)
        or re.search(r"\b(find|grep|rg)\b[^\n]*(credentials?|passwords?|private[-_ ]?keys?)", joined)
    )
    if discovery:
        raise MutationGuardError("credential_discovery_forbidden", "argv")
    if not allow_mutation and any(word in {"rm", "mv", "cp", "install", "delete", "apply", "push", "commit"} for word in words):
        raise MutationGuardError("unexpected_mutation", "argv")


class MutationGuard:
    """Validate a declaration, run one bounded operation, then verify scope."""

    def __init__(self, root: Path, declaration: MutationDeclaration | Mapping[str, Any]) -> None:
        self.root = root.resolve()
        self.declaration = (
            declaration if isinstance(declaration, MutationDeclaration) else validate_declaration(declaration, self.root)
        )
        self.before = capture_snapshot(self.root)
        _assert_identity(self.declaration.identity, self.before.identity)
        if self.before.changed_paths:
            raise MutationGuardError("unexpected_preexisting_mutation", "worktree", last_known_good=self.before.identity)

    def verify_after(self) -> WorktreeSnapshot:
        after = capture_snapshot(self.root)
        try:
            _assert_identity(self.before.identity, after.identity)
        except MutationGuardError as exc:
            raise MutationGuardError(exc.code, exc.detail, last_known_good=self.before.identity) from exc
        changed = after.changed_paths - self.before.changed_paths
        changed_bytes = max(0, after.changed_bytes - self.before.changed_bytes)
        if self.declaration.mode == "read-only" and changed:
            raise MutationGuardError("unexpected_mutation", "read_only_operation", last_known_good=self.before.identity)
        if not changed:
            return after
        root = self.root
        if any(
            (root / path).is_symlink()
            or root not in (root / path).resolve(strict=False).parents
            for path in changed
        ):
            raise MutationGuardError("unexpected_broad_mutation", "symlink_scope", last_known_good=self.before.identity)
        if any(path not in self.declaration.authorized_paths for path in changed):
            raise MutationGuardError("unexpected_broad_mutation", "path_scope", last_known_good=self.before.identity)
        if len(changed) > self.declaration.max_changed_files:
            raise MutationGuardError("unexpected_broad_mutation", "file_limit", last_known_good=self.before.identity)
        if changed_bytes > self.declaration.max_changed_bytes:
            raise MutationGuardError("unexpected_broad_mutation", "byte_limit", last_known_good=self.before.identity)
        return after

    def run(self, operation: Callable[[], Any], *, argv: Sequence[str] = ()) -> Any:
        """Run only after the declaration is bound; always verify on return."""
        if argv:
            validate_argv(argv, allow_mutation=self.declaration.mode == "mutating")
        try:
            result = operation()
        except Exception:
            # The operation's own error is authoritative; callers can still
            # inspect the pre-execution identity through ``before``.
            raise
        self.verify_after()
        return result


def read_only_declaration(root: Path, *, tool: str) -> MutationDeclaration:
    """Create a real-checkout declaration for a credential-free read-only tool."""
    identity = capture_identity(root)
    return MutationDeclaration(
        mode="read-only",
        tool=tool,
        identity=identity,
        authorized_paths=(),
        max_changed_files=0,
        max_changed_bytes=0,
        credential_discovery=False,
    )


def validate_worker_evidence(payload: Mapping[str, Any], *, identity: RepositoryIdentity | None = None) -> None:
    """Validate the SEC-02 worker-evidence fields without trusting their claims."""
    if not isinstance(payload, Mapping):
        raise MutationGuardError("evidence_malformed", "object")
    required = {
        "repository", "startingRef", "startingCommit", "startingTree", "resultingCheckpoint",
        "provider", "model", "effort", "fastMode", "authoritativeRun", "scope", "tests", "verdict", "receiptDigest",
    }
    if set(payload) - required or required - set(payload):
        raise MutationGuardError("evidence_malformed", "fields")
    if not isinstance(payload["repository"], str) or not _is_remote_repository(payload["repository"]):
        raise MutationGuardError("identity_untrusted", "evidence_repository")
    if not isinstance(payload["startingRef"], str) or not _valid_ref(payload["startingRef"]):
        raise MutationGuardError("evidence_malformed", "starting_ref")
    if not all(isinstance(payload[key], str) and SHA40_RE.fullmatch(payload[key]) for key in ("startingCommit", "startingTree")):
        raise MutationGuardError("evidence_malformed", "starting_identity")
    checkpoint = payload["resultingCheckpoint"]
    if not isinstance(checkpoint, Mapping) or set(checkpoint) != {"commit", "tree"} or not all(isinstance(checkpoint[key], str) and SHA40_RE.fullmatch(checkpoint[key]) for key in checkpoint):
        raise MutationGuardError("evidence_malformed", "resulting_checkpoint")
    if not all(isinstance(payload[key], str) and payload[key].strip() for key in ("provider", "model")):
        raise MutationGuardError("evidence_malformed", "provider_model")
    if any(any(marker in payload[key].lower() for marker in ("mock", "local", "fake")) for key in ("provider", "model")):
        raise MutationGuardError("identity_untrusted", "provider_model")
    if payload["effort"] not in {"low", "medium", "high"} or not isinstance(payload["fastMode"], bool):
        raise MutationGuardError("evidence_malformed", "execution_mode")
    run = payload["authoritativeRun"]
    if not isinstance(run, Mapping) or set(run) != {"id", "status"} or not isinstance(run["id"], str) or not run["id"].strip() or run["status"] not in EVIDENCE_RUN_STATUSES:
        raise MutationGuardError("evidence_untrusted", "authoritative_run")
    if run["id"].lower().startswith(("mock", "local", "fake", "test")):
        raise MutationGuardError("identity_untrusted", "authoritative_run")
    scope = payload["scope"]
    if not isinstance(scope, Mapping) or set(scope) != {"authorizedPaths", "maxChangedFiles", "maxChangedBytes"}:
        raise MutationGuardError("evidence_malformed", "scope")
    # Validate scope shape without requiring a non-empty mutation: SEC-02 can
    # describe a read-only run with an empty scope.
    if not isinstance(scope["authorizedPaths"], list) or not _nonnegative_int(scope["maxChangedFiles"]) or not _nonnegative_int(scope["maxChangedBytes"]):
        raise MutationGuardError("evidence_malformed", "scope")
    for path in scope["authorizedPaths"]:
        if not isinstance(path, str) or not _valid_path(path):
            raise MutationGuardError("scope_invalid", "evidence_paths")
    if identity is not None and (
        payload["repository"] != identity.repository
        or payload["startingRef"] != identity.ref
        or payload["startingCommit"] != identity.commit
        or payload["startingTree"] != identity.tree
    ):
        raise MutationGuardError("identity_mismatch", "evidence_vs_declaration")
    if not isinstance(payload["tests"], list) or any(not isinstance(test, str) or not test.strip() for test in payload["tests"]):
        raise MutationGuardError("evidence_malformed", "tests")
    if payload["verdict"] not in EVIDENCE_VERDICTS or not isinstance(payload["receiptDigest"], str) or not DIGEST_RE.fullmatch(payload["receiptDigest"]):
        raise MutationGuardError("evidence_malformed", "verdict_receipt")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--declaration", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.declaration.read_text(encoding="utf-8"))
        declaration = validate_declaration(payload, args.repo)
        snapshot = capture_snapshot(args.repo)
        if declaration.mode == "read-only" and snapshot.changed_paths:
            raise MutationGuardError("unexpected_preexisting_mutation", "worktree", last_known_good=snapshot.identity)
        print(json.dumps({"ok": True, "declaration": declaration.to_dict(), "identity": snapshot.identity.to_dict()}))
        return 0
    except (OSError, json.JSONDecodeError):
        print(json.dumps({"ok": False, "code": "declaration_unreadable", "lastKnownGood": None}))
        return 2
    except MutationGuardError as exc:
        print(json.dumps(exc.evidence()))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
