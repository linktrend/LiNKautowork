#!/usr/bin/env python3
"""Independent-review convergence controller (Update 9 / WP-U09).

Progress-based continuation with no arbitrary fixed terminal cycle cap.
Unattended work pauses after three repair cycles. Recorded founder
``continue until clean`` authority permits additional progressing cycles.
Stop only for repeated unresolved findings, two no-progress cycles, repair
reintroduction, redesign/new authority, infrastructure retry exhaustion, or
an explicit resource limit. Preserve the finding ledger and exact-head
identity. Implementer and reviewer roles stay separate. Reviewer silence
and timeouts are truthful HOLDs, never clean.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

SCHEMA_VERSION = 1
COMPONENT_KIND = "independent_review_convergence"
SESSION_KIND = "review-session"
LEDGER_KIND = "finding-ledger"
MAX_INFRASTRUCTURE_ATTEMPTS = 2
UNATTENDED_CHECKPOINT_CYCLES = 3
TERMINAL_CYCLE_CAP = None
NO_PROGRESS_STALL_STREAK = 2
REPEATED_UNRESOLVED_REPAIR_ATTEMPTS = 2
TOKEN_OVERLAP_THRESHOLD = 0.5
CONTINUE_UNTIL_CLEAN = "continue until clean"
ROLE_IMPLEMENTER = "implementer"
ROLE_REVIEWER = "reviewer"
ROLE_FOUNDER = "founder"
SEVERITIES = ("P1", "P2", "P3")
SEVERITY_RANK = {"P1": 0, "P2": 1, "P3": 2}
BLOCKING_SEVERITIES = frozenset({"P1", "P2"})

CLASS_UNRESOLVED = "unresolved"
CLASS_REPEATED = "repeated"
CLASS_CORRECTED = "corrected"
CLASS_NEWLY_DISCOVERED = "newly_discovered_in_unchanged_scope"
CLASS_INTRODUCED_BY_REPAIR = "introduced_by_repair"

STATUS_IN_PROGRESS = "in_progress"
STATUS_UNATTENDED_CHECKPOINT = "unattended_checkpoint"
STATUS_CONTINUE = "continue"
STATUS_REVIEW_CLEAN = "review_clean"
STATUS_REVIEW_STALLED = "review_stalled"
STATUS_HOLD = "hold"

STALL_REPEATED_UNRESOLVED = "repeated_unresolved_findings"
STALL_NO_PROGRESS = "no_measurable_progress"
STALL_REINTRODUCTION = "repair_reintroduction"
STALL_REDESIGN = "redesign_or_new_authority"
STALL_RESOURCE_LIMIT = "resource_limit_exhausted"
STALL_INFRA_EXHAUSTED = "infrastructure_retry_exhausted"

HOLD_REVIEWER_TIMEOUT = "reviewer_timeout"
HOLD_REVIEWER_SILENCE = "reviewer_silence"
HOLD_MALFORMED_OUTPUT = "malformed_reviewer_output"

SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
WORD_RE = re.compile(r"[a-z0-9]+")
SESSION_FILENAME = "review-session.json"
LEDGER_FILENAME = "finding-ledger.json"
PACKET_FILENAME = "founder-decision-packet.json"


class ConvergenceError(ValueError):
    """Fail-closed independent-review rejection."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


class Clock(Protocol):
    def now(self) -> float: ...


class SystemClock:
    def now(self) -> float:
        return time.time()


class ReviewerAdapter(Protocol):
    def start(self, session: "ReviewSession") -> "ReviewerLease": ...

    def cancel(self, lease: "ReviewerLease") -> None: ...

    def result(self, lease: "ReviewerLease") -> Mapping[str, Any] | None: ...


@dataclass
class Finding:
    fingerprint: str
    severity: str
    paths: list[str]
    statement: str
    evidence: str
    acceptance_test: str
    requires_redesign: bool = False
    requires_new_authority: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "severity": self.severity,
            "paths": list(self.paths),
            "statement": self.statement,
            "evidence": self.evidence,
            "acceptanceTest": self.acceptance_test,
            "requiresRedesign": self.requires_redesign,
            "requiresNewAuthority": self.requires_new_authority,
        }


@dataclass
class LedgerEntry:
    finding: Finding
    classification: str
    first_seen_head: str
    last_seen_head: str
    repair_attempts: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)
    severity_reduced_this_cycle: bool = False

    def to_dict(self) -> dict[str, Any]:
        row = self.finding.to_dict()
        row.update(
            {
                "classification": self.classification,
                "firstSeenHead": self.first_seen_head,
                "lastSeenHead": self.last_seen_head,
                "repairAttempts": self.repair_attempts,
                "history": list(self.history),
            }
        )
        return row


@dataclass
class ReviewerLease:
    lease_id: str
    session_id: str
    head_sha: str
    started_at: float
    status: str = "running"
    wait_seconds: float = 0.0


@dataclass
class RepairBatch:
    batch_id: str
    session_id: str
    head_sha: str
    fingerprints: list[str]
    findings: list[Finding]
    cycle_consumed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "batchId": self.batch_id,
            "sessionId": self.session_id,
            "headSha": self.head_sha,
            "fingerprints": list(self.fingerprints),
            "count": len(self.findings),
            "cycleConsumed": self.cycle_consumed,
        }


@dataclass
class ProgressDecision:
    status: str
    reason: str | None
    continue_authorized: bool
    measurable_progress: bool
    founder_packet_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "continueAuthorized": self.continue_authorized,
            "measurableProgress": self.measurable_progress,
            "founderPacketRequired": self.founder_packet_required,
        }


@dataclass
class ReviewSession:
    session_id: str
    root_session_id: str
    repository: str
    base_sha: str
    candidate_sha: str
    git_tree: str
    scope: list[str]
    reviewer_policy: str
    implementer_actor: str
    reviewer_actor: str
    status: str = STATUS_IN_PROGRESS
    repair_cycle_count: int = 0
    founder_authority: dict[str, Any] | None = None
    resource_limit: dict[str, Any] | None = None
    infrastructure_attempts: int = 0
    infrastructure_head: str | None = None
    live_reviewer: dict[str, Any] | None = None
    full_evidence: dict[str, Any] = field(
        default_factory=lambda: {"valid": False, "headSha": None}
    )
    prior_review: dict[str, Any] = field(
        default_factory=lambda: {"valid": False, "headSha": None}
    )
    require_full_before_review: bool = False
    splits: list[dict[str, Any]] = field(default_factory=list)
    recovery_generation: int = 0
    no_progress_streak: int = 0
    started_at: float = 0.0
    compute_units: float = 0.0
    hold_reason: str | None = None
    stall_reason: str | None = None
    last_batch_id: str | None = None
    last_touched_paths: list[str] = field(default_factory=list)
    last_progress: bool | None = None
    last_evaluated_cycle: int = 0
    preflight_failures: list[dict[str, Any]] = field(default_factory=list)
    infrastructure_failures: list[dict[str, Any]] = field(default_factory=list)
    reviewer_outputs: list[dict[str, Any]] = field(default_factory=list)
    tests: list[dict[str, Any]] = field(default_factory=list)
    pending_batch: RepairBatch | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "kind": SESSION_KIND,
            "sessionId": self.session_id,
            "rootSessionId": self.root_session_id,
            "repository": self.repository,
            "baseSha": self.base_sha,
            "candidateSha": self.candidate_sha,
            "gitTree": self.git_tree,
            "scope": list(self.scope),
            "reviewerPolicy": self.reviewer_policy,
            "implementerActor": self.implementer_actor,
            "reviewerActor": self.reviewer_actor,
            "status": self.status,
            "repairCycleCount": self.repair_cycle_count,
            "unattendedCheckpointCycles": UNATTENDED_CHECKPOINT_CYCLES,
            "terminalCycleCap": TERMINAL_CYCLE_CAP,
            "founderAuthority": self.founder_authority,
            "resourceLimit": self.resource_limit,
            "infrastructureAttempts": self.infrastructure_attempts,
            "infrastructureHead": self.infrastructure_head,
            "liveReviewer": self.live_reviewer,
            "fullEvidence": dict(self.full_evidence),
            "priorReview": dict(self.prior_review),
            "requireFullBeforeReview": self.require_full_before_review,
            "splits": list(self.splits),
            "recoveryGeneration": self.recovery_generation,
            "noProgressStreak": self.no_progress_streak,
            "startedAt": self.started_at,
            "elapsedSeconds": 0,
            "computeUnits": self.compute_units,
            "holdReason": self.hold_reason or "",
            "stallReason": self.stall_reason or "",
            "lastBatchId": self.last_batch_id or "",
            "component": COMPONENT_KIND,
        }


def require_sha(value: str, label: str) -> str:
    text = (value or "").strip().lower()
    if not SHA40_RE.fullmatch(text):
        raise ConvergenceError("invalid_identity", f"{label} must be a 40-char lowercase SHA")
    return text


def normalize_words(text: str) -> list[str]:
    return WORD_RE.findall((text or "").lower())


def token_jaccard(left: str, right: str) -> float:
    a = set(normalize_words(left))
    b = set(normalize_words(right))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def normalize_paths(paths: Sequence[str]) -> list[str]:
    if not isinstance(paths, (list, tuple)):
        return []
    out = []
    for path in paths:
        item = str(path or "").strip().replace("\\", "/")
        if item:
            out.append(item)
    return sorted(set(out))


def require_finding_paths(paths: Any) -> list[str]:
    if not isinstance(paths, list) or not paths:
        raise ConvergenceError(
            HOLD_MALFORMED_OUTPUT,
            "paths must be a nonempty list of nonempty strings",
        )
    out: list[str] = []
    for path in paths:
        if not isinstance(path, str) or not path.strip():
            raise ConvergenceError(
                HOLD_MALFORMED_OUTPUT,
                "paths must be a nonempty list of nonempty strings",
            )
        out.append(path.strip().replace("\\", "/"))
    return sorted(set(out))


def require_touched_paths(paths: Any) -> list[str]:
    if not isinstance(paths, list) or not paths:
        raise ConvergenceError(
            "invalid_touched_paths",
            "touched_paths must be a nonempty list of nonempty strings",
        )
    out: list[str] = []
    for path in paths:
        if not isinstance(path, str) or not path.strip():
            raise ConvergenceError(
                "invalid_touched_paths",
                "touched_paths must be a nonempty list of nonempty strings",
            )
        out.append(path.strip().replace("\\", "/"))
    return sorted(set(out))


def same_finding(left: Finding, right: Finding) -> bool:
    left_fp = (left.fingerprint or "").strip()
    right_fp = (right.fingerprint or "").strip()
    if left_fp and right_fp:
        return left_fp == right_fp
    if set(normalize_paths(left.paths)) != set(normalize_paths(right.paths)):
        return False
    left_norm = " ".join(normalize_words(left.statement))
    right_norm = " ".join(normalize_words(right.statement))
    if left_norm and left_norm == right_norm:
        return True
    if token_jaccard(left.statement, right.statement) >= TOKEN_OVERLAP_THRESHOLD:
        return True
    left_words = set(normalize_words(left.statement))
    right_words = set(normalize_words(right.statement))
    if left_words and right_words:
        contained = len(left_words & right_words) / min(len(left_words), len(right_words))
        if contained >= TOKEN_OVERLAP_THRESHOLD:
            return True
    return False


def severity_is_reduced(previous: str, current: str) -> bool:
    return SEVERITY_RANK.get(current, -1) > SEVERITY_RANK.get(previous, -1)


def parse_finding(raw: Mapping[str, Any]) -> Finding:
    if not isinstance(raw, Mapping):
        raise ConvergenceError(HOLD_MALFORMED_OUTPUT, "finding items must be objects")
    fingerprint = str(raw.get("fingerprint") or "").strip()
    severity = str(raw.get("severity") or "").strip().upper()
    paths = require_finding_paths(raw.get("paths"))
    statement = str(raw.get("statement") or raw.get("defect") or "").strip()
    evidence = str(raw.get("evidence") or "").strip()
    acceptance = str(raw.get("acceptanceTest") or raw.get("acceptance_test") or "").strip()
    if not fingerprint or severity not in SEVERITIES or not paths or not statement:
        raise ConvergenceError(HOLD_MALFORMED_OUTPUT, "finding is missing fingerprint, severity, paths, or statement")
    if not evidence or not acceptance:
        raise ConvergenceError(HOLD_MALFORMED_OUTPUT, "finding is missing evidence or acceptanceTest")
    return Finding(
        fingerprint=fingerprint,
        severity=severity,
        paths=paths,
        statement=statement,
        evidence=evidence,
        acceptance_test=acceptance,
        requires_redesign=bool(raw.get("requiresRedesign") or raw.get("requires_redesign")),
        requires_new_authority=bool(raw.get("requiresNewAuthority") or raw.get("requires_new_authority")),
    )


def ledger_to_dict(session: ReviewSession, entries: Sequence[LedgerEntry]) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": LEDGER_KIND,
        "sessionId": session.session_id,
        "rootSessionId": session.root_session_id,
        "entries": [entry.to_dict() for entry in entries],
        "component": COMPONENT_KIND,
    }


def find_entry(entries: Sequence[LedgerEntry], finding: Finding) -> LedgerEntry | None:
    for entry in entries:
        if same_finding(entry.finding, finding):
            return entry
    return None


def blocking_unresolved(entries: Sequence[LedgerEntry]) -> list[LedgerEntry]:
    return [
        entry
        for entry in entries
        if entry.classification in {CLASS_UNRESOLVED, CLASS_REPEATED, CLASS_NEWLY_DISCOVERED, CLASS_INTRODUCED_BY_REPAIR}
        and entry.finding.severity in BLOCKING_SEVERITIES
    ]


def open_session(
    *,
    repository: str,
    base_sha: str,
    candidate_sha: str,
    git_tree: str,
    scope: Sequence[str],
    reviewer_policy: str,
    implementer_actor: str,
    reviewer_actor: str,
    require_full_before_review: bool = False,
    resource_limit: Mapping[str, Any] | None = None,
    clock: Clock | None = None,
) -> tuple[ReviewSession, list[LedgerEntry]]:
    if not repository or "/" not in repository:
        raise ConvergenceError("invalid_identity", "repository must be owner/name")
    if not (implementer_actor or "").strip() or not (reviewer_actor or "").strip():
        raise ConvergenceError("role_separation", "implementer and reviewer actors are required")
    if implementer_actor.strip() == reviewer_actor.strip():
        raise ConvergenceError("role_separation", "reviewer actor must be independent of the implementer")
    clock = clock or SystemClock()
    identity = "|".join(
        [
            repository.strip(),
            require_sha(base_sha, "baseSha"),
            require_sha(candidate_sha, "candidateSha"),
            require_sha(git_tree, "gitTree"),
            ",".join(normalize_paths(scope)),
            (reviewer_policy or "").strip(),
        ]
    )
    session_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    session = ReviewSession(
        session_id=session_id,
        root_session_id=session_id,
        repository=repository.strip(),
        base_sha=require_sha(base_sha, "baseSha"),
        candidate_sha=require_sha(candidate_sha, "candidateSha"),
        git_tree=require_sha(git_tree, "gitTree"),
        scope=normalize_paths(scope),
        reviewer_policy=(reviewer_policy or "default").strip(),
        implementer_actor=implementer_actor.strip(),
        reviewer_actor=reviewer_actor.strip(),
        require_full_before_review=bool(require_full_before_review),
        resource_limit=dict(resource_limit) if resource_limit else None,
        started_at=clock.now(),
    )
    return session, []


def apply_repository_policy(session: ReviewSession, policy: Mapping[str, Any]) -> None:
    if policy.get("treatCycleCountAsTerminal") or policy.get("terminalCycleCap"):
        raise ConvergenceError(
            "arbitrary_terminal_cycle_cap",
            "repository policy may not replace progress-based continuation with a terminal cycle count",
        )
    if "requireFullBeforeReview" in policy:
        session.require_full_before_review = bool(policy["requireFullBeforeReview"])
    if policy.get("resourceLimit"):
        session.resource_limit = dict(policy["resourceLimit"])


def record_founder_authority(
    session: ReviewSession,
    *,
    owner: str,
    scope: str,
    instruction: str = CONTINUE_UNTIL_CLEAN,
    resource_limit: Mapping[str, Any] | None = None,
    clock: Clock | None = None,
) -> None:
    if instruction != CONTINUE_UNTIL_CLEAN:
        raise ConvergenceError("invalid_authority", "only recorded 'continue until clean' founder authority is accepted")
    if not (owner or "").strip() or not (scope or "").strip():
        raise ConvergenceError("invalid_authority", "founder authority requires owner and scope")
    clock = clock or SystemClock()
    session.founder_authority = {
        "instruction": CONTINUE_UNTIL_CLEAN,
        "scope": scope.strip(),
        "owner": owner.strip(),
        "startedAt": clock.now(),
        "resourceLimit": dict(resource_limit) if resource_limit else session.resource_limit,
    }
    if resource_limit:
        session.resource_limit = dict(resource_limit)
    if session.status == STATUS_UNATTENDED_CHECKPOINT:
        session.status = STATUS_CONTINUE


def _reset_infra_if_head_changed(session: ReviewSession) -> None:
    if session.infrastructure_head != session.candidate_sha:
        session.infrastructure_attempts = 0
        session.infrastructure_head = session.candidate_sha


def record_preflight(
    session: ReviewSession,
    problems: Sequence[Mapping[str, Any]],
    *,
    clock: Clock | None = None,
) -> dict[str, Any]:
    """Aggregate every detectable bundle-safety problem. Failures are not repair cycles."""
    clock = clock or SystemClock()
    _reset_infra_if_head_changed(session)
    aggregated = [dict(item) for item in problems]
    result = {
        "kind": "preflight",
        "headSha": session.candidate_sha,
        "problems": aggregated,
        "passed": not aggregated,
        "consumedRepairCycle": False,
        "attempt": session.infrastructure_attempts + (1 if aggregated else 0),
    }
    if not aggregated:
        return result
    if session.infrastructure_attempts >= MAX_INFRASTRUCTURE_ATTEMPTS:
        _stall(session, STALL_INFRA_EXHAUSTED)
        raise ConvergenceError(
            STALL_INFRA_EXHAUSTED,
            "third unchanged-head infrastructure attempt is rejected",
        )
    session.infrastructure_attempts += 1
    session.preflight_failures.append(
        {"at": clock.now(), "headSha": session.candidate_sha, "problems": aggregated}
    )
    result["attempt"] = session.infrastructure_attempts
    return result


def record_infrastructure_failure(
    session: ReviewSession,
    *,
    kind: str,
    detail: str,
    clock: Clock | None = None,
) -> None:
    clock = clock or SystemClock()
    _reset_infra_if_head_changed(session)
    if session.infrastructure_attempts >= MAX_INFRASTRUCTURE_ATTEMPTS:
        _stall(session, STALL_INFRA_EXHAUSTED)
        raise ConvergenceError(
            STALL_INFRA_EXHAUSTED,
            "third unchanged-head infrastructure attempt is rejected",
        )
    session.infrastructure_attempts += 1
    session.infrastructure_failures.append(
        {"at": clock.now(), "kind": kind, "detail": detail, "headSha": session.candidate_sha}
    )


def start_reviewer(
    session: ReviewSession,
    adapter: ReviewerAdapter,
    *,
    wait_seconds: float,
    clock: Clock | None = None,
) -> ReviewerLease:
    if session.live_reviewer and session.live_reviewer.get("status") == "running":
        raise ConvergenceError("duplicate_reviewer", "one live reviewer process is already running for this exact head")
    clock = clock or SystemClock()
    lease = adapter.start(session)
    lease.wait_seconds = wait_seconds
    lease.started_at = clock.now()
    session.live_reviewer = {
        "leaseId": lease.lease_id,
        "headSha": session.candidate_sha,
        "status": "running",
        "startedAt": lease.started_at,
        "waitSeconds": wait_seconds,
    }
    return lease


def timeout_reviewer(
    session: ReviewSession,
    adapter: ReviewerAdapter,
    lease: ReviewerLease,
    *,
    clock: Clock | None = None,
) -> dict[str, Any]:
    clock = clock or SystemClock()
    adapter.cancel(lease)
    lease.status = "timed_out"
    session.live_reviewer = None
    session.status = STATUS_HOLD
    session.hold_reason = HOLD_REVIEWER_TIMEOUT
    try:
        record_infrastructure_failure(
            session, kind="reviewer_timeout", detail="bounded wait expired", clock=clock
        )
    except ConvergenceError as exc:
        if exc.code != STALL_INFRA_EXHAUSTED:
            raise
        return {
            "status": STATUS_REVIEW_STALLED,
            "reason": STALL_INFRA_EXHAUSTED,
            "clean": False,
            "headSha": session.candidate_sha,
        }
    return {
        "status": STATUS_HOLD,
        "reason": HOLD_REVIEWER_TIMEOUT,
        "clean": False,
        "headSha": session.candidate_sha,
    }


def _require_reviewer_actor(session: ReviewSession, actor: str, role: str) -> None:
    if role != ROLE_REVIEWER:
        raise ConvergenceError("role_separation", "only an independent reviewer may ingest review output")
    if actor.strip() != session.reviewer_actor:
        raise ConvergenceError("role_separation", "reviewer actor does not match the session reviewer")
    if actor.strip() == session.implementer_actor:
        raise ConvergenceError("role_separation", "implementer cannot act as reviewer")


def _hold_malformed(session: ReviewSession, detail: str) -> None:
    session.status = STATUS_HOLD
    session.hold_reason = HOLD_MALFORMED_OUTPUT
    raise ConvergenceError(HOLD_MALFORMED_OUTPUT, detail)


def _require_bound_identity(session: ReviewSession, payload: Mapping[str, Any]) -> None:
    raw_head = payload.get("headSha")
    raw_tree = payload.get("gitTree")
    if not raw_head or not raw_tree:
        raise ConvergenceError("stale_review", "reviewer output must bind exact headSha and gitTree")
    head = require_sha(str(raw_head), "headSha")
    tree = require_sha(str(raw_tree), "gitTree")
    if head != session.candidate_sha or tree != session.git_tree:
        raise ConvergenceError("stale_review", "reviewer output headSha/gitTree do not match the current candidate")


def ingest_review(
    session: ReviewSession,
    entries: list[LedgerEntry],
    payload: Mapping[str, Any] | None,
    *,
    actor: str,
    role: str,
    clock: Clock | None = None,
) -> list[Finding]:
    clock = clock or SystemClock()
    _require_reviewer_actor(session, actor, role)
    if session.status in {STATUS_HOLD, STATUS_REVIEW_STALLED}:
        raise ConvergenceError(
            session.status,
            "ingest_review cannot overwrite a held or stalled exact-head identity",
        )
    if payload is None or payload == {}:
        session.live_reviewer = None
        session.status = STATUS_HOLD
        session.hold_reason = HOLD_REVIEWER_SILENCE
        raise ConvergenceError(HOLD_REVIEWER_SILENCE, "reviewer produced no output; HOLD, not clean")
    _require_bound_identity(session, payload)
    raw_findings = payload.get("findings")
    if raw_findings is None:
        session.live_reviewer = None
        _hold_malformed(session, "reviewer output is missing findings and does not consume a repair cycle")
    if not isinstance(raw_findings, list):
        session.live_reviewer = None
        _hold_malformed(session, "findings must be a list")
    findings: list[Finding] = []
    try:
        for item in raw_findings:
            if not isinstance(item, Mapping):
                raise ConvergenceError(HOLD_MALFORMED_OUTPUT, "finding items must be objects")
            findings.append(parse_finding(item))
    except ConvergenceError as exc:
        if exc.code == HOLD_MALFORMED_OUTPUT:
            session.live_reviewer = None
            _hold_malformed(session, exc.detail)
        raise
    session.live_reviewer = None
    session.reviewer_outputs.append(
        {"at": clock.now(), "headSha": session.candidate_sha, "findingCount": len(findings)}
    )
    session.prior_review = {"valid": True, "headSha": session.candidate_sha}
    _classify_into_ledger(session, entries, findings)
    if session.status in {STATUS_HOLD, STATUS_REVIEW_STALLED}:
        return findings
    if not findings and not blocking_unresolved(entries):
        session.status = STATUS_REVIEW_CLEAN
        session.hold_reason = None
        session.stall_reason = None
    elif session.status not in {STATUS_REVIEW_STALLED, STATUS_HOLD, STATUS_UNATTENDED_CHECKPOINT}:
        session.status = STATUS_IN_PROGRESS
    return findings


def _classify_into_ledger(
    session: ReviewSession,
    entries: list[LedgerEntry],
    findings: Sequence[Finding],
) -> None:
    for entry in entries:
        entry.severity_reduced_this_cycle = False
    seen: list[LedgerEntry] = []
    for finding in findings:
        existing = find_entry(entries, finding)
        if existing is None:
            touched = set(session.last_touched_paths)
            if session.repair_cycle_count == 0:
                classification = CLASS_UNRESOLVED
            elif touched and set(finding.paths) & touched:
                classification = CLASS_INTRODUCED_BY_REPAIR
            else:
                classification = CLASS_NEWLY_DISCOVERED
            entry = LedgerEntry(
                finding=finding,
                classification=classification,
                first_seen_head=session.candidate_sha,
                last_seen_head=session.candidate_sha,
            )
            entries.append(entry)
            seen.append(entry)
            continue
        previous_severity = existing.finding.severity
        existing.severity_reduced_this_cycle = severity_is_reduced(previous_severity, finding.severity)
        if existing.classification == CLASS_CORRECTED:
            existing.classification = CLASS_INTRODUCED_BY_REPAIR
        elif existing.repair_attempts > 0:
            existing.classification = CLASS_REPEATED
        else:
            existing.classification = CLASS_UNRESOLVED
        existing.finding = finding
        existing.last_seen_head = session.candidate_sha
        existing.history.append(
            {
                "headSha": session.candidate_sha,
                "statement": finding.statement,
                "classification": existing.classification,
                "severity": finding.severity,
                "previousSeverity": previous_severity,
            }
        )
        seen.append(existing)
    seen_ids = {id(entry) for entry in seen}
    if session.status in {STATUS_HOLD, STATUS_REVIEW_STALLED}:
        return
    pending = session.pending_batch
    # Absences become corrected only after apply_repair consumed the batch.
    consumable = pending is not None and pending.cycle_consumed
    pending_fps = set(pending.fingerprints) if consumable else set()
    for entry in entries:
        if id(entry) in seen_ids:
            continue
        if entry.classification in {CLASS_UNRESOLVED, CLASS_REPEATED, CLASS_NEWLY_DISCOVERED, CLASS_INTRODUCED_BY_REPAIR}:
            if consumable and entry.finding.fingerprint in pending_fps:
                entry.classification = CLASS_CORRECTED
                entry.history.append({"headSha": session.candidate_sha, "classification": CLASS_CORRECTED})


def consolidate_repair_batch(session: ReviewSession, entries: Sequence[LedgerEntry]) -> RepairBatch:
    accepted = [
        entry.finding
        for entry in entries
        if entry.classification in {CLASS_UNRESOLVED, CLASS_REPEATED, CLASS_NEWLY_DISCOVERED, CLASS_INTRODUCED_BY_REPAIR}
    ]
    batch = RepairBatch(
        batch_id=uuid.uuid4().hex,
        session_id=session.session_id,
        head_sha=session.candidate_sha,
        fingerprints=[item.fingerprint for item in accepted],
        findings=accepted,
    )
    session.pending_batch = batch
    session.last_batch_id = batch.batch_id
    return batch


def cancel_live_reviewer(
    session: ReviewSession,
    adapter: ReviewerAdapter | None = None,
) -> None:
    live = session.live_reviewer
    if not live:
        return
    if adapter is not None:
        lease = ReviewerLease(
            lease_id=str(live.get("leaseId") or ""),
            session_id=session.session_id,
            head_sha=str(live.get("headSha") or session.candidate_sha),
            started_at=float(live.get("startedAt") or 0.0),
            status=str(live.get("status") or "running"),
        )
        adapter.cancel(lease)
    session.live_reviewer = None


def apply_repair(
    session: ReviewSession,
    entries: Sequence[LedgerEntry],
    *,
    new_head: str,
    new_tree: str,
    touched_paths: Sequence[str],
    tests: Sequence[Mapping[str, Any]] | None = None,
    reviewer_adapter: ReviewerAdapter | None = None,
) -> None:
    if session.status in {STATUS_REVIEW_STALLED, STATUS_HOLD}:
        raise ConvergenceError(
            session.status,
            "apply_repair cannot change a stalled or held exact-head identity",
        )
    normalized_touched = require_touched_paths(touched_paths)
    if session.repair_cycle_count >= UNATTENDED_CHECKPOINT_CYCLES and not _has_continue_until_clean(session):
        session.status = STATUS_UNATTENDED_CHECKPOINT
        raise ConvergenceError(
            "unattended_checkpoint",
            "apply_repair after the unattended checkpoint requires recorded continue until clean",
        )
    if session.pending_batch is None:
        raise ConvergenceError("no_repair_batch", "repairs must come from one consolidated batch")
    if session.pending_batch.cycle_consumed:
        raise ConvergenceError("duplicate_cycle", "this consolidated batch already consumed its repair cycle")
    new_head = require_sha(new_head, "new_head")
    new_tree = require_sha(new_tree, "new_tree")
    if new_head == session.candidate_sha:
        raise ConvergenceError("unchanged_head", "a repair cycle requires a new reviewed head")
    cancel_live_reviewer(session, reviewer_adapter)
    session.candidate_sha = new_head
    session.git_tree = new_tree
    session.repair_cycle_count += 1
    session.pending_batch.cycle_consumed = True
    session.last_touched_paths = normalized_touched
    session.tests.extend(dict(item) for item in (tests or []))
    for entry in entries:
        if entry.finding.fingerprint in set(session.pending_batch.fingerprints):
            entry.repair_attempts += 1
    invalidate_evidence(session)
    session.status = STATUS_IN_PROGRESS


def invalidate_evidence(session: ReviewSession) -> None:
    session.full_evidence = {"valid": False, "headSha": session.candidate_sha}
    session.prior_review = {"valid": False, "headSha": session.candidate_sha}


def record_full_evidence(session: ReviewSession, *, head_sha: str) -> None:
    head_sha = require_sha(head_sha, "headSha")
    if head_sha != session.candidate_sha:
        raise ConvergenceError("stale_full", "Full evidence is not bound to the current exact head")
    if session.status in {STATUS_HOLD, STATUS_REVIEW_STALLED}:
        raise ConvergenceError(
            session.status,
            "Full cannot run while independent review is held or stalled",
        )
    if session.status != STATUS_REVIEW_CLEAN and not session.require_full_before_review:
        raise ConvergenceError(
            "full_before_review",
            "Full must not run until required independent review is clean unless policy requires Full first",
        )
    session.full_evidence = {"valid": True, "headSha": head_sha}


def _has_continue_until_clean(session: ReviewSession) -> bool:
    auth = session.founder_authority or {}
    return auth.get("instruction") == CONTINUE_UNTIL_CLEAN


def _resource_exhausted(session: ReviewSession, clock: Clock) -> bool:
    limit = session.resource_limit or (session.founder_authority or {}).get("resourceLimit") or {}
    elapsed = clock.now() - session.started_at
    max_elapsed = limit.get("maxElapsedSeconds")
    if max_elapsed is not None and elapsed >= float(max_elapsed):
        return True
    max_compute = limit.get("maxComputeUnits")
    if max_compute is not None and session.compute_units >= float(max_compute):
        return True
    return False


def record_compute_units(
    session: ReviewSession,
    units: float,
    *,
    clock: Clock | None = None,
) -> dict[str, Any]:
    clock = clock or SystemClock()
    if units < 0:
        raise ConvergenceError("invalid_compute", "compute units must be non-negative")
    session.compute_units += float(units)
    if _resource_exhausted(session, clock):
        _stall(session, STALL_RESOURCE_LIMIT)
        return {
            "status": STATUS_REVIEW_STALLED,
            "reason": STALL_RESOURCE_LIMIT,
            "computeUnits": session.compute_units,
        }
    return {
        "status": session.status,
        "reason": session.stall_reason or session.hold_reason,
        "computeUnits": session.compute_units,
    }


def _stall(session: ReviewSession, reason: str) -> None:
    session.status = STATUS_REVIEW_STALLED
    session.stall_reason = reason
    session.hold_reason = reason


def evaluate_progress(
    session: ReviewSession,
    entries: Sequence[LedgerEntry],
    *,
    clock: Clock | None = None,
) -> ProgressDecision:
    clock = clock or SystemClock()
    if session.status == STATUS_REVIEW_STALLED:
        return ProgressDecision(STATUS_REVIEW_STALLED, session.stall_reason, False, False, True)
    if session.status == STATUS_HOLD:
        return ProgressDecision(STATUS_HOLD, session.hold_reason, False, False, True)
    if session.status == STATUS_REVIEW_CLEAN:
        if blocking_unresolved(entries):
            raise ConvergenceError("findings_bypass", "clean review cannot bypass remaining blocking findings")
        return ProgressDecision(STATUS_REVIEW_CLEAN, None, False, True, False)

    if _resource_exhausted(session, clock):
        _stall(session, STALL_RESOURCE_LIMIT)
        return ProgressDecision(STATUS_REVIEW_STALLED, STALL_RESOURCE_LIMIT, False, False, True)

    for entry in entries:
        if entry.finding.requires_redesign or entry.finding.requires_new_authority:
            if entry.classification != CLASS_CORRECTED:
                _stall(session, STALL_REDESIGN)
                return ProgressDecision(STATUS_REVIEW_STALLED, STALL_REDESIGN, False, False, True)
        if entry.classification == CLASS_INTRODUCED_BY_REPAIR and entry.finding.severity in BLOCKING_SEVERITIES:
            _stall(session, STALL_REINTRODUCTION)
            return ProgressDecision(STATUS_REVIEW_STALLED, STALL_REINTRODUCTION, False, False, True)
        if (
            entry.classification == CLASS_REPEATED
            and entry.repair_attempts >= REPEATED_UNRESOLVED_REPAIR_ATTEMPTS
            and entry.finding.severity in BLOCKING_SEVERITIES
        ):
            _stall(session, STALL_REPEATED_UNRESOLVED)
            return ProgressDecision(STATUS_REVIEW_STALLED, STALL_REPEATED_UNRESOLVED, False, False, True)

    unresolved = [
        entry
        for entry in entries
        if entry.classification in {CLASS_UNRESOLVED, CLASS_REPEATED, CLASS_NEWLY_DISCOVERED, CLASS_INTRODUCED_BY_REPAIR}
    ]
    if not unresolved:
        session.status = STATUS_REVIEW_CLEAN
        session.stall_reason = None
        session.hold_reason = None
        return ProgressDecision(STATUS_REVIEW_CLEAN, None, False, True, False)

    corrected = sum(1 for entry in entries if entry.classification == CLASS_CORRECTED)
    newly_after_repair = sum(
        1
        for entry in entries
        if entry.classification == CLASS_NEWLY_DISCOVERED
        and set(entry.finding.paths) & set(session.last_touched_paths)
    )
    severity_progress = any(entry.severity_reduced_this_cycle for entry in entries)
    progress = corrected > 0 or newly_after_repair > 0 or severity_progress
    if session.repair_cycle_count > 0 and session.repair_cycle_count != session.last_evaluated_cycle:
        if progress:
            session.no_progress_streak = 0
        else:
            session.no_progress_streak += 1
        session.last_evaluated_cycle = session.repair_cycle_count
    session.last_progress = progress
    if session.repair_cycle_count > 0 and session.no_progress_streak >= NO_PROGRESS_STALL_STREAK:
        _stall(session, STALL_NO_PROGRESS)
        return ProgressDecision(STATUS_REVIEW_STALLED, STALL_NO_PROGRESS, False, False, True)

    authorized = _has_continue_until_clean(session)
    if (
        session.repair_cycle_count >= UNATTENDED_CHECKPOINT_CYCLES
        and not authorized
        and session.status != STATUS_REVIEW_STALLED
    ):
        session.status = STATUS_UNATTENDED_CHECKPOINT
        return ProgressDecision(STATUS_UNATTENDED_CHECKPOINT, "unattended_three_cycle_checkpoint", False, progress, True)

    session.status = STATUS_CONTINUE if authorized else STATUS_IN_PROGRESS
    return ProgressDecision(session.status, None, authorized, progress, False)


def authorize_split(
    session: ReviewSession,
    entries: Sequence[LedgerEntry],
    *,
    owner: str,
    units: Sequence[Mapping[str, Any]],
    recursive: bool = False,
) -> list[dict[str, Any]]:
    if not (owner or "").strip():
        raise ConvergenceError("invalid_authority", "a founder-authorized split requires an owner")
    if recursive and session.splits:
        raise ConvergenceError(
            "recursive_split_requires_new_authority",
            "a recursive split requires a new founder decision that redesigns or reduces the candidate",
        )
    session.recovery_generation += 1
    created = []
    for unit in units:
        unit_id = str(unit.get("unitId") or uuid.uuid4().hex)
        created.append(
            {
                "unitId": unit_id,
                "rootSessionId": session.root_session_id,
                "scope": list(unit.get("scope") or session.scope),
                "repairCycleCount": 0,
                "ledgerFingerprints": [entry.finding.fingerprint for entry in entries],
                "recoveryGeneration": session.recovery_generation,
            }
        )
    session.splits.extend(created)
    return created


def ingest_integration_review(
    session: ReviewSession,
    entries: list[LedgerEntry],
    payload: Mapping[str, Any],
    *,
    actor: str,
    role: str,
) -> list[Finding]:
    if not session.splits:
        raise ConvergenceError("no_split", "combined integration review requires a founder-authorized split")
    prior_count = len(entries)
    findings = ingest_review(session, entries, payload, actor=actor, role=role)
    if len(entries) < prior_count:
        raise ConvergenceError("ledger_erasure", "integration review cannot erase ledger history")
    if blocking_unresolved(entries):
        if session.status == STATUS_REVIEW_CLEAN:
            raise ConvergenceError("findings_bypass", "non-clean integration review cannot fabricate a clean result")
        session.status = STATUS_IN_PROGRESS
    return findings


def founder_decision_packet(
    session: ReviewSession,
    entries: Sequence[LedgerEntry],
    *,
    clock: Clock | None = None,
) -> dict[str, Any]:
    clock = clock or SystemClock()
    if session.status == STATUS_REVIEW_CLEAN and blocking_unresolved(entries):
        raise ConvergenceError("findings_bypass", "founder packet cannot declare clean while findings remain")
    elapsed = max(0.0, clock.now() - session.started_at)
    packet = {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "founder-decision-packet",
        "status": session.status,
        "reason": session.stall_reason or session.hold_reason,
        "sessionId": session.session_id,
        "rootSessionId": session.root_session_id,
        "repository": session.repository,
        "headSha": session.candidate_sha,
        "gitTree": session.git_tree,
        "repairCycleCount": session.repair_cycle_count,
        "terminalCycleCap": TERMINAL_CYCLE_CAP,
        "elapsedSeconds": elapsed,
        "ledger": ledger_to_dict(session, entries),
        "tests": list(session.tests),
        "reviewerOutputs": list(session.reviewer_outputs),
        "classes": {
            "code_defects": [e.to_dict() for e in entries if e.classification != CLASS_CORRECTED],
            "preflight_failures": list(session.preflight_failures),
            "infrastructure_failures": list(session.infrastructure_failures),
            "repeated_findings": [e.to_dict() for e in entries if e.classification == CLASS_REPEATED],
            "newly_discovered": [e.to_dict() for e in entries if e.classification == CLASS_NEWLY_DISCOVERED],
            "repair_introduced": [e.to_dict() for e in entries if e.classification == CLASS_INTRODUCED_BY_REPAIR],
        },
        "proposedNextDecisions": _proposed_decisions(session),
        "component": COMPONENT_KIND,
    }
    return packet


def _proposed_decisions(session: ReviewSession) -> list[str]:
    if session.stall_reason == STALL_REDESIGN:
        return ["redesign the candidate", "reduce scope", "grant new authority"]
    if session.stall_reason == STALL_RESOURCE_LIMIT:
        return ["raise the recorded resource limit", "stop and deliver a HOLD"]
    if session.stall_reason == STALL_INFRA_EXHAUSTED:
        return ["repair reviewer/preflight infrastructure", "do not retry the same unchanged head"]
    if session.status == STATUS_UNATTENDED_CHECKPOINT:
        return ["record continue until clean", "inspect the ledger and stop"]
    return ["repair remaining findings", "redesign", "stop with preserved ledger"]


def write_state(state_dir: Path, session: ReviewSession, entries: Sequence[LedgerEntry], clock: Clock | None = None) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = session.to_dict()
    clock = clock or SystemClock()
    payload["elapsedSeconds"] = max(0.0, clock.now() - session.started_at)
    (state_dir / SESSION_FILENAME).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (state_dir / LEDGER_FILENAME).write_text(
        json.dumps(ledger_to_dict(session, entries), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if session.status in {STATUS_REVIEW_STALLED, STATUS_HOLD, STATUS_UNATTENDED_CHECKPOINT}:
        (state_dir / PACKET_FILENAME).write_text(
            json.dumps(founder_decision_packet(session, entries, clock=clock), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


class MemoryReviewer:
    """Test adapter. Production callers inject a real reviewer adapter."""

    def __init__(self) -> None:
        self.started: list[str] = []
        self.cancelled: list[str] = []
        self.payloads: dict[str, Mapping[str, Any]] = {}
        self.live: ReviewerLease | None = None

    def queue(self, session_id: str, payload: Mapping[str, Any]) -> None:
        self.payloads[session_id] = payload

    def start(self, session: ReviewSession) -> ReviewerLease:
        if self.live and self.live.status == "running":
            raise ConvergenceError("duplicate_reviewer", "memory reviewer already has a live process")
        lease = ReviewerLease(
            lease_id=uuid.uuid4().hex,
            session_id=session.session_id,
            head_sha=session.candidate_sha,
            started_at=0.0,
        )
        self.started.append(lease.lease_id)
        self.live = lease
        return lease

    def cancel(self, lease: ReviewerLease) -> None:
        self.cancelled.append(lease.lease_id)
        lease.status = "cancelled"
        if self.live and self.live.lease_id == lease.lease_id:
            self.live = None

    def result(self, lease: ReviewerLease) -> Mapping[str, Any] | None:
        return self.payloads.get(lease.session_id)


def _print_json(payload: Mapping[str, Any]) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independent-review convergence controller")
    parser.add_argument("--json", action="store_true", help="print structured JSON")
    sub = parser.add_subparsers(dest="command", required=True)
    identity = argparse.ArgumentParser(add_help=False)
    identity.add_argument("--repository", required=True)
    identity.add_argument("--base-sha", required=True)
    identity.add_argument("--candidate-sha", required=True)
    identity.add_argument("--git-tree", required=True)
    identity.add_argument("--scope", action="append", default=[])
    identity.add_argument("--reviewer-policy", default="default")
    identity.add_argument("--implementer-actor", required=True)
    identity.add_argument("--reviewer-actor", required=True)
    sub.add_parser("open", parents=[identity])
    status = sub.add_parser("schema-ids")
    status.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "schema-ids":
        return _print_json(
            {
                "component": COMPONENT_KIND,
                "sessionKind": SESSION_KIND,
                "ledgerKind": LEDGER_KIND,
                "maxInfrastructureAttempts": MAX_INFRASTRUCTURE_ATTEMPTS,
                "unattendedCheckpointCycles": UNATTENDED_CHECKPOINT_CYCLES,
                "terminalCycleCap": TERMINAL_CYCLE_CAP,
            }
        )
    session, _entries = open_session(
        repository=args.repository,
        base_sha=args.base_sha,
        candidate_sha=args.candidate_sha,
        git_tree=args.git_tree,
        scope=args.scope,
        reviewer_policy=args.reviewer_policy,
        implementer_actor=args.implementer_actor,
        reviewer_actor=args.reviewer_actor,
    )
    return _print_json(session.to_dict())


if __name__ == "__main__":
    raise SystemExit(main())
