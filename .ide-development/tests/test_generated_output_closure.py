"""Adversarial tests for the PKT-08 generated-output closure contract."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.gitops.generated_output_closure import (
    BASELINE_REF_ENV,
    BASELINE_SHA_ENV,
    ClosureError,
    _generate_secret_scan_fixtures,
    _audit_command,
    candidate_source_tree,
    audit_dogfood_improvement_closure,
    close_generated_outputs,
    load_graph,
    verify_generated_outputs,
)


ROOT = Path(__file__).resolve().parents[2]


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def init_repo() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name) / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "development")
    git(root, "config", "user.email", "pkt08@example.invalid")
    git(root, "config", "user.name", "PKT-08 tests")
    git(root, "remote", "add", "origin", str(root / "origin.git"))
    return tmp, root


def write(root: Path, rel: str, value: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def commit(root: Path, message: str) -> None:
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)


def graph(
    outputs: list[dict[str, object]],
    *,
    max_passes: int = 3,
) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "kind": "generated-output-closure",
        "maxPasses": max_passes,
        "outputs": outputs,
    }


def output(
    output_path: str,
    generator: list[str],
    *,
    invalidating_sources: list[str] | None = None,
    depends_on: list[str] | None = None,
    output_id: str | None = None,
) -> dict[str, object]:
    return {
        "id": output_id or output_path.replace("/", "-"),
        "output": output_path,
        "generator": generator,
        "invalidatingSources": invalidating_sources or ["**/*.txt"],
        "dependsOn": depends_on or [],
    }


def write_graph(root: Path, payload: dict[str, object]) -> None:
    write(root, "closure.json", json.dumps(payload, indent=2) + "\n")


def script(root: Path, rel: str, body: str) -> list[str]:
    write(root, rel, body)
    return [sys.executable, rel]


class GeneratedOutputGraphTests(unittest.TestCase):
    def test_fixture_generator_relocates_only_one_exact_existing_approval(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        approved_bytes = ".".join(("ltfx", "fixture", "relocated", "v1"))
        digest = "sha256:" + hashlib.sha256(approved_bytes.encode("utf-8")).hexdigest()
        write(
            root,
            "fixture.py",
            '# moved\n{} = "{}"\n'.format("to" + "ken", approved_bytes),
        )
        write(
            root,
            ".github/linktrend-secret-scan-fixtures.json",
            json.dumps(
                {
                    "schemaVersion": 1,
                    "kind": "secret-scan-fixtures",
                    "scannerPolicyVersion": "secret-scan-policy/v1",
                    "candidateTree": "0" * 40,
                    "fixtures": [
                        {
                            "id": "existing-approval",
                            "path": "fixture.py",
                            "line": 1,
                            "field": "token",
                            "rule": "assignment.secret",
                            "digest": digest,
                            "bytes": approved_bytes,
                            "purpose": "synthetic regression fixture",
                            "production": False,
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
        )
        write_graph(
            root,
            graph(
                [
                    output(
                        ".github/linktrend-secret-scan-fixtures.json",
                        [sys.executable, "scripts/gitops/generated_output_closure.py", "--generate-fixtures"],
                        invalidating_sources=["**"],
                        output_id="secret-scan-fixtures",
                    )
                ]
            ),
        )
        commit(root, "stale fixture location")
        _generate_secret_scan_fixtures(root)
        payload = json.loads(
            (root / ".github/linktrend-secret-scan-fixtures.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["fixtures"][0]["line"], 2)
        self.assertEqual(payload["fixtures"][0]["id"], "existing-approval")
        self.assertEqual(len(payload["fixtures"]), 1)

    def test_fixture_generator_relocates_repeated_identity_when_cardinality_is_unchanged(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        approved_bytes = ".".join(("ltfx", "fixture", "repeated", "v1"))
        digest = "sha256:" + hashlib.sha256(approved_bytes.encode("utf-8")).hexdigest()
        write(
            root,
            "fixture.py",
            '# moved\n{} = "{}"\n# moved again\n{} = "{}"\n'.format(
                "to" + "ken", approved_bytes, "to" + "ken", approved_bytes
            ),
        )
        fixtures = []
        for fixture_id, line in (("first", 1), ("second", 2)):
            fixtures.append(
                {
                    "id": fixture_id,
                    "path": "fixture.py",
                    "line": line,
                    "field": "token",
                    "rule": "assignment.secret",
                    "digest": digest,
                    "bytes": approved_bytes,
                    "purpose": "synthetic regression fixture",
                    "production": False,
                }
            )
        write(
            root,
            ".github/linktrend-secret-scan-fixtures.json",
            json.dumps(
                {
                    "schemaVersion": 1,
                    "kind": "secret-scan-fixtures",
                    "scannerPolicyVersion": "secret-scan-policy/v1",
                    "candidateTree": "0" * 40,
                    "fixtures": fixtures,
                },
                indent=2,
            )
            + "\n",
        )
        commit(root, "repeated stale fixture locations")
        _generate_secret_scan_fixtures(root)
        payload = json.loads(
            (root / ".github/linktrend-secret-scan-fixtures.json").read_text(encoding="utf-8")
        )
        self.assertEqual([row["line"] for row in payload["fixtures"]], [2, 4])
        self.assertEqual([row["id"] for row in payload["fixtures"]], ["first", "second"])

    def test_dogfood_and_lean_design_audits_cover_packaged_controls(self) -> None:
        result = audit_dogfood_improvement_closure(ROOT)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "audited")
        self.assertEqual(result["leanDesign"]["mappingCount"], 6)
        self.assertGreaterEqual(result["dogfood"]["executableCommands"], 2)

    def test_top_level_verifier_is_portable_and_does_not_repeat_adoption(self) -> None:
        verify = (ROOT / "scripts/verify-ide-development.sh").read_text(encoding="utf-8")
        lifecycle = (ROOT / "scripts/tests/test-gitops-lifecycle.sh").read_text(encoding="utf-8")
        self.assertIn('mktemp "${TMPDIR:-/tmp}/ide-fast-inventory.XXXXXX"', verify)
        self.assertNotIn("ide-fast-inventory.XXXXXX.json", verify)
        self.assertEqual(verify.count("bash scripts/verify-platform-adoption.sh"), 1)
        self.assertNotIn('bash "$ROOT/scripts/verify-platform-adoption.sh"', lifecycle)

    def test_command_audit_rejects_missing_python_module_reference(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        with self.assertRaisesRegex(ClosureError, "dogfood_command_missing"):
            _audit_command(
                root,
                [
                    "env",
                    "PYTHONPATH=scripts",
                    "python3",
                    "-m",
                    "ide_development.misnamed_build_manifest",
                    "--verify",
                ],
                label="adversarial-command",
            )

    def test_invalidating_source_is_named_and_order_is_deterministic(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        order = root / "order.txt"
        first = script(
            root,
            "first.py",
            "from pathlib import Path\n"
            "Path('order.txt').write_text('first\\n', encoding='utf-8')\n"
            "Path('first.out').write_text('first\\n', encoding='utf-8')\n",
        )
        second = script(
            root,
            "second.py",
            "from pathlib import Path\n"
            "p=Path('order.txt'); p.write_text(p.read_text()+'second\\n', encoding='utf-8')\n"
            "Path('second.out').write_text('second\\n', encoding='utf-8')\n",
        )
        write(root, "source.txt", "source\n")
        write_graph(
            root,
            graph(
                outputs=[
                    output("second.out", second, output_id="second", depends_on=["first"]),
                    output("first.out", first, output_id="first"),
                ]
            ),
        )
        commit(root, "closure graph")
        result = close_generated_outputs(root, graph_path="closure.json")
        self.assertEqual(result["generatorOrder"], ["first", "second"])
        self.assertEqual(order.read_text(encoding="utf-8"), "first\nsecond\n")
        self.assertEqual(result["sourceTree"], candidate_source_tree(root, "closure.json"))
        self.assertEqual(result["invalidatingSources"]["first"], ["source.txt"])
        self.assertEqual(result["invalidatingSources"]["second"], ["source.txt"])

    def test_ambiguous_dependency_and_cycle_fail_closed(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        write_graph(
            root,
            graph(
                outputs=[
                    output("same.out", ["true"], output_id="one"),
                    output("same.out", ["true"], output_id="two"),
                ]
            ),
        )
        with self.assertRaisesRegex(ClosureError, "ambiguous_dependency"):
            load_graph(root, "closure.json")
        write_graph(
            root,
            graph(
                outputs=[
                    output("one.out", ["true"], output_id="one", depends_on=["two"]),
                    output("two.out", ["true"], output_id="two", depends_on=["one"]),
                ]
            ),
        )
        with self.assertRaisesRegex(ClosureError, "ambiguous_dependency"):
            load_graph(root, "closure.json")

    def test_post_generation_source_or_output_mutation_is_rejected(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        generator = script(
            root,
            "generator.py",
            "from pathlib import Path\n"
            "Path('generated.out').write_text('stable\\n', encoding='utf-8')\n",
        )
        write(root, "source.txt", "source\n")
        write_graph(root, graph([output("generated.out", generator)]))
        commit(root, "closure inputs")

        with self.assertRaisesRegex(ClosureError, "post_generation_mutation"):
            close_generated_outputs(
                root,
                graph_path="closure.json",
                post_generation_hook=lambda: write(root, "source.txt", "mutated\n"),
            )
        commit(root, "stable generated output after source rejection")
        write(root, "source.txt", "source\n")
        commit(root, "restore source")
        with self.assertRaisesRegex(ClosureError, "post_generation_mutation"):
            close_generated_outputs(
                root,
                graph_path="closure.json",
                post_generation_hook=lambda: write(root, "generated.out", "tampered\n"),
            )

    def test_non_convergence_and_generator_failure_include_digests(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        toggler = script(
            root,
            "toggle.py",
            "from pathlib import Path\n"
            "p=Path('generated.out'); p.write_text(p.read_text()+'x', encoding='utf-8') if p.exists() else p.write_text('x', encoding='utf-8')\n",
        )
        write(root, "source.txt", "source\n")
        write_graph(root, graph([output("generated.out", toggler)], max_passes=2))
        commit(root, "non-converging generator")
        with self.assertRaisesRegex(ClosureError, "non_convergence"):
            close_generated_outputs(root, graph_path="closure.json")

        git(root, "add", "-A")
        git(root, "commit", "-qm", "record non-converged output")
        failing = script(
            root,
            "failing.py",
            "raise SystemExit('generator boom')\n",
        )
        write_graph(root, graph([output("generated.out", failing)]))
        with self.assertRaisesRegex(ClosureError, "generator_failure") as failure:
            close_generated_outputs(root, graph_path="closure.json")
        self.assertIn("expectedDigest", failure.exception.diagnostics)
        self.assertIn("observedTree", failure.exception.diagnostics)

    def test_dirty_and_stale_output_are_rejected_by_verifier(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        generator = script(
            root,
            "generator.py",
            "from pathlib import Path\n"
            "Path('generated.out').write_text(Path('source.txt').read_text(), encoding='utf-8')\n",
        )
        write(root, "source.txt", "one\n")
        write(root, "generated.out", "one\n")
        write_graph(root, graph([output("generated.out", generator)]))
        commit(root, "clean generated output")
        verify_generated_outputs(root, graph_path="closure.json")

        write(root, "source.txt", "two\n")
        with self.assertRaisesRegex(ClosureError, "stale_output"):
            verify_generated_outputs(root, graph_path="closure.json")

        write(root, "generated.out", "dirty\n")
        with self.assertRaisesRegex(ClosureError, "dirty_output"):
            verify_generated_outputs(root, graph_path="closure.json")

    def test_generated_outputs_are_excluded_from_candidate_tree(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        write(root, "source.txt", "same\n")
        write(root, "generated.out", "first\n")
        write_graph(root, graph([output("generated.out", ["true"])]))
        commit(root, "candidate tree")
        before = candidate_source_tree(root, "closure.json")
        write(root, "generated.out", "second\n")
        git(root, "add", "generated.out")
        after = candidate_source_tree(root, "closure.json")
        self.assertEqual(before, after)

    def test_stale_output_is_rejected_by_installed_pre_push_gate(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        source_root = Path(__file__).resolve().parents[2]
        hook = root / ".githooks" / "pre-push"
        hook.parent.mkdir()
        shutil.copy2(source_root / ".githooks/pre-push", hook)
        runtime = root / "scripts/gitops/generated_output_closure.py"
        runtime.parent.mkdir(parents=True)
        shutil.copy2(source_root / "scripts/gitops/generated_output_closure.py", runtime)
        generator = script(
            root,
            "generator.py",
            "from pathlib import Path\n"
            "Path('generated.out').write_text(Path('source.txt').read_text(), encoding='utf-8')\n",
        )
        write(root, "source.txt", "one\n")
        write(root, "generated.out", "one\n")
        write_graph(root, graph([output("generated.out", generator)], max_passes=2))
        packaged_graph = root / ".ide-development/config/generated-output-closure.json"
        packaged_graph.parent.mkdir(parents=True)
        shutil.copy2(root / "closure.json", packaged_graph)
        commit(root, "installed closure gate")
        baseline = git(root, "rev-parse", "HEAD")
        git(root, "update-ref", "refs/remotes/origin/development", baseline)
        write(root, "candidate.txt", "candidate\n")
        commit(root, "candidate tip")
        git(root, "config", "core.hooksPath", ".githooks")
        passing = subprocess.run(
            [str(hook)],
            cwd=root,
            env={
                **os.environ,
                BASELINE_SHA_ENV: baseline,
                BASELINE_REF_ENV: "origin/development",
            },
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(passing.returncode, 0, passing.stderr)
        write(root, "source.txt", "two \n")
        rejected = subprocess.run(
            [str(hook)],
            cwd=root,
            env={
                **os.environ,
                BASELINE_SHA_ENV: baseline,
                BASELINE_REF_ENV: "origin/development",
            },
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("candidate", (rejected.stderr + rejected.stdout).lower())

    def test_extracted_closure_runtime_operates_without_ide_checkout(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        source_root = Path(__file__).resolve().parents[2]
        runtime = root / "scripts/gitops/generated_output_closure.py"
        runtime.parent.mkdir(parents=True)
        shutil.copy2(source_root / "scripts/gitops/generated_output_closure.py", runtime)
        generator = script(
            root,
            "generator.py",
            "from pathlib import Path\n"
            "Path('generated.out').write_text(Path('source.txt').read_text(), encoding='utf-8')\n",
        )
        write(root, "source.txt", "cleanroom\n")
        write(root, "generated.out", "cleanroom\n")
        write_graph(root, graph([output("generated.out", generator)]))
        packaged_graph = root / ".ide-development/config/generated-output-closure.json"
        packaged_graph.parent.mkdir(parents=True)
        shutil.copy2(root / "closure.json", packaged_graph)
        commit(root, "extracted closure runtime")
        baseline = git(root, "rev-parse", "HEAD")
        git(root, "update-ref", "refs/remotes/origin/development", baseline)
        write(root, "candidate.txt", "candidate\n")
        commit(root, "candidate tip")
        proc = subprocess.run(
            [
                sys.executable,
                str(runtime),
                "--finalize",
                "--baseline-sha",
                baseline,
                "--baseline-ref",
                "origin/development",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
