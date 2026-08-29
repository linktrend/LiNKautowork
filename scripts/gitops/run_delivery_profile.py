#!/usr/bin/env python3
"""Run a declared managed delivery profile without shell interpolation.

The runner is deliberately small enough to install into a consumer repository,
but produces a complete, identity-bound inventory instead of a wrapper-only
success signal.  Commands are always argv-only.  A failed command is recorded
and later commands are still represented in the inventory, while unsafe
workspace mutation stops execution and marks the remaining commands omitted.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

SCHEMA_VERSION = 1
INVENTORY_KIND = "ci-profile-inventory"
PROFILE_BOUNDARIES = {"focused", "fast", "full"}
IDENTITY_FIELDS = (
    "repository",
    "gitTree",
    "headCommit",
    "dependencyDigest",
    "profileDigest",
    "workflowDigest",
)
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
GOVERNANCE_PREFIXES = (
    ".github/",
    "core/managed-core/schemas/",
    "core/github/",
    "scripts/gitops/",
    "docs/contracts/",
)
MUTATION_MARKERS = {
    "apply",
    "cp",
    "delete",
    "docker",
    "git",
    "install",
    "mv",
    "rm",
    "terraform",
}


class DeliveryProfileError(ValueError):
    """A deterministic profile or evidence failure."""


def load_profile(root: Path, profile: str) -> tuple[Path, list[list[str]]]:
    candidates = [
        root / ".github" / "linktrend-delivery-mode.json",
        root / ".ide-development" / "config" / "delivery.json",
    ]
    config_path = next((path for path in candidates if path.is_file()), None)
    if config_path is None:
        raise SystemExit("delivery_profile_config_missing")
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        commands = data["profiles"][profile]["commands"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"delivery_profile_config_invalid:{config_path}:{exc}") from exc
    if not isinstance(commands, list) or not commands:
        raise SystemExit(f"delivery_profile_commands_missing:{config_path}:{profile}")
    validated: list[list[str]] = []
    for command in commands:
        if not isinstance(command, list) or not command or not all(isinstance(arg, str) and arg for arg in command):
            raise SystemExit(f"delivery_profile_command_invalid:{config_path}:{profile}")
        validated.append(command)
    return config_path, validated


def digest_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def digest_json(value: Any) -> str:
    return digest_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA40_RE.fullmatch(value))


def _valid_digest(value: Any) -> bool:
    return isinstance(value, str) and bool(DIGEST_RE.fullmatch(value))


def _normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def classify_risk(
    changed_paths: Sequence[str] = (),
    *,
    profile: str = "fast",
    commands: Sequence[Sequence[str]] = (),
) -> dict[str, Any]:
    """Classify the risk of a profile invocation from immutable declarations.

    This classifier never grants permission to skip a component.  It only
    raises the required scrutiny level and is included in the evidence inputs.
    """
    if profile not in PROFILE_BOUNDARIES:
        raise DeliveryProfileError(f"unknown_profile_boundary:{profile}")
    paths = [_normalize_path(str(path)) for path in changed_paths]
    if any(not path or path in {".", ".."} or ".." in path.split("/") for path in paths):
        return {
            "level": "critical",
            "surface": "unknown",
            "reason": "ambiguous_or_unsafe_path",
            "changedPaths": paths,
        }
    governance = [path for path in paths if any(path.startswith(prefix) for prefix in GOVERNANCE_PREFIXES)]
    application = [path for path in paths if path not in governance]
    command_words = {
        Path(str(arg)).name.lower()
        for command in commands
        if command
        for arg in command[:1]
    }
    mutation_command = sorted(command_words & MUTATION_MARKERS)
    if mutation_command:
        level = "critical"
        reason = "profile_declares_mutating_command"
    elif profile == "full" or (governance and application):
        level = "high"
        reason = "full_or_mixed_surface"
    elif governance:
        level = "high"
        reason = "governance_surface"
    elif application:
        level = "medium"
        reason = "application_surface"
    else:
        level = "low"
        reason = "no_changed_paths"
    return {
        "level": level,
        "surface": "mixed" if governance and application else ("governance" if governance else "application"),
        "reason": reason,
        "changedPaths": paths,
        "mutatingCommands": mutation_command,
    }


def _run_git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _remote_repository(root: Path) -> str:
    value = os.environ.get("GITHUB_REPOSITORY") or _run_git(root, "config", "--get", "remote.origin.url")
    value = value.removesuffix(".git")
    if value.startswith("git@github.com:"):
        return value.removeprefix("git@github.com:")
    if value.startswith("https://github.com/"):
        return value.removeprefix("https://github.com/")
    return value


def _digest_files(root: Path, patterns: Sequence[str]) -> str:
    """Digest matched working-tree files without traversing Git metadata."""

    matches: dict[str, Path] = {}
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        directory_names[:] = sorted(
            name for name in directory_names if name != ".git"
        )
        base = Path(directory)
        for name in sorted(file_names):
            path = base / name
            if path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            if any(
                path.match(pattern)
                or fnmatch.fnmatch(relative, pattern)
                or fnmatch.fnmatch(name, pattern.removeprefix("**/"))
                for pattern in patterns
            ):
                matches[relative] = path

    rows: list[dict[str, str]] = []
    for relative in sorted(matches):
        path = matches[relative]
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise DeliveryProfileError(
                f"dependency_declaration_unreadable:{relative}:{exc}"
            ) from exc
        rows.append({"path": relative, "digest": digest_bytes(raw)})
    return digest_json(rows)


def build_identity(
    root: Path,
    *,
    repository: str | None = None,
    head_commit: str | None = None,
    git_tree: str | None = None,
    dependency_digest: str | None = None,
    profile_digest: str | None = None,
    workflow_digest: str | None = None,
    config_path: Path | None = None,
) -> dict[str, Any] | None:
    """Resolve the reusable-evidence identity from explicit or local inputs."""
    head = head_commit or _run_git(root, "rev-parse", "HEAD") or os.environ.get("GITHUB_SHA")
    tree = git_tree or _run_git(root, "rev-parse", "HEAD^{tree}")
    repo = repository or _remote_repository(root)
    config_digest = digest_bytes(config_path.read_bytes()) if config_path and config_path.is_file() else ""
    identity = {
        "repository": repo,
        "gitTree": tree,
        "headCommit": head,
        "dependencyDigest": dependency_digest
        or _digest_files(
            root,
            (
                "**/Cargo.lock",
                "**/Gemfile.lock",
                "**/Pipfile.lock",
                "**/poetry.lock",
                "**/package-lock.json",
                "**/npm-shrinkwrap.json",
                "**/pnpm-lock.yaml",
                "**/yarn.lock",
                "**/uv.lock",
                "**/requirements*.txt",
            ),
        ),
        "profileDigest": profile_digest or config_digest,
        "workflowDigest": workflow_digest or _digest_files(root, (".github/workflows/*.yml", ".github/workflows/*.yaml")),
    }
    if not all(identity.values()):
        return None
    if not _valid_sha(identity["headCommit"]) or not _valid_sha(identity["gitTree"]):
        return None
    if not all(_valid_digest(identity[field]) for field in IDENTITY_FIELDS[3:]):
        return None
    return identity


def identity_digest(identity: Mapping[str, Any]) -> str:
    if set(identity) != set(IDENTITY_FIELDS):
        raise DeliveryProfileError("identity_fields_incomplete")
    if not isinstance(identity.get("repository"), str) or not identity["repository"]:
        raise DeliveryProfileError("identity_repository_invalid")
    if not _valid_sha(identity["gitTree"]) or not _valid_sha(identity["headCommit"]):
        raise DeliveryProfileError("identity_commit_invalid")
    if not all(_valid_digest(identity[field]) for field in IDENTITY_FIELDS[3:]):
        raise DeliveryProfileError("identity_digest_invalid")
    return digest_json({field: identity[field] for field in IDENTITY_FIELDS})


def can_reuse_evidence(previous: Mapping[str, Any] | None, current_identity: Mapping[str, Any] | None) -> dict[str, Any]:
    """Allow reuse only for a successful complete inventory with exact identity."""
    if not isinstance(previous, Mapping) or previous.get("kind") != INVENTORY_KIND:
        return {"reusable": False, "code": "evidence_missing_or_wrong_kind"}
    if previous.get("ok") is not True or previous.get("complete") is not True:
        return {"reusable": False, "code": "evidence_not_complete_success"}
    if previous.get("workspaceMutated") is True:
        return {"reusable": False, "code": "evidence_workspace_mutated"}
    if current_identity is None:
        return {"reusable": False, "code": "current_identity_missing"}
    try:
        current_digest = identity_digest(current_identity)
    except DeliveryProfileError as exc:
        return {"reusable": False, "code": str(exc)}
    previous_digest = previous.get("identityDigest")
    if previous_digest != current_digest:
        return {
            "reusable": False,
            "code": "evidence_identity_changed",
            "previousIdentityDigest": previous_digest,
            "currentIdentityDigest": current_digest,
        }
    return {"reusable": True, "code": "evidence_identity_match", "identityDigest": current_digest}


def classify_recovery(
    *,
    agent_stale: bool = False,
    capacity_available: bool = True,
    host_available: bool = True,
    workspace_mutated: bool = False,
    expected_identity: Mapping[str, Any] | None = None,
    actual_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a safe recovery action for deterministic failure simulations."""
    if workspace_mutated:
        return {"safe": True, "code": "workspace_mutated", "action": "discard_and_recompute", "reuse": False}
    if expected_identity is not None and actual_identity != expected_identity:
        return {"safe": True, "code": "stale_identity", "action": "invalidate_and_rerun", "reuse": False}
    if agent_stale:
        return {"safe": True, "code": "stale_agent", "action": "requeue_without_reuse", "reuse": False}
    if not host_available:
        return {"safe": True, "code": "host_unavailable", "action": "retry_infrastructure", "reuse": False}
    if not capacity_available:
        return {"safe": True, "code": "capacity_exhausted", "action": "defer_without_mutation", "reuse": False}
    return {"safe": True, "code": "healthy", "action": "continue", "reuse": True}


def _tail(value: str, limit: int = 2000) -> str:
    return value[-limit:] if value else ""


def _tracked_workspace_digest(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    # Compare tracked content, not porcelain status.  A freshly-created index
    # can be racily-clean: the first `git status` may refresh stat data and a
    # second identical status can then differ even though no file changed.
    # `git diff HEAD` is content based, includes staged and unstaged tracked
    # changes, and deliberately excludes harmless untracked interpreter caches.
    # Force Git to resolve any racily-clean index entries first.  On fast CI
    # filesystems a commit and the following profile can share a timestamp;
    # without this refresh, the first comparison can report a transient diff
    # which disappears after the first read.
    subprocess.run(
        ["git", "update-index", "-q", "--refresh"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    diff = _run_git(root, "diff", "--no-ext-diff", "--binary", "HEAD", "--")
    return digest_bytes(diff.encode("utf-8"))


def run_profile(
    root: Path,
    profile: str,
    *,
    config_path: Path | None = None,
    commands: Sequence[Sequence[str]] | None = None,
    changed_paths: Sequence[str] = (),
    identity: Mapping[str, Any] | None = None,
    executor: Callable[[Sequence[str], Path], Any] | None = None,
    clock: Callable[[], float] = time.monotonic,
    preflight: bool = False,
) -> dict[str, Any]:
    """Execute every safe declared command and return a complete inventory.

    ``preflight=True`` is an explicit startup gate.  It records an omitted
    command inventory when the manifest reports an environment block, so a
    missing tool or service can never be mistaken for a passing profile.
    """
    if profile not in PROFILE_BOUNDARIES:
        raise DeliveryProfileError(f"unknown_profile_boundary:{profile}")
    if commands is None:
        loaded_path, loaded_commands = load_profile(root, profile)
        config_path = loaded_path
        commands = loaded_commands
    if not commands:
        raise DeliveryProfileError(f"delivery_profile_commands_missing:{profile}")
    normalized = [list(command) for command in commands]
    risk = classify_risk(changed_paths, profile=profile, commands=normalized)
    resolved_identity_digest = identity_digest(identity) if identity is not None else None
    before_workspace = _tracked_workspace_digest(root)
    started = clock()
    rows: list[dict[str, Any]] = []
    failed = False
    mutated = False
    preflight_result: Mapping[str, Any] | None = None
    if preflight:
        try:
            from scripts.gitops.runtime_preflight import run_preflight
        except ModuleNotFoundError:  # pragma: no cover - installed managed runtime import path
            from runtime_preflight import run_preflight  # type: ignore
        preflight_result = run_preflight(root, profile=profile)
        if not preflight_result.get("ok"):
            blocked_ids = preflight_result.get("environmentBlocked") or preflight_result.get("sourceFailures") or ["unknown"]
            reason = "runtime_preflight:" + ",".join(str(item) for item in blocked_ids)
            rows = [
                {
                    "id": f"{profile}-{index:03d}",
                    "argv": list(command),
                    "boundary": profile,
                    "status": "omitted",
                    "reason": reason,
                }
                for index, command in enumerate(normalized, start=1)
            ]
            failed = True
    if risk["level"] == "critical":
        rows = [
            {
                "id": f"{profile}-{index:03d}",
                "argv": list(command),
                "boundary": profile,
                "status": "omitted",
                "reason": "critical_risk_requires_authorized_recovery",
            }
            for index, command in enumerate(normalized, start=1)
        ]
        failed = True
    for index, command in enumerate(normalized, start=1):
        if preflight_result is not None and not preflight_result.get("ok"):
            continue
        row: dict[str, Any] = {
            "id": f"{profile}-{index:03d}",
            "argv": command,
            "boundary": profile,
            "status": "omitted",
        }
        if risk["level"] == "critical":
            continue
        if mutated:
            row["reason"] = "workspace_mutated"
            rows.append(row)
            continue
        command_started = clock()
        try:
            if executor is None:
                result = subprocess.run(
                    command,
                    cwd=root,
                    check=False,
                    capture_output=True,
                    text=True,
                )
            else:
                result = executor(command, root)
            return_code = int(getattr(result, "returncode", 0))
            stdout = str(getattr(result, "stdout", "") or "")
            stderr = str(getattr(result, "stderr", "") or "")
        except (OSError, subprocess.SubprocessError) as exc:
            return_code = 1
            stdout = ""
            stderr = str(exc)
        elapsed = max(0, int(round((clock() - command_started) * 1000)))
        row.update(
            {
                "status": "passed" if return_code == 0 else "failed",
                "exitCode": return_code,
                "elapsedMs": elapsed,
                "stdoutTail": _tail(stdout),
                "stderrTail": _tail(stderr),
            }
        )
        if return_code != 0:
            failed = True
        after_workspace = _tracked_workspace_digest(root)
        if before_workspace is not None and after_workspace != before_workspace:
            mutated = True
            row["mutationDetected"] = True
        rows.append(row)
    inventory: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "kind": INVENTORY_KIND,
        "profile": profile,
        "boundary": profile,
        "config": str(config_path) if config_path else None,
        "risk": risk,
        "commands": rows,
        "complete": len(rows) == len(normalized),
        "ok": not failed and not mutated and not any(row["status"] == "omitted" for row in rows),
        "executedCount": sum(row["status"] != "omitted" for row in rows),
        "failedCount": sum(row["status"] == "failed" for row in rows),
        "omittedCount": sum(row["status"] == "omitted" for row in rows),
        "elapsedMs": max(0, int(round((clock() - started) * 1000))),
        "workspaceMutated": mutated,
        "identity": dict(identity) if identity is not None else None,
        "identityDigest": resolved_identity_digest,
    }
    inventory["inventoryDigest"] = digest_json(
        {key: inventory[key] for key in ("profile", "boundary", "risk", "commands", "identityDigest")}
    )
    return inventory


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", choices=tuple(sorted(PROFILE_BOUNDARIES)))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--inventory-json", type=Path)
    parser.add_argument("--reuse-evidence", type=Path)
    parser.add_argument("--changed", action="append", default=[])
    parser.add_argument("--repository")
    parser.add_argument("--head")
    parser.add_argument("--tree")
    parser.add_argument("--dependency-digest")
    parser.add_argument("--profile-digest")
    parser.add_argument("--workflow-digest")
    parser.add_argument("--preflight", action="store_true", help="run the declared runtime preflight before profile commands")
    args = parser.parse_args()
    root = args.root.resolve()
    config_path, commands = load_profile(root, args.profile)
    identity = build_identity(
        root,
        repository=args.repository,
        head_commit=args.head,
        git_tree=args.tree,
        dependency_digest=args.dependency_digest,
        profile_digest=args.profile_digest,
        workflow_digest=args.workflow_digest,
        config_path=config_path,
    )
    if args.reuse_evidence:
        try:
            previous = json.loads(args.reuse_evidence.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"delivery_profile_reuse_invalid:{exc}") from exc
        reuse = can_reuse_evidence(previous, identity)
        if reuse["reusable"]:
            inventory = dict(previous)
            inventory["reused"] = True
            inventory["reuse"] = reuse
            print(json.dumps(inventory, sort_keys=True))
            return 0
    inventory = run_profile(
        root,
        args.profile,
        config_path=config_path,
        commands=commands,
        changed_paths=args.changed,
        identity=identity,
        preflight=args.preflight,
    )
    if args.reuse_evidence:
        inventory["reuse"] = can_reuse_evidence(
            json.loads(args.reuse_evidence.read_text(encoding="utf-8")),
            identity,
        )
    if args.inventory_json:
        write_json(args.inventory_json, inventory)
    print(json.dumps(inventory, sort_keys=True))
    return 0 if inventory["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
