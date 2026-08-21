"""Focused tests for WP-U07 repository-owned CI trigger contract."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from scripts.gitops.repository_ci_contract import (
    CLASS_APPLICATION,
    CLASS_MIXED,
    CLASS_TRUSTED,
    CLASS_UNKNOWN,
    EVENT_CHECKPOINT_PUSH,
    EVENT_PHASE_PR,
    EVENT_PROMOTION,
    EVENT_SEALED_FULL,
    PROFILE_FAST,
    PROFILE_FULL,
    PROFILE_NONE,
    PROFILE_PROMOTION,
    PROFILE_TRUSTED,
    ContractError,
    audit_workflow_triggers,
    authorize_omission,
    classify_changed_paths,
    compute_cache_key,
    default_contract,
    digest_json,
    digest_text,
    evaluate_aggregate_gate,
    evaluate_cache_advisory,
    evaluate_promotion_with_receipt,
    expand_reverse_dependencies,
    innermost_diagnostic,
    installer_audit_repository_ci_triggers,
    load_contract,
    run_component_preflight,
    select_profile,
    validate_affected_surface_evidence,
    validate_artifact_file,
    validate_contract,
    validate_coverage_manifest,
    verify_promotion_exact_receipt,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / ".github" / "linktrend-repository-ci-contract.json"
SCHEMA_PATH = ROOT / "core" / "managed-core" / "schemas" / "repository-ci-contract.schema.json"
MANIFEST_SCHEMA = ROOT / "core" / "managed-core" / "schemas" / "ci-component-manifest.schema.json"
EVIDENCE_SCHEMA = ROOT / "core" / "managed-core" / "schemas" / "ci-evidence.schema.json"
MODULE = ROOT / "scripts" / "gitops" / "repository_ci_contract.py"


def _head(n: int = 1) -> str:
    return f"{n:040x}"


def _tree(n: int = 2) -> str:
    return f"{n:040x}"


class RepositoryCiTriggerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_contract(ROOT)
        self.assertEqual(self.contract["kind"], "repository-ci-contract")

    def test_packaged_schemas_and_repo_contract_exist(self) -> None:
        self.assertTrue(CONTRACT_PATH.is_file())
        self.assertTrue(SCHEMA_PATH.is_file())
        self.assertTrue(MANIFEST_SCHEMA.is_file())
        self.assertTrue(EVIDENCE_SCHEMA.is_file())
        self.assertTrue(MODULE.is_file())
        validate_contract(json.loads(CONTRACT_PATH.read_text(encoding="utf-8")))

    def test_checkpoint_push_consumes_no_managed_compute(self) -> None:
        decision = select_profile(
            event=EVENT_CHECKPOINT_PUSH,
            branch="issue/320-wp-u07-repository-owned-ci-trigger-contract",
            changed_paths=["src/app.ts"],
            contract=self.contract,
        )
        self.assertEqual(decision.profile, PROFILE_NONE)
        self.assertFalse(decision.startsManagedCompute)

    def test_phase_runs_fast_and_sealed_head_runs_full(self) -> None:
        fast = select_profile(
            event=EVENT_PHASE_PR,
            branch="phase/next-ide-development-v2.4.0",
            changed_paths=["src/app.ts"],
            contract=self.contract,
        )
        self.assertEqual(fast.profile, PROFILE_FAST)
        self.assertTrue(fast.startsManagedCompute)
        full = select_profile(
            event=EVENT_SEALED_FULL,
            branch="phase/next-ide-development-v2.4.0",
            changed_paths=["src/app.ts"],
            contract=self.contract,
        )
        self.assertEqual(full.profile, PROFILE_FULL)
        self.assertTrue(full.startsManagedCompute)

    def test_unchanged_promotion_receipt_only_and_changed_fails(self) -> None:
        ok = select_profile(
            event=EVENT_PROMOTION,
            branch="promote/staging/demo",
            changed_paths=[],
            contract=self.contract,
            promotion_tree_unchanged=True,
        )
        self.assertEqual(ok.profile, PROFILE_PROMOTION)
        self.assertFalse(ok.startsManagedCompute)
        with self.assertRaises(ContractError) as ctx:
            select_profile(
                event=EVENT_PROMOTION,
                branch="promote/main/demo",
                changed_paths=["x"],
                contract=self.contract,
                promotion_tree_unchanged=False,
            )
        self.assertEqual(ctx.exception.code, "promotion_content_changed")

    def test_repository_commands_preserved_in_contract_profiles(self) -> None:
        fast_cmds = self.contract["profiles"]["fast"]["commands"]
        self.assertTrue(fast_cmds)
        self.assertTrue(all(isinstance(cmd, list) and cmd for cmd in fast_cmds))

    def test_trusted_governance_vs_full_selection(self) -> None:
        trusted = select_profile(
            event=EVENT_SEALED_FULL,
            branch="issue/1-gov",
            changed_paths=[".github/workflows/ci.yml", "scripts/gitops/repository_ci_contract.py"],
            contract=self.contract,
        )
        self.assertEqual(trusted.profile, PROFILE_TRUSTED)
        mixed = select_profile(
            event=EVENT_SEALED_FULL,
            branch="issue/1-mixed",
            changed_paths=[".github/workflows/ci.yml", "apps/web/page.tsx"],
            contract=self.contract,
        )
        self.assertEqual(mixed.profile, PROFILE_FULL)
        self.assertEqual(mixed.classification, CLASS_MIXED)

    def test_aggregate_gate_trusted_and_fail_closed_cases(self) -> None:
        proofs = list(self.contract["trustedGovernance"]["requiredProofs"])
        ok = evaluate_aggregate_gate(
            contract=self.contract,
            selected_profile=PROFILE_TRUSTED,
            classification=CLASS_TRUSTED,
            governance_proofs=proofs,
        )
        self.assertTrue(ok.ok)
        self.assertFalse(ok.labeledAsFull)

        incomplete = evaluate_aggregate_gate(
            contract=self.contract,
            selected_profile=PROFILE_TRUSTED,
            classification=CLASS_TRUSTED,
            governance_proofs=proofs[:-1],
        )
        self.assertFalse(incomplete.ok)
        self.assertEqual(incomplete.code, "governance_profile_incomplete")

        forged = classify_changed_paths(["../escape/app.ts"], self.contract)
        self.assertEqual(forged["classification"], CLASS_UNKNOWN)

        mixed_as_trusted = evaluate_aggregate_gate(
            contract=self.contract,
            selected_profile=PROFILE_TRUSTED,
            classification=CLASS_MIXED,
            governance_proofs=proofs,
        )
        self.assertFalse(mixed_as_trusted.ok)

        raw = evaluate_aggregate_gate(
            contract=self.contract,
            selected_profile=PROFILE_FULL,
            classification=CLASS_APPLICATION,
            required_raw_full_context=True,
        )
        self.assertEqual(raw.code, "raw_full_context_forbidden")

    def test_full_requires_coverage_manifest_and_rejects_missing_component(self) -> None:
        head, tree = _head(11), _tree(22)
        receipt = {
            "conclusion": "success",
            "profile": PROFILE_FULL,
            "candidateHead": head,
            "candidateIdentity": {"headCommit": head, "gitTree": tree},
        }
        manifest = {
            "schemaVersion": 1,
            "kind": "ci-component-manifest",
            "candidateHead": head,
            "candidateTree": tree,
            "components": [
                {"id": "governance-gate-contract", "status": "passed"},
                {"id": "secret-scan", "status": "passed"},
                {"id": "application-tests", "status": "passed"},
                # production-resolution intentionally omitted without authorization
            ],
        }
        bad = evaluate_aggregate_gate(
            contract=self.contract,
            selected_profile=PROFILE_FULL,
            classification=CLASS_APPLICATION,
            application_receipt=receipt,
            coverage_manifest=manifest,
            candidate_head=head,
        )
        self.assertFalse(bad.ok)
        self.assertIn(bad.code, {"coverage_component_absent", "coverage_incomplete"})

        manifest["components"].append({"id": "production-resolution", "status": "passed"})
        good = evaluate_aggregate_gate(
            contract=self.contract,
            selected_profile=PROFILE_FULL,
            classification=CLASS_APPLICATION,
            application_receipt=receipt,
            coverage_manifest=manifest,
            candidate_head=head,
        )
        self.assertTrue(good.ok)
        self.assertTrue(good.labeledAsFull)

        stale = evaluate_aggregate_gate(
            contract=self.contract,
            selected_profile=PROFILE_FULL,
            classification=CLASS_APPLICATION,
            application_receipt=receipt,
            coverage_manifest=manifest,
            candidate_head=_head(99),
        )
        self.assertEqual(stale.code, "application_receipt_stale")

    def test_preflight_bindings_bootstrap_and_resume(self) -> None:
        component = {
            "id": "browser-e2e",
            "runtime": [
                {
                    "id": "chromium",
                    "kind": "browser",
                    "allowedVersions": ["120.0"],
                    "bootstrapCommand": ["install-browser", "chromium"],
                    "binding": {
                        "variable": "PLAYWRIGHT_BROWSER",
                        "executablePath": "/opt/browsers/chromium",
                    },
                }
            ],
        }
        missing = run_component_preflight(
            component=component,
            environ={},
            present_executables={},
            successful_component_ids=["unit-tests"],
            bootstrap_runner=lambda command, env: {
                "ok": False,
                "detail": "not installed",
            },
        )
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["classification"], "infrastructure")
        self.assertEqual(missing["retainedComponentIds"], ["unit-tests"])
        self.assertTrue(missing["bootstrap"]["ran"])

        sibling_only = run_component_preflight(
            component=component,
            environ={"OTHER_BROWSER": "/opt/browsers/chromium"},
            present_executables={"chromium": "120.0"},
            successful_component_ids=["unit-tests"],
        )
        self.assertFalse(sibling_only["ok"])
        self.assertEqual(sibling_only["detail"], "binding_mismatch")
        self.assertFalse(sibling_only["bindings"][0]["matched"])

        bootstrapped = run_component_preflight(
            component=component,
            environ={},
            present_executables={},
            successful_component_ids=["unit-tests"],
            invalidated_component_ids=["browser-e2e"],
            bootstrap_runner=lambda command, env: {
                "ok": True,
                "verifiedVersion": "120.0",
                "resolvedPath": "/opt/browsers/chromium",
                "evidencePath": "build/browser-bootstrap.json",
            },
        )
        self.assertTrue(bootstrapped["ok"])
        self.assertTrue(bootstrapped["bootstrap"]["ran"])
        self.assertEqual(bootstrapped["bootstrap"]["evidencePath"], "build/browser-bootstrap.json")
        self.assertTrue(bootstrapped["bindings"][0]["matched"])
        self.assertTrue(bootstrapped["resumedOnlyInvalidated"])

        skipped = run_component_preflight(
            component={"id": "unit-tests", "runtime": []},
            successful_component_ids=["unit-tests"],
            invalidated_component_ids=["browser-e2e"],
        )
        self.assertTrue(skipped["ok"])
        self.assertEqual(skipped["detail"], "skipped_not_invalidated")
        self.assertEqual(skipped["retainedComponentIds"], ["unit-tests"])

        ok = run_component_preflight(
            component=component,
            environ={"PLAYWRIGHT_BROWSER": "/opt/browsers/chromium"},
            present_executables={"chromium": "120.0"},
            successful_component_ids=["unit-tests"],
        )
        self.assertTrue(ok["ok"])

    def test_artifact_stdout_wrong_schema_missing_and_wrong_head_fail(self) -> None:
        artifact = {
            "id": "coverage-json",
            "producer": "tests",
            "path": "build/coverage.json",
            "schemaVersion": 1,
            "consumer": "aggregate-gate",
            "stdoutCannotSatisfy": True,
        }
        stdout_only = validate_artifact_file(
            artifact=artifact,
            file_path=None,
            candidate_head=_head(1),
            stdout_json={"schemaVersion": 1, "candidateHead": _head(1)},
        )
        self.assertFalse(stdout_only["ok"])
        self.assertTrue(stdout_only["stdoutOnlyRejected"])

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "coverage.json"
            path.write_text(
                json.dumps({"schemaVersion": 2, "candidateHead": _head(1)}),
                encoding="utf-8",
            )
            wrong_schema = validate_artifact_file(
                artifact=artifact,
                file_path=path,
                candidate_head=_head(1),
            )
            self.assertEqual(wrong_schema["code"], "artifact_wrong_schema")
            path.write_text(
                json.dumps({"schemaVersion": 1, "candidateHead": _head(2)}),
                encoding="utf-8",
            )
            wrong_head = validate_artifact_file(
                artifact=artifact,
                file_path=path,
                candidate_head=_head(1),
            )
            self.assertEqual(wrong_head["code"], "artifact_wrong_head")
            path.write_text(
                json.dumps({"schemaVersion": 1, "ok": True}),
                encoding="utf-8",
            )
            missing_head = validate_artifact_file(
                artifact=artifact,
                file_path=path,
                candidate_head=_head(1),
            )
            self.assertEqual(missing_head["code"], "artifact_missing_head")
            self.assertNotEqual(missing_head.get("candidateHead"), _head(1))
            path.write_text(
                json.dumps({"schemaVersion": 1, "candidateHead": _head(1)}),
                encoding="utf-8",
            )
            good = validate_artifact_file(
                artifact=artifact,
                file_path=path,
                candidate_head=_head(1),
            )
            self.assertTrue(good["ok"])
            self.assertEqual(good["candidateHead"], _head(1))

    def test_innermost_diagnostic_retained(self) -> None:
        diag = innermost_diagnostic(
            [
                {"component": "recovery", "phase": "wrapper", "exit": 1, "message": "bash exited 1"},
                {
                    "component": "recovery",
                    "phase": "nested",
                    "exit": 17,
                    "message": "restore failed: volume missing",
                    "evidencePath": "build/recovery.err",
                    "stderrTail": "volume missing",
                },
            ]
        )
        self.assertEqual(diag["message"], "restore failed: volume missing")
        self.assertEqual(diag["evidencePath"], "build/recovery.err")

    def test_authorized_omission_and_fail_closed(self) -> None:
        good = authorize_omission(
            classifier_digest=digest_text("classifier"),
            inputs_digest=digest_json(["a.ts"]),
            authorized=True,
        )
        self.assertTrue(good["ok"])
        self.assertFalse(authorize_omission(classifier_digest=None, inputs_digest=None, authorized=True)["ok"])
        self.assertEqual(
            authorize_omission(
                classifier_digest=digest_text("x"),
                inputs_digest=digest_text("y"),
                authorized=True,
                forged=True,
            )["code"],
            "omission_forged",
        )
        self.assertEqual(
            authorize_omission(
                classifier_digest=digest_text("x"),
                inputs_digest=digest_text("y"),
                authorized=True,
                stale=True,
            )["code"],
            "omission_stale",
        )
        omitted = validate_coverage_manifest(
            self.contract,
            {
                "schemaVersion": 1,
                "kind": "ci-component-manifest",
                "candidateHead": _head(3),
                "candidateTree": _tree(4),
                "components": [
                    {"id": "governance-gate-contract", "status": "passed"},
                    {"id": "secret-scan", "status": "passed"},
                    {"id": "application-tests", "status": "passed"},
                    {
                        "id": "production-resolution",
                        "status": "omitted",
                        "omission": good["omission"],
                    },
                ],
            },
            candidate_head=_head(3),
            candidate_tree=_tree(4),
        )
        self.assertTrue(omitted["ok"])

    def test_monorepo_reverse_dependency_requires_production_probes(self) -> None:
        result = expand_reverse_dependencies(
            changed_paths=["packages/ui/src/index.ts", "packages/ui/package.json"],
            dependency_graph={"packages/ui": ["apps/web", "apps/admin"]},
            package_export_paths=["packages/ui/src/index.ts"],
            selected_profile=PROFILE_FULL,
        )
        self.assertEqual(result["reverseDependencies"], ["apps/admin", "apps/web"])
        self.assertIn("production-resolution", result["requiredProbes"])
        self.assertIn("docker-import-build", result["requiredProbes"])
        self.assertTrue(result["typecheckInsufficient"])
        self.assertNotIn("typecheck", result["requiredProbes"])
        self.assertEqual(result["selectedProfile"], PROFILE_FULL)
        self.assertTrue(str(result["classifierDigest"]).startswith("sha256:"))
        self.assertTrue(str(result["inputsDigest"]).startswith("sha256:"))
        self.assertEqual(validate_affected_surface_evidence(result)["ok"], True)
        with self.assertRaises(ContractError):
            validate_affected_surface_evidence(
                {k: v for k, v in result.items() if k != "classifierDigest"}
            )

    def test_cache_key_fixed_before_mutation_and_advisory(self) -> None:
        key = compute_cache_key(
            candidate_head=_head(5),
            tracked_manifest_digest=digest_text("tracked"),
            lockfile_digest=digest_text("lock"),
            workspace_mutated=False,
        )
        self.assertTrue(key["keyFixedBeforeMutation"])
        self.assertTrue(key["advisory"])
        with self.assertRaises(ContractError):
            compute_cache_key(
                candidate_head=_head(5),
                tracked_manifest_digest=digest_text("tracked"),
                lockfile_digest=digest_text("lock"),
                workspace_mutated=True,
            )
        advisory = evaluate_cache_advisory(
            cache_key=key["cacheKey"],
            restore_status="error",
            save_status="error",
            required_profile_ok=True,
            required_component_failed=False,
        )
        self.assertTrue(advisory["correctnessUnchanged"])
        self.assertTrue(advisory["ok"])
        self.assertIn("cache_restore_failed", advisory["warnings"])

        still_blocks = evaluate_cache_advisory(
            cache_key=key["cacheKey"],
            restore_status="hit",
            save_status="saved",
            required_profile_ok=False,
            required_component_failed=True,
        )
        self.assertFalse(still_blocks["ok"])

        broad = evaluate_cache_advisory(
            cache_key=key["cacheKey"],
            restore_status="miss",
            save_status="skipped",
            required_profile_ok=True,
            required_component_failed=False,
            broad_post_job_hash=True,
        )
        self.assertTrue(broad["rejectedBroadHash"])
        self.assertFalse(broad["ok"])

    def test_installer_audit_detects_broad_expensive_triggers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wf = root / ".github" / "workflows"
            wf.mkdir(parents=True)
            (wf / "expensive.yml").write_text(
                "\n".join(
                    [
                        "name: Full matrix",
                        "on:",
                        "  pull_request:",
                        "  push:",
                        "jobs:",
                        "  build-and-test:",
                        "    runs-on: ubuntu-latest",
                        "    steps:",
                        "      - run: echo e2e browser matrix",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (wf / "promotion-safe.yml").write_text(
                "\n".join(
                    [
                        "name: Receipt gate",
                        "on:",
                        "  pull_request:",
                        "    branches: ['promote/staging/**']",
                        "jobs:",
                        "  verify:",
                        "    runs-on: ubuntu-latest",
                        "    steps:",
                        "      - run: echo ok",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (root / ".github" / "linktrend-repository-ci-contract.json").write_text(
                json.dumps(default_contract()),
                encoding="utf-8",
            )
            result = installer_audit_repository_ci_triggers(root)
            self.assertFalse(result["ok"])
            self.assertEqual(result["scanned"], 2)
            self.assertEqual(result["conflicts"][0]["code"], "promotion_expensive_retrigger")
            self.assertFalse(result["mayModify"])
            with self.assertRaises(ContractError):
                installer_audit_repository_ci_triggers(root, mutate=True, rollout_scope=False)

    def test_installer_audit_accepts_expensive_workflow_guarded_to_phase_heads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workflows = Path(tmp) / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "full.yml").write_text(
                """name: Full matrix
on:
  pull_request:
    branches: [development]
    types: [labeled]
jobs:
  full:
    if: startsWith(github.event.pull_request.head.ref, 'phase/')
    runs-on: ubuntu-latest
    steps:
      - run: echo e2e browser matrix
""",
                encoding="utf-8",
            )
            result = audit_workflow_triggers(workflows, contract=self.contract)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["conflicts"], [])

    def test_audit_live_ide_development_workflows_report(self) -> None:
        # Factory CI currently has a broad trigger; audit must detect it without mutating.
        result = audit_workflow_triggers(ROOT / ".github" / "workflows", contract=self.contract)
        self.assertIn("scanned", result)
        self.assertGreaterEqual(result["scanned"], 1)
        self.assertFalse(result.get("mayModify", True))

    def test_install_and_verify_surfaces_attach_ci_trigger_audit(self) -> None:
        from scripts.ide_development import engine as engine_mod

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wf = root / ".github" / "workflows"
            wf.mkdir(parents=True)
            (wf / "expensive.yml").write_text(
                "\n".join(
                    [
                        "name: Full matrix",
                        "on:",
                        "  pull_request:",
                        "  push:",
                        "jobs:",
                        "  build-and-test:",
                        "    runs-on: ubuntu-latest",
                        "    steps:",
                        "      - run: echo e2e browser matrix",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (root / ".github" / "linktrend-repository-ci-contract.json").write_text(
                json.dumps(default_contract()),
                encoding="utf-8",
            )
            audit = engine_mod._repository_ci_trigger_audit(ROOT, root)
            self.assertIn("repositoryCiTriggerAudit", {"repositoryCiTriggerAudit": audit})
            self.assertFalse(audit["ok"])
            self.assertEqual(audit["conflicts"][0]["code"], "promotion_expensive_retrigger")

            # Mutating install/verify payload helper must carry the same key.
            class _FakePlan:
                has_conflicts = False

                def to_dict(self) -> dict:
                    return {"schemaVersion": 1, "command": "install", "actions": []}

            payload = engine_mod._plan_payload(
                _FakePlan(),
                repositoryCiTriggerAudit=audit,
            )
            self.assertEqual(
                payload["repositoryCiTriggerAudit"]["conflicts"][0]["code"],
                "promotion_expensive_retrigger",
            )
            source = (ROOT / "scripts" / "ide_development" / "engine.py").read_text(encoding="utf-8")
            self.assertGreaterEqual(source.count("repositoryCiTriggerAudit=ci_trigger_audit"), 3)
            self.assertIn("def run_install_or_update", source)
            self.assertIn("def run_verify", source)
            install_idx = source.index("def run_install_or_update")
            verify_idx = source.index("def run_verify")
            self.assertIn("repositoryCiTriggerAudit=ci_trigger_audit", source[install_idx:verify_idx])
            self.assertIn("repositoryCiTriggerAudit=ci_trigger_audit", source[verify_idx:])

    def test_promotion_exact_receipt_obeys_promotion_receipt_gate(self) -> None:
        import subprocess

        from scripts.gitops.coordinator import receipts

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()

            def git(*args: str) -> str:
                result = subprocess.run(
                    ["git", *args],
                    cwd=repo,
                    text=True,
                    capture_output=True,
                    check=True,
                )
                return result.stdout.strip()

            git("init", "-q")
            git("config", "user.email", "u07@example.invalid")
            git("config", "user.name", "WP-U07")
            git("remote", "add", "origin", "https://github.com/acme/promotion.git")
            (repo / "app.txt").write_text("one\n", encoding="utf-8")
            (repo / "deps.lock").write_text("dep-one\n", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "initial")
            identity = receipts.compute_candidate_identity(repo, ["deps.lock"], "full")
            receipt_payload = {
                "schemaVersion": 2,
                "candidateIdentity": identity.to_dict(),
                "workflowRunId": 401,
                "workflowRunAttempt": 1,
                "runnerLabel": "ubuntu-24.04-arm",
                "startedAt": "2026-08-17T01:00:00Z",
                "completedAt": "2026-08-17T01:01:00Z",
                "conclusion": "success",
                "commandDigest": "sha256:" + ("c" * 64),
                "evidenceDigests": {"evidence/full.log": "sha256:" + ("b" * 64)},
            }
            receipt_path = root / "full-receipt.json"
            receipts.write_receipt(receipt_payload, receipt_path)

            missing = verify_promotion_exact_receipt(
                receipt_path=root / "missing.json",
                repo_path=repo,
                dependencies=["deps.lock"],
                expected_head=identity.head_commit,
            )
            self.assertFalse(missing["ok"])
            self.assertEqual(missing["code"], "promotion_receipt_missing")
            self.assertEqual(missing["gate"], "promotion_receipt_gate")

            stale = verify_promotion_exact_receipt(
                receipt_path=receipt_path,
                repo_path=repo,
                dependencies=["deps.lock"],
                expected_head=_head(9),
            )
            self.assertFalse(stale["ok"])
            self.assertIn(stale["code"], {"promotion_receipt_stale", "promotion_receipt_wrong_head"})
            self.assertEqual(stale["gate"], "promotion_receipt_gate")

            wrong = evaluate_promotion_with_receipt(
                contract=self.contract,
                branch="promote/staging/demo",
                promotion_tree_unchanged=True,
                receipt=receipt_payload,
                identity=identity.to_dict(),
                expected_head=_head(8),
            )
            self.assertFalse(wrong["ok"])
            self.assertEqual(wrong["gate"], "promotion_receipt_gate")
            self.assertFalse(wrong["receipt"]["ok"])

            accepted = evaluate_promotion_with_receipt(
                contract=self.contract,
                branch="promote/staging/demo",
                promotion_tree_unchanged=True,
                receipt_path=receipt_path,
                repo_path=repo,
                dependencies=["deps.lock"],
                expected_head=identity.head_commit,
            )
            self.assertTrue(accepted["ok"])
            self.assertEqual(accepted["profile"]["profile"], PROFILE_PROMOTION)
            self.assertEqual(accepted["receipt"]["gate"], "promotion_receipt_gate")
            self.assertTrue(accepted["receipt"]["ok"])

    def test_ci_evidence_schema_accepts_real_producer_outputs(self) -> None:
        """Draft 2020-12 instance validation against packaged ci-evidence schema.

        Uses live ``run_component_preflight`` / ``expand_reverse_dependencies``
        (and cache producers) so the schema stays reconciled with owned fields
        while ``additionalProperties: false`` still rejects unknowns.
        """
        schema = json.loads(EVIDENCE_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema.get("$schema"), "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["$defs"]["preflightEvidence"]["additionalProperties"])
        self.assertFalse(schema["$defs"]["affectedSurfaceEvidence"]["additionalProperties"])
        validator = Draft202012Validator(schema)

        component = {
            "id": "browser-e2e",
            "runtime": [
                {
                    "id": "chromium",
                    "kind": "browser",
                    "allowedVersions": ["120.0"],
                    "bootstrapCommand": ["install-browser", "chromium"],
                    "binding": {
                        "variable": "PLAYWRIGHT_BROWSER",
                        "executablePath": "/opt/browsers/chromium",
                    },
                }
            ],
        }
        bootstrapped = run_component_preflight(
            component=component,
            environ={},
            present_executables={},
            successful_component_ids=["unit-tests"],
            invalidated_component_ids=["browser-e2e"],
            bootstrap_runner=lambda command, env: {
                "ok": True,
                "verifiedVersion": "120.0",
                "resolvedPath": "/opt/browsers/chromium",
                "evidencePath": "build/browser-bootstrap.json",
            },
        )
        self.assertIn("detail", bootstrapped)
        self.assertTrue(bootstrapped["resumedOnlyInvalidated"])
        self.assertEqual(bootstrapped["bootstrap"]["command"], ["install-browser", "chromium"])
        self.assertTrue(bootstrapped["bootstrap"]["ok"])
        self.assertEqual(bootstrapped["bootstrap"]["resolvedPath"], "/opt/browsers/chromium")
        self.assertTrue(bootstrapped["bindings"][0]["bootstrap"])
        validator.validate(bootstrapped)

        skipped = run_component_preflight(
            component={"id": "unit-tests", "runtime": []},
            successful_component_ids=["unit-tests"],
            invalidated_component_ids=["browser-e2e"],
        )
        self.assertEqual(skipped["detail"], "skipped_not_invalidated")
        self.assertTrue(skipped["resumedOnlyInvalidated"])
        validator.validate(skipped)

        affected = expand_reverse_dependencies(
            changed_paths=["packages/ui/src/index.ts", "packages/ui/package.json"],
            dependency_graph={"packages/ui": ["apps/web", "apps/admin"]},
            package_export_paths=["packages/ui/src/index.ts"],
            selected_profile=PROFILE_FULL,
        )
        self.assertTrue(affected["typecheckInsufficient"])
        self.assertTrue(affected["exportHit"])
        validator.validate(affected)

        cache_key = compute_cache_key(
            candidate_head=_head(5),
            tracked_manifest_digest=digest_text("tracked"),
            lockfile_digest=digest_text("lock"),
            workspace_mutated=False,
        )
        validator.validate(cache_key)
        advisory = evaluate_cache_advisory(
            cache_key=cache_key["cacheKey"],
            restore_status="hit",
            save_status="saved",
            required_profile_ok=True,
            required_component_failed=False,
        )
        self.assertTrue(advisory["correctnessUnchanged"])
        validator.validate(advisory)

        unknown_top = dict(bootstrapped)
        unknown_top["unexpectedProducerField"] = True
        with self.assertRaises(ValidationError):
            validator.validate(unknown_top)

        unknown_bootstrap = dict(bootstrapped)
        unknown_bootstrap["bootstrap"] = {
            **bootstrapped["bootstrap"],
            "extraBootstrapKey": "nope",
        }
        with self.assertRaises(ValidationError):
            validator.validate(unknown_bootstrap)

        unknown_binding = dict(bootstrapped)
        unknown_binding["bindings"] = [
            {**bootstrapped["bindings"][0], "rogue": 1},
        ]
        with self.assertRaises(ValidationError):
            validator.validate(unknown_binding)

        unknown_affected = dict(affected)
        unknown_affected["notOwned"] = "x"
        with self.assertRaises(ValidationError):
            validator.validate(unknown_affected)

        malformed_detail = dict(bootstrapped)
        malformed_detail["detail"] = 12
        with self.assertRaises(ValidationError):
            validator.validate(malformed_detail)

        malformed_flag = dict(bootstrapped)
        malformed_flag["resumedOnlyInvalidated"] = "yes"
        with self.assertRaises(ValidationError):
            validator.validate(malformed_flag)

        malformed_command = dict(bootstrapped)
        malformed_command["bootstrap"] = {
            **bootstrapped["bootstrap"],
            "command": "install-browser chromium",
        }
        with self.assertRaises(ValidationError):
            validator.validate(malformed_command)

        malformed_binding_bootstrap = dict(bootstrapped)
        malformed_binding_bootstrap["bindings"] = [
            {**bootstrapped["bindings"][0], "bootstrap": "true"},
        ]
        with self.assertRaises(ValidationError):
            validator.validate(malformed_binding_bootstrap)

        malformed_export = dict(affected)
        malformed_export["exportHit"] = "yes"
        with self.assertRaises(ValidationError):
            validator.validate(malformed_export)

        malformed_typecheck = dict(affected)
        malformed_typecheck["typecheckInsufficient"] = 1
        with self.assertRaises(ValidationError):
            validator.validate(malformed_typecheck)


if __name__ == "__main__":
    unittest.main()
