"""Focused adversarial tests for WP-U10 fixture-aware secret scanning."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.gitops import secret_scan as secret_scan_mod
from scripts.gitops.secret_scan import (
    KIND_APPROVED,
    KIND_CREDENTIAL,
    KIND_SCOPE,
    KIND_STALE,
    RULE_INPUT_TOO_LARGE,
    RULE_INPUT_UNDECODABLE,
    RULE_MALFORMED,
    RULE_REPO_TIMEOUT,
    RULE_FORMAT_SK,
    SCANNER_POLICY_VERSION,
    SYNTHETIC_PREFIX,
    candidate_content_tree,
    digest_bytes,
    identify_synthetic_candidates,
    scan_repository,
)
from scripts.ide_development.constants import RC_REQUIRED_SCHEMA_RELS

ROOT = Path(__file__).resolve().parents[2]
SECRET_SCAN = ROOT / "scripts" / "gitops" / "secret_scan.py"
MIGRATE = ROOT / "scripts" / "gitops" / "secret_scan_migrate.py"
FIXTURE_SCHEMA = ROOT / "core" / "managed-core" / "schemas" / "secret-scan-fixtures.schema.json"
RESULT_SCHEMA = ROOT / "core" / "managed-core" / "schemas" / "secret-scan-result.schema.json"


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def sha(root: Path, spec: str = "HEAD") -> str:
    return git(root, "rev-parse", spec)


def tree(root: Path, spec: str = "HEAD^{tree}") -> str:
    return git(root, "rev-parse", spec)


def init_repo() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name) / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "development")
    git(root, "config", "user.email", "u10@example.invalid")
    git(root, "config", "user.name", "WP-U10 tests")
    git(root, "config", "core.autocrlf", "false")
    (root / "README.md").write_text("# fixture-aware secret scan\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-qm", "base")
    return tmp, root


def write_tracked(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    git(root, "add", "--", rel)


def write_tracked_bytes(root: Path, rel: str, raw: bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    git(root, "add", "--", rel)


def commit(root: Path, message: str) -> tuple[str, str]:
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)
    return sha(root), tree(root)


def synthetic_value(name: str = "integrity-secret-property") -> str:
    return f"{SYNTHETIC_PREFIX}{name}.v1"


def value_digest(value: str) -> str:
    return digest_bytes(value.encode("utf-8"))


def declaration(
    *,
    candidate_tree: str,
    fixtures: list[dict],
    policy: str = SCANNER_POLICY_VERSION,
) -> dict:
    return {
        "schemaVersion": 1,
        "kind": "secret-scan-fixtures",
        "scannerPolicyVersion": policy,
        "candidateTree": candidate_tree,
        "fixtures": fixtures,
    }


def fixture(
    *,
    fixture_id: str,
    path: str,
    line: int,
    field: str,
    rule: str,
    value: str,
    purpose: str = "negative integrity test for a synthetic secret property",
) -> dict:
    return {
        "id": fixture_id,
        "path": path,
        "line": line,
        "field": field,
        "rule": rule,
        "digest": value_digest(value),
        "purpose": purpose,
        "production": False,
    }


def write_declaration(root: Path, payload: dict, rel: str = ".github/linktrend-secret-scan-fixtures.json") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    git(root, "add", rel)
    return path


def kinds(result: dict) -> list[str]:
    return [row["kind"] for row in result["findings"]]


def by_kind(result: dict, kind: str) -> list[dict]:
    return [row for row in result["findings"] if row["kind"] == kind]


class PackagingContractTests(unittest.TestCase):
    def test_schemas_index_manifest_and_fast_cover_scanner(self) -> None:
        index = (ROOT / "core/managed-core/INDEX.yaml").read_text(encoding="utf-8")
        self.assertTrue(FIXTURE_SCHEMA.is_file())
        self.assertTrue(RESULT_SCHEMA.is_file())
        self.assertIn("schemas/secret-scan-fixtures.schema.json", index)
        self.assertIn("schemas/secret-scan-result.schema.json", index)
        self.assertIn("core/managed-core/schemas/secret-scan-fixtures.schema.json", RC_REQUIRED_SCHEMA_RELS)
        self.assertIn("core/managed-core/schemas/secret-scan-result.schema.json", RC_REQUIRED_SCHEMA_RELS)
        fixtures = json.loads(FIXTURE_SCHEMA.read_text(encoding="utf-8"))
        result = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(fixtures["properties"]["kind"]["const"], "secret-scan-fixtures")
        self.assertEqual(result["properties"]["kind"]["const"], "secret-scan-result")
        fixtures_array = fixtures["properties"]["fixtures"]
        self.assertEqual(fixtures_array.get("x-uniqueItemFields"), ["id"])
        self.assertIn("unique", fixtures_array["items"]["properties"]["id"]["description"].lower())
        for required in (
            "schemaVersion",
            "kind",
            "scannerPolicyVersion",
            "candidateTree",
            "fixtures",
        ):
            self.assertIn(required, fixtures["required"])
        for required in (
            "schemaVersion",
            "kind",
            "scannerPolicyVersion",
            "candidateTree",
            "ok",
            "findings",
        ):
            self.assertIn(required, result["required"])
        manifest = json.loads((ROOT / "core/managed-core/MANIFEST.json").read_text(encoding="utf-8"))
        sources = {row["source"] for row in manifest["files"]}
        self.assertIn("core/managed-core/schemas/secret-scan-fixtures.schema.json", sources)
        self.assertIn("core/managed-core/schemas/secret-scan-result.schema.json", sources)
        self.assertIn("scripts/gitops/secret_scan.py", sources)
        self.assertIn("scripts/gitops/secret_scan_migrate.py", sources)
        self.assertIn("scripts/tests/test_fixture_aware_secret_scan.py", sources)
        runtime = json.loads((ROOT / "core/github/managed-runtime/MANIFEST.json").read_text(encoding="utf-8"))
        self.assertIn("scripts/gitops/secret_scan.py", runtime["files"])
        self.assertIn("scripts/gitops/secret_scan_migrate.py", runtime["files"])
        live = ["python3", "scripts/gitops/secret_scan.py"]
        fast = json.loads((ROOT / ".github/linktrend-delivery-mode.json").read_text(encoding="utf-8"))
        self.assertIn(live, fast["profiles"]["fast"]["commands"])
        self.assertIn(live, fast["profiles"]["full"]["commands"])
        self.assertIn("test_fixture_aware_secret_scan", json.dumps(fast["profiles"]))
        managed = json.loads((ROOT / "core/managed-core/config/delivery.json").read_text(encoding="utf-8"))
        self.assertIn(live, managed["profiles"]["fast"]["commands"])
        self.assertIn(live, managed["profiles"]["full"]["commands"])

    def test_doctrine_and_installer_docs_name_fixture_contract(self) -> None:
        contract = (ROOT / "docs/contracts/SECRET-SCAN-FIXTURES.md").read_text(encoding="utf-8")
        delivery = (ROOT / "docs/contracts/DELIVERY-MODES.md").read_text(encoding="utf-8")
        streamlined = (ROOT / "docs/contracts/STREAMLINED-DELIVERY.md").read_text(encoding="utf-8")
        self.assertIn("approved_synthetic_fixture", contract)
        self.assertIn("never auto-approve", contract)
        self.assertIn("duplicate fixture ids", contract)
        self.assertIn("secret_scan.py", delivery)
        self.assertIn("fixture-aware secret scanning", streamlined.lower())


class AcU1001SyntheticLiteralTests(unittest.TestCase):
    def test_declared_synthetic_assignment_passes_without_syntax_evasion(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        value = synthetic_value()
        write_tracked(
            root,
            "tests/security/test_integrity.py",
            f'sample = {{"secret": "{value}"}}\n',
        )
        commit(root, "add synthetic integrity fixture")
        write_declaration(
            root,
            declaration(
                candidate_tree=candidate_content_tree(root),
                fixtures=[
                    fixture(
                        fixture_id="integrity-secret-property",
                        path="tests/security/test_integrity.py",
                        line=1,
                        field="secret",
                        rule="assignment.secret",
                        value=value,
                    )
                ],
            ),
        )
        commit(root, "declare exact synthetic fixture")
        result = scan_repository(root)
        self.assertTrue(result["ok"], result)
        self.assertEqual(kinds(result), [KIND_APPROVED])
        approved = result["findings"][0]
        self.assertEqual(approved["path"], "tests/security/test_integrity.py")
        self.assertEqual(approved["line"], 1)
        self.assertEqual(approved["field"], "secret")
        self.assertEqual(approved["digest"], value_digest(value))
        self.assertEqual(approved["rule"], "assignment.secret")


class AcU1004ExactScopeTests(unittest.TestCase):
    def test_same_bytes_in_other_file_line_field_or_production_path_fail(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        value = synthetic_value()
        write_tracked(root, "tests/security/other.py", f'secret = "{value}"\n')
        write_tracked(
            root,
            "src/app.py",
            f'token = "unused"\nsecret = "{value}"\nconfig = {{"api_key": "{value}"}}\n',
        )
        write_tracked(
            root,
            "tests/security/test_integrity.py",
            f'secret = "{value}"\nshadow = "{value}"\n',
        )
        commit(root, "place same bytes in several locations")
        write_declaration(
            root,
            declaration(
                candidate_tree=candidate_content_tree(root),
                fixtures=[
                    fixture(
                        fixture_id="integrity-secret-property",
                        path="tests/security/test_integrity.py",
                        line=1,
                        field="secret",
                        rule="assignment.secret",
                        value=value,
                    )
                ],
            ),
        )
        commit(root, "declare only the first test assignment")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        approved = by_kind(result, KIND_APPROVED)
        self.assertEqual(len(approved), 1)
        self.assertEqual(approved[0]["line"], 1)
        self.assertEqual(approved[0]["field"], "secret")
        blocking = [row for row in result["findings"] if row["kind"] != KIND_APPROVED]
        locations = {(row["path"], row["line"], row["field"]) for row in blocking}
        self.assertIn(("tests/security/other.py", 1, "secret"), locations)
        self.assertIn(("tests/security/test_integrity.py", 2, "shadow"), locations)
        self.assertTrue(any(row["path"] == "src/app.py" for row in blocking))


class AcU1005FailClosedTests(unittest.TestCase):
    def _declared_repo(self, value: str | None = None) -> tuple[tempfile.TemporaryDirectory[str], Path, str]:
        tmp, root = init_repo()
        value = value or synthetic_value()
        write_tracked(root, "tests/security/test_integrity.py", f'secret = "{value}"\n')
        commit(root, "synthetic fixture")
        write_declaration(
            root,
            declaration(
                candidate_tree=candidate_content_tree(root),
                fixtures=[
                    fixture(
                        fixture_id="integrity-secret-property",
                        path="tests/security/test_integrity.py",
                        line=1,
                        field="secret",
                        rule="assignment.secret",
                        value=value,
                    )
                ],
            ),
        )
        commit(root, "declare fixture")
        return tmp, root, value

    def test_one_byte_change_fails_closed(self) -> None:
        tmp, root, value = self._declared_repo()
        self.addCleanup(tmp.cleanup)
        mutated = value[:-1] + ("0" if value[-1] != "0" else "1")
        write_tracked(root, "tests/security/test_integrity.py", f'secret = "{mutated}"\n')
        commit(root, "one-byte fixture change")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any(row["kind"] in {KIND_STALE, KIND_SCOPE, KIND_CREDENTIAL} for row in result["findings"]))

    def test_stale_digest_fails_closed(self) -> None:
        tmp, root, value = self._declared_repo()
        self.addCleanup(tmp.cleanup)
        payload = json.loads((root / ".github/linktrend-secret-scan-fixtures.json").read_text(encoding="utf-8"))
        payload["fixtures"][0]["digest"] = value_digest(value + "x")
        write_declaration(root, payload)
        commit(root, "stale digest")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any(row["kind"] == KIND_STALE for row in result["findings"]))

    def test_renamed_file_fails_closed(self) -> None:
        tmp, root, _value = self._declared_repo()
        self.addCleanup(tmp.cleanup)
        git(root, "mv", "tests/security/test_integrity.py", "tests/security/renamed.py")
        commit(root, "rename fixture file")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any(
                row["kind"] in {KIND_STALE, KIND_SCOPE, KIND_CREDENTIAL}
                and "renamed.py" in row["path"]
                for row in result["findings"]
            )
        )

    def test_duplicated_value_fails_closed(self) -> None:
        tmp, root, value = self._declared_repo()
        self.addCleanup(tmp.cleanup)
        write_tracked(root, "tests/security/copy.py", f'secret = "{value}"\n')
        commit(root, "duplicate fixture bytes")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any(row["path"] == "tests/security/copy.py" for row in result["findings"]))

    def test_duplicate_fixture_ids_cannot_hide_stale_declaration(self) -> None:
        """Duplicate ids must not suppress unused_or_stale_declaration via used-by-id."""
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        good = synthetic_value("good")
        stale = synthetic_value("stale")
        write_tracked(root, "tests/security/good.py", f'secret = "{good}"\n')
        write_tracked(root, "tests/security/stale.py", "print('no secret')\n")
        commit(root, "used fixture plus unused stale path")
        write_declaration(
            root,
            declaration(
                candidate_tree=candidate_content_tree(root),
                fixtures=[
                    fixture(
                        fixture_id="shared-id",
                        path="tests/security/good.py",
                        line=1,
                        field="secret",
                        rule="assignment.secret",
                        value=good,
                    ),
                    fixture(
                        fixture_id="shared-id",
                        path="tests/security/stale.py",
                        line=1,
                        field="secret",
                        rule="assignment.secret",
                        value=stale,
                    ),
                ],
            ),
        )
        commit(root, "duplicate fixture ids")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any(row["rule"] == RULE_MALFORMED for row in result["findings"]))
        self.assertNotEqual(kinds(result), [KIND_APPROVED])
        self.assertFalse(
            any(row["kind"] == KIND_APPROVED for row in result["findings"]),
            "duplicate ids must fail closed before approval tracking can mask stale rows",
        )

    def test_unknown_rule_fails_closed(self) -> None:
        tmp, root, value = self._declared_repo()
        self.addCleanup(tmp.cleanup)
        payload = json.loads((root / ".github/linktrend-secret-scan-fixtures.json").read_text(encoding="utf-8"))
        payload["fixtures"][0]["rule"] = "unknown.rule"
        write_declaration(root, payload)
        commit(root, "unknown rule")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any(row["kind"] in {KIND_STALE, KIND_SCOPE} for row in result["findings"]))

    def test_undeclared_fixture_fails_closed(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        write_tracked(root, "tests/security/test_integrity.py", f'secret = "{synthetic_value()}"\n')
        commit(root, "undeclared synthetic")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any(row["kind"] == KIND_CREDENTIAL for row in result["findings"]))


class AcU1006RealisticFormatsTests(unittest.TestCase):
    def test_realistic_formats_cannot_be_approved(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        github = "ghp_" + ("A" * 36)
        cloud = "AKIA" + ("B" * 16)
        database = "postgres://" + "user:SuperSecretPassw0rd@db.example.invalid:5432/app"
        pem = "-----BEGIN RSA " + "PRIVATE KEY-----\nMIIEowIBAAKCAQEA" + ("C" * 40) + "\n-----END RSA " + "PRIVATE KEY-----\n"
        entropy = hashlib.sha256(b"live-token").hexdigest() + hashlib.sha256(b"more").hexdigest()
        samples = {
            "github.py": f'token = "{github}"\n',
            "cloud.py": f'key = "{cloud}"\n',
            "database.py": f'url = "{database}"\n',
            "private_key.pem": pem,
            "entropy.py": f'token = "{entropy}"\n',
        }
        for rel, text in samples.items():
            write_tracked(root, f"tests/security/{rel}", text)
        commit(root, "realistic samples")
        fixtures = []
        for rel, sample_text in samples.items():
            path = f"tests/security/{rel}"
            if "token" in sample_text or "PRIVATE" in sample_text:
                field_name = "token"
            elif "key =" in sample_text:
                field_name = "key"
            else:
                field_name = "url"
            fixtures.append(
                {
                    "id": rel.replace(".", "-"),
                    "path": path,
                    "line": 1,
                    "field": field_name,
                    "rule": "assignment.secret",
                    "digest": value_digest("ignored"),
                    "purpose": "attempt to approve a realistic credential",
                    "production": False,
                }
            )
        write_declaration(root, declaration(candidate_tree=candidate_content_tree(root), fixtures=fixtures))
        commit(root, "attempt realistic approvals")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        self.assertFalse(any(row["kind"] == KIND_APPROVED for row in result["findings"]))
        paths = {row["path"] for row in result["findings"] if row["kind"] == KIND_CREDENTIAL}
        for rel in samples:
            self.assertIn(f"tests/security/{rel}", paths)


class AcU1007AggregationTests(unittest.TestCase):
    def test_one_run_reports_all_findings_and_fixture_errors(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        good = synthetic_value("good")
        stale = synthetic_value("stale")
        write_tracked(root, "tests/security/good.py", f'secret = "{good}"\n')
        write_tracked(root, "tests/security/stale.py", f'secret = "{stale}"\n')
        write_tracked(root, "src/prod.py", f'secret = "{synthetic_value("prod")}"\n')
        commit(root, "several findings")
        write_declaration(
            root,
            declaration(
                candidate_tree=candidate_content_tree(root),
                fixtures=[
                    fixture(
                        fixture_id="good",
                        path="tests/security/good.py",
                        line=1,
                        field="secret",
                        rule="assignment.secret",
                        value=good,
                    ),
                    fixture(
                        fixture_id="stale",
                        path="tests/security/stale.py",
                        line=1,
                        field="secret",
                        rule="assignment.secret",
                        value=stale + "-old",
                    ),
                ],
            ),
        )
        commit(root, "mixed declarations")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        found_kinds = set(kinds(result))
        self.assertIn(KIND_APPROVED, found_kinds)
        self.assertTrue({KIND_STALE, KIND_SCOPE, KIND_CREDENTIAL} & found_kinds)
        self.assertGreaterEqual(len(result["findings"]), 3)


class AcU1008BindingTests(unittest.TestCase):
    def test_tree_or_policy_change_invalidates_until_refresh(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        value = synthetic_value()
        write_tracked(root, "tests/security/test_integrity.py", f'secret = "{value}"\n')
        commit(root, "fixture")
        payload = declaration(
            candidate_tree=candidate_content_tree(root),
            fixtures=[
                fixture(
                    fixture_id="integrity-secret-property",
                    path="tests/security/test_integrity.py",
                    line=1,
                    field="secret",
                    rule="assignment.secret",
                    value=value,
                )
            ],
        )
        write_declaration(root, payload)
        commit(root, "declare")
        write_tracked(root, "README.md", "# changed tree\n")
        commit(root, "unrelated tree change")
        stale_tree = scan_repository(root)
        self.assertFalse(stale_tree["ok"])
        self.assertTrue(any(row["kind"] == KIND_STALE for row in stale_tree["findings"]))

        payload["scannerPolicyVersion"] = "secret-scan-policy/not-this"
        payload["candidateTree"] = candidate_content_tree(root)
        write_declaration(root, payload)
        commit(root, "refresh tree but wrong policy")
        stale_policy = scan_repository(root)
        self.assertFalse(stale_policy["ok"])
        self.assertTrue(any(row["kind"] == KIND_STALE for row in stale_policy["findings"]))

        payload["scannerPolicyVersion"] = SCANNER_POLICY_VERSION
        payload["candidateTree"] = candidate_content_tree(root)
        write_declaration(root, payload)
        commit(root, "intentional refresh")
        refreshed = scan_repository(root)
        self.assertTrue(refreshed["ok"], refreshed)
        self.assertEqual(kinds(refreshed), [KIND_APPROVED])


class AcU1002NoBlindSpotTests(unittest.TestCase):
    def test_production_path_and_test_directory_are_both_scanned(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        write_tracked(root, "src/prod.py", f'secret = "{synthetic_value("prod")}"\n')
        write_tracked(root, "tests/unit/test_app.py", f'secret = "{synthetic_value("test")}"\n')
        commit(root, "undeclared in prod and tests")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        paths = {row["path"] for row in result["findings"]}
        self.assertIn("src/prod.py", paths)
        self.assertIn("tests/unit/test_app.py", paths)

    def test_missing_or_malformed_declaration_fails_closed(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        write_tracked(root, "tests/security/test_integrity.py", f'secret = "{synthetic_value()}"\n')
        commit(root, "no declaration file")
        missing = scan_repository(root)
        self.assertFalse(missing["ok"])
        write_tracked(root, ".github/linktrend-secret-scan-fixtures.json", "{not-json\n")
        commit(root, "malformed declaration")
        malformed = scan_repository(root)
        self.assertFalse(malformed["ok"])
        self.assertEqual(malformed["kind"], "secret-scan-result")
        self.assertTrue(any(row["rule"] == RULE_MALFORMED for row in malformed["findings"]))


class AcU1009RepositoryScannersTests(unittest.TestCase):
    def test_repository_owned_scanner_failure_remains_blocking(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        value = synthetic_value()
        write_tracked(root, "tests/security/test_integrity.py", f'secret = "{value}"\n')
        blocker = root / "repo-scanner.sh"
        blocker.write_text("#!/bin/sh\necho repo-owned-finding\nexit 2\n", encoding="utf-8")
        blocker.chmod(0o755)
        write_tracked(
            root,
            ".github/linktrend-repository-secret-scanners.json",
            json.dumps(
                {
                    "schemaVersion": 1,
                    "scanners": [
                        {"id": "repo-gitleaks", "command": ["./repo-scanner.sh"]}
                    ],
                }
            )
            + "\n",
        )
        git(root, "add", "repo-scanner.sh")
        commit(root, "synthetic and repo scanner")
        write_declaration(
            root,
            declaration(
                candidate_tree=candidate_content_tree(root),
                fixtures=[
                    fixture(
                        fixture_id="integrity-secret-property",
                        path="tests/security/test_integrity.py",
                        line=1,
                        field="secret",
                        rule="assignment.secret",
                        value=value,
                    )
                ],
            ),
        )
        commit(root, "declare fixture")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any(row.get("scannerId") == "repo-gitleaks" for row in result["findings"]))
        self.assertTrue(any(row["kind"] == KIND_APPROVED for row in result["findings"]))

    def test_fixture_declaration_cannot_suppress_repository_scanner(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        write_tracked(root, "README.md", "# still clean managed scan\n")
        commit(root, "clean")
        blocker = root / "repo-scanner.sh"
        blocker.write_text("#!/bin/sh\nexit 3\n", encoding="utf-8")
        blocker.chmod(0o755)
        write_tracked(
            root,
            ".github/linktrend-repository-secret-scanners.json",
            json.dumps(
                {
                    "schemaVersion": 1,
                    "scanners": [{"id": "codeql", "command": ["./repo-scanner.sh"]}],
                }
            )
            + "\n",
        )
        git(root, "add", "repo-scanner.sh")
        commit(root, "repo scanner only")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any(row.get("scannerId") == "codeql" for row in result["findings"]))


class AcU1003MigrationHelperTests(unittest.TestCase):
    def test_migration_identifies_candidates_and_never_writes_approval(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        value = synthetic_value("migrate")
        write_tracked(root, "tests/security/test_integrity.py", f'secret = "{value}"\n')
        commit(root, "candidate")
        before = list((root / ".github").glob("*")) if (root / ".github").exists() else []
        candidates = identify_synthetic_candidates(root)
        self.assertTrue(candidates)
        self.assertTrue(any(row["path"] == "tests/security/test_integrity.py" for row in candidates))
        self.assertFalse((root / ".github/linktrend-secret-scan-fixtures.json").exists())
        after = list((root / ".github").glob("*")) if (root / ".github").exists() else []
        self.assertEqual(before, after)
        proc = subprocess.run(
            ["python3", str(MIGRATE), "--repo", str(root)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload.get("approved"))
        self.assertTrue(payload["candidates"])
        self.assertFalse((root / ".github/linktrend-secret-scan-fixtures.json").exists())


class CliAggregationTests(unittest.TestCase):
    def test_cli_writes_aggregate_result_and_nonzero_on_findings(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        write_tracked(root, "src/app.py", f'secret = "{synthetic_value("cli")}"\n')
        commit(root, "undeclared")
        out = root / "scan.json"
        proc = subprocess.run(
            ["python3", str(SECRET_SCAN), "--repo", str(root), "--json-output", str(out)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(payload["kind"], "secret-scan-result")
        self.assertFalse(payload["ok"])
        self.assertGreaterEqual(len(payload["findings"]), 1)


class AdversarialRepairTests(unittest.TestCase):
    def test_directory_symlink_and_option_like_path_use_index_identities(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        (root / "core").mkdir()
        (root / "core" / "agents").mkdir()
        write_tracked(root, "core/agents/README.md", "# agents\n")
        (root / ".cursor").mkdir()
        os.symlink("../core/agents", root / ".cursor" / "agents")
        git(root, "add", "--", ".cursor/agents")
        github = "ghp_" + ("A" * 36)
        write_tracked(root, "--secret-file.py", f'token = "{github}"\n')
        commit(root, "symlink and option-like path")
        tree = candidate_content_tree(root)
        self.assertEqual(len(tree), 40)
        result = scan_repository(root)
        self.assertEqual(result["kind"], "secret-scan-result")
        self.assertFalse(result["ok"])
        self.assertFalse(any(row["rule"] == "git.failed" for row in result["findings"]))
        self.assertTrue(any(row["path"] == "--secret-file.py" and row["kind"] == KIND_CREDENTIAL for row in result["findings"]))

    def test_suffix_named_text_and_utf16_are_scanned(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        github = "ghp_" + ("B" * 36)
        write_tracked(root, "secrets.png", f'token = "{github}"\n')
        pem_header = "-----BEGIN RSA " + "PRIVATE KEY-----\n"
        write_tracked(root, "keys.pdf", pem_header)
        utf16 = f'secret = "{synthetic_value("utf16")}"\n'.encode("utf-16-le")
        write_tracked_bytes(root, "utf16-le.env", utf16)
        utf16_be = ('token = "' + github + '"\n').encode("utf-16-be")
        write_tracked_bytes(root, "utf16-be.yml", utf16_be)
        commit(root, "suffix and utf-16")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        paths = {row["path"] for row in result["findings"] if row["kind"] == KIND_CREDENTIAL}
        self.assertIn("secrets.png", paths)
        self.assertIn("keys.pdf", paths)
        self.assertIn("utf16-le.env", paths)
        self.assertIn("utf16-be.yml", paths)

    def test_declaration_bytes_and_notes_cannot_hide_credentials(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        value = synthetic_value()
        github = "ghp_" + ("C" * 36)
        write_tracked(root, "tests/security/test_integrity.py", f'secret = "{value}"\n')
        commit(root, "fixture")
        payload = declaration(
            candidate_tree=candidate_content_tree(root),
            fixtures=[
                fixture(
                    fixture_id="integrity-secret-property",
                    path="tests/security/test_integrity.py",
                    line=1,
                    field="secret",
                    rule="assignment.secret",
                    value=value,
                )
            ],
        )
        payload["fixtures"][0]["bytes"] = github
        payload["fixtures"][0]["note"] = f'token = "{github}"'
        write_declaration(root, payload)
        commit(root, "declaration with hidden credential")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["kind"], "secret-scan-result")
        self.assertTrue(any(row["path"] == ".github/linktrend-secret-scan-fixtures.json" for row in result["findings"]))
        self.assertFalse(
            any(
                row["kind"] == KIND_APPROVED and row["path"] == ".github/linktrend-secret-scan-fixtures.json"
                for row in result["findings"]
            )
        )

    def test_unquoted_env_yaml_short_and_escaped_secrets(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        entropy = hashlib.sha256(b"live-token").hexdigest()
        openai = "sk-" + "proj-abcdefghijklmnopqrstuv"
        short = "short" + "value1"
        escaped_body = "foo\\" + "bar-extra-long"
        concat_left, concat_right = "foo", "bar-extra-long"
        write_tracked(root, "src/app.py", f"token={entropy}\n")
        write_tracked(root, "config.yml", f"password: {entropy}\n")
        write_tracked(root, ".env", f"OPENAI_API_KEY={openai}\n")
        write_tracked(root, "short.py", f'key = "{short}"\n')
        write_tracked(root, "escaped.py", f'secret = "{escaped_body}"\n')
        write_tracked(root, "concat.py", f'secret = "{concat_left}" + "{concat_right}"\n')
        commit(root, "unquoted short escaped")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        paths = {row["path"] for row in result["findings"] if row["kind"] == KIND_CREDENTIAL}
        self.assertIn("src/app.py", paths)
        self.assertIn("config.yml", paths)
        self.assertIn(".env", paths)
        self.assertIn("short.py", paths)
        self.assertIn("escaped.py", paths)
        self.assertIn("concat.py", paths)
        self.assertTrue(any(row["rule"] == RULE_FORMAT_SK for row in result["findings"]))

    def test_huge_input_and_scanner_timeout_are_typed_results(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        write_tracked(root, "huge.txt", "x" * 200)
        blocker = root / "slow.sh"
        blocker.write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
        blocker.chmod(0o755)
        write_tracked(
            root,
            ".github/linktrend-repository-secret-scanners.json",
            json.dumps({"schemaVersion": 1, "scanners": [{"id": "slow", "command": ["./slow.sh"]}]}) + "\n",
        )
        git(root, "add", "--", "slow.sh")
        commit(root, "huge and slow")
        with patch.object(secret_scan_mod, "MAX_FILE_BYTES", 64), patch.object(
            secret_scan_mod, "REPO_SCANNER_TIMEOUT_SEC", 0.2
        ):
            result = scan_repository(root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["kind"], "secret-scan-result")
        self.assertTrue(any(row["rule"] == RULE_INPUT_TOO_LARGE and row["path"] == "huge.txt" for row in result["findings"]))
        self.assertTrue(any(row["rule"] == RULE_REPO_TIMEOUT and row.get("scannerId") == "slow" for row in result["findings"]))

    def test_schema_extras_and_typed_failures_match_result_schema(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        write_tracked(root, "tests/security/test_integrity.py", f'secret = "{synthetic_value()}"\n')
        commit(root, "undeclared")
        extra = declaration(
            candidate_tree=candidate_content_tree(root),
            fixtures=[
                fixture(
                    fixture_id="integrity-secret-property",
                    path="tests/security/test_integrity.py",
                    line=1,
                    field="secret",
                    rule="assignment.secret",
                    value=synthetic_value(),
                )
            ],
        )
        extra["unexpected"] = True
        extra["fixtures"][0]["extra"] = "nope"
        write_declaration(root, extra)
        commit(root, "schema extras")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["kind"], "secret-scan-result")
        self.assertIn("schemaVersion", result)
        self.assertIn("candidateTree", result)
        self.assertTrue(any(row["rule"] == RULE_MALFORMED for row in result["findings"]))
        schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["kind"]["const"], "secret-scan-result")
        self.assertFalse(schema["additionalProperties"])
        for key in ("schemaVersion", "kind", "scannerPolicyVersion", "candidateTree", "ok", "findings"):
            self.assertIn(key, result)

    def test_undecodable_nul_content_fails_closed(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        write_tracked_bytes(root, "opaque.bin", b"\x00\x01\x02\x00secret-not-decoded")
        commit(root, "undecodable")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any(row["rule"] == RULE_INPUT_UNDECODABLE and row["path"] == "opaque.bin" for row in result["findings"]))

    def test_bound_bytes_must_match_detected_value(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        value = synthetic_value()
        write_tracked(root, "tests/security/test_integrity.py", f'secret = "{value}"\n')
        commit(root, "fixture")
        payload = declaration(
            candidate_tree=candidate_content_tree(root),
            fixtures=[
                fixture(
                    fixture_id="integrity-secret-property",
                    path="tests/security/test_integrity.py",
                    line=1,
                    field="secret",
                    rule="assignment.secret",
                    value=value,
                )
            ],
        )
        payload["fixtures"][0]["bytes"] = value + "-mismatch"
        write_declaration(root, payload)
        commit(root, "mismatched bytes")
        result = scan_repository(root)
        self.assertFalse(result["ok"])
        self.assertFalse(any(row["kind"] == KIND_APPROVED for row in result["findings"]))

    def test_matching_bytes_still_approve_synthetic_only(self) -> None:
        tmp, root = init_repo()
        self.addCleanup(tmp.cleanup)
        value = synthetic_value()
        write_tracked(root, "tests/security/test_integrity.py", f'secret = "{value}"\n')
        commit(root, "fixture")
        payload = declaration(
            candidate_tree=candidate_content_tree(root),
            fixtures=[
                fixture(
                    fixture_id="integrity-secret-property",
                    path="tests/security/test_integrity.py",
                    line=1,
                    field="secret",
                    rule="assignment.secret",
                    value=value,
                )
            ],
        )
        payload["fixtures"][0]["bytes"] = value
        write_declaration(root, payload)
        commit(root, "bound bytes")
        result = scan_repository(root)
        self.assertTrue(result["ok"], result)
        self.assertEqual(kinds(result), [KIND_APPROVED])


if __name__ == "__main__":
    unittest.main()
