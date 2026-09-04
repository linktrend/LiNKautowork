#!/usr/bin/env python3
"""Fail-closed, credential-free runtime preflight for governed checks.

The manifest is declarative.  This module only reads local platform/tool
metadata and executes version/probe commands named by that manifest; it never
looks for credentials, contacts a provider, or changes the checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

MANIFEST_RELATIVE_PATH = "core/managed-core/content/config/toolchain-manifest.json"
PACKAGED_MANIFEST_RELATIVE_PATH = ".ide-development/content/config/toolchain-manifest.json"
PACKAGED_CONFIG_ALIASES = {
    "core/managed-core/config/generated-output-closure.json": ".ide-development/config/generated-output-closure.json",
    ".github/linktrend-delivery-mode.json": ".ide-development/config/delivery.json",
}
SCHEMA_VERSION = 1
MANIFEST_KIND = "toolchain-manifest"
PREFLIGHT_KIND = "runtime-preflight-evidence"
PASS = "PASS"
ENVIRONMENT_BLOCKED = "ENVIRONMENT_BLOCKED"
NOT_RUN = "NOT_RUN"
SOURCE_FAILURE = "SOURCE_FAILURE"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
VERSION_RE = re.compile(r"(?<!\d)(\d+)(?:\.(\d+))?(?:\.(\d+))?(?!\d)")


class PreflightError(ValueError):
    """Malformed or unusable preflight declaration."""

    def __init__(self, code: str, detail: str, **diagnostics: Any) -> None:
        self.code = code
        self.detail = detail
        self.diagnostics = diagnostics
        suffix = f" {json.dumps(diagnostics, sort_keys=True)}" if diagnostics else ""
        super().__init__(f"{code}: {detail}{suffix}")


def _safe_relative(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PreflightError("manifest_invalid", f"{label} must be non-empty")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise PreflightError("manifest_invalid", f"{label} must be repository-relative", value=value)
    return path.as_posix()


def _manifest_path(root: Path, requested: str | Path | None) -> Path:
    if requested is not None:
        path = Path(requested)
        return path if path.is_absolute() else root / path
    source = root / MANIFEST_RELATIVE_PATH
    if source.is_file():
        return source
    return root / PACKAGED_MANIFEST_RELATIVE_PATH


def _required_config_path(root: Path, manifest_file: Path, declared: object, label: str) -> Path:
    relative = _safe_relative(declared, label)
    packaged = (root / PACKAGED_MANIFEST_RELATIVE_PATH).resolve()
    if manifest_file.resolve() == packaged:
        relative = PACKAGED_CONFIG_ALIASES.get(relative, relative)
    return root / relative


def _require_list(value: object, label: str, *, allow_empty: bool = True) -> list[Any]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise PreflightError("manifest_invalid", f"{label} must be a non-empty array" if not allow_empty else f"{label} must be an array")
    return value


def _require_object(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PreflightError("manifest_invalid", f"{label} must be an object")
    return value


def load_manifest(repo_root: Path | str, manifest_path: str | Path | None = None) -> dict[str, Any]:
    """Load and perform the runtime-critical validation of a toolchain manifest."""
    root = Path(repo_root).resolve()
    path = _manifest_path(root, manifest_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PreflightError("manifest_missing", "toolchain manifest is unavailable", path=str(path)) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise PreflightError("manifest_invalid", "toolchain manifest cannot be read", path=str(path)) from exc
    if not isinstance(payload, Mapping) or payload.get("schemaVersion") != SCHEMA_VERSION or payload.get("kind") != MANIFEST_KIND:
        raise PreflightError("manifest_invalid", "toolchain manifest identity is invalid")
    if not isinstance(payload.get("manifestVersion"), str) or not payload["manifestVersion"].startswith("toolchain-manifest/"):
        raise PreflightError("manifest_invalid", "manifestVersion must identify a versioned toolchain contract")
    checks = _require_list(payload.get("checks"), "checks", allow_empty=False)
    ids: set[str] = set()
    for index, raw in enumerate(checks):
        check = _require_object(raw, f"checks[{index}]")
        check_id = check.get("id")
        if not isinstance(check_id, str) or not check_id or check_id in ids:
            raise PreflightError("manifest_invalid", f"checks[{index}].id is missing or duplicated")
        ids.add(check_id)
        supported = _require_object(check.get("supported"), f"checks[{index}].supported")
        _require_list(supported.get("os"), f"checks[{index}].supported.os", allow_empty=False)
        _require_list(supported.get("architectures"), f"checks[{index}].supported.architectures", allow_empty=False)
        runner_class = check.get("runnerClass")
        if not isinstance(runner_class, str) or not runner_class:
            raise PreflightError("manifest_invalid", f"checks[{index}].runnerClass is required")
        for field in ("python", "node", "packageManager", "resources"):
            _require_object(check.get(field), f"checks[{index}].{field}")
        _require_list(check.get("systemTools"), f"checks[{index}].systemTools")
        _require_list(check.get("services"), f"checks[{index}].services")
        _require_list(check.get("requiredConfig"), f"checks[{index}].requiredConfig")
        network_policy = check.get("networkPolicy")
        if network_policy not in {"offline", "allow-listed", "online"}:
            raise PreflightError("manifest_invalid", f"checks[{index}].networkPolicy is invalid")
    return dict(payload)


def _normal_os(value: str) -> str:
    value = value.lower()
    return {"darwin": "macos", "windows": "windows", "linux": "linux"}.get(value, value)


def _normal_arch(value: str) -> str:
    value = value.lower()
    return {
        "aarch64": "arm64",
        "arm64": "arm64",
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "x86": "x86",
    }.get(value, value)


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    match = VERSION_RE.search(value)
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def _version_satisfies(observed: str, requirement: object) -> bool:
    if requirement in (None, "", False):
        return True
    actual = _version_tuple(observed)
    if actual is None or not isinstance(requirement, str):
        return False
    match = re.fullmatch(r"(>=|<=|==|>|<|~=)?\s*(\d+(?:\.\d+){0,2})", requirement.strip())
    if not match:
        return False
    expected = _version_tuple(match.group(2))
    if expected is None:
        return False
    operator = match.group(1) or "=="
    if operator == ">=":
        return actual >= expected
    if operator == "<=":
        return actual <= expected
    if operator == ">":
        return actual > expected
    if operator == "<":
        return actual < expected
    if operator == "~=":
        return actual >= expected and actual[:2] == expected[:2]
    return actual == expected


def _result(
    item: str,
    status: str,
    code: str,
    detail: str,
    *,
    classification: str = "environment",
    required: bool = True,
    resolved_path: str = "",
    observed: str = "",
) -> dict[str, Any]:
    return {
        "id": item,
        "status": status,
        "classification": classification,
        "code": code,
        "detail": detail,
        "required": required,
        "resolvedPath": resolved_path,
        "observed": observed,
    }


def _check_executable(
    root: Path,
    item: str,
    declaration: Mapping[str, Any],
    *,
    executable_finder: Callable[[str], str | None],
    command_runner: Callable[[Sequence[str], Path], Any],
) -> dict[str, Any]:
    required = bool(declaration.get("required", True))
    executable = declaration.get("executable")
    if not isinstance(executable, str) or not executable:
        return _result(item, SOURCE_FAILURE, "manifest_invalid", "executable declaration is missing", classification="application", required=required)
    resolved = executable_finder(executable)
    if not resolved:
        return _result(item, ENVIRONMENT_BLOCKED if required else NOT_RUN, "missing_tool", f"required executable is unavailable: {executable}", required=required)
    command = declaration.get("versionCommand", [resolved, "--version"])
    if not isinstance(command, list) or not command or any(not isinstance(arg, str) or not arg for arg in command):
        return _result(item, SOURCE_FAILURE, "manifest_invalid", "versionCommand must be an argv array", classification="application", required=required, resolved_path=resolved)
    try:
        completed = command_runner(command, root)
        return_code = int(getattr(completed, "returncode", 1))
        output = str(getattr(completed, "stdout", "") or "") + str(getattr(completed, "stderr", "") or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return _result(item, ENVIRONMENT_BLOCKED if required else NOT_RUN, "tool_unavailable", str(exc), required=required, resolved_path=resolved)
    if return_code:
        return _result(item, ENVIRONMENT_BLOCKED if required else NOT_RUN, "tool_unavailable", f"version probe exited {return_code}", required=required, resolved_path=resolved)
    requirement = declaration.get("version")
    if not _version_satisfies(output, requirement):
        return _result(item, ENVIRONMENT_BLOCKED if required else NOT_RUN, "tool_version_mismatch", f"version does not satisfy {requirement}", required=required, resolved_path=resolved, observed=output.strip()[-120:])
    return _result(item, PASS, "available", "tool and declared version are available", required=required, resolved_path=resolved, observed=output.strip()[-120:])


def _check_probe(
    root: Path,
    item: str,
    declaration: Mapping[str, Any],
    *,
    executable_finder: Callable[[str], str | None],
    command_runner: Callable[[Sequence[str], Path], Any],
) -> dict[str, Any]:
    required = bool(declaration.get("required", True))
    probe = declaration.get("probe")
    if not isinstance(probe, list) or not probe or any(not isinstance(arg, str) or not arg for arg in probe):
        return _result(item, SOURCE_FAILURE, "manifest_invalid", "probe must be an argv array", classification="application", required=required)
    executable = probe[0]
    resolved = executable_finder(executable) if "/" not in executable else executable if Path(executable).is_file() else None
    if not resolved:
        return _result(item, ENVIRONMENT_BLOCKED if required else NOT_RUN, "missing_service", f"service probe executable is unavailable: {executable}", required=required)
    command = [resolved, *probe[1:]]
    try:
        completed = command_runner(command, root)
        return_code = int(getattr(completed, "returncode", 1))
        output = str(getattr(completed, "stdout", "") or "") + str(getattr(completed, "stderr", "") or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return _result(item, ENVIRONMENT_BLOCKED if required else NOT_RUN, "service_unavailable", str(exc), required=required, resolved_path=resolved)
    if return_code:
        return _result(item, ENVIRONMENT_BLOCKED if required else NOT_RUN, "service_unavailable", f"service probe exited {return_code}", required=required, resolved_path=resolved, observed=output.strip()[-120:])
    return _result(item, PASS, "available", "service probe passed", required=required, resolved_path=resolved, observed=output.strip()[-120:])


def _physical_memory_bytes() -> int | None:
    if hasattr(os, "sysconf"):
        try:
            return int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
        except (OSError, ValueError):
            pass
    return None


def _command_runner(command: Sequence[str], root: Path) -> Any:
    return subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)


def _executable_finder(name: str) -> str | None:
    return shutil.which(name)


def _git_check(root: Path, args: Sequence[str]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    except OSError as exc:
        return False, str(exc)
    return completed.returncode == 0, (completed.stdout or completed.stderr).strip()[-300:]


def _snapshot(root: Path, paths: Sequence[str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for rel in paths:
        safe = _safe_relative(rel, "rollback path")
        path = root / safe
        if path.is_symlink():
            raise PreflightError("rollback_unsafe_path", "rollback does not follow symlinks", path=safe)
        if path.is_file():
            digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            mode = stat.S_IMODE(path.stat().st_mode)
            rows.append({"path": safe, "present": True, "digest": digest, "mode": f"{mode:04o}"})
        else:
            rows.append({"path": safe, "present": False, "digest": None, "mode": None})
    return {"paths": rows, "digest": _digest_json(rows)}


def _digest_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def capture_rollback_snapshot(repo_root: Path | str, paths: Sequence[str]) -> dict[str, Any]:
    """Capture byte and mode identities without retaining file contents."""
    return _snapshot(Path(repo_root).resolve(), paths)


def verify_rollback_snapshot(repo_root: Path | str, snapshot: Mapping[str, Any]) -> bool:
    rows = snapshot.get("paths") if isinstance(snapshot, Mapping) else None
    if not isinstance(rows, list):
        return False
    current = _snapshot(Path(repo_root).resolve(), [row.get("path", "") for row in rows if isinstance(row, Mapping)])
    return current.get("digest") == snapshot.get("digest") and current.get("paths") == rows


def run_disposable_rollback(
    repo_root: Path | str,
    paths: Sequence[str],
    mutate: Callable[[Path], None],
    rollback: Callable[[Path], None],
) -> dict[str, Any]:
    """Run apply/rollback callbacks in a temporary copy and verify exact restore."""
    source = Path(repo_root).resolve()
    safe_paths = [_safe_relative(path, "rollback path") for path in paths]
    with tempfile.TemporaryDirectory(prefix="ide-disposable-rollback-") as temporary:
        disposable = Path(temporary)
        for rel in safe_paths:
            original = source / rel
            target = disposable / rel
            if original.is_symlink():
                raise PreflightError("rollback_unsafe_path", "rollback does not follow symlinks", path=rel)
            if original.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, target)
        before = capture_rollback_snapshot(disposable, safe_paths)
        mutate(disposable)
        after_mutation = capture_rollback_snapshot(disposable, safe_paths)
        rollback(disposable)
        after_rollback = capture_rollback_snapshot(disposable, safe_paths)
    exact = before == after_rollback
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "disposable-rollback-evidence",
        "status": PASS if exact else SOURCE_FAILURE,
        "ok": exact,
        "disposable": True,
        "hostMutated": False,
        "predecessor": before,
        "afterMutation": after_mutation,
        "afterRollback": after_rollback,
        "exactRestore": exact,
    }


def _check_worktree(root: Path) -> dict[str, Any]:
    inside, inside_detail = _git_check(root, ["rev-parse", "--is-inside-work-tree"])
    if not inside or inside_detail != "true":
        return _result("linked-worktree", ENVIRONMENT_BLOCKED, "worktree_metadata_missing", "repository is not a Git worktree")
    git_dir, git_detail = _git_check(root, ["rev-parse", "--git-dir"])
    common_dir, common_detail = _git_check(root, ["rev-parse", "--git-common-dir"])
    if not git_dir or not common_dir:
        return _result("linked-worktree", ENVIRONMENT_BLOCKED, "worktree_metadata_missing", "Git worktree metadata is incomplete")
    return _result("linked-worktree", PASS, "available", "Git worktree and common metadata are readable", resolved_path=git_detail)


def run_preflight(
    repo_root: Path | str,
    *,
    profile: str | None = None,
    manifest_path: str | Path | None = None,
    executable_finder: Callable[[str], str | None] = _executable_finder,
    command_runner: Callable[[Sequence[str], Path], Any] = _command_runner,
    system: str | None = None,
    machine: str | None = None,
    physical_memory_bytes: int | None = None,
    cpu_count: int | None = None,
) -> dict[str, Any]:
    """Return rich preflight results; no provider or credential state is read."""
    root = Path(repo_root).resolve()
    resolved_manifest_path = _manifest_path(root, manifest_path)
    try:
        manifest = load_manifest(root, manifest_path)
    except PreflightError as exc:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "kind": PREFLIGHT_KIND,
            "ok": False,
            "status": SOURCE_FAILURE,
            "classification": "application",
            "manifest": str(resolved_manifest_path),
            "checks": [_result("manifest", SOURCE_FAILURE, exc.code, exc.detail, classification="application")],
        }
    checks = [check for check in manifest["checks"] if profile is None or profile in (check.get("profiles") or [profile])]
    if not checks:
        checks = list(manifest["checks"])
    results: list[dict[str, Any]] = []
    current_os = _normal_os(system or platform.system())
    current_arch = _normal_arch(machine or platform.machine())
    for check in checks:
        check_id = str(check["id"])
        supported = check["supported"]
        supported_os = {_normal_os(str(value)) for value in supported["os"]}
        supported_arch = {_normal_arch(str(value)) for value in supported["architectures"]}
        if current_os not in supported_os:
            results.append(_result(check_id, ENVIRONMENT_BLOCKED, "unsupported_os", f"{current_os} is not supported", required=True, observed=current_os))
            continue
        if current_arch not in supported_arch:
            results.append(_result(check_id, ENVIRONMENT_BLOCKED, "unsupported_architecture", f"{current_arch} is not supported", required=True, observed=current_arch))
            continue
        resources = check["resources"]
        memory = physical_memory_bytes if physical_memory_bytes is not None else _physical_memory_bytes()
        minimum_memory = resources.get("minimumMemoryMb")
        minimum_cpu = resources.get("minimumCpuCount")
        if isinstance(minimum_memory, int) and (memory is None or memory < minimum_memory * 1024 * 1024):
            results.append(_result(check_id, ENVIRONMENT_BLOCKED, "resource_limit", f"available memory is below {minimum_memory} MiB", required=True, observed=str(memory or "unavailable")))
            continue
        if isinstance(minimum_cpu, int) and (cpu_count or os.cpu_count() or 0) < minimum_cpu:
            results.append(_result(check_id, ENVIRONMENT_BLOCKED, "resource_limit", f"available CPU count is below {minimum_cpu}", required=True, observed=str(cpu_count or os.cpu_count() or 0)))
            continue
        results.append(_check_executable(root, f"{check_id}:python", check["python"], executable_finder=executable_finder, command_runner=command_runner))
        results.append(_check_executable(root, f"{check_id}:node", check["node"], executable_finder=executable_finder, command_runner=command_runner))
        results.append(_check_executable(root, f"{check_id}:package-manager", check["packageManager"], executable_finder=executable_finder, command_runner=command_runner))
        for tool in check["systemTools"]:
            declaration = _require_object(tool, f"{check_id}.systemTools")
            results.append(_check_executable(root, f"{check_id}:tool:{declaration.get('name', 'unnamed')}", declaration, executable_finder=executable_finder, command_runner=command_runner))
        for service in check["services"]:
            declaration = _require_object(service, f"{check_id}.services")
            results.append(_check_probe(root, f"{check_id}:service:{declaration.get('id', 'unnamed')}", declaration, executable_finder=executable_finder, command_runner=command_runner))
        missing_config = []
        for value in check["requiredConfig"]:
            config_path = _required_config_path(
                root,
                resolved_manifest_path,
                value,
                f"{check_id}.requiredConfig",
            )
            if not config_path.is_file():
                missing_config.append(config_path.relative_to(root).as_posix())
        if missing_config:
            results.append(_result(f"{check_id}:configuration", ENVIRONMENT_BLOCKED, "configuration_missing", "required non-secret configuration is unavailable", required=True, observed=",".join(missing_config)))
        policy = check["networkPolicy"]
        if policy == "allow-listed" and not check.get("allowedHosts"):
            results.append(_result(f"{check_id}:network", SOURCE_FAILURE, "network_policy_invalid", "allow-listed policy requires allowedHosts", classification="application"))
        else:
            results.append(_result(f"{check_id}:network", PASS, "policy_declared", "network policy checked without making a network request", required=True, observed=policy))
    write_access = root.is_dir() and os.access(root, os.W_OK)
    results.append(_result("repository-write-access", PASS if write_access else ENVIRONMENT_BLOCKED, "available" if write_access else "write_access_denied", "repository directory is writable" if write_access else "repository directory is not writable"))
    results.append(_check_worktree(root))
    required_failures = [row for row in results if row["required"] and row["status"] != PASS]
    source_failures = [row for row in required_failures if row["classification"] == "application"]
    blocked = [row for row in required_failures if row["classification"] == "environment"]
    status = SOURCE_FAILURE if source_failures else ENVIRONMENT_BLOCKED if blocked else PASS
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": PREFLIGHT_KIND,
        "ok": not required_failures,
        "status": status,
        "classification": "application" if source_failures else "environment",
        "manifest": str(_manifest_path(root, manifest_path)),
        "platform": {"os": current_os, "architecture": current_arch},
        "runnerClasses": sorted({str(check["runnerClass"]) for check in checks}),
        "checks": results,
        "environmentBlocked": [row["id"] for row in blocked],
        "sourceFailures": [row["id"] for row in source_failures],
    }


def as_ci_preflight_evidence(result: Mapping[str, Any], component_id: str = "runtime-preflight") -> dict[str, Any]:
    """Adapt rich results to the existing strict CI preflight evidence shape."""
    checks = result.get("checks") if isinstance(result.get("checks"), list) else []
    bindings = []
    for row in checks:
        if not isinstance(row, Mapping):
            continue
        bindings.append({
            "variable": str(row.get("id", "unknown")),
            "resolvedPath": str(row.get("resolvedPath", "")),
            "matched": row.get("status") == PASS,
            "detail": f"{row.get('status', SOURCE_FAILURE)}:{row.get('code', 'unknown')}",
        })
    return {
        "schemaVersion": 1,
        "kind": "ci-preflight-evidence",
        "componentId": component_id,
        "ok": bool(result.get("ok")),
        "classification": "infrastructure" if result.get("status") == ENVIRONMENT_BLOCKED else "application",
        "detail": json.dumps({"status": result.get("status"), "environmentBlocked": result.get("environmentBlocked", []), "sourceFailures": result.get("sourceFailures", [])}, sort_keys=True),
        "bindings": bindings,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--profile")
    parser.add_argument("--evidence", action="store_true", help="emit the existing ci-preflight-evidence envelope")
    args = parser.parse_args(argv)
    result = run_preflight(args.root, profile=args.profile, manifest_path=args.manifest)
    output = as_ci_preflight_evidence(result) if args.evidence else result
    print(json.dumps(output, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
