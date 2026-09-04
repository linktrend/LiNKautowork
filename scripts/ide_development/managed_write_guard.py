"""Read-only managed files and scoped installer write leases.

Managed consumer files are ordinary physical files, but their write bits are
removed after every successful mutation.  The installer temporarily grants
the owner write bit only for the exact paths in its current transaction.  The
lease is an in-process capability; the transaction lock remains the authority
for cross-process exclusion.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from .errors import ConflictError, InvalidPackageError
from .hashing import mode_int, normalize_mode, sha256_bytes
from .io_atomic import atomic_write_bytes, read_file_bytes
from .paths import as_posix_rel, encode_backup_name, git_meta_dir, join_under_nofollow, path_is_symlink


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_OPERATIONS = frozenset({"install", "update", "repair", "rollback", "recover"})
_MAX_LEASE_SECONDS = 300.0
READ_ONLY_POLICY = "read-only"
PRESERVE_REMOVAL_POLICY = "preserve"
EXACT_REMOVAL_POLICY = "exact-match"


def read_only_mode(mode: str | int) -> str:
    """Return *mode* with every owner/group/other write bit removed."""
    return normalize_mode(_mode_value(mode) & ~0o222)


def is_read_only_mode(mode: str | int) -> bool:
    return (_mode_value(mode) & 0o222) == 0


def writable_mode(mode: str | int) -> str:
    """Grant only the owner write bit while a lease is active."""
    return normalize_mode(_mode_value(mode) | 0o200)


def _mode_value(mode: str | int) -> int:
    # Callers commonly pass stat_result.st_mode rather than its permission
    # subset.  Accept that representation without weakening validation.
    if isinstance(mode, int) and mode > 0o7777:
        return mode & 0o7777
    value = mode_int(mode)
    if value > 0o7777:
        value &= 0o7777
    return value


def _validated_paths(paths: Iterable[str]) -> tuple[str, ...]:
    normalized = {as_posix_rel(path) for path in paths}
    if not normalized:
        raise InvalidPackageError("Managed write lease requires a non-empty path scope")
    return tuple(sorted(normalized))


@dataclass(frozen=True)
class WriteLease:
    """Short-lived authorization for an exact managed path set."""

    target_root: Path
    transaction_id: str
    operation: str
    package_version: str
    manifest_digest: str
    paths: tuple[str, ...]
    issued_at: float
    expires_at: float
    _active: bool = False

    def assert_authorized(self, path: str | Path) -> str:
        if not self._active:
            raise ConflictError("Managed write lease is not active")
        if time.monotonic() >= self.expires_at:
            raise ConflictError(
                "Managed write lease expired",
                details={"transactionId": self.transaction_id},
            )
        rel = as_posix_rel(path)
        if rel not in self.paths:
            raise ConflictError(
                "Managed write is outside the transaction lease",
                details={"path": rel, "transactionId": self.transaction_id},
            )
        return rel

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "kind": "ide-managed-write-lease",
            "transactionId": self.transaction_id,
            "operation": self.operation,
            "packageVersion": self.package_version,
            "manifestDigest": self.manifest_digest,
            "paths": list(self.paths),
            "issuedAtMonotonic": self.issued_at,
            "expiresAtMonotonic": self.expires_at,
        }


class _LeaseContext:
    def __init__(
        self,
        *,
        target_root: Path,
        paths: Iterable[str],
        operation: str,
        package_version: str,
        manifest_digest: str,
        transaction_id: str,
        max_seconds: float,
        make_writable: bool,
        finalize_read_only: bool,
    ) -> None:
        if operation not in _OPERATIONS:
            raise InvalidPackageError(f"Unsupported managed write lease operation: {operation}")
        if not isinstance(package_version, str) or not package_version.strip():
            raise InvalidPackageError("Managed write lease packageVersion is required")
        if not isinstance(transaction_id, str) or not transaction_id.strip():
            raise InvalidPackageError("Managed write lease transactionId is required")
        if not isinstance(manifest_digest, str) or not _DIGEST.fullmatch(manifest_digest):
            raise InvalidPackageError("Managed write lease manifestDigest is invalid")
        if not 0 < max_seconds <= _MAX_LEASE_SECONDS:
            raise InvalidPackageError("Managed write lease duration is outside the safe bound")
        self.target_root = target_root.resolve()
        self.paths = _validated_paths(paths)
        now = time.monotonic()
        self.lease = WriteLease(
            target_root=self.target_root,
            transaction_id=transaction_id,
            operation=operation,
            package_version=package_version.strip(),
            manifest_digest=manifest_digest,
            paths=self.paths,
            issued_at=now,
            expires_at=now + max_seconds,
        )
        self._original_modes: dict[str, str] = {}
        self._entered = False
        self.make_writable = make_writable
        self.finalize_read_only = finalize_read_only

    def __enter__(self) -> WriteLease:
        prepared: list[tuple[str, Path, str]] = []
        for rel in self.paths:
            path = join_under_nofollow(self.target_root, rel)
            if path_is_symlink(path):
                if rel == ".cursor":
                    continue
                raise ConflictError(
                    "Managed write lease refuses a symlink destination",
                    details={"path": rel},
                )
            if path.exists():
                if not path.is_file():
                    if rel == ".cursor" and path.is_dir():
                        continue
                    raise ConflictError(
                        "Managed write lease refuses a non-file destination",
                        details={"path": rel},
                    )
                current = normalize_mode(path.stat().st_mode & 0o7777)
                self._original_modes[rel] = current
                prepared.append((rel, path, current))

        changed: list[tuple[Path, str]] = []
        try:
            # All destination validation is complete before the first mode
            # change.  If a chmod itself fails, restore every earlier change
            # before allowing acquisition to fail closed.
            if self.make_writable:
                for rel, path, current in prepared:
                    desired = writable_mode(current)
                    if desired == current:
                        continue
                    os.chmod(path, mode_int(desired))
                    changed.append((path, current))
        except BaseException:
            for path, original in reversed(changed):
                try:
                    os.chmod(path, mode_int(original))
                except OSError:
                    # Preserve the acquisition error; the close path remains
                    # fail-closed if the caller retries against this target.
                    pass
            self._original_modes.clear()
            raise
        object.__setattr__(self.lease, "_active", True)
        self._entered = True
        return self.lease

    def __exit__(self, exc_type, exc, tb) -> bool:
        if not self._entered:
            return False
        failure: Exception | None = None
        for rel in self.paths:
            path = join_under_nofollow(self.target_root, rel)
            try:
                if path_is_symlink(path):
                    if rel == ".cursor":
                        continue
                    raise ConflictError(
                        "Managed write lease found a symlink at close",
                        details={"path": rel},
                    )
                if path.is_file():
                    if exc is not None and rel in self._original_modes:
                        os.chmod(path, mode_int(self._original_modes[rel]))
                    elif self.finalize_read_only:
                        # The package mode is applied by the atomic writer.
                        # The final guard is intentionally independent of it.
                        current = normalize_mode(path.stat().st_mode & 0o7777)
                        os.chmod(path, mode_int(read_only_mode(current)))
                elif rel == ".cursor" and path.is_dir():
                    continue
            except Exception as caught:  # pragma: no cover - exercised by hostile races
                failure = caught
        object.__setattr__(self.lease, "_active", False)
        self._entered = False
        if failure is not None and exc is None:
            raise failure
        return False


def managed_write_lease(
    *,
    target_root: Path,
    paths: Iterable[str],
    operation: str,
    package_version: str,
    manifest_digest: str,
    transaction_id: str,
    max_seconds: float = 30.0,
    make_writable: bool = True,
    finalize_read_only: bool = True,
) -> Iterator[WriteLease]:
    """Grant a bounded lease for an exact path scope."""
    return _LeaseContext(
        target_root=target_root,
        paths=paths,
        operation=operation,
        package_version=package_version,
        manifest_digest=manifest_digest,
        transaction_id=transaction_id,
        max_seconds=max_seconds,
        make_writable=make_writable,
        finalize_read_only=finalize_read_only,
    )


@contextmanager
def quarantine_managed_file(
    target_root: Path,
    path: str,
    *,
    package_version: str,
    installed_digest: str | None = None,
    baseline_digest: str | None = None,
    classification: str = "candidate_central_ide_improvement",
    reason: str = "managed-file candidate export",
) -> Iterator[dict[str, object]]:
    """Export exact bytes to Git-local quarantine without changing the source.

    The context is intentionally not a write lease: candidate export is an
    evidence operation and never authorizes a consumer mutation.
    """
    rel = as_posix_rel(path)
    source = join_under_nofollow(target_root.resolve(), rel)
    if path_is_symlink(source) or not source.is_file():
        raise ConflictError("Candidate export requires a physical regular file", details={"path": rel})
    data = read_file_bytes(source)
    actual_digest = sha256_bytes(data)
    if installed_digest is not None and actual_digest != installed_digest:
        raise ConflictError(
            "Candidate export digest does not match installed preimage",
            details={"path": rel, "expected": installed_digest, "actual": actual_digest},
        )
    export_id = str(uuid.uuid4())
    root = git_meta_dir(target_root) / "quarantine" / export_id
    root.mkdir(parents=True, exist_ok=False)
    blob = root / encode_backup_name(rel)
    receipt = root / "receipt.json"
    atomic_write_bytes(blob, data, mode="0444")
    payload: dict[str, object] = {
        "schemaVersion": 1,
        "kind": "ide-managed-candidate-export",
        "exportId": export_id,
        "path": rel,
        "packageVersion": package_version,
        "installedDigest": baseline_digest or installed_digest,
        "baselineDigest": baseline_digest,
        "candidateDigest": actual_digest,
        "classification": classification,
        "reason": reason,
        "blob": blob.name,
    }
    atomic_write_bytes(
        receipt,
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        mode="0644",
    )
    yield payload


def export_candidate(*args, **kwargs) -> dict[str, object]:
    """Stable alias for :func:`quarantine_managed_file`."""
    with quarantine_managed_file(*args, **kwargs) as payload:
        return payload
