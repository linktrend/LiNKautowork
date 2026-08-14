"""Fail-closed loading and normalization for hosted delivery configuration.

The installed configuration is the frozen W1-P1 shape.  The previous
streamlined-delivery shapes are accepted only as read-time migration inputs;
they are never emitted by :class:`DeliveryConfig`.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

CONFIG_REL = Path(".github/linktrend-delivery-mode.json")
MODE_ISSUE_PR = "issue-pr"
MODE_PHASE_INTEGRATION = "phase-integration"
DEFAULT_DELIVERY_MODE = MODE_PHASE_INTEGRATION
DEFAULT_PHASE_PREFIX = "phase/"
HOSTED_PROVIDER = "github-hosted"
HOSTED_RUNNER = "ubuntu-24.04-arm"
MAX_TIMEOUT_MINUTES = 60
RECEIPT_IDENTITY_FIELDS = (
    "repository",
    "gitTree",
    "dependencyDigest",
    "profileDigest",
    "workflowDigest",
)


class ConfigError(ValueError):
    """Structured fail-closed configuration error with plain remediation."""

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
class ComputeConfig:
    provider: str = HOSTED_PROVIDER
    runner: str = HOSTED_RUNNER
    checkpoint_ci: bool = False
    cancel_obsolete: bool = True
    max_infrastructure_attempts: int = 2
    max_sealed_candidates: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "runner": self.runner,
            "checkpointCI": self.checkpoint_ci,
            "cancelObsolete": self.cancel_obsolete,
            "maxInfrastructureAttempts": self.max_infrastructure_attempts,
            "maxSealedCandidates": self.max_sealed_candidates,
        }


@dataclass(frozen=True)
class ResourceLimits:
    """Read-only compatibility value for pre-hosted coordinator callers."""

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
class TestProfile:
    """One repository-owned command profile.

    Commands are tuples only after parsing so callers cannot mutate the
    normalized configuration.  The original array ordering and string values
    are retained exactly in ``to_dict``.
    """

    commands: tuple[tuple[str, ...], ...]
    timeout_minutes: int | None = None
    required: bool | None = None
    # Retained as a read-only compatibility value for older callers.  It is
    # never accepted or emitted in the hosted profile.
    image: str = "alpine:3.20"

    @property
    def timeout_seconds(self) -> int:
        return (self.timeout_minutes or 0) * 60

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "commands": [list(command) for command in self.commands],
        }
        if self.timeout_minutes is not None:
            result["timeoutMinutes"] = self.timeout_minutes
        if self.required is not None:
            result["required"] = self.required
        return result


@dataclass(frozen=True)
class PromotionConfig:
    reuse_exact_receipt: bool = True
    identity: tuple[str, ...] = RECEIPT_IDENTITY_FIELDS

    def to_dict(self) -> dict[str, Any]:
        return {
            "reuseExactReceipt": self.reuse_exact_receipt,
            "identity": list(self.identity),
        }


@dataclass(frozen=True)
class ReviewConfig:
    bugbot: str = "final-candidate-only"

    def to_dict(self) -> dict[str, Any]:
        return {"bugbot": self.bugbot}


@dataclass(frozen=True)
class DeliveryConfig:
    schema_version: int = 2
    mode: str = DEFAULT_DELIVERY_MODE
    compute: ComputeConfig = ComputeConfig()
    profiles: Mapping[str, TestProfile] = ()
    promotion: PromotionConfig = PromotionConfig()
    review: ReviewConfig = ReviewConfig()

    @property
    def is_phase_integration(self) -> bool:
        return self.mode == MODE_PHASE_INTEGRATION

    # These aliases keep existing phase/mode helpers read-compatible while
    # their serialized source is now the hosted frozen interface.
    @property
    def delivery_mode(self) -> str:
        return self.mode

    @property
    def phase_branch_prefix(self) -> str:
        return DEFAULT_PHASE_PREFIX

    @property
    def test_profiles(self) -> Mapping[str, TestProfile]:
        return self.profiles

    @property
    def orchestration_mode(self) -> str:
        return "github-actions"

    @property
    def fast_target_seconds(self) -> int:
        return (self.profiles["fast"].timeout_minutes or 0) * 60

    @property
    def max_attempts_per_candidate(self) -> int:
        return self.compute.max_infrastructure_attempts

    @property
    def max_sealed_candidate_revisions(self) -> int:
        return self.compute.max_sealed_candidates

    @property
    def max_fast_jobs(self) -> int:
        return 2

    @property
    def max_heavy_jobs(self) -> int:
        return 1

    @property
    def staging_promotion(self) -> str:
        return "automatic"

    @property
    def main_promotion(self) -> str:
        return "principal-approval"

    @property
    def dependency_files(self) -> tuple[str, ...]:
        return ()

    @property
    def resource_limits(self) -> None:
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": 2,
            "mode": self.mode,
            "compute": self.compute.to_dict(),
            "profiles": {
                name: self.profiles[name].to_dict()
                for name in ("fast", "full", "release")
            },
            "promotion": self.promotion.to_dict(),
            "review": self.review.to_dict(),
        }

    @property
    def normalized(self) -> dict[str, Any]:
        """Return the canonical JSON-compatible configuration."""

        return self.to_dict()

    @property
    def digest(self) -> str:
        """Return the stable SHA-256 digest of canonical normalized JSON."""

        encoded = json.dumps(
            self.normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


def config_digest(config: DeliveryConfig) -> str:
    """Return ``config``'s deterministic normalized digest."""

    return config.digest


def _fail(code: str, detail: str, path: str = "") -> None:
    raise ConfigError(code, detail, path=path)


def _object(value: Any, *, path: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("invalid_object", "set this value to a JSON object with the documented fields", path)
    if set(value) != fields:
        missing = sorted(fields - set(value))
        unknown = sorted(set(value) - fields)
        detail = "provide the required fields"
        if missing:
            detail += f"; missing: {', '.join(missing)}"
        if unknown:
            detail += f"; remove unknown: {', '.join(unknown)}"
        _fail("unknown_or_missing_field", detail, path)
    return value


def _commands(value: Any, *, path: str) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list):
        _fail("invalid_commands", "commands must be an array of command arrays", path)
    parsed: list[tuple[str, ...]] = []
    for index, command in enumerate(value):
        command_path = f"{path}[{index}]"
        if not isinstance(command, list) or not command:
            _fail("invalid_command", "each command must be a non-empty array of strings", command_path)
        if any(not isinstance(item, str) or not item.strip() for item in command):
            _fail("invalid_command", "each command item must be a non-empty string", command_path)
        parsed.append(tuple(command))
    return tuple(parsed)


def _legacy_commands(value: Any, *, path: str) -> list[list[str]]:
    """Convert legacy string/array commands without changing their values."""

    if not isinstance(value, list):
        _fail("invalid_commands", "commands must be an array", path)
    converted: list[list[str]] = []
    for index, command in enumerate(value):
        command_path = f"{path}[{index}]"
        if isinstance(command, str):
            if not command.strip():
                _fail("invalid_command", "each command must be a non-empty string", command_path)
            converted.append([command])
            continue
        if not isinstance(command, list) or not command:
            _fail("invalid_command", "each command must be a non-empty array of strings", command_path)
        if any(not isinstance(item, str) or not item.strip() for item in command):
            _fail("invalid_command", "each command item must be a non-empty string", command_path)
        converted.append(list(command))
    return converted


def _legacy_timeout(value: Any, *, path: str) -> int:
    """Convert a legacy seconds timeout to a bounded hosted minutes value."""

    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 3600:
        _fail("invalid_timeout", "legacy timeoutSeconds must be a positive integer up to 3600", path)
    return math.ceil(value / 60)


def _legacy_phase_prefix(value: Any) -> str:
    """Validate the legacy prefix even though it is not emitted after migration."""

    if value is None:
        return DEFAULT_PHASE_PREFIX
    if not isinstance(value, str) or not re.fullmatch(r"^[A-Za-z0-9._-]+/?$", value):
        _fail(
            "invalid_phase_prefix",
            "phaseBranchPrefix must be a safe relative prefix; use letters, numbers, dots, underscores, or hyphens",
            "phaseBranchPrefix",
        )
    return value if value.endswith("/") else value + "/"


def _profile(value: Any, *, name: str) -> TestProfile:
    required_fields = {"commands", "timeoutMinutes"} if name == "fast" else {"commands"}
    if name == "full":
        required_fields.add("required")
    if not isinstance(value, dict):
        _fail("invalid_object", "set this value to a JSON object with the documented fields", f"profiles.{name}")
    unknown = set(value) - (required_fields | {"timeoutMinutes"})
    missing = required_fields - set(value)
    if unknown or missing:
        detail = "provide the required fields"
        if missing:
            detail += f"; missing: {', '.join(sorted(missing))}"
        if unknown:
            detail += f"; remove unknown: {', '.join(sorted(unknown))}"
        _fail("unknown_or_missing_field", detail, f"profiles.{name}")
    raw = value
    timeout = raw.get("timeoutMinutes")
    if timeout is not None and (
        isinstance(timeout, bool)
        or not isinstance(timeout, int)
        or not 1 <= timeout <= MAX_TIMEOUT_MINUTES
    ):
        _fail(
            "invalid_timeout",
            f"timeoutMinutes must be a positive integer from 1 through {MAX_TIMEOUT_MINUTES}",
            f"profiles.{name}.timeoutMinutes",
        )
    required = raw.get("required")
    if name == "full" and not isinstance(required, bool):
        _fail(
            "invalid_profile",
            "full.required must be a boolean; set it explicitly so full-suite policy is not implicit",
            "profiles.full.required",
        )
    return TestProfile(
        commands=_commands(raw["commands"], path=f"profiles.{name}.commands"),
        timeout_minutes=timeout,
        required=required,
    )


def _compute(value: Any, *, path: str = "compute") -> ComputeConfig:
    fields = {
        "provider", "runner", "checkpointCI", "cancelObsolete",
        "maxInfrastructureAttempts", "maxSealedCandidates",
    }
    raw = _object(value, path=path, fields=fields)
    if raw["provider"] != HOSTED_PROVIDER:
        _fail(
            "invalid_provider",
            "provider must be github-hosted; select the managed hosted compute profile",
            f"{path}.provider",
        )
    if raw["runner"] != HOSTED_RUNNER:
        _fail(
            "invalid_runner",
            "runner must be the hosted label ubuntu-24.04-arm; use the supported hosted profile",
            f"{path}.runner",
        )
    if raw["checkpointCI"] is not False:
        _fail(
            "invalid_checkpoint_policy",
            "checkpointCI must be false; checkpoint pushes do not run CI",
            f"{path}.checkpointCI",
        )
    if raw["cancelObsolete"] is not True:
        _fail(
            "invalid_cancellation_policy",
            "cancelObsolete must be true so obsolete work is cancelled",
            f"{path}.cancelObsolete",
        )
    for key in ("maxInfrastructureAttempts", "maxSealedCandidates"):
        value = raw[key]
        if isinstance(value, bool) or not isinstance(value, int) or value != 2:
            _fail(
                "invalid_limits",
                f"{key} must be the bounded positive integer 2",
                f"{path}.{key}",
            )
    return ComputeConfig(
        provider=raw["provider"],
        runner=raw["runner"],
        checkpoint_ci=raw["checkpointCI"],
        cancel_obsolete=raw["cancelObsolete"],
        max_infrastructure_attempts=raw["maxInfrastructureAttempts"],
        max_sealed_candidates=raw["maxSealedCandidates"],
    )


def _promotion(value: Any) -> PromotionConfig:
    raw = _object(
        value,
        path="promotion",
        fields={"reuseExactReceipt", "identity"},
    )
    if raw["reuseExactReceipt"] is not True:
        _fail(
            "invalid_receipt_policy",
            "reuseExactReceipt must be true so exact full-suite receipts can be reused",
            "promotion.reuseExactReceipt",
        )
    identity = raw["identity"]
    if (
        not isinstance(identity, list)
        or any(not isinstance(item, str) or not item.strip() for item in identity)
        or set(identity) != set(RECEIPT_IDENTITY_FIELDS)
        or len(identity) != len(RECEIPT_IDENTITY_FIELDS)
    ):
        _fail(
            "incomplete_receipt_identity",
            "identity must contain repository, gitTree, dependencyDigest, profileDigest, and workflowDigest",
            "promotion.identity",
        )
    return PromotionConfig(identity=RECEIPT_IDENTITY_FIELDS)


def _review(value: Any) -> ReviewConfig:
    raw = _object(value, path="review", fields={"bugbot"})
    if raw["bugbot"] != "final-candidate-only":
        _fail(
            "invalid_review_policy",
            "bugbot must be final-candidate-only",
            "review.bugbot",
        )
    return ReviewConfig()


def _new_config(payload: Mapping[str, Any]) -> DeliveryConfig:
    expected = {"schemaVersion", "mode", "compute", "profiles", "promotion", "review"}
    _object(dict(payload), path="configuration", fields=expected)
    if payload["schemaVersion"] != 2:
        _fail("unsupported_schema", "schemaVersion must be 2 for the hosted profile", "schemaVersion")
    if payload["mode"] not in {MODE_ISSUE_PR, MODE_PHASE_INTEGRATION}:
        _fail("invalid_delivery_mode", "mode must be issue-pr or phase-integration", "mode")
    raw_profiles = payload["profiles"]
    if not isinstance(raw_profiles, dict) or set(raw_profiles) != {"fast", "full", "release"}:
        _fail("unknown_or_missing_field", "profiles must contain fast, full, and release", "profiles")
    profiles = {name: _profile(raw_profiles[name], name=name) for name in ("fast", "full", "release")}
    return DeliveryConfig(
        mode=payload["mode"],
        compute=_compute(payload["compute"]),
        profiles=profiles,
        promotion=_promotion(payload["promotion"]),
        review=_review(payload["review"]),
    )


def _migrate_legacy(payload: Mapping[str, Any]) -> DeliveryConfig:
    """Convert v1/current streamlined config to the hosted frozen shape."""

    version = payload.get("schemaVersion")
    if version == 1:
        allowed = {"schemaVersion", "deliveryMode", "phaseBranchPrefix"}
        if set(payload) - allowed:
            _fail("unknown_field", "remove unknown legacy configuration properties", "configuration")
        _legacy_phase_prefix(payload.get("phaseBranchPrefix"))
        mode = payload.get("deliveryMode", MODE_PHASE_INTEGRATION)
        if mode not in {MODE_ISSUE_PR, MODE_PHASE_INTEGRATION}:
            _fail("invalid_delivery_mode", "legacy deliveryMode must be issue-pr or phase-integration", "deliveryMode")
        commands = {"fast": [], "full": [], "release": []}
        timeouts: dict[str, int] = {}
        required = False
    else:
        legacy_fields = {
            "schemaVersion", "deliveryMode", "phaseBranchPrefix", "orchestrationMode",
            "fastTargetSeconds", "maxAttemptsPerCandidate", "maxSealedCandidateRevisions",
            "maxFastJobs", "maxHeavyJobs", "stagingPromotion", "mainPromotion",
            "testProfiles", "dependencyFiles", "resourceLimits",
        }
        if set(payload) != legacy_fields:
            _fail(
                "unknown_or_missing_field",
                "legacy streamlined configuration must contain its complete documented fields",
                "configuration",
            )
        _legacy_phase_prefix(payload.get("phaseBranchPrefix"))
        mode = payload["deliveryMode"]
        if mode not in {MODE_ISSUE_PR, MODE_PHASE_INTEGRATION}:
            _fail("invalid_delivery_mode", "legacy deliveryMode must be issue-pr or phase-integration", "deliveryMode")
        raw_profiles = payload["testProfiles"]
        if not isinstance(raw_profiles, dict) or set(raw_profiles) != {"fast", "full", "release"}:
            _fail("unknown_or_missing_field", "legacy testProfiles must contain fast, full, and release", "testProfiles")
        commands: dict[str, list[list[str]]] = {}
        timeouts: dict[str, int] = {}
        for name in ("fast", "full", "release"):
            profile = raw_profiles[name]
            if not isinstance(profile, dict):
                _fail("invalid_profile", "legacy profile must be an object", f"testProfiles.{name}")
            commands[name] = _legacy_commands(profile.get("commands"), path=f"testProfiles.{name}.commands")
            timeouts[name] = _legacy_timeout(profile.get("timeoutSeconds"), path=f"testProfiles.{name}.timeoutSeconds")
        fast_target_seconds = payload["fastTargetSeconds"]
        if (
            isinstance(fast_target_seconds, bool)
            or not isinstance(fast_target_seconds, int)
            or not 1 <= fast_target_seconds <= 300
        ):
            _fail(
                "invalid_timeout",
                "legacy fastTargetSeconds must be a positive integer up to 300",
                "fastTargetSeconds",
            )
        fast_target = _legacy_timeout(fast_target_seconds, path="fastTargetSeconds")
        if timeouts["fast"] > fast_target:
            _fail("invalid_timeout", "legacy fast profile timeout exceeds fastTargetSeconds", "testProfiles.fast.timeoutSeconds")
        required = raw_profiles["full"].get("required")
        if not isinstance(required, bool):
            _fail("invalid_profile", "legacy full.required must be boolean", "testProfiles.full.required")
    migrated = {
        "schemaVersion": 2,
        "mode": mode,
        "compute": ComputeConfig().to_dict(),
        "profiles": {
            "fast": {"commands": commands["fast"], "timeoutMinutes": timeouts.get("fast", 5)},
            "full": {"commands": commands["full"], "required": required if version != 1 else False},
            "release": {"commands": commands["release"]},
        },
        "promotion": PromotionConfig().to_dict(),
        "review": ReviewConfig().to_dict(),
    }
    return _new_config(migrated)


def _default_payload() -> dict[str, Any]:
    return {
        "schemaVersion": 2,
        "mode": DEFAULT_DELIVERY_MODE,
        "compute": ComputeConfig().to_dict(),
        "profiles": {
            "fast": {"commands": [], "timeoutMinutes": 5},
            "full": {"commands": [], "required": True},
            "release": {"commands": []},
        },
        "promotion": PromotionConfig().to_dict(),
        "review": ReviewConfig().to_dict(),
    }


def _load_payload(source: Any) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)
    if source is None:
        return _default_payload()
    path = Path(source)
    config_path = path / CONFIG_REL if path.is_dir() else path
    if config_path.is_dir() or not config_path.exists():
        return _default_payload()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("config_unreadable", str(exc), str(config_path))
    if not isinstance(payload, dict):
        _fail("config_not_object", "configuration must be a JSON object", str(config_path))
    return payload


def load_delivery_config(
    repo_root_or_payload: Any = None,
    *,
    env: Mapping[str, str] | None = None,
) -> DeliveryConfig:
    """Load the hosted profile, migrating legacy input in memory only."""

    del env  # Environment selection is intentionally not a post-migration profile switch.
    payload = _load_payload(repo_root_or_payload)
    if payload.get("mode") is not None:
        return _new_config(payload)
    if payload.get("schemaVersion") in {1, 2} and "deliveryMode" in payload:
        return _migrate_legacy(payload)
    _fail(
        "unsupported_schema",
        "configuration must use the hosted schemaVersion 2 shape or be a complete legacy migration input",
        "configuration",
    )
