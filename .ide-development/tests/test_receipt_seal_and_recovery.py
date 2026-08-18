"""Focused adversarial tests for WP-U06 receipt sealing and recovery."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.gitops.coordinator import receipts
from scripts.gitops.phase_integrator import phase_merge_eligibility
from scripts.gitops.promotion_receipt_gate import verify_receipt_payload
from scripts.gitops.receipt_seal import (
    RecoveryError,
    SealError,
    classify_receipt_artifact,
    enumerate_and_select_receipt,
    evaluate_recovered_receipt_for_promotion,
    phase_merge_eligibility_with_receipt,
    resolve_canonical_candidate_head,
    validate_recovery_dispatch,
)


DIGEST = "sha256:" + ("b" * 64)
COMMAND_DIGEST = "sha256:" + ("c" * 64)
DEP_DIGEST = "sha256:" + ("d" * 64)
PROFILE_DIGEST = "sha256:" + ("e" * 64)
WORKFLOW_DIGEST = "sha256:" + ("f" * 64)


def _sha(n: int = 1) -> str:
    return f"{n:040x}"


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _identity(
    *,
    repository: str = "acme/demo",
    branch: str = "phase/demo",
    head: str | None = None,
    tree: str | None = None,
) -> dict[str, str]:
    return {
        "repository": repository,
        "sourceBranch": branch,
        "headCommit": head or _sha(1),
        "gitTree": tree or _sha(2),
        "dependencyDigest": DEP_DIGEST,
        "profileDigest": PROFILE_DIGEST,
        "workflowDigest": WORKFLOW_DIGEST,
    }


def _receipt(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schemaVersion": 2,
        "candidateIdentity": _identity(),
        "workflowRunId": 101,
        "workflowRunAttempt": 1,
        "runnerLabel": "ubuntu-24.04-arm",
        "startedAt": "2026-08-17T01:00:00Z",
        "completedAt": "2026-08-17T01:01:00Z",
        "conclusion": "success",
        "commandDigest": COMMAND_DIGEST,
        "evidenceDigests": {"evidence/full.log": DIGEST},
    }
    value.update(changes)
    return value


def _complete_receipt(**changes: object) -> dict[str, object]:
    raw = _receipt(**changes)
    return receipts.create_full_suite_receipt(raw).to_dict()


class ReceiptBodyTrustTests(unittest.TestCase):
    def test_metadata_body_mismatch_missing_schema_forged_digest_never_exact(self) -> None:
        head = _sha(1)
        tree = _sha(2)
        trusted = _complete_receipt(candidateIdentity=_identity(head=head, tree=tree))
        expected = {
            "repository": "acme/demo",
            "prNumber": 7,
            "headCommit": head,
            "gitTree": tree,
            "workflowRunId": 101,
            "workflowRunAttempt": 1,
        }

        mismatch = {
            "id": "meta-mismatch",
            "readable": True,
            "repository": "acme/demo",
            "prNumber": 7,
            "headCommit": _sha(9),
            "gitTree": tree,
            "workflowRunId": 101,
            "workflowRunAttempt": 1,
            "receipt": trusted,
        }
        self.assertEqual(
            classify_receipt_artifact(mismatch, expected=expected)["classification"],
            "metadata_body_head_mismatch",
        )

        missing_body = {
            "id": "no-body",
            "readable": True,
            "repository": "acme/demo",
            "prNumber": 7,
            "headCommit": head,
            "gitTree": tree,
            "workflowRunId": 101,
            "workflowRunAttempt": 1,
        }
        self.assertEqual(
            classify_receipt_artifact(missing_body, expected=expected)["classification"],
            "malformed",
        )

        no_schema = dict(trusted)
        no_schema.pop("schemaVersion")
        missing_schema = {
            "id": "no-schema",
            "readable": True,
            "repository": "acme/demo",
            "prNumber": 7,
            "headCommit": head,
            "gitTree": tree,
            "workflowRunId": 101,
            "workflowRunAttempt": 1,
            "receipt": no_schema,
        }
        self.assertEqual(
            classify_receipt_artifact(missing_schema, expected=expected)["classification"],
            "malformed",
        )

        forged = dict(trusted)
        forged["receiptDigest"] = "sha256:" + ("0" * 64)
        forged_artifact = {
            "id": "forged-digest",
            "readable": True,
            "repository": "acme/demo",
            "prNumber": 7,
            "headCommit": head,
            "gitTree": tree,
            "workflowRunId": 101,
            "workflowRunAttempt": 1,
            "receipt": forged,
        }
        self.assertEqual(
            classify_receipt_artifact(forged_artifact, expected=expected)["classification"],
            "malformed",
        )

        exact = {
            "id": "exact-trusted",
            "readable": True,
            "repository": "acme/demo",
            "prNumber": 7,
            "headCommit": head,
            "gitTree": tree,
            "workflowRunId": 101,
            "workflowRunAttempt": 1,
            "receipt": trusted,
        }
        self.assertEqual(classify_receipt_artifact(exact, expected=expected)["classification"], "exact")
        selected = enumerate_and_select_receipt([mismatch, missing_body, exact], expected=expected)
        self.assertTrue(selected["accepted"])
        self.assertEqual(selected["selected"]["id"], "exact-trusted")

    def test_exhaustive_metadata_body_field_cross_check_before_exact(self) -> None:
        from scripts.gitops.receipt_seal import DUPLICATED_METADATA_BODY_FIELDS

        head = _sha(1)
        tree = _sha(2)
        trusted = _complete_receipt(candidateIdentity=_identity(head=head, tree=tree))
        expected = {
            "repository": "acme/demo",
            "prNumber": 7,
            "headCommit": head,
            "gitTree": tree,
            "workflowRunId": 101,
            "workflowRunAttempt": 1,
        }
        base = {
            "id": "base",
            "readable": True,
            "repository": "acme/demo",
            "prNumber": 7,
            "headCommit": head,
            "gitTree": tree,
            "workflowRunId": 101,
            "workflowRunAttempt": 1,
            "schemaVersion": 2,
            "conclusion": "success",
            "receiptDigest": trusted["receiptDigest"],
            "commandDigest": trusted["commandDigest"],
            "requiredGate": "full-gate",
            "gate": "full-gate",
            "receipt": trusted,
        }
        self.assertEqual(classify_receipt_artifact(base, expected=expected)["classification"], "exact")

        cases = [
            ("repository", "other/repo", "metadata_body_repository_mismatch"),
            ("workflowRunId", 999, "metadata_body_run_mismatch"),
            ("workflowRunAttempt", 2, "metadata_body_attempt_mismatch"),
            ("headCommit", _sha(9), "metadata_body_head_mismatch"),
            ("gitTree", _sha(8), "metadata_body_tree_mismatch"),
            ("conclusion", "failure", "metadata_body_conclusion_mismatch"),
            ("schemaVersion", 1, "metadata_body_schema_mismatch"),
            ("receiptDigest", "sha256:" + ("1" * 64), "metadata_body_receipt_digest_mismatch"),
            ("commandDigest", "sha256:" + ("2" * 64), "metadata_body_command_digest_mismatch"),
            ("requiredGate", "fast-gate", "metadata_body_gate_mismatch"),
            ("gate", "fast-gate", "metadata_body_gate_mismatch"),
        ]
        covered = {code for _, _, code in cases}
        inventory_codes = {spec["code"] for spec in DUPLICATED_METADATA_BODY_FIELDS}
        self.assertTrue(
            inventory_codes <= covered | {"metadata_body_head_mismatch", "metadata_body_tree_mismatch"},
            f"test inventory missing codes: {sorted(inventory_codes - covered)}",
        )
        self.assertEqual(
            {spec["name"] for spec in DUPLICATED_METADATA_BODY_FIELDS},
            {
                "repository",
                "headCommit",
                "gitTree",
                "workflowRunId",
                "workflowRunAttempt",
                "conclusion",
                "schemaVersion",
                "receiptDigest",
                "commandDigest",
                "gate",
            },
        )
        for field, bad_value, code in cases:
            poisoned = dict(base)
            poisoned["id"] = f"bad-{field}"
            poisoned[field] = bad_value
            row = classify_receipt_artifact(poisoned, expected=expected)
            self.assertEqual(row["classification"], code, field)
            self.assertNotEqual(row["classification"], "exact", field)

        # Metadata must not override body when selecting against expected identity.
        override = dict(base)
        override["id"] = "override-run"
        override["workflowRunId"] = 101  # matches expected
        # Body has 101; if we mutated only a shadow field that disagreed we'd catch it above.
        # Forge metadata run to match expected while body differs — rebuild body with run 55.
        body_other_run = _complete_receipt(
            candidateIdentity=_identity(head=head, tree=tree),
            workflowRunId=55,
        )
        override["receipt"] = body_other_run
        override["workflowRunId"] = 101
        override["receiptDigest"] = body_other_run["receiptDigest"]
        override["commandDigest"] = body_other_run["commandDigest"]
        row = classify_receipt_artifact(override, expected=expected)
        self.assertEqual(row["classification"], "metadata_body_run_mismatch")

        positive = dict(base)
        positive["id"] = "positive-exact"
        self.assertEqual(classify_receipt_artifact(positive, expected=expected)["classification"], "exact")
        selected = enumerate_and_select_receipt([override, positive], expected=expected)
        self.assertTrue(selected["accepted"])
        self.assertEqual(selected["selected"]["id"], "positive-exact")

    def test_truncated_receipt_and_wrong_tree_fail_merge_eligibility(self) -> None:
        head = _sha(1)
        tree = _sha(2)
        record = {
            "sealed": True,
            "sealedSha": head,
            "headSha": head,
            "candidateIdentity": {"sourceSha": head, "gitTreeSha": tree},
            "fast": {"status": "passed", "sha": head},
            "bugbot": {"status": "passed", "sha": head},
            "full": {"status": "passed", "sha": head},
        }
        truncated = {
            "candidateIdentity": _identity(head=head, tree=tree),
            "conclusion": "success",
        }
        blocked = phase_merge_eligibility_with_receipt(
            record, live_head_sha=head, retained_receipt=truncated, expected_tree=tree
        )
        self.assertFalse(blocked.eligible)
        self.assertTrue(
            "retained_receipt_malformed" in blocked.detail
            or "invalid_receipt" in blocked.detail
            or "unsupported_version" in blocked.detail,
            blocked.detail,
        )

        wrong_tree = _complete_receipt(candidateIdentity=_identity(head=head, tree=_sha(8)))
        tree_blocked = phase_merge_eligibility_with_receipt(
            record, live_head_sha=head, retained_receipt=wrong_tree, expected_tree=tree
        )
        self.assertFalse(tree_blocked.eligible)
        self.assertIn("retained_receipt_wrong_tree", tree_blocked.detail)

        forged = _complete_receipt(candidateIdentity=_identity(head=head, tree=tree))
        forged = dict(forged)
        forged["receiptDigest"] = "sha256:" + ("a" * 64)
        digest_blocked = phase_merge_eligibility_with_receipt(
            record, live_head_sha=head, retained_receipt=forged, expected_tree=tree
        )
        self.assertFalse(digest_blocked.eligible)
        self.assertIn("receipt_digest_mismatch", digest_blocked.detail)

        trusted = _complete_receipt(candidateIdentity=_identity(head=head, tree=tree))
        ok = phase_merge_eligibility_with_receipt(
            record, live_head_sha=head, retained_receipt=trusted, expected_tree=tree
        )
        self.assertTrue(ok.eligible, ok.detail)

    def test_integrator_eligible_cli_requires_retained_receipt(self) -> None:
        head = _sha(1)
        tree = _sha(2)
        record = {
            "sealed": True,
            "sealedSha": head,
            "headSha": head,
            "candidateIdentity": {"sourceSha": head, "gitTreeSha": tree},
            "fast": {"status": "passed", "sha": head},
            "bugbot": {"status": "passed", "sha": head},
            "full": {"status": "passed", "sha": head},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record_path = root / "record.json"
            receipt_path = root / "receipt.json"
            record_path.write_text(json.dumps(record), encoding="utf-8")
            receipt_path.write_text(
                json.dumps(_complete_receipt(candidateIdentity=_identity(head=head, tree=tree))),
                encoding="utf-8",
            )
            missing = subprocess.run(
                [
                    "python3",
                    "scripts/gitops/phase_integrator.py",
                    "eligible",
                    str(record_path),
                    head,
                ],
                cwd=Path(__file__).resolve().parents[2],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(missing.returncode, 0)
            missing_payload = json.loads(missing.stdout)
            self.assertFalse(missing_payload["eligible"])
            self.assertIn("retained_receipt_missing", missing_payload["detail"])

            ok = subprocess.run(
                [
                    "python3",
                    "scripts/gitops/phase_integrator.py",
                    "eligible",
                    str(record_path),
                    head,
                    "--receipt",
                    str(receipt_path),
                    "--expected-tree",
                    tree,
                ],
                cwd=Path(__file__).resolve().parents[2],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            ok_payload = json.loads(ok.stdout)
            self.assertTrue(ok_payload["eligible"])


class CanonicalCandidateHeadTests(unittest.TestCase):
    def test_pull_request_event_with_synthetic_merge_sha_selects_pr_head(self) -> None:
        head = _sha(11)
        merge = _sha(99)
        tree = _sha(22)
        resolved = resolve_canonical_candidate_head(
            {
                "event_name": "pull_request",
                "pull_request": {
                    "number": 42,
                    "head": {"sha": head, "ref": "phase/demo", "repo": {"full_name": "acme/demo"}},
                    "base": {"sha": _sha(10), "ref": "development"},
                    "merge_commit_sha": merge,
                },
                "merge_ref_sha": merge,
                "merge_ref_tree": _sha(88),
                "candidate_tree": tree,
                "base_tree": _sha(33),
            }
        )
        self.assertEqual(resolved["candidateHead"], head)
        self.assertEqual(resolved["candidateTree"], tree)
        self.assertEqual(resolved["sourceBranch"], "phase/demo")
        self.assertEqual(resolved["checkoutRef"], head)
        self.assertNotEqual(resolved["candidateHead"], merge)
        evidence = resolved["mergeRefEvidence"]
        self.assertEqual(evidence["kind"], "synthetic-merge-ref")
        self.assertEqual(evidence["mergeSha"], merge)
        self.assertEqual(evidence["canonicalHead"], head)
        self.assertFalse(evidence.get("promotableIdentity", True))

    def test_merge_ref_never_becomes_candidate_identity(self) -> None:
        with self.assertRaisesRegex(SealError, "merge_ref_identity_forbidden"):
            resolve_canonical_candidate_head(
                {
                    "event_name": "pull_request",
                    "candidate_head": _sha(99),
                    "candidate_tree": _sha(2),
                    "source_branch": "refs/pull/42/merge",
                    "pull_request": {
                        "number": 42,
                        "head": {"sha": _sha(11), "ref": "phase/demo"},
                        "merge_commit_sha": _sha(99),
                    },
                }
            )

    def test_forged_or_empty_identity_fails_closed(self) -> None:
        with self.assertRaisesRegex(SealError, "candidate_head_invalid"):
            resolve_canonical_candidate_head({"pull_request": {"head": {"sha": "not-a-sha", "ref": "phase/x"}}})
        with self.assertRaisesRegex(SealError, "candidate_head_missing"):
            resolve_canonical_candidate_head({"pull_request": {"number": 1}})


class ReceiptDiscoverySelectionTests(unittest.TestCase):
    def test_inaccessible_stale_before_exact_is_skipped_and_exact_selected(self) -> None:
        expected_head = _sha(1)
        expected_tree = _sha(2)
        exact = {
            "id": "exact-1",
            "name": "linktrend-full-suite-receipt-7-9001",
            "readable": True,
            "repository": "acme/demo",
            "prNumber": 7,
            "headCommit": expected_head,
            "gitTree": expected_tree,
            "workflowRunId": 9001,
            "workflowRunAttempt": 1,
            "receipt": _complete_receipt(
                candidateIdentity=_identity(head=expected_head, tree=expected_tree),
                workflowRunId=9001,
            ),
        }
        stale = {
            "id": "stale-0",
            "name": "linktrend-full-suite-receipt-7-8000",
            "readable": False,
            "error": "permission_denied",
            "repository": "acme/demo",
            "prNumber": 7,
            "headCommit": _sha(8),
            "gitTree": expected_tree,
            "workflowRunId": 8000,
            "workflowRunAttempt": 1,
        }
        result = enumerate_and_select_receipt(
            [stale, exact],
            expected={
                "repository": "acme/demo",
                "prNumber": 7,
                "headCommit": expected_head,
                "gitTree": expected_tree,
                "workflowRunId": 9001,
                "workflowRunAttempt": 1,
            },
        )
        self.assertTrue(result["accepted"])
        self.assertEqual(result["selected"]["id"], "exact-1")
        classifications = {row["id"]: row["classification"] for row in result["enumerated"]}
        self.assertEqual(classifications["stale-0"], "inaccessible_stale")
        self.assertEqual(classifications["exact-1"], "exact")
        self.assertIn("stale-0", result["skipped"])

    def test_inaccessible_expected_exact_fails_closed_even_if_other_readable(self) -> None:
        expected_head = _sha(1)
        expected_tree = _sha(2)
        other = {
            "id": "other-readable",
            "readable": True,
            "repository": "acme/demo",
            "prNumber": 7,
            "headCommit": _sha(9),
            "gitTree": _sha(9),
            "workflowRunId": 1,
            "workflowRunAttempt": 1,
            "receipt": _complete_receipt(candidateIdentity=_identity(head=_sha(9), tree=_sha(9))),
        }
        expected_exact = {
            "id": "expected-exact",
            "readable": False,
            "error": "expired",
            "repository": "acme/demo",
            "prNumber": 7,
            "headCommit": expected_head,
            "gitTree": expected_tree,
            "workflowRunId": 9001,
            "workflowRunAttempt": 1,
        }
        result = enumerate_and_select_receipt(
            [other, expected_exact],
            expected={
                "repository": "acme/demo",
                "prNumber": 7,
                "headCommit": expected_head,
                "gitTree": expected_tree,
                "workflowRunId": 9001,
                "workflowRunAttempt": 1,
            },
        )
        self.assertFalse(result["accepted"])
        self.assertEqual(result["code"], "expected_receipt_inaccessible")
        self.assertIsNone(result.get("selected"))

    def test_head_change_makes_prior_receipt_stale_even_if_tree_or_name_matches(self) -> None:
        old_head = _sha(1)
        new_head = _sha(3)
        tree = _sha(2)
        prior = {
            "id": "prior",
            "name": "linktrend-full-suite-receipt-7-1",
            "readable": True,
            "repository": "acme/demo",
            "prNumber": 7,
            "headCommit": old_head,
            "gitTree": tree,
            "lockDigest": DEP_DIGEST,
            "workflowRunId": 101,
            "workflowRunAttempt": 1,
            "receipt": _complete_receipt(candidateIdentity=_identity(head=old_head, tree=tree)),
        }
        row = classify_receipt_artifact(
            prior,
            expected={
                "repository": "acme/demo",
                "prNumber": 7,
                "headCommit": new_head,
                "gitTree": tree,
                "workflowRunId": 101,
                "workflowRunAttempt": 1,
            },
        )
        self.assertEqual(row["classification"], "stale_head")
        result = enumerate_and_select_receipt(
            [prior],
            expected={
                "repository": "acme/demo",
                "prNumber": 7,
                "headCommit": new_head,
                "gitTree": tree,
                "workflowRunId": 101,
                "workflowRunAttempt": 1,
            },
        )
        self.assertFalse(result["accepted"])
        self.assertEqual(result["code"], "exact_receipt_missing")


class MergeEligibilityReceiptTests(unittest.TestCase):
    def test_ordinary_phase_cannot_merge_without_exact_retained_receipt(self) -> None:
        head = _sha(1)
        tree = _sha(2)
        record = {
            "sealed": True,
            "sealedSha": head,
            "headSha": head,
            "candidateIdentity": {"sourceSha": head, "gitTreeSha": tree},
            "fast": {"status": "passed", "sha": head},
            "bugbot": {"status": "passed", "sha": head},
            "full": {"status": "passed", "sha": head},
        }
        base = phase_merge_eligibility(record, live_head_sha=head)
        self.assertTrue(base.eligible)
        blocked = phase_merge_eligibility_with_receipt(record, live_head_sha=head, retained_receipt=None)
        self.assertFalse(blocked.eligible)
        self.assertIn("retained_receipt_missing", blocked.detail)

        receipt = _complete_receipt(candidateIdentity=_identity(head=head, tree=tree))
        ok = phase_merge_eligibility_with_receipt(record, live_head_sha=head, retained_receipt=receipt)
        self.assertTrue(ok.eligible, ok.detail)

        wrong_head = _complete_receipt(candidateIdentity=_identity(head=_sha(9), tree=tree))
        stale = phase_merge_eligibility_with_receipt(record, live_head_sha=head, retained_receipt=wrong_head)
        self.assertFalse(stale.eligible)
        self.assertIn("retained_receipt_wrong_head", stale.detail)


class RecoveryDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "demo"
        self.repo.mkdir()
        run_git(self.repo, "init", "-q", "-b", "development")
        run_git(self.repo, "config", "user.email", "u06@example.invalid")
        run_git(self.repo, "config", "user.name", "U06 Test")
        (self.repo / "app.txt").write_text("v1\n", encoding="utf-8")
        (self.repo / ".ide-development").mkdir()
        state = {
            "packageName": "ide-development-managed-core",
            "packageVersion": "2.4.0",
            "packageDigest": "sha256:" + ("a" * 64),
            "dependencyDigest": DEP_DIGEST,
            "installedAt": "2026-08-17T00:00:00Z",
        }
        (self.repo / ".ide-development" / "installed-state.json").write_text(
            json.dumps(state, sort_keys=True) + "\n", encoding="utf-8"
        )
        (self.repo / ".ide-development" / "MANIFEST.json").write_text(
            json.dumps({"schemaVersion": 1, "packageVersion": "2.4.0", "files": []}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        run_git(self.repo, "add", ".")
        run_git(self.repo, "commit", "-qm", "integrated")
        self.head = run_git(self.repo, "rev-parse", "HEAD")
        self.tree = run_git(self.repo, "rev-parse", "HEAD^{tree}")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_valid_unchanged_tree_recovery_without_commit_or_pr(self) -> None:
        before = run_git(self.repo, "rev-parse", "HEAD")
        plan = validate_recovery_dispatch(
            repo=self.repo,
            repository="acme/demo",
            expected_ref="development",
            expected_commit=self.head,
            expected_tree=self.tree,
            package_version="2.4.0",
            checks={"fast": "success", "ci": "success", "security": "success"},
            dependency_digest=DEP_DIGEST,
        )
        self.assertTrue(plan["accepted"])
        self.assertEqual(plan["mode"], "recovery")
        self.assertEqual(plan["checkoutRef"], "development")
        self.assertEqual(plan["candidateHead"], self.head)
        self.assertEqual(plan["candidateTree"], self.tree)
        self.assertFalse(plan["opensPullRequest"])
        self.assertFalse(plan["createsCommit"])
        self.assertEqual(plan["receiptSchemaVersion"], 2)
        after = run_git(self.repo, "rev-parse", "HEAD")
        self.assertEqual(before, after)
        self.assertEqual([], run_git(self.repo, "status", "--porcelain").splitlines())

    def test_recovery_rejects_forged_changed_stale_missing_inputs(self) -> None:
        cases = [
            ({"expected_commit": _sha(9)}, "forged_or_wrong_commit"),
            ({"expected_tree": _sha(9)}, "forged_or_wrong_tree"),
            ({"expected_ref": "phase/fake"}, "recovery_ref_invalid"),
            ({"checks": {"fast": "success", "ci": "failure", "security": "success"}}, "stale_or_failed_checks"),
            ({"package_version": "9.9.9"}, "manifest_version_mismatch"),
            ({"dependency_digest": "sha256:" + ("0" * 64)}, "dependency_digest_mismatch"),
        ]
        for overrides, code in cases:
            kwargs = {
                "repo": self.repo,
                "repository": "acme/demo",
                "expected_ref": "development",
                "expected_commit": self.head,
                "expected_tree": self.tree,
                "package_version": "2.4.0",
                "checks": {"fast": "success", "ci": "success", "security": "success"},
                "dependency_digest": DEP_DIGEST,
            }
            kwargs.update(overrides)
            with self.assertRaisesRegex(RecoveryError, code):
                validate_recovery_dispatch(**kwargs)

        (self.repo / ".ide-development" / "MANIFEST.json").unlink()
        with self.assertRaisesRegex(RecoveryError, "manifest_missing"):
            validate_recovery_dispatch(
                repo=self.repo,
                repository="acme/demo",
                expected_ref="development",
                expected_commit=self.head,
                expected_tree=self.tree,
                package_version="2.4.0",
                checks={"fast": "success", "ci": "success", "security": "success"},
                dependency_digest=DEP_DIGEST,
            )

    def test_managed_drift_blocks_recovery(self) -> None:
        (self.repo / "app.txt").write_text("drift\n", encoding="utf-8")
        with self.assertRaisesRegex(RecoveryError, "managed_drift"):
            validate_recovery_dispatch(
                repo=self.repo,
                repository="acme/demo",
                expected_ref="development",
                expected_commit=self.head,
                expected_tree=self.tree,
                package_version="2.4.0",
                checks={"fast": "success", "ci": "success", "security": "success"},
                dependency_digest=DEP_DIGEST,
            )


class RecoveredReceiptPromotionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "promo"
        self.repo.mkdir()
        run_git(self.repo, "init", "-q", "-b", "development")
        run_git(self.repo, "config", "user.email", "u06@example.invalid")
        run_git(self.repo, "config", "user.name", "U06 Test")
        (self.repo / "src").mkdir()
        (self.repo / ".github" / "workflows").mkdir(parents=True)
        (self.repo / "profiles").mkdir()
        (self.repo / "src" / "app.txt").write_text("stable\n", encoding="utf-8")
        (self.repo / "deps.lock").write_text("lock\n", encoding="utf-8")
        (self.repo / "profiles" / "full.json").write_text('{"suite":"full"}\n', encoding="utf-8")
        (self.repo / ".github" / "workflows" / "check.yml").write_text("name: Check\n", encoding="utf-8")
        run_git(self.repo, "add", ".")
        run_git(self.repo, "commit", "-qm", "base")
        run_git(self.repo, "remote", "add", "origin", "https://github.com/acme/promo.git")
        self.identity = receipts.compute_candidate_identity(
            self.repo,
            ["deps.lock"],
            "full",
            profile_files=["profiles/full.json"],
            workflow_files=[".github/workflows/check.yml"],
            source_branch="development",
        )
        raw = {
            "schemaVersion": 2,
            "candidateIdentity": self.identity.to_dict(),
            "workflowRunId": 55,
            "workflowRunAttempt": 1,
            "runnerLabel": "ubuntu-24.04-arm",
            "startedAt": "2026-08-17T02:00:00Z",
            "completedAt": "2026-08-17T02:05:00Z",
            "conclusion": "success",
            "commandDigest": COMMAND_DIGEST,
            "evidenceDigests": {"evidence/full.log": DIGEST},
            "recovery": True,
        }
        # recovery marker is evidence-only metadata outside schema; strip before write
        self.receipt_path = Path(self.tmp.name) / "receipt.json"
        receipts.write_receipt(
            {k: v for k, v in raw.items() if k != "recovery"},
            self.receipt_path,
        )
        self.receipt = receipts.load_json(self.receipt_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_recovered_receipt_accepted_for_unchanged_promotion_rejected_after_change(self) -> None:
        accepted = evaluate_recovered_receipt_for_promotion(
            self.receipt,
            self.identity,
            required_gate="full-gate",
        )
        self.assertTrue(accepted["accepted"], accepted)
        decision = verify_receipt_payload(self.receipt, self.identity, "full-gate")
        self.assertTrue(decision.accepted)

        (self.repo / "src" / "app.txt").write_text("changed\n", encoding="utf-8")
        run_git(self.repo, "add", "src/app.txt")
        run_git(self.repo, "commit", "-qm", "content change")
        changed = receipts.compute_candidate_identity(
            self.repo,
            ["deps.lock"],
            "full",
            profile_files=["profiles/full.json"],
            workflow_files=[".github/workflows/check.yml"],
            source_branch="development",
        )
        rejected = evaluate_recovered_receipt_for_promotion(
            self.receipt,
            changed,
            required_gate="full-gate",
        )
        self.assertFalse(rejected["accepted"])
        self.assertEqual(rejected["code"], "content_changed")


if __name__ == "__main__":
    unittest.main()
