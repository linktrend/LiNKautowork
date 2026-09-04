"""Atomic filesystem helpers (physical files only)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .hashing import mode_int
from .paths import path_is_symlink


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def atomic_write_bytes(dest: Path, data: bytes, *, mode: str | int) -> None:
    """Write bytes to dest via temp file + os.replace. Never creates symlinks.

    Fail-closed against symlink destinations: pre-check, refuse replace when
    ``dest`` became a symlink (TOCTOU), and set mode via ``fchmod`` on the
    temp fd when available so a swapped symlink temp cannot be followed.
    """
    if path_is_symlink(dest):
        raise OSError(f"Refusing to overwrite symlink: {dest}")
    ensure_parent(dest)
    mode_value = mode_int(mode)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{dest.name}.",
        suffix=".tmp",
        dir=str(dest.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            # Mode on the open fd — avoids chmod following a raced symlink at tmp_path.
            if hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), mode_value)
            else:
                os.chmod(tmp_path, mode_value)
        # TOCTOU: dest may have become a symlink between the initial check and replace.
        # Policy refuses overwriting symlink paths (even though replace would not follow).
        if path_is_symlink(dest):
            raise OSError(f"Refusing to overwrite symlink: {dest}")
        # Windows refuses replacing a destination carrying its read-only
        # attribute. Clear that attribute only for the replace operation; the
        # replacement temp file already has the requested final mode.
        original_dest_mode: int | None = None
        if os.name == "nt" and dest.is_file():
            original_dest_mode = dest.stat().st_mode & 0o7777
            os.chmod(dest, original_dest_mode | 0o200)
        try:
            os.replace(tmp_path, dest)
        except Exception:
            if original_dest_mode is not None and dest.is_file():
                os.chmod(dest, original_dest_mode)
            raise
    except Exception:
        try:
            if tmp_path.exists() or path_is_symlink(tmp_path):
                tmp_path.unlink()
        except OSError:
            pass
        raise


def read_file_bytes(path: Path) -> bytes:
    """Read physical file bytes. Refuses symlink-following (fail closed).

    Uses ``O_NOFOLLOW`` where available and re-checks ``is_symlink`` on open
    failure / post-open so a TOCTOU symlink swap cannot follow into a target.
    """
    if path_is_symlink(path):
        raise OSError(f"Refusing to read through symlink: {path}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        if path_is_symlink(path):
            raise OSError(f"Refusing to read through symlink: {path}") from None
        err = getattr(exc, "errno", None)
        if err in {getattr(os, "ELOOP", -1), getattr(os, "EMLINK", -2)}:
            raise OSError(f"Refusing to read through symlink: {path}") from exc
        raise
    try:
        if path_is_symlink(path):
            raise OSError(f"Refusing to read through symlink: {path}")
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            return handle.read()
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass


def remove_file(path: Path) -> None:
    if path_is_symlink(path):
        path.unlink()
        return
    if path.is_file():
        original_mode: int | None = None
        if os.name == "nt":
            original_mode = path.stat().st_mode & 0o7777
            os.chmod(path, original_mode | 0o200)
        try:
            path.unlink()
        except Exception:
            if original_mode is not None and path.is_file():
                os.chmod(path, original_mode)
            raise
        return
    if path.exists():
        raise OSError(f"Refusing to remove non-file path: {path}")


def copy_file_physical(src: Path, dest: Path, *, mode: str | int) -> None:
    data = read_file_bytes(src)
    atomic_write_bytes(dest, data, mode=mode)
