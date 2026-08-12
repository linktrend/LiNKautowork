"""Shared constants for the IDE Development installer."""

from __future__ import annotations

from pathlib import PurePosixPath

# Exit codes (stable contract — docs/contracts/MANAGED-CORE-V2.md)
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_DRIFT = 10
EXIT_CONFLICT = 11
EXIT_INVALID_PACKAGE = 12
EXIT_ROLLBACK_FAILURE = 13

SCHEMA_VERSION = 1
INSTALLER_VERSION = "2.1.8"
PACKAGE_VERSION_TARGET = "2.1.8"
PACKAGE_NAME = "ide-development-managed-core"

# Release-candidate packaging (Lane D) — archives under ignored build/
RC_SCHEMA_VERSION = 1
RC_KIND = "ide-development-release-candidate"
RC_BUILD_DIR_REL = "build/release-candidate"
RC_METADATA_NAME = "release-candidate.json"
RC_CHECKSUMS_NAME = "SHA256SUMS.json"
# Deterministic archive epoch: 2026-08-01T00:00:00Z
RC_ARCHIVE_EPOCH = 1_785_542_400
RC_ARCHIVE_EPOCH_UTC = "2026-08-01T00:00:00Z"
RC_REQUIRED_SCHEMA_RELS = (
    "core/managed-core/schemas/manifest.schema.json",
    "core/managed-core/schemas/installed-state.schema.json",
    "core/managed-core/schemas/transaction.schema.json",
    "core/managed-core/schemas/release-candidate.schema.json",
    "core/managed-core/schemas/release-candidate-checksums.schema.json",
    "core/managed-core/schemas/delivery-modes.schema.json",
    "core/managed-core/schemas/managed-core-release.schema.json",
)
RC_REQUIRED_TEST_RELS = (
    "scripts/ide_development_tests/test_release_candidate.py",
    "scripts/ide_development_tests/test_package_reproducibility.py",
)
RC_REQUIRED_EVIDENCE_RELS = (
    "tests/packaging/LANE_D_RESULT.md",
)
RC_EXCLUSION_CLASSES = (
    "credentials-and-secret-values",
    "git-metadata",
    "absolute-host-paths",
    "external-symlinks",
    "caches-and-temp-files",
    "consumer-data",
    "claude-surfaces",
    "build-artifacts",
)

# Committed managed-core root inside a consumer repository
MANAGED_CORE_DIR = ".ide-development"
INSTALLED_STATE_REL = PurePosixPath(".ide-development/installed-state.json")

# Package-relative defaults (WP1 layout)
DEFAULT_MANIFEST_REL = PurePosixPath("core/managed-core/MANIFEST.json")
# Canonical Wave 1 path only — do not reintroduce duplicate catalogs.
DEFAULT_MIGRATION_CATALOG_REL = PurePosixPath("core/managed-core/migrations/catalog.json")
DEFAULT_MIGRATION_CATALOG_RELS = (DEFAULT_MIGRATION_CATALOG_REL,)
DEFAULT_PACKAGE_VERSION_REL = PurePosixPath("core/managed-core/VERSION")
DEFAULT_PACKAGE_VERSION_FALLBACK_REL = PurePosixPath("VERSION")

# Git-local metadata (not committed)
GIT_META_DIR = PurePosixPath(".git/ide-development")
TX_CURRENT_REL = GIT_META_DIR / "current-transaction"
TX_LAST_REL = GIT_META_DIR / "last-transaction"
LOCK_REL = GIT_META_DIR / "lock"

DEFAULT_MARKER_BEGIN = "<!-- BEGIN LINKTREND-IDE-MANAGED -->"
DEFAULT_MARKER_END = "<!-- END LINKTREND-IDE-MANAGED -->"

OWNERSHIP_CLASSES = frozenset(
    {
        "managed",
        "managed-core",
        "managed-entrypoint",
        "managed-marker",
        "optional",
        "consumer-preserve",
        "external-state",
    }
)
MERGE_STRATEGIES = frozenset(
    {
        "replace",
        "create-only",
        "remove-if-matches",
        "marker-upsert",
        "external-plan-only",
    }
)
# Discovery/runtime adapter scope (not an OS filter)
PLATFORMS = frozenset({"all", "cursor", "codex", "github", "none"})
# Host OS applicability
OS_FILTERS = frozenset({"all", "posix", "windows", "darwin", "linux"})
