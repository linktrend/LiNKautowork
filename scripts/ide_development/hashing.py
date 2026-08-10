"""Hashing helpers (sha256, content + mode identity)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .paths import path_is_symlink


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a physical file. Refuses symlink-following (fail closed).

    Uses ``O_NOFOLLOW`` where available and re-checks ``is_symlink`` on open
    failure so a TOCTOU symlink swap between check and open cannot follow.
    """
    if path_is_symlink(path):
        raise OSError(f"Refusing to hash through symlink: {path}")
    digest = hashlib.sha256()
    flags = os.O_RDONLY
    # Prefer O_NOFOLLOW where the platform supports it (POSIX); still check
    # is_symlink above for portability and clearer errors.
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        # TOCTOU: path may have become a symlink between check and open.
        if path_is_symlink(path):
            raise OSError(f"Refusing to hash through symlink: {path}") from None
        # ELOOP/EMLINK-style failures also indicate a symlink race on some platforms.
        err = getattr(exc, "errno", None)
        if err in {getattr(os, "ELOOP", -1), getattr(os, "EMLINK", -2)}:
            raise OSError(f"Refusing to hash through symlink: {path}") from exc
        raise
    try:
        # Post-open belt: refuse if the path is a symlink (platforms without O_NOFOLLOW).
        if path_is_symlink(path):
            raise OSError(f"Refusing to hash through symlink: {path}")
        with os.fdopen(fd, "rb") as handle:
            fd = -1  # ownership transferred
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
    return "sha256:" + digest.hexdigest()


def normalize_mode(mode: int | str) -> str:
    """Return a 4-digit octal mode string (e.g. '0644').

    String modes must be valid octal (optional ``0`` / ``0o`` prefix). Decimal
    digit strings that are not valid octal (e.g. ``999``, ``rwxr``) are refused.
    """
    from .errors import InvalidPackageError

    if isinstance(mode, str):
        text = mode.strip().lower()
        if not text:
            raise InvalidPackageError("mode must be a non-empty octal string")
        if text.startswith("0o"):
            body = text[2:]
        elif text.startswith("0") and len(text) > 1 and text.isdigit():
            body = text
        else:
            body = text
        if not body or not all(c in "01234567" for c in body):
            raise InvalidPackageError(
                f"Invalid octal mode: {mode!r}",
                details={"mode": mode},
            )
        try:
            value = int(body, 8)
        except ValueError as exc:
            raise InvalidPackageError(
                f"Invalid octal mode: {mode!r}",
                details={"mode": mode},
            ) from exc
    else:
        value = int(mode)
    if value < 0 or value > 0o7777:
        raise InvalidPackageError(
            f"Invalid mode value: {mode!r}",
            details={"mode": mode},
        )
    value &= 0o7777
    return f"{value:04o}"


def mode_int(mode: str | int) -> int:
    return int(normalize_mode(mode), 8)


def modes_match(actual: str | int, expected: str | int) -> bool:
    """Compare file modes in a platform-correct way.

    On Windows, POSIX permission bits are not preserved by the filesystem the
    way Unix does (writes commonly surface as ``0666``). Content hash remains
    the identity; mode equality is treated as always matching on ``win32``.
    On POSIX, compare normalized 4-digit octal modes exactly.
    """
    import sys

    if sys.platform == "win32":
        return True
    return normalize_mode(actual) == normalize_mode(expected)
