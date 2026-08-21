"""W1-P3 FullSuiteReceipt creation, reuse, and fail-closed probes."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.gitops.coordinator import receipts


DIGEST = "sha256:" + ("b" * 64)
COMMAND_DIGEST = "sha256:" + ("c" * 64)


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return result.stdout.strip()


class GateReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "receipt-repo"
        self.repo.mkdir()
        run_git(self.repo, "init", "-q")
        run_git(self.repo, "config", "user.email", "receipt-test@example.com")
        run_git(self.repo, "config", "user.name", "Receipt Test")
        run_git(self.repo, "remote", "add", "origin", "https://github.com/acme/receipt-repo.git")
        (self.repo / "src").mkdir()
        (self.repo / ".github" / "workflows").mkdir(parents=True)
        (self.repo / "profiles").mkdir()
        (self.repo / "src" / "app.txt").write_text("version one\n", encoding="utf-8")
        (self.repo / "deps.lock").write_text("dependency one\n", encoding="utf-8")
        (self.repo / "profiles" / "full.json").write_text('{"suite":"full","timeout":3600}\n', encoding="utf-8")
        (self.repo / ".github" / "workflows" / "check.yml").write_text("name: Check\n", encoding="utf-8")
        run_git(self.repo, "add", ".")
        run_git(self.repo, "commit", "-qm", "initial")
        self.identity = receipts.compute_candidate_identity(
            self.repo,
            ["deps.lock"],
            "full",
            profile_files=["profiles/full.json"],
            workflow_files=[".github/workflows/check.yml"],
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _result(self, **changes: object) -> dict[str, object]:
        value: dict[str, object] = {
            "schemaVersion": 2,
            "candidateIdentity": self.identity.to_dict(),
            "workflowRunId": 101,
            "workflowRunAttempt": 1,
            "runnerLabel": "ubuntu-24.04-arm",
            "startedAt": "2026-08-13T01:00:00Z",
            "completedAt": "2026-08-13T01:01:00Z",
            "conclusion": "success",
            "commandDigest": COMMAND_DIGEST,
            "evidenceDigests": {"evidence/full.log": DIGEST},
        }
        value.update(changes)
        return value

    def _write(self, path: Path | None = None, **changes: object) -> Path:
        output = path or Path(self.tmp.name) / "receipt.json"
        receipts.write_receipt(self._result(**changes), output)
        return output

    def _identity(self) -> receipts.CandidateIdentity:
        return receipts.compute_candidate_identity(
            self.repo,
            ["deps.lock"],
            "full",
            profile_files=["profiles/full.json"],
            workflow_files=[".github/workflows/check.yml"],
        )

    def test_exact_identity_rejects_different_commit_same_tree(self) -> None:
        receipt = self._write()
        self.assertTrue(receipts.verify_receipt(receipts.load_json(receipt), self.identity, "full-gate"))
        old_source = self.identity.head_commit
        run_git(self.repo, "commit", "--allow-empty", "-qm", "metadata-only")
        newer = self._identity()
        self.assertNotEqual(old_source, newer.head_commit)
        self.assertEqual(self.identity.git_tree, newer.git_tree)
        verdict = receipts.verify_receipt(receipts.load_json(receipt), newer, "full-gate")
        self.assertEqual(verdict.code, "head_mismatch")
        self.assertIsNone(verdict.source_commit)
        self.assertIsNone(verdict.promotion_commit)

    def test_source_dependency_profile_and_workflow_changes_fail(self) -> None:
        receipt = self._write()

        (self.repo / "src" / "app.txt").write_text("version two\n", encoding="utf-8")
        run_git(self.repo, "add", ".")
        run_git(self.repo, "commit", "-qm", "source change")
        self.assertEqual(receipts.verify_receipt(receipts.load_json(receipt), self._identity(), "full-gate").code, "tree_mismatch")

        (self.repo / "src" / "app.txt").write_text("version one\n", encoding="utf-8")
        run_git(self.repo, "add", "src/app.txt")
        run_git(self.repo, "commit", "-qm", "restore source")
        (self.repo / "deps.lock").write_text("dependency two\n", encoding="utf-8")
        self.assertEqual(receipts.verify_receipt(receipts.load_json(receipt), self._identity(), "full-gate").code, "dependency_mismatch")

        (self.repo / "deps.lock").write_text("dependency one\n", encoding="utf-8")
        (self.repo / "profiles" / "full.json").write_text('{"suite":"full","timeout":3601}\n', encoding="utf-8")
        self.assertEqual(receipts.verify_receipt(receipts.load_json(receipt), self._identity(), "full-gate").code, "profile_mismatch")

        (self.repo / "profiles" / "full.json").write_text('{"suite":"full","timeout":3600}\n', encoding="utf-8")
        (self.repo / ".github" / "workflows" / "check.yml").write_text("name: Changed\n", encoding="utf-8")
        self.assertEqual(receipts.verify_receipt(receipts.load_json(receipt), self._identity(), "full-gate").code, "workflow_mismatch")

    def test_repository_run_attempt_head_and_runner_fail_closed(self) -> None:
        receipt = self._write()
        payload = receipts.load_json(receipt)
        self.assertEqual(
            receipts.verify_receipt(payload, self.identity, "full-gate", workflow_run_id=102).code,
            "run_mismatch",
        )
        self.assertEqual(
            receipts.verify_receipt(payload, self.identity, "full-gate", workflow_run_attempt=2).code,
            "attempt_mismatch",
        )
        self.assertEqual(
            receipts.verify_receipt(payload, self.identity, "full-gate", workflow_head_commit="a" * 40).code,
            "superseded_head",
        )
        self.assertEqual(
            receipts.verify_receipt(payload, self.identity, "full-gate", runner_label="unknown-runner").code,
            "unknown_runner",
        )

        wrong_identity = dict(self.identity.to_dict(), repository="other/repository")
        wrong_receipt = self._write(candidateIdentity=wrong_identity, path=Path(self.tmp.name) / "wrong.json")
        self.assertEqual(receipts.verify_receipt(receipts.load_json(wrong_receipt), self.identity, "full-gate").code, "repository_mismatch")

    def test_failure_cancelled_skipped_and_legacy_are_not_trusted(self) -> None:
        for conclusion in ("failure", "cancelled", "skipped"):
            with self.subTest(conclusion=conclusion):
                with self.assertRaises(receipts.ReceiptError) as context:
                    receipts.write_receipt(self._result(conclusion=conclusion), Path(self.tmp.name) / f"{conclusion}.json")
                self.assertEqual(context.exception.code, "conclusion_not_success")

        legacy = self._result(schemaVersion=1)
        self.assertEqual(receipts.verify_receipt(legacy, self.identity, "full-gate").code, "unsupported_version")

    def test_digest_and_evidence_tampering_fail_without_credentials(self) -> None:
        with mock.patch.dict(os.environ, {"LINKTREND_GITOPS_APP_TOKEN": "ltfx.gate.must_not_be_read.v1"}, clear=False):
            receipt = self._write()
        payload = receipts.load_json(receipt)
        self.assertTrue(payload["receiptDigest"].startswith("sha256:"))
        payload["evidenceDigests"]["evidence/full.log"] = "sha256:" + ("d" * 64)
        self.assertEqual(receipts.verify_receipt(payload, self.identity, "full-gate").code, "receipt_digest_mismatch")
        self.assertEqual(
            receipts.verify_receipt(
                receipts.load_json(receipt),
                self.identity,
                "full-gate",
                expected_evidence_digests={"evidence/full.log": "sha256:" + ("d" * 64)},
            ).code,
            "evidence_mismatch",
        )

    def test_schema_shape_digest_lookup_and_atomic_output_are_stable(self) -> None:
        first = Path(self.tmp.name) / "one.json"
        second = Path(self.tmp.name) / "two.json"
        receipts.write_receipt(self._result(), first)
        receipts.write_receipt(json.loads(first.read_text(encoding="utf-8")), second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        parsed = receipts.load_json(first)
        self.assertEqual(parsed["receiptDigest"], receipts.compute_receipt_digest(parsed))
        self.assertEqual(
            receipts.receipt_lookup_key(parsed),
            f"{self.identity.repository}/101/1/{parsed['receiptDigest']}",
        )

        previous = first.read_bytes()
        with mock.patch.object(receipts.os, "replace", side_effect=RuntimeError("interrupted")):
            with self.assertRaises(RuntimeError):
                receipts.write_receipt(self._result(completedAt="2026-08-13T01:02:00Z"), first)
        self.assertEqual(first.read_bytes(), previous)
        self.assertFalse(any(first.parent.glob(f".{first.name}.*.tmp")))

    def test_path_escape_and_symlink_are_rejected(self) -> None:
        with self.assertRaises(receipts.ReceiptError) as context:
            receipts.compute_candidate_identity(self.repo, ["../outside.txt"], "full")
        self.assertEqual(context.exception.code, "invalid_path")
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("secret\n", encoding="utf-8")
        (self.repo / "escape.lock").symlink_to(outside)
        with self.assertRaises(receipts.ReceiptError) as context:
            receipts.compute_candidate_identity(self.repo, ["escape.lock"], "full")
        self.assertEqual(context.exception.code, "invalid_path")


if __name__ == "__main__":
    unittest.main()
