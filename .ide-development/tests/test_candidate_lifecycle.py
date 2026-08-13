"""Focused W1-P2 candidate lifecycle and retry-budget acceptance tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.gitops.coordinator.state import (
    CandidateLifecycle,
    CandidateLifecycleStore,
    OUTCOME_CANDIDATE_SEALED,
    OUTCOME_CANDIDATE_SUPERSEDED,
    OUTCOME_CHECKPOINT_RECORDED,
    OUTCOME_CHECK_PASSED,
    OUTCOME_CODE_FAILURE,
    OUTCOME_DUPLICATE_IGNORED,
    OUTCOME_HOLD_SEALED_CANDIDATE_LIMIT,
    OUTCOME_INFRASTRUCTURE_RETRY,
    OUTCOME_LATE_RESULT_REJECTED,
    OUTCOME_STOPPED_ALERT,
    PhaseCandidateIdentity,
    concurrency_key,
)


BASE = "0" * 40
HEADS = tuple(hex(index)[2:] * 40 for index in range(1, 5))


def identity(head: str, *, profile: str = "sha256:profile") -> dict[str, str]:
    return PhaseCandidateIdentity(
        repository="owner/name",
        source_branch="phase/demo",
        head_commit=head,
        git_tree=head,
        dependency_digest="sha256:dependencies",
        profile_digest=profile,
        workflow_digest="sha256:workflow",
    ).to_dict()


class CandidateLifecycleTests(unittest.TestCase):
    def lifecycle(self) -> CandidateLifecycle:
        return CandidateLifecycle.new("owner/name", "P2", "phase/demo", BASE)

    def checkpoint(self, lifecycle: CandidateLifecycle, head: str, event_id: str | None = None):
        event = {
            "type": "checkpoint",
            "repository": "owner/name",
            "phaseId": "P2",
            "phaseBranch": "phase/demo",
            "headCommit": head,
        }
        if event_id:
            event["eventId"] = event_id
        return lifecycle.apply(event)

    def seal(self, lifecycle: CandidateLifecycle, head: str, pr: int, *, profile: str = "sha256:profile", event_id: str | None = None):
        event = {
            "type": "seal",
            "repository": "owner/name",
            "phaseId": "P2",
            "phaseBranch": "phase/demo",
            "prNumber": pr,
            "sourceBranch": "phase/demo",
            "headCommit": head,
            "candidateIdentity": identity(head, profile=profile),
        }
        if event_id:
            event["eventId"] = event_id
        return lifecycle.apply(event)

    def start_fast(self, lifecycle: CandidateLifecycle, candidate_id: str, event_id: str):
        return lifecycle.apply({
            "type": "check-started", "eventId": event_id,
            "candidateId": candidate_id, "check": "fast",
        })

    def complete_fast(self, lifecycle: CandidateLifecycle, candidate_id: str, event_id: str, **extra):
        return lifecycle.apply({
            "type": "check-completed", "eventId": event_id,
            "candidateId": candidate_id, "check": "fast", "conclusion": "success", **extra,
        })

    def test_checkpoint_is_free_and_duplicate_is_idempotent(self) -> None:
        lifecycle = self.lifecycle()
        first = self.checkpoint(lifecycle, HEADS[0], "checkpoint-1")
        self.assertEqual(first.code, OUTCOME_CHECKPOINT_RECORDED)
        self.assertIsNone(first.dispatch)
        self.assertEqual(lifecycle.state.status, "checkpointed")
        before = lifecycle.to_dict()
        duplicate = self.checkpoint(lifecycle, HEADS[0], "checkpoint-1")
        self.assertEqual(duplicate.code, OUTCOME_DUPLICATE_IGNORED)
        self.assertEqual(lifecycle.to_dict(), before)

    def test_lifecycle_models_phase_and_gate_states(self) -> None:
        lifecycle = self.lifecycle()
        self.checkpoint(lifecycle, HEADS[0])
        self.assertEqual(lifecycle.apply({"type": "integrating"}).status, "integrating")
        self.assertEqual(lifecycle.apply({"type": "draft-phase-pr"}).status, "draft-phase-pr")
        sealed = self.seal(lifecycle, HEADS[0], 7)
        candidate_id = sealed.candidate_id
        self.assertEqual(sealed.code, OUTCOME_CANDIDATE_SEALED)
        self.assertEqual(lifecycle.state.status, "sealed-candidate")
        self.start_fast(lifecycle, candidate_id, "fast-start")
        self.assertEqual(self.complete_fast(lifecycle, candidate_id, "fast-pass").code, OUTCOME_CHECK_PASSED)
        lifecycle.apply({"type": "check-started", "eventId": "full-start", "candidateId": candidate_id, "check": "full"})
        lifecycle.apply({"type": "check-completed", "eventId": "full-pass", "candidateId": candidate_id, "check": "full", "conclusion": "success"})
        lifecycle.apply({"type": "check-started", "eventId": "review-start", "candidateId": candidate_id, "check": "review"})
        lifecycle.apply({"type": "check-completed", "eventId": "review-pass", "candidateId": candidate_id, "check": "review", "conclusion": "success"})
        self.assertEqual(lifecycle.state.status, "review-complete")
        lifecycle.apply({"type": "eligibility", "eventId": "eligible", "candidateId": candidate_id, "target": "development"})
        self.assertEqual(lifecycle.state.status, "development-eligible")
        self.assertEqual(lifecycle.state.candidates[candidate_id].attempts, 1)

    def test_new_head_supersedes_old_candidate_and_late_success_is_rejected(self) -> None:
        lifecycle = self.lifecycle()
        self.checkpoint(lifecycle, HEADS[0])
        first = self.seal(lifecycle, HEADS[0], 7)
        self.start_fast(lifecycle, first.candidate_id, "old-start")
        superseded = self.checkpoint(lifecycle, HEADS[1])
        self.assertEqual(superseded.code, OUTCOME_CANDIDATE_SUPERSEDED)
        old = lifecycle.state.candidates[first.candidate_id]
        self.assertEqual(old.status, "superseded")
        self.assertTrue(old.invalidated)
        late = self.complete_fast(lifecycle, first.candidate_id, "old-late-pass")
        self.assertEqual(late.code, OUTCOME_LATE_RESULT_REJECTED)
        second = self.seal(lifecycle, HEADS[1], 7)
        active = [row for row in lifecycle.state.candidates.values() if not row.invalidated]
        self.assertEqual([row.candidate_id for row in active], [second.candidate_id])
        self.assertNotEqual(concurrency_key("owner/name", "fast-gate", 7), concurrency_key("owner/name", "fast-gate", 8))

    def test_different_prs_keep_independent_candidate_work(self) -> None:
        lifecycle = self.lifecycle()
        self.checkpoint(lifecycle, HEADS[0])
        first = self.seal(lifecycle, HEADS[0], 7)
        second = self.seal(lifecycle, HEADS[0], 8)
        self.assertEqual(first.code, OUTCOME_CANDIDATE_SEALED)
        self.assertEqual(second.code, OUTCOME_CANDIDATE_SEALED)
        self.assertEqual({row.status for row in lifecycle.state.candidates.values()}, {"sealed-candidate"})

    def test_candidate_cancellation_is_terminal_without_dispatch(self) -> None:
        lifecycle = self.lifecycle()
        self.checkpoint(lifecycle, HEADS[0])
        sealed = self.seal(lifecycle, HEADS[0], 7)
        cancelled = lifecycle.apply({
            "type": "candidate-cancelled", "eventId": "cancel", "candidateId": sealed.candidate_id,
        })
        self.assertEqual(cancelled.code, "cancelled")
        self.assertIsNone(cancelled.dispatch)
        self.assertEqual(lifecycle.state.candidates[sealed.candidate_id].status, "cancelled")
        self.assertEqual(
            lifecycle.apply({
                "type": "check-started", "eventId": "late-start", "candidateId": sealed.candidate_id, "check": "fast",
            }).code,
            OUTCOME_LATE_RESULT_REJECTED,
        )

    def test_infrastructure_failure_has_one_retry_then_stops(self) -> None:
        lifecycle = self.lifecycle()
        self.checkpoint(lifecycle, HEADS[0])
        sealed = self.seal(lifecycle, HEADS[0], 7)
        self.start_fast(lifecycle, sealed.candidate_id, "attempt-1-start")
        retry = lifecycle.apply({
            "type": "check-completed", "eventId": "attempt-1-fail", "candidateId": sealed.candidate_id,
            "check": "fast", "conclusion": "failure", "failureClass": "infrastructure",
        })
        self.assertEqual(retry.code, OUTCOME_INFRASTRUCTURE_RETRY)
        self.assertEqual(retry.dispatch["attempt"], 2)
        self.start_fast(lifecycle, sealed.candidate_id, "attempt-2-start")
        stopped = lifecycle.apply({
            "type": "check-completed", "eventId": "attempt-2-fail", "candidateId": sealed.candidate_id,
            "check": "fast", "conclusion": "failure", "failureClass": "infrastructure",
        })
        self.assertEqual(stopped.code, OUTCOME_STOPPED_ALERT)
        self.assertEqual(lifecycle.state.status, "stopped-alert")
        self.assertEqual(lifecycle.state.candidates[sealed.candidate_id].attempts, 2)

    def test_code_failure_returns_to_development_without_retry(self) -> None:
        lifecycle = self.lifecycle()
        self.checkpoint(lifecycle, HEADS[0])
        sealed = self.seal(lifecycle, HEADS[0], 7)
        self.start_fast(lifecycle, sealed.candidate_id, "code-start")
        failed = lifecycle.apply({
            "type": "check-completed", "eventId": "code-fail", "candidateId": sealed.candidate_id,
            "check": "fast", "conclusion": "failure", "failureClass": "code",
        })
        self.assertEqual(failed.code, OUTCOME_CODE_FAILURE)
        self.assertIsNone(failed.dispatch)
        self.assertEqual(lifecycle.state.candidates[sealed.candidate_id].status, "code-failed")
        self.assertEqual(lifecycle.state.candidates[sealed.candidate_id].attempts, 1)

    def test_third_sealed_revision_is_hold_and_stop(self) -> None:
        lifecycle = self.lifecycle()
        for index, head in enumerate(HEADS[:3]):
            self.checkpoint(lifecycle, head)
            outcome = self.seal(lifecycle, head, 7, profile=f"sha256:profile-{index}")
            if index < 2:
                self.assertEqual(outcome.code, OUTCOME_CANDIDATE_SEALED)
            else:
                self.assertEqual(outcome.code, OUTCOME_HOLD_SEALED_CANDIDATE_LIMIT)
        self.assertEqual(lifecycle.state.sealed_revisions, 2)
        self.assertEqual(lifecycle.state.status, "stopped-alert")

    def test_store_reload_preserves_retry_counters_and_terminal_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CandidateLifecycleStore(Path(tmp) / "candidate-lifecycle.json")
            lifecycle = self.lifecycle()
            store.save(lifecycle)
            store.apply({"type": "checkpoint", "eventId": "checkpoint", "headCommit": HEADS[0]})
            sealed = store.load()
            seal = self.seal(sealed, HEADS[0], 7, event_id="seal")
            store.save(sealed)
            store.apply({"type": "check-started", "eventId": "start", "candidateId": seal.candidate_id, "check": "fast"})
            store.apply({
                "type": "check-completed", "eventId": "failure", "candidateId": seal.candidate_id,
                "check": "fast", "conclusion": "failure", "failureClass": "infrastructure",
            })
            reloaded = store.load()
            self.assertEqual(reloaded.state.candidates[seal.candidate_id].attempts, 1)
            self.assertEqual(reloaded.state.status, "infrastructure-retry")
            store.save(reloaded)
            with patch("scripts.gitops.coordinator.state.os.replace", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    store.save(self.lifecycle())
            self.assertEqual(store.load().state.status, "infrastructure-retry")


if __name__ == "__main__":
    unittest.main()
