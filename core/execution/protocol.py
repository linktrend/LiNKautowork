"""Coding Execution Protocol 1.0.1 validation and runtime discovery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

PROTOCOL_ID = "coding-execution-protocol"
PROTOCOL_VERSION = "1.0.1"
AMENDMENT_ID = "V25_BOOTSTRAP_LEAN"
PORTFOLIO_CONTROL_LOOP_PROTOCOL = "portfolio-control-loop"
PORTFOLIO_CONTROL_LOOP_VERSION = "1.0"
PORTFOLIO_LANE_STATES = frozenset(
    {
        "PREPARED",
        "RUNNING",
        "WAITING_DEPENDENCY",
        "TERMINAL_ACCEPT",
        "TERMINAL_REJECT",
        "INTEGRATING",
        "COMPLETE",
        "BLOCKED",
    }
)
CANONICAL_PUBLISHER = None
WAIVED_LEGACY_GATE = "WAIVED_LEGACY_GATE"
LEGACY_PUBLISHERS = frozenset(
    {
        "linktrend-review-ready-publisher",
        "mark-review-ready.sh-as-publisher",
        "review-ready.json",
        "user-pat-publisher",
    }
)
ISSUE_CHECKPOINT_EVIDENCE = (
    "exact_pushed_commit_tree",
    "scoped_diff",
    "focused_tests",
    "independent_narrow_review",
    "manifest_evidence",
)
ADMIN_RECOVERY_OPERATIONS = frozenset(
    {"protection_snapshot", "restore", "readback"}
)
_SHA40 = frozenset("0123456789abcdef")

PROTOCOL_DOCUMENT_RELATIVE_PATH = "core/execution/CODING-EXECUTION-PROTOCOL.md"
CONTROL_CONTRACT_RELATIVE_PATH = "core/contracts/EXECUTION-CONTROL-CONTRACT.md"
SCHEMA_RELATIVE_PATH = "core/contracts/EXECUTION-MANIFEST.schema.json"
DOCTRINE_RELATIVE_PATH = (
    "core/managed-core/content/doctrine/CODING-EXECUTION-PROTOCOL.md"
)
HOSTED_CAPACITY_DOCTRINE_RELATIVE_PATH = (
    "core/managed-core/content/doctrine/HOSTED-CAPACITY-SCHEDULER.md"
)
CONTINUOUS_UTILIZATION_CONFIG_RELATIVE_PATH = (
    "core/managed-core/content/config/continuous-utilization.json"
)
CONTINUOUS_UTILIZATION_SCHEMA_RELATIVE_PATH = (
    "core/managed-core/schemas/continuous-utilization.schema.json"
)
CONTINUOUS_UTILIZATION_EXAMPLE_RELATIVE_PATH = (
    "core/managed-core/examples/continuous-utilization.example.json"
)
EXAMPLE_MANIFEST_RELATIVE_PATH = (
    "core/execution/examples/execution-manifest.example.json"
)
VERIFICATION_LIVENESS_CONTRACT_RELATIVE_PATH = (
    "core/contracts/VERIFICATION-LIVENESS-CONTRACT.md"
)
VERIFICATION_RUN_SCHEMA_RELATIVE_PATH = "core/contracts/VERIFICATION-RUN.schema.json"
VERIFICATION_LIVENESS_DOCTRINE_RELATIVE_PATH = (
    "core/managed-core/content/doctrine/VERIFICATION-LIVENESS.md"
)
VERIFICATION_LIVENESS_CONFIG_RELATIVE_PATH = (
    "core/managed-core/content/config/verification-liveness.json"
)
VERIFICATION_LIVENESS_SCHEMA_RELATIVE_PATH = (
    "core/managed-core/schemas/verification-liveness.schema.json"
)
VERIFICATION_RUN_MANAGED_SCHEMA_RELATIVE_PATH = (
    "core/managed-core/schemas/verification-run.schema.json"
)
VERIFICATION_RUN_EXAMPLE_RELATIVE_PATH = (
    "core/execution/examples/verification-run.example.json"
)
VERIFICATION_RUN_MANAGED_EXAMPLE_RELATIVE_PATH = (
    "core/managed-core/examples/verification-run.example.json"
)
TRANSACTIONAL_DISPATCH_CONTRACT_RELATIVE_PATH = (
    "core/contracts/PKT08-REVISION-60-FINAL-CONTROLS.md"
)
TRANSACTIONAL_DISPATCH_CONFIG_RELATIVE_PATH = (
    "core/managed-core/content/config/transactional-dispatch.json"
)
TRANSACTIONAL_DISPATCH_SCHEMA_RELATIVE_PATH = (
    "core/managed-core/schemas/transactional-dispatch.schema.json"
)
TRANSACTIONAL_DISPATCH_DOCTRINE_RELATIVE_PATH = (
    "core/managed-core/content/doctrine/PKT08-REVISION-60-FINAL-CONTROLS.md"
)
HEARTBEAT_COMPARE_FIELDS = (
    "packet_id",
    "attempt_id",
    "sequence",
    "repository",
    "commit",
    "tree",
    "payload_digest",
)
EXHAUSTION_REASONS = frozenset(
    {
        "ordinary_source_exhausted",
        "infrastructure_stopped",
        "code_failure_no_retry",
    }
)
EXHAUSTION_RECOVERY = {
    "ordinary_source_exhausted": "new_identity",
    "infrastructure_stopped": "hold",
    "code_failure_no_retry": "new_identity",
}

ORDINARY_SOURCE_REPAIR_LIMIT = 3
INFRASTRUCTURE_ATTEMPT_LIMIT = 2
CODE_FAILURE_RETRY_LIMIT = 0

PROTECTED_REFS = frozenset({"development", "staging", "main"})
RESERVED_APPROVAL_ACTIONS = frozenset(
    {
        "main_promote",
        "publish_release",
        "deploy_production",
        "github_protection_change",
        "provider_live_mutation",
    }
)
AUTOMATIC_ACTIONS = frozenset({"checkpoint", "issue_commit"})
FORBIDDEN_ACTOR_ACTIONS = frozenset({"self_review", "self_merge", "prefer_incoming"})

REQUIRED_DISCOVERY_PATHS = (
    PROTOCOL_DOCUMENT_RELATIVE_PATH,
    CONTROL_CONTRACT_RELATIVE_PATH,
    SCHEMA_RELATIVE_PATH,
    DOCTRINE_RELATIVE_PATH,
    HOSTED_CAPACITY_DOCTRINE_RELATIVE_PATH,
    CONTINUOUS_UTILIZATION_CONFIG_RELATIVE_PATH,
    CONTINUOUS_UTILIZATION_SCHEMA_RELATIVE_PATH,
    CONTINUOUS_UTILIZATION_EXAMPLE_RELATIVE_PATH,
    VERIFICATION_LIVENESS_CONTRACT_RELATIVE_PATH,
    VERIFICATION_RUN_SCHEMA_RELATIVE_PATH,
    VERIFICATION_LIVENESS_DOCTRINE_RELATIVE_PATH,
    VERIFICATION_LIVENESS_CONFIG_RELATIVE_PATH,
    VERIFICATION_LIVENESS_SCHEMA_RELATIVE_PATH,
    VERIFICATION_RUN_MANAGED_SCHEMA_RELATIVE_PATH,
    VERIFICATION_RUN_EXAMPLE_RELATIVE_PATH,
    VERIFICATION_RUN_MANAGED_EXAMPLE_RELATIVE_PATH,
    TRANSACTIONAL_DISPATCH_CONTRACT_RELATIVE_PATH,
    TRANSACTIONAL_DISPATCH_CONFIG_RELATIVE_PATH,
    TRANSACTIONAL_DISPATCH_SCHEMA_RELATIVE_PATH,
    TRANSACTIONAL_DISPATCH_DOCTRINE_RELATIVE_PATH,
)


@dataclass(frozen=True)
class ProtocolDiscovery:
    protocol_id: str
    protocol_version: str
    repo_root: Path
    protocol_document: Path
    control_contract: Path
    schema_path: Path
    doctrine_path: Path
    hosted_capacity_doctrine: Path
    continuous_utilization_config: Path
    continuous_utilization_schema: Path
    continuous_utilization_example: Path
    example_manifest: Path | None
    verification_liveness_contract: Path
    verification_run_schema: Path
    verification_liveness_doctrine: Path
    verification_liveness_config: Path
    verification_liveness_schema: Path
    verification_run_managed_schema: Path
    verification_run_example: Path
    verification_run_managed_example: Path
    transactional_dispatch_contract: Path
    transactional_dispatch_config: Path
    transactional_dispatch_schema: Path
    transactional_dispatch_doctrine: Path


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()

    @property
    def skipped(self) -> bool:
        return False


@dataclass(frozen=True)
class CandidateIdentity:
    repository: str
    commit: str
    tree: str
    workflow_digest: str | None = None
    profile_digest: str | None = None


@dataclass(frozen=True)
class InvalidationResult:
    invalidated: bool
    reason: str | None = None


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    stop: bool
    reason: str


@dataclass(frozen=True)
class LeaseState:
    holder: str
    packet_id: str
    repository: str
    nonce: str
    expires_at: datetime


@dataclass(frozen=True)
class ResourceVerdict:
    admitted: bool
    reason: str
    uncertain: bool = False


@dataclass(frozen=True)
class ApprovalDecision:
    allowed: bool
    automatic: bool
    founder_required: bool
    reason: str


@dataclass(frozen=True)
class AutoworkDiscoveryDecision:
    required: bool
    ok: bool
    proof_level: str
    reason: str


@dataclass(frozen=True)
class IssueCheckpointDecision:
    accepted: bool
    requires_review_ready: bool
    requires_token: bool
    reason: str


@dataclass(frozen=True)
class LegacyGateResult:
    classification: str
    is_pass: bool
    is_implementation_failure: bool
    reason: str


@dataclass(frozen=True)
class AdministratorRecoveryDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class HeartbeatGateResult:
    ok: bool
    reason: str


@dataclass(frozen=True)
class VerificationReceiptDecision:
    accepted: bool
    promotable: bool
    reason: str


@dataclass(frozen=True)
class ExhaustionDiagnosis:
    kind: str
    exhausted: bool
    recovery: str
    reason: str


@dataclass(frozen=True)
class RecoveryDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class SchedulerVerdict:
    scheduled: bool
    reason: str
    diagnosis: str
    uncertain: bool = False


def control_loop_invocation_key(
    *,
    coordinator_task_id: str,
    trigger: str,
    invocation_id: str | None = None,
) -> str:
    """Return the stable key shared by hourly and exact ``PULSE`` wakes."""

    task = str(coordinator_task_id or "").strip()
    event = str(invocation_id or trigger or "").strip()
    if not task or not event:
        raise ValueError("control_loop_invocation_identity_required")
    return f"{task}:{event}"


def validate_control_loop_lease(
    lease: Mapping[str, Any],
    *,
    holder: str,
    coordinator_task_id: str,
    now: datetime | None = None,
) -> bool:
    """Validate a durable portfolio-controller lease without ambient state."""

    clock = now or datetime.now(timezone.utc)
    if not isinstance(lease, Mapping):
        return False
    try:
        expires = datetime.fromisoformat(str(lease["expiresAt"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return False
    if expires.tzinfo is None or expires <= clock.astimezone(timezone.utc):
        return False
    return (
        lease.get("holder") == holder
        and lease.get("coordinatorTaskId") == coordinator_task_id
        and isinstance(lease.get("nonce"), str)
        and bool(lease.get("nonce"))
    )


class DurableHeartbeatStore:
    """In-process durable store used by protocol tests. Not a hosted runtime."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}

    @staticmethod
    def key(record: Mapping[str, Any]) -> str:
        return ":".join(
            (
                str(record.get("packet_id") or ""),
                str(record.get("attempt_id") or ""),
                str(record.get("sequence") or ""),
            )
        )

    def write(self, record: Mapping[str, Any]) -> None:
        self._records[self.key(record)] = dict(record)

    def read(self, record: Mapping[str, Any]) -> dict[str, Any] | None:
        stored = self._records.get(self.key(record))
        return dict(stored) if stored is not None else None


def _as_root(repo_root: Path | str) -> Path:
    return Path(repo_root).resolve()


def _installed_relative_path(relative_path: str) -> str:
    if relative_path.startswith("core/managed-core/"):
        return ".ide-development/" + relative_path.removeprefix("core/managed-core/")
    if relative_path.startswith("core/contracts/"):
        return ".ide-development/contracts/" + relative_path.removeprefix(
            "core/contracts/"
        )
    if relative_path.startswith("core/execution/"):
        return ".ide-development/execution/" + relative_path.removeprefix(
            "core/execution/"
        )
    raise ValueError(f"unsupported protocol discovery path: {relative_path}")


def discover_runtime(repo_root: Path | str) -> ProtocolDiscovery:
    root = _as_root(repo_root)
    source_paths = {rel: root / rel for rel in REQUIRED_DISCOVERY_PATHS}
    if all(path.is_file() for path in source_paths.values()):
        paths = source_paths
        example = root / EXAMPLE_MANIFEST_RELATIVE_PATH
    else:
        paths = {
            rel: root / _installed_relative_path(rel)
            for rel in REQUIRED_DISCOVERY_PATHS
        }
        missing = [str(path.relative_to(root)) for path in paths.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError(
                "coding execution protocol surfaces missing: " + ", ".join(missing)
            )
        example = root / _installed_relative_path(EXAMPLE_MANIFEST_RELATIVE_PATH)
    return ProtocolDiscovery(
        protocol_id=PROTOCOL_ID,
        protocol_version=PROTOCOL_VERSION,
        repo_root=root,
        protocol_document=paths[PROTOCOL_DOCUMENT_RELATIVE_PATH],
        control_contract=paths[CONTROL_CONTRACT_RELATIVE_PATH],
        schema_path=paths[SCHEMA_RELATIVE_PATH],
        doctrine_path=paths[DOCTRINE_RELATIVE_PATH],
        hosted_capacity_doctrine=paths[HOSTED_CAPACITY_DOCTRINE_RELATIVE_PATH],
        continuous_utilization_config=paths[CONTINUOUS_UTILIZATION_CONFIG_RELATIVE_PATH],
        continuous_utilization_schema=paths[CONTINUOUS_UTILIZATION_SCHEMA_RELATIVE_PATH],
        continuous_utilization_example=paths[CONTINUOUS_UTILIZATION_EXAMPLE_RELATIVE_PATH],
        example_manifest=example if example.is_file() else None,
        verification_liveness_contract=paths[VERIFICATION_LIVENESS_CONTRACT_RELATIVE_PATH],
        verification_run_schema=paths[VERIFICATION_RUN_SCHEMA_RELATIVE_PATH],
        verification_liveness_doctrine=paths[VERIFICATION_LIVENESS_DOCTRINE_RELATIVE_PATH],
        verification_liveness_config=paths[VERIFICATION_LIVENESS_CONFIG_RELATIVE_PATH],
        verification_liveness_schema=paths[VERIFICATION_LIVENESS_SCHEMA_RELATIVE_PATH],
        verification_run_managed_schema=paths[VERIFICATION_RUN_MANAGED_SCHEMA_RELATIVE_PATH],
        verification_run_example=paths[VERIFICATION_RUN_EXAMPLE_RELATIVE_PATH],
        verification_run_managed_example=paths[VERIFICATION_RUN_MANAGED_EXAMPLE_RELATIVE_PATH],
        transactional_dispatch_contract=paths[TRANSACTIONAL_DISPATCH_CONTRACT_RELATIVE_PATH],
        transactional_dispatch_config=paths[TRANSACTIONAL_DISPATCH_CONFIG_RELATIVE_PATH],
        transactional_dispatch_schema=paths[TRANSACTIONAL_DISPATCH_SCHEMA_RELATIVE_PATH],
        transactional_dispatch_doctrine=paths[TRANSACTIONAL_DISPATCH_DOCTRINE_RELATIVE_PATH],
    )


def load_execution_schema(repo_root: Path | str | None = None) -> dict[str, Any]:
    if repo_root is None:
        schema_path = Path(__file__).resolve().parents[1] / "contracts" / (
            "EXECUTION-MANIFEST.schema.json"
        )
    else:
        schema_path = discover_runtime(repo_root).schema_path
    return json.loads(schema_path.read_text(encoding="utf-8"))


def validate_execution_manifest(
    document: Mapping[str, Any],
    *,
    schema: Mapping[str, Any] | None = None,
    repo_root: Path | str | None = None,
) -> ValidationResult:
    loaded = dict(schema) if schema is not None else load_execution_schema(repo_root)
    validator = Draft202012Validator(loaded)
    errors = sorted(
        error.message for error in validator.iter_errors(document)
    )
    if errors:
        return ValidationResult(ok=False, errors=tuple(errors))
    protocol = document.get("protocol") or {}
    if protocol.get("id") != PROTOCOL_ID or protocol.get("version") != PROTOCOL_VERSION:
        return ValidationResult(
            ok=False,
            errors=("protocol identity must be coding-execution-protocol 1.0.1",),
        )
    if protocol.get("amendment") != AMENDMENT_ID:
        return ValidationResult(
            ok=False,
            errors=("protocol amendment must be V25_BOOTSTRAP_LEAN",),
        )
    publisher = (document.get("controls") or {}).get("publisherAuthority") or {}
    if publisher.get("canonicalForV25") not in (None, "none"):
        return ValidationResult(
            ok=False,
            errors=("v2.5 forbids a singular canonical legacy publisher",),
        )
    return ValidationResult(ok=True)


def candidate_identity(
    *,
    repository: str,
    commit: str,
    tree: str,
    workflow_digest: str | None = None,
    profile_digest: str | None = None,
) -> CandidateIdentity:
    return CandidateIdentity(
        repository=repository,
        commit=commit,
        tree=tree,
        workflow_digest=workflow_digest,
        profile_digest=profile_digest,
    )


def invalidate_candidate(
    previous: CandidateIdentity,
    current: CandidateIdentity,
) -> InvalidationResult:
    if previous.repository != current.repository:
        return InvalidationResult(True, "repository_changed")
    if previous.commit != current.commit or previous.tree != current.tree:
        return InvalidationResult(True, "exact_candidate_changed")
    if (
        previous.workflow_digest is not None
        and previous.workflow_digest != current.workflow_digest
    ):
        return InvalidationResult(True, "workflow_digest_changed")
    if (
        previous.profile_digest is not None
        and previous.profile_digest != current.profile_digest
    ):
        return InvalidationResult(True, "profile_digest_changed")
    return InvalidationResult(False, None)


def retry_decision(
    kind: str,
    attempt: int,
    *,
    ordinary_limit: int = ORDINARY_SOURCE_REPAIR_LIMIT,
    infrastructure_limit: int = INFRASTRUCTURE_ATTEMPT_LIMIT,
    code_failure_limit: int = CODE_FAILURE_RETRY_LIMIT,
) -> RetryDecision:
    if attempt < 1:
        return RetryDecision(False, True, "invalid_attempt")
    if kind == "ordinary_source":
        if attempt <= ordinary_limit:
            return RetryDecision(True, False, "ordinary_source_repair")
        return RetryDecision(False, True, "ordinary_source_exhausted")
    if kind == "infrastructure":
        if attempt < infrastructure_limit:
            return RetryDecision(True, False, "infrastructure_retry")
        return RetryDecision(False, True, "infrastructure_stopped")
    if kind == "code_failure":
        if attempt <= code_failure_limit:
            return RetryDecision(True, False, "code_failure_retry")
        return RetryDecision(False, True, "code_failure_no_retry")
    return RetryDecision(False, True, "unknown_failure_kind")


def acquire_orchestration_lease(
    *,
    holder: str,
    packet_id: str,
    repository: str,
    nonce: str,
    expires_at: datetime,
    existing: LeaseState | None = None,
    now: datetime | None = None,
) -> LeaseState:
    clock = now or datetime.now(timezone.utc)
    if existing is not None and existing.expires_at > clock:
        if (
            existing.packet_id == packet_id
            and existing.repository == repository
            and existing.holder != holder
        ):
            raise PermissionError("orchestration_lease_held")
        if existing.nonce != nonce and existing.holder != holder:
            raise PermissionError("orchestration_lease_conflict")
    return LeaseState(
        holder=holder,
        packet_id=packet_id,
        repository=repository,
        nonce=nonce,
        expires_at=expires_at,
    )


def validate_lease(
    lease: LeaseState,
    *,
    holder: str,
    packet_id: str,
    repository: str,
    now: datetime | None = None,
) -> bool:
    clock = now or datetime.now(timezone.utc)
    if lease.expires_at <= clock:
        return False
    return (
        lease.holder == holder
        and lease.packet_id == packet_id
        and lease.repository == repository
    )


def admit_resources(snapshot: Mapping[str, Any] | None) -> ResourceVerdict:
    if snapshot is None:
        return ResourceVerdict(False, "resource_uncertain", True)
    required = ("cpu_percent", "memory_percent", "free_disk_gib", "docker_available")
    for key in required:
        if key not in snapshot or snapshot[key] is None:
            return ResourceVerdict(False, "resource_uncertain", True)
    if snapshot.get("interactive_use"):
        return ResourceVerdict(False, "interactive_use", False)
    return ResourceVerdict(True, "admitted", False)


def required_approval(
    action: str,
    *,
    recorded_approvals: Mapping[str, str] | None = None,
) -> ApprovalDecision:
    if action in FORBIDDEN_ACTOR_ACTIONS:
        return ApprovalDecision(False, False, False, "actor_forbidden")
    if action in AUTOMATIC_ACTIONS:
        return ApprovalDecision(True, True, False, "automatic")
    if action == "staging_promote":
        return ApprovalDecision(True, True, False, "automatic_on_receipt_identity")
    if action in RESERVED_APPROVAL_ACTIONS:
        approvals = recorded_approvals or {}
        if approvals.get(action) == "founder":
            return ApprovalDecision(True, False, True, "founder_recorded")
        return ApprovalDecision(False, False, True, "founder_required")
    return ApprovalDecision(False, False, True, "unknown_action")


def git_authority_allows(
    action: str,
    *,
    branch: str,
    actor: str,
) -> bool:
    if action in {"push_protected", "merge_own_pr", "prefer_incoming", "nested_self_install"}:
        return False
    if action == "push_work_branch":
        if branch in PROTECTED_REFS:
            return False
        return branch.startswith("issue/") and actor == "implementer"
    if action == "open_pr":
        return actor in {"packager", "packager_coordinator"}
    if action == "merge_to_development":
        return actor == "delivery_controller"
    return False


def _is_sha40(value: str) -> bool:
    return len(value) == 40 and all(char in _SHA40 for char in value)


def valid_independent_narrow_review(
    review: Mapping[str, Any] | None,
    *,
    commit: str,
    tree: str,
) -> bool:
    """Validate one provider-neutral, exact-candidate narrow review.

    The route may be the ordinary Cursor reviewer or a Principal-authorized
    Luna reviewer.  The protocol therefore validates identity and role
    separation, not a vendor or model name.
    """

    if not isinstance(review, Mapping) or review.get("accepted") is not True:
        return False
    if review.get("headSha") != commit or review.get("gitTree") != tree:
        return False
    paths = review.get("paths") or review.get("scope")
    if not isinstance(paths, list) or not paths or any(
        not isinstance(path, str) or not path.strip() for path in paths
    ):
        return False
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, Mapping):
        return False
    actor = str(reviewer.get("actor") or reviewer.get("id") or "").strip()
    role = str(reviewer.get("role") or "").strip().lower()
    implementer = str(
        review.get("implementerActor") or review.get("implementer") or ""
    ).strip()
    if not actor or role != "reviewer" or not implementer or actor == implementer:
        return False
    return True


def publisher_is_canonical(name: str | None) -> bool:
    del name
    return False


def classify_legacy_publisher_gate(
    *,
    publisher: str,
    state: str,
) -> LegacyGateResult:
    if publisher not in LEGACY_PUBLISHERS:
        return LegacyGateResult(
            "unknown_publisher",
            False,
            True,
            "unknown_publisher",
        )
    if state in {"missing", "failed"}:
        return LegacyGateResult(
            WAIVED_LEGACY_GATE,
            False,
            False,
            "legacy_publisher_waived",
        )
    if state == "success":
        return LegacyGateResult(
            "LEGACY_NON_CANONICAL",
            False,
            False,
            "legacy_publisher_not_canonical_for_v25",
        )
    return LegacyGateResult(
        "unknown_legacy_state",
        False,
        True,
        "unknown_legacy_state",
    )


def evaluate_issue_checkpoint(
    *,
    pushed: bool,
    commit: str,
    tree: str,
    scoped_diff: bool,
    focused_tests_passed: bool,
    independent_narrow_review: Mapping[str, Any] | None,
    manifest_evidence: bool,
    review_ready: bool = False,
    automation_token_present: bool = False,
) -> IssueCheckpointDecision:
    del review_ready, automation_token_present
    if not pushed or not _is_sha40(commit) or not _is_sha40(tree):
        return IssueCheckpointDecision(
            False, False, False, "exact_pushed_commit_tree_required"
        )
    if not scoped_diff:
        return IssueCheckpointDecision(False, False, False, "scoped_diff_required")
    if not focused_tests_passed:
        return IssueCheckpointDecision(False, False, False, "focused_tests_required")
    if not valid_independent_narrow_review(
        independent_narrow_review, commit=commit, tree=tree
    ):
        return IssueCheckpointDecision(
            False, False, False, "independent_narrow_review_required"
        )
    if not manifest_evidence:
        return IssueCheckpointDecision(
            False, False, False, "manifest_evidence_required"
        )
    return IssueCheckpointDecision(
        True,
        False,
        False,
        "v25_bootstrap_lean_issue_checkpoint",
    )


def administrator_recovery(
    *,
    named_exception: str,
    exact_head: str,
    replacement_proof: bool,
    operations: tuple[str, ...] | list[str],
) -> AdministratorRecoveryDecision:
    if not named_exception.strip():
        return AdministratorRecoveryDecision(False, "named_exception_required")
    if not replacement_proof:
        return AdministratorRecoveryDecision(False, "replacement_proof_required")
    if not _is_sha40(exact_head):
        return AdministratorRecoveryDecision(False, "exact_head_required")
    ops = tuple(operations)
    if not ops:
        return AdministratorRecoveryDecision(False, "recovery_operations_required")
    if any(op not in ADMIN_RECOVERY_OPERATIONS for op in ops):
        return AdministratorRecoveryDecision(
            False, "operations_limited_to_snapshot_restore_readback"
        )
    return AdministratorRecoveryDecision(True, "named_exact_head_recovery")


def autowork_discovery_decision(
    *,
    callable_now: bool,
    performed: bool,
    claimed_live_pass: bool = False,
) -> AutoworkDiscoveryDecision:
    if callable_now:
        if not performed:
            return AutoworkDiscoveryDecision(
                True,
                False,
                "none",
                "autowork_discovery_required_when_callable",
            )
        return AutoworkDiscoveryDecision(True, True, "discovery", "performed")
    if claimed_live_pass:
        return AutoworkDiscoveryDecision(
            False,
            False,
            "none",
            "cannot_claim_live_pass_when_not_callable",
        )
    return AutoworkDiscoveryDecision(False, True, "hold", "unavailable_hold")


def _heartbeat_identity(record: Mapping[str, Any]) -> CandidateIdentity:
    return candidate_identity(
        repository=str(record.get("repository") or ""),
        commit=str(record.get("commit") or ""),
        tree=str(record.get("tree") or ""),
    )


def _records_match(written: Mapping[str, Any], readback: Mapping[str, Any]) -> bool:
    for field in HEARTBEAT_COMPARE_FIELDS:
        if written.get(field) != readback.get(field):
            return False
    return True


def evaluate_heartbeat_gate(
    *,
    written: Mapping[str, Any] | None,
    readback: Mapping[str, Any] | None,
    checkout: CandidateIdentity,
) -> HeartbeatGateResult:
    if written is None:
        return HeartbeatGateResult(False, "heartbeat_write_missing")
    if not _is_sha40(checkout.commit) or not _is_sha40(checkout.tree):
        return HeartbeatGateResult(False, "heartbeat_identity_unbound")
    if str(written.get("commit") or "") != checkout.commit or str(
        written.get("tree") or ""
    ) != checkout.tree:
        return HeartbeatGateResult(False, "heartbeat_identity_unbound")
    if str(written.get("repository") or "") != checkout.repository:
        return HeartbeatGateResult(False, "heartbeat_identity_unbound")
    if readback is None:
        return HeartbeatGateResult(False, "heartbeat_readback_missing")
    if not _records_match(written, readback):
        return HeartbeatGateResult(False, "heartbeat_readback_mismatch")
    return HeartbeatGateResult(True, "heartbeat_durable")


def persist_heartbeat(
    store: DurableHeartbeatStore,
    record: Mapping[str, Any],
) -> HeartbeatGateResult:
    checkout = _heartbeat_identity(record)
    if not _is_sha40(checkout.commit) or not _is_sha40(checkout.tree):
        return HeartbeatGateResult(False, "heartbeat_identity_unbound")
    store.write(record)
    return evaluate_heartbeat_gate(
        written=dict(record),
        readback=store.read(record),
        checkout=checkout,
    )


def _is_merge_ref(checkout_ref: str) -> bool:
    ref = checkout_ref.strip()
    if "refs/pull/" not in ref:
        return False
    return ref.rstrip("/").endswith("/merge")


def evaluate_verification_receipt(
    receipt: Mapping[str, Any],
    *,
    checkout: CandidateIdentity,
) -> VerificationReceiptDecision:
    ref = str(receipt.get("checkoutRef") or "")
    commit = str(receipt.get("commit") or "")
    tree = str(receipt.get("tree") or "")
    merge_evidence = receipt.get("mergeRefEvidence")
    if _is_merge_ref(ref):
        return VerificationReceiptDecision(
            False, False, "merge_ref_identity_forbidden"
        )
    if merge_evidence not in (None, {}, False) and receipt.get("promotableIdentity") is True:
        return VerificationReceiptDecision(False, False, "merge_ref_not_promotable")
    if commit != checkout.commit or tree != checkout.tree:
        return VerificationReceiptDecision(
            False, False, "checkout_identity_mismatch"
        )
    if checkout.repository and receipt.get("repository") not in (
        None,
        checkout.repository,
    ):
        return VerificationReceiptDecision(
            False, False, "checkout_identity_mismatch"
        )
    if receipt.get("promotableIdentity") is not True:
        return VerificationReceiptDecision(
            False, False, "receipt_not_promotable"
        )
    if not _is_sha40(commit) or not _is_sha40(tree):
        return VerificationReceiptDecision(
            False, False, "checkout_identity_mismatch"
        )
    return VerificationReceiptDecision(True, True, "checkout_bound_receipt")


def diagnose_retry_exhaustion(kind: str, attempt: int) -> ExhaustionDiagnosis:
    decision = retry_decision(kind, attempt)
    if decision.retry:
        return ExhaustionDiagnosis(kind, False, "continue", decision.reason)
    recovery = EXHAUSTION_RECOVERY.get(decision.reason, "hold")
    return ExhaustionDiagnosis(kind, True, recovery, decision.reason)


def evaluate_exhaustion_recovery(
    diagnosis: ExhaustionDiagnosis,
    *,
    previous: CandidateIdentity,
    current: CandidateIdentity,
    named_exception: bool = False,
) -> RecoveryDecision:
    if not diagnosis.exhausted:
        return RecoveryDecision(True, "not_exhausted")
    same_identity = (
        previous.repository == current.repository
        and previous.commit == current.commit
        and previous.tree == current.tree
    )
    if same_identity and named_exception and diagnosis.recovery == "hold":
        return RecoveryDecision(True, "named_exception_recovery")
    if same_identity:
        return RecoveryDecision(False, "silent_retry_after_exhaustion")
    if diagnosis.recovery in {"new_identity", "hold"}:
        return RecoveryDecision(True, "new_identity_recovery")
    return RecoveryDecision(False, "silent_retry_after_exhaustion")


def schedule_hosted_capacity(
    snapshot: Mapping[str, Any] | None,
    *,
    allocator_status: str | None = None,
    available_slots: int | None = None,
) -> SchedulerVerdict:
    admitted = admit_resources(snapshot)
    busy = allocator_status in {"busy", "exhausted"}
    if admitted.uncertain or not admitted.admitted:
        reason = "resource_uncertain" if admitted.uncertain else admitted.reason
        return SchedulerVerdict(
            False,
            reason,
            "uncertain" if admitted.uncertain else admitted.reason,
            admitted.uncertain,
        )
    if available_slots is not None and available_slots <= 0:
        return SchedulerVerdict(False, "capacity_exhausted", "capacity_exhausted", False)
    if busy and available_slots is None:
        return SchedulerVerdict(
            False,
            "allocator_busy_not_diagnosis",
            "not_diagnosed",
            True,
        )
    return SchedulerVerdict(True, "scheduled", "admitted", False)


def protocol_document_version(text: str) -> str | None:
    for line in text.splitlines():
        lowered = line.lower().lstrip("* ").strip()
        if lowered.startswith("protocol version:"):
            return line.split(":", 1)[1].replace("*", "").strip()
    return None
