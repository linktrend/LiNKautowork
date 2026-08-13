"""Strict loading and normalization for delivery runtime configuration.

The loader accepts a repository root, a JSON payload, or no source.  A v1
payload remains intentionally small; v2 is a complete protected policy and is
normalized into immutable Python values before any later packet can consume it.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

CONFIG_REL = Path(".github/linktrend-delivery-mode.json")
MODE_ISSUE_PR = "issue-pr"
MODE_PHASE_INTEGRATION = "phase-integration"
DEFAULT_DELIVERY_MODE = MODE_ISSUE_PR
DEFAULT_PHASE_PREFIX = "phase/"
_SHA_SAFE_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_SHELL_META = frozenset(";&|`$<>\n\r")


class ConfigError(ValueError):
    """Structured fail-closed configuration error."""

    def __init__(self, code: str, detail: str, *, path: str = "") -> None:
        self.code = code
        self.detail = detail
        self.path = path
        super().__init__(f"{code}: {detail}" + (f" ({path})" if path else ""))

    def to_dict(self) -> dict[str, str]:
        result = {"code": self.code, "detail": self.detail}
        if self.path:
            result["path"] = self.path
        return result


@dataclass(frozen=True)
class TestProfile:
    commands: tuple[tuple[str, ...], ...]
    timeout_seconds: int
    required: bool | None = None
    image: str = "alpine:3.20"

    def to_dict(self) -> dict[str, Any]:
        result = {
            "commands": [list(command) if len(command) > 1 else command[0] for command in self.commands],
            "timeoutSeconds": self.timeout_seconds,
        }
        if self.required is not None:
            result["required"] = self.required
        if self.image != "alpine:3.20":
            result["image"] = self.image
        return result


@dataclass(frozen=True)
class ResourceLimits:
    fast_cpus: float
    fast_memory_mib: int
    heavy_cpus: float
    heavy_memory_mib: int
    pids_limit: int
    pause_cpu_percent: int
    pause_memory_percent: int
    minimum_free_disk_gib: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "fastCpus": self.fast_cpus,
            "fastMemoryMiB": self.fast_memory_mib,
            "heavyCpus": self.heavy_cpus,
            "heavyMemoryMiB": self.heavy_memory_mib,
            "pidsLimit": self.pids_limit,
            "pauseCpuPercent": self.pause_cpu_percent,
            "pauseMemoryPercent": self.pause_memory_percent,
            "minimumFreeDiskGiB": self.minimum_free_disk_gib,
        }


@dataclass(frozen=True)
class DeliveryConfig:
    schema_version: int = 1
    delivery_mode: str = DEFAULT_DELIVERY_MODE
    phase_branch_prefix: str = DEFAULT_PHASE_PREFIX
    orchestration_mode: str = "github-actions"
    fast_target_seconds: int = 300
    max_attempts_per_candidate: int = 2
    max_sealed_candidate_revisions: int = 2
    max_fast_jobs: int = 2
    max_heavy_jobs: int = 1
    staging_promotion: str = "automatic"
    main_promotion: str = "principal-approval"
    test_profiles: Mapping[str, TestProfile] = ()
    dependency_files: tuple[str, ...] = ()
    resource_limits: ResourceLimits | None = None

    @property
    def is_phase_integration(self) -> bool:
        return self.delivery_mode == MODE_PHASE_INTEGRATION

    def to_dict(self) -> dict[str, Any]:
        if self.schema_version == 1:
            result: dict[str, Any] = {
                "schemaVersion": 1,
                "deliveryMode": self.delivery_mode,
            }
            if self.phase_branch_prefix != DEFAULT_PHASE_PREFIX:
                result["phaseBranchPrefix"] = self.phase_branch_prefix
            return result
        profiles = self.test_profiles
        return {
            "schemaVersion": 2,
            "deliveryMode": self.delivery_mode,
            "phaseBranchPrefix": self.phase_branch_prefix,
            "orchestrationMode": self.orchestration_mode,
            "fastTargetSeconds": self.fast_target_seconds,
            "maxAttemptsPerCandidate": self.max_attempts_per_candidate,
            "maxSealedCandidateRevisions": self.max_sealed_candidate_revisions,
            "maxFastJobs": self.max_fast_jobs,
            "maxHeavyJobs": self.max_heavy_jobs,
            "stagingPromotion": self.staging_promotion,
            "mainPromotion": self.main_promotion,
            "testProfiles": {name: profiles[name].to_dict() for name in ("fast", "full", "release")},
            "dependencyFiles": list(self.dependency_files),
            "resourceLimits": self.resource_limits.to_dict() if self.resource_limits else None,
        }


_V1_KEYS = frozenset({"schemaVersion", "deliveryMode", "phaseBranchPrefix"})
_V2_KEYS = frozenset(
    {
        "schemaVersion", "deliveryMode", "phaseBranchPrefix", "orchestrationMode",
        "fastTargetSeconds", "maxAttemptsPerCandidate", "maxSealedCandidateRevisions",
        "maxFastJobs", "maxHeavyJobs", "stagingPromotion", "mainPromotion",
        "testProfiles", "dependencyFiles", "resourceLimits",
    }
)


def _fail(code: str, detail: str, path: str = "") -> None:
    raise ConfigError(code, detail, path=path)


def _relative_path(value: Any, *, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("invalid_path", "path must be a non-empty string", path)
    value = value.strip()
    if "\x00" in value or "\\" in value or value.startswith(("/", "~")) or _SHA_SAFE_DRIVE.match(value):
        _fail("unsafe_path", "absolute, home, drive, or backslash paths are not allowed", path)
    normalized = PurePosixPath(value)
    if normalized.is_absolute() or str(normalized) in {"", "."} or str(normalized).startswith("../") or str(normalized) == "..":
        _fail("path_escape", "path must remain inside the repository", path)
    return str(normalized)


def _command(value: Any, *, path: str) -> tuple[str, ...]:
    if isinstance(value, str):
        return (_relative_path(value, path=path),)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        _fail("invalid_command", "command must be an executable path or non-empty argument array", path)
    if any(any(char in item for char in _SHELL_META) for item in value):
        _fail("unsafe_command", "shell metacharacters are not allowed", path)
    executable = _relative_path(value[0], path=f"{path}[0]")
    for index, argument in enumerate(value[1:], start=1):
        if argument.startswith(("/", "~")) or _SHA_SAFE_DRIVE.match(argument) or "\\" in argument:
            _fail("unsafe_command", "command arguments may not contain host paths", f"{path}[{index}]")
    return (executable, *value[1:])


def _profile(value: Any, *, path: str, full: bool = False) -> TestProfile:
    expected = {"commands", "timeoutSeconds", "required"} if full else {"commands", "timeoutSeconds"}
    if not isinstance(value, dict) or not expected.issubset(value) or set(value) - (expected | {"image"}):
        _fail("unknown_or_missing_field", "test profile must contain only commands and timeoutSeconds", path)
    commands = value["commands"]
    if not isinstance(commands, list):
        _fail("invalid_commands", "commands must be an array", f"{path}.commands")
    timeout = value["timeoutSeconds"]
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 3600:
        _fail("invalid_timeout", "timeoutSeconds must be an integer from 1 through 3600", f"{path}.timeoutSeconds")
    required = value.get("required")
    if full and not isinstance(required, bool):
        _fail("invalid_profile", "full.required must be boolean", f"{path}.required")
    image = value.get("image", "alpine:3.20")
    if not isinstance(image, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9./_:@+-]{0,254}", image):
        _fail("invalid_image", "image must be one safe container reference", f"{path}.image")
    return TestProfile(tuple(_command(item, path=f"{path}.commands[{i}]") for i, item in enumerate(commands)), timeout, required, image)


def _resource_limits(value: Any) -> ResourceLimits:
    if not isinstance(value, dict):
        _fail("invalid_limits", "resourceLimits must be an object", "resourceLimits")
    required = {
        "fastCpus", "fastMemoryMiB", "heavyCpus", "heavyMemoryMiB", "pidsLimit",
        "pauseCpuPercent", "pauseMemoryPercent", "minimumFreeDiskGiB",
    }
    if set(value) != required:
        _fail("unknown_or_missing_field", "resourceLimits has unknown or missing fields", "resourceLimits")
    integer_fields = {"fastMemoryMiB", "heavyMemoryMiB", "pidsLimit", "pauseCpuPercent", "pauseMemoryPercent"}
    for key in integer_fields:
        if isinstance(value[key], bool) or not isinstance(value[key], int):
            _fail("invalid_limits", "limit must be an integer", f"resourceLimits.{key}")
    if value["fastMemoryMiB"] < 128 or value["heavyMemoryMiB"] < 128 or value["pidsLimit"] < 64:
        _fail("invalid_limits", "memory and pid limits are below safe minimums", "resourceLimits")
    if not 1 <= value["pauseCpuPercent"] <= 100 or not 1 <= value["pauseMemoryPercent"] <= 100:
        _fail("invalid_limits", "pause percentages must be from 1 through 100", "resourceLimits")
    for key in ("fastCpus", "heavyCpus", "minimumFreeDiskGiB"):
        if isinstance(value[key], bool) or not isinstance(value[key], (int, float)) or value[key] <= 0:
            _fail("invalid_limits", "numeric resource limit must be positive", f"resourceLimits.{key}")
    return ResourceLimits(
        float(value["fastCpus"]), value["fastMemoryMiB"], float(value["heavyCpus"]),
        value["heavyMemoryMiB"], value["pidsLimit"], value["pauseCpuPercent"],
        value["pauseMemoryPercent"], float(value["minimumFreeDiskGiB"]),
    )


def _load_payload(source: Any, environ: Mapping[str, str]) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)
    if source is None:
        return {"schemaVersion": 1, "deliveryMode": environ.get("LINKTREND_DELIVERY_MODE") or MODE_ISSUE_PR}
    path = Path(source)
    config_path = path / CONFIG_REL if path.is_dir() else path
    if config_path.is_dir() or not config_path.exists():
        return {"schemaVersion": 1, "deliveryMode": environ.get("LINKTREND_DELIVERY_MODE") or MODE_ISSUE_PR}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("config_unreadable", str(exc), str(config_path))
    if not isinstance(payload, dict):
        _fail("config_not_object", "configuration must be a JSON object", str(config_path))
    return payload


def load_delivery_config(repo_root_or_payload: Any = None, *, env: Mapping[str, str] | None = None) -> DeliveryConfig:
    """Load and normalize a v1 or complete v2 delivery configuration."""
    environ = env if env is not None else os.environ
    payload = _load_payload(repo_root_or_payload, environ)
    version = payload.get("schemaVersion")
    if version == 1:
        if not _V1_KEYS.issuperset(payload):
            _fail("unknown_field", "unknown v1 configuration property", next(iter(set(payload) - _V1_KEYS)))
        mode = payload.get("deliveryMode", MODE_ISSUE_PR)
        if mode not in {MODE_ISSUE_PR, MODE_PHASE_INTEGRATION}:
            _fail("invalid_delivery_mode", "deliveryMode is not supported", "deliveryMode")
        prefix = payload.get("phaseBranchPrefix", DEFAULT_PHASE_PREFIX)
        if not isinstance(prefix, str) or not re.fullmatch(r"^[A-Za-z0-9._-]+/?$", prefix):
            _fail("invalid_phase_prefix", "phaseBranchPrefix must be a safe relative prefix", "phaseBranchPrefix")
        if not prefix.endswith("/"):
            prefix += "/"
        if (environ.get("LINKTREND_DELIVERY_MODE") or "").strip() in {MODE_ISSUE_PR, MODE_PHASE_INTEGRATION}:
            mode = environ["LINKTREND_DELIVERY_MODE"].strip()
        return DeliveryConfig(delivery_mode=mode, phase_branch_prefix=prefix)
    if version != 2:
        _fail("unsupported_schema", "schemaVersion must be 1 or 2", "schemaVersion")
    if set(payload) != _V2_KEYS:
        _fail("unknown_or_missing_field", "v2 configuration must contain exactly the frozen fields", "configuration")
    mode = payload["deliveryMode"]
    prefix = payload["phaseBranchPrefix"]
    if mode not in {MODE_ISSUE_PR, MODE_PHASE_INTEGRATION}:
        _fail("invalid_delivery_mode", "deliveryMode is not supported", "deliveryMode")
    if not isinstance(prefix, str) or not re.fullmatch(r"^[A-Za-z0-9._-]+/$", prefix):
        _fail("invalid_phase_prefix", "phaseBranchPrefix must be a safe relative prefix", "phaseBranchPrefix")
    if payload["orchestrationMode"] not in {"local-coordinator", "github-actions"}:
        _fail("invalid_orchestration_mode", "unsupported orchestration mode", "orchestrationMode")
    exact_ints = {
        "fastTargetSeconds": (1, 300), "maxAttemptsPerCandidate": (2, 2),
        "maxSealedCandidateRevisions": (2, 2), "maxFastJobs": (1, 2), "maxHeavyJobs": (1, 1),
    }
    for key, (low, high) in exact_ints.items():
        value = payload[key]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            _fail("invalid_limits", f"{key} must be an integer from {low} through {high}", key)
    if payload["stagingPromotion"] not in {"automatic", "principal-approval"} or payload["mainPromotion"] not in {"automatic", "principal-approval"}:
        _fail("invalid_promotion_mode", "promotion mode is unsupported", "promotion")
    raw_profiles = payload["testProfiles"]
    if not isinstance(raw_profiles, dict) or set(raw_profiles) != {"fast", "full", "release"}:
        _fail("unknown_or_missing_field", "testProfiles must contain fast, full, and release", "testProfiles")
    profiles = {
        "fast": _profile(raw_profiles["fast"], path="testProfiles.fast"),
        "full": _profile(raw_profiles["full"], path="testProfiles.full", full=True),
        "release": _profile(raw_profiles["release"], path="testProfiles.release"),
    }
    if profiles["fast"].timeout_seconds > payload["fastTargetSeconds"]:
        _fail("invalid_timeout", "fast profile timeout exceeds fastTargetSeconds", "testProfiles.fast.timeoutSeconds")
    dependencies = payload["dependencyFiles"]
    if not isinstance(dependencies, list):
        _fail("invalid_dependencies", "dependencyFiles must be an array", "dependencyFiles")
    normalized_dependencies = tuple(sorted({_relative_path(item, path=f"dependencyFiles[{i}]") for i, item in enumerate(dependencies)}))
    if (environ.get("LINKTREND_DELIVERY_MODE") or "").strip() in {MODE_ISSUE_PR, MODE_PHASE_INTEGRATION}:
        mode = environ["LINKTREND_DELIVERY_MODE"].strip()
    return DeliveryConfig(
        schema_version=2, delivery_mode=mode, phase_branch_prefix=prefix,
        orchestration_mode=payload["orchestrationMode"], fast_target_seconds=payload["fastTargetSeconds"],
        max_attempts_per_candidate=payload["maxAttemptsPerCandidate"], max_sealed_candidate_revisions=payload["maxSealedCandidateRevisions"],
        max_fast_jobs=payload["maxFastJobs"], max_heavy_jobs=payload["maxHeavyJobs"],
        staging_promotion=payload["stagingPromotion"], main_promotion=payload["mainPromotion"],
        test_profiles=profiles, dependency_files=normalized_dependencies,
        resource_limits=_resource_limits(payload["resourceLimits"]),
    )
