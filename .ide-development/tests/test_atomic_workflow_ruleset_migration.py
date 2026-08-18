"""Focused adversarial tests for WP-U05 atomic workflow/ruleset migration."""

from __future__ import annotations

import unittest

from scripts.gitops import atomic_workflow_ruleset_migration as mig
from scripts.gitops import repository_protection as rp


class CheckContractTests(unittest.TestCase):
    def test_active_contract_derives_source_policy_not_obsolete_step(self) -> None:
        contract = mig.derive_active_check_contract(release_id="v2.4.0")
        self.assertEqual(contract["checks"]["sourcePolicy"], "Linktrend Branch Source Policy")
        self.assertEqual(
            contract["obsoleteManaged"]["Enforce allowed PR source branches"],
            "Linktrend Branch Source Policy",
        )
        self.assertNotIn(
            "Enforce allowed PR source branches",
            contract["checks"].values(),
        )

    def test_protection_baseline_uses_active_source_policy(self) -> None:
        dev = rp.managed_baseline("development")
        self.assertEqual(
            dev,
            [
                "Linktrend Review Gate",
                "Verify IDE Development",
                "Linktrend Branch Source Policy",
            ],
        )
        for branch in ("staging", "main"):
            checks = rp.managed_baseline(branch)
            self.assertIn("Linktrend Branch Source Policy", checks)
            self.assertNotIn("Enforce allowed PR source branches", checks)


class ThreeBranchRenameTests(unittest.TestCase):
    def test_rename_migrates_all_three_branches_together(self) -> None:
        plan = mig.plan_three_branch_rename(
            {
                "development": [
                    "Linktrend Review Gate",
                    "Verify IDE Development",
                    "Enforce allowed PR source branches",
                ],
                "staging": ["Verify IDE Development", "Enforce allowed PR source branches"],
                "main": ["Verify IDE Development", "Enforce allowed PR source branches"],
            }
        )
        self.assertTrue(plan["complete"])
        for branch in mig.GOVERNED_BRANCHES:
            after = plan["branches"][branch]["after"]
            self.assertIn("Linktrend Branch Source Policy", after)
            self.assertNotIn("Enforce allowed PR source branches", after)
            self.assertEqual(plan["branches"][branch]["action"], "update")

    def test_missing_branch_is_incomplete_not_success(self) -> None:
        plan = mig.plan_three_branch_rename(
            {
                "development": ["Enforce allowed PR source branches"],
                "staging": ["Enforce allowed PR source branches"],
            }
        )
        self.assertFalse(plan["complete"])
        self.assertEqual(plan["code"], mig.MIGRATION_INCOMPLETE)

    def test_apply_failure_after_one_branch_rolls_back(self) -> None:
        plan = mig.plan_three_branch_rename(
            {
                "development": ["Enforce allowed PR source branches"],
                "staging": ["Enforce allowed PR source branches"],
                "main": ["Enforce allowed PR source branches"],
            }
        )
        store: dict[str, list[str]] = {
            "development": ["Enforce allowed PR source branches"],
            "staging": ["Enforce allowed PR source branches"],
            "main": ["Enforce allowed PR source branches"],
        }

        def apply_branch(branch: str, after: list[str]) -> None:
            if branch == "staging":
                raise RuntimeError("simulated staging write failure")
            store[branch] = list(after)

        def restore_branch(branch: str, before: list[str]) -> None:
            store[branch] = list(before)

        result = mig.apply_atomic_branch_updates(
            plan, apply_branch=apply_branch, restore_branch=restore_branch
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], mig.MIGRATION_INCOMPLETE)
        self.assertFalse(result["falseSuccess"])
        self.assertEqual(
            store,
            {
                "development": ["Enforce allowed PR source branches"],
                "staging": ["Enforce allowed PR source branches"],
                "main": ["Enforce allowed PR source branches"],
            },
        )


class PreserveRepoOwnedTests(unittest.TestCase):
    def test_union_preserves_repo_owned_and_replaces_obsolete_managed(self) -> None:
        managed = rp.managed_baseline("development")
        union = rp.union_checks(
            managed,
            [
                "Enforce allowed PR source branches",
                "Consumer Custom Lint",
                "Verify IDE Development",
            ],
            ["Extra Gate"],
        )
        self.assertIn("Consumer Custom Lint", union["preserved"])
        self.assertIn("Extra Gate", union["preserved"])
        self.assertIn("Linktrend Branch Source Policy", union["desired"])
        self.assertNotIn("Enforce allowed PR source branches", union["desired"])
        self.assertEqual(union["desired"].index("Linktrend Review Gate"), 0)


class ContextDefectTests(unittest.TestCase):
    def test_detects_missing_misspelled_duplicate_stale_skipped_wrong_event(self) -> None:
        defects = mig.detect_context_defects(
            required=[
                "Linktrend Branch Source Policy",
                "Linktrend Review Gate",
                "Verify IDE Development",
                "Linktrend Fast Checks",
            ],
            published=[
                {"name": "Linktrend Branch Source Policy", "conclusion": "skipped", "event": "push"},
                {"name": "Linktrend Branch Source Policy", "conclusion": "skipped", "event": "push"},
                {"name": "linktrend fast checks", "conclusion": "success", "event": "pull_request"},
                {"name": "Enforce allowed PR source branches", "conclusion": "success", "event": "pull_request"},
                {
                    "name": "Linktrend Review Gate",
                    "conclusion": "success",
                    "event": "pull_request",
                    "head": "a" * 40,
                    "expectedHead": "b" * 40,
                },
            ],
            expected_events=["pull_request"],
        )
        kinds = {d["kind"] for d in defects}
        self.assertIn("duplicate", kinds)
        self.assertIn("misspelled", kinds)
        self.assertIn("stale", kinds)
        self.assertIn("skipped_only", kinds)
        self.assertIn("wrong_event", kinds)
        self.assertIn("missing", kinds)


class EvaluatorMigrationTests(unittest.TestCase):
    def test_replaces_stale_defaults_and_repository_variables(self) -> None:
        result = mig.migrate_evaluator_check_names(
            {
                "integratorRequiredChecks": [
                    "Verify IDE Development",
                    "Enforce allowed PR source branches",
                ],
                "packagerRequiredChecks": ["Cursor Bugbot", "Verify IDE Development"],
                "promoterRequiredChecks": "Verify IDE Development,Enforce allowed PR source branches",
                "repositoryVariables": {
                    "LINKTREND_INTEGRATOR_REQUIRED_CHECKS": "Verify IDE Development,Enforce allowed PR source branches",
                    "LINKTREND_STAGING_GATE_CHECKS": "Verify IDE Development",
                    "OTHER": "keep",
                },
            }
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["changed"])
        after = result["after"]
        self.assertEqual(
            after["integratorRequiredChecks"],
            ["Verify IDE Development", "Linktrend Branch Source Policy"],
        )
        self.assertEqual(
            after["packagerRequiredChecks"],
            ["Linktrend Review Gate", "Verify IDE Development"],
        )
        self.assertEqual(
            after["promoterRequiredChecks"],
            "Verify IDE Development,Linktrend Branch Source Policy",
        )
        self.assertEqual(
            after["repositoryVariables"]["LINKTREND_INTEGRATOR_REQUIRED_CHECKS"],
            "Verify IDE Development,Linktrend Branch Source Policy",
        )
        self.assertEqual(after["repositoryVariables"]["OTHER"], "keep")


class LabelTests(unittest.TestCase):
    def test_creates_exact_full_suite_label_when_missing(self) -> None:
        plan = mig.reconcile_managed_labels([])
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["actions"][0]["op"], "create")
        self.assertEqual(plan["actions"][0]["label"]["name"], "linktrend-full-suite")

    def test_conflicting_metadata_and_wrong_name_fail_closed(self) -> None:
        conflict = mig.reconcile_managed_labels(
            [
                {
                    "name": "linktrend-full-suite",
                    "description": "wrong",
                    "color": "ffffff",
                }
            ]
        )
        self.assertFalse(conflict["ok"])
        self.assertEqual(conflict["problems"][0]["kind"], "conflicting_metadata")

        wrong = mig.reconcile_managed_labels(
            [{"name": "Linktrend-Full-Suite", "description": "x", "color": "0E8A16"}]
        )
        self.assertFalse(wrong["ok"])
        self.assertEqual(wrong["problems"][0]["kind"], "wrong_name")

    def test_label_application_rejects_stale_or_ineligible_pr(self) -> None:
        head = "a" * 40
        ok = mig.evaluate_label_application(
            label_name="linktrend-full-suite",
            pr={"head": {"sha": head}, "state": "open"},
            expected_head=head,
            eligible_heads=[head],
        )
        self.assertTrue(ok["ok"])

        stale = mig.evaluate_label_application(
            label_name="linktrend-full-suite",
            pr={"head": {"sha": "b" * 40}, "state": "open"},
            expected_head=head,
            eligible_heads=[head],
        )
        self.assertFalse(stale["ok"])
        self.assertEqual(stale["code"], "stale_or_ineligible")

        wrong = mig.evaluate_label_application(
            label_name="full-suite",
            pr={"head": {"sha": head}, "state": "open"},
            expected_head=head,
        )
        self.assertEqual(wrong["code"], "wrong_name")


class TrustedVerifierTests(unittest.TestCase):
    def test_candidate_only_verifier_refuses_and_keeps_sealed_identity(self) -> None:
        head = "c" * 40
        tree = "d" * 40
        plan = mig.plan_trusted_verifier_migration(
            trusted_base_verifier="gate-v1",
            candidate_verifier="gate-v2",
            sealed_candidate_head=head,
            sealed_candidate_tree=tree,
        )
        self.assertFalse(plan["ok"])
        self.assertEqual(plan["code"], mig.TRUSTED_GATE_UNAVAILABLE)
        self.assertTrue(plan["candidateUnchanged"])
        self.assertEqual(plan["sealedCandidate"], {"head": head, "tree": tree})

    def test_failed_trusted_install_reports_unavailable_without_candidate_mutation(self) -> None:
        head = "c" * 40
        tree = "d" * 40
        plan = mig.plan_trusted_verifier_migration(
            trusted_base_verifier="gate-v1",
            candidate_verifier="gate-v2",
            sealed_candidate_head=head,
            sealed_candidate_tree=tree,
            trusted_install_evidence={"status": "failed", "verified": False, "detail": "ruleset reject"},
        )
        self.assertFalse(plan["ok"])
        self.assertEqual(plan["code"], mig.TRUSTED_GATE_UNAVAILABLE)
        self.assertTrue(plan["priorTrustedPreserved"])
        self.assertTrue(plan["candidateUnchanged"])

    def test_separate_trusted_install_resumes_unchanged_candidate(self) -> None:
        head = "c" * 40
        tree = "d" * 40
        plan = mig.plan_trusted_verifier_migration(
            trusted_base_verifier="gate-v1",
            candidate_verifier="gate-v2",
            sealed_candidate_head=head,
            sealed_candidate_tree=tree,
            trusted_install_evidence={
                "status": "installed",
                "verified": True,
                "installedVerifier": "gate-v2",
            },
        )
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["action"], "resume_unchanged_candidate")
        self.assertEqual(plan["sealedCandidate"]["head"], head)


class CapabilityPreflightTests(unittest.TestCase):
    def test_http_403_and_protected_false_stop_before_mutation(self) -> None:
        report = mig.capability_preflight({"httpStatus": 403, "mechanism": "rulesets"})
        self.assertFalse(report.ok)
        self.assertEqual(report.code, mig.NATIVE_PROTECTION_UNVERIFIED)

        report2 = mig.capability_preflight(
            {
                "mechanism": "rulesets",
                "branches": {
                    "development": {"protected": False},
                    "staging": {"protected": True},
                    "main": {"protected": True},
                },
            }
        )
        self.assertFalse(report2.ok)
        self.assertIn("development:protected_false", report2.findings)

    def test_invisible_org_rules_and_missing_permission(self) -> None:
        report = mig.capability_preflight(
            {
                "mechanism": "rulesets",
                "organizationRulesPresent": True,
                "organizationRulesVisible": False,
            }
        )
        self.assertFalse(report.ok)
        self.assertEqual(report.code, mig.NATIVE_PROTECTION_UNVERIFIED)

        report2 = mig.capability_preflight(
            {"mechanism": "rulesets", "administrator": False, "missingPermission": "admin:repo"}
        )
        self.assertFalse(report2.ok)

    def test_reduced_assurance_requires_founder_approval(self) -> None:
        denied = mig.capability_preflight(
            {"mechanism": "rulesets", "reducedAssuranceRequested": True, "founderApproved": False}
        )
        self.assertFalse(denied.ok)
        self.assertEqual(denied.code, mig.REDUCED_ASSURANCE)

        allowed = mig.capability_preflight(
            {"mechanism": "rulesets", "reducedAssuranceRequested": True, "founderApproved": True}
        )
        self.assertTrue(allowed.ok)
        self.assertEqual(allowed.assurance, "reduced_assurance")


class InstallationCompletenessTests(unittest.TestCase):
    def test_obsolete_required_check_blocks_completion(self) -> None:
        capability = mig.CapabilityReport(ok=True, assurance="protected")
        result = mig.installation_complete(
            branch_required={
                "development": ["Enforce allowed PR source branches"],
                "staging": ["Linktrend Branch Source Policy"],
                "main": ["Linktrend Branch Source Policy"],
            },
            published_by_branch={
                "development": ["Enforce allowed PR source branches"],
                "staging": ["Linktrend Branch Source Policy"],
                "main": ["Linktrend Branch Source Policy"],
            },
            labels=[dict(mig.FULL_SUITE_LABEL)],
            evaluator_config={
                "integratorRequiredChecks": ["Verify IDE Development", "Linktrend Branch Source Policy"]
            },
            capability=capability,
            live_consumer_verified=None,
        )
        self.assertFalse(result["complete"])
        self.assertTrue(any("obsolete_required" in p for p in result["problems"]))


if __name__ == "__main__":
    unittest.main()
