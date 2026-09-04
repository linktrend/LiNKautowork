"""Transactional apply, backup, recovery, and rollback."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .constants import INSTALLED_STATE_REL, MANAGED_CORE_DIR
from .errors import ConflictError, RollbackError
from .hashing import normalize_mode, sha256_file
from .managed_write_guard import WriteLease, is_read_only_mode, managed_write_lease, read_only_mode
from .io_atomic import atomic_write_bytes, copy_file_physical, read_file_bytes, remove_file
from .lock import exclusive_transaction_lock
from .manifest import Manifest, ManifestEntry
from .paths import encode_backup_name, git_meta_dir, join_under, join_under_nofollow, path_is_symlink
from .plan import OpKind, Plan, PlanAction
from .resolution import UpgradeResolution
from .state import FileState, InstalledState, save_installed_state, utc_now
from .symlink_migrate import (
    apply_migrate_symlink,
    is_under_any,
    path_crosses_symlink_ancestor,
    restore_migrated_symlink,
)

MANIFEST_DEST = f"{MANAGED_CORE_DIR}/MANIFEST.json"


PHASE_BACKUP = "backup"
PHASE_APPLY = "apply"
PHASE_STATE = "state"
PHASE_COMPLETE = "complete"


@dataclass
class BackupRecord:
    path: str
    existed: bool
    mode: str | None
    content_hash: str | None
    backup_name: str | None
    was_symlink: bool = False
    symlink_target: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": self.path,
            "existed": self.existed,
            "mode": self.mode,
            "contentHash": self.content_hash,
            "backupName": self.backup_name,
        }
        if self.was_symlink:
            payload["wasSymlink"] = True
            payload["symlinkTarget"] = self.symlink_target
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "BackupRecord":
        return cls(
            path=raw["path"],
            existed=bool(raw["existed"]),
            mode=raw.get("mode"),
            content_hash=raw.get("contentHash"),
            backup_name=raw.get("backupName"),
            was_symlink=bool(raw.get("wasSymlink")),
            symlink_target=raw.get("symlinkTarget"),
        )


def current_tx_dir(target_root: Path) -> Path:
    return git_meta_dir(target_root) / "current-transaction"


def last_tx_dir(target_root: Path) -> Path:
    return git_meta_dir(target_root) / "last-transaction"


def journal_path(tx_dir: Path) -> Path:
    return tx_dir / "journal.json"


def backups_dir(tx_dir: Path) -> Path:
    return tx_dir / "backups"


def read_journal(tx_dir: Path) -> dict[str, Any] | None:
    path = journal_path(tx_dir)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_journal(tx_dir: Path, payload: dict[str, Any]) -> None:
    tx_dir.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    atomic_write_bytes(journal_path(tx_dir), data, mode="0644")


def _entry_map(manifest: Manifest) -> dict[str, ManifestEntry]:
    return {e.destination: e for e in manifest.active_entries()}


def backup_migrate_symlink(target_root: Path, action: PlanAction) -> BackupRecord:
    """Record original symlink target for rollback; never read outside contents."""
    dest = join_under_nofollow(target_root, action.path)
    if not path_is_symlink(dest):
        raise ConflictError(
            f"MIGRATE_SYMLINK backup expected symlink at {action.path}",
            details={"path": action.path},
        )
    target = action.symlink_target
    if target is None:
        target = os.readlink(dest)
    else:
        # Confirm link text without following.
        current = os.readlink(dest)
        if current != target:
            raise ConflictError(
                f"Symlink target changed since plan for {action.path}",
                details={"path": action.path, "expected": target, "actual": current},
            )
    return BackupRecord(
        path=action.path,
        existed=True,
        mode=None,
        content_hash=None,
        backup_name=None,
        was_symlink=True,
        symlink_target=target,
    )


def backup_path(target_root: Path, action: PlanAction) -> BackupRecord:
    dest = join_under(target_root, action.path)
    if path_is_symlink(dest):
        raise ConflictError(
            f"Refusing to backup symlink at {action.path}",
            details={"path": action.path},
        )
    if not dest.exists():
        return BackupRecord(
            path=action.path,
            existed=False,
            mode=None,
            content_hash=None,
            backup_name=None,
        )
    if not dest.is_file():
        raise ConflictError(
            f"Refusing to backup non-file at {action.path}",
            details={"path": action.path},
        )
    name = encode_backup_name(action.path)
    return BackupRecord(
        path=action.path,
        existed=True,
        mode=normalize_mode(dest.stat().st_mode & 0o7777),
        content_hash=sha256_file(dest),
        backup_name=name,
    )


def _authorize_managed_write(lease: WriteLease | None, path: str) -> WriteLease:
    if lease is None:
        raise ConflictError("Managed transaction write requires an active lease")
    lease.assert_authorized(path)
    return lease


def _save_installed_state(
    target_root: Path, state: InstalledState, *, lease: WriteLease | None
) -> None:
    _authorize_managed_write(lease, str(INSTALLED_STATE_REL))
    save_installed_state(target_root, state)


def write_backup_file(
    tx_dir: Path,
    target_root: Path,
    record: BackupRecord,
    *,
    lease: WriteLease | None = None,
) -> None:
    _authorize_managed_write(lease, record.path)
    if not record.existed or not record.backup_name:
        return
    src = join_under(target_root, record.path)
    dest = backups_dir(tx_dir) / record.backup_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = read_file_bytes(src)
    # Backup blobs live in transaction metadata and must remain removable on
    # Windows. The original destination mode is retained separately in the
    # BackupRecord and restored from there.
    atomic_write_bytes(dest, data, mode="0644")


def apply_action(
    *,
    target_root: Path,
    package_root: Path,
    action: PlanAction,
    entries: dict[str, ManifestEntry],
    lease: WriteLease | None = None,
) -> None:
    _authorize_managed_write(lease, action.path)
    if action.op in {OpKind.NOOP, OpKind.EXTERNAL_PLAN}:
        return
    if action.op == OpKind.MIGRATE_SYMLINK:
        apply_migrate_symlink(
            target_root,
            path=action.path,
            expected_target=action.symlink_target,
        )
        return
    dest = join_under(target_root, action.path)
    if action.op == OpKind.REMOVE:
        if dest.exists():
            remove_file(dest)
        return
    entry = entries.get(action.path)
    if entry is None:
        raise ConflictError(f"No manifest entry for action path {action.path}")
    source = join_under(package_root, entry.source)
    if action.op == OpKind.MARKER_UPSERT:
        from .markers import render_marker_file

        existing = None
        if dest.exists() and dest.is_file() and not path_is_symlink(dest):
            existing = read_file_bytes(dest).decode("utf-8")
        body = read_file_bytes(source).decode("utf-8")
        begin = entry.marker_begin or ""
        end = entry.marker_end or ""
        rendered = render_marker_file(existing, body, begin, end)
        atomic_write_bytes(dest, rendered.encode("utf-8"), mode=read_only_mode(entry.mode))
        return
    copy_file_physical(source, dest, mode=read_only_mode(entry.mode))


def restore_backup(
    target_root: Path,
    tx_dir: Path,
    record: BackupRecord,
    *,
    lease: WriteLease | None = None,
) -> None:
    _authorize_managed_write(lease, record.path)
    if record.was_symlink:
        if not record.symlink_target:
            raise RollbackError(f"Missing symlink target for rollback of {record.path}")
        restore_migrated_symlink(
            target_root,
            path=record.path,
            symlink_target=record.symlink_target,
        )
        return
    if not record.existed:
        # Never follow a symlink ancestor into an outside tree when cleaning creates.
        if path_crosses_symlink_ancestor(target_root, record.path):
            return
        dest = join_under_nofollow(target_root, record.path)
        if path_is_symlink(dest) or dest.is_file():
            remove_file(dest)
        return
    dest = join_under(target_root, record.path)
    if not record.backup_name:
        raise RollbackError(f"Missing backup blob for {record.path}")
    blob = backups_dir(tx_dir) / record.backup_name
    if not blob.is_file() or path_is_symlink(blob):
        raise RollbackError(f"Backup file missing for {record.path}: {blob}")
    data = read_file_bytes(blob)
    atomic_write_bytes(dest, data, mode=record.mode or "0644")


def build_next_state(
    *,
    prior: InstalledState | None,
    manifest: Manifest,
    target_root: Path,
    actions: list[PlanAction],
    transaction_id: str | None = None,
) -> InstalledState:
    files: dict[str, FileState] = {}
    if prior is not None:
        files.update(prior.files)
    entries = _entry_map(manifest)
    for action in actions:
        if action.op == OpKind.MIGRATE_SYMLINK:
            continue
        if action.op == OpKind.REMOVE:
            files.pop(action.path, None)
            continue
        if action.op == OpKind.NOOP:
            entry = entries.get(action.path)
            if entry is None:
                continue
            dest = join_under(target_root, action.path)
            if dest.is_file() and not path_is_symlink(dest):
                files[action.path] = FileState(
                    id=entry.id,
                    source_hash=entry.source_hash,
                    content_hash=sha256_file(dest),
                    mode=normalize_mode(dest.stat().st_mode & 0o7777),
                    owner=entry.owner,
                    package_version=manifest.package_version,
                    mutability_policy=entry.mutability_policy,
                    removal_policy=entry.removal_policy,
                    ownership_class=entry.ownership_class,
                    platform=entry.platform,
                    merge_strategy=entry.merge_strategy,
                )
            continue
        if action.path == MANIFEST_DEST or action.entry_id == "package-manifest":
            dest = join_under(target_root, MANIFEST_DEST)
            if dest.is_file() and not path_is_symlink(dest):
                files[MANIFEST_DEST] = FileState(
                    id="package-manifest",
                    source_hash=action.source_hash or sha256_file(dest),
                    content_hash=sha256_file(dest),
                    mode=normalize_mode(dest.stat().st_mode & 0o7777),
                    owner=manifest.package_name,
                    package_version=manifest.package_version,
                    mutability_policy="read-only",
                    removal_policy="preserve",
                    ownership_class="managed-core",
                    platform="all",
                    merge_strategy="replace",
                )
            continue
        entry = entries[action.path]
        dest = join_under(target_root, action.path)
        files[action.path] = FileState(
            id=entry.id,
            source_hash=entry.source_hash,
            content_hash=sha256_file(dest),
            mode=normalize_mode(dest.stat().st_mode & 0o7777),
            owner=entry.owner,
            package_version=manifest.package_version,
            mutability_policy=entry.mutability_policy,
            removal_policy=entry.removal_policy,
            ownership_class=entry.ownership_class,
            platform=entry.platform,
            merge_strategy=entry.merge_strategy,
        )
    # Ensure all active manifest paths that exist are recorded
    for entry in entries.values():
        dest = join_under(target_root, entry.destination)
        if dest.is_file() and not path_is_symlink(dest):
            files[entry.destination] = FileState(
                id=entry.id,
                source_hash=entry.source_hash,
                content_hash=sha256_file(dest),
                mode=normalize_mode(dest.stat().st_mode & 0o7777),
                owner=entry.owner,
                package_version=manifest.package_version,
                mutability_policy=entry.mutability_policy,
                removal_policy=entry.removal_policy,
                ownership_class=entry.ownership_class,
                platform=entry.platform,
                merge_strategy=entry.merge_strategy,
            )
        elif entry.destination in files and not dest.exists():
            files.pop(entry.destination, None)
    return InstalledState(
        schema_version=manifest.schema_version,
        package_version=manifest.package_version,
        installed_at=utc_now(),
        files=files,
        package_name=manifest.package_name,
        last_transaction_id=transaction_id,
        manifest_hash=sha256_file(manifest.path),
    )


def _promote_current_to_last(target_root: Path) -> None:
    current = current_tx_dir(target_root)
    last = last_tx_dir(target_root)
    if last.exists():
        shutil.rmtree(last)
    if current.exists():
        last.parent.mkdir(parents=True, exist_ok=True)
        os.replace(current, last)


def _recover_interrupted_unlocked(
    target_root: Path, *, lease: WriteLease | None = None
) -> dict[str, Any] | None:
    """Recover from an interrupted transaction (caller must hold exclusive lock)."""
    if lease is None:
        raise ConflictError("Managed transaction recovery requires an active lease")
    current = current_tx_dir(target_root)
    journal = read_journal(current)
    if journal is None:
        return None
    phase = journal.get("phase")
    if phase == PHASE_COMPLETE:
        _promote_current_to_last(target_root)
        return {"recovered": False, "reason": "already-complete-promoted"}
    backups = [BackupRecord.from_dict(x) for x in journal.get("backups") or []]
    # Restore in reverse order for safety
    for record in reversed(backups):
        restore_backup(target_root, current, record, lease=lease)
    # Drop incomplete transaction after successful restore
    shutil.rmtree(current)
    return {
        "recovered": True,
        "transactionId": journal.get("transactionId"),
        "phase": phase,
        "restored": [b.path for b in backups],
    }


def recover_interrupted(target_root: Path) -> dict[str, Any] | None:
    """Recover from an interrupted transaction by restoring backups.

    Takes the exclusive transaction lock. Returns a small report dict if
    recovery ran, else None.
    """
    with exclusive_transaction_lock(target_root):
        current = current_tx_dir(target_root)
        journal = read_journal(current)
        if journal is None:
            return None
        paths = {
            record.get("path")
            for record in journal.get("backups") or []
            if isinstance(record, dict) and isinstance(record.get("path"), str)
        }
        paths.add(".ide-development/installed-state.json")
        manifest = join_under_nofollow(target_root, MANIFEST_DEST)
        manifest_digest = journal.get("manifestDigest")
        if not isinstance(manifest_digest, str):
            manifest_digest = sha256_file(manifest) if manifest.is_file() and not path_is_symlink(manifest) else "sha256:" + ("0" * 64)
        with managed_write_lease(
            target_root=target_root,
            paths=paths,
            operation="recover",
            package_version=str(journal.get("packageVersion") or "unknown"),
            manifest_digest=manifest_digest,
            transaction_id=f"recovery-{journal.get('transactionId') or uuid.uuid4()}",
            make_writable=False,
            finalize_read_only=False,
        ) as lease:
            return _recover_interrupted_unlocked(target_root, lease=lease)


def apply_plan(
    *,
    target_root: Path,
    package_root: Path,
    manifest: Manifest,
    plan: Plan,
    prior: InstalledState | None,
    resolution: UpgradeResolution | None = None,
    post_apply_check: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if plan.has_conflicts:
        raise ConflictError(
            "Refusing to apply plan with conflicts",
            details={"conflicts": [c.to_dict() for c in plan.conflicts]},
        )

    with exclusive_transaction_lock(target_root):
        lease_paths = {action.path for action in plan.mutating_actions}
        lease_paths.update({MANIFEST_DEST, ".ide-development/installed-state.json"})
        pending = read_journal(current_tx_dir(target_root))
        if isinstance(pending, dict):
            lease_paths.update(
                record.get("path")
                for record in pending.get("backups") or []
                if isinstance(record, dict) and isinstance(record.get("path"), str)
            )
        with managed_write_lease(
            target_root=target_root,
            paths=lease_paths,
            operation=plan.command if plan.command in {"install", "update", "repair"} else "repair",
            package_version=manifest.package_version,
            manifest_digest=sha256_file(manifest.path),
            transaction_id=f"lease-{uuid.uuid4()}",
            make_writable=False,
            finalize_read_only=True,
        ) as lease:
            return _apply_plan_unlocked(
                target_root=target_root,
                package_root=package_root,
                manifest=manifest,
                plan=plan,
                prior=prior,
                resolution=resolution,
                post_apply_check=post_apply_check,
                write_lease=lease,
            )


def _apply_plan_unlocked(
    *,
    target_root: Path,
    package_root: Path,
    manifest: Manifest,
    plan: Plan,
    prior: InstalledState | None,
    resolution: UpgradeResolution | None = None,
    post_apply_check: Callable[[], dict[str, Any]] | None = None,
    write_lease: WriteLease | None = None,
) -> dict[str, Any]:
    # Recover any interrupted transaction before starting a new one
    recovery = _recover_interrupted_unlocked(target_root, lease=write_lease)

    mutating = plan.mutating_actions
    if not mutating:
        # Idempotent success: no backups/journal.  Once the package manifest and
        # installed-state already describe this exact package, do not rewrite
        # installedAt (or any other committed byte) on a second install.
        dest = join_under(target_root, MANIFEST_DEST)
        manifest_hash = sha256_file(manifest.path)
        current_manifest = (
            dest.is_file()
            and not path_is_symlink(dest)
            and sha256_file(dest) == manifest_hash
            and is_read_only_mode(dest.stat().st_mode & 0o7777)
        )
        prior_manifest = prior.files.get(MANIFEST_DEST) if prior is not None else None
        if (
            prior is not None
            and prior.package_version == manifest.package_version
            and current_manifest
            and prior_manifest is not None
            and prior_manifest.content_hash == manifest_hash
            and prior.manifest_hash == manifest_hash
        ):
            return {
                "transactionId": None,
                "applied": [],
                "recovery": recovery,
                "packageVersion": manifest.package_version,
                "noop": True,
                "installedStateWritten": False,
            }
        if not dest.is_file():
            _authorize_managed_write(write_lease, MANIFEST_DEST)
            copy_file_physical(manifest.path, dest, mode="0444")
        next_state = build_next_state(
            prior=prior,
            manifest=manifest,
            target_root=target_root,
            actions=plan.actions,
            transaction_id=None,
        )
        next_state.files[MANIFEST_DEST] = FileState(
            id="package-manifest",
            source_hash=manifest_hash,
            content_hash=sha256_file(join_under(target_root, MANIFEST_DEST)),
            mode=normalize_mode(
                join_under(target_root, MANIFEST_DEST).stat().st_mode & 0o7777
            ),
            owner=manifest.package_name,
            package_version=manifest.package_version,
            mutability_policy="read-only",
            removal_policy="preserve",
            ownership_class="managed-core",
            platform="all",
            merge_strategy="replace",
        )
        _save_installed_state(target_root, next_state, lease=write_lease)
        return {
            "transactionId": None,
            "applied": [],
            "recovery": recovery,
            "packageVersion": manifest.package_version,
            "noop": True,
            "installedStateWritten": True,
        }

    current = current_tx_dir(target_root)
    if current.exists():
        raise ConflictError(
            "Incomplete transaction still present after recovery attempt",
            details={"path": str(current)},
        )

    if resolution is not None:
        for item in resolution.conflicts:
            destination = join_under_nofollow(target_root, item.path)
            if path_is_symlink(destination) or not destination.is_file() or sha256_file(destination) != item.current_digest:
                raise ConflictError(
                    "Managed upgrade resolution became stale before apply",
                    details={"path": item.path},
                )
        state_path = join_under_nofollow(target_root, ".ide-development/installed-state.json")
        if path_is_symlink(state_path) or not state_path.is_file() or sha256_file(state_path) != resolution.installed_state_digest:
            raise ConflictError("Installed-state preimage became stale before apply")

    tx_id = str(uuid.uuid4())
    journal: dict[str, Any] = {
        "schemaVersion": 1,
        "transactionId": tx_id,
        "operation": plan.command,
        "command": plan.command,
        "status": "in_progress",
        "packageName": manifest.package_name,
        "packageVersion": manifest.package_version,
        "manifestDigest": sha256_file(manifest.path),
        "phase": PHASE_BACKUP,
        "createdAt": utc_now(),
        "dryRun": False,
        "actions": [a.to_dict() for a in mutating],
        "operations": [a.to_dict() for a in mutating],
        "backups": [],
        "applied": [],
        "priorInstalledState": prior.to_dict() if prior is not None else None,
    }
    if resolution is not None:
        journal["managedUpgradeResolution"] = resolution.to_dict()
    write_journal(current, journal)

    backups: list[BackupRecord] = []
    try:
        # Always snapshot installed-state when present so rollback can restore it.
        state_action = PlanAction(
            op=OpKind.REPLACE,
            path=".ide-development/installed-state.json",
            entry_id=None,
            reason="installed-state snapshot",
        )
        state_record = backup_path(target_root, state_action)
        write_backup_file(current, target_root, state_record, lease=write_lease)
        backups.append(state_record)

        migrate_ancestors = {
            a.path for a in mutating if a.op == OpKind.MIGRATE_SYMLINK
        }

        for action in mutating:
            if action.op == OpKind.MIGRATE_SYMLINK:
                record = backup_migrate_symlink(target_root, action)
            elif is_under_any(action.path, migrate_ancestors):
                # Destinations under the migrating symlink must not be probed
                # through the outside target; treat as non-existent for backup.
                record = BackupRecord(
                    path=action.path,
                    existed=False,
                    mode=None,
                    content_hash=None,
                    backup_name=None,
                )
            else:
                record = backup_path(target_root, action)
            write_backup_file(current, target_root, record, lease=write_lease)
            backups.append(record)
            journal["backups"] = [b.to_dict() for b in backups]
            write_journal(current, journal)

        journal["backups"] = [b.to_dict() for b in backups]
        journal["phase"] = PHASE_APPLY
        write_journal(current, journal)

        entries = _entry_map(manifest)
        applied: list[str] = []
        for action in mutating:
            if action.entry_id == "package-manifest" or action.path == MANIFEST_DEST:
                # Not a files[] entry — copy the package manifest bytes directly.
                if action.op != OpKind.NOOP:
                    _authorize_managed_write(write_lease, MANIFEST_DEST)
                    copy_file_physical(
                        manifest.path,
                        join_under(target_root, MANIFEST_DEST),
                        mode="0444",
                    )
            else:
                apply_action(
                    target_root=target_root,
                    package_root=package_root,
                    action=action,
                    entries=entries,
                    lease=write_lease,
                )
            applied.append(action.path)
            journal["applied"] = applied
            write_journal(current, journal)

        # Ensure MANIFEST.json exists even when the plan had only a NOOP/missing edge.
        if MANIFEST_DEST not in applied:
            _authorize_managed_write(write_lease, MANIFEST_DEST)
            copy_file_physical(
                manifest.path,
                join_under(target_root, MANIFEST_DEST),
                mode="0444",
            )
            applied.append(MANIFEST_DEST)
            journal["applied"] = applied
            write_journal(current, journal)

        journal["phase"] = PHASE_STATE
        write_journal(current, journal)
        next_state = build_next_state(
            prior=prior,
            manifest=manifest,
            target_root=target_root,
            actions=plan.actions,
            transaction_id=tx_id,
        )
        # Record MANIFEST.json in installed-state
        next_state.files[MANIFEST_DEST] = FileState(
            id="package-manifest",
            source_hash=sha256_file(manifest.path),
            content_hash=sha256_file(join_under(target_root, MANIFEST_DEST)),
            mode=normalize_mode(
                join_under(target_root, MANIFEST_DEST).stat().st_mode & 0o7777
            ),
            owner=manifest.package_name,
            package_version=manifest.package_version,
            mutability_policy="read-only",
            removal_policy="preserve",
            ownership_class="managed-core",
            platform="all",
            merge_strategy="replace",
        )
        _save_installed_state(target_root, next_state, lease=write_lease)

        post_verification = post_apply_check() if post_apply_check is not None else None
        if post_verification is not None:
            journal["postInstallVerification"] = post_verification
            write_journal(current, journal)

        journal["phase"] = PHASE_COMPLETE
        journal["status"] = "completed"
        journal["completedAt"] = utc_now()
        journal["updatedAt"] = journal["completedAt"]
        journal["resultCode"] = "clean"
        journal["exitCode"] = 0
        write_journal(current, journal)
        _promote_current_to_last(target_root)
    except Exception as exc:
        # Best-effort rollback of this transaction
        try:
            for record in reversed(backups):
                restore_backup(target_root, current, record, lease=write_lease)
            if current.exists():
                shutil.rmtree(current)
        except Exception as rollback_exc:  # pragma: no cover
            raise RollbackError(
                f"Apply failed and rollback failed: {exc}; rollback: {rollback_exc}"
            ) from rollback_exc
        raise

    return {
        "transactionId": tx_id,
        "applied": [a.to_dict() for a in mutating],
        "recovery": recovery,
        "packageVersion": manifest.package_version,
        "backupReceipt": {
            "transactionId": tx_id,
            "backupCount": len(backups),
            "paths": [record.path for record in backups],
            "rollbackAvailable": True,
            "journal": str(last_tx_dir(target_root) / "journal.json"),
        },
        "managedUpgradeResolution": resolution.to_dict() if resolution else None,
        "postInstallVerification": post_verification,
    }


def rollback_last(target_root: Path) -> dict[str, Any]:
    """Restore exact pre-change bytes/modes from the last completed transaction."""
    with exclusive_transaction_lock(target_root):
        current_journal = read_journal(current_tx_dir(target_root))
        last = last_tx_dir(target_root)
        journal = read_journal(last)
        if journal is None:
            raise RollbackError("No completed transaction available to rollback")
        paths = {
            record.get("path")
            for record in (journal.get("backups") or [])
            if isinstance(record, dict) and isinstance(record.get("path"), str)
        }
        if isinstance(current_journal, dict):
            paths.update(
                record.get("path")
                for record in current_journal.get("backups") or []
                if isinstance(record, dict) and isinstance(record.get("path"), str)
            )
        paths.add(".ide-development/installed-state.json")
        manifest = join_under_nofollow(target_root, MANIFEST_DEST)
        manifest_digest = journal.get("manifestDigest")
        if not isinstance(manifest_digest, str):
            manifest_digest = sha256_file(manifest) if manifest.is_file() and not path_is_symlink(manifest) else "sha256:" + ("0" * 64)
        with managed_write_lease(
            target_root=target_root,
            paths=paths,
            operation="rollback",
            package_version=str(journal.get("packageVersion") or "unknown"),
            manifest_digest=manifest_digest,
            transaction_id=f"rollback-{journal.get('transactionId') or uuid.uuid4()}",
            make_writable=False,
            finalize_read_only=False,
        ) as lease:
            return _rollback_last_unlocked(target_root, lease=lease)


def _rollback_last_unlocked(
    target_root: Path, *, lease: WriteLease | None = None
) -> dict[str, Any]:
    # Prefer recovering incomplete current first
    recovery = _recover_interrupted_unlocked(target_root, lease=lease)
    last = last_tx_dir(target_root)
    journal = read_journal(last)
    if journal is None:
        raise RollbackError("No completed transaction available to rollback")
    if journal.get("phase") != PHASE_COMPLETE:
        raise RollbackError("Last transaction journal is not complete")
    backups = [BackupRecord.from_dict(x) for x in journal.get("backups") or []]
    try:
        for record in reversed(backups):
            restore_backup(target_root, last, record, lease=lease)
    except Exception as exc:
        raise RollbackError(f"Rollback failed: {exc}") from exc

    # The installed-state backup is the exact preimage.  Do not reserialize it
    # after restoring it: doing so changes formatting/timestamps and can lose
    # legacy fields even though the transaction has an exact backup.
    has_installed_state_preimage = any(
        record.path == str(INSTALLED_STATE_REL) and record.existed for record in backups
    )
    prior_state = journal.get("priorInstalledState")
    if not has_installed_state_preimage and isinstance(prior_state, dict):
        files = {
            path: FileState.from_dict(path, raw)
            for path, raw in (prior_state.get("files") or {}).items()
        }
        state = InstalledState(
            schema_version=int(prior_state.get("schemaVersion") or 1),
            package_version=str(prior_state.get("packageVersion") or ""),
            installed_at=str(prior_state.get("installedAt") or utc_now()),
            files=files,
            package_name=str(prior_state.get("packageName") or "ide-development-managed-core"),
            manifest_hash=prior_state.get("manifestHash")
            if isinstance(prior_state.get("manifestHash"), str)
            else None,
        )
        _save_installed_state(target_root, state, lease=lease)
    elif not backups:
        pass

    marker = {
        "rolledBackAt": utc_now(),
        "transactionId": journal.get("transactionId"),
        "recovery": recovery,
    }
    atomic_write_bytes(
        last / "rollback-marker.json",
        (json.dumps(marker, indent=2) + "\n").encode("utf-8"),
        mode="0644",
    )
    return {
        "transactionId": journal.get("transactionId"),
        "restored": [b.path for b in backups],
        "recovery": recovery,
    }
