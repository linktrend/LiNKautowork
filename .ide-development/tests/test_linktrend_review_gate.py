"""Focused tests for WP-U01 Linktrend Review Gate (Packager #329+#330 reconcile)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.gitops.linktrend_review_gate import (
    EVIDENCE_CHANNEL_CANDIDATE_FILE,
    EVIDENCE_CHANNEL_GITHUB_CHECK_RUN,
    EVIDENCE_CHANNEL_OPERATOR_PRIVILEGED,
    EVIDENCE_CHANNEL_PROVIDER_STATUS_API,
    EVIDENCE_CHANNEL_REPAIR_OBSERVER_RECORD,
    FULL_SUITE_CONTEXT,
    MAX_INFRASTRUCTURE_ATTEMPTS,
    OUTCOME_ADVISORY,
    OUTCOME_FAILED,
    OUTCOME_FINDINGS,
    OUTCOME_PASSED,
    OUTCOME_UNKNOWN,
    RAW_BUGBOT_CONTEXT,
    REVIEW_GATE_CONTEXT,
    TRUSTED_PROVIDER_SOURCES,
    ReviewGateError,
    assert_full_suite_allows_bugbot,
    build_durable_founder_alert,
    build_fallback_request_comment,
    build_workflow_file_shas_payload,
    classify_bugbot_result,
    comment_bodies_from_slurp,
    count_infrastructure_attempts,
    decide_founder_alert_publish,
    evaluate_fallback_review,
    evaluate_github_approval,
    extract_trusted_full_receipt_from_check_runs,
    extract_trusted_provider_evidence_from_check_runs,
    flatten_gh_slurp_pages,
    founder_alert_already_recorded,
    founder_alert_marker,
    gate_commit_status,
    infrastructure_attempt_marker,
    invalidate_if_head_changed,
    issue_bodies_from_slurp,
    migrated_required_contexts,
    normalize_full_receipt_payload,
    overlay_retained_full_suite_receipt,
    reject_third_infrastructure_attempt,
    reject_undocumented_task_hold,
    require_full_receipt_for_gate_success,
    require_no_raw_bugbot_required,
    require_review_gate_on_development,
    simulate_repeated_founder_alert_events,
    structured_bugbot_findings_present,
    verified_provider_unavailability,
    TRUSTED_FULL_RECEIPT_PROVENANCE_KINDS,
    TRUSTED_PROVIDER_PROVENANCE_KINDS,
    authenticate_provider_unavailability_evidence,
    findings_present_from_event_evidence,
    provider_error_from_usage_limit_repair_issues,
    stamp_full_receipt_provenance,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "core" / "managed-core" / "schemas" / "linktrend-review-gate.schema.json"
MODULE = ROOT / "scripts" / "gitops" / "linktrend_review_gate.py"
DOCTRINE = ROOT / "docs" / "contracts" / "LINKTREND-REVIEW-GATE.md"
WORKFLOW = ROOT / ".github" / "workflows" / "linktrend-review-gate.yml"
MANAGED_WORKFLOW = ROOT / "core" / "github" / "managed-workflows" / "linktrend-review-gate.yml"
OBSERVER_TEMPLATE = ROOT / "core" / "github" / "managed-workflows" / "linktrend-repair-observer.yml"
HEAD = "a" * 40
TREE = "b" * 40
REPO = "linktrend/IDE-Development"
DEFAULT_BRANCH = "development"
DEFAULT_WF_BLOB = "c" * 40
REWRITTEN_WF_BLOB = "d" * 40
FULL_WF_PATH = ".github/workflows/linktrend-integrator-merge.yml"
PROVIDER_WF_PATH = ".github/workflows/linktrend-repair-observer.yml"
COLLISION_WF_PATH = ".github/workflows/candidate-forged-full.yml"


def _actions_check(
    *,
    name: str,
    run_id: int,
    summary: str,
    app_slug: str = "github-actions",
    head_sha: str = HEAD,
    check_id: int | None = None,
    suite_id: int | None = None,
    conclusion: str = "success",
    details_run_id: int | None = None,
) -> dict:
    cid = check_id if check_id is not None else run_id * 10
    sid = suite_id if suite_id is not None else run_id * 100
    details = details_run_id if details_run_id is not None else run_id
    return {
        "id": cid,
        "name": name,
        "head_sha": head_sha,
        "conclusion": conclusion,
        "app": {"slug": app_slug},
        "check_suite": {"id": sid},
        "details_url": f"https://github.com/{REPO}/actions/runs/{details}",
        "output": {"summary": summary},
    }


def _workflow_run(
    *,
    run_id: int,
    path: str,
    head_branch: str = "issue/329-candidate",
    head_sha: str = HEAD,
    suite_id: int | None = None,
    conclusion: str = "success",
    status: str = "completed",
) -> dict:
    return {
        "id": run_id,
        "path": path,
        "head_branch": head_branch,
        "head_sha": head_sha,
        "check_suite_id": suite_id if suite_id is not None else run_id * 100,
        "conclusion": conclusion,
        "status": status,
    }


def _jobs_for(
    *,
    run_id: int,
    check_id: int,
    name: str,
    conclusion: str = "success",
) -> dict:
    return {
        "jobs": [
            {
                "id": check_id + 1,
                "run_id": run_id,
                "name": name,
                "status": "completed",
                "conclusion": conclusion,
                "check_run_url": f"https://api.github.com/repos/{REPO}/check-runs/{check_id}",
            }
        ]
    }


def _wf_shas(
    path: str,
    *,
    default: str = DEFAULT_WF_BLOB,
    head: str | None = DEFAULT_WF_BLOB,
    by_head: dict[str, str] | None = None,
) -> dict:
    entry: dict = {"default": default}
    if by_head is not None:
        entry["byHead"] = by_head
    elif head is not None:
        entry["head"] = head
    return {path: entry}


def _trusted_extract_kwargs(
    *,
    run_id: int,
    path: str,
    name: str,
    head_branch: str = DEFAULT_BRANCH,
    suite_id: int | None = None,
    check_id: int | None = None,
    shas: dict | None = None,
) -> dict:
    cid = check_id if check_id is not None else run_id * 10
    sid = suite_id if suite_id is not None else run_id * 100
    return {
        "default_branch": DEFAULT_BRANCH,
        "workflow_runs": {
            "workflow_runs": [
                _workflow_run(
                    run_id=run_id,
                    path=path,
                    head_branch=head_branch,
                    suite_id=sid,
                )
            ]
        },
        "workflow_jobs": _jobs_for(run_id=run_id, check_id=cid, name=name),
        "workflow_file_shas": shas
        if shas is not None
        else _wf_shas(path, head=None if head_branch == DEFAULT_BRANCH else DEFAULT_WF_BLOB),
    }


def _trusted_provenance(kind: str = "github.repair_task.api") -> dict:
    return {
        "kind": kind,
        "headSha": HEAD,
        "authenticated": True,
        "evidenceRef": "test",
    }

def _verified_quota(*, source: str = "repair_observer.usage_limit") -> dict:
    return {
        "verified": True,
        "class": "quota",
        "source": source,
        "headSha": HEAD,
        "provenance": _trusted_provenance(
            "github.repair_task.api"
            if source == "repair_observer.usage_limit"
            else (
                "provider_status_api.authenticated"
                if source == "provider_status_api"
                else "github.repository_variable"
            )
        ),
    }

def _trusted_full_receipt(**overrides) -> dict:
    payload = {
        "name": FULL_SUITE_CONTEXT,
        "headSha": HEAD,
        "gitTree": TREE,
        "status": "success",
        "provenance": {
            "kind": "github.check_runs.api",
            "headSha": HEAD,
            "authenticated": True,
            "evidenceRef": "checks:test",
        },
    }
    payload.update(overrides)
    return payload


# Bootstrap omits live ruleset/evaluator/observer product migrations (AC-U05-14).
_BOOTSTRAP_SKIP_SURFACES = (
    "bootstrap scope: deferred to sealed product candidate / later ruleset migration; "
    "do not copy verifier repair onto PR #326"
)




class LinktrendReviewGateTests(unittest.TestCase):
    def test_packaged_surfaces_exist(self) -> None:
        self.assertTrue(MODULE.is_file())
        self.assertTrue(SCHEMA.is_file())
        self.assertTrue(DOCTRINE.is_file())
        self.assertTrue(WORKFLOW.is_file())
        self.assertTrue(MANAGED_WORKFLOW.is_file())
        self.assertIn("needs: full", (ROOT / ".github/workflows/linktrend-integrator-merge.yml").read_text())
        integrator = (ROOT / ".github/workflows/linktrend-integrator-merge.yml").read_text()
        self.assertIn("gitTree={identity.git_tree}", integrator)
        self.assertEqual(
            integrator,
            (ROOT / "core/github/managed-workflows/linktrend-integrator-merge.yml").read_text(),
        )
        # Default-branch trust boundary: live workflow == managed template bytes.
        live = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(live, MANAGED_WORKFLOW.read_text(encoding="utf-8"))
        self.assertIn("on:\n  check_run:", live)
        self.assertIn("Linktrend Review Gate", live)
        self.assertIn("advisory_must_not_claim_bugbot_pass", live)
        self.assertIn("require-full-receipt", live)
        self.assertNotIn(".gitTree=$t", live)
        doctrine = DOCTRINE.read_text(encoding="utf-8")
        packaged = (
            ROOT / "core/managed-core/content/doctrine/LINKTREND-REVIEW-GATE.md"
        ).read_text(encoding="utf-8")
        self.assertEqual(doctrine, packaged)
        self.assertIn("full_receipt_missing_trusted_check", doctrine)
        self.assertRegex(doctrine, r"fail-closed producer\s+binding")
        self.assertIn("unbound name-only Checks fallback", doctrine)
        self.assertNotIn(
            "Prefer producer-bound Checks extraction (#329); else provenance-stamped Checks (#330).",
            doctrine,
        )
        self.assertIn("`FULL_RAW`", doctrine)  # named only as the forbidden bypass

    def _classify(self, **kwargs):
        base = dict(
            repository=REPO,
            head_sha=HEAD,
            git_tree=TREE,
            pull_request=322,
            bugbot_state="completed",
            bugbot_conclusion="success",
            infrastructure_attempts=0,
            result_head_sha=HEAD,
        )
        base.update(kwargs)
        return classify_bugbot_result(**base)

    def test_all_classified_outcomes(self) -> None:
        passed = self._classify()
        self.assertEqual(passed.outcome, OUTCOME_PASSED)
        self.assertTrue(passed.gateSuccess)
        self.assertTrue(passed.bugbotPassedClaim)

        findings = self._classify(findings_present=True)
        self.assertEqual(findings.outcome, OUTCOME_FINDINGS)
        self.assertFalse(findings.gateSuccess)

        annotated = self._classify(annotations_count=2, bugbot_conclusion="success")
        self.assertEqual(annotated.outcome, OUTCOME_FINDINGS)
        self.assertFalse(annotated.gateSuccess)
        self.assertFalse(annotated.bugbotPassedClaim)

        action_required = self._classify(
            bugbot_state="completed",
            bugbot_conclusion="action_required",
        )
        self.assertEqual(action_required.outcome, OUTCOME_FINDINGS)
        self.assertFalse(action_required.gateSuccess)

        failed = self._classify(bugbot_state="failure", bugbot_conclusion="failure")
        self.assertEqual(failed.outcome, OUTCOME_FAILED)
        self.assertFalse(failed.gateSuccess)

        advisory = self._classify(
            bugbot_state="completed",
            bugbot_conclusion="neutral",
            provider_error=_verified_quota(),
            provider_evidence_channel=EVIDENCE_CHANNEL_REPAIR_OBSERVER_RECORD,
            infrastructure_attempts=1,
        )
        self.assertEqual(advisory.outcome, OUTCOME_ADVISORY)
        self.assertTrue(advisory.gateSuccess)
        self.assertFalse(advisory.bugbotPassedClaim)
        self.assertTrue(advisory.alertFounder)
        self.assertIn("advisory-unavailable", advisory.sanitizedAlert or "")
        status = gate_commit_status(advisory)
        self.assertEqual(status["state"], "success")
        self.assertIn("not a Bugbot pass", status["description"])

        unknown = self._classify(bugbot_conclusion="neutral")
        self.assertEqual(unknown.outcome, OUTCOME_UNKNOWN)
        self.assertFalse(unknown.gateSuccess)

        Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(passed.to_dict())
        Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(advisory.to_dict())

    def test_failure_never_becomes_advisory_via_heuristic(self) -> None:
        # Free-text / unverified payload must not convert failure into gate success.
        heuristic = {"class": "quota", "verified": False, "source": "repair_observer.usage_limit"}
        result = self._classify(
            bugbot_state="failure",
            bugbot_conclusion="failure",
            provider_error=heuristic,
        )
        self.assertEqual(result.outcome, OUTCOME_FAILED)
        self.assertFalse(result.gateSuccess)
        self.assertIsNone(verified_provider_unavailability({"class": "quota"}))
        self.assertIsNone(
            verified_provider_unavailability(
                {"verified": True, "class": "quota", "source": "grep-heuristic"},
                evidence_channel=EVIDENCE_CHANNEL_REPAIR_OBSERVER_RECORD,
            )
        )
        self.assertIsNone(
            verified_provider_unavailability(
                _verified_quota(),
                evidence_channel=EVIDENCE_CHANNEL_CANDIDATE_FILE,
            )
        )
        self.assertEqual(
            verified_provider_unavailability(
                _verified_quota(),
                evidence_channel=EVIDENCE_CHANNEL_REPAIR_OBSERVER_RECORD,
            ),
            "quota",
        )

    def test_fail_closed_missing_malformed_forged_wrong_head(self) -> None:
        for kwargs in (
            {"missing": True},
            {"malformed": True},
            {"forged": True},
            {"result_head_sha": "c" * 40},
        ):
            result = self._classify(**kwargs)
            self.assertEqual(result.outcome, OUTCOME_UNKNOWN)
            self.assertFalse(result.gateSuccess)

    def test_full_failure_blocks_bugbot_request(self) -> None:
        with self.assertRaises(ReviewGateError) as ctx:
            assert_full_suite_allows_bugbot("failure")
        self.assertEqual(ctx.exception.code, "bugbot_before_full_forbidden")
        assert_full_suite_allows_bugbot("success")

    def test_full_receipt_required_before_successful_gate_publish(self) -> None:
        good = {
            "name": FULL_SUITE_CONTEXT,
            "headSha": HEAD,
            "gitTree": TREE,
            "status": "success",
        }
        channel = EVIDENCE_CHANNEL_GITHUB_CHECK_RUN
        require_full_receipt_for_gate_success(
            gate_success=True,
            full_receipt=good,
            head_sha=HEAD,
            git_tree=TREE,
            evidence_channel=channel,
        )
        require_full_receipt_for_gate_success(
            gate_success=False, full_receipt=None, head_sha=HEAD, git_tree=TREE
        )
        with self.assertRaises(ReviewGateError) as untrusted:
            require_full_receipt_for_gate_success(
                gate_success=True,
                full_receipt=good,
                head_sha=HEAD,
                git_tree=TREE,
                evidence_channel=EVIDENCE_CHANNEL_CANDIDATE_FILE,
            )
        self.assertIn(untrusted.exception.code, {"full_receipt_untrusted_channel", "full_receipt_untrusted_provenance"})
        with self.assertRaises(ReviewGateError) as missing_channel:
            require_full_receipt_for_gate_success(
                gate_success=True, full_receipt=good, head_sha=HEAD, git_tree=TREE
            )
        self.assertIn(missing_channel.exception.code, {"full_receipt_untrusted_channel", "full_receipt_untrusted_provenance"})
        with self.assertRaises(ReviewGateError) as missing:
            require_full_receipt_for_gate_success(
                gate_success=True,
                full_receipt=None,
                head_sha=HEAD,
                git_tree=TREE,
                evidence_channel=channel,
            )
        self.assertEqual(missing.exception.code, "full_receipt_missing")
        with self.assertRaises(ReviewGateError) as wrong_head:
            require_full_receipt_for_gate_success(
                gate_success=True,
                full_receipt={**good, "headSha": "c" * 40},
                head_sha=HEAD,
                git_tree=TREE,
                evidence_channel=channel,
            )
        self.assertEqual(wrong_head.exception.code, "full_receipt_wrong_head")
        with self.assertRaises(ReviewGateError) as wrong_tree:
            require_full_receipt_for_gate_success(
                gate_success=True,
                full_receipt={**good, "gitTree": "d" * 40},
                head_sha=HEAD,
                git_tree=TREE,
                evidence_channel=channel,
            )
        self.assertEqual(wrong_tree.exception.code, "full_receipt_wrong_tree")
        with self.assertRaises(ReviewGateError) as stale:
            require_full_receipt_for_gate_success(
                gate_success=True,
                full_receipt={**good, "status": "failure"},
                head_sha=HEAD,
                git_tree=TREE,
                evidence_channel=channel,
            )
        self.assertEqual(stale.exception.code, "full_receipt_not_success")
        with self.assertRaises(ReviewGateError) as missing_tree:
            require_full_receipt_for_gate_success(
                gate_success=True,
                full_receipt={"name": FULL_SUITE_CONTEXT, "headSha": HEAD, "status": "success"},
                head_sha=HEAD,
                git_tree=TREE,
                evidence_channel=channel,
            )
        self.assertEqual(missing_tree.exception.code, "full_receipt_missing_tree")
        # FullSuiteReceipt v2 candidateIdentity.gitTreeSha (legacy) is preserved.
        v2_legacy = {
            "name": FULL_SUITE_CONTEXT,
            "candidateIdentity": {"sourceSha": HEAD, "gitTreeSha": TREE},
            "conclusion": "success",
        }
        require_full_receipt_for_gate_success(
            gate_success=True,
            full_receipt=v2_legacy,
            head_sha=HEAD,
            git_tree=TREE,
            evidence_channel=channel,
        )
        # SchemaVersion 2 producer shape: candidateIdentity.gitTree + headCommit.
        v2_canonical = {
            "schemaVersion": 2,
            "candidateIdentity": {
                "repository": REPO,
                "sourceBranch": "phase/example",
                "headCommit": HEAD,
                "gitTree": TREE,
                "dependencyDigest": "sha256:" + ("1" * 64),
                "profileDigest": "sha256:" + ("2" * 64),
                "workflowDigest": "sha256:" + ("3" * 64),
            },
            "conclusion": "success",
        }
        require_full_receipt_for_gate_success(
            gate_success=True,
            full_receipt=v2_canonical,
            head_sha=HEAD,
            git_tree=TREE,
            evidence_channel=channel,
        )

    def test_normalize_full_receipt_never_injects_live_tree(self) -> None:
        raw = {
            "name": FULL_SUITE_CONTEXT,
            "headSha": HEAD,
            "status": "success",
            "outputSummary": f"head={HEAD}\ngitTreeSha={'d' * 40}\n",
        }
        normalized = normalize_full_receipt_payload(raw)
        assert normalized is not None
        self.assertEqual(normalized["gitTree"], "d" * 40)
        self.assertNotEqual(normalized["gitTree"], TREE)
        # Empty receipt stays empty — callers must not fill from live TREE.
        empty = normalize_full_receipt_payload(
            {"name": FULL_SUITE_CONTEXT, "headSha": HEAD, "status": "success"}
        )
        assert empty is not None
        self.assertEqual(empty["gitTree"], "")
        # Prefer candidateIdentity.gitTree over legacy gitTreeSha when both differ.
        both = normalize_full_receipt_payload(
            {
                "candidateIdentity": {
                    "headCommit": HEAD,
                    "gitTree": "c" * 40,
                    "gitTreeSha": "d" * 40,
                },
                "conclusion": "success",
            }
        )
        assert both is not None
        self.assertEqual(both["gitTree"], "c" * 40)
        self.assertEqual(both["headSha"], HEAD)

    def test_overlay_retained_full_suite_receipt_fills_git_tree(self) -> None:
        """Producer-bound extract with empty tree gains gitTree from retained v2 receipt."""
        extracted = {
            "receipt": {
                "name": FULL_SUITE_CONTEXT,
                "headSha": HEAD,
                "gitTree": "",
                "status": "success",
            },
            "evidenceChannel": EVIDENCE_CHANNEL_GITHUB_CHECK_RUN,
            "workflowRunId": 32111296118,
            "checkRunId": 1,
            "checkSuiteId": 2,
            "workflowPath": FULL_WF_PATH,
        }
        retained = {
            "schemaVersion": 2,
            "candidateIdentity": {
                "headCommit": HEAD,
                "gitTree": TREE,
            },
            "conclusion": "success",
        }
        merged = overlay_retained_full_suite_receipt(extracted, retained)
        assert merged is not None
        self.assertEqual(merged["receipt"]["gitTree"], TREE)
        self.assertEqual(merged["receipt"]["headSha"], HEAD)
        self.assertEqual(merged["evidenceChannel"], EVIDENCE_CHANNEL_GITHUB_CHECK_RUN)
        # Never invent tree from the live TREE argument — retained must carry it.
        with self.assertRaises(ReviewGateError) as missing:
            overlay_retained_full_suite_receipt(
                extracted,
                {"candidateIdentity": {"headCommit": HEAD}, "conclusion": "success"},
            )
        self.assertEqual(missing.exception.code, "full_receipt_missing_tree")
        with self.assertRaises(ReviewGateError) as wrong_head:
            overlay_retained_full_suite_receipt(
                extracted,
                {
                    "candidateIdentity": {"headCommit": "c" * 40, "gitTree": TREE},
                    "conclusion": "success",
                },
            )
        self.assertEqual(wrong_head.exception.code, "full_receipt_wrong_head")

    def test_infrastructure_attempts_count_only_infra_markers(self) -> None:
        markers = [
            infrastructure_attempt_marker(HEAD, 1),
            "ordinary classification note",
            founder_alert_marker(HEAD),
            infrastructure_attempt_marker(HEAD, 2),
            infrastructure_attempt_marker("c" * 40, 1),
        ]
        self.assertEqual(count_infrastructure_attempts(markers, head_sha=HEAD), 2)
        reject_third_infrastructure_attempt(MAX_INFRASTRUCTURE_ATTEMPTS)
        with self.assertRaises(ReviewGateError) as ctx:
            reject_third_infrastructure_attempt(MAX_INFRASTRUCTURE_ATTEMPTS + 1)
        self.assertEqual(ctx.exception.code, "infrastructure_attempt_limit")
        # Ordinary classifications with attempts=0 do not hit the infra limit.
        self.assertEqual(self._classify(infrastructure_attempts=0).outcome, OUTCOME_PASSED)
        with self.assertRaises(ReviewGateError):
            self._classify(
                provider_error=_verified_quota(),
                provider_evidence_channel=EVIDENCE_CHANNEL_REPAIR_OBSERVER_RECORD,
                bugbot_conclusion="neutral",
                infrastructure_attempts=3,
            )

    def test_new_commit_invalidates_prior_outcome(self) -> None:
        with self.assertRaises(ReviewGateError) as ctx:
            invalidate_if_head_changed(bound_head=HEAD, live_head="d" * 40)
        self.assertEqual(ctx.exception.code, "stale_head")

    def test_raw_bugbot_required_contexts_rejected(self) -> None:
        migrated = migrated_required_contexts([RAW_BUGBOT_CONTEXT, "Linktrend Fast Gate"])
        self.assertEqual(migrated[0], REVIEW_GATE_CONTEXT)
        require_review_gate_on_development(migrated)
        with self.assertRaises(ReviewGateError) as ctx:
            require_no_raw_bugbot_required([RAW_BUGBOT_CONTEXT])
        self.assertEqual(ctx.exception.code, "raw_bugbot_required")
        with self.assertRaises(ReviewGateError):
            require_review_gate_on_development(["Linktrend Fast Gate"])

    def test_protection_and_consumer_defaults_migrated(self) -> None:
        from scripts.gitops import repository_protection as rp
        from scripts.gitops import ruleset_plan as plan

        self.assertEqual(rp.BUGBOT_CHECK, REVIEW_GATE_CONTEXT)
        self.assertNotIn(RAW_BUGBOT_CONTEXT, rp.managed_baseline("development"))
        self.assertIn(REVIEW_GATE_CONTEXT, rp.managed_baseline("development"))
        self.assertIn(REVIEW_GATE_CONTEXT, plan.CONTEXTS["development"])
        self.assertNotIn(RAW_BUGBOT_CONTEXT, plan.CONTEXTS["development"])
        consumer = json.loads((ROOT / ".github/linktrend-gitops-consumer.json").read_text())
        self.assertEqual(consumer["bugbotCheckName"], REVIEW_GATE_CONTEXT)
        self.assertEqual(consumer["reviewGateCheckName"], REVIEW_GATE_CONTEXT)
        self.assertEqual(consumer["bugbotProviderCheckName"], RAW_BUGBOT_CONTEXT)

    def test_managed_surfaces_reject_raw_bugbot_required_defaults(self) -> None:
        wire = (ROOT / "scripts/wire-repo.sh").read_text()
        self.assertIn('BUGBOT_NAME="${BUGBOT_NAME:-Linktrend Review Gate}"', wire)
        self.assertIn('"bugbotProviderCheckName": "Cursor Bugbot"', wire)
        verify = (ROOT / "scripts/verify-ide-development.sh").read_text()
        self.assertIn('__LINKTREND_BUGBOT_PROVIDER_CHECK_NAME__", "Cursor Bugbot"', verify)
        self.assertIn('__LINKTREND_REVIEW_GATE_CHECK_NAME__", "Linktrend Review Gate"', verify)
        apply = (ROOT / "scripts/apply-development-merge-ruleset.sh").read_text()
        self.assertIn("Linktrend Review Gate", apply)
        self.assertNotIn('"Cursor Bugbot"', apply)
        self.assertNotIn("\n  \"Cursor Bugbot\"\n", apply)
        coord = (ROOT / "scripts/tests/test_local_coordinator_workflow_profile.sh").read_text()
        self.assertIn("Linktrend Review Gate", coord)
        self.assertNotIn('"bugbotCheckName": "Cursor Bugbot"', coord)
        observer = OBSERVER_TEMPLATE.read_text()
        self.assertIn("__LINKTREND_BUGBOT_PROVIDER_CHECK_NAME__", observer)
        self.assertIn("__LINKTREND_REVIEW_GATE_CHECK_NAME__", observer)
        self.assertIn(
            "github.event.check_run.name == '__LINKTREND_BUGBOT_PROVIDER_CHECK_NAME__'",
            observer,
        )
        bootstrap = (ROOT / "core/github/managed-runtime/cursor-gitops-bootstrap.mdc").read_text()
        self.assertIn("Linktrend Review Gate", bootstrap)
        self.assertNotIn("named gates + Cursor Bugbot", bootstrap)
        cursor_bootstrap = (ROOT / ".cursor/rules/cursor-gitops-bootstrap.mdc").read_text()
        self.assertIn("named gates + Linktrend Review Gate", cursor_bootstrap)
        self.assertNotIn("named gates + Cursor Bugbot", cursor_bootstrap)
        external = (ROOT / "docs/contracts/EXTERNAL-STATE-AUDIT.md").read_text()
        self.assertIn("Linktrend Review Gate", external)
        self.assertNotIn("`Cursor Bugbot`", external)
        for rel in (
            "scripts/tests/test-consumer-profile-matrix.sh",
            "scripts/tests/test_local_coordinator_workflow_profile.sh",
            "scripts/tests/test-managed-runner-routing.sh",
        ):
            text = (ROOT / rel).read_text()
            self.assertIn("bugbotProviderCheckName", text)
            self.assertRegex(
                text,
                r'"bugbotProviderCheckName"\s*:\s*"Cursor Bugbot"',
            )
            self.assertNotRegex(
                text,
                r'"bugbotProviderCheckName"\s*:\s*"Linktrend Review Gate"',
            )

    def test_workflow_forbids_heuristic_and_wires_alert_fallback_full(self) -> None:
        for path in (WORKFLOW, MANAGED_WORKFLOW):
            text = path.read_text()
            self.assertIn("Free-text provider heuristics are forbidden", text)
            self.assertNotIn("grep -Eq 'quota|rate limit", text)
            self.assertIn("founder-alert", text)
            self.assertIn("founder-alert-dedupe", text)
            self.assertIn("fallback", text)
            self.assertIn("require-full-receipt", text)
            self.assertIn("extract-trusted-full-receipt", text)
            self.assertIn("overlay-retained-full-receipt", text)
            self.assertIn("linktrend-full-suite-receipt-", text)
            self.assertIn("full_receipt_artifact_not_unique_or_missing", text)
            self.assertIn("count-infra-attempts", text)
            self.assertIn("issues: write", text)
            self.assertNotIn("contents/.linktrend/", text)
            # Candidate paths may be named only in ignore notes; never cat/read them.
            self.assertIn("ignoring_candidate_provider_error_file", text)
            self.assertIn("ignoring_candidate_full_suite_receipt_file", text)
            self.assertNotRegex(
                text,
                r'cat\s+"\$\{CANDIDATE_DIR\}/\.linktrend/review-gate-provider-error\.json"',
            )
            self.assertNotRegex(
                text,
                r'cat\s+"\$\{CANDIDATE_DIR\}/\.linktrend/full-suite-receipt\.json"',
            )
            self.assertIn("extract-trusted-provider-evidence", text)
            self.assertIn("extract-trusted-full-receipt", text)
            self.assertIn("--default-branch", text)
            self.assertIn("--workflow-runs-json", text)
            self.assertIn("--workflow-jobs-json", text)
            self.assertIn("--workflow-file-shas-json", text)
            self.assertIn("resolve-workflow-file-shas", text)
            self.assertIn("resolve-workflow-jobs", text)
            self.assertIn("actions/runs?head_sha=", text)
            self.assertIn("HOLD: workflow_runs_unreadable", text)
            self.assertIn("HOLD: workflow_jobs_unreadable", text)
            self.assertIn("HOLD: workflow_file_shas_unreadable", text)
            self.assertIn("--provider-evidence-channel", text)
            self.assertIn("--evidence-channel", text)
            # Full Suite: fail-closed producer binding only — no unbound name-only fallback.
            self.assertIn("full_receipt_missing_trusted_check", text)
            self.assertIn("Fail-closed producer binding", text)
            self.assertIn(
                'producer-bound-artifact:${FULL_RUN_ID}:${ARTIFACT_NAME}',
                text,
            )
            self.assertNotIn("FULL_RAW", text)
            self.assertNotIn('select(.name=="Linktrend Full Suite")', text)
            self.assertNotIn(
                'producer-bound-checks:${HEAD_SHA}:Linktrend Full Suite',
                text,
            )
            self.assertNotIn(
                '--provenance-evidence-ref "checks:${HEAD_SHA}:Linktrend Full Suite"',
                text,
            )
            self.assertNotIn(
                "Prefer producer-bound Checks extraction (#329); else provenance-stamped Checks (#330).",
                text,
            )
            # U01-R3: never overwrite receipt tree with live TREE.
            self.assertNotIn(".gitTree=$t", text)
            self.assertNotIn("gitTree:$t", text)
            self.assertIn("never overwrite with live TREE", text)
            # U01-R2: dedupe from issue bodies with fail-closed read.
            self.assertIn("flatten-issue-bodies", text)
            self.assertIn("founder_alert_dedupe_unreadable", text)
            self.assertIn("--paginate --slurp", text)
            # Slurp payloads must enter via stdin, never argv interpolation.
            self.assertIn("--slurp-json -", text)
            self.assertIn("--issue-bodies-json -", text)
            self.assertIn("--markers-json -", text)
            self.assertNotIn('--slurp-json "${', text)
            self.assertNotIn("--slurp-json \"${", text)
            self.assertNotIn("MARKERS_SLURP", text)
            self.assertNotIn("ALERT_SLURP", text)
            # Marker reads must not fail-open to empty arrays.
            self.assertNotIn("2>/dev/null || echo '[]'", text)
            self.assertNotIn("|| echo '[]'", text)
            self.assertIn("flatten-comment-bodies", text)
            self.assertIn("HOLD: infra_marker_read_failed", text)
            self.assertIn("set -euo pipefail", text)
            # Trust boundary: default-branch scripts; candidate is data only.
            self.assertIn("github.event.repository.default_branch", text)
            self.assertIn("Checkout trusted default branch only (scripts)", text)
            self.assertNotIn("ref: ${{ github.event.check_run.head_sha }}", text)
            # detect-findings may consume event summary/title; never execute candidate scripts.
            self.assertIn("CHECK_DETAILS", text)
            self.assertIn("detect-findings", text)
            self.assertIn("CHECK_ANNOTATIONS_COUNT", text)
            self.assertIn("--annotations-count", text)
            self.assertIn('GATE_PY="${TRUSTED_ROOT}/scripts/gitops/linktrend_review_gate.py"', text)
            self.assertIn('python3 "${GATE_PY}" classify', text)
            self.assertIn("extract-trusted-provider-evidence", text)
            self.assertIn("statuses: write", text)
            # U01-R4: infra marker publication is fail-closed.
            self.assertIn("infra_attempt_marker_persist_failed", text)
            self.assertNotIn('-f body="${INFRA_MARKER}" >/dev/null || true', text)

    def test_pr_cannot_rewrite_classifier_or_self_approve(self) -> None:
        """Negative: PR head must not supply executable classifier scripts."""
        live = WORKFLOW.read_text(encoding="utf-8")
        managed = MANAGED_WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(live, managed)
        for text in (live, managed):
            self.assertIn("ref: ${{ github.event.repository.default_branch }}", text)
            self.assertNotIn("ref: ${{ github.event.check_run.head_sha }}", text)
            self.assertNotIn("ref: ${{ github.event.pull_request.head.sha }}", text)
            self.assertNotIn("untrusted-source-data/scripts", text)
            # Scripts execute from trusted checkout root only.
            self.assertIn('GATE_PY="${TRUSTED_ROOT}/scripts/gitops/linktrend_review_gate.py"', text)
            self.assertIn('python3 "${GATE_PY}" classify', text)
            # Event summary feeds detect-findings only; classifier scripts stay default-branch.
            self.assertIn("detect-findings", text)
            self.assertIn("github.event.check_run.output.summary", text)

        # Missing / neutral / free-text provider hints never become pass.
        self.assertEqual(self._classify(missing=True).outcome, OUTCOME_UNKNOWN)
        self.assertFalse(self._classify(missing=True).gateSuccess)
        neutral = self._classify(bugbot_conclusion="neutral")
        self.assertEqual(neutral.outcome, OUTCOME_UNKNOWN)
        self.assertFalse(neutral.gateSuccess)
        heuristic = self._classify(
            bugbot_state="completed",
            bugbot_conclusion="success",
            provider_error={
                "verified": False,
                "class": "quota",
                "source": "candidate-free-text-says-clean",
            },
        )
        # Unverified provider error is ignored; clean success remains success.
        self.assertEqual(heuristic.outcome, OUTCOME_PASSED)
        # Candidate prose / untrusted source cannot force advisory success:
        forged_advisory = self._classify(
            bugbot_state="completed",
            bugbot_conclusion="neutral",
            provider_error={
                "verified": True,
                "class": "quota",
                "source": "grep-heuristic",
            },
        )
        self.assertEqual(forged_advisory.outcome, OUTCOME_UNKNOWN)
        self.assertFalse(forged_advisory.gateSuccess)

        # Structured annotations force review-findings even if conclusion looks clean.
        self.assertTrue(structured_bugbot_findings_present(annotations_count=1))
        self.assertFalse(structured_bugbot_findings_present(annotations_count=0))
        self.assertFalse(structured_bugbot_findings_present(annotations_count=None))
        blocked = self._classify(annotations_count=1, bugbot_conclusion="success")
        self.assertEqual(blocked.outcome, OUTCOME_FINDINGS)
        self.assertFalse(blocked.gateSuccess)
        self.assertFalse(blocked.bugbotPassedClaim)

    def test_durable_founder_alert_dedupe_and_fail_closed(self) -> None:
        advisory = self._classify(
            bugbot_conclusion="neutral",
            provider_error=_verified_quota(),
            provider_evidence_channel=EVIDENCE_CHANNEL_REPAIR_OBSERVER_RECORD,
            infrastructure_attempts=1,
        )
        alert = build_durable_founder_alert(advisory)
        self.assertTrue(alert["required"])
        self.assertIn(founder_alert_marker(HEAD), alert["body"])
        self.assertTrue(
            founder_alert_already_recorded([alert["body"]], head_sha=HEAD)
        )
        self.assertFalse(founder_alert_already_recorded(["other"], head_sha=HEAD))
        # Issue-body dedupe decision path.
        first = decide_founder_alert_publish(
            alert_required=True,
            issue_bodies=[],
            bodies_readable=True,
            head_sha=HEAD,
        )
        self.assertTrue(first["publish"])
        second = decide_founder_alert_publish(
            alert_required=True,
            issue_bodies=[alert["body"]],
            bodies_readable=True,
            head_sha=HEAD,
        )
        self.assertFalse(second["publish"])
        self.assertEqual(second["reason"], "already_recorded")
        with self.assertRaises(ReviewGateError) as unreadable:
            decide_founder_alert_publish(
                alert_required=True,
                issue_bodies=None,
                bodies_readable=False,
                head_sha=HEAD,
            )
        self.assertEqual(unreadable.exception.code, "founder_alert_dedupe_unreadable")
        # Repeated workflow events create exactly one durable alert.
        repeated = simulate_repeated_founder_alert_events(alert_required=True, head_sha=HEAD)
        self.assertEqual(repeated["created"], 1)
        passed = self._classify()
        with self.assertRaises(ReviewGateError):
            build_durable_founder_alert(passed)

    def test_workflow_path_wrong_tree_receipt_negative(self) -> None:
        """Adversarial: receipt tree differs from live TREE and must fail closed."""
        receipt = {
            "name": FULL_SUITE_CONTEXT,
            "headSha": HEAD,
            "gitTree": "d" * 40,
            "status": "success",
        }
        # Simulate the fixed workflow: normalize without injecting live TREE.
        normalized = normalize_full_receipt_payload(receipt)
        assert normalized is not None
        self.assertEqual(normalized["gitTree"], "d" * 40)
        with self.assertRaises(ReviewGateError) as ctx:
            require_full_receipt_for_gate_success(
                gate_success=True,
                full_receipt=normalized,
                head_sha=HEAD,
                git_tree=TREE,
                evidence_channel=EVIDENCE_CHANNEL_GITHUB_CHECK_RUN,
            )
        self.assertEqual(ctx.exception.code, "full_receipt_wrong_tree")
        # Old buggy overwrite path would have masked this — prove inject is absent.
        self.assertNotIn('.gitTree=$t', WORKFLOW.read_text())

    def test_candidate_planted_allowlisted_provider_evidence_never_authorizes_success(self) -> None:
        """P2: every allowlisted source planted via candidate file must not yield advisory success."""
        for source in sorted(TRUSTED_PROVIDER_SOURCES):
            planted = {
                "verified": True,
                "class": "quota",
                "source": source,
                # Candidate may also plant a fake channel claim inside JSON — ignored.
                "evidenceChannel": EVIDENCE_CHANNEL_GITHUB_CHECK_RUN,
            }
            for conclusion, state in (
                ("failure", "failure"),
                ("neutral", "completed"),
            ):
                for channel in (
                    "",
                    EVIDENCE_CHANNEL_CANDIDATE_FILE,
                    # Wrong channel for source (operator source with repair channel, etc.)
                    EVIDENCE_CHANNEL_OPERATOR_PRIVILEGED
                    if source != "operator_verified_provider_error"
                    else EVIDENCE_CHANNEL_REPAIR_OBSERVER_RECORD,
                ):
                    result = self._classify(
                        bugbot_state=state,
                        bugbot_conclusion=conclusion,
                        provider_error=planted,
                        provider_evidence_channel=channel,
                        infrastructure_attempts=1,
                    )
                    self.assertNotEqual(
                        result.outcome,
                        OUTCOME_ADVISORY,
                        msg=f"source={source} conclusion={conclusion} channel={channel!r}",
                    )
                    self.assertFalse(
                        result.gateSuccess,
                        msg=f"source={source} conclusion={conclusion} channel={channel!r}",
                    )
                    self.assertFalse(result.bugbotPassedClaim)

            # Findings still take precedence over planted allowlisted evidence on a trusted channel.
            trusted_channel = {
                "repair_observer.usage_limit": EVIDENCE_CHANNEL_REPAIR_OBSERVER_RECORD,
                "operator_verified_provider_error": EVIDENCE_CHANNEL_OPERATOR_PRIVILEGED,
                "provider_status_api": EVIDENCE_CHANNEL_PROVIDER_STATUS_API,
            }[source]
            findings = self._classify(
                bugbot_state="completed",
                bugbot_conclusion="success",
                annotations_count=1,
                provider_error=planted,
                provider_evidence_channel=trusted_channel,
            )
            self.assertEqual(findings.outcome, OUTCOME_FINDINGS)
            self.assertFalse(findings.gateSuccess)

        # Legitimate trusted-channel advisory still works for repair_observer source.
        ok = self._classify(
            bugbot_state="completed",
            bugbot_conclusion="neutral",
            provider_error=_verified_quota(),
            provider_evidence_channel=EVIDENCE_CHANNEL_REPAIR_OBSERVER_RECORD,
            infrastructure_attempts=1,
        )
        self.assertEqual(ok.outcome, OUTCOME_ADVISORY)
        self.assertTrue(ok.gateSuccess)
        self.assertFalse(ok.bugbotPassedClaim)

    def test_forged_full_receipt_authorship_and_candidate_file_provenance(self) -> None:
        """P2: forged Full receipt without trusted GitHub check provenance cannot authorize success."""
        forged = {
            "name": FULL_SUITE_CONTEXT,
            "headSha": HEAD,
            "gitTree": TREE,
            "status": "success",
        }
        for channel in ("", EVIDENCE_CHANNEL_CANDIDATE_FILE, "operator_privileged_input"):
            with self.assertRaises(ReviewGateError) as ctx:
                require_full_receipt_for_gate_success(
                    gate_success=True,
                    full_receipt=forged,
                    head_sha=HEAD,
                    git_tree=TREE,
                    evidence_channel=channel,
                )
            self.assertIn(ctx.exception.code, {"full_receipt_untrusted_channel", "full_receipt_untrusted_provenance"})

        # Candidate-authored check (non github-actions) must not extract as trusted Full.
        planted_checks = {
            "check_runs": [
                _actions_check(
                    name=FULL_SUITE_CONTEXT,
                    run_id=1,
                    summary=f"head={HEAD}\ngitTree={TREE}\n",
                    app_slug="cursor",
                )
            ]
        }
        self.assertIsNone(
            extract_trusted_full_receipt_from_check_runs(
                planted_checks,
                head_sha=HEAD,
                **_trusted_extract_kwargs(
                    run_id=1, path=FULL_WF_PATH, name=FULL_SUITE_CONTEXT
                ),
            )
        )

        # Trusted suite+job-bound Full check extracts with github_check_run channel.
        trusted_checks = {
            "check_runs": [
                _actions_check(
                    name=FULL_SUITE_CONTEXT,
                    run_id=42,
                    summary=f"head={HEAD}\ngitTree={TREE}\n",
                )
            ]
        }
        extracted = extract_trusted_full_receipt_from_check_runs(
            trusted_checks,
            head_sha=HEAD,
            **_trusted_extract_kwargs(
                run_id=42, path=FULL_WF_PATH, name=FULL_SUITE_CONTEXT
            ),
        )
        assert extracted is not None
        self.assertEqual(extracted["evidenceChannel"], EVIDENCE_CHANNEL_GITHUB_CHECK_RUN)
        require_full_receipt_for_gate_success(
            gate_success=True,
            full_receipt=extracted["receipt"],
            head_sha=HEAD,
            git_tree=TREE,
            evidence_channel=extracted["evidenceChannel"],
        )

        # Planted provider-unavailability check from non-actions app is ignored.
        planted_provider = {
            "check_runs": [
                _actions_check(
                    name="Linktrend Provider Unavailability",
                    run_id=7,
                    summary=json.dumps(
                        {
                            "verified": True,
                            "class": "quota",
                            "source": "repair_observer.usage_limit",
                        }
                    ),
                    app_slug="dependabot",
                )
            ]
        }
        self.assertIsNone(
            extract_trusted_provider_evidence_from_check_runs(
                planted_provider,
                head_sha=HEAD,
                **_trusted_extract_kwargs(
                    run_id=7,
                    path=PROVIDER_WF_PATH,
                    name="Linktrend Provider Unavailability",
                ),
            )
        )

        trusted_provider = {
            "check_runs": [
                _actions_check(
                    name="Linktrend Provider Unavailability",
                    run_id=8,
                    summary=json.dumps(
                        {
                            "verified": True,
                            "class": "quota",
                            "source": "repair_observer.usage_limit",
                        }
                    ),
                )
            ]
        }
        provider = extract_trusted_provider_evidence_from_check_runs(
            trusted_provider,
            head_sha=HEAD,
            **_trusted_extract_kwargs(
                run_id=8,
                path=PROVIDER_WF_PATH,
                name="Linktrend Provider Unavailability",
            ),
        )
        assert provider is not None
        self.assertEqual(provider["evidenceChannel"], EVIDENCE_CHANNEL_GITHUB_CHECK_RUN)
        classified = self._classify(
            bugbot_state="completed",
            bugbot_conclusion="neutral",
            provider_error=provider["providerError"],
            provider_evidence_channel=provider["evidenceChannel"],
            infrastructure_attempts=1,
        )
        self.assertEqual(classified.outcome, OUTCOME_ADVISORY)

    def test_details_url_hijack_and_producer_membership_binding(self) -> None:
        """P1: borrowed details_url + forged summary cannot authorize Full/provider success."""
        full_summary = f"head={HEAD}\ngitTree={TREE}\n"
        forged_summary = f"head={HEAD}\ngitTree={TREE}\nforged=1\n"
        provider_summary = json.dumps(
            {
                "verified": True,
                "class": "quota",
                "source": "repair_observer.usage_limit",
            }
        )
        forged_provider = json.dumps(
            {
                "verified": True,
                "class": "quota",
                "source": "repair_observer.usage_limit",
                "forged": True,
            }
        )

        # Genuine successful producer run/job/suite (membership target).
        genuine_run = 201
        genuine_check = 2010
        genuine_suite = 20100
        genuine_jobs = _jobs_for(
            run_id=genuine_run, check_id=genuine_check, name=FULL_SUITE_CONTEXT
        )
        genuine_runs = {
            "workflow_runs": [
                _workflow_run(
                    run_id=genuine_run,
                    path=FULL_WF_PATH,
                    head_branch=DEFAULT_BRANCH,
                    suite_id=genuine_suite,
                )
            ]
        }

        # Attacker check borrows genuine details_url but has a different suite/check id.
        hijack = {
            "check_runs": [
                _actions_check(
                    name=FULL_SUITE_CONTEXT,
                    run_id=999,
                    check_id=9990,
                    suite_id=99900,
                    details_run_id=genuine_run,
                    summary=forged_summary,
                )
            ]
        }
        self.assertIsNone(
            extract_trusted_full_receipt_from_check_runs(
                hijack,
                head_sha=HEAD,
                default_branch=DEFAULT_BRANCH,
                workflow_runs=genuine_runs,
                workflow_jobs=genuine_jobs,
                workflow_file_shas=_wf_shas(FULL_WF_PATH, head=None),
            )
        )

        # Failed genuine producer cannot authorize even with matching suite membership.
        failed_runs = {
            "workflow_runs": [
                _workflow_run(
                    run_id=genuine_run,
                    path=FULL_WF_PATH,
                    head_branch=DEFAULT_BRANCH,
                    suite_id=genuine_suite,
                    conclusion="failure",
                )
            ]
        }
        self.assertIsNone(
            extract_trusted_full_receipt_from_check_runs(
                {
                    "check_runs": [
                        _actions_check(
                            name=FULL_SUITE_CONTEXT,
                            run_id=genuine_run,
                            check_id=genuine_check,
                            suite_id=genuine_suite,
                            summary=full_summary,
                        )
                    ]
                },
                head_sha=HEAD,
                default_branch=DEFAULT_BRANCH,
                workflow_runs=failed_runs,
                workflow_jobs=genuine_jobs,
                workflow_file_shas=_wf_shas(FULL_WF_PATH, head=None),
            )
        )

        # Missing check_suite / check id → fail closed.
        self.assertIsNone(
            extract_trusted_full_receipt_from_check_runs(
                {
                    "check_runs": [
                        {
                            "name": FULL_SUITE_CONTEXT,
                            "head_sha": HEAD,
                            "conclusion": "success",
                            "app": {"slug": "github-actions"},
                            "details_url": f"https://github.com/{REPO}/actions/runs/{genuine_run}",
                            "output": {"summary": full_summary},
                        }
                    ]
                },
                head_sha=HEAD,
                default_branch=DEFAULT_BRANCH,
                workflow_runs=genuine_runs,
                workflow_jobs=genuine_jobs,
                workflow_file_shas=_wf_shas(FULL_WF_PATH, head=None),
            )
        )

        # Valid producer: suite + successful job membership + successful run.
        ok = extract_trusted_full_receipt_from_check_runs(
            {
                "check_runs": [
                    _actions_check(
                        name=FULL_SUITE_CONTEXT,
                        run_id=genuine_run,
                        check_id=genuine_check,
                        suite_id=genuine_suite,
                        summary=full_summary,
                    )
                ]
            },
            head_sha=HEAD,
            default_branch=DEFAULT_BRANCH,
            workflow_runs=genuine_runs,
            workflow_jobs=genuine_jobs,
            workflow_file_shas=_wf_shas(FULL_WF_PATH, head=None),
        )
        assert ok is not None
        self.assertEqual(ok["workflowRunId"], genuine_run)
        self.assertEqual(ok["checkRunId"], genuine_check)

        # Provider hijack: borrow genuine repair-observer URL with forged summary.
        p_run, p_check, p_suite = 301, 3010, 30100
        p_jobs = _jobs_for(
            run_id=p_run,
            check_id=p_check,
            name="Linktrend Provider Unavailability",
        )
        p_runs = {
            "workflow_runs": [
                _workflow_run(
                    run_id=p_run,
                    path=PROVIDER_WF_PATH,
                    head_branch=DEFAULT_BRANCH,
                    suite_id=p_suite,
                )
            ]
        }
        self.assertIsNone(
            extract_trusted_provider_evidence_from_check_runs(
                {
                    "check_runs": [
                        _actions_check(
                            name="Linktrend Provider Unavailability",
                            run_id=888,
                            check_id=8880,
                            suite_id=88800,
                            details_run_id=p_run,
                            summary=forged_provider,
                        )
                    ]
                },
                head_sha=HEAD,
                default_branch=DEFAULT_BRANCH,
                workflow_runs=p_runs,
                workflow_jobs=p_jobs,
                workflow_file_shas=_wf_shas(PROVIDER_WF_PATH, head=None),
            )
        )
        ok_provider = extract_trusted_provider_evidence_from_check_runs(
            {
                "check_runs": [
                    _actions_check(
                        name="Linktrend Provider Unavailability",
                        run_id=p_run,
                        check_id=p_check,
                        suite_id=p_suite,
                        summary=provider_summary,
                    )
                ]
            },
            head_sha=HEAD,
            default_branch=DEFAULT_BRANCH,
            workflow_runs=p_runs,
            workflow_jobs=p_jobs,
            workflow_file_shas=_wf_shas(PROVIDER_WF_PATH, head=None),
        )
        assert ok_provider is not None
        self.assertEqual(ok_provider["checkSuiteId"], p_suite)

    def test_same_app_check_name_collision_requires_default_branch_workflow_identity(
        self,
    ) -> None:
        """P1: github-actions + matching check name is not enough without workflow binding."""
        full_summary = f"head={HEAD}\ngitTree={TREE}\n"
        provider_summary = json.dumps(
            {
                "verified": True,
                "class": "quota",
                "source": "repair_observer.usage_limit",
            }
        )

        # Colliding candidate workflow path under the same Actions app.
        self.assertIsNone(
            extract_trusted_full_receipt_from_check_runs(
                {
                    "check_runs": [
                        _actions_check(
                            name=FULL_SUITE_CONTEXT, run_id=101, summary=full_summary
                        )
                    ]
                },
                head_sha=HEAD,
                **_trusted_extract_kwargs(
                    run_id=101,
                    path=COLLISION_WF_PATH,
                    name=FULL_SUITE_CONTEXT,
                    shas={
                        **_wf_shas(FULL_WF_PATH),
                        **_wf_shas(COLLISION_WF_PATH),
                    },
                ),
            )
        )

        # Allowlisted path but rewritten producer blob on the candidate tip.
        self.assertIsNone(
            extract_trusted_full_receipt_from_check_runs(
                {
                    "check_runs": [
                        _actions_check(
                            name=FULL_SUITE_CONTEXT, run_id=102, summary=full_summary
                        )
                    ]
                },
                head_sha=HEAD,
                **_trusted_extract_kwargs(
                    run_id=102,
                    path=FULL_WF_PATH,
                    name=FULL_SUITE_CONTEXT,
                    head_branch="issue/329-candidate",
                    shas=_wf_shas(FULL_WF_PATH, head=REWRITTEN_WF_BLOB),
                ),
            )
        )

        # Missing suite/job membership → fail closed.
        self.assertIsNone(
            extract_trusted_full_receipt_from_check_runs(
                {
                    "check_runs": [
                        {
                            "name": FULL_SUITE_CONTEXT,
                            "head_sha": HEAD,
                            "conclusion": "success",
                            "app": {"slug": "github-actions"},
                            "details_url": f"https://github.com/{REPO}/actions/runs/103",
                            "output": {"summary": full_summary},
                        }
                    ]
                },
                head_sha=HEAD,
                default_branch=DEFAULT_BRANCH,
                workflow_runs={
                    "workflow_runs": [
                        _workflow_run(
                            run_id=103, path=FULL_WF_PATH, head_branch=DEFAULT_BRANCH
                        )
                    ]
                },
                workflow_jobs={"jobs": []},
                workflow_file_shas=_wf_shas(FULL_WF_PATH, head=None),
            )
        )

        # Missing default branch / empty default blob → fail closed.
        self.assertIsNone(
            extract_trusted_full_receipt_from_check_runs(
                {
                    "check_runs": [
                        _actions_check(
                            name=FULL_SUITE_CONTEXT, run_id=104, summary=full_summary
                        )
                    ]
                },
                head_sha=HEAD,
                default_branch="",
                workflow_runs={
                    "workflow_runs": [
                        _workflow_run(
                            run_id=104, path=FULL_WF_PATH, head_branch=DEFAULT_BRANCH
                        )
                    ]
                },
                workflow_jobs=_jobs_for(
                    run_id=104, check_id=1040, name=FULL_SUITE_CONTEXT
                ),
                workflow_file_shas=_wf_shas(FULL_WF_PATH),
            )
        )
        self.assertIsNone(
            extract_trusted_full_receipt_from_check_runs(
                {
                    "check_runs": [
                        _actions_check(
                            name=FULL_SUITE_CONTEXT, run_id=105, summary=full_summary
                        )
                    ]
                },
                head_sha=HEAD,
                **_trusted_extract_kwargs(
                    run_id=105,
                    path=FULL_WF_PATH,
                    name=FULL_SUITE_CONTEXT,
                    shas=_wf_shas(FULL_WF_PATH, default="", head=None),
                ),
            )
        )

        # Valid: default-branch producer.
        ok_default = extract_trusted_full_receipt_from_check_runs(
            {
                "check_runs": [
                    _actions_check(
                        name=FULL_SUITE_CONTEXT, run_id=201, summary=full_summary
                    )
                ]
            },
            head_sha=HEAD,
            **_trusted_extract_kwargs(
                run_id=201, path=FULL_WF_PATH, name=FULL_SUITE_CONTEXT
            ),
        )
        assert ok_default is not None
        self.assertEqual(ok_default["workflowPath"], FULL_WF_PATH)

        # Valid: PR tip with byte-identical allowlisted workflow blob vs default.
        ok_same_blob = extract_trusted_full_receipt_from_check_runs(
            {
                "check_runs": [
                    _actions_check(
                        name=FULL_SUITE_CONTEXT, run_id=202, summary=full_summary
                    )
                ]
            },
            head_sha=HEAD,
            **_trusted_extract_kwargs(
                run_id=202,
                path=FULL_WF_PATH,
                name=FULL_SUITE_CONTEXT,
                head_branch="issue/329-candidate",
                shas=_wf_shas(FULL_WF_PATH, by_head={HEAD: DEFAULT_WF_BLOB}),
            ),
        )
        assert ok_same_blob is not None
        self.assertEqual(ok_same_blob["workflowRunId"], 202)

        # Provider: same-app name collision via non-allowlisted path.
        self.assertIsNone(
            extract_trusted_provider_evidence_from_check_runs(
                {
                    "check_runs": [
                        _actions_check(
                            name="Linktrend Provider Unavailability",
                            run_id=301,
                            summary=provider_summary,
                        )
                    ]
                },
                head_sha=HEAD,
                **_trusted_extract_kwargs(
                    run_id=301,
                    path=COLLISION_WF_PATH,
                    name="Linktrend Provider Unavailability",
                    shas={
                        **_wf_shas(PROVIDER_WF_PATH),
                        **_wf_shas(COLLISION_WF_PATH),
                    },
                ),
            )
        )
        # Provider: rewritten repair-observer workflow on candidate tip.
        self.assertIsNone(
            extract_trusted_provider_evidence_from_check_runs(
                {
                    "check_runs": [
                        _actions_check(
                            name="Linktrend Provider Unavailability",
                            run_id=302,
                            summary=provider_summary,
                        )
                    ]
                },
                head_sha=HEAD,
                **_trusted_extract_kwargs(
                    run_id=302,
                    path=PROVIDER_WF_PATH,
                    name="Linktrend Provider Unavailability",
                    head_branch="issue/329-candidate",
                    shas=_wf_shas(PROVIDER_WF_PATH, head=REWRITTEN_WF_BLOB),
                ),
            )
        )
        # Provider valid: default-branch producer.
        ok_provider = extract_trusted_provider_evidence_from_check_runs(
            {
                "check_runs": [
                    _actions_check(
                        name="Linktrend Provider Unavailability",
                        run_id=303,
                        summary=provider_summary,
                    )
                ]
            },
            head_sha=HEAD,
            **_trusted_extract_kwargs(
                run_id=303,
                path=PROVIDER_WF_PATH,
                name="Linktrend Provider Unavailability",
            ),
        )
        assert ok_provider is not None
        self.assertEqual(ok_provider["workflowPath"], PROVIDER_WF_PATH)
        # Provider valid: identical blob on candidate tip.
        ok_provider_blob = extract_trusted_provider_evidence_from_check_runs(
            {
                "check_runs": [
                    _actions_check(
                        name="Linktrend Provider Unavailability",
                        run_id=304,
                        summary=provider_summary,
                    )
                ]
            },
            head_sha=HEAD,
            **_trusted_extract_kwargs(
                run_id=304,
                path=PROVIDER_WF_PATH,
                name="Linktrend Provider Unavailability",
                head_branch="issue/329-candidate",
                shas=_wf_shas(PROVIDER_WF_PATH, by_head={HEAD: DEFAULT_WF_BLOB}),
            ),
        )
        assert ok_provider_blob is not None
        self.assertEqual(ok_provider_blob["workflowRunId"], 304)

        # resolve-workflow-file-shas helper indexes Contents SHAs by path + run head.
        calls: list[tuple[str, str]] = []

        def fake_lookup(path: str, ref: str) -> str:
            calls.append((path, ref))
            if ref == DEFAULT_BRANCH:
                return DEFAULT_WF_BLOB
            if ref == HEAD:
                return DEFAULT_WF_BLOB
            return REWRITTEN_WF_BLOB

        built = build_workflow_file_shas_payload(
            repository=REPO,
            default_branch=DEFAULT_BRANCH,
            workflow_runs={
                "workflow_runs": [
                    _workflow_run(run_id=1, path=FULL_WF_PATH),
                    _workflow_run(run_id=2, path=PROVIDER_WF_PATH),
                ]
            },
            contents_sha_lookup=fake_lookup,
        )
        self.assertEqual(built[FULL_WF_PATH]["default"], DEFAULT_WF_BLOB)
        self.assertEqual(built[FULL_WF_PATH]["byHead"][HEAD], DEFAULT_WF_BLOB)
        self.assertEqual(built[PROVIDER_WF_PATH]["byHead"][HEAD], DEFAULT_WF_BLOB)
        self.assertIn((FULL_WF_PATH, DEFAULT_BRANCH), calls)

    def test_provider_extractor_requires_exact_item_and_run_head(self) -> None:
        """P2: provider extraction requires exact check head and workflow_run head."""
        summary = json.dumps(
            {
                "verified": True,
                "class": "quota",
                "source": "repair_observer.usage_limit",
            }
        )
        kwargs = _trusted_extract_kwargs(
            run_id=401,
            path=PROVIDER_WF_PATH,
            name="Linktrend Provider Unavailability",
        )
        # Missing check head_sha → reject.
        missing_item_head = {
            "check_runs": [
                {
                    "id": 4010,
                    "name": "Linktrend Provider Unavailability",
                    "conclusion": "success",
                    "app": {"slug": "github-actions"},
                    "check_suite": {"id": 40100},
                    "details_url": f"https://github.com/{REPO}/actions/runs/401",
                    "output": {"summary": summary},
                }
            ]
        }
        self.assertIsNone(
            extract_trusted_provider_evidence_from_check_runs(
                missing_item_head, head_sha=HEAD, **kwargs
            )
        )
        # Wrong workflow_run.head_sha → reject.
        wrong_run = dict(kwargs)
        wrong_run["workflow_runs"] = {
            "workflow_runs": [
                _workflow_run(
                    run_id=401,
                    path=PROVIDER_WF_PATH,
                    head_branch=DEFAULT_BRANCH,
                    head_sha="e" * 40,
                )
            ]
        }
        self.assertIsNone(
            extract_trusted_provider_evidence_from_check_runs(
                {
                    "check_runs": [
                        _actions_check(
                            name="Linktrend Provider Unavailability",
                            run_id=401,
                            summary=summary,
                        )
                    ]
                },
                head_sha=HEAD,
                **wrong_run,
            )
        )
        # Exact heads succeed.
        ok = extract_trusted_provider_evidence_from_check_runs(
            {
                "check_runs": [
                    _actions_check(
                        name="Linktrend Provider Unavailability",
                        run_id=401,
                        summary=summary,
                    )
                ]
            },
            head_sha=HEAD,
            **kwargs,
        )
        assert ok is not None

    def test_paginated_slurp_flatten_multi_page_bodies_and_dedupe(self) -> None:
        """Two+ pages must flatten to one JSON list; alert/marker counts stay exact."""
        marker = founder_alert_marker(HEAD)
        infra1 = infrastructure_attempt_marker(HEAD, 1)
        infra2 = infrastructure_attempt_marker(HEAD, 2)
        # Empty / single / multi-page deterministic flatten.
        self.assertEqual(flatten_gh_slurp_pages([]), [])
        self.assertEqual(
            comment_bodies_from_slurp([[{"body": infra1}]]),
            [infra1],
        )
        two_pages = [
            [{"body": infra1}, {"body": "noise"}],
            [{"body": infra2}, {"body": marker + "\nalert body"}],
        ]
        bodies = comment_bodies_from_slurp(two_pages)
        self.assertEqual(len(bodies), 4)
        self.assertEqual(count_infrastructure_attempts(bodies, head_sha=HEAD), 2)
        # Issue pages skip pull_request entries and flatten across pages.
        issue_pages = [
            [
                {"body": "pr body", "pull_request": {"url": "https://example/pr/1"}},
                {"body": "other issue"},
            ],
            [{"body": f"{marker}\nfounder alert page 2"}],
        ]
        issue_bodies = issue_bodies_from_slurp(issue_pages)
        self.assertEqual(issue_bodies, ["other issue", f"{marker}\nfounder alert page 2"])
        decision = decide_founder_alert_publish(
            alert_required=True,
            issue_bodies=issue_bodies,
            bodies_readable=True,
            head_sha=HEAD,
        )
        self.assertFalse(decision["publish"])
        self.assertEqual(decision["reason"], "already_recorded")
        # Malformed slurp / fail-open equivalent must fail closed (not become []).
        with self.assertRaises(ReviewGateError) as bad:
            flatten_gh_slurp_pages("not-json")
        self.assertEqual(bad.exception.code, "paginated_response_invalid")
        with self.assertRaises(ReviewGateError):
            flatten_gh_slurp_pages([{"not": "a page list"}])
        # Simulate two workflow events after multi-page prior bodies → one alert.
        repeated = simulate_repeated_founder_alert_events(
            alert_required=True,
            head_sha=HEAD,
            prior_issue_bodies=["unrelated"],
        )
        self.assertEqual(repeated["created"], 1)

    def test_slurp_json_stdin_handles_arg_max_and_pipefail_hold(self) -> None:
        """Workflow path: stdin --slurp-json - survives ARG_MAX; upstream fail stays HOLD."""
        marker = founder_alert_marker(HEAD)
        infra1 = infrastructure_attempt_marker(HEAD, 1)
        # Empty / one / multi-page via stdin CLI.
        for pages, expected_len in (
            ([], 0),
            ([[{"body": infra1}]], 1),
            ([[{"body": infra1}], [{"body": infrastructure_attempt_marker(HEAD, 2)}]], 2),
        ):
            proc = subprocess.run(
                [sys.executable, str(MODULE), "flatten-comment-bodies", "--slurp-json", "-"],
                input=json.dumps(pages),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            bodies = json.loads(proc.stdout)
            self.assertEqual(len(bodies), expected_len)
            if expected_len:
                self.assertEqual(
                    count_infrastructure_attempts(bodies, head_sha=HEAD),
                    expected_len,
                )

        # Payload larger than ARG_MAX must succeed via stdin and fail via argv.
        try:
            arg_max = int(os.sysconf("SC_ARG_MAX"))
        except (AttributeError, ValueError, OSError):
            arg_max = 131072
        # Keep well above ARG_MAX while staying tractable for unit runtime.
        target = max(arg_max + 4096, 300_000)
        chunk = "x" * 4000
        page: list[dict[str, str]] = []
        size = 2  # rough JSON overhead
        while size < target:
            page.append({"body": chunk})
            size += len(chunk) + 20
        pages = [page, [{"body": marker + "\npage2"}]]
        payload = json.dumps(pages)
        self.assertGreater(len(payload), arg_max)

        stdin_proc = subprocess.run(
            [sys.executable, str(MODULE), "flatten-issue-bodies", "--slurp-json", "-"],
            input=payload,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(stdin_proc.returncode, 0, stdin_proc.stderr)
        issue_bodies = json.loads(stdin_proc.stdout)
        self.assertTrue(any(marker in body for body in issue_bodies))
        decision = decide_founder_alert_publish(
            alert_required=True,
            issue_bodies=issue_bodies,
            bodies_readable=True,
            head_sha=HEAD,
        )
        self.assertFalse(decision["publish"])

        argv_failed = False
        try:
            argv_proc = subprocess.run(
                [sys.executable, str(MODULE), "flatten-issue-bodies", "--slurp-json", payload],
                text=True,
                capture_output=True,
                check=False,
            )
            argv_failed = argv_proc.returncode != 0
        except OSError:
            argv_failed = True
        self.assertTrue(argv_failed)

        # Upstream read failure must not be masked when pipefail is set.
        hold_script = r"""
set -euo pipefail
if ! (
  false \
    | python3 scripts/gitops/linktrend_review_gate.py flatten-comment-bodies --slurp-json -
); then
  echo "HOLD: infra_marker_read_failed"
  exit 1
fi
"""
        hold = subprocess.run(
            ["bash", "-lc", hold_script],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(hold.returncode, 1)
        self.assertIn("HOLD: infra_marker_read_failed", hold.stdout + hold.stderr)

    def test_undocumented_task_hold_rejected(self) -> None:
        reject_undocumented_task_hold(configured_gates_passed=True, task_hold=None)
        with self.assertRaises(ReviewGateError) as ctx:
            reject_undocumented_task_hold(configured_gates_passed=True, task_hold="extra review")
        self.assertEqual(ctx.exception.code, "undocumented_task_hold")

    def test_fallback_reviewer_rules_and_comment(self) -> None:
        ok = evaluate_fallback_review(
            outcome=OUTCOME_ADVISORY,
            independent_review_configured=True,
            reviewer_actor="reviewer-bot",
            implementer_actor="implementer-bot",
            evidence_head=HEAD,
            live_head=HEAD,
        )
        self.assertTrue(ok["requested"])
        comment = build_fallback_request_comment(fallback=ok, head_sha=HEAD)
        self.assertTrue(comment["posted"])
        self.assertIn("advisory-unavailable", comment["body"])
        with self.assertRaises(ReviewGateError) as ctx:
            evaluate_fallback_review(
                outcome=OUTCOME_ADVISORY,
                independent_review_configured=True,
                reviewer_actor="same",
                implementer_actor="same",
                evidence_head=HEAD,
                live_head=HEAD,
            )
        self.assertEqual(ctx.exception.code, "fallback_implementer_rejected")
        with self.assertRaises(ReviewGateError):
            evaluate_fallback_review(
                outcome=OUTCOME_ADVISORY,
                independent_review_configured=True,
                reviewer_actor="reviewer-bot",
                implementer_actor="implementer-bot",
                evidence_head=HEAD,
                live_head="e" * 40,
            )

    def test_same_account_comment_not_github_approval(self) -> None:
        with self.assertRaises(ReviewGateError) as ctx:
            evaluate_github_approval(
                approving_review_required=True,
                reviewer_login="",
                comment_author_login="carlos",
                technical_review_clean=True,
                evidence_head=HEAD,
                live_head=HEAD,
                approval_source="comment",
            )
        self.assertEqual(ctx.exception.code, "same_account_approval_rejected")
        technical = evaluate_github_approval(
            approving_review_required=False,
            reviewer_login="reviewer",
            comment_author_login="reviewer",
            technical_review_clean=True,
            evidence_head=HEAD,
            live_head=HEAD,
        )
        self.assertEqual(technical["mode"], "technical_review_only")
        self.assertFalse(technical["rerunFastFull"])

    def test_observer_rejects_raw_bugbot_as_managed_gate(self) -> None:
        script = r"""
import os, sys
sys.path.insert(0, "scripts/gitops")
os.chdir(%r)
import repair_observer
cfg = repair_observer.load_config({
    "LINKTREND_BUGBOT_PROVIDER_CHECK_NAME": "Cursor Bugbot",
    "LINKTREND_REVIEW_GATE_CHECK_NAME": "Linktrend Review Gate",
})
assert cfg.bugbot_check_name == "Cursor Bugbot"
assert cfg.review_gate_check_name == "Linktrend Review Gate"
try:
    repair_observer.load_config({"LINKTREND_REVIEW_GATE_CHECK_NAME": "Cursor Bugbot"})
except RuntimeError as exc:
    assert "raw_bugbot_required" in str(exc)
else:
    raise SystemExit("expected raw_bugbot_required")
print("ok")
""" % str(ROOT)
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("ok", completed.stdout)

    def test_workflow_static_no_trailing_whitespace(self) -> None:
        # Observer template is present on development but not migrated in this
        # bootstrap; still enforce no trailing whitespace on gate surfaces.
        for path in (WORKFLOW, MANAGED_WORKFLOW, MODULE):
            for index, line in enumerate(path.read_text().splitlines(), 1):
                self.assertFalse(
                    line.endswith(" ") or line.endswith("\t"),
                    f"{path}:{index} has trailing whitespace",
                )

    def test_detect_findings_from_trustworthy_event_evidence(self) -> None:
            empty = findings_present_from_event_evidence(
                annotations_count=0,
                check_title="",
                check_details="",
                bugbot_conclusion="neutral",
            )
            self.assertFalse(empty["findingsPresent"])
            self.assertEqual(empty["reasons"], [])

            by_annotations = findings_present_from_event_evidence(annotations_count=3)
            self.assertTrue(by_annotations["findingsPresent"])
            self.assertIn("annotations_count:3", by_annotations["reasons"])

            by_details = findings_present_from_event_evidence(
                check_details="Found 2 potential issues in this review."
            )
            self.assertTrue(by_details["findingsPresent"])

            by_title = findings_present_from_event_evidence(
                check_title="Bugbot reported 1 finding"
            )
            self.assertTrue(by_title["findingsPresent"])

            verified = findings_present_from_event_evidence(
                provider_findings={
                    "verified": True,
                    "source": "cursor_bugbot.check_run",
                    "findingsPresent": True,
                }
            )
            self.assertTrue(verified["findingsPresent"])

            # Untrusted / unverified provider payloads cannot force findings.
            forged = findings_present_from_event_evidence(
                provider_findings={
                    "verified": True,
                    "source": "candidate_self_approve",
                    "findingsPresent": True,
                }
            )
            self.assertFalse(forged["findingsPresent"])
            unverified = findings_present_from_event_evidence(
                provider_findings={
                    "verified": False,
                    "source": "cursor_bugbot.check_run",
                    "findingsCount": 9,
                }
            )
            self.assertFalse(unverified["findingsPresent"])

            # Wire into classifier: event findings → review-findings (not pass).
            classified = self._classify(
                bugbot_conclusion="success",
                findings_present=by_annotations["findingsPresent"],
            )
            self.assertEqual(classified.outcome, OUTCOME_FINDINGS)
            self.assertFalse(classified.gateSuccess)
            self.assertFalse(classified.bugbotPassedClaim)

            # CLI path used by the workflow.
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE),
                    "detect-findings",
                    "--annotations-count",
                    "2",
                    "--check-details",
                    "Found 2 issues",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertTrue(payload["findingsPresent"])
    def test_candidate_cannot_replace_classifier_or_self_approve(self) -> None:
            """Negative: candidate tree cannot replace trusted classifier / self-approve."""
            live = WORKFLOW.read_text(encoding="utf-8")
            managed = MANAGED_WORKFLOW.read_text(encoding="utf-8")
            self.assertEqual(live, managed)
            # Privileged write job must not check out candidate head for execution.
            self.assertNotRegex(
                live,
                r"ref:\s*\$\{\{\s*github\.event\.check_run\.head_sha\s*\}\}",
            )
            self.assertIn("github.event.repository.default_branch", live)
            self.assertIn('GATE_PY="${TRUSTED_ROOT}/scripts/gitops/linktrend_review_gate.py"', live)
            self.assertIn("untrusted data path collapsed into trusted root", live)
            self.assertIn("ignoring_candidate_provider_error_file", live)
            self.assertIn("ignoring_candidate_full_suite_receipt_file", live)
            self.assertIn("authenticate-provider-error", live)
            self.assertIn("overlay-retained-full-receipt", live)
            self.assertIn("--provenance-kind github.actions.artifact", live)
            # Never cat candidate success-evidence files.
            self.assertNotRegex(
                live,
                r'cat\s+"\$\{CANDIDATE_DIR\}/\.linktrend/review-gate-provider-error\.json"',
            )
            self.assertNotRegex(
                live,
                r'cat\s+"\$\{CANDIDATE_DIR\}/\.linktrend/full-suite-receipt\.json"',
            )

            with tempfile.TemporaryDirectory() as tmp:
                candidate = Path(tmp)
                malicious = candidate / "scripts" / "gitops"
                malicious.mkdir(parents=True)
                (malicious / "linktrend_review_gate.py").write_text(
                    "#!/usr/bin/env python3\n"
                    "import json\n"
                    "print(json.dumps({\n"
                    '  "classification": {\n'
                    '    "outcome": "review-passed",\n'
                    '    "gateSuccess": True,\n'
                    '    "bugbotPassedClaim": True,\n'
                    '    "alertFounder": False,\n'
                    '    "detail": "pwned",\n'
                    f'    "headSha": "{HEAD}",\n'
                    f'    "gitTree": "{TREE}",\n'
                    f'    "repository": "{REPO}",\n'
                    '    "pullRequest": 1,\n'
                    '    "infrastructureAttempts": 0,\n'
                    '    "providerClass": None,\n'
                    '    "sanitizedAlert": None,\n'
                    '    "schemaVersion": 1,\n'
                    '    "kind": "linktrend-review-gate"\n'
                    "  },\n"
                    '  "commitStatus": {\n'
                    '    "state": "success",\n'
                    '    "context": "Linktrend Review Gate",\n'
                    '    "description": "forged"\n'
                    "  }\n"
                    "}))\n",
                    encoding="utf-8",
                )
                (candidate / ".linktrend").mkdir()
                (candidate / ".linktrend" / "review-gate-provider-error.json").write_text(
                    json.dumps(
                        {
                            "verified": True,
                            "class": "quota",
                            "source": "candidate_forged_self_approve",
                        }
                    ),
                    encoding="utf-8",
                )
                # Trusted classifier still rejects forged unavailability source.
                self.assertIsNone(
                    verified_provider_unavailability(
                        json.loads(
                            (candidate / ".linktrend" / "review-gate-provider-error.json").read_text()
                        )
                    )
                )
                # Even if candidate ships a self-approving classifier, workflow binds GATE_PY
                # to the trusted workspace path — prove trusted module still fails closed.
                forged_run = subprocess.run(
                    [
                        sys.executable,
                        str(MODULE),
                        "classify",
                        "--repository",
                        REPO,
                        "--head-sha",
                        HEAD,
                        "--git-tree",
                        TREE,
                        "--bugbot-state",
                        "completed",
                        "--bugbot-conclusion",
                        "success",
                        "--findings-present",
                        "--infrastructure-attempts",
                        "0",
                        "--result-head-sha",
                        HEAD,
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(forged_run.returncode, 0, forged_run.stderr)
                trusted_out = json.loads(forged_run.stdout)
                self.assertEqual(
                    trusted_out["classification"]["outcome"], OUTCOME_FINDINGS
                )
                self.assertFalse(trusted_out["classification"]["gateSuccess"])
                self.assertFalse(trusted_out["classification"]["bugbotPassedClaim"])
                # Candidate malicious script would claim pass — ensure it differs.
                malicious_out = subprocess.run(
                    [sys.executable, str(malicious / "linktrend_review_gate.py")],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(malicious_out.returncode, 0)
                self.assertEqual(
                    json.loads(malicious_out.stdout)["classification"]["outcome"],
                    OUTCOME_PASSED,
                )
                self.assertNotEqual(
                    json.loads(malicious_out.stdout)["classification"]["outcome"],
                    trusted_out["classification"]["outcome"],
                )

            # Missing findings evidence must not become a pass via neutral alone.
            unknown = self._classify(bugbot_conclusion="neutral")
            self.assertEqual(unknown.outcome, OUTCOME_UNKNOWN)
            self.assertFalse(unknown.gateSuccess)
    def test_planted_allowlisted_provider_error_and_forged_receipt_rejected(self) -> None:
            """Adversarial: each allowlisted planted source + forged Full receipt fail closed."""
            self.assertEqual(
                set(TRUSTED_PROVIDER_SOURCES),
                {
                    "repair_observer.usage_limit",
                    "operator_verified_provider_error",
                    "provider_status_api",
                },
            )
            self.assertIn("github.check_runs.api", TRUSTED_FULL_RECEIPT_PROVENANCE_KINDS)
            self.assertIn("github.repair_task.api", TRUSTED_PROVIDER_PROVENANCE_KINDS)

            for source in sorted(TRUSTED_PROVIDER_SOURCES):
                planted = {
                    "verified": True,
                    "class": "quota",
                    "source": source,
                    "headSha": HEAD,
                    # Candidate file may even claim a trusted-looking provenance kind name,
                    # but without authenticate-* stamping authenticated must remain false/absent.
                }
                self.assertIsNone(
                    verified_provider_unavailability(planted),
                    msg=f"planted source {source} must not verify without provenance",
                )
                planted_claimed = {
                    **planted,
                    "provenance": {
                        "kind": "github.repository_variable",
                        "headSha": HEAD,
                        "authenticated": False,
                    },
                }
                self.assertIsNone(verified_provider_unavailability(planted_claimed))

                for conclusion, state, expected in (
                    ("failure", "failure", OUTCOME_FAILED),
                    ("neutral", "completed", OUTCOME_UNKNOWN),
                ):
                    result = self._classify(
                        bugbot_state=state,
                        bugbot_conclusion=conclusion,
                        provider_error=planted,
                        infrastructure_attempts=1,
                    )
                    # Planted allowlisted sources without provenance are ignored: real
                    # Bugbot conclusions stay truthful and never become gateSuccess.
                    self.assertEqual(result.outcome, expected, msg=f"{source}/{conclusion}")
                    self.assertFalse(result.gateSuccess, msg=f"{source}/{conclusion}")
                    self.assertFalse(result.bugbotPassedClaim)

                # Findings precedence: planted allowlisted source must not override findings.
                findings_first = self._classify(
                    bugbot_conclusion="neutral",
                    findings_present=True,
                    provider_error=planted,
                    infrastructure_attempts=1,
                )
                self.assertEqual(findings_first.outcome, OUTCOME_FINDINGS)
                self.assertFalse(findings_first.gateSuccess)

                # Authenticate helper must reject candidate-controlled provenance kinds.
                with self.assertRaises(ReviewGateError) as cand:
                    authenticate_provider_unavailability_evidence(
                        {
                            **planted,
                            "provenance": {
                                "kind": "candidate.worktree_file",
                                "authenticated": True,
                            },
                        },
                        provenance_kind="github.repository_variable",
                        head_sha=HEAD,
                    )
                self.assertEqual(cand.exception.code, "provider_error_candidate_controlled")

            # Legitimate trusted routes still authorize advisory for neutral.
            for source in sorted(TRUSTED_PROVIDER_SOURCES):
                trusted = _verified_quota(source=source)
                self.assertEqual(verified_provider_unavailability(trusted), "quota")
                advisory = self._classify(
                    bugbot_conclusion="neutral",
                    provider_error=trusted,
                    infrastructure_attempts=1,
                )
                self.assertEqual(advisory.outcome, OUTCOME_ADVISORY)
                self.assertTrue(advisory.gateSuccess)
                self.assertFalse(advisory.bugbotPassedClaim)

            # Repair-issue trusted route for usage_limit.
            issue = {
                "number": 42,
                "body": (
                    "## LiNKtrend repair task\n"
                    "- failureType: `usage_limit`\n"
                    f"- headSha: `{HEAD}`\n"
                    "- resolutionState: **open**\n"
                ),
                "labels": [{"name": "linktrend-repair-usage-limit"}],
            }
            resolved = provider_error_from_usage_limit_repair_issues([issue], head_sha=HEAD)
            assert resolved is not None
            self.assertEqual(resolved["source"], "repair_observer.usage_limit")
            self.assertTrue(resolved["provenance"]["authenticated"])
            self.assertEqual(resolved["provenance"]["kind"], "github.repair_task.api")

            # Forged candidate Full receipt (matching head/tree/success) lacks provenance.
            forged_receipt = {
                "name": FULL_SUITE_CONTEXT,
                "headSha": HEAD,
                "gitTree": TREE,
                "status": "success",
            }
            with self.assertRaises(ReviewGateError) as forged:
                require_full_receipt_for_gate_success(
                    gate_success=True,
                    full_receipt=forged_receipt,
                    head_sha=HEAD,
                    git_tree=TREE,
                )
            self.assertIn(forged.exception.code, {"full_receipt_untrusted_channel", "full_receipt_untrusted_provenance"})

            forged_candidate_kind = {
                **forged_receipt,
                "provenance": {
                    "kind": "candidate.worktree_file",
                    "headSha": HEAD,
                    "authenticated": True,
                },
            }
            with self.assertRaises(ReviewGateError) as forged_kind:
                require_full_receipt_for_gate_success(
                    gate_success=True,
                    full_receipt=forged_candidate_kind,
                    head_sha=HEAD,
                    git_tree=TREE,
                )
            self.assertIn(forged_kind.exception.code, {"full_receipt_untrusted_channel", "full_receipt_untrusted_provenance"})

            with self.assertRaises(ReviewGateError) as stamp_reject:
                stamp_full_receipt_provenance(
                    forged_receipt,
                    provenance_kind="candidate.worktree_file",
                    head_sha=HEAD,
                )
            self.assertIn(stamp_reject.exception.code, {"full_receipt_untrusted_channel", "full_receipt_untrusted_provenance"})

            # Trusted Checks API stamp remains valid.
            trusted_receipt = stamp_full_receipt_provenance(
                forged_receipt,
                provenance_kind="github.check_runs.api",
                head_sha=HEAD,
                evidence_ref="checks:trusted",
            )
            require_full_receipt_for_gate_success(
                gate_success=True,
                full_receipt=trusted_receipt,
                head_sha=HEAD,
                git_tree=TREE,
            )

            # CLI authenticate-provider-error used by workflow trusted route.
            auth_cli = subprocess.run(
                [
                    sys.executable,
                    str(MODULE),
                    "authenticate-provider-error",
                    "--provider-error-json",
                    json.dumps(
                        {
                            "verified": True,
                            "class": "quota",
                            "source": "operator_verified_provider_error",
                            "headSha": HEAD,
                        }
                    ),
                    "--provenance-kind",
                    "github.repository_variable",
                    "--head-sha",
                    HEAD,
                    "--evidence-ref",
                    "vars.LINKTREND_REVIEW_GATE_VERIFIED_PROVIDER_ERROR",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(auth_cli.returncode, 0, auth_cli.stderr)
            auth_payload = json.loads(auth_cli.stdout)
            self.assertTrue(auth_payload["provenance"]["authenticated"])
            self.assertEqual(
                verified_provider_unavailability(auth_payload),
                "quota",
            )

if __name__ == "__main__":
    unittest.main()
