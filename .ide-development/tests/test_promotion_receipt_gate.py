from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.gitops.coordinator import receipts
from scripts.gitops.promotion_receipt_gate import (
    canonical_digest,
    evaluate_automatic_main,
    evaluate_development_gates,
    evaluate_main_approval,
    evaluate_release_path,
    select_promotion_candidate,
    verify_receipt_file,
)


COMMAND_DIGEST = "sha256:" + ("c" * 64)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True)
    return result.stdout.strip()


class PromotionReceiptGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "w1-p3@example.com")
        git(self.repo, "config", "user.name", "W1 P3")
        git(self.repo, "remote", "add", "origin", "https://github.com/acme/promotion.git")
        (self.repo / "app.txt").write_text("one\n", encoding="utf-8")
        (self.repo / "deps.lock").write_text("dep-one\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "initial")
        self.identity = receipts.compute_candidate_identity(self.repo, ["deps.lock"], "full")
        self.identity_path = self.root / "identity.json"
        self.identity_path.write_text(json.dumps(self.identity.to_dict()), encoding="utf-8")
        self.receipt = self.root / "full-receipt.json"
        receipts.write_receipt(self._receipt(), self.receipt)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _receipt(self, **changes: object) -> dict[str, object]:
        result: dict[str, object] = {
            "schemaVersion": 2,
            "candidateIdentity": self.identity.to_dict(),
            "workflowRunId": 301,
            "workflowRunAttempt": 1,
            "runnerLabel": "ubuntu-24.04-arm",
            "startedAt": "2026-08-13T01:00:00Z",
            "completedAt": "2026-08-13T01:01:00Z",
            "conclusion": "success",
            "commandDigest": COMMAND_DIGEST,
            "evidenceDigests": {"evidence/full.log": "sha256:" + ("b" * 64)},
        }
        result.update(changes)
        return result

    def test_missing_exact_reuse_and_negative_content_matrix(self) -> None:
        self.assertEqual(
            verify_receipt_file(self.root / "missing.json", repo_path=self.repo, dependencies=["deps.lock"]).code,
            "invalid_receipt",
        )
        self.assertEqual(
            verify_receipt_file(self.receipt, repo_path=self.repo, dependencies=["deps.lock"]).code,
            "accepted",
        )
        git(self.repo, "commit", "--allow-empty", "-qm", "different commit same content")
        self.assertEqual(
            verify_receipt_file(self.receipt, repo_path=self.repo, dependencies=["deps.lock"]).code,
            "head_mismatch",
        )
        (self.repo / "app.txt").write_text("two\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "source change")
        self.assertEqual(
            verify_receipt_file(self.receipt, repo_path=self.repo, dependencies=["deps.lock"]).code,
            "tree_mismatch",
        )
        (self.repo / "app.txt").write_text("one\n", encoding="utf-8")
        git(self.repo, "add", "app.txt")
        git(self.repo, "commit", "-qm", "restore source")
        (self.repo / "deps.lock").write_text("dep-two\n", encoding="utf-8")
        self.assertEqual(
            verify_receipt_file(self.receipt, repo_path=self.repo, dependencies=["deps.lock"]).code,
            "dependency_mismatch",
        )

        legacy = self.root / "legacy.json"
        legacy.write_text(json.dumps(self._receipt(schemaVersion=1)), encoding="utf-8")
        self.assertEqual(verify_receipt_file(legacy, identity_path=self.identity_path).code, "unsupported_version")

    def test_run_profile_command_and_workflow_context_is_required_when_supplied(self) -> None:
        self.assertEqual(
            verify_receipt_file(
                self.receipt,
                identity_path=self.identity_path,
                workflow_run_id=302,
            ).code,
            "run_mismatch",
        )
        self.assertEqual(
            verify_receipt_file(
                self.receipt,
                identity_path=self.identity_path,
                workflow_run_attempt=2,
            ).code,
            "attempt_mismatch",
        )
        self.assertEqual(
            verify_receipt_file(
                self.receipt,
                identity_path=self.identity_path,
                expected_command_digest="sha256:" + ("d" * 64),
            ).code,
            "command_mismatch",
        )
        self.assertEqual(
            verify_receipt_file(
                self.receipt,
                identity_path=self.identity_path,
                expected_workflow_digest="sha256:" + ("d" * 64),
            ).code,
            "workflow_mismatch",
        )

    def test_development_release_approval_and_lineage_are_machine_readable(self) -> None:
        head = "a" * 40
        good = {"status": "passed", "sha": head}
        decision = evaluate_development_gates(
            {"sealed": good, "fastGate": good, "bugbot": good, "fullSuite": {"status": "not-required"}},
            head,
        )
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.to_dict()["status"], "PASS")
        stale = dict(good, sha="b" * 40)
        self.assertEqual(
            evaluate_development_gates({"sealed": good, "fastGate": stale, "bugbot": good, "fullSuite": good}, head).code,
            "fast_stale",
        )
        self.assertEqual(
            evaluate_release_path({"status": "passed", "testProfile": "release", "fullSuiteInvoked": True}).code,
            "full_suite_reentered",
        )

        receipt_payload = json.loads(self.receipt.read_text(encoding="utf-8"))
        source, base, pr_head = "a" * 40, "b" * 40, "c" * 40
        approval = {
            "sourceSha": source,
            "baseSha": base,
            "prHeadSha": pr_head,
            "receiptDigest": receipt_payload["receiptDigest"],
        }
        self.assertTrue(
            evaluate_main_approval(
                approval,
                source_sha=source,
                base_sha=base,
                pr_head_sha=pr_head,
                receipt=receipt_payload,
            ).accepted
        )
        self.assertEqual(
            evaluate_main_approval(
                dict(approval, receiptDigest=canonical_digest({"tampered": True})),
                source_sha=source,
                base_sha=base,
                pr_head_sha=pr_head,
                receipt=receipt_payload,
            ).code,
            "receipt_mismatch",
        )
        self.assertEqual(
            select_promotion_candidate(
                [
                    {"number": 9, "sourceSha": source, "targetSha": base, "headRefName": "promote/main/aaaaaaaaaaaa"},
                    {"number": 4, "sourceSha": source, "targetSha": base, "headRefName": "promote/main/aaaaaaaaaaaa"},
                ],
                source_sha=source,
                target_sha=base,
                branch="promote/main/aaaaaaaaaaaa",
            )["reason"],
            "duplicate_promotion_candidates",
        )

        automatic = evaluate_automatic_main(
            release={"status": "passed", "testProfile": "release", "fullSuiteInvoked": False},
            required_receipt=receipt_payload,
            candidate_identity=self.identity,
            workflow_run_id=301,
            workflow_run_attempt=1,
            runner_label="ubuntu-24.04-arm",
        )
        self.assertTrue(automatic.accepted)
        self.assertIn(self.identity.head_commit, automatic.detail)
        self.assertEqual(automatic.source_commit, self.identity.head_commit)
        self.assertEqual(automatic.promotion_commit, self.identity.head_commit)
        self.assertEqual(automatic.to_dict()["status"], "PASS")
        self.assertIn("receiptLookupKey", automatic.to_dict())


if __name__ == "__main__":
    unittest.main()
