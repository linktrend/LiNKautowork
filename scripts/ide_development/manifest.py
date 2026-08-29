"""Manifest loading and validation (aligned to core/managed-core/schemas)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .constants import (
    DEFAULT_MANIFEST_REL,
    DEFAULT_MARKER_BEGIN,
    DEFAULT_MARKER_END,
    DEFAULT_MIGRATION_CATALOG_RELS,
    DEFAULT_PACKAGE_VERSION_FALLBACK_REL,
    DEFAULT_PACKAGE_VERSION_REL,
    MERGE_STRATEGIES,
    OS_FILTERS,
    OWNERSHIP_CLASSES,
    PACKAGE_NAME,
    PLATFORMS,
    SCHEMA_VERSION,
)
from .errors import InvalidPackageError
from .hashing import normalize_mode, sha256_file
from .paths import as_posix_rel, join_under, join_under_nofollow, os_matches, path_is_symlink, platform_matches


@dataclass(frozen=True)
class ManifestEntry:
    id: str
    ownership_class: str
    source: str
    destination: str
    mode: str
    platform: str
    os: str
    merge_strategy: str
    source_hash: str
    supersession_identity: str | None
    marker_begin: str | None = None
    marker_end: str | None = None
    notes: str | None = None
    owner: str = PACKAGE_NAME
    mutability_policy: str = "read-only"
    removal_policy: str = "preserve"
    capability_id: str | None = None
    capability_version: str | None = None
    requires: tuple[str, ...] = ()

    @property
    def destination_posix(self) -> str:
        return self.destination


@dataclass(frozen=True)
class Manifest:
    schema_version: int
    package_name: str
    package_version: str
    entries: tuple[ManifestEntry, ...]
    path: Path
    capabilities: tuple["Capability", ...] = ()

    def active_entries(self) -> tuple[ManifestEntry, ...]:
        out: list[ManifestEntry] = []
        for entry in self.entries:
            if entry.ownership_class in {"consumer-preserve"}:
                continue
            if not platform_matches(entry.platform):
                continue
            if not os_matches(entry.os):
                continue
            out.append(entry)
        return tuple(out)


@dataclass(frozen=True)
class Capability:
    id: str
    version: str
    entry_ids: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()


@dataclass(frozen=True)
class MigrationEntry:
    identity: str
    path: str
    content_hash: str
    action: str


@dataclass(frozen=True)
class MigrationCatalog:
    schema_version: int
    entries: tuple[MigrationEntry, ...]
    path: Path | None


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidPackageError(f"{label} must be a JSON object")
    return value


def _require_str(obj: dict[str, Any], key: str, *, allow_empty: bool = False) -> str:
    if key not in obj:
        raise InvalidPackageError(f"Missing required field: {key}")
    value = obj[key]
    if not isinstance(value, str):
        raise InvalidPackageError(f"Field {key} must be a string")
    if not allow_empty and not value.strip():
        raise InvalidPackageError(f"Field {key} must be non-empty")
    return value


def load_package_version(package_root: Path, manifest_obj: dict[str, Any]) -> str:
    declared: str | None = None
    if "packageVersion" in manifest_obj and isinstance(manifest_obj["packageVersion"], str):
        declared = manifest_obj["packageVersion"].strip().lstrip("v")
    for rel in (DEFAULT_PACKAGE_VERSION_REL, DEFAULT_PACKAGE_VERSION_FALLBACK_REL):
        version_path = package_root / rel
        if version_path.is_file():
            text = version_path.read_text(encoding="utf-8").strip()
            if text:
                version = text.lstrip("v")
                if declared is not None and declared != version:
                    raise InvalidPackageError(
                        "Package version collision: MANIFEST.json and VERSION differ",
                        details={"manifest": declared, "versionFile": version},
                    )
                return declared or version
    if declared is not None:
        return declared
    raise InvalidPackageError("Package version missing (manifest.packageVersion or VERSION)")


def parse_manifest_entry(raw: Any, *, index: int) -> ManifestEntry:
    obj = _require_mapping(raw, f"files[{index}]")
    entry_id = _require_str(obj, "id")
    ownership = _require_str(obj, "ownershipClass")
    if ownership not in OWNERSHIP_CLASSES:
        raise InvalidPackageError(
            f"Invalid ownershipClass for {entry_id}: {ownership}",
            details={"allowed": sorted(OWNERSHIP_CLASSES)},
        )
    source = as_posix_rel(_require_str(obj, "source"))
    destination = as_posix_rel(_require_str(obj, "destination"))
    for label, rel in (("source", source), ("destination", destination)):
        lowered = rel.lower()
        parts = PurePosixPath(lowered).parts
        if (
            lowered == "claude.md"
            or lowered.endswith("/claude.md")
            or parts[:1] == (".claude",)
            or parts[:1] == ("claude",)
            or ".claude/" in lowered
        ):
            raise InvalidPackageError(
                f"Claude surfaces are out of scope for {entry_id} ({label}={rel})"
            )
    mode = normalize_mode(_require_str(obj, "mode"))
    platform = _require_str(obj, "platform").lower()
    if platform not in PLATFORMS:
        raise InvalidPackageError(f"Invalid platform for {entry_id}: {platform}")
    os_filter = obj.get("os", "all")
    if not isinstance(os_filter, str):
        raise InvalidPackageError(f"os must be a string for {entry_id}")
    os_filter = os_filter.lower()
    if os_filter not in OS_FILTERS:
        raise InvalidPackageError(f"Invalid os for {entry_id}: {os_filter}")
    merge = _require_str(obj, "mergeStrategy")
    if merge not in MERGE_STRATEGIES:
        raise InvalidPackageError(f"Invalid mergeStrategy for {entry_id}: {merge}")
    source_hash = _require_str(obj, "sourceHash")
    if not source_hash.startswith("sha256:") or len(source_hash) != len("sha256:") + 64:
        raise InvalidPackageError(f"Invalid sourceHash for {entry_id}")
    supersession = obj.get("supersessionIdentity")
    if supersession is not None and not isinstance(supersession, str):
        raise InvalidPackageError(f"supersessionIdentity must be string or null for {entry_id}")
    if isinstance(supersession, str) and not supersession.strip():
        supersession = None

    marker_begin = obj.get("markerBegin")
    marker_end = obj.get("markerEnd")
    if ownership == "managed-marker":
        if merge != "marker-upsert":
            raise InvalidPackageError(
                f"managed-marker requires mergeStrategy=marker-upsert for {entry_id}"
            )
        if not isinstance(marker_begin, str) or not marker_begin:
            marker_begin = DEFAULT_MARKER_BEGIN
        if not isinstance(marker_end, str) or not marker_end:
            marker_end = DEFAULT_MARKER_END
    else:
        marker_begin = marker_begin if isinstance(marker_begin, str) else None
        marker_end = marker_end if isinstance(marker_end, str) else None

    if ownership == "external-state":
        if merge != "external-plan-only":
            raise InvalidPackageError(
                f"external-state requires mergeStrategy=external-plan-only for {entry_id}"
            )
        if platform != "github":
            raise InvalidPackageError(
                f"external-state requires platform=github for {entry_id}"
            )

    notes = obj.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise InvalidPackageError(f"notes must be a string for {entry_id}")

    owner = obj.get("owner", PACKAGE_NAME)
    if not isinstance(owner, str) or not owner.strip():
        raise InvalidPackageError(f"owner must be a non-empty string for {entry_id}")
    mutability = obj.get("mutabilityPolicy", "read-only")
    if mutability != "read-only":
        raise InvalidPackageError(f"Unsupported mutabilityPolicy for {entry_id}: {mutability}")
    removal_default = "exact-match" if merge == "remove-if-matches" else "preserve"
    removal = obj.get("removalPolicy", removal_default)
    if removal not in {"preserve", "exact-match", "transaction-only"}:
        raise InvalidPackageError(f"Unsupported removalPolicy for {entry_id}: {removal}")
    capability_id = obj.get("capabilityId")
    if capability_id is not None and (not isinstance(capability_id, str) or not capability_id.strip()):
        raise InvalidPackageError(f"capabilityId must be a non-empty string for {entry_id}")
    capability_version = obj.get("capabilityVersion")
    if capability_version is not None and (not isinstance(capability_version, str) or not capability_version.strip()):
        raise InvalidPackageError(f"capabilityVersion must be a non-empty string for {entry_id}")
    requires_raw = obj.get("requires", [])
    if not isinstance(requires_raw, list) or any(not isinstance(item, str) or not item.strip() for item in requires_raw):
        raise InvalidPackageError(f"requires must be an array of non-empty strings for {entry_id}")
    requires = tuple(sorted(set(requires_raw)))

    return ManifestEntry(
        id=entry_id,
        ownership_class=ownership,
        source=source,
        destination=destination,
        mode=mode,
        platform=platform,
        os=os_filter,
        merge_strategy=merge,
        source_hash=source_hash,
        supersession_identity=supersession,
        marker_begin=marker_begin,
        marker_end=marker_end,
        notes=notes,
        owner=owner.strip(),
        mutability_policy=mutability,
        removal_policy=removal,
        capability_id=capability_id.strip() if isinstance(capability_id, str) else None,
        capability_version=capability_version.strip() if isinstance(capability_version, str) else None,
        requires=requires,
    )


def _parse_capabilities(raw: Any) -> tuple[Capability, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise InvalidPackageError("manifest capabilities must be an array")
    result: list[Capability] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        row = _require_mapping(item, f"capabilities[{index}]")
        capability_id = _require_str(row, "id")
        version = _require_str(row, "version")
        if capability_id in seen:
            raise InvalidPackageError(f"Duplicate capability id: {capability_id}")
        entry_ids = row.get("entryIds", [])
        requires = row.get("requires", [])
        if not isinstance(entry_ids, list) or any(not isinstance(value, str) or not value.strip() for value in entry_ids):
            raise InvalidPackageError(f"capabilities[{index}].entryIds must be an array of strings")
        if not isinstance(requires, list) or any(not isinstance(value, str) or not value.strip() for value in requires):
            raise InvalidPackageError(f"capabilities[{index}].requires must be an array of strings")
        seen.add(capability_id)
        result.append(Capability(capability_id, version, tuple(sorted(set(entry_ids))), tuple(sorted(set(requires)))))
    return tuple(sorted(result, key=lambda item: item.id))


def validate_capability_closure(manifest: Manifest) -> None:
    """Reject duplicate or missing capability dependencies before installation."""
    declared = {entry.id for entry in manifest.entries}
    declared.update(capability.id for capability in manifest.capabilities)
    versions: dict[str, str] = {}
    for entry in manifest.entries:
        if entry.capability_id:
            previous = versions.setdefault(entry.capability_id, entry.capability_version or "")
            if previous != (entry.capability_version or ""):
                raise InvalidPackageError(
                    f"Capability version collision for {entry.capability_id}"
                )
            declared.add(entry.capability_id)
        for required in entry.requires:
            if required not in declared:
                raise InvalidPackageError(
                    f"Manifest capability dependency is absent: {entry.id} requires {required}"
                )
    capability_ids = {capability.id for capability in manifest.capabilities}
    for capability in manifest.capabilities:
        if any(entry_id not in {entry.id for entry in manifest.entries} for entry_id in capability.entry_ids):
            raise InvalidPackageError(f"Capability {capability.id} references an absent manifest entry")
        for required in capability.requires:
            if required not in declared:
                raise InvalidPackageError(
                    f"Manifest capability dependency is absent: {capability.id} requires {required}"
                )
        if capability.id in versions and versions[capability.id] not in {"", capability.version}:
            raise InvalidPackageError(f"Capability version collision for {capability.id}")
        versions[capability.id] = capability.version


def load_manifest(package_root: Path, *, manifest_rel: PurePosixPath | str | None = None) -> Manifest:
    rel = PurePosixPath(manifest_rel) if manifest_rel else DEFAULT_MANIFEST_REL
    path = package_root / rel
    if not path.is_file():
        raise InvalidPackageError(f"Missing manifest: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidPackageError(f"Manifest is not valid JSON: {path}") from exc
    obj = _require_mapping(raw, "manifest")
    schema_version = obj.get("schemaVersion")
    if schema_version != SCHEMA_VERSION:
        raise InvalidPackageError(
            f"Unsupported manifest schemaVersion: {schema_version} (expected {SCHEMA_VERSION})"
        )
    package_name = obj.get("packageName", PACKAGE_NAME)
    if package_name != PACKAGE_NAME:
        raise InvalidPackageError(f"Unsupported packageName: {package_name}")
    package_version = load_package_version(package_root, obj)
    files = obj.get("files")
    if not isinstance(files, list) or not files:
        raise InvalidPackageError("Manifest files must be a non-empty array")
    entries: list[ManifestEntry] = []
    seen_ids: set[str] = set()
    seen_dests: set[str] = set()
    for index, item in enumerate(files):
        entry = parse_manifest_entry(item, index=index)
        if entry.id in seen_ids:
            raise InvalidPackageError(f"Duplicate manifest id: {entry.id}")
        if entry.destination in seen_dests:
            raise InvalidPackageError(f"Duplicate destination: {entry.destination}")
        # external-state / consumer-preserve may still declare a source for hash identity
        if entry.ownership_class != "consumer-preserve":
            # Check symlink on the logical path first so an escaping package
            # symlink is InvalidPackage (12), not PATH_ESCAPE Conflict (11).
            logical_source = join_under_nofollow(package_root, entry.source)
            if path_is_symlink(logical_source):
                raise InvalidPackageError(
                    f"Source must be a physical file (symlink refused): {entry.source}"
                )
            source_path = join_under(package_root, entry.source)
            if not source_path.is_file():
                if entry.ownership_class == "optional":
                    continue
                raise InvalidPackageError(f"Missing source file for {entry.id}: {entry.source}")
            if path_is_symlink(source_path):
                raise InvalidPackageError(
                    f"Source must be a physical file (symlink refused): {entry.source}"
                )
            actual = sha256_file(source_path)
            if actual != entry.source_hash:
                raise InvalidPackageError(
                    f"sourceHash mismatch for {entry.id}",
                    details={"expected": entry.source_hash, "actual": actual},
                )
        seen_ids.add(entry.id)
        seen_dests.add(entry.destination)
        entries.append(entry)
    entries.sort(key=lambda e: (e.destination, e.id))
    capabilities = _parse_capabilities(obj.get("capabilities"))
    manifest = Manifest(
        schema_version=schema_version,
        package_name=package_name,
        package_version=package_version,
        entries=tuple(entries),
        path=path,
        capabilities=capabilities,
    )
    validate_capability_closure(manifest)
    return manifest


def load_migration_catalog(
    package_root: Path,
    *,
    catalog_rel: PurePosixPath | str | None = None,
) -> MigrationCatalog:
    path: Path | None = None
    if catalog_rel is not None:
        candidate = package_root / PurePosixPath(catalog_rel)
        if candidate.is_file():
            path = candidate
    else:
        for rel in DEFAULT_MIGRATION_CATALOG_RELS:
            candidate = package_root / rel
            if candidate.is_file():
                path = candidate
                break
    if path is None:
        return MigrationCatalog(schema_version=SCHEMA_VERSION, entries=(), path=None)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidPackageError(f"Migration catalog is not valid JSON: {path}") from exc
    obj = _require_mapping(raw, "migration-catalog")
    schema_version = obj.get("schemaVersion")
    if schema_version != SCHEMA_VERSION:
        raise InvalidPackageError(
            f"Unsupported migration catalog schemaVersion: {schema_version}"
        )
    items = obj.get("entries") or []
    if not isinstance(items, list):
        raise InvalidPackageError("migration catalog entries must be an array")
    entries: list[MigrationEntry] = []
    seen_identities: set[str] = set()
    seen_paths: set[str] = set()
    for index, item in enumerate(items):
        row = _require_mapping(item, f"entries[{index}]")
        identity = _require_str(row, "identity")
        path_rel = as_posix_rel(_require_str(row, "path"))
        content_hash = _require_str(row, "contentHash")
        action = _require_str(row, "action")
        if identity in seen_identities:
            raise InvalidPackageError(f"Duplicate migration identity: {identity}")
        if path_rel in seen_paths:
            raise InvalidPackageError(f"Duplicate migration path: {path_rel}")
        if action != "remove":
            raise InvalidPackageError(f"Unsupported migration action: {action}")
        if not content_hash.startswith("sha256:") or len(content_hash) != len("sha256:") + 64:
            raise InvalidPackageError(f"Invalid contentHash for migration {identity}")
        seen_identities.add(identity)
        seen_paths.add(path_rel)
        entries.append(
            MigrationEntry(
                identity=identity,
                path=path_rel,
                content_hash=content_hash,
                action=action,
            )
        )
    entries.sort(key=lambda e: (e.path, e.identity))
    return MigrationCatalog(schema_version=schema_version, entries=tuple(entries), path=path)
