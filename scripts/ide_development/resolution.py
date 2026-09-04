"""Fail-closed v2 managed-core upgrade resolution receipts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .errors import InvalidPackageError
from .hashing import sha256_file
from .paths import as_posix_rel, path_is_symlink

HEX40 = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
KIND = "ide-managed-upgrade-resolution"
# These are the only managed files that the IDE provider may supersede in a
# digest-bound upgrade. Keep this set explicit so a provider manifest cannot
# become implicit overwrite authority.
ALLOWED_CONFLICT_PATHS = frozenset({
    ".ide-development/schemas/managed-upgrade-resolution.schema.json",
    ".ide-development/schemas/phase-handoff.schema.json",
    ".ide-development/schemas/phase-record.schema.json",
    ".ide-development/schemas/secret-scan-result.schema.json",
    ".ide-development/tests/test_fixture_aware_secret_scan.py",
    ".ide-development/tests/test_phase_packager_coordinator.py",
    "scripts/gitops/packager_coordinator.py",
    "scripts/gitops/phase_integrator.py",
    "scripts/gitops/secret_scan.py",
})
CHANGE_SCOPED_EVIDENCE_KEY = "changeScopedSecretScan"
CHANGE_SCOPED_EVIDENCE_REQUIRED = frozenset({
    "schemaVersion",
    "kind",
    "repository",
    "authoritativeRemoteRef",
    "baselineCommit",
    "baselineTree",
    "candidateCommit",
    "candidateGitTree",
    "scannerPolicyVersion",
    "managedPaths",
    "configDigest",
    "findings",
})


@dataclass(frozen=True)
class ConflictResolution:
    path: str
    old_digest: str
    current_digest: str
    provider_digest: str
    decision: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "oldDigest": self.old_digest, "currentDigest": self.current_digest, "providerDigest": self.provider_digest, "decision": self.decision}


@dataclass(frozen=True)
class UpgradeResolution:
    path: Path
    repository: str
    target_worktree: str
    commit: str
    tree: str
    provider_commit: str
    provider_tree: str
    package_version: str
    conflicts: tuple[ConflictResolution, ...]
    manifest_digest: str
    installed_state_digest: str
    verification: dict[str, Any]
    raw_digest: str

    @property
    def paths(self) -> frozenset[str]:
        return frozenset(item.path for item in self.conflicts)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": KIND, "schemaVersion": 2, "repository": self.repository, "targetWorktree": self.target_worktree, "consumer": {"commit": self.commit, "tree": self.tree}, "provider": {"commit": self.provider_commit, "tree": self.provider_tree}, "packageVersion": self.package_version, "manifestDigest": self.manifest_digest, "installedStateDigest": self.installed_state_digest, "conflicts": [item.to_dict() for item in self.conflicts], "verification": self.verification, "resolutionDigest": self.raw_digest}


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
    if result.returncode:
        raise InvalidPackageError("Cannot verify Git identity for managed upgrade resolution", details={"stderr": result.stderr.strip()})
    return result.stdout.strip()


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise InvalidPackageError(f"Resolution {field} must be a sha256 digest")
    return value


def _oid(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HEX40.fullmatch(value):
        raise InvalidPackageError(f"Resolution {field} must be a 40-character Git OID")
    return value


def _status_paths(root: Path) -> list[str]:
    out = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    paths: list[str] = []
    for line in out.splitlines():
        if len(line) < 3 or "->" in line or line[:2][0] in "RC" or line[:2][1] in "RC":
            raise InvalidPackageError("Resolution refuses malformed or rename/copy Git state")
        if line[:2] == "!!":
            continue
        paths.append(as_posix_rel(line[3:]))
    return paths


def _path(value: Any) -> str:
    if not isinstance(value, str) or any(ch in value for ch in "*?[]"):
        raise InvalidPackageError("Resolution path must be an exact non-wildcard string")
    normalized = as_posix_rel(value)
    if normalized != value:
        raise InvalidPackageError(f"Resolution path must be normalized: {value!r}")
    return normalized


def _canonical_digest(value: Any) -> str:
    """Digest an evidence object without allowing JSON formatting ambiguity."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _validate_observed_conflict_paths(paths: Iterable[str]) -> frozenset[str]:
    """Require a non-empty observed subset of the explicit provider allowlist."""
    observed = frozenset(paths)
    if not observed:
        raise InvalidPackageError("Observed conflicts must contain at least one managed path")
    if not observed.issubset(ALLOWED_CONFLICT_PATHS):
        raise InvalidPackageError("Observed conflicts contain an undeclared managed path")
    return observed


def _validate_change_scoped_binding(verification: dict[str, Any]) -> None:
    """Validate the receipt envelope before any transaction can begin.

    The target scanner performs repository/Git/config validation after the
    package is materialized.  This preflight only validates the immutable
    envelope and evidence shape, preventing malformed or silently omitted
    evidence from reaching the post-install hook.
    """
    if CHANGE_SCOPED_EVIDENCE_KEY not in verification:
        return
    binding = verification.get(CHANGE_SCOPED_EVIDENCE_KEY)
    if not isinstance(binding, dict) or set(binding) != {"evidence", "evidenceDigest"}:
        raise InvalidPackageError(
            "Change-scoped secret-scan binding must contain only evidence and evidenceDigest"
        )
    evidence = binding.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) - (CHANGE_SCOPED_EVIDENCE_REQUIRED | {"candidateTree"}):
        raise InvalidPackageError("Change-scoped secret-scan evidence has unknown fields")
    if CHANGE_SCOPED_EVIDENCE_REQUIRED - set(evidence):
        raise InvalidPackageError("Change-scoped secret-scan evidence is missing required identity")
    if evidence.get("schemaVersion") != 1 or evidence.get("kind") != "change-scoped-secret-scan-evidence":
        raise InvalidPackageError("Change-scoped secret-scan evidence schema/kind is invalid")
    if not isinstance(evidence.get("managedPaths"), list) or not evidence["managedPaths"]:
        raise InvalidPackageError("Change-scoped secret-scan managed path identity is required")
    if not isinstance(evidence.get("findings"), list):
        raise InvalidPackageError("Change-scoped secret-scan findings must be an array")
    if _digest(binding.get("evidenceDigest"), "changeScopedSecretScan.evidenceDigest") != _canonical_digest(evidence):
        raise InvalidPackageError("Change-scoped secret-scan evidence digest is stale")


def load_and_validate_resolution(resolution_path: Path, *, target_root: Path, package_root: Path, package_version: str, package_manifest_digest: str, prior_package_version: str | None, prior_installed_state_digest: str | None = None, observed_conflicts: Iterable[tuple[str, str, str, str]]) -> UpgradeResolution:
    path = resolution_path.resolve(strict=False)
    if not path.is_file() or path.is_symlink():
        raise InvalidPackageError(f"Resolution manifest must be a physical file: {path}")
    try:
        raw_bytes = path.read_bytes()
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidPackageError(f"Resolution manifest is not valid JSON: {path}") from exc
    if not isinstance(raw, dict) or raw.get("kind") != KIND or raw.get("schemaVersion") != 2:
        raise InvalidPackageError("Unsupported managed-upgrade resolution manifest kind/version")
    dangerous = {"force", "wildcard", "autoMerge", "merge", "preferIncoming", "preferProvider", "overwrite"}
    if any(key in dangerous for key in raw):
        raise InvalidPackageError("Resolution refuses force, wildcard, merge, or overwrite controls")
    target_worktree = raw.get("targetWorktree")
    if not isinstance(target_worktree, str) or str(Path(target_worktree).resolve(strict=False)) != str(target_root.resolve()):
        raise InvalidPackageError("Resolution targetWorktree does not exactly match target")
    consumer = raw.get("consumer")
    if not isinstance(consumer, dict) or not {"commit", "tree"}.issubset(consumer):
        raise InvalidPackageError("Resolution consumer commit/tree identity is required")
    commit, tree = _oid(consumer["commit"], "consumer.commit"), _oid(consumer["tree"], "consumer.tree")
    actual = (_git(target_root, "rev-parse", "--verify", "HEAD^{commit}"), _git(target_root, "rev-parse", "--verify", "HEAD^{tree}"))
    if (commit, tree) != actual:
        raise InvalidPackageError("Resolution consumer Git identity is stale")
    status = _status_paths(target_root)
    if status:
        raise InvalidPackageError("Resolution requires a clean consumer worktree", details={"paths": status})
    provider = raw.get("provider")
    required_provider = {"repository", "authoritativeRef", "commit", "tree", "installerVersion", "phasePullRequest", "independentVerificationReceipt", "managedPackageManifest"}
    if not isinstance(provider, dict) or not required_provider.issubset(provider):
        raise InvalidPackageError("Resolution provider provenance is incomplete")
    provider_commit, provider_tree = _oid(provider["commit"], "provider.commit"), _oid(provider["tree"], "provider.tree")
    provider_actual = (_git(package_root, "rev-parse", "--verify", "HEAD^{commit}"), _git(package_root, "rev-parse", "--verify", "HEAD^{tree}"))
    if (provider_commit, provider_tree) != provider_actual:
        raise InvalidPackageError("Resolution provider source identity is stale")
    managed = provider["managedPackageManifest"]
    if provider["installerVersion"] != "2.5.1" or not isinstance(managed, dict) or managed.get("path") != "core/managed-core/MANIFEST.json":
        raise InvalidPackageError("Resolution provider package provenance is invalid")
    manifest_path = package_root / "core/managed-core/MANIFEST.json"
    if managed.get("bytes") != manifest_path.stat().st_size or _digest(managed.get("sha256"), "provider.managedPackageManifest.sha256") != package_manifest_digest:
        raise InvalidPackageError("Resolution provider MANIFEST digest/size is stale")
    if raw.get("allowedConflictPaths") != sorted(ALLOWED_CONFLICT_PATHS):
        raise InvalidPackageError("Resolution allowedConflictPaths must exactly equal canonical scanner paths")
    expected = {rel: (old, current, provider_hash) for rel, old, current, provider_hash in observed_conflicts}
    observed_paths = _validate_observed_conflict_paths(expected)
    rows = raw.get("conflicts")
    if not isinstance(rows, list) or len(rows) != len(observed_paths) or {row.get("path") for row in rows if isinstance(row, dict)} != observed_paths:
        raise InvalidPackageError("Resolution conflicts do not exactly match observed managed paths")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = {entry.get("destination"): entry for entry in manifest.get("files", [])}
    resolutions: list[ConflictResolution] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("decision") != "provider-supersedes":
            raise InvalidPackageError("Every conflict requires explicit provider-supersedes decision")
        rel = _path(row.get("path"))
        old = _digest(row.get("installedBaseline", {}).get("sha256"), f"{rel}.installedBaseline")
        current = _digest(row.get("currentConsumer", {}).get("sha256"), f"{rel}.currentConsumer")
        provider_hash = _digest(row.get("provider", {}).get("sha256"), f"{rel}.provider")
        for field, row_key, digest in (("installedBaseline", "installedBaseline", old), ("currentConsumer", "currentConsumer", current), ("provider", "provider", provider_hash)):
            declared_bytes = row.get(row_key, {}).get("bytes")
            if not isinstance(declared_bytes, int) or declared_bytes < 0:
                raise InvalidPackageError(f"Resolution {rel}.{field}.bytes is required")
            if field == "currentConsumer" and declared_bytes != (target_root / rel).stat().st_size:
                raise InvalidPackageError(f"Resolution current byte size is stale: {rel}")
        if (old, current, provider_hash) != expected[rel]:
            raise InvalidPackageError(f"Resolution digest is stale for conflict path: {rel}")
        entry = entries.get(rel)
        if not entry or row["provider"].get("source") != entry.get("source") or provider_hash != entry.get("sourceHash"):
            raise InvalidPackageError(f"Provider source/digest is not bound to MANIFEST for {rel}")
        provider_source = package_root / entry["source"]
        if not provider_source.is_file() or provider_source.is_symlink() or row["provider"].get("bytes") != provider_source.stat().st_size:
            raise InvalidPackageError(f"Provider source byte preimage is stale for {rel}")
        dest = target_root / rel
        if path_is_symlink(dest) or not dest.is_file() or sha256_file(dest) != current:
            raise InvalidPackageError(f"Current consumer digest no longer matches: {rel}")
        resolutions.append(ConflictResolution(rel, old, current, provider_hash, "provider_supersedes"))
    baseline = raw.get("installedBaseline", {}).get("installedStatePreimage", {})
    state = target_root / ".ide-development/installed-state.json"
    baseline_digest = _digest(baseline.get("sha256"), "installedStatePreimage.sha256")
    if baseline.get("path") != ".ide-development/installed-state.json" or not state.is_file() or baseline.get("bytes") != state.stat().st_size or baseline_digest != sha256_file(state):
        raise InvalidPackageError("Installed-state preimage is stale")
    if prior_installed_state_digest and prior_installed_state_digest != sha256_file(state):
        raise InvalidPackageError("Installed-state digest changed since planning")
    verification = raw.get("verification")
    if not isinstance(verification, dict) or verification.get("providerReceipt") != provider["independentVerificationReceipt"] or verification.get("providerTreeRequired") is not True or verification.get("consumerTreeRequired") is not True or verification.get("noUpstreamScanOrMutation") is not True:
        raise InvalidPackageError("Independent verification receipt is incomplete or mismatched")
    _validate_change_scoped_binding(verification)
    checks = verification.get("canonicalProviderChecks")
    required_cases = {
        "quoted member and call references are non-findings",
        "binary and undecodable inputs are typed nonblocking skipped_input",
        "oversized decodable text is scanned fully",
        "recognized and high-entropy credential literals remain blocking",
        "stale identity, configuration, and path-set evidence fails closed",
    }
    if not isinstance(checks, dict) or checks.get("fullFixtureAwareSuite") != "41/41 passed" or checks.get("focusedSuite") != "20/20 passed" or set(checks.get("requiredCases", [])) != required_cases:
        raise InvalidPackageError("Canonical provider verification semantics are incomplete")
    rollback = raw.get("backupAndRollback")
    if not isinstance(rollback, dict) or rollback.get("backupRequiredBeforeApply") is not True or rollback.get("transactionRequired") is not True or rollback.get("manualOverwriteForbidden") is not True:
        raise InvalidPackageError("Backup/rollback transaction proof is incomplete")
    resolution = raw.get("resolution")
    if not isinstance(resolution, dict) or resolution.get("deferredPaths") != [] or resolution.get("noExtraPaths") is not True:
        raise InvalidPackageError("Resolution contains deferred or extra paths")
    if prior_package_version is not None and package_version < prior_package_version:
        raise InvalidPackageError("Managed upgrade resolution refuses package downgrade")
    return UpgradeResolution(path, str(raw.get("repository", "")), target_worktree, commit, tree, provider_commit, provider_tree, package_version, tuple(sorted(resolutions, key=lambda item: item.path)), package_manifest_digest, baseline_digest, verification, "sha256:" + hashlib.sha256(raw_bytes).hexdigest())
