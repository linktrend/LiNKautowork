"""Safe physical migration of consumer `.cursor` directory symlinks.

Never opens, reads, writes, or lists through the outside symlink target.
Rollback restores the original symlink via ``os.readlink`` target string.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .errors import ConflictError
from .paths import as_posix_rel, join_under_nofollow, path_is_symlink

# Only this consumer discovery root is migratable; other unsafe links fail closed.
MIGRATABLE_CURSOR_REL = ".cursor"


@dataclass(frozen=True)
class CursorSymlinkInfo:
    """Detected `.cursor` symlink (link path + exact readlink target string)."""

    path: str
    target: str  # exact os.readlink() bytes decoded as str; never resolved


def detect_cursor_symlink(target_root: Path) -> CursorSymlinkInfo | None:
    """Return info when consumer `.cursor` is a symlink (any target).

    Uses ``lstat`` / ``readlink`` only — never follows into the outside tree.
    """
    dest = join_under_nofollow(target_root, MIGRATABLE_CURSOR_REL)
    if not path_is_symlink(dest):
        return None
    try:
        target = os.readlink(dest)
    except OSError as exc:
        raise ConflictError(
            f"Unable to readlink migratable path {MIGRATABLE_CURSOR_REL}",
            details={"path": MIGRATABLE_CURSOR_REL, "error": str(exc)},
        ) from exc
    return CursorSymlinkInfo(path=MIGRATABLE_CURSOR_REL, target=target)


def is_under_path(rel: str, ancestor: str) -> bool:
    """True if ``rel`` is ``ancestor`` or a descendant (POSIX relative paths)."""
    rel_p = as_posix_rel(rel)
    anc_p = as_posix_rel(ancestor)
    return rel_p == anc_p or rel_p.startswith(anc_p + "/")


def is_under_any(rel: str, ancestors: set[str] | frozenset[str]) -> bool:
    return any(is_under_path(rel, a) for a in ancestors)


def path_crosses_symlink_ancestor(root: Path, rel: str) -> bool:
    """True if any strict ancestor of ``rel`` under ``root`` is a symlink.

    Walks logical components with ``lstat`` only — does not follow links.
    """
    parts = PurePosixPath(as_posix_rel(rel)).parts
    if len(parts) <= 1:
        return False
    cur = root.resolve()
    for part in parts[:-1]:
        cur = cur / part
        if path_is_symlink(cur):
            return True
        try:
            cur.lstat()
        except FileNotFoundError:
            return False
        except OSError:
            return False
    return False


def apply_migrate_symlink(target_root: Path, *, path: str, expected_target: str | None) -> None:
    """Unlink the symlink itself and mkdir a physical empty directory.

    Never ``rmtree``/read through the outside target.
    """
    dest = join_under_nofollow(target_root, path)
    if path_is_symlink(dest):
        try:
            current = os.readlink(dest)
        except OSError as exc:
            raise ConflictError(
                f"Unable to readlink before migrate: {path}",
                details={"path": path, "error": str(exc)},
            ) from exc
        if expected_target is not None and current != expected_target:
            raise ConflictError(
                f"Symlink target changed since plan for {path}",
                details={
                    "path": path,
                    "expected": expected_target,
                    "actual": current,
                },
            )
        # unlink removes the directory entry (the symlink), not the outside tree.
        dest.unlink()
        dest.mkdir(mode=0o755)
        return

    # Idempotent re-apply / recovery: physical directory already present.
    if dest.is_dir() and not path_is_symlink(dest):
        return

    raise ConflictError(
        f"MIGRATE_SYMLINK expected a symlink or physical directory at {path}",
        details={"path": path},
    )


def restore_migrated_symlink(
    target_root: Path,
    *,
    path: str,
    symlink_target: str,
) -> None:
    """Remove in-repo physical tree at ``path`` and recreate the original symlink.

    Only touches the consumer path; never opens the outside target for I/O.
    """
    if not symlink_target:
        raise ConflictError(
            f"Missing symlink target for rollback of {path}",
            details={"path": path},
        )
    dest = join_under_nofollow(target_root, path)
    # Prefer lstat so we never follow a raced symlink into outside trees.
    try:
        st = dest.lstat()
    except FileNotFoundError:
        st = None
    if st is not None and path_is_symlink(dest):
        dest.unlink()
    elif st is not None:
        import stat as stat_mod

        if stat_mod.S_ISDIR(st.st_mode):
            # Physical tree created inside the consumer — safe to remove.
            shutil.rmtree(dest)
        else:
            dest.unlink()

    # Recreate byte-for-byte link text (relative or absolute as originally stored).
    kwargs = {}
    if os.name == "nt":
        kwargs["target_is_directory"] = True
    os.symlink(symlink_target, dest, **kwargs)
