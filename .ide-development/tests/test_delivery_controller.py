"""WP-U02 delivery controller unit, negative, and contract tests."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.gitops import delivery_controller as controller
from scripts.gitops.coordinator import receipts
from scripts.ide_development.constants import RC_REQUIRED_SCHEMA_RELS


ROOT = Path(__file__).resolve().parents[2]
DIGEST = "sha256:" + ("b" * 64)
COMMAND_DIGEST = "sha256:" + ("c" * 64)
DEP_DIGEST = "sha256:" + ("d" * 64)
PROFILE_DIGEST = "sha256:" + ("e" * 64)
WORKFLOW_DIGEST = "sha256:" + ("f" * 64)


def _sha(n: int = 1) -> str:
    return f"{n:040x}"


def _identity(*, head: str, tree: str, repository: str = "owner/name", branch: str = "phase/next") -> dict[str, str]:
    return {
        "repository": repository,
        "sourceBranch": branch,
        "headCommit": head,
        "gitTree": tree,
        "dependencyDigest": DEP_DIGEST,
        "profileDigest": PROFILE_DIGEST,
        "workflowDigest": WORKFLOW_DIGEST,
    }


def _receipt(identity: dict[str, str]) -> dict[str, object]:
    raw = {
        "schemaVersion": 2,
        "candidateIdentity": identity,
        "workflowRunId": 501,
        "workflowRunAttempt": 1,
        "runnerLabel": "ubuntu-24.04-arm",
        "startedAt": "2026-08-18T01:00:00Z",
        "completedAt": "2026-08-18T01:01:00Z",
        "conclusion": "success",
        "commandDigest": COMMAND_DIGEST,
        "evidenceDigests": {"evidence/full.log": DIGEST},
    }
    return receipts.create_full_suite_receipt(raw).to_dict()


def _handoff(*, head: str, tree: str, base: str | None = None) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "kind": "phase-handoff",
        "repository": "owner/name",
        "phaseBranch": "phase/next",
        "phasePr": {"number": 11, "url": "https://github.com/owner/name/pull/11", "isDraft": True},
        "headCommit": head,
        "gitTree": tree,
        "baseCommit": base or _sha(9),
        "candidateRevision": "rev-1",
        "acceptedCommits": [{"branch": "issue/1-alpha", "sha": head, "order": 1}],
        "evidenceLocations": {
            "phaseRecord": ".linktrend/phase-delivery-record.json",
            "handoff": ".linktrend/phase-handoff.json",
        },
        "valid": True,
        "component": "phase_packager_coordinator",
    }


def _named_checks(head: str) -> dict[str, dict[str, str]]:
    return {
        name: {"status": "success", "sha": head}
        for name in controller.REQUIRED_CHECK_NAMES
    }


def _repository_ci(head: str, *, name: str = "Verify IDE Development") -> dict[str, object]:
    return {
        "required": [name],
        "results": {name: {"status": "success", "sha": head}},
    }


def _gates(head: str) -> dict[str, dict[str, str]]:
    return {
        "seal": {"status": "passed", "sha": head},
        "fast": {"status": "passed", "sha": head},
        "bugbot": {"status": "passed", "sha": head},
        "full": {"status": "passed", "sha": head},
    }


class DeliveryControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.head = _sha(1)
        self.tree = _sha(2)
        self.identity = _identity(head=self.head, tree=self.tree)
        self.receipt = _receipt(self.identity)
        self.handoff = _handoff(head=self.head, tree=self.tree)
        self.pr = {
            "number": 11,
            "isDraft": False,
            "state": "open",
            "head": "phase/next",
            "base": "development",
            "headSha": self.head,
            "mergeableState": "MERGEABLE",
        }
        self.github = controller.MemoryGitHub(repository="owner/name")
        self.github.prs[11] = dict(self.pr)
        self.github.refs["development"] = _sha(8)
        self.github.refs["staging"] = _sha(7)
        self.github.refs["main"] = _sha(6)

    def _deliver(self, **kwargs):
        defaults = dict(
            github=self.github,
            repository="owner/name",
            handoff=self.handoff,
            pr=self.pr,
            live_head=self.head,
            live_tree=self.tree,
            gate_payload=_gates(self.head),
            named_checks=_named_checks(self.head),
            repository_ci=_repository_ci(self.head),
            receipt=self.receipt,
            candidate_identity=self.identity,
            role="operator",
        )
        defaults.update(kwargs)
        return controller.deliver_phase_to_development(**defaults)

    def _verify(self, **kwargs):
        defaults = dict(
            handoff=self.handoff,
            pr=self.pr,
            repository="owner/name",
            live_head=self.head,
            live_tree=self.tree,
            gate_payload=_gates(self.head),
            named_checks=_named_checks(self.head),
            repository_ci=_repository_ci(self.head),
            receipt=self.receipt,
            candidate_identity=self.identity,
        )
        defaults.update(kwargs)
        return controller.verify_development_eligibility(**defaults)

    def test_component_replaces_nonexistent_integrator_handoff(self) -> None:
        self.assertTrue(controller.IS_DELIVERY_CONTROLLER)
        self.assertEqual(controller.COMPONENT_KIND, "delivery_controller")
        self.assertIn("Replaces the nonexistent Integrator", controller.__doc__)
        self.assertFalse(getattr(controller, "IS_PHASE_PACKAGER", False))

    def test_valid_phase_pr_reaches_development_without_external_integrator(self) -> None:
        result = self._deliver()
        self.assertEqual(result["status"], "merged")
        self.assertEqual(result["stage"], "development")
        self.assertFalse(result["directPush"])
        self.assertEqual(result["component"], "delivery_controller")
        self.assertEqual(len(self.github.merges), 1)
        self.assertEqual(self.github.protected_push_attempts[0]["branch"], "development")

    def test_worker_cannot_invoke_self_merge_path(self) -> None:
        with self.assertRaisesRegex(controller.ControllerError, "worker_self_merge_forbidden"):
            controller.merge_to_development(
                github=self.github,
                repository="owner/name",
                pr_number=11,
                expected_head=self.head,
                role="worker",
            )
        with self.assertRaisesRegex(controller.ControllerError, "worker_self_merge_forbidden"):
            controller.require_controller_role("implementer")

    def test_stale_or_changed_pr_is_rejected(self) -> None:
        with self.assertRaisesRegex(controller.ControllerError, "stale_pr_head"):
            controller.accept_phase_pr(
                {**self.pr, "headSha": _sha(99)},
                self.handoff,
                repository="owner/name",
                live_head=self.head,
                live_tree=self.tree,
            )
        stale_handoff = dict(self.handoff, headCommit=_sha(3), valid=True)
        with self.assertRaisesRegex(controller.ControllerError, "handoff_stale_head"):
            controller.accept_phase_pr(
                self.pr,
                stale_handoff,
                repository="owner/name",
                live_head=self.head,
                live_tree=self.tree,
            )

    def test_failed_missing_or_skipped_gates_are_rejected(self) -> None:
        missing = dict(_named_checks(self.head))
        del missing["Linktrend Full Suite"]
        with self.assertRaisesRegex(controller.ControllerError, "required_gate_missing"):
            controller.verify_development_eligibility(
                handoff=self.handoff,
                pr=self.pr,
                repository="owner/name",
                live_head=self.head,
                live_tree=self.tree,
                gate_payload=_gates(self.head),
                named_checks=missing,
                repository_ci=_repository_ci(self.head),
                receipt=self.receipt,
                candidate_identity=self.identity,
            )
        skipped = dict(_named_checks(self.head))
        skipped["Linktrend Fast Checks"] = {"status": "skipped", "sha": self.head}
        with self.assertRaisesRegex(controller.ControllerError, "required_gate_skipped"):
            controller.verify_development_eligibility(
                handoff=self.handoff,
                pr=self.pr,
                repository="owner/name",
                live_head=self.head,
                live_tree=self.tree,
                gate_payload=_gates(self.head),
                named_checks=skipped,
                repository_ci=_repository_ci(self.head),
                receipt=self.receipt,
                candidate_identity=self.identity,
            )
        failed_gates = dict(_gates(self.head), fast={"status": "failed", "sha": self.head})
        with self.assertRaisesRegex(controller.ControllerError, "fast_not_passed"):
            controller.verify_development_eligibility(
                handoff=self.handoff,
                pr=self.pr,
                repository="owner/name",
                live_head=self.head,
                live_tree=self.tree,
                gate_payload=failed_gates,
                named_checks=_named_checks(self.head),
                repository_ci=_repository_ci(self.head),
                receipt=self.receipt,
                candidate_identity=self.identity,
            )

    def test_receipt_mismatch_or_forgery_is_rejected(self) -> None:
        forged = dict(self.receipt, receiptDigest="sha256:" + ("a" * 64))
        with self.assertRaisesRegex(controller.ControllerError, "receipt_rejected"):
            controller.verify_development_eligibility(
                handoff=self.handoff,
                pr=self.pr,
                repository="owner/name",
                live_head=self.head,
                live_tree=self.tree,
                gate_payload=_gates(self.head),
                named_checks=_named_checks(self.head),
                repository_ci=_repository_ci(self.head),
                receipt=forged,
                candidate_identity=self.identity,
            )

    def test_staging_reuses_exact_receipt_without_full_rerun(self) -> None:
        result = controller.promote_to_staging(
            github=self.github,
            repository="owner/name",
            development_sha=self.head,
            staging_sha=_sha(7),
            candidate_sha=self.head,
            candidate_tree=self.tree,
            receipt=self.receipt,
            candidate_identity=self.identity,
            release_gate={"status": "passed", "testProfile": "release", "fullSuiteInvoked": False},
            role="operator",
        )
        self.assertEqual(result["status"], "merged")
        self.assertEqual(result["stage"], "staging")
        self.assertTrue(result["receiptReused"])
        self.assertFalse(result["fullSuiteRerun"])
        marker = json.loads(
            re.search(r"<!-- linktrend-promote:\s*(\{.*?\})\s*-->", self.github.prs[1]["body"]).group(1)
        )
        self.assertEqual(marker["fullRunId"], self.receipt["workflowRunId"])
        with self.assertRaisesRegex(controller.ControllerError, "full_suite_reentered"):
            controller.promote_to_staging(
                github=self.github,
                repository="owner/name",
                development_sha=self.head,
                staging_sha=_sha(7),
                candidate_sha=self.head,
                candidate_tree=self.tree,
                receipt=self.receipt,
                candidate_identity=self.identity,
                release_gate={"status": "passed", "testProfile": "release"},
                role="operator",
                full_suite_invoked=True,
            )

    def test_staged_rollout_uses_configured_stage_names_on_critical_path(self) -> None:
        rollout = controller.StagedRolloutConfig.from_mapping(
            {
                "phaseBranchPrefix": "candidate/",
                "developmentBranch": "integrated",
                "stagingBranch": "canary",
                "mainBranch": "production",
                "requiredChecks": ["System Fast", "System Full"],
            }
        )
        result = controller.promote_to_staging(
            github=self.github,
            repository="owner/name",
            development_sha=self.head,
            staging_sha=_sha(7),
            candidate_sha=self.head,
            candidate_tree=self.tree,
            receipt=self.receipt,
            candidate_identity=self.identity,
            release_gate={"status": "passed", "testProfile": "release", "fullSuiteInvoked": False},
            role="operator",
            rollout=rollout,
        )
        self.assertEqual(result["stage"], "canary")
        self.assertEqual(result["promoteBranch"], f"promote/canary/{self.head[:12]}")
        self.assertEqual(self.github.prs[1]["base"], "canary")

    def test_staged_rollout_rejects_duplicate_stage_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate_rollout_branch"):
            controller.StagedRolloutConfig.from_mapping(
                {"developmentBranch": "same", "stagingBranch": "same"}
            )

    def test_changed_staging_content_is_rejected(self) -> None:
        with self.assertRaisesRegex(controller.ControllerError, "changed_staging_content"):
            controller.promote_to_staging(
                github=self.github,
                repository="owner/name",
                development_sha=self.head,
                staging_sha=_sha(7),
                candidate_sha=self.head,
                candidate_tree=_sha(99),
                receipt=self.receipt,
                candidate_identity=self.identity,
                release_gate={"status": "passed", "testProfile": "release"},
                role="operator",
            )

    def test_main_waits_for_explicit_founder_approval(self) -> None:
        prepared = controller.prepare_main_promotion(
            github=self.github,
            repository="owner/name",
            staging_sha=self.head,
            main_sha=_sha(6),
            candidate_sha=self.head,
            receipt=self.receipt,
            candidate_identity=self.identity,
            release_gate={"status": "passed", "testProfile": "release"},
            role="operator",
        )
        self.assertEqual(prepared["status"], "waiting_founder_approval")
        self.assertFalse(prepared["founderApprovalInferred"])
        marker = json.loads(
            re.search(r"<!-- linktrend-promote:\s*(\{.*?\})\s*-->", self.github.prs[1]["body"]).group(1)
        )
        self.assertEqual(marker["fullRunId"], self.receipt["workflowRunId"])
        with self.assertRaisesRegex(controller.ControllerError, "founder_approval_missing"):
            controller.complete_main_promotion(
                github=self.github,
                repository="owner/name",
                pr_number=int(prepared["pr"]),
                expected_head=self.head,
                source_sha=self.head,
                base_sha=_sha(6),
                approval={},
                receipt=self.receipt,
                role="operator",
            )

    def test_promotion_rejects_missing_or_invalid_full_run_id(self) -> None:
        for invalid in (None, 0, True, "not-a-run"):
            bad_receipt = dict(self.receipt)
            if invalid is None:
                bad_receipt.pop("workflowRunId", None)
            else:
                bad_receipt["workflowRunId"] = invalid
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                controller.ControllerError, "receipt_workflow_run_invalid"
            ):
                controller._receipt_workflow_run_id(bad_receipt)

    def test_ambiguous_or_stale_main_approval_is_rejected(self) -> None:
        prepared = controller.prepare_main_promotion(
            github=self.github,
            repository="owner/name",
            staging_sha=self.head,
            main_sha=_sha(6),
            candidate_sha=self.head,
            receipt=self.receipt,
            candidate_identity=self.identity,
            release_gate={"status": "passed", "testProfile": "release"},
            role="operator",
        )
        with self.assertRaisesRegex(controller.ControllerError, "founder_approval_ambiguous"):
            controller.complete_main_promotion(
                github=self.github,
                repository="owner/name",
                pr_number=int(prepared["pr"]),
                expected_head=self.head,
                source_sha=self.head,
                base_sha=_sha(6),
                approval={
                    "decision": "approve",
                    "inferredFromGreenCi": True,
                    "sourceSha": self.head,
                    "baseSha": _sha(6),
                    "prHeadSha": self.head,
                    "receiptDigest": receipts.compute_receipt_digest(self.receipt),
                },
                receipt=self.receipt,
                role="operator",
            )
        with self.assertRaisesRegex(controller.ControllerError, "stale_"):
            controller.complete_main_promotion(
                github=self.github,
                repository="owner/name",
                pr_number=int(prepared["pr"]),
                expected_head=self.head,
                source_sha=self.head,
                base_sha=_sha(6),
                approval={
                    "decision": "approve",
                    "sourceSha": _sha(55),
                    "baseSha": _sha(6),
                    "prHeadSha": self.head,
                    "receiptDigest": receipts.compute_receipt_digest(self.receipt),
                },
                receipt=self.receipt,
                role="operator",
            )

    def test_protected_merge_rejection_stops_without_direct_push(self) -> None:
        self.github.merge_rejections[11] = "branch protection prevented merge"
        stopped = controller.deliver_phase_to_development(
            github=self.github,
            repository="owner/name",
            handoff=self.handoff,
            pr=self.pr,
            live_head=self.head,
            live_tree=self.tree,
            gate_payload=_gates(self.head),
            named_checks=_named_checks(self.head),
            repository_ci=_repository_ci(self.head),
            receipt=self.receipt,
            candidate_identity=self.identity,
            role="operator",
        )
        self.assertEqual(stopped["status"], "stopped")
        self.assertEqual(stopped["code"], "protected_merge_rejected")
        self.assertFalse(stopped["directPushAttempted"])
        self.assertFalse(stopped["bypassAttempted"])

    def test_temporary_branches_deleted_only_after_successful_merges(self) -> None:
        with self.assertRaisesRegex(controller.ControllerError, "cleanup_before_success"):
            controller.cleanup_temporary_branches(
                github=self.github,
                repository="owner/name",
                branches=["promote/staging/aaaaaaaaaaaa"],
                merge_succeeded=False,
                controller_owned={"promote/staging/aaaaaaaaaaaa": True},
            )
        self.github.refs["promote/staging/aaaaaaaaaaaa"] = self.head
        self.github.refs["issue/1-unique"] = self.head
        cleaned = controller.cleanup_temporary_branches(
            github=self.github,
            repository="owner/name",
            branches=["promote/staging/aaaaaaaaaaaa", "issue/1-unique"],
            merge_succeeded=True,
            controller_owned={"promote/staging/aaaaaaaaaaaa": True},
        )
        self.assertEqual(cleaned["deleted"], ["promote/staging/aaaaaaaaaaaa"])
        self.assertEqual(cleaned["preserved"], ["issue/1-unique"])

    def test_controller_identical_across_supported_agents(self) -> None:
        result = controller.run_identical_under_agents(
            "merge-development",
            {"head": self.head, "tree": self.tree},
            [
                {},
                {"CURSOR_AGENT": "cursor"},
                {"CODEX_HOME": "/tmp/codex"},
                {"TERRA_AGENT": "terra"},
            ],
        )
        self.assertEqual(result["status"], "identical")
        self.assertEqual(len({row["payloadDigest"] for row in result["results"]}), 1)

    def test_draft_cross_repo_and_conflict_rejected(self) -> None:
        with self.assertRaisesRegex(controller.ControllerError, "draft_pr"):
            controller.accept_phase_pr(
                {**self.pr, "isDraft": True},
                self.handoff,
                repository="owner/name",
                live_head=self.head,
                live_tree=self.tree,
            )
        with self.assertRaisesRegex(controller.ControllerError, "cross_repository"):
            controller.accept_phase_pr(
                {**self.pr, "crossRepository": True},
                self.handoff,
                repository="owner/name",
                live_head=self.head,
                live_tree=self.tree,
            )
        with self.assertRaisesRegex(controller.ControllerError, "merge_conflict"):
            controller.verify_development_eligibility(
                handoff=self.handoff,
                pr=self.pr,
                repository="owner/name",
                live_head=self.head,
                live_tree=self.tree,
                gate_payload=_gates(self.head),
                named_checks=_named_checks(self.head),
                repository_ci=_repository_ci(self.head),
                receipt=self.receipt,
                candidate_identity=self.identity,
                conflict=True,
            )

    def test_complete_main_success_path(self) -> None:
        prepared = controller.prepare_main_promotion(
            github=self.github,
            repository="owner/name",
            staging_sha=self.head,
            main_sha=_sha(6),
            candidate_sha=self.head,
            receipt=self.receipt,
            candidate_identity=self.identity,
            release_gate={"status": "passed", "testProfile": "release"},
            role="founder",
        )
        completed = controller.complete_main_promotion(
            github=self.github,
            repository="owner/name",
            pr_number=int(prepared["pr"]),
            expected_head=self.head,
            source_sha=self.head,
            base_sha=_sha(6),
            approval={
                "decision": "approve",
                "sourceSha": self.head,
                "baseSha": _sha(6),
                "prHeadSha": self.head,
                "receiptDigest": receipts.compute_receipt_digest(self.receipt),
            },
            receipt=self.receipt,
            role="founder",
        )
        self.assertEqual(completed["status"], "merged")
        self.assertTrue(completed["founderApproval"])

    def test_production_live_github_adapter_is_executable(self) -> None:
        self.assertTrue(hasattr(controller, "LiveGitHub"))
        self.assertTrue(callable(controller.resolve_production_github))
        with self.assertRaisesRegex(controller.ControllerError, "missing_github_credentials"):
            controller.resolve_production_github("owner/name")
        calls: list[tuple[str, str]] = []

        def transport(method: str, url: str, token: str, body):
            calls.append((method, url))
            self.assertEqual(token, "tok")
            if method == "GET" and url.endswith("/pulls/11"):
                return {
                    "number": 11,
                    "html_url": "https://github.com/owner/name/pull/11",
                    "draft": False,
                    "state": "open",
                    "head": {"ref": "phase/next", "sha": self.head, "repo": {"full_name": "owner/name"}},
                    "base": {"ref": "development"},
                    "mergeable_state": "clean",
                }
            if method == "PUT" and url.endswith("/merge"):
                return {"merged": True, "sha": _sha(4)}
            raise AssertionError((method, url))

        live = controller.LiveGitHub(repository="owner/name", automation_token="tok", transport=transport)
        merged = live.merge_pull_request(repository="owner/name", number=11, expected_head=self.head)
        self.assertEqual(merged["mergeCommitSha"], _sha(4))
        self.assertFalse(merged["directPush"])
        self.assertEqual(calls[0][0], "GET")
        self.assertEqual(calls[1][0], "PUT")
        with self.assertRaisesRegex(controller.ControllerError, "direct_push_forbidden"):
            live.push_protected(repository="owner/name", branch="development", sha=self.head)

    def test_staging_and_main_require_exact_source_sha_equality(self) -> None:
        with self.assertRaisesRegex(controller.ControllerError, "promotion_source_mismatch"):
            controller.promote_to_staging(
                github=self.github,
                repository="owner/name",
                development_sha=self.head,
                staging_sha=_sha(7),
                candidate_sha=_sha(99),
                candidate_tree=self.tree,
                receipt=self.receipt,
                candidate_identity=self.identity,
                release_gate={"status": "passed", "testProfile": "release"},
                role="operator",
            )
        with self.assertRaisesRegex(controller.ControllerError, "promotion_source_mismatch"):
            controller.prepare_main_promotion(
                github=self.github,
                repository="owner/name",
                staging_sha=self.head,
                main_sha=_sha(6),
                candidate_sha=_sha(88),
                receipt=self.receipt,
                candidate_identity=self.identity,
                release_gate={"status": "passed", "testProfile": "release"},
                role="operator",
            )
        with self.assertRaisesRegex(controller.ControllerError, "promotion_source_mismatch"):
            controller.complete_main_promotion(
                github=self.github,
                repository="owner/name",
                pr_number=11,
                expected_head=self.head,
                source_sha=_sha(55),
                base_sha=_sha(6),
                approval={
                    "decision": "approve",
                    "sourceSha": _sha(55),
                    "baseSha": _sha(6),
                    "prHeadSha": self.head,
                    "receiptDigest": receipts.compute_receipt_digest(self.receipt),
                },
                receipt=self.receipt,
                role="founder",
            )

    def test_infrastructure_retry_bound_is_enforced(self) -> None:
        attempts = {"n": 0}

        def flaky() -> str:
            attempts["n"] += 1
            raise controller.ControllerError("github_unavailable", f"attempt-{attempts['n']}")

        with self.assertRaisesRegex(controller.ControllerError, "infrastructure_retries_exhausted"):
            controller.call_with_infrastructure_retry(flaky)
        self.assertEqual(attempts["n"], controller.INFRA_RETRY_LIMIT)

        attempts["n"] = 0

        def recover() -> str:
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise controller.ControllerError("network_error", "transient")
            return "ok"

        self.assertEqual(controller.call_with_infrastructure_retry(recover), "ok")
        self.assertEqual(attempts["n"], 2)

        with self.assertRaisesRegex(controller.ControllerError, "stale_pr_head"):
            controller.call_with_infrastructure_retry(
                lambda: (_ for _ in ()).throw(controller.ControllerError("stale_pr_head", "no-retry"))
            )

    def test_repository_owned_ci_is_distinct_eligibility_gate(self) -> None:
        ok = self._verify()
        self.assertEqual(ok["repositoryCi"], "passed")
        with self.assertRaisesRegex(controller.ControllerError, "repository_ci_missing"):
            self._verify(repository_ci={"required": [], "results": {}})
        with self.assertRaisesRegex(controller.ControllerError, "repository_ci_failed"):
            self._verify(
                repository_ci={
                    "required": ["Verify IDE Development"],
                    "results": {"Verify IDE Development": {"status": "failure", "sha": self.head}},
                }
            )
        with self.assertRaisesRegex(controller.ControllerError, "repository_ci_stale"):
            self._verify(
                repository_ci={
                    "required": ["Verify IDE Development"],
                    "results": {"Verify IDE Development": {"status": "success", "sha": _sha(99)}},
                }
            )
        with self.assertRaisesRegex(controller.ControllerError, "repository_ci_collides_with_system"):
            self._verify(
                repository_ci={
                    "required": ["Linktrend Fast Checks"],
                    "results": {"Linktrend Fast Checks": {"status": "success", "sha": self.head}},
                }
            )

    def test_live_github_promote_ref_exact_binding_and_wrong_tip(self) -> None:
        branch = f"promote/staging/{self.head[:12]}"
        refs: dict[str, str] = {branch: _sha(99)}
        calls: list[tuple[str, str]] = []

        def transport(method: str, url: str, token: str, body):
            calls.append((method, url))
            self.assertEqual(token, "tok")
            if method == "GET" and "/git/refs/heads/" in url:
                name = url.rsplit("/git/refs/heads/", 1)[-1]
                if name not in refs:
                    raise controller.ControllerError("github_api_failed", f"GET {url} -> 404: not found")
                return {"ref": f"refs/heads/{name}", "object": {"sha": refs[name]}}
            if method == "PATCH" and "/git/refs/heads/" in url:
                name = url.rsplit("/git/refs/heads/", 1)[-1]
                refs[name] = str(body["sha"])
                return {"ref": f"refs/heads/{name}", "object": {"sha": refs[name]}}
            if method == "POST" and url.endswith("/git/refs"):
                name = str(body["ref"]).removeprefix("refs/heads/")
                refs[name] = str(body["sha"])
                return {"ref": body["ref"], "object": {"sha": body["sha"]}}
            if method == "POST" and url.endswith("/pulls"):
                return {
                    "number": 42,
                    "html_url": "https://github.com/owner/name/pull/42",
                    "draft": False,
                    "state": "open",
                    "head": {"ref": branch, "sha": self.head, "repo": {"full_name": "owner/name"}},
                    "base": {"ref": "staging"},
                }
            if method == "GET" and url.endswith("/pulls/42"):
                return {
                    "number": 42,
                    "html_url": "https://github.com/owner/name/pull/42",
                    "draft": False,
                    "state": "open",
                    "head": {"ref": branch, "sha": refs[branch], "repo": {"full_name": "owner/name"}},
                    "base": {"ref": "staging"},
                    "mergeable_state": "clean",
                }
            raise AssertionError((method, url, body))

        live = controller.LiveGitHub(repository="owner/name", automation_token="tok", transport=transport)
        # Existing wrong tip must be rewritten to exact head_sha before PR open.
        pr = live.create_pull_request(
            repository="owner/name",
            head=branch,
            base="staging",
            title="promote",
            body="body",
            head_sha=self.head,
        )
        self.assertEqual(refs[branch], self.head)
        self.assertEqual(pr["headSha"], self.head)
        self.assertTrue(any(method == "PATCH" for method, _ in calls))

        # Adversarial: remote remains wrong after write → fail closed.
        def bad_transport(method: str, url: str, token: str, body):
            if method == "GET" and "/git/refs/heads/" in url:
                return {"object": {"sha": _sha(77)}}
            if method in {"PATCH", "POST"} and "git/refs" in url:
                return {"object": {"sha": _sha(77)}}
            raise AssertionError((method, url))

        bad = controller.LiveGitHub(repository="owner/name", automation_token="tok", transport=bad_transport)
        with self.assertRaisesRegex(controller.ControllerError, "promote_ref_mismatch"):
            bad.ensure_promote_ref(repository="owner/name", branch=branch, head_sha=self.head)

        # Successful create path when ref is absent.
        fresh_branch = f"promote/main/{self.head[:12]}"
        fresh_refs: dict[str, str] = {}

        def create_transport(method: str, url: str, token: str, body):
            if method == "GET" and "/git/refs/heads/" in url:
                name = url.rsplit("/git/refs/heads/", 1)[-1]
                if name not in fresh_refs:
                    raise controller.ControllerError("github_api_failed", f"GET {url} -> 404: missing")
                return {"object": {"sha": fresh_refs[name]}}
            if method == "POST" and url.endswith("/git/refs"):
                name = str(body["ref"]).removeprefix("refs/heads/")
                fresh_refs[name] = str(body["sha"])
                return {"object": {"sha": body["sha"]}}
            if method == "POST" and url.endswith("/pulls"):
                return {"number": 7}
            if method == "GET" and url.endswith("/pulls/7"):
                return {
                    "number": 7,
                    "html_url": "https://github.com/owner/name/pull/7",
                    "draft": False,
                    "state": "open",
                    "head": {"ref": fresh_branch, "sha": self.head, "repo": {"full_name": "owner/name"}},
                    "base": {"ref": "main"},
                }
            raise AssertionError((method, url))

        creator = controller.LiveGitHub(repository="owner/name", automation_token="tok", transport=create_transport)
        created = creator.create_pull_request(
            repository="owner/name",
            head=fresh_branch,
            base="main",
            title="main",
            body="body",
            head_sha=self.head,
        )
        self.assertEqual(fresh_refs[fresh_branch], self.head)
        self.assertEqual(created["headSha"], self.head)

    def test_cleanup_cli_requires_truthful_merge_evidence(self) -> None:
        branch = f"promote/staging/{self.head[:12]}"
        with self.assertRaisesRegex(controller.ControllerError, "cleanup_before_success"):
            controller.authorize_cleanup_from_evidence({}, [branch])
        with self.assertRaisesRegex(controller.ControllerError, "cleanup_before_success"):
            controller.authorize_cleanup_from_evidence({"status": "waiting"}, [branch])
        with self.assertRaisesRegex(controller.ControllerError, "cleanup_before_success"):
            controller.authorize_cleanup_from_evidence(
                {"status": "merged", "promoteBranch": "promote/staging/deadbeefcafe"},
                [branch],
            )
        owned = controller.authorize_cleanup_from_evidence(
            {"status": "merged", "promoteBranch": branch},
            [branch],
        )
        self.assertEqual(owned, {branch: True})

        evidence_path = Path(tempfile.mkdtemp()) / "merge.json"
        evidence_path.write_text(json.dumps({"status": "merged", "promoteBranch": branch}), encoding="utf-8")
        self.github.refs[branch] = self.head
        with mock.patch.dict(
            os.environ,
            {"AUTOMATION_TOKEN": "tok", "AUTOMATION_TOKEN_SOURCE": "github_token"},
            clear=False,
        ):
            with mock.patch.object(controller, "resolve_production_github", return_value=self.github):
                rc = controller.main(
                    [
                        "cleanup",
                        "--repository",
                        "owner/name",
                        "--role",
                        "operator",
                        "--branches",
                        branch,
                        "--merge-evidence-json",
                        str(evidence_path),
                    ]
                )
                self.assertEqual(rc, 0)
                self.assertIn(branch, self.github.deleted_refs)
                rc_fail = controller.main(
                    [
                        "cleanup",
                        "--repository",
                        "owner/name",
                        "--role",
                        "operator",
                        "--branches",
                        branch,
                    ]
                )
                self.assertEqual(rc_fail, 2)

    def test_production_github_accepts_gh_token_without_automation_token(self) -> None:
        saved = {
            key: os.environ.pop(key, None)
            for key in ("AUTOMATION_TOKEN", "AUTOMATION_TOKEN_SOURCE", "GH_TOKEN", "GITHUB_TOKEN")
        }
        try:
            os.environ["GH_TOKEN"] = "ghs_phase_api"
            live = controller.resolve_production_github("owner/name")
            self.assertEqual(live.automation_token, "ghs_phase_api")
            os.environ.pop("GH_TOKEN", None)
            os.environ["AUTOMATION_TOKEN"] = "ghs_publisher"
            os.environ["AUTOMATION_TOKEN_SOURCE"] = "github_token"
            with self.assertRaisesRegex(controller.ControllerError, "legacy_publisher_token_not_canonical"):
                controller.resolve_production_github("owner/name")
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_index_manifest_schema_and_hosted_fast_cover_controller(self) -> None:
        index = (ROOT / ".ide-development/INDEX.yaml").read_text(encoding="utf-8")
        self.assertIn("schemas/delivery-operation.schema.json", index)
        self.assertIn("core/managed-core/schemas/delivery-operation.schema.json", RC_REQUIRED_SCHEMA_RELS)
        manifest = json.loads((ROOT / ".ide-development/MANIFEST.json").read_text(encoding="utf-8"))
        sources = {row["source"] for row in manifest["files"]}
        self.assertIn("core/managed-core/schemas/delivery-operation.schema.json", sources)
        self.assertIn("scripts/gitops/delivery_controller.py", sources)
        self.assertIn("scripts/tests/test_delivery_controller.py", sources)
        doctrine = (ROOT / ".ide-development/content/doctrine/AUTONOMOUS-GIT-OPERATIONS.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("delivery controller", doctrine.lower())
        self.assertNotIn("waits indefinitely for an undefined merge actor", doctrine.lower())
        agents = (ROOT / ".ide-development/platforms/codex/AGENTS.managed-section.md").read_text(encoding="utf-8")
        self.assertIn("delivery controller", agents.lower())
        self.assertNotIn("Integrator merges to `development`", agents)
        bootstrap = (ROOT / ".cursor/rules/cursor-gitops-bootstrap.mdc").read_text(encoding="utf-8")
        self.assertIn("delivery controller", bootstrap.lower())
        self.assertNotIn("Integrator merges only when", bootstrap)
        branching = (ROOT / ".cursor/rules/linktrend-git-branching.mdc").read_text(encoding="utf-8")
        self.assertIn("delivery controller", branching.lower())
        self.assertNotIn("→ Integrator", branching)
        protection = (ROOT / ".ide-development/content/doctrine/REPOSITORY-PROTECTION.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("delivery controller may auto-merge", protection)
        self.assertNotIn("so the Integrator may auto-merge", protection)
        schema = json.loads(
            (ROOT / ".ide-development/schemas/delivery-operation.schema.json").read_text(encoding="utf-8")
        )
        record = controller.write_operation_record(
            Path(tempfile.mkdtemp()) / "delivery-operation.json",
            {
                "status": "merged",
                "stage": "development",
                "pr": 11,
                "testedHead": self.head,
                "mergeCommitSha": _sha(3),
                "directPush": False,
            },
        )
        for key in schema["required"]:
            self.assertIn(key, record)

    def _consolidation_evidence(self, *, keeper: int = 12, replacement: int = 10) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "kind": "phase-consolidation-evidence",
            "repository": "owner/name",
            "phaseBranch": "phase/next",
            "base": "development",
            "keeper": {
                "number": keeper,
                "url": f"https://github.com/owner/name/pull/{keeper}",
                "head": "phase/next",
                "headSha": self.head,
            },
            "replacements": [
                {
                    "number": replacement,
                    "url": f"https://github.com/owner/name/pull/{replacement}",
                    "head": "phase/next",
                    "headSha": self.head,
                    "reason": "stale_duplicate",
                }
            ],
        }

    def test_phase_consolidation_requires_controller_and_explicit_evidence(self) -> None:
        self.github.prs[12] = {
            "number": 12,
            "url": "https://github.com/owner/name/pull/12",
            "isDraft": True,
            "state": "open",
            "head": "phase/next",
            "base": "development",
            "headSha": self.head,
        }
        self.github.prs[10] = {
            "number": 10,
            "url": "https://github.com/owner/name/pull/10",
            "isDraft": True,
            "state": "open",
            "head": "phase/next",
            "base": "development",
            "headSha": self.head,
        }
        with self.assertRaisesRegex(controller.ControllerError, "worker_self_merge_forbidden"):
            controller.authorize_phase_consolidation(
                github=self.github,
                repository="owner/name",
                evidence=self._consolidation_evidence(),
                role="implementer",
            )
        with self.assertRaisesRegex(controller.ControllerError, "keeper_evidence_missing"):
            controller.validate_phase_consolidation_evidence(
                {
                    "schemaVersion": 1,
                    "kind": "phase-consolidation-evidence",
                    "repository": "owner/name",
                    "phaseBranch": "phase/next",
                    "replacements": [{"number": 10, "reason": "stale_duplicate"}],
                },
                repository="owner/name",
            )
        with self.assertRaisesRegex(controller.ControllerError, "replacement_evidence_missing"):
            controller.validate_phase_consolidation_evidence(
                {
                    "schemaVersion": 1,
                    "kind": "phase-consolidation-evidence",
                    "repository": "owner/name",
                    "phaseBranch": "phase/next",
                    "keeper": {"number": 12, "head": "phase/next"},
                    "replacements": [],
                },
                repository="owner/name",
            )

    def test_phase_consolidation_closes_named_drafts_and_writes_receipt(self) -> None:
        self.github.prs[12] = {
            "number": 12,
            "url": "https://github.com/owner/name/pull/12",
            "isDraft": True,
            "state": "open",
            "head": "phase/next",
            "base": "development",
            "headSha": self.head,
        }
        self.github.prs[10] = {
            "number": 10,
            "url": "https://github.com/owner/name/pull/10",
            "isDraft": True,
            "state": "open",
            "head": "phase/next",
            "base": "development",
            "headSha": self.head,
        }
        record_path = Path(tempfile.mkdtemp()) / "delivery-operation.json"
        first = controller.authorize_phase_consolidation(
            github=self.github,
            repository="owner/name",
            evidence=self._consolidation_evidence(),
            role="operator",
            record_path=record_path,
        )
        self.assertEqual(first["status"], "consolidated")
        self.assertEqual(first["kind"], "phase-consolidation-receipt")
        self.assertEqual(first["keeper"]["number"], 12)
        self.assertEqual(first["closed"][0]["number"], 10)
        self.assertFalse(first["merged"])
        self.assertFalse(first["refDeleted"])
        self.assertFalse(first["idempotent"])
        self.assertEqual(self.github.closed_numbers, [10])
        self.assertEqual(self.github.merges, [])
        self.assertEqual(self.github.deleted_refs, [])
        self.assertEqual(self.github.prs[12]["state"], "open")
        saved = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["kind"], "phase-consolidation-receipt")
        self.assertEqual(saved["receiptDigest"], first["receiptDigest"])
        second = controller.authorize_phase_consolidation(
            github=self.github,
            repository="owner/name",
            evidence=self._consolidation_evidence(),
            role="coordinator",
        )
        self.assertTrue(second["idempotent"])
        self.assertEqual(second["alreadyClosed"][0]["number"], 10)
        self.assertEqual(self.github.closed_numbers, [10])

    def test_phase_consolidation_rejects_protected_and_non_draft(self) -> None:
        self.github.prs[12] = {
            "number": 12,
            "url": "https://github.com/owner/name/pull/12",
            "isDraft": True,
            "state": "open",
            "head": "phase/next",
            "base": "development",
            "headSha": self.head,
        }
        self.github.prs[8] = {
            "number": 8,
            "url": "https://github.com/owner/name/pull/8",
            "isDraft": False,
            "state": "open",
            "head": "phase/next",
            "base": "development",
            "headSha": self.head,
        }
        with self.assertRaisesRegex(controller.ControllerError, "phase_pr_not_draft"):
            controller.authorize_phase_consolidation(
                github=self.github,
                repository="owner/name",
                evidence=self._consolidation_evidence(replacement=8),
                role="operator",
            )
        self.assertNotIn(8, self.github.closed_numbers)
        self.github.prs[9] = {
            "number": 9,
            "url": "https://github.com/owner/name/pull/9",
            "isDraft": True,
            "state": "open",
            "head": "development",
            "base": "development",
            "headSha": self.head,
        }
        with self.assertRaisesRegex(controller.ControllerError, "unrelated_source"):
            controller.validate_phase_consolidation_evidence(
                {
                    **self._consolidation_evidence(replacement=9),
                    "replacements": [
                        {
                            "number": 9,
                            "url": "https://github.com/owner/name/pull/9",
                            "head": "development",
                            "headSha": self.head,
                            "reason": "stale_duplicate",
                        }
                    ],
                },
                repository="owner/name",
            )
        with self.assertRaisesRegex(controller.ControllerError, "protected_pr_close"):
            controller.authorize_phase_consolidation(
                github=self.github,
                repository="owner/name",
                evidence=self._consolidation_evidence(replacement=9),
                role="operator",
            )
        self.github.prs[7] = {
            "number": 7,
            "url": "https://github.com/owner/name/pull/7",
            "isDraft": True,
            "state": "open",
            "head": "issue/1-other",
            "base": "development",
            "headSha": self.head,
        }
        evidence = self._consolidation_evidence(replacement=7)
        evidence["replacements"][0]["head"] = "phase/next"
        with self.assertRaisesRegex(controller.ControllerError, "unrelated_source"):
            controller.authorize_phase_consolidation(
                github=self.github,
                repository="owner/name",
                evidence=evidence,
                role="operator",
            )
        self.assertEqual(self.github.closed_numbers, [])
        self.assertEqual(self.github.merges, [])

    def test_consolidate_phase_cli_uses_canonical_token_and_mocked_github(self) -> None:
        self.github.prs[12] = {
            "number": 12,
            "url": "https://github.com/owner/name/pull/12",
            "isDraft": True,
            "state": "open",
            "head": "phase/next",
            "base": "development",
            "headSha": self.head,
        }
        self.github.prs[10] = {
            "number": 10,
            "url": "https://github.com/owner/name/pull/10",
            "isDraft": True,
            "state": "open",
            "head": "phase/next",
            "base": "development",
            "headSha": self.head,
        }
        evidence_path = Path(tempfile.mkdtemp()) / "evidence.json"
        evidence_path.write_text(json.dumps(self._consolidation_evidence()), encoding="utf-8")
        out_path = Path(tempfile.mkdtemp()) / "receipt.json"
        with mock.patch.object(controller, "resolve_production_github", return_value=self.github):
            rc = controller.main(
                [
                    "consolidate-phase",
                    "--repository",
                    "owner/name",
                    "--role",
                    "operator",
                    "--evidence-json",
                    str(evidence_path),
                    "--out",
                    str(out_path),
                ]
            )
        self.assertEqual(rc, 0)
        payload = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "consolidated")
        self.assertEqual(payload["closed"][0]["number"], 10)
        self.assertEqual(self.github.merges, [])
        self.assertEqual(self.github.deleted_refs, [])
        from scripts.gitops.github_auth import resolve_live_phase_mutation_token

        token, source = resolve_live_phase_mutation_token({"GH_TOKEN": "ghs_phase_api"})
        self.assertEqual((token, source), ("ghs_phase_api", "GH_TOKEN"))
        with self.assertRaisesRegex(Exception, "legacy_publisher_token_not_canonical"):
            resolve_live_phase_mutation_token({"AUTOMATION_TOKEN": "ghs_publisher"})

    def test_live_controller_close_never_merges_or_deletes(self) -> None:
        calls: list[tuple[str, str, object]] = []

        def transport(method: str, url: str, token: str, body):
            calls.append((method, url, body))
            if method == "GET" and url.endswith("/pulls/10"):
                return {
                    "number": 10,
                    "html_url": "https://github.com/owner/name/pull/10",
                    "draft": True,
                    "state": "open",
                    "head": {"ref": "phase/next", "sha": self.head, "repo": {"full_name": "owner/name"}},
                    "base": {"ref": "development"},
                    "merged": False,
                }
            if method == "PATCH" and url.endswith("/pulls/10"):
                self.assertEqual(body, {"state": "closed"})
                return {
                    "number": 10,
                    "html_url": "https://github.com/owner/name/pull/10",
                    "draft": True,
                    "state": "closed",
                    "head": {"ref": "phase/next", "sha": self.head},
                    "base": {"ref": "development"},
                    "merged": False,
                }
            raise AssertionError((method, url, body))

        live = controller.LiveGitHub(repository="owner/name", automation_token="tok", transport=transport)
        result = live.close_draft_phase_pr(
            repository="owner/name",
            number=10,
            expected_head=self.head,
            phase_branch="phase/next",
        )
        self.assertEqual(result["state"], "closed")
        self.assertFalse(any("/merge" in url or method == "DELETE" for method, url, _ in calls))


if __name__ == "__main__":
    unittest.main()
