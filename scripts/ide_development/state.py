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
from .io_atomic import atomic_write_bytes
from .paths import as_posix_rel, join_under


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class FileState:
    id: str
    source_hash: str
    content_hash: str
    mode: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "sourceHash": self.source_hash,
            "contentHash": self.content_hash,
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, path_key: str, raw: Any) -> "FileState":
        if not isinstance(raw, dict):
            raise InvalidPackageError(f"installed-state entry must be object: {path_key}")
        for key in ("id", "sourceHash", "contentHash", "mode"):
            if key not in raw or not isinstance(raw[key], str):
                raise InvalidPackageError(f"installed-state.{path_key} missing {key}")
        return cls(
            id=raw["id"],
            source_hash=raw["sourceHash"],
            content_hash=raw["contentHash"],
            mode=normalize_mode(raw["mode"]),
        )


@dataclass
class InstalledState:
    schema_version: int
    package_version: str
    installed_at: str
    files: dict[str, FileState]
    package_name: str = "ide-development-managed-core"
    last_transaction_id: str | None = None

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
        return payload

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
        files[path_key] = FileState.from_dict(path_key, value)
    return InstalledState(
        schema_version=SCHEMA_VERSION,
        package_version=package_version,
        installed_at=installed_at,
        files=files,
        package_name=str(raw.get("packageName") or "ide-development-managed-core"),
        last_transaction_id=raw.get("lastTransactionId")
        if isinstance(raw.get("lastTransactionId"), str)
        else None,
    )


def save_installed_state(target_root: Path, state: InstalledState) -> None:
    path = installed_state_path(target_root)
    payload = (json.dumps(state.to_dict(), indent=2, sort_keys=False) + "\n").encode("utf-8")
    atomic_write_bytes(path, payload, mode="0644")
