"""Installed-state load/save helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import INSTALLED_STATE_REL, SCHEMA_VERSION
from .errors import InvalidPackageError
from .hashing import normalize_mode
from .managed_write_guard import READ_ONLY_POLICY, PRESERVE_REMOVAL_POLICY, is_read_only_mode
from .io_atomic import atomic_write_bytes
from .paths import as_posix_rel, join_under, path_is_symlink


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class FileState:
    id: str
    source_hash: str
    content_hash: str
    mode: str
    owner: str = "ide-development-managed-core"
    package_version: str | None = None
    mutability_policy: str = READ_ONLY_POLICY
    removal_policy: str = PRESERVE_REMOVAL_POLICY
    ownership_class: str = "managed"
    platform: str = "all"
    merge_strategy: str = "replace"

    def to_dict(self) -> dict[str, str]:
        payload: dict[str, str] = {
            "id": self.id,
            "sourceHash": self.source_hash,
            "contentHash": self.content_hash,
            "sourceDigest": self.source_hash,
            "installedDigest": self.content_hash,
            "mode": self.mode,
            "owner": self.owner,
            "mutabilityPolicy": self.mutability_policy,
            "removalPolicy": self.removal_policy,
            "ownershipClass": self.ownership_class,
            "platform": self.platform,
            "mergeStrategy": self.merge_strategy,
        }
        if self.package_version:
            payload["packageVersion"] = self.package_version
        return payload

    @classmethod
    def from_dict(cls, path_key: str, raw: Any) -> "FileState":
        if not isinstance(raw, dict):
            raise InvalidPackageError(f"installed-state entry must be object: {path_key}")
        for key in ("id", "sourceHash", "contentHash", "mode"):
            if key not in raw or not isinstance(raw[key], str):
                raise InvalidPackageError(f"installed-state.{path_key} missing {key}")
        owner = raw.get("owner", "ide-development-managed-core")
        mutability = raw.get("mutabilityPolicy", READ_ONLY_POLICY)
        removal = raw.get("removalPolicy", PRESERVE_REMOVAL_POLICY)
        if not isinstance(owner, str) or not owner.strip():
            raise InvalidPackageError(f"installed-state.{path_key} owner is invalid")
        if mutability != READ_ONLY_POLICY:
            raise InvalidPackageError(f"installed-state.{path_key} mutabilityPolicy is invalid")
        if removal not in {PRESERVE_REMOVAL_POLICY, "exact-match", "transaction-only"}:
            raise InvalidPackageError(f"installed-state.{path_key} removalPolicy is invalid")
        if "sourceDigest" in raw and raw["sourceDigest"] != raw["sourceHash"]:
            raise InvalidPackageError(f"installed-state.{path_key} source digest collision")
        if "installedDigest" in raw and raw["installedDigest"] != raw["contentHash"]:
            raise InvalidPackageError(f"installed-state.{path_key} installed digest collision")
        return cls(
            id=raw["id"],
            source_hash=raw["sourceHash"],
            content_hash=raw["contentHash"],
            mode=normalize_mode(raw["mode"]),
            owner=owner.strip(),
            package_version=(
                str(raw["packageVersion"])
                if isinstance(raw.get("packageVersion"), str) and raw["packageVersion"]
                else None
            ),
            mutability_policy=mutability,
            removal_policy=removal,
            ownership_class=str(raw.get("ownershipClass") or "managed"),
            platform=str(raw.get("platform") or "all"),
            merge_strategy=str(raw.get("mergeStrategy") or "replace"),
        )


@dataclass
class InstalledState:
    schema_version: int
    package_version: str
    installed_at: str
    files: dict[str, FileState]
    package_name: str = "ide-development-managed-core"
    last_transaction_id: str | None = None
    manifest_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schemaVersion": self.schema_version,
            "packageName": self.package_name,
            "packageVersion": self.package_version,
            "installedAt": self.installed_at,
            "files": {path: state.to_dict() for path, state in sorted(self.files.items())},
        }
        if self.last_transaction_id:
            payload["lastTransactionId"] = self.last_transaction_id
        if self.manifest_hash:
            payload["manifestHash"] = self.manifest_hash
        return payload

    def ownership_manifest(self) -> dict[str, Any]:
        """Return the explicit ownership view of this installed state."""
        return {
            "schemaVersion": SCHEMA_VERSION,
            "kind": "ide-managed-ownership",
            "packageName": self.package_name,
            "packageVersion": self.package_version,
            "manifestDigest": self.manifest_hash,
            "files": {
                path: {
                    "owner": value.owner,
                    "packageVersion": value.package_version or self.package_version,
                    "sourceDigest": value.source_hash,
                    "installedDigest": value.content_hash,
                    "mutabilityPolicy": value.mutability_policy,
                    "removalPolicy": value.removal_policy,
                    "ownershipClass": value.ownership_class,
                    "mode": value.mode,
                }
                for path, value in sorted(self.files.items())
            },
        }

    @classmethod
    def empty(cls, package_version: str) -> "InstalledState":
        return cls(
            schema_version=SCHEMA_VERSION,
            package_version=package_version,
            installed_at=utc_now(),
            files={},
        )


def installed_state_path(target_root: Path) -> Path:
    return join_under(target_root, INSTALLED_STATE_REL)


def load_installed_state(target_root: Path) -> InstalledState | None:
    path = installed_state_path(target_root)
    if not path.exists():
        return None
    if path.is_symlink():
        raise InvalidPackageError("installed-state.json must not be a symlink")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidPackageError(f"Corrupt installed-state.json: {path}") from exc
    if not isinstance(raw, dict):
        raise InvalidPackageError("installed-state.json must be a JSON object")
    if raw.get("schemaVersion") != SCHEMA_VERSION:
        raise InvalidPackageError(
            f"Unsupported installed-state schemaVersion: {raw.get('schemaVersion')}"
        )
    package_version = raw.get("packageVersion")
    if not isinstance(package_version, str) or not package_version:
        raise InvalidPackageError("installed-state packageVersion missing")
    installed_at = raw.get("installedAt")
    if not isinstance(installed_at, str) or not installed_at:
        raise InvalidPackageError("installed-state installedAt missing")
    files_raw = raw.get("files")
    if not isinstance(files_raw, dict):
        raise InvalidPackageError("installed-state files must be an object")
    files: dict[str, FileState] = {}
    for key, value in files_raw.items():
        path_key = as_posix_rel(key)
        file_state = FileState.from_dict(path_key, value)
        if file_state.package_version is not None and file_state.package_version != package_version:
            raise InvalidPackageError(
                f"installed-state.{path_key} packageVersion collision"
            )
        files[path_key] = file_state
    return InstalledState(
        schema_version=SCHEMA_VERSION,
        package_version=package_version,
        installed_at=installed_at,
        files=files,
        package_name=str(raw.get("packageName") or "ide-development-managed-core"),
            last_transaction_id=raw.get("lastTransactionId")
        if isinstance(raw.get("lastTransactionId"), str)
        else None,
        manifest_hash=raw.get("manifestHash")
        if isinstance(raw.get("manifestHash"), str)
        else None,
    )


def save_installed_state(target_root: Path, state: InstalledState) -> None:
    path = installed_state_path(target_root)
    payload = (json.dumps(state.to_dict(), indent=2, sort_keys=False) + "\n").encode("utf-8")
    atomic_write_bytes(path, payload, mode="0444")


def validate_read_only_state(target_root: Path, state: InstalledState) -> list[str]:
    """Return installed paths that violate the persisted read-only policy."""
    violations: list[str] = []
    for rel, file_state in sorted(state.files.items()):
        path = join_under(target_root, rel)
        if path_is_symlink(path) or not path.is_file():
            continue
        if file_state.mutability_policy == READ_ONLY_POLICY and not is_read_only_mode(
            path.stat().st_mode & 0o7777
        ):
            violations.append(rel)
    return violations
