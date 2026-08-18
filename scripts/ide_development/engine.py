"""High-level installer operations."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from . import __version__ as installer_version
from .constants import EXIT_CONFLICT, EXIT_DRIFT, EXIT_OK, MANAGED_CORE_DIR
from .errors import InstallerError, InvalidPackageError, RollbackError
from .manifest import load_manifest, load_migration_catalog
from .paths import require_git_repo, resolve_dir, same_path
from .plan import Plan, build_drift_report, build_plan, meaningful_drift
from .state import load_installed_state
from .transaction import apply_plan, current_tx_dir, read_journal, recover_interrupted, rollback_last
from .io_atomic import atomic_write_bytes


CONSUMER_CONFIG = Path(".github/linktrend-gitops-consumer.json")
MANAGED_FAST_WORKFLOW = "Linktrend Fast Checks"
MANAGED_RUNNER_TYPE = "github-hosted"
RETIRED_RUNNER_TYPE = "linktrend-private-macos-arm64"
CI_CONTRACT_MODULE_REL = Path("scripts/gitops/repository_ci_contract.py")


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


def _repository_ci_trigger_audit(package_root: Path, target_root: Path) -> dict[str, Any]:
    ci_module = _load_repository_ci_contract_module(package_root)
    return ci_module.installer_audit_repository_ci_triggers(target_root)


def run_plan(
    *,
    target: Path,
    package: Path | None = None,
    command: str = "plan",
    dry_run: bool = True,
) -> EngineResult:
    package_root, target_root = _prepare(target=target, package=package)
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
    ci_trigger_audit = _repository_ci_trigger_audit(package_root, target_root)
    exit_code = EXIT_CONFLICT if plan.has_conflicts else EXIT_OK
    payload = _plan_payload(
        plan,
        recovery=recovery,
        installerVersion=installer_version,
        normalizedFastWorkflowName=normalized_fast,
        repositoryCiTriggerAudit=ci_trigger_audit,
    )
    return EngineResult(exit_code=exit_code, payload=payload)


def run_install_or_update(
    *,
    target: Path,
    package: Path | None = None,
    command: str,
    dry_run: bool = False,
) -> EngineResult:
    package_root, target_root = _prepare(target=target, package=package)
    recovery = _maybe_recover(target_root, mutate=not dry_run)
    manifest = load_manifest(package_root)
    migration = load_migration_catalog(package_root)

    # The installer is the authoritative upgrade path.  Early consumers have
    # a repository-owned config without the later receipt-bound Fast key; add
    # only that fixed managed declaration.  Never infer a consumer CI name.
    normalized_fast = _normalize_consumer_workflow_contract(target_root, mutate=not dry_run)
    prior = load_installed_state(target_root)

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
    ci_trigger_audit = _repository_ci_trigger_audit(package_root, target_root)
    payload = _plan_payload(
        plan,
        recovery=recovery,
        installerVersion=installer_version,
        normalizedFastWorkflowName=normalized_fast,
        repositoryCiTriggerAudit=ci_trigger_audit,
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
    prior = load_installed_state(target_root)
    items = build_drift_report(
        package_root=package_root,
        target_root=target_root,
        manifest=manifest,
        prior=prior,
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
