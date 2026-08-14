"""W2-P2 Phase batch, sealing, gate, and negative-probe tests."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.gitops.coordinator.state import CandidateIdentity
from scripts.gitops.delivery_modes import (
    DeliveryConfig,
    MODE_ISSUE_PR,
    MODE_PHASE_INTEGRATION,
    effective_delivery_mode,
    recommended_v2_delivery_config,
    should_open_pr_for_branch,
    validate_risk_class,
)
from scripts.gitops.phase_integrator import (
    IssueTip,
    PhaseIntegrator,
    PhaseLifecycleError,
    phase_bugbot_request_allowed,
    phase_merge_eligibility,
    validate_issue_batch,
)

_TEMP_DIRS: list[tempfile.TemporaryDirectory[str]] = []


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def fixture_repo() -> tuple[Path, str, str, list[str]]:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    git(root, "init", "-q", "-b", "development")
    git(root, "config", "user.email", "tests@example.invalid")
    git(root, "config", "user.name", "W2-P2 tests")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", "base.txt")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-qb", "phase/demo")
    for number in (1, 2, 3):
        path = root / f"issue-{number}.txt"
        path.write_text(f"issue {number}\n", encoding="utf-8")
        git(root, "add", path.name)
        git(root, "commit", "-qm", f"issue {number}")
    head = git(root, "rev-parse", "HEAD")
    tips = [git(root, "rev-parse", "HEAD~2"), git(root, "rev-parse", "HEAD~1"), head]
    # Keep the TemporaryDirectory alive through the test process.
    _TEMP_DIRS.append(tmp)
    return root, base, head, tips


class PhaseBatchLifecycleTests(unittest.TestCase):
    def test_integrator_records_exact_acceptance_then_merges_issue_tip(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        git(root, "init", "-q", "-b", "development")
        git(root, "config", "user.email", "tests@example.invalid")
        git(root, "config", "user.name", "W2-P2 tests")
        (root / "base.txt").write_text("base\n", encoding="utf-8")
        git(root, "add", "base.txt")
        git(root, "commit", "-qm", "base")
        base = git(root, "rev-parse", "HEAD")
        git(root, "checkout", "-qb", "phase/demo")
        git(root, "checkout", "-qb", "issue/11-one")
        (root / "issue.txt").write_text("accepted issue\n", encoding="utf-8")
        git(root, "add", "issue.txt")
        git(root, "commit", "-qm", "issue 11")
        issue_sha = git(root, "rev-parse", "HEAD")
        git(root, "checkout", "phase/demo")
        integrator = PhaseIntegrator(root, repository="owner/name", phase_branch="phase/demo", phase_id="P2", immutable_base_sha=base)
        recorded = integrator.record_acceptance(IssueTip("issue/11-one", issue_sha, acceptance_sha=issue_sha, live_sha=issue_sha))
        self.assertFalse(recorded["acceptedIssues"][0]["included"])
        included = integrator.integrate_issue(IssueTip("issue/11-one", issue_sha, acceptance_sha=issue_sha, live_sha=issue_sha))
        self.assertTrue(included["acceptedIssues"][0]["included"])
        self.assertEqual(git(root, "rev-parse", "--abbrev-ref", "HEAD"), "phase/demo")
        self.assertTrue((root / "issue.txt").is_file())

    def test_three_issue_tips_create_one_draft_and_sealed_candidate(self) -> None:
        root, base, head, tips = fixture_repo()
        integrator = PhaseIntegrator(
            root,
            repository="owner/name",
            phase_branch="phase/demo",
            phase_id="P2",
            immutable_base_sha=base,
        )
        issues = [
            IssueTip(f"issue/{number}-part", sha, acceptance_sha=sha, included=True)
            for number, sha in zip((1, 2, 3), tips)
        ]
        record = integrator.aggregate(issues, phase_head_sha=head)
        self.assertEqual(len(record["acceptedIssues"]), 3)
        record = integrator.create_draft(
            head_sha=head,
            pr={"number": 7, "url": "https://example.invalid/pr/7", "base": "development"},
        )
        self.assertEqual(record["phasePr"]["number"], 7)
        with self.assertRaisesRegex(PhaseLifecycleError, "duplicate_phase_pr"):
            integrator.create_draft(
                head_sha=head,
                pr={"number": 8, "url": "https://example.invalid/pr/8", "base": "development"},
            )

        identity = CandidateIdentity("owner/name", head, git(root, "rev-parse", "HEAD^{tree}"), {}, "full")
        record = integrator.seal(head_sha=head, candidate_identity=identity)
        self.assertEqual((record["sealed"], record["sealRevision"]), (True, 1))
        self.assertEqual(phase_bugbot_request_allowed(record, live_head_sha=head), (False, "fast_gate_not_passed_for_current_seal"))
        record = integrator.update_gate("fast", status="passed", sha=head)
        self.assertEqual(phase_bugbot_request_allowed(record, live_head_sha=head), (True, "current_sealed_fast_pass"))
        record = integrator.update_gate("bugbot", status="requested", sha=head)
        self.assertEqual(phase_bugbot_request_allowed(record, live_head_sha=head), (False, "bugbot_already_requested"))
        integrator.update_gate("bugbot", status="passed", sha=head)
        integrator.update_gate("full", status="not-required", sha=head)
        final = integrator.load()
        self.assertIsNotNone(final)
        verdict = phase_merge_eligibility(final or {}, live_head_sha=head)
        self.assertTrue(verdict.eligible, verdict.detail)

    def test_negative_batch_validation_and_seal_rules(self) -> None:
        root, base, head, tips = fixture_repo()
        valid = lambda n, sha, **kwargs: IssueTip(f"issue/{n}-part", sha, acceptance_sha=kwargs.pop("acceptance_sha", sha), **kwargs)
        with self.assertRaisesRegex(PhaseLifecycleError, "duplicate_issue"):
            validate_issue_batch([valid(1, tips[0]), valid(1, tips[1])], immutable_base_sha=base, phase_head_sha=head, repo=root)
        with self.assertRaisesRegex(PhaseLifecycleError, "stale_issue_tip"):
            validate_issue_batch(
                [{"branch": "issue/1-part", "sha": tips[0], "accepted": True, "acceptanceSha": tips[0], "liveSha": "f" * 40}],
                immutable_base_sha=base,
                phase_head_sha=head,
                repo=root,
            )
        with self.assertRaisesRegex(PhaseLifecycleError, "acceptance_missing"):
            validate_issue_batch(
                [{"branch": "issue/1-part", "sha": tips[0], "accepted": True}],
                immutable_base_sha=base,
                phase_head_sha=head,
                repo=root,
            )
        with self.assertRaisesRegex(PhaseLifecycleError, "unproven_inclusion"):
            validate_issue_batch(
                [{"branch": "issue/1-part", "sha": "a" * 40, "accepted": True, "acceptanceSha": "a" * 40}],
                immutable_base_sha=base,
                phase_head_sha=head,
                repo=root,
            )
        with self.assertRaisesRegex(PhaseLifecycleError, "non_integrator_mutation"):
            PhaseIntegrator(root, repository="owner/name", phase_branch="phase/demo", phase_id="P2", immutable_base_sha=base, actor="worker")

        integrator = PhaseIntegrator(root, repository="owner/name", phase_branch="phase/demo", phase_id="P2", immutable_base_sha=base)
        integrator.aggregate([valid(1, tips[0], included=False)], phase_head_sha=head)
        identity = CandidateIdentity("owner/name", head, git(root, "rev-parse", "HEAD^{tree}"), {}, "full")
        with self.assertRaisesRegex(PhaseLifecycleError, "unincluded_issue"):
            integrator.seal(head_sha=head, candidate_identity=identity)

        integrator = PhaseIntegrator(root, repository="owner/name", phase_branch="phase/demo", phase_id="P3", immutable_base_sha=base)
        integrator.aggregate([valid(1, tips[0], included=True)], phase_head_sha=head)
        fast_identity = CandidateIdentity("owner/name", head, git(root, "rev-parse", "HEAD^{tree}"), {}, "fast")
        with self.assertRaisesRegex(PhaseLifecycleError, "candidate_profile_mismatch"):
            integrator.seal(head_sha=head, candidate_identity=fast_identity)

    def test_head_change_invalidates_candidate_and_allows_only_revision_two(self) -> None:
        root, base, head, tips = fixture_repo()
        integrator = PhaseIntegrator(root, repository="owner/name", phase_branch="phase/demo", phase_id="P2", immutable_base_sha=base)
        integrator.aggregate([IssueTip("issue/1-part", tips[0], acceptance_sha=tips[0], included=True)], phase_head_sha=head)
        identity = CandidateIdentity("owner/name", head, git(root, "rev-parse", "HEAD^{tree}"), {}, "full")
        integrator.seal(head_sha=head, candidate_identity=identity)
        integrator.update_gate("fast", status="passed", sha=head)
        (root / "late.txt").write_text("late\n", encoding="utf-8")
        git(root, "add", "late.txt")
        git(root, "commit", "-qm", "late phase movement")
        changed = git(root, "rev-parse", "HEAD")
        record = integrator.aggregate([IssueTip("issue/1-part", tips[0], acceptance_sha=tips[0], included=True)], phase_head_sha=changed)
        self.assertFalse(record["sealed"])
        self.assertEqual(record["fast"]["status"], "invalidated")
        second = CandidateIdentity("owner/name", changed, git(root, "rev-parse", "HEAD^{tree}"), {}, "full")
        record = integrator.seal(head_sha=changed, candidate_identity=second)
        self.assertEqual(record["sealRevision"], 2)
        with self.assertRaisesRegex(PhaseLifecycleError, "third_seal"):
            integrator.seal(head_sha=changed, candidate_identity=second)

    def test_mode_defaults_and_risk_exception_remain_compatible(self) -> None:
        self.assertEqual(recommended_v2_delivery_config().delivery_mode, MODE_PHASE_INTEGRATION)
        self.assertEqual(effective_delivery_mode(recommended_v2_delivery_config(), explicit_mode="issue-pr"), MODE_ISSUE_PR)
        self.assertEqual(validate_risk_class("security"), "security")
        decision = should_open_pr_for_branch(
            "issue/99-security",
            DeliveryConfig(delivery_mode=MODE_PHASE_INTEGRATION),
            risk_class="security",
            review_ready=True,
        )
        self.assertTrue(decision.open_pr)


if __name__ == "__main__":
    unittest.main()
