"""Validation for the explicit v2.5.2 same-version source repair receipt."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .constants import MANAGED_CORE_DIR, PACKAGE_VERSION_TARGET
from .errors import ConflictError, InvalidPackageError
from .hashing import sha256_file
from .manifest import Manifest
from .paths import as_posix_rel, join_under_nofollow, path_is_symlink
from .state import InstalledState

KIND = "ide-managed-same-version-repair"
SCHEMA_VERSION = 1
HEX40 = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
MANIFEST_DEST = f"{MANAGED_CORE_DIR}/MANIFEST.json"


@dataclass(frozen=True)
class RepairPath:
    path: str
    source: str
    old_source_digest: str
    old_installed_digest: str
    source_digest: str
    source_bytes: int


@dataclass(frozen=True)
class SameVersionRepair:
    receipt_path: Path
    target_worktree: str
    source_repository: str
    source_ref: str
    source_commit: str
    source_tree: str
    manifest_digest: str
    installed_manifest_digest: str
    paths: tuple[RepairPath, ...]
    receipt_digest: str


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise InvalidPackageError(f"Same-version repair {field} must be a sha256 digest")
    return value


def _oid(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HEX40.fullmatch(value):
        raise InvalidPackageError(f"Same-version repair {field} must be a 40-character Git OID")
    return value


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if result.returncode:
        raise InvalidPackageError(
            "Cannot verify exact source identity for same-version repair",
            details={"stderr": result.stderr.strip()},
        )
    return result.stdout.strip()


def _path(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise InvalidPackageError(f"Same-version repair {field} must be a path")
    normalized = as_posix_rel(value)
    if normalized != value:
        raise InvalidPackageError(f"Same-version repair {field} must be normalized")
    return normalized


def _load(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise InvalidPackageError(f"Same-version repair manifest must be a physical file: {path}")
    try:
        raw_bytes = path.read_bytes()
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidPackageError(f"Same-version repair manifest is not valid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise InvalidPackageError("Same-version repair manifest must be a JSON object")
    return raw, raw_bytes


def load_and_validate_same_version_repair(
    repair_path: Path,
    *,
    target_root: Path,
    package_root: Path,
    manifest: Manifest,
    prior: InstalledState | None,
) -> SameVersionRepair:
    """Validate an exact receipt before any consumer mutation is possible."""
    raw, raw_bytes = _load(repair_path.resolve(strict=False))
    if raw.get("schemaVersion") != SCHEMA_VERSION or raw.get("kind") != KIND:
        raise InvalidPackageError("Unsupported same-version repair manifest kind/version")
    if raw.get("packageVersion") != PACKAGE_VERSION_TARGET or manifest.package_version != PACKAGE_VERSION_TARGET:
        raise InvalidPackageError("Same-version repair is available only for packageVersion 2.5.2")
    if prior is None or prior.package_version != PACKAGE_VERSION_TARGET:
        raise InvalidPackageError("Same-version repair requires an installed packageVersion of 2.5.2")

    target_worktree = raw.get("targetWorktree")
    if not isinstance(target_worktree, str) or str(Path(target_worktree).resolve(strict=False)) != str(target_root.resolve()):
        raise InvalidPackageError("Same-version repair targetWorktree does not exactly match target")

    source = raw.get("source")
    if not isinstance(source, Mapping):
        raise InvalidPackageError("Same-version repair source identity is required")
    source_repository = source.get("repository")
    source_ref = source.get("ref")
    if not isinstance(source_repository, str) or not source_repository.strip():
        raise InvalidPackageError("Same-version repair source.repository is required")
    if not isinstance(source_ref, str) or not source_ref.strip():
        raise InvalidPackageError("Same-version repair source.ref is required")
    source_commit = _oid(source.get("commit"), "source.commit")
    source_tree = _oid(source.get("tree"), "source.tree")
    manifest_digest = _digest(source.get("manifestDigest"), "source.manifestDigest")
    actual_identity = (
        _git(package_root, "rev-parse", "--verify", "HEAD^{commit}"),
        _git(package_root, "rev-parse", "--verify", "HEAD^{tree}"),
    )
    if (source_commit, source_tree) != actual_identity:
        raise InvalidPackageError("Same-version repair source identity is stale")
    actual_manifest_digest = sha256_file(manifest.path)
    if manifest_digest != actual_manifest_digest:
        raise InvalidPackageError("Same-version repair source manifest digest is stale")

    installed = raw.get("installed")
    if not isinstance(installed, Mapping) or installed.get("packageVersion") != PACKAGE_VERSION_TARGET:
        raise InvalidPackageError("Same-version repair installed package identity is invalid")
    installed_manifest_digest = _digest(
        installed.get("manifestDigest"), "installed.manifestDigest"
    )
    if prior.manifest_hash != installed_manifest_digest:
        raise InvalidPackageError("Same-version repair installed manifest identity is stale")
    if installed_manifest_digest == manifest_digest:
        raise InvalidPackageError("Same-version repair requires a manifest identity difference")

    entries = {entry.destination: entry for entry in manifest.active_entries()}
    rows = raw.get("paths")
    if not isinstance(rows, list) or not rows:
        raise InvalidPackageError("Same-version repair paths must be a non-empty array")
    parsed: list[RepairPath] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise InvalidPackageError(f"Same-version repair paths[{index}] is invalid")
        rel = _path(row.get("path"), f"paths[{index}].path")
        if rel in seen or rel == MANIFEST_DEST:
            raise InvalidPackageError("Same-version repair paths contain a duplicate or manifest path")
        seen.add(rel)
        entry = entries.get(rel)
        previous = prior.files.get(rel)
        if entry is None or previous is None or entry.ownership_class == "external-state":
            raise InvalidPackageError(
                "Same-version repair path is not an IDE-managed file",
                details={"path": rel},
            )
        source_path = row.get("source")
        if source_path != entry.source:
            raise InvalidPackageError(f"Same-version repair source path is not bound to MANIFEST: {rel}")
        old_source = _digest(row.get("installedSourceDigest"), f"{rel}.installedSourceDigest")
        old_installed = _digest(row.get("installedDigest"), f"{rel}.installedDigest")
        new_source = _digest(row.get("sourceDigest"), f"{rel}.sourceDigest")
        source_file = join_under_nofollow(package_root, entry.source)
        destination = join_under_nofollow(target_root, rel)
        if path_is_symlink(source_file) or not source_file.is_file() or path_is_symlink(destination) or not destination.is_file():
            raise InvalidPackageError("Same-version repair source or destination is missing/unsafe", details={"path": rel})
        if old_source != previous.source_hash or old_installed != previous.content_hash:
            raise InvalidPackageError(f"Same-version repair installed preimage is stale: {rel}")
        if sha256_file(destination) != old_installed:
            raise ConflictError(
                "Same-version repair refuses a consumer file changed after receipt",
                details={"path": rel},
            )
        if new_source != entry.source_hash or new_source == old_source:
            raise InvalidPackageError(f"Same-version repair source digest is invalid: {rel}")
        source_bytes = row.get("sourceBytes")
        if not isinstance(source_bytes, int) or source_bytes < 0 or source_bytes != source_file.stat().st_size:
            raise InvalidPackageError(f"Same-version repair source byte identity is stale: {rel}")
        if sha256_file(source_file) != new_source:
            raise InvalidPackageError(f"Same-version repair source bytes do not match MANIFEST: {rel}")
        parsed.append(RepairPath(rel, source_path, old_source, old_installed, new_source, source_bytes))

    return SameVersionRepair(
        receipt_path=repair_path.resolve(strict=False),
        target_worktree=target_worktree,
        source_repository=source_repository,
        source_ref=source_ref,
        source_commit=source_commit,
        source_tree=source_tree,
        manifest_digest=manifest_digest,
        installed_manifest_digest=installed_manifest_digest,
        paths=tuple(sorted(parsed, key=lambda item: item.path)),
        receipt_digest="sha256:" + hashlib.sha256(raw_bytes).hexdigest(),
    )
