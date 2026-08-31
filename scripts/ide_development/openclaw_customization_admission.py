"""OpenClaw-only customization-scoped v2.5.2 admission.

Checks LiNKtrend Prime customization paths from a validated consumer
manifest plus v2.5.2 managed/transaction-changed destinations. Untouched
upstream OpenClaw is never scanned and never required to be repaired.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from .errors import InvalidPackageError
KIND = "openclaw-customization-admission"
BOUNDARY_KIND = "openclaw-prime-customization-boundary"
INSTALLER_VERSION = "2.5.2"
REPOSITORY = "linktrend/openclaw_prime"
BOUNDARY_REL = ".linktrend/openclaw-prime/customization-boundary.json"
SCHEMA_REL = "core/managed-core/schemas/openclaw-customization-admission.schema.json"
INSTALLED_STATE_REL = ".ide-development/installed-state.json"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SKIPPED_KIND = "skipped_input"
Scanner = Callable[[list[str]], Mapping[str, Any]]


class OpenClawAdmissionError(InvalidPackageError):
    """Fail-closed OpenClaw customization admission refusal."""


def _require_oid(value: Any, code: str) -> str:
    if not isinstance(value, str) or not HEX40.fullmatch(value):
        raise OpenClawAdmissionError(code)
    return value


def _require_relpath(value: Any, code: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or ".." in PurePosixPath(value).parts
        or ":" in value
    ):
        raise OpenClawAdmissionError(code)
    return value


def _identity(raw: Any, code: str) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        raise OpenClawAdmissionError(code)
    return {
        "commit": _require_oid(raw.get("commit"), code),
        "tree": _require_oid(raw.get("tree"), code),
    }


def _load_json(path: Path, code: str) -> Any:
    if path.is_symlink() or not path.is_file():
        raise OpenClawAdmissionError(code)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OpenClawAdmissionError(code) from exc


def _path_matches(candidate: str, rule: str) -> bool:
    if candidate == rule or candidate.startswith(rule + "/"):
        return True
    return rule.endswith("-") and candidate.startswith(rule)


def _boundary(path: Path) -> dict[str, Any]:
    payload = _load_json(path, "boundary-invalid")
    if not isinstance(payload, dict):
        raise OpenClawAdmissionError("boundary-invalid")
    if payload.get("schemaVersion") != 1 or payload.get("kind") != BOUNDARY_KIND:
        raise OpenClawAdmissionError("boundary-kind-mismatch")

    prime = payload.get("prime")
    if not isinstance(prime, Mapping) or prime.get("repository") != REPOSITORY:
        raise OpenClawAdmissionError("boundary-invalid")
    prime_identity = _identity(prime, "boundary-invalid")

    upstream = payload.get("upstream")
    if not isinstance(upstream, Mapping) or upstream.get("repository") != "openclaw/openclaw":
        raise OpenClawAdmissionError("boundary-invalid")
    pin = _identity(upstream.get("classificationPin"), "upstream-identity-drift")

    exclusion = payload.get("exclusion")
    forbidden_raw = exclusion.get("forbiddenWholeTrees") if isinstance(exclusion, Mapping) else None
    if not isinstance(forbidden_raw, list) or not forbidden_raw:
        raise OpenClawAdmissionError("boundary-invalid")
    forbidden = [_require_relpath(item, "boundary-invalid") for item in forbidden_raw]

    owned = payload.get("linktrendOwned")
    if not isinstance(owned, Mapping):
        raise OpenClawAdmissionError("boundary-invalid")
    owned_prefixes: list[str] = []
    owned_exact_paths: list[str] = []
    for group in ("prefixes", "exactPaths"):
        entries = owned.get(group)
        if not isinstance(entries, list):
            raise OpenClawAdmissionError("boundary-invalid")
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise OpenClawAdmissionError("boundary-invalid")
            path = _require_relpath(entry.get("path"), "boundary-invalid")
            (owned_prefixes if group == "prefixes" else owned_exact_paths).append(path)

    ide = payload.get("ideManaged")
    if not isinstance(ide, Mapping) or ide.get("separateFromLinktrendOwnedInventory") is not True:
        raise OpenClawAdmissionError("boundary-invalid")
    inventory_path = _require_relpath(ide.get("inventoryPath"), "boundary-invalid")
    if inventory_path != INSTALLED_STATE_REL:
        raise OpenClawAdmissionError("boundary-invalid")
    ide_prefixes = ide.get("prefixes")
    if not isinstance(ide_prefixes, list) or not ide_prefixes:
        raise OpenClawAdmissionError("boundary-invalid")
    ide_prefixes = [_require_relpath(item, "boundary-invalid") for item in ide_prefixes]
    overlays = ide.get("overlayOnUpstreamExactPaths") or []
    if not isinstance(overlays, list):
        raise OpenClawAdmissionError("boundary-invalid")
    overlays = [_require_relpath(item, "boundary-invalid") for item in overlays]

    transactions = payload.get("ideTransactionChanged")
    if not isinstance(transactions, Mapping) or transactions.get("separateFromIdeManagedInventory") is not True:
        raise OpenClawAdmissionError("boundary-invalid")
    transaction_paths = transactions.get("paths")
    if not isinstance(transaction_paths, list):
        raise OpenClawAdmissionError("boundary-invalid")
    transaction_paths = [_require_relpath(item, "boundary-invalid") for item in transaction_paths]
    records_raw = transactions.get("records")
    if not isinstance(records_raw, list):
        raise OpenClawAdmissionError("boundary-invalid")
    records: list[dict[str, Any]] = []
    for record in records_raw:
        if not isinstance(record, Mapping):
            raise OpenClawAdmissionError("boundary-invalid")
        receipt = _require_relpath(record.get("receiptPath"), "boundary-invalid")
        paths = record.get("paths")
        if not isinstance(paths, list):
            raise OpenClawAdmissionError("boundary-invalid")
        records.append(
            {"receiptPath": receipt, "paths": [_require_relpath(item, "boundary-invalid") for item in paths]}
        )

    baseline_raw = payload.get("preExistingFindings", [])
    if not isinstance(baseline_raw, list):
        raise OpenClawAdmissionError("boundary-invalid")
    baseline_findings = [_finding(item) for item in baseline_raw]
    declared_missing = ide.get("declaredMissingLocally") or []
    if not isinstance(declared_missing, list):
        raise OpenClawAdmissionError("boundary-invalid")
    declared_missing = [_require_relpath(item, "boundary-invalid") for item in declared_missing]

    # Validate declarations before invoking the scanner. A forged forbidden
    # path must never expand the scan scope.
    declared = owned_prefixes + owned_exact_paths + ide_prefixes + overlays + transaction_paths
    if any(_path_matches(candidate, tree) for candidate in declared for tree in forbidden):
        raise OpenClawAdmissionError("forbidden-path")
    return {
        "prime": {"repository": REPOSITORY, **prime_identity},
        "upstream": {"repository": "openclaw/openclaw", "classificationPin": pin},
        "forbiddenWholeTrees": forbidden,
        "ownedPrefixes": owned_prefixes,
        "ownedExactPaths": owned_exact_paths,
        "ide": {
            "inventoryPath": inventory_path,
            "packageName": ide.get("packageName"),
            "packageVersion": ide.get("packageVersion"),
            "destinationCount": ide.get("destinationCount"),
            "prefixes": ide_prefixes,
            "overlayOnUpstreamExactPaths": overlays,
            "declaredMissingLocally": declared_missing,
        },
        "transaction": {"records": records, "paths": transaction_paths},
        "preExistingFindings": baseline_findings,
    }


def _finding(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise OpenClawAdmissionError("scanner-error")
    row: dict[str, Any] = {
        "kind": raw.get("kind"),
        "path": _require_relpath(raw.get("path"), "scanner-error"),
        "rule": raw.get("rule"),
    }
    if not isinstance(row["kind"], str) or not row["kind"]:
        raise OpenClawAdmissionError("scanner-error")
    if not isinstance(row["rule"], str) or not row["rule"]:
        raise OpenClawAdmissionError("scanner-error")
    if "line" in raw:
        line = raw["line"]
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            raise OpenClawAdmissionError("scanner-error")
        row["line"] = line
    if "field" in raw:
        field = raw["field"]
        if not isinstance(field, str) or not field:
            raise OpenClawAdmissionError("scanner-error")
        row["field"] = field
    if "digest" in raw:
        digest = raw["digest"]
        if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
            raise OpenClawAdmissionError("scanner-error")
        row["digest"] = digest
    if "detail" in raw:
        detail = raw["detail"]
        if not isinstance(detail, str) or not detail:
            raise OpenClawAdmissionError("scanner-error")
        row["detail"] = detail
    return row


def _path_is_forbidden(path: str, forbidden: list[str]) -> bool:
    return any(_path_matches(path, tree) for tree in forbidden)


def _walk_owned_prefix(root: Path, prefix: str, forbidden: list[str]) -> set[str]:
    base = root / Path(prefix)
    if not base.exists():
        if prefix.endswith("-"):
            parent = root / Path(prefix).parent
            if parent.is_dir() and not parent.is_symlink():
                return {
                    path.relative_to(root).as_posix()
                    for path in parent.rglob("*")
                    if path.is_file()
                    and not path.is_symlink()
                    and _path_matches(path.relative_to(root).as_posix(), prefix)
                    and not _path_is_forbidden(path.relative_to(root).as_posix(), forbidden)
                }
        return set()
    if base.is_symlink():
        raise OpenClawAdmissionError("symlink-path")
    if base.is_file():
        return {prefix} if not _path_is_forbidden(prefix, forbidden) else set()

    paths: set[str] = set()
    for directory, dirnames, filenames in os.walk(base, followlinks=False):
        directory_path = Path(directory)
        kept_dirs: list[str] = []
        for name in dirnames:
            candidate = (directory_path / name).relative_to(root).as_posix()
            if _path_is_forbidden(candidate, forbidden):
                continue
            child = directory_path / name
            if child.is_symlink():
                raise OpenClawAdmissionError("symlink-path")
            kept_dirs.append(name)
        dirnames[:] = kept_dirs
        for name in filenames:
            candidate = (directory_path / name).relative_to(root).as_posix()
            if _path_is_forbidden(candidate, forbidden):
                continue
            path = directory_path / name
            if path.is_symlink():
                raise OpenClawAdmissionError("symlink-path")
            paths.add(candidate)
    return paths


def _owned_paths(root: Path, boundary: Mapping[str, Any]) -> set[str]:
    paths: set[str] = set()
    for owned in boundary["ownedPrefixes"] + boundary["ownedExactPaths"]:
        paths.update(_walk_owned_prefix(root, owned, boundary["forbiddenWholeTrees"]))
    return paths


def _declared_ide_paths(root: Path, boundary: Mapping[str, Any]) -> set[str]:
    inventory = root / INSTALLED_STATE_REL
    if not inventory.exists():
        return set()
    raw = _load_json(inventory, "ide-inventory-invalid")
    if not isinstance(raw, Mapping) or not isinstance(raw.get("files"), Mapping):
        raise OpenClawAdmissionError("ide-inventory-invalid")
    if raw.get("packageVersion") != INSTALLER_VERSION:
        raise OpenClawAdmissionError("ide-package-version-mismatch")
    paths: set[str] = set()
    for value in raw["files"]:
        path = _require_relpath(value, "ide-inventory-invalid")
        if not any(_path_matches(path, prefix) for prefix in boundary["ide"]["prefixes"]):
            raise OpenClawAdmissionError("ide-inventory-out-of-boundary")
        if _path_is_forbidden(path, boundary["forbiddenWholeTrees"]):
            raise OpenClawAdmissionError("forbidden-path")
        candidate = root / Path(path)
        if candidate.is_symlink():
            raise OpenClawAdmissionError("symlink-path")
        # A prior package can declare paths that are intentionally absent in
        # the current consumer (for example the legacy core/ prefix). Those
        # paths are identity evidence, not scanner inputs.
        if candidate.is_file():
            paths.add(path)
    return paths


def _present_paths(root: Path, paths: list[str]) -> tuple[set[str], list[str]]:
    present: set[str] = set()
    missing: list[str] = []
    for rel in paths:
        candidate = root / Path(rel)
        if candidate.is_symlink():
            raise OpenClawAdmissionError("symlink-path")
        if candidate.is_file():
            present.add(rel)
        else:
            missing.append(rel)
    return present, missing


def _run_scanner(scanner: Scanner, paths: list[str]) -> Mapping[str, Any]:
    try:
        result = scanner(paths)
    except TimeoutError as exc:
        raise OpenClawAdmissionError("scanner-timeout") from exc
    except OpenClawAdmissionError:
        raise
    except Exception as exc:
        raise OpenClawAdmissionError("scanner-error") from exc
    if not isinstance(result, Mapping):
        raise OpenClawAdmissionError("scanner-error")
    error_type = result.get("errorType")
    if error_type == "timeout":
        raise OpenClawAdmissionError("scanner-timeout")
    if error_type:
        raise OpenClawAdmissionError("scanner-error")
    if not isinstance(result.get("ok"), bool):
        raise OpenClawAdmissionError("scanner-error")
    return result


def _finding_key(row: Mapping[str, Any]) -> str:
    # Findings are compared after strict shape validation and without secret
    # values. The digest/line/field binding keeps an old finding from masking
    # a changed customization.
    return json.dumps(dict(sorted(row.items())), sort_keys=True, separators=(",", ":"))


def _baseline_findings(
    *,
    boundary: Mapping[str, Any],
    observed_upstream: Mapping[str, Any] | None,
    scan: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    rows: list[Any] = list(boundary.get("preExistingFindings") or [])
    if isinstance(observed_upstream, Mapping):
        observed = observed_upstream.get("findings") or observed_upstream.get("preExistingFindings") or []
        if not isinstance(observed, list):
            raise OpenClawAdmissionError("scanner-error")
        rows.extend(observed)
    supplied = scan.get("baselineFindings") or scan.get("preExistingFindings") or []
    if not isinstance(supplied, list):
        raise OpenClawAdmissionError("scanner-error")
    rows.extend(supplied)
    normalized: dict[str, dict[str, Any]] = {}
    for raw in rows:
        row = _finding(raw)
        normalized[_finding_key(row)] = row
    return normalized


def admit_openclaw_customization(
    *,
    consumer_root: Path,
    package_root: Path | None = None,
    boundary_path: Path | None = None,
    manifest_path: Path | None = None,
    scanner: Scanner,
    observed_upstream: Mapping[str, Any] | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Admit the live boundary's owned and explicitly declared IDE paths."""
    del package_root, timeout_seconds
    consumer_root = consumer_root.resolve()
    path = Path(boundary_path or manifest_path or consumer_root / BOUNDARY_REL)
    if not path.is_absolute():
        path = consumer_root / path
    boundary = _boundary(path)

    checked_set = _owned_paths(consumer_root, boundary)
    checked_set.update(_declared_ide_paths(consumer_root, boundary))
    overlay_present, omitted_overlay = _present_paths(
        consumer_root, boundary["ide"]["overlayOnUpstreamExactPaths"]
    )
    checked_set.update(overlay_present)
    transaction_present, omitted_transaction = _present_paths(
        consumer_root, boundary["transaction"]["paths"]
    )
    checked_set.update(transaction_present)
    checked = sorted(checked_set)
    if any(_path_is_forbidden(item, boundary["forbiddenWholeTrees"]) for item in checked):
        raise OpenClawAdmissionError("forbidden-path")

    scan = _run_scanner(scanner, checked)
    raw_findings = scan.get("findings")
    if not isinstance(raw_findings, list):
        raise OpenClawAdmissionError("scanner-error")
    scoped: list[dict[str, Any]] = []
    for raw in raw_findings:
        row = _finding(raw)
        if _path_is_forbidden(row["path"], boundary["forbiddenWholeTrees"]):
            raise OpenClawAdmissionError("forbidden-path")
        if row["path"] in checked_set:
            scoped.append(row)
    baseline = _baseline_findings(
        boundary=boundary, observed_upstream=observed_upstream, scan=scan
    )
    new_findings = [row for row in scoped if _finding_key(row) not in baseline]
    for row in new_findings:
        if row["kind"] == SKIPPED_KIND:
            raise OpenClawAdmissionError("new-skipped-input")
        raise OpenClawAdmissionError("new-or-changed-finding")
    # A scanner that failed without producing a finding is still a scanner
    # failure. A false ``ok`` is allowed only when every scoped finding is an
    # exact pre-existing finding from the completed rollout evidence.
    if scan.get("ok") is not True and not scoped:
        raise OpenClawAdmissionError("scanner-error")

    return {
        "schemaVersion": 1,
        "kind": KIND,
        "installerVersion": INSTALLER_VERSION,
        "repository": REPOSITORY,
        "prime": boundary["prime"],
        "upstream": boundary["upstream"],
        "boundary": {"path": path.name, "kind": BOUNDARY_KIND},
        "scope": {
            "linktrendOwned": {
                "prefixes": sorted(boundary["ownedPrefixes"]),
                "exactPaths": sorted(boundary["ownedExactPaths"]),
            },
            "ideManaged": boundary["ide"],
            "ideTransactionChanged": boundary["transaction"],
            "forbiddenWholeTrees": sorted(boundary["forbiddenWholeTrees"]),
        },
        "checkedPaths": checked,
        "findings": scoped,
        "preExistingFindings": sorted(baseline.values(), key=_finding_key),
        "omittedMissingPaths": sorted(
            set(omitted_overlay)
            | set(omitted_transaction)
            | set(boundary["ide"]["declaredMissingLocally"])
        ),
        "verdict": "admitted",
        "noUpstreamScanOrMutation": True,
    }
