"""High-level installer operations."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import __version__ as installer_version
from .constants import EXIT_CONFLICT, EXIT_DRIFT, EXIT_OK, MANAGED_CORE_DIR, PACKAGE_VERSION_TARGET
from .errors import InstallerError, InvalidPackageError, RollbackError
from .manifest import Manifest, load_manifest, load_migration_catalog
from .paths import require_git_repo, resolve_dir, same_path
from .plan import OpKind, Plan, PlanAction, build_drift_report, build_plan, meaningful_drift
from .state import load_installed_state
from .transaction import apply_plan, current_tx_dir, read_journal, recover_interrupted, rollback_last
from .io_atomic import atomic_write_bytes
from .hashing import sha256_file
from .managed_write_guard import export_candidate
from .resolution import UpgradeResolution, load_and_validate_resolution
from .same_version_repair import load_and_validate_same_version_repair
from .openclaw_customization_admission import (
    BOUNDARY_REL,
    admit_openclaw_customization,
)


CONSUMER_CONFIG = Path(".github/linktrend-gitops-consumer.json")
MANAGED_FAST_WORKFLOW = "Linktrend Fast Checks"
MANAGED_RUNNER_TYPE = "github-hosted"
RETIRED_RUNNER_TYPE = "linktrend-private-macos-arm64"
CI_CONTRACT_MODULE_REL = Path("scripts/gitops/repository_ci_contract.py")
SECRET_SCAN_MODULE_REL = Path("scripts/gitops/secret_scan.py")


def _load_repository_ci_contract_module(package_root: Path):
    """Load WP-U07 audit helpers from the package tree without package coupling.

    The packaged module imports sibling gitops helpers as ``scripts.gitops.*``,
    so the package root (not the installer ``scripts/`` directory) must be on
    ``sys.path`` while it loads. Incomplete loads are discarded fail-closed.
    """
    import sys

    module_path = package_root / CI_CONTRACT_MODULE_REL
    if not module_path.is_file():
        raise InvalidPackageError(f"repository CI contract module missing: {module_path}")
    module_name = "linktrend_repository_ci_contract"
    existing = sys.modules.get(module_name)
    if (
        existing is not None
        and getattr(existing, "__file__", None) == str(module_path)
        and hasattr(existing, "installer_audit_repository_ci_triggers")
    ):
        return existing
    package_root_str = str(package_root.resolve())
    if package_root_str not in sys.path:
        sys.path.insert(0, package_root_str)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise InvalidPackageError(f"repository CI contract module unloadable: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    if not hasattr(module, "installer_audit_repository_ci_triggers"):
        sys.modules.pop(module_name, None)
        raise InvalidPackageError(f"repository CI contract module missing installer audit: {module_path}")
    return module


def _normalize_consumer_workflow_contract(target_root: Path, *, mutate: bool) -> bool:
    """Upgrade bounded legacy delivery declarations without inferring CI.

    The workflow config is repository-owned, so an installer may only fill the
    historic absent managed Fast declaration and the one retired private runner
    declaration. Explicit blank/wrong values and any missing/blank CI
    declaration fail closed before managed workflows are installed or updated.
    """
    path = target_root / CONSUMER_CONFIG
    if not path.is_file():
        return False
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InvalidPackageError(f"consumer workflow config is invalid: {path}: {exc}") from exc
    if not isinstance(config, dict):
        raise InvalidPackageError(f"consumer workflow config is not an object: {path}")
    ci = config.get("ciWorkflowName")
    if not isinstance(ci, str) or not ci.strip():
        raise InvalidPackageError(f"consumer workflow config requires non-empty ciWorkflowName: {path}")
    changed = False
    fast = config.get("fastWorkflowName")
    if fast is None:
        config["fastWorkflowName"] = MANAGED_FAST_WORKFLOW
        changed = True
    elif not isinstance(fast, str) or fast != MANAGED_FAST_WORKFLOW:
        raise InvalidPackageError(
            f"consumer workflow config fastWorkflowName must equal {MANAGED_FAST_WORKFLOW!r}: {path}"
        )
    runner = config.get("runnerType", MANAGED_RUNNER_TYPE)
    if runner == RETIRED_RUNNER_TYPE:
        config["runnerType"] = MANAGED_RUNNER_TYPE
        changed = True
    elif runner != MANAGED_RUNNER_TYPE:
        raise InvalidPackageError(
            f"consumer workflow config runnerType must equal {MANAGED_RUNNER_TYPE!r}: {path}"
        )
    if mutate and changed:
        atomic_write_bytes(path, (json.dumps(config, indent=2) + "\n").encode("utf-8"), mode="0644")
    return changed


class EngineResult:
    def __init__(self, *, exit_code: int, payload: dict[str, Any]) -> None:
        self.exit_code = exit_code
        self.payload = payload


def _detect_package_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return resolve_dir(explicit)
    here = Path(__file__).resolve()
    return resolve_dir(here.parents[2])


def _prepare(
    *,
    target: Path,
    package: Path | None,
) -> tuple[Path, Path]:
    package_root = _detect_package_root(package)
    target_root = require_git_repo(target)
    if same_path(package_root, target_root):
        raise InvalidPackageError(
            "Refusing to install the system repository into itself "
            f"(package={package_root}, target={target_root})"
        )
    return package_root, target_root


def _pending_recovery(target_root: Path) -> dict[str, Any] | None:
    journal = read_journal(current_tx_dir(target_root))
    if journal is None:
        return None
    return {
        "pending": True,
        "transactionId": journal.get("transactionId"),
        "phase": journal.get("phase"),
    }


def _maybe_recover(target_root: Path, *, mutate: bool) -> dict[str, Any] | None:
    pending = _pending_recovery(target_root)
    if pending is None:
        return None
    if not mutate:
        return pending
    return recover_interrupted(target_root)


def _plan_payload(plan: Plan, **extra: Any) -> dict[str, Any]:
    payload = plan.to_dict()
    payload.update(extra)
    return payload


def _validate_package_identity(manifest: Manifest, prior: Any | None) -> str:
    """Reject a different package identity reusing an installed version."""
    digest = sha256_file(manifest.path)
    if prior is None or prior.package_version != manifest.package_version:
        return digest
    if prior.manifest_hash is not None and prior.manifest_hash != digest:
        raise InvalidPackageError(
            "Managed package version collision: manifest bytes changed for an installed version",
            details={
                "packageVersion": manifest.package_version,
                "installedManifestHash": prior.manifest_hash,
                "packageManifestHash": digest,
            },
        )
    current = {entry.destination: entry.source_hash for entry in manifest.active_entries()}
    installed = {
        path: file_state.source_hash
        for path, file_state in prior.files.items()
        if path != f"{MANAGED_CORE_DIR}/MANIFEST.json"
    }
    collisions = sorted(
        path for path in current.keys() & installed.keys() if current[path] != installed[path]
    )
    if collisions:
        raise InvalidPackageError(
            "Managed package version collision: source bytes changed for an installed version",
            details={"packageVersion": manifest.package_version, "paths": collisions},
        )
    return digest


def _export_conflict_candidates(
    *, target_root: Path, package_version: str, prior: Any | None, plan: Plan
) -> list[dict[str, object]]:
    """Quarantine changed owned bytes before reporting an overwrite refusal."""
    if prior is None:
        return []
    exports: list[dict[str, object]] = []
    for conflict in plan.conflicts:
        if conflict.kind.value != "hash_mismatch_owned":
            continue
        file_state = prior.files.get(conflict.path)
        destination = target_root / conflict.path
        if file_state is None or not destination.is_file() or destination.is_symlink():
            continue
        try:
            exports.append(
                export_candidate(
                    target_root,
                    conflict.path,
                    package_version=package_version,
                    baseline_digest=file_state.content_hash,
                    classification="candidate_central_ide_improvement",
                    reason="managed bytes changed outside an authorized transaction",
                )
            )
        except (OSError, InstallerError) as exc:
            exports.append(
                {
                    "path": conflict.path,
                    "classification": "candidate_export_failed",
                    "error": str(exc),
                }
            )
    return exports


def _repository_ci_trigger_audit(package_root: Path, target_root: Path) -> dict[str, Any]:
    ci_module = _load_repository_ci_contract_module(package_root)
    return ci_module.installer_audit_repository_ci_triggers(target_root)


def _load_secret_scan_module(package_root: Path):
    """Load the package scanner so admission can pass an explicit path scope."""
    import sys

    module_path = package_root / SECRET_SCAN_MODULE_REL
    if not module_path.is_file():
        raise InvalidPackageError(f"secret scan module missing: {module_path}")
    module_name = "linktrend_secret_scan"
    existing = sys.modules.get(module_name)
    if (
        existing is not None
        and getattr(existing, "__file__", None) == str(module_path)
        and hasattr(existing, "scan_repository")
    ):
        return existing
    package_root_str = str(package_root.resolve())
    if package_root_str not in sys.path:
        sys.path.insert(0, package_root_str)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise InvalidPackageError(f"secret scan module unloadable: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    if not hasattr(module, "scan_repository"):
        sys.modules.pop(module_name, None)
        raise InvalidPackageError(f"secret scan module missing scanner: {module_path}")
    return module


def _openclaw_admission(package_root: Path, target_root: Path) -> dict[str, Any] | None:
    """Run scoped admission when the target exposes the OpenClaw boundary."""
    boundary = target_root / BOUNDARY_REL
    if not boundary.exists():
        return None
    scanner_module = _load_secret_scan_module(package_root)

    def scanner(paths: list[str]) -> dict[str, Any]:
        return scanner_module.scan_repository(target_root, paths=paths)

    return admit_openclaw_customization(
        consumer_root=target_root,
        package_root=package_root,
        boundary_path=boundary,
        scanner=scanner,
    )


def _resolve_authorized_upgrade(
    *,
    resolution_manifest: Path | None,
    target_root: Path,
    package_root: Path,
    manifest: Manifest,
    prior: Any,
    plan: Plan,
) -> UpgradeResolution | None:
    if resolution_manifest is None:
        return None
    entries = {entry.destination: entry for entry in manifest.active_entries()}
    observed: list[tuple[str, str, str, str]] = []
    for conflict in plan.conflicts:
        if conflict.kind.value != "hash_mismatch_owned":
            raise InvalidPackageError(
                "Resolution may authorize only hash_mismatch_owned conflicts",
                details={"path": conflict.path, "kind": conflict.kind.value},
            )
        entry = entries.get(conflict.path)
        prior_file = prior.files.get(conflict.path) if prior is not None else None
        destination = target_root / conflict.path
        if entry is None or prior_file is None or not destination.is_file() or destination.is_symlink():
            raise InvalidPackageError(f"Resolution conflict is not a regular managed file: {conflict.path}")
        observed.append(
            (conflict.path, prior_file.content_hash, sha256_file(destination), entry.source_hash)
        )
    resolution = load_and_validate_resolution(
        resolution_manifest,
        target_root=target_root,
        package_version=manifest.package_version,
        package_manifest_digest=sha256_file(manifest.path),
        package_root=package_root,
        prior_package_version=prior.package_version if prior is not None else None,
        prior_installed_state_digest=(
            sha256_file(target_root / ".ide-development/installed-state.json")
            if (target_root / ".ide-development/installed-state.json").is_file()
            else None
        ),
        observed_conflicts=observed,
    )
    return resolution


def _post_install_verification(
    *, target_root: Path, package_root: Path, resolution: UpgradeResolution | None
) -> dict[str, Any]:
    """Verify the applied package before its transaction is committed."""
    verify = run_verify(target=target_root, package=package_root)
    manifest = load_manifest(package_root)
    installed_manifest = target_root / MANAGED_CORE_DIR / "MANIFEST.json"
    manifest_ok = installed_manifest.is_file() and not installed_manifest.is_symlink() and (
        sha256_file(installed_manifest) == sha256_file(manifest.path)
    )
    scan = _run_post_install_secret_scan(target_root=target_root, resolution=resolution)
    scan_ok = scan["ok"]
    scan_exit = scan.get("exitCode")
    scan_mode = scan["mode"]
    scan_error_type = scan.get("errorType")
    receipt_ok = resolution is not None and resolution.verification.get("providerReceipt") and resolution.verification.get("providerTreeRequired") is True and resolution.verification.get("consumerTreeRequired") is True and resolution.verification.get("noUpstreamScanOrMutation") is True
    result = {
        "manifest": "pass" if manifest_ok else "fail",
        "managedHashes": "pass" if verify.exit_code == EXIT_OK else "fail",
        "closure": "pass" if verify.exit_code == EXIT_OK else "fail",
        "selfScan": "pass" if scan_ok else "fail",
        "cleanroom": "receipt-bound-pass" if receipt_ok else "fail",
        "verifyExitCode": verify.exit_code,
        "selfScanMode": scan_mode,
    }
    if scan_exit is not None:
        result["selfScanExitCode"] = scan_exit
    if scan_error_type is not None:
        result["selfScanErrorType"] = scan_error_type
    if not all(result[key] in {"pass", "receipt-bound-pass"} for key in ("manifest", "managedHashes", "closure", "selfScan", "cleanroom")):
        raise InvalidPackageError("Post-install managed upgrade verification failed", details=result)
    return result


def _run_post_install_secret_scan(
    *, target_root: Path, resolution: UpgradeResolution | None
) -> dict[str, Any]:
    """Run the installed scanner with an exact optional change-scope receipt."""
    scanner = target_root / "scripts/gitops/secret_scan.py"
    if not scanner.is_file() or scanner.is_symlink():
        return {"ok": False, "mode": "full", "errorType": "missing-scanner"}

    scan_args = [sys.executable, str(scanner), "--repo", str(target_root)]
    scan_mode = "full"
    evidence_file: Path | None = None
    scoped = resolution.verification.get("changeScopedSecretScan") if resolution is not None else None
    if scoped is not None:
        # The resolution loader validated the exact digest and shape. Keep the
        # evidence outside the consumer and delete it in all cases.
        scan_mode = "change-scoped"
        evidence_fd, evidence_name = tempfile.mkstemp(prefix="ide-change-scan-", suffix=".json")
        os.close(evidence_fd)
        evidence_file = Path(evidence_name)
        try:
            evidence_file.write_text(
                json.dumps(scoped["evidence"], sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            scan_args.extend(["--baseline-evidence", str(evidence_file)])
            result = subprocess.run(
                scan_args, cwd=target_root, text=True, capture_output=True, timeout=60, check=False
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "mode": scan_mode, "errorType": "timeout"}
        finally:
            evidence_file.unlink(missing_ok=True)
    else:
        try:
            result = subprocess.run(
                scan_args, cwd=target_root, text=True, capture_output=True, timeout=60, check=False
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "mode": scan_mode, "errorType": "timeout"}
    return {"ok": result.returncode == 0, "mode": scan_mode, "exitCode": result.returncode}


def run_plan(
    *,
    target: Path,
    package: Path | None = None,
    command: str = "plan",
    dry_run: bool = True,
    resolution_manifest: Path | None = None,
) -> EngineResult:
    package_root, target_root = _prepare(target=target, package=package)
    openclaw_admission = _openclaw_admission(package_root, target_root)
    recovery = _maybe_recover(target_root, mutate=False)
    manifest = load_manifest(package_root)
    migration = load_migration_catalog(package_root)
    prior = load_installed_state(target_root)

    # Planning is deliberately non-mutating.  Report whether an older
    # consumer would receive the managed Fast declaration during install.
    normalized_fast = _normalize_consumer_workflow_contract(target_root, mutate=False)
    plan = build_plan(
        command=command,
        package_root=package_root,
        target_root=target_root,
        manifest=manifest,
        migration=migration,
        prior=prior,
        dry_run=True,
    )
    resolution = _resolve_authorized_upgrade(
        resolution_manifest=resolution_manifest,
        target_root=target_root,
        package_root=package_root,
        manifest=manifest,
        prior=prior,
        plan=plan,
    )
    if resolution is not None:
        plan = build_plan(
            command=command,
            package_root=package_root,
            target_root=target_root,
            manifest=manifest,
            migration=migration,
            prior=prior,
            dry_run=True,
            authorized_replacements=resolution.paths,
        )
    ci_trigger_audit = _repository_ci_trigger_audit(package_root, target_root)
    exit_code = EXIT_CONFLICT if plan.has_conflicts else EXIT_OK
    payload = _plan_payload(
        plan,
        recovery=recovery,
        installerVersion=installer_version,
        normalizedFastWorkflowName=normalized_fast,
        repositoryCiTriggerAudit=ci_trigger_audit,
        managedUpgradeResolution=resolution.to_dict() if resolution else None,
        openclawAdmission=openclaw_admission,
    )
    return EngineResult(exit_code=exit_code, payload=payload)


def run_install_or_update(
    *,
    target: Path,
    package: Path | None = None,
    command: str,
    dry_run: bool = False,
    resolution_manifest: Path | None = None,
) -> EngineResult:
    package_root, target_root = _prepare(target=target, package=package)
    openclaw_admission = _openclaw_admission(package_root, target_root)
    recovery = _maybe_recover(target_root, mutate=not dry_run)
    manifest = load_manifest(package_root)
    migration = load_migration_catalog(package_root)

    prior = load_installed_state(target_root)
    package_manifest_digest = _validate_package_identity(manifest, prior)

    # The installer is the authoritative upgrade path.  Early consumers have
    # a repository-owned config without the later receipt-bound Fast key; add
    # only that fixed managed declaration.  Never infer a consumer CI name.
    # A digest-bound resolution must be completely preflighted before any
    # consumer write; its clean-worktree proof also excludes config repair.
    normalized_fast = _normalize_consumer_workflow_contract(
        target_root, mutate=not dry_run and resolution_manifest is None
    )
    if command == "update" and prior is None:
        raise InvalidPackageError(
            "update requires an existing installed-state; use install for first-time setup"
        )

    plan = build_plan(
        command=command,
        package_root=package_root,
        target_root=target_root,
        manifest=manifest,
        migration=migration,
        prior=prior,
        dry_run=dry_run,
    )
    resolution = _resolve_authorized_upgrade(
        resolution_manifest=resolution_manifest,
        target_root=target_root,
        package_root=package_root,
        manifest=manifest,
        prior=prior,
        plan=plan,
    )
    if resolution_manifest is not None and normalized_fast:
        raise InvalidPackageError(
            "Digest-bound resolution refuses unrelated workflow-config normalization"
        )
    if resolution is not None:
        plan = build_plan(
            command=command,
            package_root=package_root,
            target_root=target_root,
            manifest=manifest,
            migration=migration,
            prior=prior,
            dry_run=dry_run,
            authorized_replacements=resolution.paths,
        )
    ci_trigger_audit = _repository_ci_trigger_audit(package_root, target_root)
    payload = _plan_payload(
        plan,
        recovery=recovery,
        installerVersion=installer_version,
        normalizedFastWorkflowName=normalized_fast,
        repositoryCiTriggerAudit=ci_trigger_audit,
        managedUpgradeResolution=resolution.to_dict() if resolution else None,
        managedPackageManifestDigest=package_manifest_digest,
        openclawAdmission=openclaw_admission,
        candidateExports=_export_conflict_candidates(
            target_root=target_root,
            package_version=manifest.package_version,
            prior=prior,
            plan=plan,
        ),
    )

    if plan.has_conflicts:
        return EngineResult(exit_code=EXIT_CONFLICT, payload=payload)

    if dry_run:
        payload["applied"] = False
        return EngineResult(exit_code=EXIT_OK, payload=payload)

    result = apply_plan(
        target_root=target_root,
        package_root=package_root,
        manifest=manifest,
        plan=plan,
        prior=prior,
        resolution=resolution,
        post_apply_check=(
            lambda: _post_install_verification(
                target_root=target_root, package_root=package_root, resolution=resolution
            )
            if resolution is not None
            else {}
        ),
    )
    payload["applied"] = True
    payload["transaction"] = result
    payload["postInstallVerification"] = result.get("postInstallVerification")
    return EngineResult(exit_code=EXIT_OK, payload=payload)


def run_same_version_repair(
    *,
    target: Path,
    package: Path | None = None,
    repair_manifest: Path | None = None,
    dry_run: bool = False,
) -> EngineResult:
    """Apply only an explicit v2.5.2 source-identity repair.

    This path intentionally does not fall through to install/update planning:
    a same-version manifest collision is repaired only for the exact managed
    files named by the signed-by-content receipt.  ``apply_plan`` supplies the
    ordinary transaction lock, backup journal, rollback, and managed write
    lease.
    """
    if repair_manifest is None:
        raise InvalidPackageError("same-version repair requires --repair-manifest")
    package_root, target_root = _prepare(target=target, package=package)
    manifest = load_manifest(package_root)
    prior = load_installed_state(target_root)
    repair = load_and_validate_same_version_repair(
        repair_manifest,
        target_root=target_root,
        package_root=package_root,
        manifest=manifest,
        prior=prior,
    )
    openclaw_admission = _openclaw_admission(package_root, target_root)

    actions = [
        PlanAction(
            op=OpKind.REPLACE,
            path=item.path,
            entry_id=next(
                entry.id for entry in manifest.active_entries() if entry.destination == item.path
            ),
            reason="explicit same-version exact-source repair",
            source_hash=item.source_digest,
            classification="same_version_source_repair",
        )
        for item in repair.paths
    ]
    # The manifest is itself a managed destination and must move with the
    # source identity; installed-state is maintained by the transaction.
    actions.append(
        PlanAction(
            op=OpKind.REPLACE,
            path=f"{MANAGED_CORE_DIR}/MANIFEST.json",
            entry_id="package-manifest",
            reason="record repaired package manifest identity",
            source_hash=repair.manifest_digest,
            classification="same_version_source_repair",
        )
    )
    plan = Plan(
        command="repair",
        package_version=PACKAGE_VERSION_TARGET,
        target=str(target_root),
        dry_run=dry_run,
        actions=actions,
    )
    payload = plan.to_dict()
    payload.update(
        {
            "command": "repair",
            "installerVersion": installer_version,
            "sourceIdentity": {
                "repository": repair.source_repository,
                "ref": repair.source_ref,
                "commit": repair.source_commit,
                "tree": repair.source_tree,
                "manifestDigest": repair.manifest_digest,
            },
            "installedManifestDigest": repair.installed_manifest_digest,
            "repairManifest": str(repair.receipt_path),
            "repairManifestDigest": repair.receipt_digest,
            "openclawAdmission": openclaw_admission,
        }
    )
    if dry_run:
        payload["applied"] = False
        return EngineResult(exit_code=EXIT_OK, payload=payload)

    result = apply_plan(
        target_root=target_root,
        package_root=package_root,
        manifest=manifest,
        plan=plan,
        prior=prior,
    )
    payload["applied"] = True
    payload["transaction"] = result
    return EngineResult(exit_code=EXIT_OK, payload=payload)


def run_drift(
    *,
    target: Path,
    package: Path | None = None,
) -> EngineResult:
    package_root, target_root = _prepare(target=target, package=package)
    recovery = _maybe_recover(target_root, mutate=False)
    manifest = load_manifest(package_root)
    migration = load_migration_catalog(package_root)
    prior = load_installed_state(target_root)
    items = build_drift_report(
        package_root=package_root,
        target_root=target_root,
        manifest=manifest,
        prior=prior,
        migration=migration,
    )
    meaningful = meaningful_drift(items)
    payload = {
        "schemaVersion": 1,
        "command": "drift",
        "packageVersion": manifest.package_version,
        "target": str(target_root),
        "installerVersion": installer_version,
        "recovery": recovery,
        "drift": [i.to_dict() for i in meaningful],
        "all": [i.to_dict() for i in items],
        "summary": {
            "driftCount": len(meaningful),
            "managedFileCount": len(items),
        },
    }
    return EngineResult(exit_code=EXIT_DRIFT if meaningful else EXIT_OK, payload=payload)


def run_verify(
    *,
    target: Path,
    package: Path | None = None,
) -> EngineResult:
    package_root, target_root = _prepare(target=target, package=package)
    recovery = _maybe_recover(target_root, mutate=False)
    manifest = load_manifest(package_root)
    migration = load_migration_catalog(package_root)
    prior = load_installed_state(target_root)
    plan = build_plan(
        command="verify",
        package_root=package_root,
        target_root=target_root,
        manifest=manifest,
        migration=migration,
        prior=prior,
        dry_run=True,
    )
    items = build_drift_report(
        package_root=package_root,
        target_root=target_root,
        manifest=manifest,
        prior=prior,
        migration=migration,
    )
    meaningful = meaningful_drift(items)
    needs_work = [a for a in plan.actions if a.op.value != "noop"]
    ci_trigger_audit = _repository_ci_trigger_audit(package_root, target_root)
    payload = _plan_payload(
        plan,
        recovery=recovery,
        installerVersion=installer_version,
        drift=[i.to_dict() for i in meaningful],
        verify={
            "ok": not plan.has_conflicts and not meaningful and not needs_work,
            "needsWorkCount": len(needs_work),
        },
        repositoryCiTriggerAudit=ci_trigger_audit,
    )
    # The verify response replaces planning drift with the authoritative
    # byte-level report; keep its summary consistent with that public field.
    payload["summary"]["driftCount"] = len(meaningful)
    if plan.has_conflicts:
        return EngineResult(exit_code=EXIT_CONFLICT, payload=payload)
    if meaningful or needs_work:
        return EngineResult(exit_code=EXIT_DRIFT, payload=payload)
    return EngineResult(exit_code=EXIT_OK, payload=payload)


def run_version(
    *,
    target: Path | None = None,
    package: Path | None = None,
) -> EngineResult:
    package_root = _detect_package_root(package)
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "command": "version",
        "installerVersion": installer_version,
        "packageRoot": str(package_root),
    }
    try:
        manifest = load_manifest(package_root)
        payload["packageVersion"] = manifest.package_version
    except InstallerError as exc:
        payload["packageVersion"] = None
        payload["packageError"] = exc.message
    if target is not None:
        try:
            target_root = require_git_repo(target)
            prior = load_installed_state(target_root)
            payload["target"] = str(target_root)
            payload["installedVersion"] = prior.package_version if prior else None
            payload["managedCoreDir"] = MANAGED_CORE_DIR
        except InstallerError as exc:
            payload["targetError"] = exc.message
    return EngineResult(exit_code=EXIT_OK, payload=payload)


def run_rollback(*, target: Path) -> EngineResult:
    target_root = require_git_repo(target)
    try:
        result = rollback_last(target_root)
    except RollbackError as exc:
        return EngineResult(
            exit_code=exc.exit_code,
            payload={
                "schemaVersion": 1,
                "command": "rollback",
                "ok": False,
                "error": exc.message,
                "details": exc.details,
                "exitCode": exc.exit_code,
            },
        )
    return EngineResult(
        exit_code=EXIT_OK,
        payload={
            "schemaVersion": 1,
            "command": "rollback",
            "ok": True,
            "result": result,
        },
    )
