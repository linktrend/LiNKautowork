"""Deterministic plan construction for install/update/drift."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .hashing import modes_match, normalize_mode, sha256_bytes, sha256_file
from .managed_write_guard import is_read_only_mode, read_only_mode
from .manifest import Manifest, ManifestEntry, MigrationCatalog
from .markers import extract_marker_block, render_marker_file
from .errors import ConflictError
from .paths import join_under, join_under_nofollow, path_is_symlink
from .state import InstalledState
from .symlink_migrate import detect_cursor_symlink, is_under_any, path_crosses_symlink_ancestor


class OpKind(str, Enum):
    CREATE = "create"
    REPLACE = "replace"
    REMOVE = "remove"
    MARKER_UPSERT = "marker_upsert"
    MIGRATE_SYMLINK = "migrate_symlink"
    EXTERNAL_PLAN = "external_plan"
    NOOP = "noop"


class DriftKind(str, Enum):
    MISSING = "missing"
    MODIFIED = "modified"
    MODE_CHANGED = "mode_changed"
    UNEXPECTED_SYMLINK = "unexpected_symlink"
    ORPHAN_MANAGED = "orphan_managed"
    UNKNOWN_COLLISION = "unknown_collision"
    MATCHES_SOURCE = "matches_source"
    MARKER_DRIFT = "marker_drift"
    REPOSITORY_OWNED_EXTENSION = "repository_owned_extension"
    CANDIDATE_CENTRAL_IDE_IMPROVEMENT = "candidate_central_ide_improvement"
    OBSOLETE_RESIDUE = "obsolete_residue"


class ConflictKind(str, Enum):
    UNKNOWN_CONTENT = "unknown_content"
    SYMLINK = "symlink"
    NOT_A_FILE = "not_a_file"
    CREATE_ONLY_EXISTS = "create_only_exists"
    PATH_ESCAPE = "path_escape"
    HASH_MISMATCH_OWNED = "hash_mismatch_owned"
    MARKER_CONFLICT = "marker_conflict"


@dataclass(frozen=True)
class PlanAction:
    op: OpKind
    path: str
    entry_id: str | None = None
    reason: str = ""
    source_hash: str | None = None
    mode: str | None = None
    classification: str = "missing"
    # Exact os.readlink() string for MIGRATE_SYMLINK (rollback restores it).
    symlink_target: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "op": self.op.value,
            "path": self.path,
            "reason": self.reason,
            "classification": self.classification,
        }
        if self.entry_id is not None:
            payload["entryId"] = self.entry_id
        if self.source_hash is not None:
            payload["sourceHash"] = self.source_hash
        if self.mode is not None:
            payload["mode"] = self.mode
        if self.symlink_target is not None:
            payload["symlinkTarget"] = self.symlink_target
        return payload


@dataclass(frozen=True)
class DriftItem:
    kind: DriftKind
    path: str
    detail: str = ""
    expected_hash: str | None = None
    actual_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind.value,
            "path": self.path,
            "detail": self.detail,
        }
        if self.expected_hash is not None:
            payload["expectedHash"] = self.expected_hash
        if self.actual_hash is not None:
            payload["actualHash"] = self.actual_hash
        return payload


@dataclass(frozen=True)
class ConflictItem:
    kind: ConflictKind
    path: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "path": self.path, "detail": self.detail}


@dataclass
class Plan:
    command: str
    package_version: str
    target: str
    dry_run: bool
    actions: list[PlanAction] = field(default_factory=list)
    conflicts: list[ConflictItem] = field(default_factory=list)
    drift: list[DriftItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "command": self.command,
            "packageVersion": self.package_version,
            "target": self.target,
            "dryRun": self.dry_run,
            "actions": [a.to_dict() for a in self.actions],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "drift": [d.to_dict() for d in self.drift],
            "summary": {
                "actionCount": len(self.actions),
                "mutatingActionCount": sum(
                    1 for a in self.actions if a.op not in {OpKind.NOOP, OpKind.EXTERNAL_PLAN}
                ),
                "conflictCount": len(self.conflicts),
                "driftCount": len(self.drift),
            },
        }

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)

    @property
    def has_drift(self) -> bool:
        return bool(self.drift)

    @property
    def mutating_actions(self) -> list[PlanAction]:
        return [
            a
            for a in self.actions
            if a.op not in {OpKind.NOOP, OpKind.EXTERNAL_PLAN}
        ]


def _file_mode(path: Path) -> str:
    return normalize_mode(path.stat().st_mode & 0o7777)


def _classify_marker(
    *,
    package_root: Path,
    dest: Path,
    entry: ManifestEntry,
    prior: InstalledState | None,
) -> tuple[OpKind | None, ConflictItem | None, DriftItem | None, str, str]:
    begin = entry.marker_begin or ""
    end = entry.marker_end or ""

    if path_is_symlink(dest):
        return (
            None,
            ConflictItem(ConflictKind.SYMLINK, entry.destination, "destination is a symlink"),
            DriftItem(DriftKind.UNEXPECTED_SYMLINK, entry.destination, "symlink at managed path"),
            "symlink",
            "unsafe_link",
        )
    if dest.exists() and not dest.is_file():
        return (
            None,
            ConflictItem(ConflictKind.NOT_A_FILE, entry.destination, "destination is not a file"),
            None,
            "not-a-file",
            "unknown_conflict",
        )

    if not dest.exists():
        return OpKind.MARKER_UPSERT, None, None, "create marker file", "missing"

    try:
        existing = dest.read_text(encoding="utf-8")
        parts = extract_marker_block(existing, begin, end)
        rendered = render_marker_file(
            existing,
            join_under(package_root, entry.source).read_text(encoding="utf-8"),
            begin,
            end,
        )
    except ConflictError as exc:
        return (
            None,
            ConflictItem(ConflictKind.MARKER_CONFLICT, entry.destination, str(exc)),
            DriftItem(DriftKind.MARKER_DRIFT, entry.destination, "marker pair corrupted"),
            "marker-conflict",
            "marker_conflict",
        )

    actual_hash = sha256_bytes(existing.encode("utf-8"))
    if rendered == existing:
        if not modes_match(_file_mode(dest), read_only_mode(entry.mode)):
            return OpKind.MARKER_UPSERT, None, None, "repair managed marker mode", "managed_upgrade"
        classification = "repository_owned_extension" if parts.before or parts.after else "match"
        return OpKind.NOOP, None, None, "marker block already matches", classification

    prior_file = prior.files.get(entry.destination) if prior else None
    if prior_file is None and not parts.had_markers:
        return OpKind.MARKER_UPSERT, None, None, "append managed markers", "managed_upgrade"
    if prior_file is None and parts.had_markers:
        return OpKind.MARKER_UPSERT, None, None, "upsert existing markers", "managed_upgrade"

    if prior_file and prior_file.content_hash != actual_hash:
        if parts.had_markers:
            return OpKind.MARKER_UPSERT, None, None, "repair drifted marker region", "managed_upgrade"
        return (
            None,
            ConflictItem(
                ConflictKind.HASH_MISMATCH_OWNED,
                entry.destination,
                "managed marker file drifted without markers",
            ),
            DriftItem(
                DriftKind.MODIFIED,
                entry.destination,
                "managed content hash mismatch",
                expected_hash=prior_file.content_hash,
                actual_hash=actual_hash,
            ),
            "owned-drift",
            "unknown_conflict",
        )

    return OpKind.MARKER_UPSERT, None, None, "update marker block", "managed_upgrade"


def _classify_existing(
    *,
    package_root: Path,
    dest: Path,
    entry: ManifestEntry,
    prior: InstalledState | None,
    authorized_replacements: frozenset[str] = frozenset(),
) -> tuple[OpKind | None, ConflictItem | None, DriftItem | None, str, str]:
    rel = entry.destination

    if entry.merge_strategy == "external-plan-only" or entry.ownership_class == "external-state":
        return OpKind.EXTERNAL_PLAN, None, None, "external-state plan only", "match"

    if entry.merge_strategy == "marker-upsert" or entry.ownership_class == "managed-marker":
        return _classify_marker(
            package_root=package_root, dest=dest, entry=entry, prior=prior
        )

    if path_is_symlink(dest):
        return (
            None,
            ConflictItem(ConflictKind.SYMLINK, rel, "destination is a symlink"),
            DriftItem(DriftKind.UNEXPECTED_SYMLINK, rel, "symlink at managed path"),
            "symlink",
            "unsafe_link",
        )
    if dest.exists() and not dest.is_file():
        return (
            None,
            ConflictItem(ConflictKind.NOT_A_FILE, rel, "destination is not a regular file"),
            None,
            "not-a-file",
            "unknown_conflict",
        )

    prior_file = prior.files.get(rel) if prior else None
    if not dest.exists():
        if entry.merge_strategy == "remove-if-matches":
            return OpKind.NOOP, None, None, "already absent", "match"
        return OpKind.CREATE, None, None, "missing destination", "missing"

    actual_hash = sha256_file(dest)
    actual_mode = _file_mode(dest)

    desired_mode = read_only_mode(entry.mode)
    if actual_hash == entry.source_hash and modes_match(actual_mode, desired_mode):
        return OpKind.NOOP, None, None, "already matches package", "match"

    if entry.merge_strategy == "create-only":
        if prior_file is None:
            return (
                None,
                ConflictItem(
                    ConflictKind.CREATE_ONLY_EXISTS,
                    rel,
                    "create-only destination already exists",
                ),
                DriftItem(
                    DriftKind.UNKNOWN_COLLISION,
                    rel,
                    "unmanaged file blocks create-only",
                    actual_hash=actual_hash,
                ),
                "create-only-exists",
                "consumer_owned",
            )
        return OpKind.NOOP, None, None, "create-only preserves owned file", "match"

    if entry.merge_strategy == "remove-if-matches":
        if actual_hash == entry.source_hash:
            return OpKind.REMOVE, None, None, "exact match remove-if-matches", "supersede_exact"
        return (
            None,
            ConflictItem(
                ConflictKind.UNKNOWN_CONTENT,
                rel,
                "remove-if-matches hash does not match; refusing removal",
            ),
            DriftItem(
                DriftKind.MODIFIED,
                rel,
                "content differs from removable identity",
                expected_hash=entry.source_hash,
                actual_hash=actual_hash,
            ),
            "remove-hash-mismatch",
            "supersede_mismatch",
        )

    # replace
    if prior_file is None:
        if actual_hash == entry.source_hash:
            if not modes_match(actual_mode, entry.mode):
                return OpKind.REPLACE, None, None, "adopt matching content; fix read-only mode", "managed_upgrade"
            return OpKind.NOOP, None, None, "matching unmanaged content", "match"
        return (
            None,
            ConflictItem(
                ConflictKind.UNKNOWN_CONTENT,
                rel,
                "existing unmanaged content differs from package",
            ),
            DriftItem(
                DriftKind.UNKNOWN_COLLISION,
                rel,
                "unmanaged differing content",
                expected_hash=entry.source_hash,
                actual_hash=actual_hash,
            ),
            "unknown-content",
            "consumer_owned",
        )

    if prior_file.content_hash != actual_hash:
        if rel in authorized_replacements:
            return OpKind.REPLACE, None, None, "explicit digest-bound provider supersedes", "managed_upgrade"
        if actual_hash == entry.source_hash:
            return OpKind.REPLACE, None, None, "repair state to matching package bytes", "managed_upgrade"
        return (
            None,
            ConflictItem(
                ConflictKind.HASH_MISMATCH_OWNED,
                rel,
                "managed file drifted from installed-state; refusing blind overwrite",
            ),
            DriftItem(
                DriftKind.MODIFIED,
                rel,
                "managed content hash mismatch",
                expected_hash=prior_file.content_hash,
                actual_hash=actual_hash,
            ),
            "owned-drift",
            "unknown_conflict",
        )

    return OpKind.REPLACE, None, None, "update managed content", "managed_upgrade"


def _plan_as_missing_under_migrate(
    entry: ManifestEntry,
) -> tuple[OpKind | None, str, str]:
    """Classify managed destinations under a migrating symlink as absent.

    Must not probe through the outside target (exists/read/hash/list).
    """
    if entry.merge_strategy == "external-plan-only" or entry.ownership_class == "external-state":
        return OpKind.EXTERNAL_PLAN, "external-state plan only", "match"
    if entry.merge_strategy == "remove-if-matches":
        return OpKind.NOOP, "already absent (under migrating symlink)", "match"
    if entry.merge_strategy == "marker-upsert" or entry.ownership_class == "managed-marker":
        return OpKind.MARKER_UPSERT, "create marker file after symlink migrate", "missing"
    return OpKind.CREATE, "missing destination after symlink migrate", "missing"


def build_plan(
    *,
    command: str,
    package_root: Path,
    target_root: Path,
    manifest: Manifest,
    migration: MigrationCatalog,
    prior: InstalledState | None,
    dry_run: bool,
    authorized_replacements: frozenset[str] = frozenset(),
) -> Plan:
    plan = Plan(
        command=command,
        package_version=manifest.package_version,
        target=str(target_root),
        dry_run=dry_run,
    )

    active_entries = list(manifest.active_entries())
    managed_paths = {e.destination for e in active_entries}

    # Migratable consumer `.cursor` symlink → physical empty dir (then normal creates).
    migrate_ancestors: set[str] = set()
    cursor_link = detect_cursor_symlink(target_root)
    if cursor_link is not None:
        plan.actions.append(
            PlanAction(
                op=OpKind.MIGRATE_SYMLINK,
                path=cursor_link.path,
                entry_id="migrate-cursor-symlink",
                reason="migrate .cursor symlink to physical directory (never follow outside)",
                classification="unsafe_link",
                symlink_target=cursor_link.target,
            )
        )
        migrate_ancestors.add(cursor_link.path)

    def dest_for(rel: str) -> Path:
        if is_under_any(rel, migrate_ancestors):
            return join_under_nofollow(target_root, rel)
        logical = join_under_nofollow(target_root, rel)
        # Leaf or ancestor symlink (other than migratable .cursor) must fail closed
        # as unsafe_link — do not resolve-follow into PATH_ESCAPE.
        if path_is_symlink(logical) or path_crosses_symlink_ancestor(target_root, rel):
            return logical
        return join_under(target_root, rel)

    for entry in active_entries:
        if is_under_any(entry.destination, migrate_ancestors):
            # Do not resolve/stat/read through the external `.cursor` symlink.
            op, reason, classification = _plan_as_missing_under_migrate(entry)
            if op is None:
                continue
            plan.actions.append(
                PlanAction(
                    op=op,
                    path=entry.destination,
                    entry_id=entry.id,
                    reason=reason,
                    source_hash=entry.source_hash,
                    mode=entry.mode,
                    classification=classification,
                )
            )
            continue

        dest = dest_for(entry.destination)
        if path_crosses_symlink_ancestor(target_root, entry.destination) and not path_is_symlink(
            dest
        ):
            plan.conflicts.append(
                ConflictItem(
                    ConflictKind.SYMLINK,
                    entry.destination,
                    "path crosses a non-migratable symlink ancestor",
                )
            )
            if command in {"drift", "verify"}:
                plan.drift.append(
                    DriftItem(
                        DriftKind.UNEXPECTED_SYMLINK,
                        entry.destination,
                        "symlink ancestor blocks managed path",
                    )
                )
            continue

        op, conflict, drift, reason, classification = _classify_existing(
            package_root=package_root,
            dest=dest,
            entry=entry,
            prior=prior,
            authorized_replacements=authorized_replacements,
        )
        if conflict is not None:
            plan.conflicts.append(conflict)
        if drift is not None and command in {"drift", "verify"}:
            plan.drift.append(drift)
        if op is None:
            continue
        plan.actions.append(
            PlanAction(
                op=op,
                path=entry.destination,
                entry_id=entry.id,
                reason=reason,
                source_hash=entry.source_hash,
                mode=entry.mode,
                classification=classification,
            )
        )

    for mig in migration.entries:
        if mig.path in managed_paths:
            continue
        if is_under_any(mig.path, migrate_ancestors):
            # Obsolete paths under migrating symlink are absent in-repo; no-op.
            plan.actions.append(
                PlanAction(
                    op=OpKind.NOOP,
                    path=mig.path,
                    entry_id=mig.identity,
                    reason="migration target absent (under migrating symlink)",
                    classification="match",
                )
            )
            continue
        dest = dest_for(mig.path)
        if path_is_symlink(dest):
            plan.conflicts.append(
                ConflictItem(ConflictKind.SYMLINK, mig.path, "migration target is symlink")
            )
            continue
        if not dest.exists():
            plan.actions.append(
                PlanAction(
                    op=OpKind.NOOP,
                    path=mig.path,
                    entry_id=mig.identity,
                    reason="migration target absent",
                    classification="match",
                )
            )
            continue
        if not dest.is_file():
            plan.conflicts.append(
                ConflictItem(ConflictKind.NOT_A_FILE, mig.path, "migration target not a file")
            )
            continue
        actual = sha256_file(dest)
        if actual != mig.content_hash:
            plan.conflicts.append(
                ConflictItem(
                    ConflictKind.UNKNOWN_CONTENT,
                    mig.path,
                    "migration hash mismatch; refusing removal",
                )
            )
            if command in {"drift", "verify"}:
                plan.drift.append(
                    DriftItem(
                        DriftKind.MODIFIED,
                        mig.path,
                        "migration identity mismatch",
                        expected_hash=mig.content_hash,
                        actual_hash=actual,
                    )
                )
            continue
        plan.actions.append(
            PlanAction(
                op=OpKind.REMOVE,
                path=mig.path,
                entry_id=mig.identity,
                reason=f"migration remove exact match ({mig.identity})",
                source_hash=mig.content_hash,
                classification="supersede_exact",
            )
        )

    if prior is not None:
        remove_paths = {a.path for a in plan.actions if a.op == OpKind.REMOVE}
        for rel, file_state in sorted(prior.files.items()):
            if rel in managed_paths or rel in remove_paths:
                continue
            if is_under_any(rel, migrate_ancestors):
                # Prior state under migrating symlink cannot be probed safely.
                if command in {"drift", "verify"}:
                    plan.drift.append(
                        DriftItem(
                            DriftKind.ORPHAN_MANAGED,
                            rel,
                            "state entry under migrating symlink (not probed)",
                        )
                    )
                continue
            dest = dest_for(rel)
            if not dest.exists():
                if command in {"drift", "verify"}:
                    plan.drift.append(
                        DriftItem(DriftKind.ORPHAN_MANAGED, rel, "state entry missing on disk")
                    )
                continue
            if path_is_symlink(dest) or not dest.is_file():
                plan.conflicts.append(
                    ConflictItem(
                        ConflictKind.NOT_A_FILE,
                        rel,
                        "orphan managed path is not a regular file",
                    )
                )
                continue
            actual = sha256_file(dest)
            if actual != file_state.content_hash:
                plan.conflicts.append(
                    ConflictItem(
                        ConflictKind.HASH_MISMATCH_OWNED,
                        rel,
                        "orphan managed path drifted; refusing automatic removal",
                    )
                )
                if command in {"drift", "verify"}:
                    plan.drift.append(
                        DriftItem(
                            DriftKind.MODIFIED,
                            rel,
                            "orphan managed drift",
                            expected_hash=file_state.content_hash,
                            actual_hash=actual,
                        )
                    )
            elif command in {"drift", "verify"}:
                plan.drift.append(
                    DriftItem(
                        DriftKind.ORPHAN_MANAGED,
                        rel,
                        "managed path no longer in manifest (preserved without migration)",
                        expected_hash=file_state.content_hash,
                        actual_hash=actual,
                    )
                )

    # Always plan materialization of package MANIFEST.json into consumer core.
    from .constants import MANAGED_CORE_DIR

    manifest_dest = f"{MANAGED_CORE_DIR}/MANIFEST.json"
    manifest_hash = sha256_file(manifest.path)
    dest = dest_for(manifest_dest)
    if path_is_symlink(dest):
        plan.conflicts.append(
            ConflictItem(ConflictKind.SYMLINK, manifest_dest, "MANIFEST destination is symlink")
        )
    elif not dest.exists():
        plan.actions.append(
            PlanAction(
                op=OpKind.CREATE,
                path=manifest_dest,
                entry_id="package-manifest",
                reason="materialize package MANIFEST.json",
                source_hash=manifest_hash,
                mode="0644",
                classification="missing",
            )
        )
    elif dest.is_file() and sha256_file(dest) == manifest_hash:
        plan.actions.append(
            PlanAction(
                op=OpKind.NOOP,
                path=manifest_dest,
                entry_id="package-manifest",
                reason="MANIFEST.json already matches package",
                source_hash=manifest_hash,
                mode="0644",
                classification="match",
            )
        )
    elif dest.is_file():
        prior_file = prior.files.get(manifest_dest) if prior else None
        if prior_file is None and sha256_file(dest) != manifest_hash:
            plan.conflicts.append(
                ConflictItem(
                    ConflictKind.UNKNOWN_CONTENT,
                    manifest_dest,
                    "existing MANIFEST.json differs from package and is not owned",
                )
            )
        else:
            plan.actions.append(
                PlanAction(
                    op=OpKind.REPLACE,
                    path=manifest_dest,
                    entry_id="package-manifest",
                    reason="update package MANIFEST.json",
                    source_hash=manifest_hash,
                    mode="0644",
                    classification="managed_upgrade",
                )
            )

    # migrate_symlink must run before creates under that path; path sort does this
    # (".cursor" < ".cursor/..."). Op tie-break keeps migrate before other ops.
    plan.actions.sort(
        key=lambda a: (
            a.path,
            0 if a.op == OpKind.MIGRATE_SYMLINK else 1,
            a.op.value,
            a.entry_id or "",
        )
    )
    plan.conflicts.sort(key=lambda c: (c.path, c.kind.value))
    plan.drift.sort(key=lambda d: (d.path, d.kind.value))
    return plan


def build_drift_report(
    *,
    package_root: Path,
    target_root: Path,
    manifest: Manifest,
    prior: InstalledState | None,
    migration: MigrationCatalog | None = None,
) -> list[DriftItem]:
    items: list[DriftItem] = []
    cursor_link = detect_cursor_symlink(target_root)
    migrate_ancestors = {cursor_link.path} if cursor_link is not None else set()

    for entry in manifest.active_entries():
        if entry.merge_strategy == "external-plan-only":
            continue
        if is_under_any(entry.destination, migrate_ancestors):
            items.append(
                DriftItem(
                    DriftKind.UNEXPECTED_SYMLINK,
                    entry.destination,
                    "ancestor .cursor symlink pending physical migrate",
                )
            )
            continue
        dest = join_under(target_root, entry.destination)
        prior_file = prior.files.get(entry.destination) if prior else None
        if path_is_symlink(dest):
            items.append(
                DriftItem(DriftKind.UNEXPECTED_SYMLINK, entry.destination, "symlink present")
            )
            continue
        if not dest.exists():
            items.append(
                DriftItem(
                    DriftKind.MISSING,
                    entry.destination,
                    "managed file missing",
                    expected_hash=entry.source_hash,
                )
            )
            continue
        if not dest.is_file():
            items.append(
                DriftItem(DriftKind.UNKNOWN_COLLISION, entry.destination, "not a regular file")
            )
            continue

        if entry.merge_strategy == "marker-upsert":
            begin = entry.marker_begin or ""
            end = entry.marker_end or ""
            try:
                existing = dest.read_text(encoding="utf-8")
                parts = extract_marker_block(existing, begin, end)
                rendered = render_marker_file(
                    existing,
                    join_under(package_root, entry.source).read_text(encoding="utf-8"),
                    begin,
                    end,
                )
            except Exception as exc:  # ConflictError etc.
                items.append(
                    DriftItem(
                        DriftKind.MARKER_DRIFT,
                        entry.destination,
                        f"marker error: {exc}",
                    )
                )
                continue
            if rendered == existing:
                if not modes_match(_file_mode(dest), read_only_mode(entry.mode)):
                    items.append(
                        DriftItem(
                            DriftKind.MODE_CHANGED,
                            entry.destination,
                            "managed marker file is writable",
                            expected_hash=entry.source_hash,
                            actual_hash=sha256_bytes(existing.encode("utf-8")),
                        )
                    )
                    continue
                if parts.before or parts.after:
                    items.append(
                        DriftItem(
                            DriftKind.REPOSITORY_OWNED_EXTENSION,
                            entry.destination,
                            "consumer text outside managed markers is preserved",
                            expected_hash=entry.source_hash,
                            actual_hash=sha256_bytes(existing.encode("utf-8")),
                        )
                    )
                    continue
                items.append(
                    DriftItem(
                        DriftKind.MATCHES_SOURCE,
                        entry.destination,
                        "ok",
                        expected_hash=entry.source_hash,
                    )
                )
            else:
                items.append(
                    DriftItem(
                        DriftKind.MARKER_DRIFT,
                        entry.destination,
                        "marker region differs from package",
                        expected_hash=entry.source_hash,
                        actual_hash=sha256_bytes(existing.encode("utf-8")),
                    )
                )
            continue

        actual = sha256_file(dest)
        actual_mode = _file_mode(dest)
        if prior_file and prior_file.content_hash != actual:
            items.append(
                DriftItem(
                    DriftKind.MODIFIED,
                    entry.destination,
                    "differs from installed-state",
                    expected_hash=prior_file.content_hash,
                    actual_hash=actual,
                )
            )
        elif actual != entry.source_hash:
            if prior_file is None:
                items.append(
                    DriftItem(
                        DriftKind.UNKNOWN_COLLISION,
                        entry.destination,
                        "unmanaged content differs from package",
                        expected_hash=entry.source_hash,
                        actual_hash=actual,
                    )
                )
            else:
                items.append(
                    DriftItem(
                        DriftKind.MODIFIED,
                        entry.destination,
                        "differs from package sourceHash",
                        expected_hash=entry.source_hash,
                        actual_hash=actual,
                    )
                )
        elif not modes_match(actual_mode, read_only_mode(entry.mode)):
            items.append(
                DriftItem(
                    DriftKind.MODE_CHANGED,
                    entry.destination,
                    f"mode {actual_mode} != {entry.mode}",
                    expected_hash=entry.source_hash,
                    actual_hash=actual,
                )
            )
        else:
            items.append(
                DriftItem(
                    DriftKind.MATCHES_SOURCE,
                    entry.destination,
                    "ok",
                    expected_hash=entry.source_hash,
                    actual_hash=actual,
                )
            )
    manifest_dest = join_under_nofollow(target_root, ".ide-development/MANIFEST.json")
    if path_is_symlink(manifest_dest):
        items.append(DriftItem(DriftKind.UNEXPECTED_SYMLINK, ".ide-development/MANIFEST.json", "installed manifest is a symlink"))
    elif not manifest_dest.is_file():
        items.append(DriftItem(DriftKind.MISSING, ".ide-development/MANIFEST.json", "installed manifest missing"))
    elif sha256_file(manifest_dest) != sha256_file(manifest.path):
        expected_manifest_hash = sha256_file(manifest.path)
        items.append(DriftItem(DriftKind.MODIFIED, ".ide-development/MANIFEST.json", "installed manifest differs from package", expected_hash=expected_manifest_hash, actual_hash=sha256_file(manifest_dest)))
    elif not is_read_only_mode(manifest_dest.stat().st_mode & 0o7777):
        items.append(DriftItem(DriftKind.MODE_CHANGED, ".ide-development/MANIFEST.json", "installed manifest is writable"))

    state_dest = join_under_nofollow(target_root, ".ide-development/installed-state.json")
    if state_dest.is_file() and not path_is_symlink(state_dest) and not is_read_only_mode(state_dest.stat().st_mode & 0o7777):
        items.append(DriftItem(DriftKind.MODE_CHANGED, ".ide-development/installed-state.json", "installed state is writable"))

    if migration is not None:
        active_paths = {entry.destination for entry in manifest.active_entries()}
        for obsolete in migration.entries:
            if obsolete.path in active_paths:
                continue
            dest = join_under_nofollow(target_root, obsolete.path)
            if path_is_symlink(dest):
                items.append(
                    DriftItem(
                        DriftKind.UNKNOWN_COLLISION,
                        obsolete.path,
                        "obsolete residue is a symlink",
                    )
                )
            elif dest.is_file():
                actual = sha256_file(dest)
                if actual == obsolete.content_hash:
                    items.append(
                        DriftItem(
                            DriftKind.OBSOLETE_RESIDUE,
                            obsolete.path,
                            "exact obsolete managed residue is removable in a transaction",
                            expected_hash=obsolete.content_hash,
                            actual_hash=actual,
                        )
                    )
                else:
                    items.append(
                        DriftItem(
                            DriftKind.MODIFIED,
                            obsolete.path,
                            "obsolete residue differs from its reviewed identity",
                            expected_hash=obsolete.content_hash,
                            actual_hash=actual,
                        )
                    )
    items.sort(key=lambda d: (d.path, d.kind.value))
    return items


def meaningful_drift(items: list[DriftItem]) -> list[DriftItem]:
    return [
        i
        for i in items
        if i.kind not in {DriftKind.MATCHES_SOURCE, DriftKind.REPOSITORY_OWNED_EXTENSION}
    ]
