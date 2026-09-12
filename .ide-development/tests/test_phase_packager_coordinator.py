"""WP-U03 Phase Packager/Coordinator unit, negative, and contract tests."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, RefResolver

from scripts.gitops import packager_coordinator as coordinator
from scripts.ide_development.constants import RC_REQUIRED_SCHEMA_RELS


ROOT = Path(__file__).resolve().parents[2]
INSTALLED_HANDOFF_SCHEMA = ROOT / ".ide-development/schemas/phase-handoff.schema.json"
INSTALLED_RECORD_SCHEMA = ROOT / ".ide-development/schemas/phase-record.schema.json"
INSTALLED_FAST_WORKFLOW = ROOT / ".ide-development/workflows/linktrend-review-packager.yml"
LIVE_FAST_WORKFLOW = ROOT / ".github/workflows/linktrend-review-packager.yml"
LIVE_FULL_WORKFLOW = ROOT / ".github/workflows/linktrend-integrator-merge.yml"


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)
    if check and result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return (result.stdout or "").strip()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def remote_sha(repo: Path, branch: str) -> str:
    output = git(repo, "ls-remote", "--heads", "origin", f"refs/heads/{branch}", check=False)
    if not output:
        return ""
    return output.split()[0]


class Fixture:
    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.origin = root / "origin.git"
        self.work = root / "work"
        self.work.mkdir()
        git(root, "init", "--bare", str(self.origin))
        git(self.work, "init", "-q", "-b", "development")
        git(self.work, "config", "user.email", "packager@example.invalid")
        git(self.work, "config", "user.name", "Phase Packager tests")
        git(self.work, "remote", "add", "origin", str(self.origin))
        write(self.work / "base.txt", "base\n")
        git(self.work, "add", "base.txt")
        git(self.work, "commit", "-qm", "base")
        git(self.work, "push", "-q", "-u", "origin", "development")
        self.github = coordinator.MemoryGitHub(repository="owner/name")

    def cleanup(self) -> None:
        self.tmp.cleanup()

    def development_sha(self) -> str:
        return git(self.work, "rev-parse", "origin/development")

    def accept_issue(self, number: int, filename: str, content: str, *, ready: bool = True) -> coordinator.AcceptedSource:
        branch = f"issue/{number}-{filename.split('.')[0]}"
        git(self.work, "checkout", "-B", branch, "development")
        write(self.work / filename, content)
        git(self.work, "add", filename)
        git(self.work, "commit", "-qm", f"issue {number}")
        sha = git(self.work, "rev-parse", "HEAD")
        git(self.work, "push", "-q", "-u", "origin", branch)
        git(self.work, "checkout", "development")
        source = coordinator.AcceptedSource(branch=branch, sha=sha, order=number)
        if ready:
            self.github.ready_shas.add(sha)
            self.github.evidence[sha] = {"schemaVersion": 1, "headSha": sha, "classification": "tests"}
        return source

    def assemble(self, sources: list[coordinator.AcceptedSource], **kwargs):
        ordered = [
            coordinator.AcceptedSource(branch=item.branch, sha=item.sha, order=index)
            for index, item in enumerate(sources, start=1)
        ]
        return coordinator.assemble_phase(
            repo=self.work,
            repository="owner/name",
            sources=ordered,
            github=kwargs.get("github", self.github),
            pusher=kwargs.get("pusher", coordinator.GitPushAdapter()),
            phase_branch=kwargs.get("phase_branch", "phase/next"),
            require_evidence=kwargs.get("require_evidence", True),
            expected_repository=kwargs.get("expected_repository", "owner/name"),
            require_live_pr=kwargs.get("require_live_pr", False),
            evidence_payloads=kwargs.get("evidence_payloads"),
            provider_consumer_handoff=kwargs.get("provider_consumer_handoff"),
        )


class PhasePackagerCoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)

    def test_discover_is_not_phase_packager(self) -> None:
        with self.assertRaises(ImportError):
            from scripts.gitops import packager_discover as _discover  # noqa: F401
        self.assertTrue(coordinator.IS_PHASE_PACKAGER)
        self.assertIn("not this component", coordinator.__doc__)

    def test_one_issue_creates_one_phase_branch_and_draft_pr(self) -> None:
        one = self.fx.accept_issue(11, "alpha.txt", "alpha\n")
        result = self.fx.assemble([one])
        self.assertEqual(result["action"], "created")
        self.assertEqual(result["phaseBranch"], "phase/next")
        self.assertEqual(result["phasePr"]["number"], 1)
        self.assertTrue(result["phasePr"]["isDraft"])
        self.assertEqual(len(self.fx.github.prs), 1)
        self.assertEqual(git(self.fx.work, "rev-parse", "--abbrev-ref", "HEAD"), "development")
        self.assertEqual(remote_sha(self.fx.work, "phase/next"), result["headSha"])
        self.assertEqual(result["remoteSha"], result["headSha"])
        git(self.fx.work, "cat-file", "-e", f"{result['headSha']}:alpha.txt")
        self.assertEqual(result["acceptedCommits"][0]["sha"], one.sha)
        self.assertFalse(result["record"]["sealed"])
        self.assertFalse(result["fullDispatchAllowed"])
        self._assert_published_phase_pr_identity(result, number=1)

    def _assert_published_phase_pr_identity(self, result: dict, *, number: int, url: str | None = None) -> None:
        expected_url = url or result["phasePr"]["url"]
        for payload in (result["phasePr"], result["record"]["phasePr"], result["handoff"]["phasePr"]):
            self.assertEqual(payload["number"], number)
            self.assertEqual(payload["url"], expected_url)
            self.assertTrue(payload["isDraft"])
            self.assertEqual(payload["head"], result["phaseBranch"])
            self.assertEqual(payload["base"], "development")
            self.assertEqual(payload["headSha"], result["headSha"])
            self.assertEqual(payload["gitTree"], result["gitTree"])
            self.assertEqual(payload["headSha"], result["remoteSha"])
        ok, detail = coordinator.consume_handoff(
            result["handoff"],
            live_head=result["headSha"],
            live_tree=result["gitTree"],
            repository="owner/name",
        )
        self.assertTrue(ok, detail)

    def test_many_compatible_issues_create_one_ordered_phase(self) -> None:
        first = self.fx.accept_issue(1, "one.txt", "one\n")
        second = self.fx.accept_issue(2, "two.txt", "two\n")
        result = self.fx.assemble([first, second])
        self.assertEqual([row["branch"] for row in result["acceptedCommits"]], [first.branch, second.branch])
        self.assertEqual(result["record"]["dependencyOrder"], [first.branch, second.branch])
        self.assertEqual(len(self.fx.github.prs), 1)
        git(self.fx.work, "cat-file", "-e", f"{result['headSha']}:one.txt")
        git(self.fx.work, "cat-file", "-e", f"{result['headSha']}:two.txt")
        log = git(self.fx.work, "log", "--oneline", f"origin/development..{result['headSha']}")
        self.assertIn("issue 1", log)
        self.assertIn("issue 2", log)

    def test_identical_invocation_is_idempotent(self) -> None:
        one = self.fx.accept_issue(3, "same.txt", "same\n")
        first = self.fx.assemble([one])
        second = self.fx.assemble([one])
        self.assertTrue(second["idempotent"])
        self.assertEqual(second["action"], "reused")
        self.assertEqual(first["phasePr"]["number"], second["phasePr"]["number"])
        self.assertEqual(first["headSha"], second["headSha"])
        self.assertEqual(first["candidateRevision"], second["candidateRevision"])
        self.assertEqual(len(self.fx.github.prs), 1)
        self.assertEqual(self.fx.github.ensure_calls, 2)
        self.assertEqual(self.fx.github.labels, [])
        self.assertEqual(self.fx.github.workflow_dispatches, [])
        self._assert_published_phase_pr_identity(first, number=1)
        self._assert_published_phase_pr_identity(second, number=1)
        self.assertEqual(first["phasePr"], second["phasePr"])
        self.assertEqual(first["handoff"]["phasePr"], second["handoff"]["phasePr"])

    def test_created_phase_pr_publishes_exact_live_identity(self) -> None:
        one = self.fx.accept_issue(41, "created-id.txt", "created-id\n")
        result = self.fx.assemble([one])
        self.assertEqual(result["action"], "created")
        self.assertEqual(self.fx.github.ensure_calls, 1)
        self.assertEqual(len(self.fx.github.prs), 1)
        self._assert_published_phase_pr_identity(result, number=1)

    def test_reused_phase_pr_does_not_create_a_duplicate(self) -> None:
        one = self.fx.accept_issue(42, "reuse-id.txt", "reuse-id\n")
        first = self.fx.assemble([one])
        second = self.fx.assemble([one])
        self.assertEqual(second["action"], "reused")
        self.assertTrue(second["idempotent"])
        self.assertEqual(self.fx.github.ensure_calls, 2)
        self.assertEqual(len(self.fx.github.prs), 1)
        self.assertEqual(first["phasePr"]["number"], second["phasePr"]["number"])
        self._assert_published_phase_pr_identity(second, number=first["phasePr"]["number"])

    def test_stale_live_phase_pr_sha_is_rejected(self) -> None:
        one = self.fx.accept_issue(43, "stale-id.txt", "stale-id\n")
        created = self.fx.assemble([one])

        class StaleShaGitHub(coordinator.MemoryGitHub):
            def list_open_phase_prs(self, *, repository: str, head: str, base: str):
                rows = super().list_open_phase_prs(repository=repository, head=head, base=base)
                for row in rows:
                    row["headSha"] = "b" * 40
                return rows

        github = StaleShaGitHub(repository="owner/name")
        github.prs = self.fx.github.prs
        github.next_number = self.fx.github.next_number
        github.ready_shas = set(self.fx.github.ready_shas)
        github.evidence = dict(self.fx.github.evidence)
        with self.assertRaisesRegex(coordinator.CoordinatorError, "unverified_phase_ref"):
            self.fx.assemble([one], github=github)
        self.assertEqual(len(github.prs), 1)
        self.assertEqual(created["phasePr"]["number"], 1)

    def test_mismatched_live_head_or_base_is_rejected(self) -> None:
        one = self.fx.accept_issue(44, "mismatch-id.txt", "mismatch-id\n")
        self.fx.assemble([one])
        stored = next(iter(self.fx.github.prs.values()))
        stored["head"] = "phase/other"
        with self.assertRaisesRegex(coordinator.CoordinatorError, "stale_phase_pr_identity"):
            self.fx.assemble([one])
        stored["head"] = "phase/next"
        stored["base"] = "staging"
        with self.assertRaisesRegex(coordinator.CoordinatorError, "stale_phase_pr_identity"):
            self.fx.assemble([one])
        self.assertEqual(len(self.fx.github.prs), 1)

    def test_duplicate_open_phase_prs_are_rejected(self) -> None:
        one = self.fx.accept_issue(45, "dup-id.txt", "dup-id\n")

        class DuplicateListGitHub(coordinator.MemoryGitHub):
            def list_open_phase_prs(self, *, repository: str, head: str, base: str):
                found = super().list_open_phase_prs(repository=repository, head=head, base=base)
                if not found:
                    return found
                clone = dict(found[0])
                clone["number"] = int(found[0]["number"]) + 1
                clone["url"] = f"https://example.invalid/{repository}/pull/{clone['number']}"
                return [found[0], clone]

        github = DuplicateListGitHub(repository="owner/name")
        github.ready_shas = set(self.fx.github.ready_shas)
        github.evidence = dict(self.fx.github.evidence)
        with self.assertRaisesRegex(coordinator.CoordinatorError, "duplicate_phase_pr"):
            self.fx.assemble([one], github=github)
        self.assertEqual(len(github.prs), 1)

    def test_new_accepted_commit_updates_phase_and_invalidates_old_evidence(self) -> None:
        first = self.fx.accept_issue(4, "first.txt", "first\n")
        created = self.fx.assemble([first])
        second = self.fx.accept_issue(5, "second.txt", "second\n")
        updated = self.fx.assemble([first, second])
        self.assertEqual(updated["action"], "updated")
        self.assertNotEqual(updated["headSha"], created["headSha"])
        self.assertNotEqual(updated["candidateRevision"], created["candidateRevision"])
        self.assertEqual(updated["phasePr"]["number"], created["phasePr"]["number"])
        self.assertEqual(updated["record"]["invalidatedFromSha"], created["headSha"])
        self.assertEqual(updated["record"]["fast"]["status"], "invalidated")
        stale = coordinator.invalidate_handoff_if_head_changed(created["handoff"], live_head=updated["headSha"])
        self.assertFalse(stale["valid"])
        ok, detail = coordinator.consume_handoff(created["handoff"], live_head=updated["headSha"])
        self.assertFalse(ok)
        self.assertEqual(detail, "handoff_stale_head")
        ok, detail = coordinator.consume_handoff(updated["handoff"], live_head=updated["headSha"], live_tree=updated["gitTree"])
        self.assertTrue(ok, detail)

    def test_rejects_uncommitted_unpushed_wrong_repo_stale_missing(self) -> None:
        ready = self.fx.accept_issue(6, "ready.txt", "ready\n")
        git(self.fx.work, "checkout", ready.branch)
        write(self.fx.work / "dirty.txt", "dirty\n")
        with self.assertRaisesRegex(coordinator.CoordinatorError, "uncommitted"):
            self.fx.assemble([ready])
        (self.fx.work / "dirty.txt").unlink()
        git(self.fx.work, "checkout", "-f", "development")

        git(self.fx.work, "checkout", "-B", "issue/7-unpushed", "development")
        write(self.fx.work / "unpushed.txt", "unpushed\n")
        git(self.fx.work, "add", "unpushed.txt")
        git(self.fx.work, "commit", "-qm", "unpushed")
        unpushed_sha = git(self.fx.work, "rev-parse", "HEAD")
        git(self.fx.work, "checkout", "development")
        self.fx.github.ready_shas.add(unpushed_sha)
        with self.assertRaisesRegex(coordinator.CoordinatorError, "unpushed"):
            self.fx.assemble([coordinator.AcceptedSource("issue/7-unpushed", unpushed_sha, 1)])

        with self.assertRaisesRegex(coordinator.CoordinatorError, "wrong_repository"):
            self.fx.assemble([ready], expected_repository="other/name")

        stale = self.fx.accept_issue(8, "stale.txt", "stale\n")
        git(self.fx.work, "checkout", stale.branch)
        write(self.fx.work / "stale.txt", "newer\n")
        git(self.fx.work, "add", "stale.txt")
        git(self.fx.work, "commit", "-qm", "newer stale")
        git(self.fx.work, "push", "-q")
        git(self.fx.work, "checkout", "development")
        with self.assertRaisesRegex(coordinator.CoordinatorError, "stale_commit"):
            self.fx.assemble([stale])

        with self.assertRaisesRegex(coordinator.CoordinatorError, "missing_commit"):
            self.fx.assemble([coordinator.AcceptedSource("issue/9-missing", "a" * 40, 1)])

        bare = self.fx.accept_issue(10, "noevidence.txt", "x\n", ready=False)
        with self.assertRaisesRegex(coordinator.CoordinatorError, "evidence_missing"):
            self.fx.assemble([bare])

        status_only = self.fx.accept_issue(32, "statusonly.txt", "status-only\n", ready=False)
        self.fx.github.ready_shas.add(status_only.sha)
        with self.assertRaisesRegex(coordinator.CoordinatorError, "evidence_missing"):
            self.fx.assemble([status_only])

    def test_lean_evidence_payload_accepts_without_review_ready_status(self) -> None:
        source = self.fx.accept_issue(33, "lean.txt", "lean\n", ready=False)
        tree = git(self.fx.work, "rev-parse", f"{source.sha}^{{tree}}")
        payload = {
            "schemaVersion": 1,
            "kind": "v25-issue-checkpoint",
            "headSha": source.sha,
            "gitTree": tree,
            "pushed": True,
            "scopedDiff": True,
            "focusedTests": {"passed": True},
            "independentNarrowReview": {
                "accepted": True,
                "headSha": source.sha,
                "gitTree": tree,
                "paths": ["declared-checkpoint-scope"],
                "reviewer": {"actor": "independent-reviewer", "role": "reviewer"},
                "implementerActor": "implementer",
            },
            "manifestEvidence": True,
            "classification": "tests",
            "acceptance": "PKT-05 lean checkpoint",
        }
        result = self.fx.assemble([source], evidence_payloads={source.sha: payload})
        self.assertEqual(result["acceptedCommits"][0]["sha"], source.sha)
        self.assertNotIn(source.sha, self.fx.github.ready_shas)

    def test_overlapping_and_conflicting_commits_stop(self) -> None:
        left = self.fx.accept_issue(12, "shared.txt", "left\n")
        git(self.fx.work, "checkout", "-B", "issue/13-shared", "development")
        write(self.fx.work / "shared.txt", "right\n")
        git(self.fx.work, "add", "shared.txt")
        git(self.fx.work, "commit", "-qm", "right")
        right_sha = git(self.fx.work, "rev-parse", "HEAD")
        git(self.fx.work, "push", "-q", "-u", "origin", "issue/13-shared")
        git(self.fx.work, "checkout", "development")
        self.fx.github.ready_shas.add(right_sha)
        self.fx.github.evidence[right_sha] = {
            "schemaVersion": 1,
            "headSha": right_sha,
            "classification": "tests",
            "acceptance": "lean-or-schema-v1",
        }
        with self.assertRaisesRegex(coordinator.CoordinatorError, "overlapping_commits"):
            self.fx.assemble(
                [
                    left,
                    coordinator.AcceptedSource("issue/13-shared", right_sha, 2),
                ]
            )

    def test_unrelated_commits_are_not_included(self) -> None:
        wanted = self.fx.accept_issue(14, "wanted.txt", "wanted\n")
        extra = self.fx.accept_issue(15, "extra.txt", "extra\n")
        result = self.fx.assemble([wanted])
        self.assertEqual([row["sha"] for row in result["acceptedCommits"]], [wanted.sha])
        git(self.fx.work, "cat-file", "-e", f"{result['headSha']}:wanted.txt")
        missing = subprocess.run(
            ["git", "cat-file", "-e", f"{result['headSha']}:extra.txt"],
            cwd=self.fx.work,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(missing.returncode, 0)
        self.assertFalse(coordinator._is_ancestor(self.fx.work, extra.sha, result["headSha"]))

    def test_checkpoint_push_does_not_start_managed_ci_and_phase_pr_starts_fast(self) -> None:
        fast = INSTALLED_FAST_WORKFLOW.read_text(encoding="utf-8")
        contract = coordinator.parse_fast_trigger_contract(fast)
        self.assertTrue(contract["namedFast"])
        self.assertFalse(contract["checkpointPush"])
        self.assertTrue(contract["phasePullRequest"])
        self.assertTrue(contract["phaseHeadOnly"])
        self.assertTrue(contract["checksExactHead"])
        self.assertTrue(contract["cancelObsolete"])
        self.assertFalse(contract["startsFull"])
        live = LIVE_FAST_WORKFLOW.read_text(encoding="utf-8")
        live_contract = coordinator.parse_fast_trigger_contract(live)
        self.assertEqual(contract["namedFast"], live_contract["namedFast"])
        self.assertFalse(live_contract["checkpointPush"])
        self.assertTrue(live_contract["phasePullRequest"])
        self.assertFalse(live_contract["startsFull"])
        full = LIVE_FULL_WORKFLOW.read_text(encoding="utf-8")
        self.assertNotRegex(full, r"(?m)^\s+push:")
        self.assertIn("types: [labeled]", full)
        one = self.fx.accept_issue(16, "fast.txt", "fast\n")
        result = self.fx.assemble([one])
        self.assertEqual(result["fastTrigger"], "phase_pr")
        self.assertFalse(result["checkpointCI"])
        self.assertFalse(result["fullDispatchAllowed"])
        self.assertEqual(self.fx.github.labels, [])
        self.assertEqual(self.fx.github.workflow_dispatches, [])

    def test_full_cannot_start_before_fast_and_required_ci(self) -> None:
        allowed, detail = coordinator.full_may_start(
            sealed=False,
            fast_status="passed",
            required_ci={"CI": "success"},
            live_head_sha="a" * 40,
        )
        self.assertFalse(allowed)
        self.assertEqual(detail, "unsealed")
        allowed, detail = coordinator.full_may_start(
            sealed=True,
            fast_status="running",
            required_ci={"CI": "success"},
            live_head_sha="a" * 40,
        )
        self.assertFalse(allowed)
        self.assertIn("fast_not_passed", detail)
        allowed, detail = coordinator.full_may_start(
            sealed=True,
            fast_status="passed",
            required_ci={"CI": "pending"},
            live_head_sha="a" * 40,
        )
        self.assertFalse(allowed)
        self.assertIn("required_ci_not_passed", detail)

    def test_handoff_schema_and_agent_agnostic_behavior(self) -> None:
        one = self.fx.accept_issue(17, "handoff.txt", "handoff\n")
        os.environ["CURSOR_AGENT"] = "1"
        os.environ["CODEX_HOME"] = "/tmp/codex-fixture"
        try:
            cursor = self.fx.assemble([one])
        finally:
            os.environ.pop("CURSOR_AGENT", None)
            os.environ.pop("CODEX_HOME", None)
        os.environ["TERRA_AGENT"] = "terra"
        try:
            terra = self.fx.assemble([one])
        finally:
            os.environ.pop("TERRA_AGENT", None)
        self.assertEqual(cursor["headSha"], terra["headSha"])
        self.assertEqual(cursor["candidateRevision"], terra["candidateRevision"])
        self.assertEqual(cursor["phasePr"]["number"], terra["phasePr"]["number"])
        self.assertIn("CURSOR_AGENT", cursor["agentEnvIgnored"])
        handoff = cursor["handoff"]
        for key in (
            "schemaVersion",
            "kind",
            "repository",
            "phaseBranch",
            "phasePr",
            "headCommit",
            "gitTree",
            "baseCommit",
            "candidateRevision",
            "acceptedCommits",
            "evidenceLocations",
            "valid",
            "component",
        ):
            self.assertIn(key, handoff)
        self.assertEqual(handoff["kind"], "phase-handoff")
        self.assertEqual(handoff["component"], coordinator.COMPONENT_KIND)
        schema = json.loads(INSTALLED_HANDOFF_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["required"], list(key for key in schema["required"]))
        for key in schema["required"]:
            self.assertIn(key, handoff)
        record_schema = json.loads(INSTALLED_RECORD_SCHEMA.read_text(encoding="utf-8"))
        for key in record_schema["required"]:
            self.assertIn(key, cursor["record"])

    def test_typed_provider_consumer_handoff_is_carried_and_written_separately(self) -> None:
        one = self.fx.accept_issue(171, "typed.txt", "typed\n")
        provider = {"repository": "owner/provider", "commit": "a" * 40, "tree": "b" * 40}
        consumer = {"repository": "owner/consumer", "commit": "c" * 40, "tree": "d" * 40}
        receipt = {
            "status": "accepted",
            "protected": True,
            "receiptDigest": "sha256:" + "e" * 64,
            "provider": provider,
        }
        typed = coordinator.build_provider_consumer_handoff(
            provider=provider,
            consumer=consumer,
            artifact_digest="sha256:" + "f" * 64,
            contract_digest="sha256:" + "1" * 64,
            verdict="accepted",
            lifecycle_state="accepted",
            accepted_receipt=receipt,
        )
        result = self.fx.assemble([one], provider_consumer_handoff=typed)
        self.assertEqual(result["providerConsumerHandoff"], typed)
        state_dir = Path(result["stateDir"])
        self.assertEqual(
            json.loads((state_dir / "provider-consumer-handoff.json").read_text(encoding="utf-8")),
            typed,
        )
        phase_schema_path = INSTALLED_HANDOFF_SCHEMA
        phase_schema = json.loads(phase_schema_path.read_text(encoding="utf-8"))
        typed_schema_path = ROOT / ".ide-development/schemas/provider-consumer-handoff.schema.json"
        typed_schema = json.loads(typed_schema_path.read_text(encoding="utf-8"))
        resolver = RefResolver(
            phase_schema_path.as_uri(),
            phase_schema,
            store={typed_schema_path.as_uri(): typed_schema, typed_schema["$id"]: typed_schema},
        )
        errors = list(Draft202012Validator(phase_schema, resolver=resolver).iter_errors(result["handoff"]))
        self.assertEqual(errors, [])

    def test_does_not_push_protected_branches(self) -> None:
        one = self.fx.accept_issue(18, "protect.txt", "protect\n")
        before = git(self.fx.work, "rev-parse", "origin/development")
        result = self.fx.assemble([one])
        after = git(self.fx.work, "rev-parse", "origin/development")
        self.assertEqual(before, after)
        self.assertEqual(git(self.fx.work, "rev-parse", "--abbrev-ref", "HEAD"), "development")
        self.assertEqual(remote_sha(self.fx.work, "phase/next"), result["headSha"])
        with self.assertRaisesRegex(coordinator.CoordinatorError, "invalid_phase_branch"):
            coordinator.assemble_phase(
                repo=self.fx.work,
                repository="owner/name",
                sources=[one],
                github=self.fx.github,
                pusher=coordinator.GitPushAdapter(),
                phase_branch="development",
            )


class PhasePackagerCoordinatorAdversarialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)

    def test_cli_assemble_refuses_memory_github_without_credentials(self) -> None:
        one = self.fx.accept_issue(21, "cli.txt", "cli\n")
        env_keys = (
            "AUTOMATION_TOKEN",
            "AUTOMATION_TOKEN_SOURCE",
            "LINKTREND_BUGBOT_USER_TOKEN",
            "BUGBOT_USER_TOKEN",
            "GH_TOKEN",
            "GITHUB_TOKEN",
        )
        saved = {key: os.environ.pop(key, None) for key in env_keys}
        stdout = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
                code = coordinator.main(
                    [
                        "assemble",
                        "--repository",
                        "owner/name",
                        "--repo-path",
                        str(self.fx.work),
                        "--phase-branch",
                        "phase/next",
                        "--accept",
                        f"{one.branch}@{one.sha}",
                        "--no-evidence",
                    ]
                )
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "missing_github_credentials")
        self.assertNotIn("example.invalid", stdout.getvalue())
        self.assertNotIn("example.invalid", json.dumps(payload))
        self.assertEqual(remote_sha(self.fx.work, "phase/next"), "")

    def test_production_success_rejects_example_invalid_pr(self) -> None:
        one = self.fx.accept_issue(22, "livepr.txt", "live\n")
        with self.assertRaisesRegex(coordinator.CoordinatorError, "invalid_phase_pr"):
            self.fx.assemble([one], require_live_pr=True)
        self.assertEqual(remote_sha(self.fx.work, "phase/next"), "")

    def _live_transport(
        self,
        *,
        url: str,
        draft: bool,
        sha: str | None = None,
        head_ref: str = "phase/next",
        base_ref: str = "development",
        extra_open: list[dict[str, object]] | None = None,
        readback_sha: str | None = None,
    ):
        created: dict[str, object] = {}
        posts = {"count": 0}

        def transport(method: str, request_url: str, token: str, body):
            if method == "GET" and "/pulls?" in request_url:
                rows = [dict(created)] if created else []
                if extra_open:
                    rows.extend(extra_open)
                return rows
            if method == "GET" and "/pulls/" in request_url:
                if not created:
                    raise AssertionError(f"readback before create {request_url}")
                payload = dict(created)
                if readback_sha is not None:
                    payload["head"] = {"ref": head_ref, "sha": readback_sha}
                return payload
            if method == "POST" and request_url.endswith("/pulls"):
                posts["count"] += 1
                head_sha = sha or remote_sha(self.fx.work, "phase/next")
                created.update(
                    {
                        "number": 42,
                        "html_url": url,
                        "draft": draft,
                        "head": {"ref": head_ref, "sha": head_sha},
                        "base": {"ref": base_ref},
                    }
                )
                return dict(created)
            if method == "PATCH":
                return dict(created)
            raise AssertionError(f"unexpected GitHub call {method} {request_url}")

        github = coordinator.LiveGitHub(
            repository="owner/name",
            automation_token="ltfx.coordinator.auto_token.v1",
            user_token="ltfx.coordinator.user_token.v1",
            transport=transport,
        )
        github.posts = posts
        return github

    def test_live_github_rejects_example_invalid_pr_url(self) -> None:
        invalid = self.fx.accept_issue(28, "badurl.txt", "badurl\n")
        with self.assertRaisesRegex(coordinator.CoordinatorError, "invalid_phase_pr"):
            self.fx.assemble(
                [invalid],
                github=self._live_transport(url="https://example.invalid/owner/name/pull/42", draft=True),
                require_live_pr=True,
                require_evidence=False,
            )

    def test_live_github_rejects_non_draft_pr(self) -> None:
        ready = self.fx.accept_issue(29, "nondraft.txt", "nondraft\n")
        with self.assertRaisesRegex(coordinator.CoordinatorError, "phase_pr_not_draft"):
            self.fx.assemble(
                [ready],
                github=self._live_transport(url="https://github.com/owner/name/pull/42", draft=False),
                require_live_pr=True,
                require_evidence=False,
            )

    def test_live_github_success_requires_real_draft_pr_and_remote_sha(self) -> None:
        one = self.fx.accept_issue(30, "goodpr.txt", "goodpr\n")
        result = self.fx.assemble(
            [one],
            github=self._live_transport(url="https://github.com/owner/name/pull/42", draft=True),
            require_live_pr=True,
            require_evidence=False,
        )
        self.assertEqual(result["phasePr"]["number"], 42)
        self.assertEqual(result["phasePr"]["url"], "https://github.com/owner/name/pull/42")
        self.assertTrue(result["phasePr"]["isDraft"])
        self.assertEqual(result["phasePr"]["head"], "phase/next")
        self.assertEqual(result["phasePr"]["base"], "development")
        self.assertEqual(result["phasePr"]["headSha"], result["headSha"])
        self.assertEqual(result["phasePr"]["gitTree"], result["gitTree"])
        self.assertEqual(result["handoff"]["phasePr"]["headSha"], result["headSha"])
        self.assertEqual(result["handoff"]["phasePr"]["gitTree"], result["gitTree"])
        self.assertEqual(remote_sha(self.fx.work, "phase/next"), result["headSha"])
        self.assertNotIn("example.invalid", json.dumps(result["phasePr"]))
        ok, detail = coordinator.consume_handoff(
            result["handoff"],
            live_head=result["headSha"],
            live_tree=result["gitTree"],
            repository="owner/name",
        )
        self.assertTrue(ok, detail)

    def test_live_github_rejects_mismatched_readback_sha(self) -> None:
        one = self.fx.accept_issue(46, "badsha.txt", "badsha\n")
        with self.assertRaisesRegex(coordinator.CoordinatorError, "unverified_phase_ref"):
            self.fx.assemble(
                [one],
                github=self._live_transport(
                    url="https://github.com/owner/name/pull/42",
                    draft=True,
                    readback_sha="a" * 40,
                ),
                require_live_pr=True,
                require_evidence=False,
            )

    def test_live_github_reuses_without_second_create(self) -> None:
        one = self.fx.accept_issue(47, "livereuse.txt", "livereuse\n")
        github = self._live_transport(url="https://github.com/owner/name/pull/42", draft=True)
        first = self.fx.assemble(
            [one],
            github=github,
            require_live_pr=True,
            require_evidence=False,
        )
        second = self.fx.assemble(
            [one],
            github=github,
            require_live_pr=True,
            require_evidence=False,
        )
        self.assertEqual(github.posts["count"], 1)
        self.assertEqual(second["action"], "reused")
        self.assertEqual(first["phasePr"]["number"], second["phasePr"]["number"])
        self.assertEqual(first["phasePr"]["headSha"], second["phasePr"]["headSha"])
        self.assertEqual(first["phasePr"]["gitTree"], second["phasePr"]["gitTree"])
        self.assertEqual(github.ensure_calls, 2)

    def test_success_requires_verified_remote_phase_ref(self) -> None:
        one = self.fx.accept_issue(23, "push.txt", "push\n")
        result = self.fx.assemble([one])
        self.assertEqual(remote_sha(self.fx.work, "phase/next"), result["headSha"])
        self.assertEqual(result["remoteSha"], result["headSha"])
        self.assertEqual(result["phasePr"]["number"], 1)

    def test_existing_unique_phase_work_is_preserved(self) -> None:
        one = self.fx.accept_issue(24, "keep.txt", "keep\n")
        git(self.fx.work, "checkout", "-B", "phase/next", "development")
        write(self.fx.work / "unique.txt", "unique phase work\n")
        git(self.fx.work, "add", "unique.txt")
        git(self.fx.work, "commit", "-qm", "unique phase work")
        unique_sha = git(self.fx.work, "rev-parse", "HEAD")
        git(self.fx.work, "push", "-q", "-u", "origin", "phase/next")
        git(self.fx.work, "checkout", "development")
        with self.assertRaisesRegex(coordinator.CoordinatorError, "unique_phase_divergence"):
            self.fx.assemble([one])
        self.assertEqual(remote_sha(self.fx.work, "phase/next"), unique_sha)
        git(self.fx.work, "cat-file", "-e", f"{unique_sha}:unique.txt")
        self.assertEqual(git(self.fx.work, "rev-parse", "--abbrev-ref", "HEAD"), "development")

    def test_unique_commits_on_assembled_phase_block_identical_reuse(self) -> None:
        one = self.fx.accept_issue(31, "keep2.txt", "keep2\n")
        created = self.fx.assemble([one])
        git(self.fx.work, "checkout", "-B", "phase/next", created["headSha"])
        write(self.fx.work / "unique-reuse.txt", "unique reuse work\n")
        git(self.fx.work, "add", "unique-reuse.txt")
        git(self.fx.work, "commit", "-qm", "unique reuse work")
        unique_sha = git(self.fx.work, "rev-parse", "HEAD")
        git(self.fx.work, "push", "-q", "origin", "phase/next")
        git(self.fx.work, "checkout", "development")
        with self.assertRaisesRegex(coordinator.CoordinatorError, "unique_phase_divergence"):
            self.fx.assemble([one])
        self.assertEqual(remote_sha(self.fx.work, "phase/next"), unique_sha)
        git(self.fx.work, "cat-file", "-e", f"{unique_sha}:unique-reuse.txt")
        git(self.fx.work, "cat-file", "-e", f"{unique_sha}:keep2.txt")
        self.assertEqual(git(self.fx.work, "rev-parse", "--abbrev-ref", "HEAD"), "development")

    def test_existing_phase_drift_is_rejected(self) -> None:
        one = self.fx.accept_issue(25, "drift.txt", "drift\n")
        created = self.fx.assemble([one])
        git(self.fx.work, "checkout", "-B", "phase/next", created["headSha"])
        write(self.fx.work / "drifted.txt", "drifted\n")
        git(self.fx.work, "add", "drifted.txt")
        git(self.fx.work, "commit", "-qm", "drifted phase")
        drifted = git(self.fx.work, "rev-parse", "HEAD")
        git(self.fx.work, "push", "-q", "origin", "phase/next")
        git(self.fx.work, "update-ref", "refs/heads/phase/next", created["headSha"])
        git(self.fx.work, "checkout", "development")
        with self.assertRaisesRegex(coordinator.CoordinatorError, "phase_ref_drift"):
            self.fx.assemble([one])
        self.assertEqual(remote_sha(self.fx.work, "phase/next"), drifted)

    def test_assemble_uses_isolated_worktree_and_state(self) -> None:
        one = self.fx.accept_issue(26, "isolated.txt", "isolated\n")
        caller_head = git(self.fx.work, "rev-parse", "HEAD")
        result = self.fx.assemble([one])
        self.assertEqual(git(self.fx.work, "rev-parse", "HEAD"), caller_head)
        self.assertEqual(git(self.fx.work, "rev-parse", "--abbrev-ref", "HEAD"), "development")
        self.assertFalse((self.fx.work / "isolated.txt").exists())
        self.assertFalse((self.fx.work / ".linktrend" / "phase-handoff.json").exists())
        state_dir = Path(result["stateDir"])
        self.assertTrue(state_dir.is_dir())
        self.assertTrue((state_dir / "phase-handoff.json").is_file())
        self.assertTrue((state_dir / "phase-delivery-record.json").is_file())
        common = Path(git(self.fx.work, "rev-parse", "--git-common-dir"))
        if not common.is_absolute():
            common = (self.fx.work / common).resolve()
        self.assertEqual(
            state_dir.resolve().relative_to(common.resolve()).parts[:2],
            ("ide-development", "phase-packager"),
        )
        listed = git(self.fx.work, "worktree", "list", "--porcelain")
        self.assertNotIn("phase-assemble", listed)

    def test_index_manifest_schema_and_hosted_fast_cover_coordinator(self) -> None:
        index = (ROOT / ".ide-development/INDEX.yaml").read_text(encoding="utf-8")
        self.assertIn("schemas/phase-handoff.schema.json", index)
        self.assertIn("schemas/phase-record.schema.json", index)
        self.assertIn("core/managed-core/schemas/phase-handoff.schema.json", RC_REQUIRED_SCHEMA_RELS)
        self.assertIn("core/managed-core/schemas/phase-record.schema.json", RC_REQUIRED_SCHEMA_RELS)
        manifest = json.loads((ROOT / ".ide-development/MANIFEST.json").read_text(encoding="utf-8"))
        sources = {row["source"] for row in manifest["files"]}
        destinations = {row["destination"] for row in manifest["files"]}
        self.assertIn("core/managed-core/schemas/phase-handoff.schema.json", sources)
        self.assertIn("core/managed-core/schemas/phase-record.schema.json", sources)
        self.assertIn("scripts/gitops/packager_coordinator.py", sources)
        self.assertIn("scripts/tests/test_phase_packager_coordinator.py", sources)
        self.assertIn(".ide-development/schemas/phase-handoff.schema.json", destinations)
        self.assertIn("scripts/gitops/packager_coordinator.py", destinations)
        self.assertTrue(INSTALLED_HANDOFF_SCHEMA.is_file())
        self.assertTrue(INSTALLED_RECORD_SCHEMA.is_file())
        one = self.fx.accept_issue(27, "schema.txt", "schema\n")
        result = self.fx.assemble([one])
        handoff_schema = json.loads(INSTALLED_HANDOFF_SCHEMA.read_text(encoding="utf-8"))
        record_schema = json.loads(INSTALLED_RECORD_SCHEMA.read_text(encoding="utf-8"))
        for key in handoff_schema["required"]:
            self.assertIn(key, result["handoff"])
        extra_handoff = set(result["handoff"]) - set(handoff_schema["properties"])
        self.assertEqual(extra_handoff, set())
        for key in record_schema["required"]:
            self.assertIn(key, result["record"])

    def test_memory_github_stays_test_only(self) -> None:
        self.assertIn("Never talks to GitHub", coordinator.MemoryGitHub.__doc__)
        adapters = coordinator.resolve_production_adapters
        with self.assertRaisesRegex(coordinator.CoordinatorError, "missing_github_credentials"):
            adapters("owner/name")


if __name__ == "__main__":
    unittest.main()
