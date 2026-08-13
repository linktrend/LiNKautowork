#!/usr/bin/env python3
"""Integrator-owned Phase aggregation and sealed-candidate lifecycle.

This module deliberately keeps GitHub I/O outside the lifecycle model.  The
Integrator (and only the Integrator) supplies exact branch tips, acceptance
records, and gate observations.  The model then applies the fail-closed Phase
rules against a local Git checkout and writes a sanitized record atomically.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

try:  # Prefer the package path so unittest and CLI share one class identity.
    from scripts.gitops.coordinator.state import CandidateIdentity
    from scripts.gitops.delivery_modes import (
        DEFAULT_PHASE_PREFIX,
        MODE_PHASE_INTEGRATION,
        is_valid_sha,
        normalize_sha,
    )
except ModuleNotFoundError:  # pragma: no cover - exercised by package-style tests
    from coordinator.state import CandidateIdentity
    from delivery_modes import (
        DEFAULT_PHASE_PREFIX,
        MODE_PHASE_INTEGRATION,
        is_valid_sha,
        normalize_sha,
    )

PHASE_RECORD_REL = Path(".linktrend/phase-delivery-record.json")
INTEGRATOR_ROLE = "integrator"
ISSUE_BRANCH_RE = re.compile(r"^issue/([1-9][0-9]{0,8})-(.+)$")
TERMINAL_PHASE_STATES = frozenset({"main-promoted", "stopped", "blocked", "cancelled"})


class PhaseLifecycleError(ValueError):
    """A fail-closed Phase lifecycle rejection."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True)
class IssueTip:
    """One exact accepted Issue tip and its independent acceptance proof."""

    branch: str
    sha: str
    accepted: bool = True
    acceptance_sha: str | None = None
    live_sha: str | None = None
    included: bool = False

    def __post_init__(self) -> None:
        if not self.branch.startswith("issue/"):
            raise PhaseLifecycleError("invalid_issue_branch", self.branch)
        if not is_valid_sha(self.sha):
            raise PhaseLifecycleError("invalid_issue_sha", self.branch)
        if self.acceptance_sha is not None and normalize_sha(self.acceptance_sha) != normalize_sha(self.sha):
            raise PhaseLifecycleError("acceptance_sha_mismatch", self.branch)
        if self.live_sha is not None and normalize_sha(self.live_sha) != normalize_sha(self.sha):
            raise PhaseLifecycleError("stale_issue_tip", self.branch)

    @property
    def issue_number(self) -> str:
        match = ISSUE_BRANCH_RE.fullmatch(self.branch)
        if not match:
            raise PhaseLifecycleError("invalid_issue_branch", self.branch)
        return match.group(1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "sha": normalize_sha(self.sha),
            "accepted": bool(self.accepted),
            "included": bool(self.included),
            "acceptanceSha": normalize_sha(self.acceptance_sha) if self.acceptance_sha else None,
        }


@dataclass(frozen=True)
class MergeEligibility:
    eligible: bool
    detail: str
    checks: Mapping[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return {"eligible": self.eligible, "detail": self.detail, "checks": dict(self.checks)}


def _git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)
    if check and result.returncode:
        detail = (result.stderr or result.stdout or "git command failed").strip()
        raise PhaseLifecycleError("git_failed", detail[:300])
    return (result.stdout or "").strip()


def _checkout_has_unrelated_changes(repo: Path) -> bool:
    """The Integrator-owned record may be the one intentional dirty path."""

    rows = _git(repo, "status", "--porcelain", "--untracked-files=all").splitlines()
    record = PHASE_RECORD_REL.as_posix()
    return any(row[3:].strip() != record for row in rows if len(row) >= 3)


def git_is_ancestor(repo: str | Path, ancestor_sha: str, descendant_sha: str) -> bool:
    """Prove exact Git ancestry without relying on branch names or PR metadata."""

    if not is_valid_sha(ancestor_sha) or not is_valid_sha(descendant_sha):
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", normalize_sha(ancestor_sha), normalize_sha(descendant_sha)],
        cwd=Path(repo), text=True, capture_output=True, check=False,
    )
    return result.returncode == 0


def _issue_key(branch: str) -> str:
    match = ISSUE_BRANCH_RE.fullmatch(branch)
    if not match:
        raise PhaseLifecycleError("invalid_issue_branch", branch)
    return match.group(1)


def validate_issue_batch(
    issues: Iterable[IssueTip | Mapping[str, Any]],
    *,
    immutable_base_sha: str,
    phase_head_sha: str,
    repo: str | Path | None = None,
) -> list[IssueTip]:
    """Validate a batch before the Integrator mutates Phase state."""

    if not is_valid_sha(immutable_base_sha) or not is_valid_sha(phase_head_sha):
        raise PhaseLifecycleError("invalid_phase_identity", "base and Phase head must be non-zero 40-hex SHAs")
    result: list[IssueTip] = []
    seen_numbers: set[str] = set()
    seen_branches: set[str] = set()
    seen_shas: set[str] = set()
    for raw in issues:
        item = raw if isinstance(raw, IssueTip) else IssueTip(
            branch=str(raw.get("branch") or ""),
            sha=str(raw.get("sha") or ""),
            accepted=bool(raw.get("accepted")),
            acceptance_sha=raw.get("acceptanceSha", raw.get("acceptedSha")),
            live_sha=raw.get("liveSha", raw.get("tipSha")),
            included=bool(raw.get("included")),
        )
        number = item.issue_number
        if number in seen_numbers or item.branch in seen_branches:
            raise PhaseLifecycleError("duplicate_issue", item.branch)
        if item.sha in seen_shas:
            raise PhaseLifecycleError("duplicate_issue_sha", item.sha)
        if not item.accepted:
            raise PhaseLifecycleError("issue_not_accepted", item.branch)
        if item.acceptance_sha is None:
            raise PhaseLifecycleError("acceptance_missing", item.branch)
        if item.live_sha is not None and normalize_sha(item.live_sha) != normalize_sha(item.sha):
            raise PhaseLifecycleError("stale_issue_tip", item.branch)
        if repo is not None and not git_is_ancestor(repo, item.sha, phase_head_sha):
            raise PhaseLifecycleError("unproven_inclusion", item.branch)
        seen_numbers.add(number)
        seen_branches.add(item.branch)
        seen_shas.add(item.sha)
        result.append(item)
    if not result:
        raise PhaseLifecycleError("no_accepted_issues", "Phase requires at least one accepted Issue")
    if repo is not None and not git_is_ancestor(repo, immutable_base_sha, phase_head_sha):
        raise PhaseLifecycleError("wrong_base", "Phase head is not descended from immutable base")
    return result


def _digest_set(identity: CandidateIdentity) -> str:
    return hashlib.sha256(identity.canonical().encode("utf-8")).hexdigest()


def candidate_identity_for(
    *, repository: str, source_sha: str, git_tree_sha: str, dependency_digests: Mapping[str, str], test_profile: str = "full"
) -> CandidateIdentity:
    return CandidateIdentity(repository, normalize_sha(source_sha), normalize_sha(git_tree_sha), dict(dependency_digests), test_profile)


def invalidate_candidate_gates(record: Mapping[str, Any], *, old_head_sha: str, new_head_sha: str) -> dict[str, Any]:
    """Return a copy whose candidate gates cannot be reused after head movement."""

    result = copy.deepcopy(dict(record))
    result["headSha"] = normalize_sha(new_head_sha)
    result["sealed"] = False
    result["candidateIdentity"] = None
    result["candidateId"] = None
    result["sealedSha"] = None
    result["sealRevision"] = result.get("sealRevision", result.get("sealedCandidateRevisions", 0))
    result["invalidatedFromSha"] = normalize_sha(old_head_sha)
    for gate in ("fast", "bugbot", "full", "staging", "release"):
        result[gate] = {"status": "invalidated", "detail": "phase_head_changed"}
    result["namedGateEvidence"] = {
        "gate": "fast-gate",
        "sha": normalize_sha(new_head_sha),
        "status": "failed",
        "detail": "phase_head_changed",
        "checks": [],
    }
    return result


def phase_bugbot_request_allowed(record: Mapping[str, Any], *, live_head_sha: str) -> tuple[bool, str]:
    """Bugbot is one-shot and only follows the current sealed candidate fast pass."""

    head = normalize_sha(live_head_sha)
    if not record.get("sealed"):
        return False, "phase_not_sealed"
    if normalize_sha(str(record.get("sealedSha") or record.get("headSha") or "")) != head:
        return False, "sealed_head_stale"
    identity = record.get("candidateIdentity")
    if not isinstance(identity, Mapping) or normalize_sha(str(identity.get("sourceSha") or "")) != head:
        return False, "candidate_identity_stale"
    fast = record.get("fast") if isinstance(record.get("fast"), Mapping) else {}
    if fast.get("status") != "passed" or normalize_sha(str(fast.get("sha") or head)) != head:
        return False, "fast_gate_not_passed_for_current_seal"
    bugbot = record.get("bugbot") if isinstance(record.get("bugbot"), Mapping) else {}
    if bugbot.get("status") in {"requested", "passed"}:
        return False, "bugbot_already_requested"
    return True, "current_sealed_fast_pass"


def phase_full_suite_dispatch_allowed(
    record: Mapping[str, Any], *, live_head_sha: str, pr_number: int
) -> tuple[bool, str, dict[str, str] | None]:
    """Build the only valid Full Suite dispatch for the current sealed head.

    The caller still performs the explicit GitHub dispatch.  Keeping the
    decision pure makes it testable and prevents a draft or superseded head
    from waking the expensive workflow.  Bugbot is requested by the Full Suite
    workflow after the receipt succeeds, so both actions remain final-candidate
    only without introducing a second trigger path.
    """

    allowed, detail = phase_bugbot_request_allowed(record, live_head_sha=live_head_sha)
    if not allowed:
        return False, detail, None
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number < 1:
        return False, "invalid_pr_number", None
    full = record.get("full") if isinstance(record.get("full"), Mapping) else {}
    if full.get("status") in {"requested", "running", "passed"}:
        return False, "full_suite_already_requested", None
    try:
        prior_attempt = int(full.get("attempt") or 0)
    except (TypeError, ValueError):
        return False, "full_suite_attempt_invalid", None
    if prior_attempt >= 2:
        return False, "full_suite_attempt_limit", None
    candidate_id = str(record.get("candidateId") or "").strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_id):
        return False, "candidate_id_missing", None
    head = normalize_sha(live_head_sha)
    revision = str(record.get("sealRevision") or record.get("sealedCandidateRevisions") or "")
    if revision not in {"1", "2"}:
        return False, "invalid_seal_revision", None
    return True, "current_sealed_candidate", {
        "pr_number": str(pr_number),
        "source_branch": str(record.get("phaseBranch") or ""),
        "head_sha": head,
        "candidate_id": candidate_id,
        "seal_revision": revision,
        "attempt": str(prior_attempt + 1),
    }


def phase_merge_eligibility(
    record: Mapping[str, Any], *, live_head_sha: str, conflict: bool = False
) -> MergeEligibility:
    """Check all exact candidate conditions immediately before a Phase merge."""

    head = normalize_sha(live_head_sha)
    sealed = bool(record.get("sealed")) and normalize_sha(str(record.get("sealedSha") or "")) == head
    identity = record.get("candidateIdentity")
    identity_head = normalize_sha(str(identity.get("sourceSha") or "")) if isinstance(identity, Mapping) else ""
    fast = record.get("fast") if isinstance(record.get("fast"), Mapping) else {}
    bugbot = record.get("bugbot") if isinstance(record.get("bugbot"), Mapping) else {}
    full = record.get("full") if isinstance(record.get("full"), Mapping) else {}
    checks = {
        "currentSeal": sealed and identity_head == head,
        "fastSuccess": fast.get("status") == "passed" and normalize_sha(str(fast.get("sha") or "")) == head,
        "bugbotSuccess": bugbot.get("status") == "passed" and normalize_sha(str(bugbot.get("sha") or "")) == head,
        "fullSuccessOrNotRequired": (
            full.get("status") == "not-required"
            or (full.get("status") == "passed" and normalize_sha(str(full.get("sha") or "")) == head)
        ),
        "noConflict": not conflict,
        "liveHeadUnchanged": normalize_sha(str(record.get("headSha") or "")) == head,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return MergeEligibility(not failed, "all_current_candidate_gates_passed" if not failed else "blocked:" + ",".join(failed), checks)


def synchronize_phase(
    repo: str | Path,
    *,
    phase_branch: str,
    development_branch: str = "development",
    actor: str = INTEGRATOR_ROLE,
) -> dict[str, Any]:
    """Explicitly synchronize Phase with development, preserving both lines.

    A conflict is reported and aborted without choosing ours/theirs.  The
    caller must create a fresh seal after a successful synchronization.
    """

    if actor != INTEGRATOR_ROLE:
        raise PhaseLifecycleError("non_integrator_mutation", "only Integrator may synchronize the Phase branch")
    root = Path(repo)
    phase_before = _git(root, "rev-parse", phase_branch)
    development = _git(root, "rev-parse", development_branch)
    if _checkout_has_unrelated_changes(root):
        raise PhaseLifecycleError("dirty_checkout", "synchronization requires a clean checkout")
    _git(root, "checkout", phase_branch)
    result = subprocess.run(["git", "merge", "--no-ff", "--no-edit", development], cwd=root, text=True, capture_output=True, check=False)
    if result.returncode:
        subprocess.run(["git", "merge", "--abort"], cwd=root, text=True, capture_output=True, check=False)
        return {"status": "blocked", "detail": "merge_conflict", "phaseSha": phase_before, "developmentSha": development}
    phase_after = _git(root, "rev-parse", "HEAD")
    return {"status": "synchronized", "detail": "development_merged_without_preference", "phaseSha": phase_after, "developmentSha": development}


class PhaseIntegrator:
    """Mutation boundary for a single repository/Phase identity."""

    def __init__(
        self,
        repo: str | Path,
        *,
        repository: str,
        phase_branch: str,
        phase_id: str,
        immutable_base_sha: str,
        actor: str = INTEGRATOR_ROLE,
        record_path: str | Path | None = None,
    ) -> None:
        if actor != INTEGRATOR_ROLE:
            raise PhaseLifecycleError("non_integrator_mutation", "only Integrator may mutate Phase branch/record")
        if not is_valid_sha(immutable_base_sha):
            raise PhaseLifecycleError("wrong_base", immutable_base_sha)
        self.repo = Path(repo).resolve()
        self.repository = repository
        self.phase_branch = phase_branch
        self.phase_id = phase_id
        self.immutable_base_sha = normalize_sha(immutable_base_sha)
        self.record_path = self.repo / (Path(record_path) if record_path else PHASE_RECORD_REL)

    def _write(self, record: Mapping[str, Any]) -> dict[str, Any]:
        self.record_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.record_path.parent, delete=False) as handle:
            handle.write(payload)
            handle.flush()
            temporary = Path(handle.name)
        temporary.replace(self.record_path)
        return dict(record)

    def load(self) -> dict[str, Any] | None:
        if not self.record_path.is_file():
            return None
        try:
            value = json.loads(self.record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PhaseLifecycleError("phase_record_unreadable", str(exc)) from exc
        if not isinstance(value, dict):
            raise PhaseLifecycleError("phase_record_invalid", "record must be an object")
        return value

    def _base_record(self, head_sha: str, accepted: list[IssueTip]) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "deliveryMode": MODE_PHASE_INTEGRATION,
            "phaseId": self.phase_id,
            "phaseBranch": self.phase_branch,
            "baseSha": self.immutable_base_sha,
            "immutableBaseSha": self.immutable_base_sha,
            "headSha": normalize_sha(head_sha),
            "mergeSha": None,
            "phasePr": None,
            "acceptedIssues": [issue.to_dict() for issue in accepted],
            "namedGateEvidence": {"gate": "fast-gate", "sha": normalize_sha(head_sha), "status": "missing", "detail": "unsealed", "checks": []},
            "sealed": False,
            "sealRevision": 0,
            "sealedCandidateRevisions": 0,
            "sealedSha": None,
            "candidateId": None,
            "candidateIdentity": None,
            "fast": {"status": "not-run"},
            "bugbot": {"status": "not-run"},
            "full": {"status": "not-run"},
            "staging": {"status": "not-run"},
            "release": {"status": "not-run"},
            "stopReason": None,
        }

    def aggregate(self, issues: Iterable[IssueTip | Mapping[str, Any]], *, phase_head_sha: str | None = None) -> dict[str, Any]:
        """Record accepted Issue tips already proven included by exact ancestry."""

        head = normalize_sha(phase_head_sha or _git(self.repo, "rev-parse", self.phase_branch))
        validated = validate_issue_batch(issues, immutable_base_sha=self.immutable_base_sha, phase_head_sha=head, repo=self.repo)
        current = self.load()
        if current is not None:
            previous = {str(row.get("branch")): str(row.get("sha")) for row in current.get("acceptedIssues", []) if isinstance(row, Mapping)}
            for issue in validated:
                if issue.branch in previous and previous[issue.branch] != issue.sha:
                    raise PhaseLifecycleError("stale_issue_tip", issue.branch)
            if normalize_sha(str(current.get("baseSha") or "")) != self.immutable_base_sha:
                raise PhaseLifecycleError("wrong_base", "existing Phase record base differs from immutable base")
            record = copy.deepcopy(current)
            previous_head = normalize_sha(str(record.get("headSha") or ""))
            if previous_head and previous_head != head and bool(record.get("sealed")):
                record = invalidate_candidate_gates(record, old_head_sha=previous_head, new_head_sha=head)
            record["headSha"] = head
            record["acceptedIssues"] = [issue.to_dict() for issue in validated]
        else:
            record = self._base_record(head, validated)
        record["phaseReady"] = True
        return self._write(record)

    def record_acceptance(self, issue: IssueTip | Mapping[str, Any], *, phase_head_sha: str | None = None) -> dict[str, Any]:
        """Persist independent acceptance before the Integrator includes the tip."""

        item = issue if isinstance(issue, IssueTip) else IssueTip(
            branch=str(issue.get("branch") or ""),
            sha=str(issue.get("sha") or ""),
            accepted=bool(issue.get("accepted")),
            acceptance_sha=issue.get("acceptanceSha", issue.get("acceptedSha")),
            live_sha=issue.get("liveSha", issue.get("tipSha")),
        )
        if not item.accepted or item.acceptance_sha is None:
            raise PhaseLifecycleError("acceptance_missing", item.branch)
        head = normalize_sha(phase_head_sha or _git(self.repo, "rev-parse", self.phase_branch))
        if not git_is_ancestor(self.repo, self.immutable_base_sha, head):
            raise PhaseLifecycleError("wrong_base", "Phase head is not descended from immutable base")
        current = self.load() or self._base_record(head, [])
        if normalize_sha(str(current.get("headSha") or "")) != head:
            raise PhaseLifecycleError("stale_phase_head", "acceptance must attach to the live Phase head")
        existing = list(current.get("acceptedIssues") or [])
        if any(str(row.get("branch") or "") == item.branch for row in existing):
            raise PhaseLifecycleError("duplicate_issue", item.branch)
        if any(_issue_key(str(row.get("branch") or "")) == item.issue_number for row in existing):
            raise PhaseLifecycleError("duplicate_issue", item.issue_number)
        existing.append(item.to_dict())
        current["acceptedIssues"] = existing
        current["phaseReady"] = False
        current["status"] = "collecting"
        return self._write(current)

    def integrate_issue(self, issue: IssueTip | Mapping[str, Any]) -> dict[str, Any]:
        """Merge one independently accepted tip onto the Phase branch.

        Conflicts abort the merge and leave the checkout at the Phase tip; no
        ours/theirs strategy is ever selected.
        """

        item = issue if isinstance(issue, IssueTip) else IssueTip(
            branch=str(issue.get("branch") or ""),
            sha=str(issue.get("sha") or ""),
            accepted=bool(issue.get("accepted")),
            acceptance_sha=issue.get("acceptanceSha", issue.get("acceptedSha")),
            live_sha=issue.get("liveSha", issue.get("tipSha")),
        )
        current = self.load()
        if current is None:
            raise PhaseLifecycleError("acceptance_missing", item.branch)
        rows = list(current.get("acceptedIssues") or [])
        match = next((row for row in rows if row.get("branch") == item.branch), None)
        if not isinstance(match, dict) or match.get("sha") != item.sha or not match.get("accepted"):
            raise PhaseLifecycleError("acceptance_missing", item.branch)
        if normalize_sha(str(current.get("headSha") or "")) != normalize_sha(_git(self.repo, "rev-parse", self.phase_branch)):
            raise PhaseLifecycleError("stale_phase_head", "Phase moved after acceptance")
        if _checkout_has_unrelated_changes(self.repo):
            raise PhaseLifecycleError("dirty_checkout", "Issue integration requires a clean checkout")
        _git(self.repo, "checkout", self.phase_branch)
        result = subprocess.run(["git", "merge", "--no-ff", "--no-edit", item.sha], cwd=self.repo, text=True, capture_output=True, check=False)
        if result.returncode:
            subprocess.run(["git", "merge", "--abort"], cwd=self.repo, text=True, capture_output=True, check=False)
            raise PhaseLifecycleError("merge_conflict", "Issue integration conflict; no side preference applied")
        head = _git(self.repo, "rev-parse", "HEAD")
        for row in rows:
            if row.get("branch") == item.branch:
                row["included"] = True
        return self.aggregate(
            [
                IssueTip(
                    str(row.get("branch") or ""),
                    str(row.get("sha") or ""),
                    accepted=bool(row.get("accepted")),
                    acceptance_sha=row.get("acceptanceSha", row.get("sha")),
                    included=bool(row.get("included")),
                )
                for row in rows
            ],
            phase_head_sha=head,
        )

    def integrate_accepted_issues(self, issues: Iterable[IssueTip | Mapping[str, Any]]) -> dict[str, Any]:
        """Record and integrate a batch in caller-supplied order."""

        issues = list(issues)
        for issue in issues:
            self.record_acceptance(issue)
        result = self.load()
        for issue in issues:
            result = self.integrate_issue(issue)
        if result is None:  # pragma: no cover - the input is non-empty by contract
            raise PhaseLifecycleError("no_accepted_issues", "empty Issue batch")
        return result

    def create_draft(self, *, head_sha: str, pr: Mapping[str, Any]) -> dict[str, Any]:
        record = self.load()
        if record is None:
            raise PhaseLifecycleError("phase_record_missing", "aggregate accepted Issue tips before draft creation")
        if normalize_sha(str(record.get("headSha") or "")) != normalize_sha(head_sha):
            raise PhaseLifecycleError("stale_phase_head", "draft head is not the recorded Phase head")
        existing = record.get("phasePr")
        if existing is not None and dict(existing) != dict(pr):
            raise PhaseLifecycleError("duplicate_phase_pr", "Phase may have one draft PR identity")
        record["phasePr"] = dict(pr)
        record["draftPr"] = dict(pr)
        record["status"] = "draft"
        return self._write(record)

    def seal(self, *, head_sha: str, candidate_identity: CandidateIdentity | Mapping[str, Any]) -> dict[str, Any]:
        record = self.load()
        if record is None:
            raise PhaseLifecycleError("phase_record_missing", "cannot seal without Phase record")
        head = normalize_sha(head_sha)
        if normalize_sha(str(record.get("headSha") or "")) != head:
            raise PhaseLifecycleError("stale_phase_head", "seal must bind to current Phase head")
        accepted = record.get("acceptedIssues")
        if not isinstance(accepted, list) or not accepted or any(not row.get("accepted") or not row.get("included") for row in accepted):
            raise PhaseLifecycleError("unincluded_issue", "every accepted Issue must be proven included before sealing")
        if not git_is_ancestor(self.repo, self.immutable_base_sha, head):
            raise PhaseLifecycleError("wrong_base", "sealed Phase head is not descended from immutable base")
        candidate = candidate_identity if isinstance(candidate_identity, CandidateIdentity) else CandidateIdentity.from_dict(candidate_identity)
        if normalize_sha(candidate.source_sha) != head:
            raise PhaseLifecycleError("candidate_head_mismatch", "candidate sourceSha must equal sealed Phase head")
        if candidate.test_profile != "full":
            raise PhaseLifecycleError("candidate_profile_mismatch", "sealed candidate identity must use the full test profile")
        revisions = int(record.get("sealRevision", record.get("sealedCandidateRevisions", 0)) or 0)
        if revisions >= 2:
            raise PhaseLifecycleError("third_seal", "a third sealed candidate requires principal authorization")
        old_head = normalize_sha(str(record.get("sealedSha") or ""))
        if old_head and old_head != head:
            record = invalidate_candidate_gates(record, old_head_sha=old_head, new_head_sha=head)
        record["sealed"] = True
        record["status"] = "sealed"
        record["sealRevision"] = revisions + 1
        record["sealedCandidateRevisions"] = revisions + 1
        record["sealedSha"] = head
        record["candidateId"] = "sha256:" + _digest_set(candidate)
        record["candidateIdentity"] = candidate.to_dict()
        record["namedGateEvidence"] = {"gate": "fast-gate", "sha": head, "status": "missing", "detail": "sealed_candidate", "checks": []}
        return self._write(record)

    def update_gate(self, gate: str, *, status: str, sha: str, detail: str = "", **extra: Any) -> dict[str, Any]:
        record = self.load()
        if record is None or not record.get("sealed"):
            raise PhaseLifecycleError("phase_not_sealed", "gates require a sealed Phase")
        head = normalize_sha(str(record.get("sealedSha") or ""))
        if normalize_sha(sha) != head:
            raise PhaseLifecycleError("stale_candidate_gate", "gate result is not for current sealed head")
        if gate not in {"fast", "bugbot", "full", "staging", "release"}:
            raise PhaseLifecycleError("invalid_gate", gate)
        record[gate] = {"status": status, "sha": head, "detail": detail, **extra}
        record["namedGateEvidence"] = {"gate": f"{gate}-gate" if gate != "bugbot" else "bugbot", "sha": head, "status": "success" if status in {"passed", "not-required"} else status, "detail": detail, "checks": extra.get("checks", [])}
        return self._write(record)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["eligible", "bugbot-allowed"])
    parser.add_argument("record")
    parser.add_argument("head")
    args = parser.parse_args(argv)
    record = json.loads(Path(args.record).read_text(encoding="utf-8"))
    if args.command == "eligible":
        result = phase_merge_eligibility(record, live_head_sha=args.head)
    else:
        ok, detail = phase_bugbot_request_allowed(record, live_head_sha=args.head)
        result = {"eligible": ok, "detail": detail}
    print(json.dumps(result.to_dict() if hasattr(result, "to_dict") else result, sort_keys=True))
    return 0 if (result.eligible if isinstance(result, MergeEligibility) else result["eligible"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
