#!/usr/bin/env python3
"""Linktrend Review Gate (WP-U01 / Update 1).

Classifies exact-head Bugbot provider results into managed outcomes and decides
the required ``Linktrend Review Gate`` context. Raw ``Cursor Bugbot`` remains an
observed provider signal only and must not stay required after migration.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1
KIND = "linktrend-review-gate"

REVIEW_GATE_CONTEXT = "Linktrend Review Gate"
RAW_BUGBOT_CONTEXT = "Cursor Bugbot"

OUTCOME_PASSED = "review-passed"
OUTCOME_FINDINGS = "review-findings"
OUTCOME_FAILED = "review-failed"
OUTCOME_ADVISORY = "advisory-unavailable"
OUTCOME_UNKNOWN = "review-unknown"

OUTCOMES = frozenset(
    {
        OUTCOME_PASSED,
        OUTCOME_FINDINGS,
        OUTCOME_FAILED,
        OUTCOME_ADVISORY,
        OUTCOME_UNKNOWN,
    }
)

MAX_INFRASTRUCTURE_ATTEMPTS = 2

PROVIDER_UNAVAILABLE_CLASSES = frozenset(
    {
        "quota",
        "spending_limit",
        "service_outage",
        "provider_error",
    }
)

FULL_SUITE_CONTEXT = "Linktrend Full Suite"
FOUNDER_ALERT_MARKER_PREFIX = "<!-- linktrend-review-gate-alert:"
INFRA_ATTEMPT_MARKER_PREFIX = "<!-- linktrend-review-gate-infra-attempt:"
FALLBACK_REQUEST_MARKER_PREFIX = "<!-- linktrend-review-gate-fallback:"
TRUSTED_PROVIDER_SOURCES = frozenset(
    {
        "repair_observer.usage_limit",
        "operator_verified_provider_error",
        "provider_status_api",
    }
)

# Authenticated provenance kinds that may authorize advisory-unavailable success.
# Claiming an allowlisted source name inside a candidate worktree file is never enough.
TRUSTED_PROVIDER_PROVENANCE_KINDS = frozenset(
    {
        "github.repository_variable",
        "github.repair_task.api",
        "github.actions.trusted_env",
        "provider_status_api.authenticated",
    }
)

# Full receipt / check evidence must come from authenticated GitHub surfaces.
TRUSTED_FULL_RECEIPT_PROVENANCE_KINDS = frozenset(
    {
        "github.check_runs.api",
        "github.actions.artifact",
    }
)

# Structured findings evidence may only come from GitHub check_run event fields
# or verified provider findings payloads — never from candidate-controlled scripts.
TRUSTED_FINDINGS_SOURCES = frozenset(
    {
        "github.check_run.annotations",
        "github.check_run.output",
        "cursor_bugbot.check_run",
        "operator_verified_findings",
    }
)

# Provider-authored check output with an explicit positive findings count.
_FINDINGS_COUNT_RE = re.compile(
    r"(?i)\b(?:found|reported|detected)\s+(\d+)\s+(?:potential\s+)?"
    r"(?:issue|finding|problem)s?\b"
    r"|\b(\d+)\s+(?:unresolved\s+)?(?:issue|finding)s?\b"
)

# Evidence channels are assigned by the trusted workflow loader — never by candidate JSON.
EVIDENCE_CHANNEL_GITHUB_CHECK_RUN = "github_check_run"
EVIDENCE_CHANNEL_REPAIR_OBSERVER_RECORD = "repair_observer_record"
EVIDENCE_CHANNEL_OPERATOR_PRIVILEGED = "operator_privileged_input"
EVIDENCE_CHANNEL_PROVIDER_STATUS_API = "provider_status_api"
EVIDENCE_CHANNEL_CANDIDATE_FILE = "candidate_repository_file"

TRUSTED_EVIDENCE_CHANNELS = frozenset(
    {
        EVIDENCE_CHANNEL_GITHUB_CHECK_RUN,
        EVIDENCE_CHANNEL_REPAIR_OBSERVER_RECORD,
        EVIDENCE_CHANNEL_OPERATOR_PRIVILEGED,
        EVIDENCE_CHANNEL_PROVIDER_STATUS_API,
    }
)

PROVIDER_SOURCE_TRUSTED_CHANNELS: dict[str, frozenset[str]] = {
    "repair_observer.usage_limit": frozenset(
        {
            EVIDENCE_CHANNEL_REPAIR_OBSERVER_RECORD,
            EVIDENCE_CHANNEL_GITHUB_CHECK_RUN,
        }
    ),
    "operator_verified_provider_error": frozenset({EVIDENCE_CHANNEL_OPERATOR_PRIVILEGED}),
    "provider_status_api": frozenset({EVIDENCE_CHANNEL_PROVIDER_STATUS_API}),
}

TRUSTED_FULL_RECEIPT_CHANNELS = frozenset({EVIDENCE_CHANNEL_GITHUB_CHECK_RUN})
TRUSTED_CHECK_APP_SLUGS = frozenset({"github-actions"})
TRUSTED_PROVIDER_UNAVAILABILITY_CHECK_NAMES = frozenset(
    {"Linktrend Provider Unavailability"}
)
# Workflow paths are the authenticated producer identity (default-branch files).
# Candidate branches cannot forge these paths' default-branch blob identity.
TRUSTED_FULL_SUITE_WORKFLOW_PATHS = frozenset(
    {".github/workflows/linktrend-integrator-merge.yml"}
)
TRUSTED_PROVIDER_UNAVAILABILITY_WORKFLOW_PATHS = frozenset(
    {".github/workflows/linktrend-repair-observer.yml"}
)
_ACTIONS_RUN_ID_RE = re.compile(r"/actions/runs/(\d+)")
_CHECK_RUN_ID_RE = re.compile(r"/check-runs/(\d+)")

_SHA40 = re.compile(r"^[0-9a-f]{40}$")


class ReviewGateError(Exception):
    """Fail-closed review-gate failure with a stable machine code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


def require_sha40(value: str, label: str = "sha") -> str:
    text = (value or "").strip().lower()
    if not _SHA40.fullmatch(text):
        raise ReviewGateError("invalid_sha", f"{label} must be 40 lowercase hex")
    return text


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _norm(value).lower()


def structured_bugbot_findings_present(
    *,
    annotations_count: int | None = None,
    bugbot_conclusion: str | None = None,
    findings_present: bool = False,
) -> bool:
    """Return True only for trustworthy structured Bugbot finding signals.

    Accepts explicit classifier flags, GitHub check ``annotations_count > 0``,
    or ``conclusion=action_required``. Never interprets free-text summaries,
    candidate prose, missing output, or neutral-alone as findings or as pass.
    """
    if findings_present:
        return True
    if annotations_count is not None:
        try:
            count = int(annotations_count)
        except (TypeError, ValueError) as exc:
            raise ReviewGateError(
                "invalid_annotations_count",
                "annotations_count must be an integer",
            ) from exc
        if count < 0:
            raise ReviewGateError(
                "invalid_annotations_count",
                "annotations_count must be >= 0",
            )
        if count > 0:
            return True
    return _lower(bugbot_conclusion) == "action_required"


@dataclass(frozen=True)
class Classification:
    """One exact-candidate managed review classification."""

    outcome: str
    gateSuccess: bool
    bugbotPassedClaim: bool
    alertFounder: bool
    detail: str
    headSha: str
    gitTree: str
    repository: str
    pullRequest: int | None
    infrastructureAttempts: int
    providerClass: str | None
    sanitizedAlert: str | None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schemaVersion"] = SCHEMA_VERSION
        payload["kind"] = KIND
        payload["context"] = REVIEW_GATE_CONTEXT
        return payload


def assert_full_suite_allows_bugbot(full_suite_status: str) -> None:
    """Final-candidate Bugbot may run only after exact Full Suite success."""
    if _lower(full_suite_status) != "success":
        raise ReviewGateError(
            "bugbot_before_full_forbidden",
            f"full_suite_status={full_suite_status!r}",
        )


def reject_third_infrastructure_attempt(attempts: int) -> None:
    if attempts < 0:
        raise ReviewGateError("invalid_attempts", "attempts must be >= 0")
    if attempts > MAX_INFRASTRUCTURE_ATTEMPTS:
        raise ReviewGateError(
            "infrastructure_attempt_limit",
            f"attempts={attempts} max={MAX_INFRASTRUCTURE_ATTEMPTS}",
        )


def invalidate_if_head_changed(*, bound_head: str, live_head: str) -> None:
    bound = require_sha40(bound_head, "bound_head")
    live = require_sha40(live_head, "live_head")
    if bound != live:
        raise ReviewGateError("stale_head", f"bound={bound} live={live}")


def require_no_raw_bugbot_required(contexts: Sequence[str]) -> None:
    """Managed required contexts must not retain raw Cursor Bugbot after migration."""
    retained = [c for c in contexts if _norm(c) == RAW_BUGBOT_CONTEXT]
    if retained:
        raise ReviewGateError(
            "raw_bugbot_required",
            f"replace {RAW_BUGBOT_CONTEXT!r} with {REVIEW_GATE_CONTEXT!r}",
        )
    if REVIEW_GATE_CONTEXT not in {_norm(c) for c in contexts}:
        # Callers that pass development required-check lists must include the gate.
        # Empty lists are allowed for non-development surfaces.
        return


def require_review_gate_on_development(contexts: Sequence[str]) -> None:
    names = {_norm(c) for c in contexts}
    require_no_raw_bugbot_required(list(names))
    if REVIEW_GATE_CONTEXT not in names:
        raise ReviewGateError(
            "review_gate_missing",
            f"development required checks must include {REVIEW_GATE_CONTEXT!r}",
        )


def reject_undocumented_task_hold(
    *,
    configured_gates_passed: bool,
    task_hold: str | None,
) -> None:
    if configured_gates_passed and _norm(task_hold):
        raise ReviewGateError(
            "undocumented_task_hold",
            "task-level review HOLD is forbidden after configured gates pass",
        )


def evaluate_fallback_review(
    *,
    outcome: str,
    independent_review_configured: bool,
    reviewer_actor: str,
    implementer_actor: str,
    evidence_head: str,
    live_head: str,
) -> dict[str, Any]:
    """Route advisory-unavailable candidates to a non-implementer fallback reviewer."""
    if outcome != OUTCOME_ADVISORY:
        return {"requested": False, "reason": "fallback_not_applicable"}
    if not independent_review_configured:
        return {"requested": False, "reason": "independent_review_not_configured"}
    reviewer = _norm(reviewer_actor)
    implementer = _norm(implementer_actor)
    if not reviewer:
        raise ReviewGateError("fallback_reviewer_missing", "reviewer_actor required")
    if not implementer:
        raise ReviewGateError("implementer_missing", "implementer_actor required")
    if reviewer == implementer:
        raise ReviewGateError(
            "fallback_implementer_rejected",
            "fallback reviewer must not be the implementer",
        )
    invalidate_if_head_changed(bound_head=evidence_head, live_head=live_head)
    return {
        "requested": True,
        "reviewerActor": reviewer,
        "implementerActor": implementer,
        "headSha": require_sha40(live_head, "live_head"),
        "reason": "advisory_unavailable_fallback",
    }


def evaluate_github_approval(
    *,
    approving_review_required: bool,
    reviewer_login: str,
    comment_author_login: str,
    technical_review_clean: bool,
    evidence_head: str,
    live_head: str,
    approval_source: str = "review",
) -> dict[str, Any]:
    """Distinguish technical review evidence from GitHub approval."""
    invalidate_if_head_changed(bound_head=evidence_head, live_head=live_head)
    reviewer = _norm(reviewer_login)
    commenter = _norm(comment_author_login)
    source = _lower(approval_source) or "review"
    if approving_review_required:
        if source == "comment" or (commenter and not reviewer):
            raise ReviewGateError(
                "same_account_approval_rejected",
                "same-account review comment cannot satisfy required GitHub approval",
            )
        if not reviewer:
            raise ReviewGateError("approval_missing", "approving review required")
        return {
            "approvalSatisfied": True,
            "mode": "github_approval",
            "reviewerLogin": reviewer,
        }
    if not technical_review_clean:
        raise ReviewGateError("technical_review_incomplete", "exact-head technical review required")
    return {
        "approvalSatisfied": True,
        "mode": "technical_review_only",
        "rerunFastFull": False,
        "reviewerLogin": reviewer or commenter,
    }


def _provider_class(raw: Mapping[str, Any] | None) -> str | None:
    if not raw:
        return None
    value = _lower(raw.get("class") or raw.get("providerClass") or raw.get("errorClass"))
    if value in PROVIDER_UNAVAILABLE_CLASSES:
        return value
    return None


def evidence_channel_is_trusted(channel: str) -> bool:
    return _norm(channel) in TRUSTED_EVIDENCE_CHANNELS


def _provenance_mapping(raw: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if not raw:
        return None
    provenance = raw.get("provenance")
    return provenance if isinstance(provenance, Mapping) else None

def verified_provider_unavailability(
    raw: Mapping[str, Any] | None,
    *,
    evidence_channel: str = "",
) -> str | None:
    """Return an approved unavailable class only for trusted verified evidence.

    Trust is established by either:
    - a loader-assigned ``evidence_channel`` (#329 producer/Checks / privileged routes), or
    - authenticated ``provenance`` stamped by trusted workflow helpers (#330).

    Candidate-controlled repository files never authorize advisory success, even
    when they plant an allowlisted ``source`` string. Free-text heuristics and
    unverified payloads must not produce ``advisory-unavailable`` or gate success.
    """
    if not raw:
        return None
    if raw.get("verified") is not True:
        return None
    source = _norm(raw.get("source") or raw.get("evidenceSource"))
    if source not in TRUSTED_PROVIDER_SOURCES:
        return None

    channel = _norm(evidence_channel)
    # Explicit candidate-file channel always fails closed (even if JSON plants provenance).
    if channel == EVIDENCE_CHANNEL_CANDIDATE_FILE:
        return None

    channel_ok = False
    if channel:
        if channel not in TRUSTED_EVIDENCE_CHANNELS:
            channel_ok = False
        else:
            allowed_channels = PROVIDER_SOURCE_TRUSTED_CHANNELS.get(source, frozenset())
            channel_ok = channel in allowed_channels

    provenance = _provenance_mapping(raw)
    provenance_ok = False
    if provenance is not None:
        kind = _norm(provenance.get("kind"))
        if kind in {"candidate.worktree_file", "candidate.committed_artifact"}:
            provenance_ok = False
        else:
            provenance_ok = (
                kind in TRUSTED_PROVIDER_PROVENANCE_KINDS
                and provenance.get("authenticated") is True
            )

    if not channel_ok and not provenance_ok:
        return None
    return _provider_class(raw)


def authenticate_provider_unavailability_evidence(
    raw: Mapping[str, Any] | None,
    *,
    provenance_kind: str,
    head_sha: str,
    evidence_ref: str = "",
) -> dict[str, Any]:
    """Stamp authenticated provenance onto verified provider-unavailability evidence.

    Candidate worktree files must never call this helper. Only trusted workflow
    routes (repository variable, repair-task API, trusted env, authenticated
    provider status API) may authenticate success-authorizing evidence.
    """
    head = require_sha40(head_sha, "head_sha")
    kind = _norm(provenance_kind)
    if kind not in TRUSTED_PROVIDER_PROVENANCE_KINDS:
        raise ReviewGateError("provider_error_untrusted_provenance", kind or "missing")
    if not isinstance(raw, Mapping):
        raise ReviewGateError("provider_error_missing", "provider error must be an object")
    existing = _provenance_mapping(raw)
    if existing is not None:
        existing_kind = _norm(existing.get("kind"))
        if existing_kind in {"candidate.worktree_file", "candidate.committed_artifact"}:
            raise ReviewGateError(
                "provider_error_candidate_controlled",
                existing_kind,
            )
        if existing_kind and existing_kind not in TRUSTED_PROVIDER_PROVENANCE_KINDS:
            raise ReviewGateError("provider_error_untrusted_provenance", existing_kind)
    bound_raw = _norm(
        raw.get("headSha") or (existing.get("headSha") if existing is not None else "")
    )
    if bound_raw:
        bound = require_sha40(bound_raw, "provider_error.headSha")
        if bound != head:
            raise ReviewGateError("provider_error_wrong_head", f"evidence={bound} live={head}")
    if raw.get("verified") is not True:
        raise ReviewGateError("provider_error_unverified", "verified must be true")
    source = _norm(raw.get("source") or raw.get("evidenceSource"))
    if source not in TRUSTED_PROVIDER_SOURCES:
        raise ReviewGateError("provider_error_untrusted_source", source or "missing")
    provider_class = _provider_class(raw)
    if provider_class is None:
        raise ReviewGateError("provider_error_invalid_class", "class missing or unsupported")
    out = dict(raw)
    out["verified"] = True
    out["source"] = source
    out["class"] = provider_class
    out["headSha"] = head
    out["provenance"] = {
        "kind": kind,
        "headSha": head,
        "authenticated": True,
        "evidenceRef": _norm(evidence_ref) or None,
    }
    return out


def provider_error_from_usage_limit_repair_issues(
    issues: Sequence[Any] | None,
    *,
    head_sha: str,
) -> dict[str, Any] | None:
    """Build authenticated provider-error from open usage_limit repair issues.

    Trusted route for ``repair_observer.usage_limit``: GitHub Issues created by
    the repair observer, never candidate-committed JSON files.
    """
    head = require_sha40(head_sha, "head_sha")
    for raw_issue in issues or []:
        if not isinstance(raw_issue, Mapping):
            continue
        body = _norm(raw_issue.get("body"))
        labels = raw_issue.get("labels") or []
        label_names = {
            _norm(item.get("name") if isinstance(item, Mapping) else item) for item in labels
        }
        has_usage = (
            "linktrend-repair-usage-limit" in label_names
            or "failureType: `usage_limit`" in body
            or "failureType:`usage_limit`" in body
            or "- failureType: `usage_limit`" in body
        )
        if not has_usage:
            continue
        if f"headSha: `{head}`" not in body and f"headSha:`{head}`" not in body:
            continue
        if (
            "resolutionState: **resolved**" in body
            or "resolutionState:**resolved**" in body
            or "- resolutionState: **resolved**" in body
        ):
            continue
        issue_number = raw_issue.get("number")
        return authenticate_provider_unavailability_evidence(
            {
                "verified": True,
                "class": "quota",
                "source": "repair_observer.usage_limit",
                "headSha": head,
            },
            provenance_kind="github.repair_task.api",
            head_sha=head,
            evidence_ref=f"issue:{issue_number}" if issue_number is not None else "repair_task",
        )
    return None


def stamp_full_receipt_provenance(
    receipt: Mapping[str, Any] | None,
    *,
    provenance_kind: str,
    head_sha: str,
    evidence_ref: str = "",
) -> dict[str, Any] | None:
    """Attach authenticated Full receipt provenance; reject candidate-controlled kinds."""
    if receipt is None:
        return None
    if not isinstance(receipt, Mapping):
        raise ReviewGateError("invalid_full_receipt", "full receipt must be an object")
    kind = _norm(provenance_kind)
    if kind not in TRUSTED_FULL_RECEIPT_PROVENANCE_KINDS:
        raise ReviewGateError("full_receipt_untrusted_provenance", kind or "missing")
    head = require_sha40(head_sha, "head_sha")
    existing = _provenance_mapping(receipt)
    if existing is not None:
        existing_kind = _norm(existing.get("kind"))
        if existing_kind in {"candidate.worktree_file", "candidate.committed_artifact"}:
            raise ReviewGateError("full_receipt_candidate_controlled", existing_kind)
    out = dict(receipt)
    out["provenance"] = {
        "kind": kind,
        "headSha": head,
        "authenticated": True,
        "evidenceRef": _norm(evidence_ref) or None,
    }
    return out


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def findings_present_from_event_evidence(
    *,
    annotations_count: Any = None,
    check_title: str = "",
    check_details: str = "",
    bugbot_conclusion: str = "",
    provider_findings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Decide findings-present from trustworthy GitHub/Bugbot event evidence.

    Candidate-controlled scripts cannot supply this decision. Free-text alone
    never converts provider failure into gate success; this helper only sets
    ``review-findings`` when structured event/provider evidence shows genuine
    unresolved findings.
    """
    del bugbot_conclusion  # conclusion alone never authorizes findings-present
    reasons: list[str] = []

    count = _positive_int(annotations_count)
    if count is not None:
        reasons.append(f"annotations_count:{count}")

    if provider_findings and isinstance(provider_findings, Mapping):
        if provider_findings.get("verified") is True:
            source = _norm(
                provider_findings.get("source") or provider_findings.get("evidenceSource")
            )
            if source in TRUSTED_FINDINGS_SOURCES:
                if provider_findings.get("findingsPresent") is True:
                    reasons.append(f"verified_provider_findings:{source}")
                findings_count = _positive_int(provider_findings.get("findingsCount"))
                if findings_count is not None:
                    reasons.append(f"verified_provider_findings_count:{findings_count}")

    for label, text in (("title", check_title), ("details", check_details)):
        match = _FINDINGS_COUNT_RE.search(_norm(text))
        if not match:
            continue
        raw_count = match.group(1) or match.group(2)
        findings_count = _positive_int(raw_count)
        if findings_count is not None:
            reasons.append(f"check_run.output.{label}_count:{findings_count}")

    present = bool(reasons)
    return {
        "findingsPresent": present,
        "evidenceSource": "github.check_run.event" if present else None,
        "reasons": reasons,
    }

def _as_check_run_list(check_runs: Any) -> list[Any]:
    if check_runs is None:
        return []
    if isinstance(check_runs, Mapping):
        runs = check_runs.get("check_runs")
        if runs is None:
            return [check_runs]
        if not isinstance(runs, list):
            raise ReviewGateError("invalid_check_runs", "check_runs must be a list")
        return runs
    if isinstance(check_runs, list):
        return check_runs
    raise ReviewGateError("invalid_check_runs", "check_runs must be list or object")


def _as_workflow_run_list(workflow_runs: Any) -> list[Any]:
    if workflow_runs is None:
        return []
    if isinstance(workflow_runs, Mapping):
        runs = workflow_runs.get("workflow_runs")
        if runs is None:
            return [workflow_runs]
        if not isinstance(runs, list):
            raise ReviewGateError("invalid_workflow_runs", "workflow_runs must be a list")
        return runs
    if isinstance(workflow_runs, list):
        return workflow_runs
    raise ReviewGateError("invalid_workflow_runs", "workflow_runs must be list or object")


def _as_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def check_suite_id_from_check_run(check_run: Mapping[str, Any]) -> int | None:
    """Return the GitHub-assigned check_suite id (not attacker-settable on create)."""
    suite = check_run.get("check_suite") if isinstance(check_run.get("check_suite"), Mapping) else {}
    suite_id = _as_int((suite or {}).get("id"))
    if suite_id is not None:
        return suite_id
    return _as_int(check_run.get("check_suite_id") or check_run.get("checkSuiteId"))


def check_run_numeric_id(check_run: Mapping[str, Any]) -> int | None:
    return _as_int(check_run.get("id"))


def workflow_run_id_from_check_run(check_run: Mapping[str, Any]) -> int | None:
    """Parse an Actions workflow run id from check URL fields (advisory only).

    ``details_url`` / attacker-influenced ``html_url`` fragments are controllable on
    Checks API creates and must never be the sole membership proof.
    """
    for key in ("details_url", "html_url"):
        match = _ACTIONS_RUN_ID_RE.search(_norm(check_run.get(key)))
        if match:
            return int(match.group(1))
    return None


def index_workflow_runs_by_id(workflow_runs: Any) -> dict[int, Mapping[str, Any]]:
    indexed: dict[int, Mapping[str, Any]] = {}
    for item in _as_workflow_run_list(workflow_runs):
        if not isinstance(item, Mapping):
            continue
        run_id = _as_int(item.get("id"))
        if run_id is None:
            continue
        indexed[run_id] = item
    return indexed


def index_workflow_runs_by_check_suite_id(
    workflow_runs: Any,
) -> dict[int, Mapping[str, Any]]:
    indexed: dict[int, Mapping[str, Any]] = {}
    for item in _as_workflow_run_list(workflow_runs):
        if not isinstance(item, Mapping):
            continue
        suite_id = _as_int(item.get("check_suite_id") or item.get("checkSuiteId"))
        if suite_id is None:
            continue
        indexed.setdefault(suite_id, item)
    return indexed


def _as_workflow_job_list(workflow_jobs: Any) -> list[Any]:
    if workflow_jobs is None:
        return []
    if isinstance(workflow_jobs, Mapping):
        jobs = workflow_jobs.get("jobs")
        if jobs is None:
            return [workflow_jobs]
        if not isinstance(jobs, list):
            raise ReviewGateError("invalid_workflow_jobs", "jobs must be a list")
        return jobs
    if isinstance(workflow_jobs, list):
        return workflow_jobs
    raise ReviewGateError("invalid_workflow_jobs", "workflow_jobs must be list or object")


def check_run_id_from_job(job: Mapping[str, Any]) -> int | None:
    """Extract the check-run id owned by an Actions job (API-authenticated)."""
    direct = _as_int(job.get("check_run_id") or job.get("checkRunId"))
    if direct is not None:
        return direct
    for key in ("check_run_url", "checkRunUrl", "html_url", "url"):
        match = _CHECK_RUN_ID_RE.search(_norm(job.get(key)))
        if match:
            return int(match.group(1))
    return None


def index_successful_jobs_by_check_run_id(
    workflow_jobs: Any,
) -> dict[int, Mapping[str, Any]]:
    """Map check-run id → successful completed Actions job for membership proofs."""
    indexed: dict[int, Mapping[str, Any]] = {}
    for item in _as_workflow_job_list(workflow_jobs):
        if not isinstance(item, Mapping):
            continue
        status = _lower(item.get("status"))
        if status and status != "completed":
            continue
        if _lower(item.get("conclusion")) != "success":
            continue
        check_id = check_run_id_from_job(item)
        if check_id is None:
            continue
        indexed[check_id] = item
    return indexed


def producer_run_is_successful(workflow_run: Mapping[str, Any]) -> bool:
    status = _lower(workflow_run.get("status"))
    conclusion = _lower(workflow_run.get("conclusion"))
    if status and status != "completed":
        return False
    return conclusion == "success"


def check_output_is_successful(check_run: Mapping[str, Any]) -> bool:
    return _lower(check_run.get("conclusion")) == "success"


def workflow_file_shas_for_path(
    workflow_file_shas: Mapping[str, Any] | None,
    path: str,
    *,
    run_head_sha: str = "",
) -> tuple[str, str]:
    """Return (default_branch_blob_sha, run_head_blob_sha) for a workflow path.

    ``workflow_file_shas[path]`` may include:
    - ``default`` / ``defaultBranch``: Contents API blob SHA on the default branch
    - ``head`` / ``runHead``: single run-head blob SHA (tests / single-run callers)
    - ``byHead`` / ``by_head``: map of commit SHA → workflow blob SHA at that commit
    """
    if not isinstance(workflow_file_shas, Mapping):
        return ("", "")
    entry = workflow_file_shas.get(path)
    if not isinstance(entry, Mapping):
        return ("", "")
    default_sha = _norm(entry.get("default") or entry.get("defaultBranch") or "").lower()
    run_head = _norm(run_head_sha).lower()
    by_head = entry.get("byHead") if "byHead" in entry else entry.get("by_head")
    head_sha = ""
    if run_head and isinstance(by_head, Mapping):
        head_sha = _norm(by_head.get(run_head) or "").lower()
    if not head_sha:
        head_sha = _norm(
            entry.get("head") or entry.get("runHead") or entry.get("headSha") or ""
        ).lower()
    return (default_sha, head_sha)


def trusted_default_branch_workflow_binding(
    *,
    workflow_run: Mapping[str, Any],
    default_branch: str,
    allowed_paths: frozenset[str],
    workflow_file_sha_at_default: str,
    workflow_file_sha_at_run_head: str,
) -> bool:
    """True when the workflow run is bound to an authenticated default-branch producer.

    Candidate code cannot forge this: either the run executed on the protected
    default branch, or the allowlisted workflow file blob at the run head is
    byte-identical to the default-branch blob (PR did not rewrite the producer).
    """
    path = _norm(workflow_run.get("path"))
    if path not in allowed_paths:
        return False
    branch = _norm(default_branch)
    if not branch:
        return False
    default_sha = _norm(workflow_file_sha_at_default).lower()
    if not default_sha:
        return False
    head_branch = _norm(workflow_run.get("head_branch") or workflow_run.get("headBranch"))
    if head_branch == branch:
        return True
    run_head_sha = _norm(workflow_file_sha_at_run_head).lower()
    return bool(run_head_sha) and run_head_sha == default_sha


def resolve_authenticated_workflow_run_for_check(
    check_run: Mapping[str, Any],
    *,
    workflow_runs: Any,
    workflow_jobs: Any = None,
    default_branch: str,
    allowed_paths: frozenset[str],
    workflow_file_shas: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    """Bind a check run to its authenticated producer run via suite + job identity.

    Rejects borrowed ``details_url`` pointers: membership is proven by GitHub-assigned
    ``check_suite.id`` matching ``workflow_run.check_suite_id`` and by a successful
    Actions job whose ``check_run_url`` owns this check-run id. URL fields, when
    present, must agree with that bound run id.
    """
    suite_id = check_suite_id_from_check_run(check_run)
    check_id = check_run_numeric_id(check_run)
    if suite_id is None or check_id is None:
        return None
    if not check_output_is_successful(check_run):
        return None

    by_suite = index_workflow_runs_by_check_suite_id(workflow_runs)
    workflow_run = by_suite.get(suite_id)
    if workflow_run is None:
        return None
    run_id = _as_int(workflow_run.get("id"))
    if run_id is None:
        return None
    if not producer_run_is_successful(workflow_run):
        return None

    # Borrowed/free details_url pointing at a different run is never accepted.
    url_run_id = workflow_run_id_from_check_run(check_run)
    if url_run_id is not None and url_run_id != run_id:
        return None

    jobs_by_check = index_successful_jobs_by_check_run_id(workflow_jobs)
    job = jobs_by_check.get(check_id)
    if job is None:
        return None
    job_run_id = _as_int(job.get("run_id") or job.get("runId"))
    if job_run_id is not None and job_run_id != run_id:
        return None

    path = _norm(workflow_run.get("path"))
    run_commit = _norm(workflow_run.get("head_sha") or workflow_run.get("headSha")).lower()
    default_sha, head_sha = workflow_file_shas_for_path(
        workflow_file_shas,
        path,
        run_head_sha=run_commit,
    )
    if not trusted_default_branch_workflow_binding(
        workflow_run=workflow_run,
        default_branch=default_branch,
        allowed_paths=allowed_paths,
        workflow_file_sha_at_default=default_sha,
        workflow_file_sha_at_run_head=head_sha,
    ):
        return None
    return workflow_run


def build_workflow_file_shas_payload(
    *,
    repository: str,
    default_branch: str,
    workflow_runs: Any,
    trusted_paths: Sequence[str] | None = None,
    contents_sha_lookup: Any | None = None,
) -> dict[str, Any]:
    """Build Contents-API blob SHA map for allowlisted workflow producers.

    ``contents_sha_lookup(path, ref) -> sha`` is injectable for tests; the CLI
    defaults to ``gh api repos/.../contents/...``.
    """
    repo = _norm(repository)
    branch = _norm(default_branch)
    if not repo or not branch:
        raise ReviewGateError("invalid_workflow_file_shas", "repository and default_branch required")
    paths = tuple(trusted_paths or (
        *sorted(TRUSTED_FULL_SUITE_WORKFLOW_PATHS),
        *sorted(TRUSTED_PROVIDER_UNAVAILABILITY_WORKFLOW_PATHS),
    ))
    lookup = contents_sha_lookup
    if lookup is None:
        def lookup(path: str, ref: str) -> str:  # type: ignore[misc]
            return _gh_contents_blob_sha(repo, path, ref)

    runs = _as_workflow_run_list(workflow_runs)
    out: dict[str, Any] = {}
    for path in paths:
        default_sha = _norm(lookup(path, branch)).lower()
        by_head: dict[str, str] = {}
        for run in runs:
            if not isinstance(run, Mapping):
                continue
            if _norm(run.get("path")) != path:
                continue
            head = _norm(run.get("head_sha") or run.get("headSha")).lower()
            if not head or head in by_head:
                continue
            by_head[head] = _norm(lookup(path, head)).lower()
        out[path] = {"default": default_sha, "byHead": by_head}
    return out


def _gh_contents_blob_sha(repository: str, path: str, ref: str) -> str:
    import subprocess
    import urllib.parse

    if not path or not ref:
        return ""
    encoded = urllib.parse.quote(path, safe="/")
    url = (
        f"repos/{repository}/contents/{encoded}"
        f"?ref={urllib.parse.quote(ref, safe='')}"
    )
    proc = subprocess.run(
        ["gh", "api", url, "--jq", ".sha"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ""
    return _norm(proc.stdout).lower()


def build_workflow_jobs_payload(
    *,
    repository: str,
    workflow_runs: Any,
    jobs_lookup: Any | None = None,
) -> dict[str, Any]:
    """Fetch Actions jobs for workflow runs (check-run membership proofs).

    ``jobs_lookup(run_id) -> list[job]`` is injectable for tests; CLI uses ``gh api``.
    """
    repo = _norm(repository)
    if not repo:
        raise ReviewGateError("invalid_workflow_jobs", "repository required")
    lookup = jobs_lookup
    if lookup is None:
        def lookup(run_id: int) -> list[Any]:  # type: ignore[misc]
            return _gh_workflow_jobs(repo, run_id)

    jobs: list[Any] = []
    seen_runs: set[int] = set()
    for run in _as_workflow_run_list(workflow_runs):
        if not isinstance(run, Mapping):
            continue
        run_id = _as_int(run.get("id"))
        if run_id is None or run_id in seen_runs:
            continue
        seen_runs.add(run_id)
        batch = lookup(run_id)
        if not isinstance(batch, list):
            raise ReviewGateError("invalid_workflow_jobs", "jobs_lookup must return a list")
        jobs.extend(batch)
    return {"jobs": jobs}


def _gh_workflow_jobs(repository: str, run_id: int) -> list[Any]:
    import subprocess

    proc = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repository}/actions/runs/{run_id}/jobs?per_page=100",
            "--jq",
            ".jobs",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return []
    try:
        payload = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def extract_trusted_provider_evidence_from_check_runs(
    check_runs: Any,
    *,
    head_sha: str,
    default_branch: str = "",
    workflow_runs: Any = None,
    workflow_jobs: Any = None,
    workflow_file_shas: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Load provider-unavailability evidence only from default-branch-bound checks."""
    head = require_sha40(head_sha, "head_sha")
    if not _norm(default_branch):
        return None
    for item in _as_check_run_list(check_runs):
        if not isinstance(item, Mapping):
            continue
        name = _norm(item.get("name"))
        if name not in TRUSTED_PROVIDER_UNAVAILABILITY_CHECK_NAMES:
            continue
        app = item.get("app") if isinstance(item.get("app"), Mapping) else {}
        slug = _lower((app or {}).get("slug"))
        if slug not in TRUSTED_CHECK_APP_SLUGS:
            continue
        item_head = _norm(item.get("head_sha") or item.get("headSha")).lower()
        if item_head != head:
            continue
        workflow_run = resolve_authenticated_workflow_run_for_check(
            item,
            workflow_runs=workflow_runs,
            workflow_jobs=workflow_jobs,
            default_branch=default_branch,
            allowed_paths=TRUSTED_PROVIDER_UNAVAILABILITY_WORKFLOW_PATHS,
            workflow_file_shas=workflow_file_shas,
        )
        if workflow_run is None:
            continue
        run_head = _norm(workflow_run.get("head_sha") or workflow_run.get("headSha")).lower()
        if run_head != head:
            continue
        summary = _norm(
            item.get("outputSummary")
            or ((item.get("output") or {}) if isinstance(item.get("output"), Mapping) else {}).get(
                "summary"
            )
            or item.get("summary")
            or ""
        )
        if not summary:
            continue
        try:
            payload = json.loads(summary)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, Mapping):
            continue
        if verified_provider_unavailability(
            payload,
            evidence_channel=EVIDENCE_CHANNEL_GITHUB_CHECK_RUN,
        ):
            return {
                "providerError": dict(payload),
                "evidenceChannel": EVIDENCE_CHANNEL_GITHUB_CHECK_RUN,
                "workflowPath": _norm(workflow_run.get("path")),
                "workflowRunId": int(workflow_run.get("id")),
                "checkRunId": int(item.get("id")),
                "checkSuiteId": int(
                    check_suite_id_from_check_run(item) or 0
                ),
            }
    return None


def extract_trusted_full_receipt_from_check_runs(
    check_runs: Any,
    *,
    head_sha: str,
    default_branch: str = "",
    workflow_runs: Any = None,
    workflow_jobs: Any = None,
    workflow_file_shas: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Load Full Suite success evidence only from default-branch-bound checks."""
    head = require_sha40(head_sha, "head_sha")
    if not _norm(default_branch):
        return None
    for item in _as_check_run_list(check_runs):
        if not isinstance(item, Mapping):
            continue
        name = _norm(item.get("name") or item.get("context"))
        if name not in {FULL_SUITE_CONTEXT, "full", "full-gate"}:
            continue
        app = item.get("app") if isinstance(item.get("app"), Mapping) else {}
        slug = _lower((app or {}).get("slug")) if app else ""
        if slug not in TRUSTED_CHECK_APP_SLUGS:
            continue
        item_head = _norm(item.get("head_sha") or item.get("headSha")).lower()
        if item_head != head:
            continue
        workflow_run = resolve_authenticated_workflow_run_for_check(
            item,
            workflow_runs=workflow_runs,
            workflow_jobs=workflow_jobs,
            default_branch=default_branch,
            allowed_paths=TRUSTED_FULL_SUITE_WORKFLOW_PATHS,
            workflow_file_shas=workflow_file_shas,
        )
        if workflow_run is None:
            continue
        # Full suite producer must evaluate the exact candidate head.
        run_head = _norm(workflow_run.get("head_sha") or workflow_run.get("headSha")).lower()
        if run_head != head:
            continue
        raw = {
            "name": name or FULL_SUITE_CONTEXT,
            "headSha": item.get("head_sha") or item.get("headSha") or "",
            "status": item.get("conclusion") or item.get("status") or "",
            "outputSummary": (
                item.get("outputSummary")
                or (
                    (item.get("output") or {}).get("summary")
                    if isinstance(item.get("output"), Mapping)
                    else ""
                )
                or item.get("summary")
                or ""
            ),
            "gitTree": item.get("gitTree") or item.get("gitTreeSha") or "",
        }
        # Preserve nested candidateIdentity when a check/output embeds a FullSuiteReceipt.
        if isinstance(item.get("candidateIdentity"), Mapping):
            raw["candidateIdentity"] = dict(item["candidateIdentity"])
        elif isinstance(item.get("output"), Mapping) and isinstance(
            item["output"].get("candidateIdentity"), Mapping
        ):
            raw["candidateIdentity"] = dict(item["output"]["candidateIdentity"])
        normalized = normalize_full_receipt_payload(raw)
        if not normalized:
            continue
        receipt_head = _norm(normalized.get("headSha")).lower()
        if receipt_head and receipt_head != head:
            continue
        return {
            "receipt": normalized,
            "evidenceChannel": EVIDENCE_CHANNEL_GITHUB_CHECK_RUN,
            "workflowPath": _norm(workflow_run.get("path")),
            "workflowRunId": int(workflow_run.get("id")),
            "checkRunId": int(item.get("id")),
            "checkSuiteId": int(check_suite_id_from_check_run(item) or 0),
        }
    return None


def count_infrastructure_attempts(markers: Sequence[str] | None, *, head_sha: str) -> int:
    """Count only infrastructure-retry markers for the exact candidate head."""
    head = require_sha40(head_sha, "head_sha")
    needle = f"{INFRA_ATTEMPT_MARKER_PREFIX} {head}"
    count = 0
    for raw in markers or []:
        text = _norm(raw)
        if needle in text:
            count += 1
    return count


def founder_alert_marker(head_sha: str) -> str:
    return f"{FOUNDER_ALERT_MARKER_PREFIX} {require_sha40(head_sha)} -->"


def infrastructure_attempt_marker(head_sha: str, attempt: int) -> str:
    return f"{INFRA_ATTEMPT_MARKER_PREFIX} {require_sha40(head_sha)}:{int(attempt)} -->"


def fallback_request_marker(head_sha: str) -> str:
    return f"{FALLBACK_REQUEST_MARKER_PREFIX} {require_sha40(head_sha)} -->"


def build_durable_founder_alert(classification: Classification) -> dict[str, Any]:
    """Build a durable, sanitized founder-alert payload with dedupe marker."""
    if not classification.alertFounder or not classification.sanitizedAlert:
        raise ReviewGateError("founder_alert_not_required", classification.outcome)
    marker = founder_alert_marker(classification.headSha)
    title = (
        f"[Linktrend Review Gate] Bugbot unavailable "
        f"{classification.repository}@{classification.headSha[:12]}"
    )
    body = (
        f"{marker}\n"
        f"{classification.sanitizedAlert}\n\n"
        f"outcome={classification.outcome}\n"
        f"providerClass={classification.providerClass or 'none'}\n"
        f"headSha={classification.headSha}\n"
        f"gitTree={classification.gitTree}\n"
        "This is not a Bugbot pass.\n"
    )
    return {
        "required": True,
        "marker": marker,
        "title": title,
        "body": body,
        "headSha": classification.headSha,
        "dedupeKey": marker,
    }


def flatten_gh_slurp_pages(pages: Any) -> list[Any]:
    """Flatten ``gh api --paginate --slurp`` output into one item list.

    Empty slurps (``[]``), a single page, and multiple pages must all yield one
    deterministic list. Non-list roots or non-list pages fail closed.
    """
    if pages is None:
        raise ReviewGateError("paginated_response_invalid", "slurp payload is null")
    if isinstance(pages, str):
        text = pages.strip()
        if not text:
            raise ReviewGateError("paginated_response_invalid", "slurp payload is empty")
        try:
            pages = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ReviewGateError("paginated_response_invalid", "slurp JSON is malformed") from exc
    if not isinstance(pages, list):
        raise ReviewGateError("paginated_response_invalid", "slurp root must be a JSON array")
    items: list[Any] = []
    for index, page in enumerate(pages):
        if not isinstance(page, list):
            raise ReviewGateError(
                "paginated_response_invalid",
                f"page {index} must be a JSON array",
            )
        items.extend(page)
    return items


def comment_bodies_from_slurp(pages: Any) -> list[str]:
    """Extract comment bodies from paginated/slurped comment pages."""
    bodies: list[str] = []
    for item in flatten_gh_slurp_pages(pages):
        if not isinstance(item, Mapping):
            raise ReviewGateError("paginated_response_invalid", "comment page item must be object")
        bodies.append(str(item.get("body") or ""))
    return bodies


def issue_bodies_from_slurp(pages: Any) -> list[str]:
    """Extract non-PR issue bodies from paginated/slurped issue pages."""
    bodies: list[str] = []
    for item in flatten_gh_slurp_pages(pages):
        if not isinstance(item, Mapping):
            raise ReviewGateError("paginated_response_invalid", "issue page item must be object")
        if "pull_request" in item:
            continue
        bodies.append(str(item.get("body") or ""))
    return bodies


def founder_alert_already_recorded(existing_bodies: Sequence[str], *, head_sha: str) -> bool:
    """Return True when a prior founder-alert issue body already carries the marker."""
    marker = founder_alert_marker(head_sha)
    return any(marker in _norm(body) for body in existing_bodies or [])


def decide_founder_alert_publish(
    *,
    alert_required: bool,
    issue_bodies: Sequence[str] | None,
    bodies_readable: bool,
    head_sha: str,
) -> dict[str, Any]:
    """Decide whether to create a founder-alert issue.

    Dedupe inspects prior alert **issue bodies** only. If dedupe state cannot be
    read, fail closed.
    """
    if not alert_required:
        return {"publish": False, "reason": "not_required"}
    if not bodies_readable:
        raise ReviewGateError(
            "founder_alert_dedupe_unreadable",
            "cannot read prior founder-alert issue bodies",
        )
    marker = founder_alert_marker(head_sha)
    if founder_alert_already_recorded(issue_bodies or [], head_sha=head_sha):
        return {"publish": False, "reason": "already_recorded", "marker": marker}
    return {"publish": True, "reason": "create", "marker": marker}


def simulate_repeated_founder_alert_events(
    *,
    alert_required: bool,
    head_sha: str,
    prior_issue_bodies: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Workflow-path proof: repeated events create at most one durable alert."""
    bodies = list(prior_issue_bodies or [])
    created = 0
    for _ in range(2):
        decision = decide_founder_alert_publish(
            alert_required=alert_required,
            issue_bodies=bodies,
            bodies_readable=True,
            head_sha=head_sha,
        )
        if decision.get("publish"):
            created += 1
            bodies.append(f"{decision['marker']}\nsimulated durable founder alert\n")
    return {"created": created, "bodies": bodies, "marker": founder_alert_marker(head_sha)}


def normalize_full_receipt_payload(raw: Any) -> dict[str, Any] | None:
    """Normalize Full check/receipt JSON without injecting the live tree.

    Receipt ``gitTree`` must come from the Full receipt/check itself (flat
    fields, ``candidateIdentity.gitTree`` / legacy ``gitTreeSha``, or embedded
    summary text). SchemaVersion 2 FullSuiteReceipt uses ``gitTree``; older
    callers may still emit ``gitTreeSha``. Never invent tree from live TREE.
    """
    if raw is None or raw == "" or raw == "null":
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text or text == "null":
            return None
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ReviewGateError("invalid_full_receipt", "receipt JSON is malformed") from exc
        return normalize_full_receipt_payload(loaded)
    if not isinstance(raw, Mapping):
        raise ReviewGateError("invalid_full_receipt", "full receipt must be an object")

    candidate = raw.get("candidateIdentity")
    head = _norm(raw.get("headSha") or raw.get("head") or "")
    # Never accept a caller-supplied live tree overwrite here — only receipt fields.
    # Top-level: prefer canonical gitTree, then legacy gitTreeSha / tree aliases.
    tree = _norm(raw.get("gitTree") or raw.get("gitTreeSha") or raw.get("tree") or "")
    if isinstance(candidate, Mapping):
        head = head or _norm(candidate.get("sourceSha") or candidate.get("headCommit") or "")
        # candidateIdentity: prefer schema-canonical gitTree, then legacy gitTreeSha.
        tree = tree or _norm(candidate.get("gitTree") or candidate.get("gitTreeSha") or "")
    summary = _norm(
        raw.get("outputSummary")
        or raw.get("summary")
        or ((raw.get("output") or {}) if isinstance(raw.get("output"), Mapping) else {}).get("summary")
        or ""
    )
    if not tree:
        match = re.search(r"\b(?:gitTree|gitTreeSha)=([0-9a-f]{40})\b", summary)
        if match:
            tree = match.group(1)
    if not head:
        match = re.search(r"\bhead=([0-9a-f]{40})\b", summary)
        if match:
            head = match.group(1)
    status = _norm(raw.get("status") or raw.get("conclusion") or "")
    name = _norm(raw.get("name") or raw.get("context") or FULL_SUITE_CONTEXT)
    provenance = _provenance_mapping(raw)
    payload: dict[str, Any] = {
        "name": name or FULL_SUITE_CONTEXT,
        "headSha": head,
        "gitTree": tree,
        "status": status,
    }
    if provenance is not None:
        payload["provenance"] = dict(provenance)
    return payload


def overlay_retained_full_suite_receipt(
    extracted: Mapping[str, Any] | None,
    retained_receipt: Any,
) -> dict[str, Any] | None:
    """Fill producer-bound extract tree/head from a retained FullSuiteReceipt.

    GitHub Actions job checks often have empty ``output.summary``, so extract
    alone cannot recover ``gitTree``. The retained artifact from the same
    producer-bound workflow run carries schemaVersion 2
    ``candidateIdentity.gitTree``. Candidate worktree files must never be
    passed here. Live TREE is never injected.
    """
    if extracted is None:
        return None
    if not isinstance(extracted, Mapping):
        raise ReviewGateError("invalid_full_receipt", "extract payload must be an object")
    bound_receipt = extracted.get("receipt")
    if not isinstance(bound_receipt, Mapping):
        raise ReviewGateError("invalid_full_receipt", "extract receipt missing")
    retained = normalize_full_receipt_payload(retained_receipt)
    if not retained:
        raise ReviewGateError("full_receipt_missing", "retained Full receipt required")
    bound_head = _norm(bound_receipt.get("headSha")).lower()
    retained_head = _norm(retained.get("headSha")).lower()
    if bound_head and retained_head and bound_head != retained_head:
        raise ReviewGateError(
            "full_receipt_wrong_head",
            f"retained={retained_head} extract={bound_head}",
        )
    retained_tree = _norm(retained.get("gitTree"))
    if not retained_tree:
        raise ReviewGateError(
            "full_receipt_missing_tree",
            "retained receipt gitTree must come from Full receipt, not live TREE",
        )
    # Prefer non-empty extract fields; fill gaps from retained schema v2 receipt.
    merged = dict(bound_receipt)
    merged["headSha"] = bound_head or retained_head
    extract_tree = _norm(bound_receipt.get("gitTree"))
    if extract_tree and retained_tree and extract_tree.lower() != retained_tree.lower():
        raise ReviewGateError(
            "full_receipt_wrong_tree",
            f"retained={retained_tree} extract={extract_tree}",
        )
    merged["gitTree"] = extract_tree or retained_tree
    merged["status"] = _norm(bound_receipt.get("status")) or _norm(retained.get("status"))
    merged["name"] = _norm(bound_receipt.get("name")) or _norm(retained.get("name")) or FULL_SUITE_CONTEXT
    if "provenance" in bound_receipt and isinstance(bound_receipt.get("provenance"), Mapping):
        merged["provenance"] = dict(bound_receipt["provenance"])
    elif isinstance(retained.get("provenance"), Mapping):
        merged["provenance"] = dict(retained["provenance"])
    out = dict(extracted)
    out["receipt"] = merged
    return out


def require_full_receipt_for_gate_success(
    *,
    gate_success: bool,
    full_receipt: Mapping[str, Any] | None,
    head_sha: str,
    git_tree: str,
    evidence_channel: str = "",
) -> None:
    """Successful managed gate publish requires an exact-head Full receipt/check.

    The receipt-provided ``gitTree`` is preserved and compared independently to
    the live exact tree. Callers must never overwrite receipt tree with live TREE.
    Trust is established by either a loader-assigned ``evidence_channel``
    (``github_check_run``) or authenticated Full receipt ``provenance``.
    Candidate-controlled repository files never authorize success.
    """
    if not gate_success:
        return
    head = require_sha40(head_sha, "head_sha")
    live_tree = require_sha40(git_tree, "git_tree")
    normalized = normalize_full_receipt_payload(full_receipt)
    if not normalized:
        raise ReviewGateError("full_receipt_missing", "successful gate requires Full receipt")

    channel = _norm(evidence_channel)
    channel_ok = channel in TRUSTED_FULL_RECEIPT_CHANNELS
    provenance = _provenance_mapping(normalized)
    provenance_ok = False
    if provenance is not None:
        provenance_kind = _norm(provenance.get("kind"))
        provenance_ok = (
            provenance_kind in TRUSTED_FULL_RECEIPT_PROVENANCE_KINDS
            and provenance.get("authenticated") is True
        )
    if not channel_ok and not provenance_ok:
        if channel:
            raise ReviewGateError(
                "full_receipt_untrusted_channel",
                f"channel={channel}; provenance missing/unauthenticated; "
                "candidate files cannot authorize success",
            )
        raise ReviewGateError(
            "full_receipt_untrusted_provenance",
            "successful gate requires authenticated Full receipt provenance",
        )

    receipt_head_raw = _norm(normalized.get("headSha"))
    receipt_tree_raw = _norm(normalized.get("gitTree"))
    if not receipt_head_raw:
        raise ReviewGateError("full_receipt_missing_head", "receipt headSha missing")
    if not receipt_tree_raw:
        raise ReviewGateError(
            "full_receipt_missing_tree",
            "receipt gitTree must come from Full receipt, not live TREE",
        )
    receipt_head = require_sha40(receipt_head_raw, "full_receipt.headSha")
    receipt_tree = require_sha40(receipt_tree_raw, "full_receipt.gitTree")
    status = _lower(normalized.get("status"))
    context = _norm(normalized.get("name") or FULL_SUITE_CONTEXT)
    if context not in {FULL_SUITE_CONTEXT, "full", "full-gate", "Linktrend Full Suite"}:
        raise ReviewGateError("full_receipt_wrong_context", context)
    if receipt_head != head:
        raise ReviewGateError("full_receipt_wrong_head", f"receipt={receipt_head} live={head}")
    if receipt_tree != live_tree:
        raise ReviewGateError(
            "full_receipt_wrong_tree",
            f"receipt={receipt_tree} live={live_tree}",
        )
    if status not in {"success", "passed"}:
        raise ReviewGateError("full_receipt_not_success", status or "missing")


def build_fallback_request_comment(
    *,
    fallback: Mapping[str, Any],
    head_sha: str,
) -> dict[str, Any]:
    if not fallback.get("requested"):
        return {"posted": False, "reason": fallback.get("reason") or "not_requested"}
    marker = fallback_request_marker(head_sha)
    reviewer = _norm(fallback.get("reviewerActor"))
    body = (
        f"{marker}\n"
        f"Linktrend Review Gate advisory-unavailable: requesting independent fallback review "
        f"from `{reviewer}` for exact head `{require_sha40(head_sha)}`.\n"
        "Implementer self-review is rejected.\n"
    )
    return {"posted": True, "marker": marker, "body": body, "reviewerActor": reviewer}


def classify_bugbot_result(
    *,
    repository: str,
    head_sha: str,
    git_tree: str,
    pull_request: int | None,
    bugbot_state: str,
    bugbot_conclusion: str | None = None,
    findings_present: bool = False,
    annotations_count: int | None = None,
    provider_error: Mapping[str, Any] | None = None,
    provider_evidence_channel: str = "",
    infrastructure_attempts: int = 1,
    result_head_sha: str | None = None,
    malformed: bool = False,
    forged: bool = False,
    missing: bool = False,
) -> Classification:
    """Classify one Bugbot provider observation into a managed outcome."""
    repo = _norm(repository)
    if not repo or "/" not in repo:
        raise ReviewGateError("invalid_repository", repository)
    head = require_sha40(head_sha, "head_sha")
    tree = require_sha40(git_tree, "git_tree")
    if infrastructure_attempts < 0:
        raise ReviewGateError("invalid_attempts", "attempts must be >= 0")
    has_findings = structured_bugbot_findings_present(
        annotations_count=annotations_count,
        bugbot_conclusion=bugbot_conclusion,
        findings_present=findings_present,
    )

    if missing or malformed or forged:
        return Classification(
            outcome=OUTCOME_UNKNOWN,
            gateSuccess=False,
            bugbotPassedClaim=False,
            alertFounder=False,
            detail="missing_malformed_or_forged_result",
            headSha=head,
            gitTree=tree,
            repository=repo,
            pullRequest=pull_request,
            infrastructureAttempts=infrastructure_attempts,
            providerClass=None,
            sanitizedAlert=None,
        )

    if result_head_sha is not None:
        result_head = require_sha40(result_head_sha, "result_head_sha")
        if result_head != head:
            return Classification(
                outcome=OUTCOME_UNKNOWN,
                gateSuccess=False,
                bugbotPassedClaim=False,
                alertFounder=False,
                detail="wrong_head_result",
                headSha=head,
                gitTree=tree,
                repository=repo,
                pullRequest=pull_request,
                infrastructureAttempts=infrastructure_attempts,
                providerClass=None,
                sanitizedAlert=None,
            )

    state = _lower(bugbot_state)
    conclusion = _lower(bugbot_conclusion) if bugbot_conclusion is not None else ""
    # Unverified / heuristic / candidate-file provider payloads never authorize advisory success.
    # Channel/provenance are assigned by the trusted loader — ignore channel keys inside JSON.
    # Untrusted verified claims are ignored so real Bugbot failure/neutral conclusions stand
    # (#330 planted-source adversarial); they never rewrite outcomes into advisory success.
    provider = verified_provider_unavailability(
        provider_error,
        evidence_channel=provider_evidence_channel,
    )
    if provider_error and provider is None:
        provider = None

    if state in {"pending", "queued", "in_progress"}:
        return Classification(
            outcome=OUTCOME_UNKNOWN,
            gateSuccess=False,
            bugbotPassedClaim=False,
            alertFounder=False,
            detail="provider_still_running",
            headSha=head,
            gitTree=tree,
            repository=repo,
            pullRequest=pull_request,
            infrastructureAttempts=infrastructure_attempts,
            providerClass=None,
            sanitizedAlert=None,
        )

    if has_findings:
        return Classification(
            outcome=OUTCOME_FINDINGS,
            gateSuccess=False,
            bugbotPassedClaim=False,
            alertFounder=False,
            detail="genuine_unresolved_findings",
            headSha=head,
            gitTree=tree,
            repository=repo,
            pullRequest=pull_request,
            infrastructureAttempts=infrastructure_attempts,
            providerClass=None,
            sanitizedAlert=None,
        )

    if provider is not None:
        # Infrastructure retries are counted only on verified-unavailability attempts.
        reject_third_infrastructure_attempt(infrastructure_attempts)
        alert = (
            f"Bugbot provider unavailable ({provider}) for {repo}"
            f"@{head[:12]}; Linktrend Review Gate advisory-unavailable"
        )
        return Classification(
            outcome=OUTCOME_ADVISORY,
            gateSuccess=True,
            bugbotPassedClaim=False,
            alertFounder=True,
            detail=f"verified_provider_unavailable:{provider}",
            headSha=head,
            gitTree=tree,
            repository=repo,
            pullRequest=pull_request,
            infrastructureAttempts=infrastructure_attempts,
            providerClass=provider,
            sanitizedAlert=alert,
        )

    # Neutral alone is never advisory-unavailable.
    if conclusion == "neutral" or state == "neutral":
        return Classification(
            outcome=OUTCOME_UNKNOWN,
            gateSuccess=False,
            bugbotPassedClaim=False,
            alertFounder=False,
            detail="neutral_without_verified_provider_error",
            headSha=head,
            gitTree=tree,
            repository=repo,
            pullRequest=pull_request,
            infrastructureAttempts=infrastructure_attempts,
            providerClass=None,
            sanitizedAlert=None,
        )

    if state in {"success", "completed"} and conclusion in {"", "success"}:
        return Classification(
            outcome=OUTCOME_PASSED,
            gateSuccess=True,
            bugbotPassedClaim=True,
            alertFounder=False,
            detail="exact_head_bugbot_clean",
            headSha=head,
            gitTree=tree,
            repository=repo,
            pullRequest=pull_request,
            infrastructureAttempts=infrastructure_attempts,
            providerClass=None,
            sanitizedAlert=None,
        )

    if state in {"failure", "failed", "error", "cancelled", "timed_out"} or conclusion in {
        "failure",
        "cancelled",
        "timed_out",
    }:
        # conclusion=failure never becomes gate success without verified unavailability above.
        # action_required is handled as structured findings above (never a pass).
        return Classification(
            outcome=OUTCOME_FAILED,
            gateSuccess=False,
            bugbotPassedClaim=False,
            alertFounder=False,
            detail=f"provider_review_or_policy_failure:{state or conclusion}",
            headSha=head,
            gitTree=tree,
            repository=repo,
            pullRequest=pull_request,
            infrastructureAttempts=infrastructure_attempts,
            providerClass=None,
            sanitizedAlert=None,
        )

    return Classification(
        outcome=OUTCOME_UNKNOWN,
        gateSuccess=False,
        bugbotPassedClaim=False,
        alertFounder=False,
        detail=f"ambiguous_provider_result:{state}:{conclusion}",
        headSha=head,
        gitTree=tree,
        repository=repo,
        pullRequest=pull_request,
        infrastructureAttempts=infrastructure_attempts,
        providerClass=None,
        sanitizedAlert=None,
    )


def gate_commit_status(classification: Classification) -> dict[str, str]:
    """Map classification to an honest named commit-status payload."""
    if classification.outcome == OUTCOME_ADVISORY:
        description = "advisory-unavailable (not a Bugbot pass)"
    elif classification.outcome == OUTCOME_PASSED:
        description = "review-passed"
    else:
        description = classification.outcome
    return {
        "context": REVIEW_GATE_CONTEXT,
        "state": "success" if classification.gateSuccess else "failure",
        "description": description[:140],
    }


def migrated_required_contexts(contexts: Sequence[str]) -> list[str]:
    """Replace raw Bugbot required contexts with the managed review gate."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in contexts:
        name = REVIEW_GATE_CONTEXT if _norm(raw) == RAW_BUGBOT_CONTEXT else _norm(raw)
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _load_json_arg(raw: str) -> Any:
    if raw == "-":
        return json.load(sys.stdin)
    # Prefer existing file paths over inline JSON (workflow ARG_MAX safety).
    if raw and os.path.isfile(raw):
        with open(raw, encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    c = sub.add_parser("classify", help="Classify one Bugbot provider result")
    c.add_argument("--repository", required=True)
    c.add_argument("--head-sha", required=True)
    c.add_argument("--git-tree", required=True)
    c.add_argument("--pull-request", type=int)
    c.add_argument("--bugbot-state", required=True)
    c.add_argument("--bugbot-conclusion", default="")
    c.add_argument("--findings-present", action="store_true")
    c.add_argument(
        "--annotations-count",
        type=int,
        default=None,
        help="GitHub check_run.output.annotations_count (structured findings only)",
    )
    c.add_argument("--provider-error-json", default="")
    c.add_argument(
        "--provider-evidence-channel",
        default="",
        help="Trusted loader channel (never candidate_repository_file)",
    )
    c.add_argument("--infrastructure-attempts", type=int, default=1)
    c.add_argument("--result-head-sha", default="")
    c.add_argument("--missing", action="store_true")
    c.add_argument("--malformed", action="store_true")
    c.add_argument("--forged", action="store_true")


    df = sub.add_parser(
        "detect-findings",
        help="Decide findings-present from trustworthy check_run event evidence",
    )
    df.add_argument("--annotations-count", default="0")
    df.add_argument("--check-title", default="")
    df.add_argument("--check-details", default="")
    df.add_argument("--bugbot-conclusion", default="")
    df.add_argument("--provider-findings-json", default="")

    r = sub.add_parser("require-contexts", help="Validate migrated required contexts")
    r.add_argument("--contexts-json", required=True)
    r.add_argument("--development", action="store_true")

    f = sub.add_parser("fallback", help="Evaluate advisory fallback review routing")
    f.add_argument("--outcome", required=True)
    f.add_argument("--independent-review-configured", action="store_true")
    f.add_argument("--reviewer-actor", required=True)
    f.add_argument("--implementer-actor", required=True)
    f.add_argument("--evidence-head", required=True)
    f.add_argument("--live-head", required=True)

    a = sub.add_parser("approval", help="Evaluate GitHub approval vs technical review")
    a.add_argument("--approving-review-required", action="store_true")
    a.add_argument("--reviewer-login", default="")
    a.add_argument("--comment-author-login", default="")
    a.add_argument("--technical-review-clean", action="store_true")
    a.add_argument("--evidence-head", required=True)
    a.add_argument("--live-head", required=True)
    a.add_argument("--approval-source", default="review", choices=["review", "comment"])

    b = sub.add_parser("assert-full", help="Fail closed when Bugbot precedes Full")
    b.add_argument("--full-suite-status", required=True)

    t = sub.add_parser("assert-attempts", help="Reject a third infrastructure attempt")
    t.add_argument("--attempts", type=int, required=True)

    fr = sub.add_parser("require-full-receipt", help="Require exact Full receipt before gate success")
    fr.add_argument("--gate-success", action="store_true")
    fr.add_argument("--full-receipt-json", required=True)
    fr.add_argument("--head-sha", required=True)
    fr.add_argument("--git-tree", required=True)
    fr.add_argument(
        "--evidence-channel",
        default="",
        help="Trusted Full receipt channel (github_check_run only)",
    )

    nr = sub.add_parser(
        "normalize-full-receipt",
        help="Normalize Full receipt/check JSON without injecting live TREE",
    )
    nr.add_argument("--receipt-json", required=True)
    nr.add_argument(
        "--provenance-kind",
        default="",
        help="Authenticated provenance kind (github.check_runs.api | github.actions.artifact)",
    )
    nr.add_argument("--provenance-head-sha", default="")
    nr.add_argument("--provenance-evidence-ref", default="")

    ape = sub.add_parser(
        "authenticate-provider-error",
        help="Stamp trusted provenance onto verified provider-unavailability evidence",
    )
    ape.add_argument("--provider-error-json", required=True)
    ape.add_argument("--provenance-kind", required=True)
    ape.add_argument("--head-sha", required=True)
    ape.add_argument("--evidence-ref", default="")

    rpe = sub.add_parser(
        "resolve-usage-limit-provider-error",
        help="Resolve authenticated repair_observer.usage_limit evidence from open repair issues",
    )
    rpe.add_argument("--head-sha", required=True)
    rpe.add_argument(
        "--slurp-json",
        required=True,
        help="Paginated issue slurp JSON, or '-' to read stdin",
    )

    ep = sub.add_parser(
        "extract-trusted-provider-evidence",
        help="Extract provider-unavailability evidence from default-branch-bound checks only",
    )
    ep.add_argument("--head-sha", required=True)
    ep.add_argument("--check-runs-json", required=True, help="JSON, file path, or '-' for stdin")
    ep.add_argument("--default-branch", required=True)
    ep.add_argument("--workflow-runs-json", required=True, help="JSON, file path, or '-' for stdin")
    ep.add_argument("--workflow-jobs-json", required=True, help="JSON, file path, or '-' for stdin")
    ep.add_argument(
        "--workflow-file-shas-json",
        required=True,
        help='JSON map path->{default,byHead}, file path, or "-" for stdin',
    )

    ef = sub.add_parser(
        "extract-trusted-full-receipt",
        help="Extract Full Suite receipt from default-branch-bound checks only",
    )
    ef.add_argument("--head-sha", required=True)
    ef.add_argument("--check-runs-json", required=True, help="JSON, file path, or '-' for stdin")
    ef.add_argument("--default-branch", required=True)
    ef.add_argument("--workflow-runs-json", required=True, help="JSON, file path, or '-' for stdin")
    ef.add_argument("--workflow-jobs-json", required=True, help="JSON, file path, or '-' for stdin")
    ef.add_argument(
        "--workflow-file-shas-json",
        required=True,
        help='JSON map path->{default,byHead}, file path, or "-" for stdin',
    )
    ef.add_argument(
        "--retained-receipt-json",
        default="",
        help="Optional producer-bound FullSuiteReceipt JSON (artifact); fills gitTree",
    )

    br = sub.add_parser(
        "overlay-retained-full-receipt",
        help="Overlay retained FullSuiteReceipt onto producer-bound extract (no live TREE)",
    )
    br.add_argument("--extract-json", required=True)
    br.add_argument("--retained-receipt-json", required=True)

    rw = sub.add_parser(
        "resolve-workflow-file-shas",
        help="Resolve Contents API blob SHAs for allowlisted workflow producers",
    )
    rw.add_argument("--repository", required=True)
    rw.add_argument("--default-branch", required=True)
    rw.add_argument("--workflow-runs-json", required=True, help="JSON, file path, or '-' for stdin")
    rw.add_argument(
        "--output",
        default="-",
        help="Write JSON to path, or '-' for stdout (default)",
    )

    rj = sub.add_parser(
        "resolve-workflow-jobs",
        help="Resolve Actions jobs for workflow runs (check-run membership proofs)",
    )
    rj.add_argument("--repository", required=True)
    rj.add_argument("--workflow-runs-json", required=True, help="JSON, file path, or '-' for stdin")
    rj.add_argument(
        "--output",
        default="-",
        help="Write JSON to path, or '-' for stdout (default)",
    )

    fa = sub.add_parser("founder-alert", help="Build durable founder-alert payload")
    fa.add_argument("--classification-json", required=True)

    fd = sub.add_parser(
        "founder-alert-dedupe",
        help="Decide founder-alert publish from prior issue bodies (fail closed)",
    )
    fd.add_argument("--head-sha", required=True)
    fd.add_argument("--issue-bodies-json", required=True)
    fd.add_argument("--alert-required", action="store_true")
    fd.add_argument(
        "--bodies-readable",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="False when issue-body pagination/read failed",
    )

    ci = sub.add_parser("count-infra-attempts", help="Count infrastructure retry markers")
    ci.add_argument("--head-sha", required=True)
    ci.add_argument("--markers-json", required=True)

    fc = sub.add_parser(
        "flatten-comment-bodies",
        help="Flatten gh --paginate --slurp comment pages into one JSON body array",
    )
    fc.add_argument(
        "--slurp-json",
        required=True,
        help="Slurp JSON pages, or '-' to read stdin (never pass large slurps via argv)",
    )

    fi = sub.add_parser(
        "flatten-issue-bodies",
        help="Flatten gh --paginate --slurp issue pages into non-PR body array",
    )
    fi.add_argument(
        "--slurp-json",
        required=True,
        help="Slurp JSON pages, or '-' to read stdin (never pass large slurps via argv)",
    )

    fb = sub.add_parser("fallback-comment", help="Build fallback request comment body")
    fb.add_argument("--fallback-json", required=True)
    fb.add_argument("--head-sha", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "classify":
            provider = json.loads(args.provider_error_json) if args.provider_error_json else None
            result = classify_bugbot_result(
                repository=args.repository,
                head_sha=args.head_sha,
                git_tree=args.git_tree,
                pull_request=args.pull_request,
                bugbot_state=args.bugbot_state,
                bugbot_conclusion=args.bugbot_conclusion or None,
                findings_present=args.findings_present,
                annotations_count=args.annotations_count,
                provider_error=provider,
                provider_evidence_channel=args.provider_evidence_channel,
                infrastructure_attempts=args.infrastructure_attempts,
                result_head_sha=args.result_head_sha or None,
                malformed=args.malformed,
                forged=args.forged,
                missing=args.missing,
            )
            payload = {
                "classification": result.to_dict(),
                "commitStatus": gate_commit_status(result),
                "infraAttemptMarker": (
                    infrastructure_attempt_marker(result.headSha, result.infrastructureAttempts)
                    if result.outcome == OUTCOME_ADVISORY
                    else None
                ),
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.command == "detect-findings":
            provider_findings = (
                json.loads(args.provider_findings_json) if args.provider_findings_json else None
            )
            decision = findings_present_from_event_evidence(
                annotations_count=args.annotations_count,
                check_title=args.check_title,
                check_details=args.check_details,
                bugbot_conclusion=args.bugbot_conclusion,
                provider_findings=provider_findings,
            )
            print(json.dumps(decision, indent=2, sort_keys=True))
            return 0
        if args.command == "authenticate-provider-error":
            raw = json.loads(args.provider_error_json)
            stamped = authenticate_provider_unavailability_evidence(
                raw,
                provenance_kind=args.provenance_kind,
                head_sha=args.head_sha,
                evidence_ref=args.evidence_ref,
            )
            print(json.dumps(stamped, separators=(",", ":"), sort_keys=True))
            return 0
        if args.command == "resolve-usage-limit-provider-error":
            pages = _load_json_arg(args.slurp_json)
            issues = flatten_gh_slurp_pages(pages)
            resolved = provider_error_from_usage_limit_repair_issues(
                issues,
                head_sha=args.head_sha,
            )
            print(json.dumps(resolved, separators=(",", ":"), sort_keys=True))
            return 0
        if args.command == "require-contexts":
            contexts = _load_json_arg(args.contexts_json)
            if not isinstance(contexts, list):
                raise ReviewGateError("invalid_contexts", "contexts-json must be a list")
            migrated = migrated_required_contexts([str(x) for x in contexts])
            if args.development:
                require_review_gate_on_development(migrated)
            else:
                require_no_raw_bugbot_required(migrated)
            print(json.dumps({"contexts": migrated}, indent=2, sort_keys=True))
            return 0
        if args.command == "fallback":
            payload = evaluate_fallback_review(
                outcome=args.outcome,
                independent_review_configured=args.independent_review_configured,
                reviewer_actor=args.reviewer_actor,
                implementer_actor=args.implementer_actor,
                evidence_head=args.evidence_head,
                live_head=args.live_head,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.command == "approval":
            payload = evaluate_github_approval(
                approving_review_required=args.approving_review_required,
                reviewer_login=args.reviewer_login,
                comment_author_login=args.comment_author_login,
                technical_review_clean=args.technical_review_clean,
                evidence_head=args.evidence_head,
                live_head=args.live_head,
                approval_source=args.approval_source,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.command == "assert-full":
            assert_full_suite_allows_bugbot(args.full_suite_status)
            print(json.dumps({"ok": True}, indent=2))
            return 0
        if args.command == "assert-attempts":
            reject_third_infrastructure_attempt(args.attempts)
            print(json.dumps({"ok": True, "attempts": args.attempts}, indent=2))
            return 0
        if args.command == "require-full-receipt":
            receipt = normalize_full_receipt_payload(_load_json_arg(args.full_receipt_json))
            require_full_receipt_for_gate_success(
                gate_success=args.gate_success,
                full_receipt=receipt,
                head_sha=args.head_sha,
                git_tree=args.git_tree,
                evidence_channel=args.evidence_channel,
            )
            print(json.dumps({"ok": True}, indent=2, sort_keys=True))
            return 0
        if args.command == "normalize-full-receipt":
            normalized = normalize_full_receipt_payload(_load_json_arg(args.receipt_json))
            if args.provenance_kind:
                normalized = stamp_full_receipt_provenance(
                    normalized,
                    provenance_kind=args.provenance_kind,
                    head_sha=args.provenance_head_sha or (normalized or {}).get("headSha") or "",
                    evidence_ref=args.provenance_evidence_ref,
                )
            print(json.dumps(normalized, indent=2, sort_keys=True))
            return 0
        if args.command == "extract-trusted-provider-evidence":
            shas = _load_json_arg(args.workflow_file_shas_json)
            if not isinstance(shas, dict):
                raise ReviewGateError("invalid_workflow_file_shas", "must be object")
            payload = extract_trusted_provider_evidence_from_check_runs(
                _load_json_arg(args.check_runs_json),
                head_sha=args.head_sha,
                default_branch=args.default_branch,
                workflow_runs=_load_json_arg(args.workflow_runs_json),
                workflow_jobs=_load_json_arg(args.workflow_jobs_json),
                workflow_file_shas=shas,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.command == "extract-trusted-full-receipt":
            shas = _load_json_arg(args.workflow_file_shas_json)
            if not isinstance(shas, dict):
                raise ReviewGateError("invalid_workflow_file_shas", "must be object")
            payload = extract_trusted_full_receipt_from_check_runs(
                _load_json_arg(args.check_runs_json),
                head_sha=args.head_sha,
                default_branch=args.default_branch,
                workflow_runs=_load_json_arg(args.workflow_runs_json),
                workflow_jobs=_load_json_arg(args.workflow_jobs_json),
                workflow_file_shas=shas,
            )
            retained_raw = _norm(getattr(args, "retained_receipt_json", "") or "")
            if payload is not None and retained_raw:
                payload = overlay_retained_full_suite_receipt(
                    payload,
                    _load_json_arg(retained_raw),
                )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.command == "overlay-retained-full-receipt":
            payload = overlay_retained_full_suite_receipt(
                _load_json_arg(args.extract_json),
                _load_json_arg(args.retained_receipt_json),
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.command == "resolve-workflow-file-shas":
            payload = build_workflow_file_shas_payload(
                repository=args.repository,
                default_branch=args.default_branch,
                workflow_runs=_load_json_arg(args.workflow_runs_json),
            )
            text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
            if args.output == "-":
                sys.stdout.write(text)
            else:
                with open(args.output, "w", encoding="utf-8") as handle:
                    handle.write(text)
            return 0
        if args.command == "resolve-workflow-jobs":
            payload = build_workflow_jobs_payload(
                repository=args.repository,
                workflow_runs=_load_json_arg(args.workflow_runs_json),
            )
            text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
            if args.output == "-":
                sys.stdout.write(text)
            else:
                with open(args.output, "w", encoding="utf-8") as handle:
                    handle.write(text)
            return 0
        if args.command == "founder-alert":
            raw = _load_json_arg(args.classification_json)
            if not isinstance(raw, dict):
                raise ReviewGateError("invalid_classification", "classification-json must be object")
            classification = Classification(
                outcome=str(raw["outcome"]),
                gateSuccess=bool(raw["gateSuccess"]),
                bugbotPassedClaim=bool(raw["bugbotPassedClaim"]),
                alertFounder=bool(raw["alertFounder"]),
                detail=str(raw.get("detail") or ""),
                headSha=str(raw["headSha"]),
                gitTree=str(raw["gitTree"]),
                repository=str(raw["repository"]),
                pullRequest=raw.get("pullRequest"),
                infrastructureAttempts=int(raw.get("infrastructureAttempts") or 0),
                providerClass=raw.get("providerClass"),
                sanitizedAlert=raw.get("sanitizedAlert"),
            )
            print(json.dumps(build_durable_founder_alert(classification), indent=2, sort_keys=True))
            return 0
        if args.command == "founder-alert-dedupe":
            bodies_raw = _load_json_arg(args.issue_bodies_json)
            if not isinstance(bodies_raw, list):
                raise ReviewGateError("invalid_issue_bodies", "issue-bodies-json must be a list")
            decision = decide_founder_alert_publish(
                alert_required=args.alert_required,
                issue_bodies=[str(x) for x in bodies_raw],
                bodies_readable=bool(args.bodies_readable),
                head_sha=args.head_sha,
            )
            print(json.dumps(decision, indent=2, sort_keys=True))
            return 0
        if args.command == "count-infra-attempts":
            markers = _load_json_arg(args.markers_json)
            if not isinstance(markers, list):
                raise ReviewGateError("invalid_markers", "markers-json must be a list")
            count = count_infrastructure_attempts([str(x) for x in markers], head_sha=args.head_sha)
            print(json.dumps({"attempts": count}, indent=2, sort_keys=True))
            return 0
        if args.command == "flatten-comment-bodies":
            bodies = comment_bodies_from_slurp(_load_json_arg(args.slurp_json))
            print(json.dumps(bodies, indent=2, sort_keys=True))
            return 0
        if args.command == "flatten-issue-bodies":
            bodies = issue_bodies_from_slurp(_load_json_arg(args.slurp_json))
            print(json.dumps(bodies, indent=2, sort_keys=True))
            return 0
        if args.command == "fallback-comment":
            fallback = _load_json_arg(args.fallback_json)
            if not isinstance(fallback, dict):
                raise ReviewGateError("invalid_fallback", "fallback-json must be object")
            print(
                json.dumps(
                    build_fallback_request_comment(fallback=fallback, head_sha=args.head_sha),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        raise ReviewGateError("unknown_command", args.command)
    except ReviewGateError as exc:
        print(json.dumps({"error": exc.code, "detail": exc.detail}, indent=2, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
