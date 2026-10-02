from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.gitops.coordinator.receipts import (
    compute_candidate_identity,
    create_transition_receipt,
    write_receipt,
)
from scripts.gitops import delivery_controller


ROOT = Path(__file__).resolve().parents[3]


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True)
    return result.stdout.strip()


class FakeGitHub:
    def __init__(self, merged_sha: str) -> None:
        self.merged_sha = merged_sha
        self.body = ""

    def create_pull_request(self, *, repository: str, head: str, base: str, title: str, body: str, head_sha: str):
        self.body = body
        return {"number": 1}

    def merge_pull_request(self, *, repository: str, number: int, expected_head: str, method: str = "merge", admin: bool = False, match_head_commit: bool = True):
        return {"mergeCommitSha": self.merged_sha}


class GateReceiptTransitionTests(unittest.TestCase):
    def test_cli_accepts_only_authenticated_same_tree_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            (repo / ".github").mkdir(parents=True)
            (repo / ".github" / "linktrend-delivery-mode.json").write_text('{"mode":"test"}\n')
            (repo / "app.txt").write_text("same tree\n")
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "receipt-test@example.invalid")
            git(repo, "config", "user.name", "Receipt Test")
            git(repo, "remote", "add", "origin", "https://github.com/linktrend/LiNKautowork.git")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "audited full-suite source")
            source = compute_candidate_identity(
                repo,
                test_profile="full",
                profile_files=[".github/linktrend-delivery-mode.json"],
                source_branch="phase/test",
            )
            receipt_path = root / "full-suite-receipt.json"
            write_receipt(
                {
                    "schemaVersion": 2,
                    "candidateIdentity": source.to_dict(),
                    "workflowRunId": 123,
                    "workflowRunAttempt": 1,
                    "runnerLabel": "ubuntu-24.04-arm",
                    "startedAt": "2026-10-02T00:00:00Z",
                    "completedAt": "2026-10-02T00:01:00Z",
                    "conclusion": "success",
                    "commandDigest": "sha256:" + "a" * 64,
                    "evidenceDigests": {},
                },
                receipt_path,
            )
            git(repo, "commit", "--allow-empty", "-qm", "protected staging promotion")
            target_commit = git(repo, "rev-parse", "HEAD")
            target = compute_candidate_identity(
                repo,
                test_profile="full",
                profile_files=[".github/linktrend-delivery-mode.json"],
                source_branch="staging",
            )
            transition = create_transition_receipt(
                json.loads(receipt_path.read_text()),
                target_branch="staging",
                target_commit=target_commit,
                target_tree=target.git_tree,
                protected_base_commit=git(repo, "rev-parse", "HEAD^"),
            ).to_dict()
            transition_path = root / "transition-receipt.json"
            transition_path.write_text(json.dumps(transition))

            command = [
                "python3",
                str(ROOT / "scripts/gitops/gate_receipt.py"),
                "verify",
                "--receipt",
                str(receipt_path),
                "--repo",
                str(repo),
                "--profile",
                "full",
                "--source-branch",
                "staging",
                "--transition-receipt",
                str(transition_path),
                "--workflow-run-id",
                "123",
                "--gate",
                "full-gate",
            ]
            accepted = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
            self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
            self.assertTrue(json.loads(accepted.stdout)["accepted"])

            forged = dict(transition, target_tree="0" * 40)
            transition_path.write_text(json.dumps(forged))
            rejected = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertFalse(json.loads(rejected.stdout)["accepted"])

            development_identity = compute_candidate_identity(
                repo,
                test_profile="full",
                profile_files=[".github/linktrend-delivery-mode.json"],
                source_branch="development",
            )
            development_transition = create_transition_receipt(
                json.loads(receipt_path.read_text()),
                target_branch="development",
                target_commit=target_commit,
                target_tree=development_identity.git_tree,
                protected_base_commit=git(repo, "rev-parse", "HEAD^"),
            ).to_dict()
            github = FakeGitHub("b" * 40)
            delivery_controller.promote_to_staging(
                github=github,
                repository="linktrend/LiNKautowork",
                development_sha=target_commit,
                staging_sha=git(repo, "rev-parse", "HEAD^"),
                candidate_sha=target_commit,
                candidate_tree=development_identity.git_tree,
                receipt=json.loads(receipt_path.read_text()),
                candidate_identity=development_identity.to_dict(),
                release_gate={"status": "passed", "testProfile": "release"},
                role="founder",
                transition_receipt=development_transition,
            )
            marker = json.loads(github.body.split("<!-- linktrend-promote:", 1)[1].split("-->", 1)[0])
            self.assertEqual(marker["transitionReceipt"], development_transition)
            self.assertEqual(marker["transitionReceiptDigest"], development_transition["receiptDigest"])


if __name__ == "__main__":
    unittest.main()
