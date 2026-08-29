"""Focused adversarial tests for WP-U09 independent-review convergence."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.gitops.independent_review_convergence import (
    CLASS_CORRECTED,
    CLASS_INTRODUCED_BY_REPAIR,
    CLASS_NEWLY_DISCOVERED,
    CLASS_REPEATED,
    CLASS_UNRESOLVED,
    CONTINUE_UNTIL_CLEAN,
    HOLD_MALFORMED_OUTPUT,
    HOLD_REVIEWER_SILENCE,
    HOLD_REVIEWER_TIMEOUT,
    MAX_INFRASTRUCTURE_ATTEMPTS,
    STATUS_HOLD,
    STATUS_IN_PROGRESS,
    STATUS_REVIEW_CLEAN,
    STATUS_REVIEW_STALLED,
    STATUS_UNATTENDED_CHECKPOINT,
    STALL_INFRA_EXHAUSTED,
    STALL_NO_PROGRESS,
    STALL_REDESIGN,
    STALL_REINTRODUCTION,
    STALL_REPEATED_UNRESOLVED,
    STALL_RESOURCE_LIMIT,
    TERMINAL_CYCLE_CAP,
    UNATTENDED_CHECKPOINT_CYCLES,
    ConvergenceError,
    MemoryReviewer,
    apply_repair,
    apply_repository_policy,
    authorize_split,
    consolidate_repair_batch,
    evaluate_progress,
    founder_decision_packet,
    ingest_integration_review,
    ingest_review,
    invalidate_evidence,
    ledger_to_dict,
    open_session,
    record_compute_units,
    record_focused_changed_path_checks,
    record_founder_authority,
    record_full_evidence,
    record_preflight,
    start_reviewer,
    ingest_delta_review,
    plan_delivery,
    transition_delivery,
    timeout_reviewer,
)
from scripts.ide_development.constants import RC_REQUIRED_SCHEMA_RELS

ROOT = Path(__file__).resolve().parents[2]
HEAD_A = "a" * 40
HEAD_B = "b" * 40
HEAD_C = "c" * 40
HEAD_D = "d" * 40
HEAD_E = "e" * 40
HEAD_F = "f" * 40
TREE_A = "1" * 40
TREE_B = "2" * 40
TREE_C = "3" * 40
TREE_D = "4" * 40
TREE_E = "5" * 40
TREE_F = "6" * 40
BASE = "0" * 40


class FakeClock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.value = start

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def finding(
    fingerprint: str,
    *,
    statement: str | None = None,
    paths: list[str] | None = None,
    severity: str = "P1",
    redesign: bool = False,
    authority: bool = False,
) -> dict[str, object]:
    return {
        "fingerprint": fingerprint,
        "severity": severity,
        "paths": paths or [f"src/{fingerprint}.py"],
        "statement": statement or f"{fingerprint} is defective",
        "evidence": f"observed {fingerprint}",
        "acceptanceTest": f"test_{fingerprint}_is_fixed",
        "requiresRedesign": redesign,
        "requiresNewAuthority": authority,
    }


def open_default(**kwargs):
    clock = kwargs.pop("clock", FakeClock())
    session, entries = open_session(
        repository="linktrend/IDE-Development",
        base_sha=BASE,
        candidate_sha=kwargs.pop("candidate_sha", HEAD_A),
        git_tree=kwargs.pop("git_tree", TREE_A),
        scope=kwargs.pop("scope", ["src/"]),
        reviewer_policy=kwargs.pop("reviewer_policy", "default"),
        implementer_actor=kwargs.pop("implementer_actor", "grok-implementer"),
        reviewer_actor=kwargs.pop("reviewer_actor", "opus-reviewer"),
        require_full_before_review=kwargs.pop("require_full_before_review", False),
        full_first_justification=kwargs.pop("full_first_justification", "repository policy requires pre-review Full"),
        resource_limit=kwargs.pop("resource_limit", None),
        clock=clock,
    )
    return session, entries, clock


def review(session, entries, findings, *, head=None, tree=None):
    return ingest_review(
        session,
        entries,
        {
            "headSha": head or session.candidate_sha,
            "gitTree": tree or session.git_tree,
            "findings": findings,
        },
        actor=session.reviewer_actor,
        role="reviewer",
    )


def cycle(session, entries, *, new_head: str, new_tree: str, remaining: list[dict[str, object]], touched=None):
    batch = consolidate_repair_batch(session, entries)
    apply_repair(
        session,
        entries,
        new_head=new_head,
        new_tree=new_tree,
        touched_paths=touched or [item["paths"][0] for item in remaining] or ["src/x.py"],
        tests=[{"command": "focused", "exitCode": 0}],
    )
    review(session, entries, remaining)
    return batch, evaluate_progress(session, entries)


class SchemaAndIdentityTests(unittest.TestCase):
    def test_schemas_and_indexes_are_packaged(self) -> None:
        session_schema = ROOT / "core/managed-core/schemas/review-session.schema.json"
        ledger_schema = ROOT / "core/managed-core/schemas/finding-ledger.schema.json"
        index = (ROOT / "core/managed-core/INDEX.yaml").read_text(encoding="utf-8")
        self.assertTrue(session_schema.is_file())
        self.assertTrue(ledger_schema.is_file())
        self.assertIn("schemas/review-session.schema.json", index)
        self.assertIn("schemas/finding-ledger.schema.json", index)
        self.assertIn("core/managed-core/schemas/review-session.schema.json", RC_REQUIRED_SCHEMA_RELS)
        self.assertIn("core/managed-core/schemas/finding-ledger.schema.json", RC_REQUIRED_SCHEMA_RELS)
        session = json.loads(session_schema.read_text(encoding="utf-8"))
        self.assertEqual(session["properties"]["terminalCycleCap"]["type"], "null")
        self.assertIsNone(TERMINAL_CYCLE_CAP)

    def test_exact_identity_and_role_separation(self) -> None:
        with self.assertRaises(ConvergenceError) as raised:
            open_session(
                repository="linktrend/IDE-Development",
                base_sha=BASE,
                candidate_sha=HEAD_A,
                git_tree=TREE_A,
                scope=["src/"],
                reviewer_policy="default",
                implementer_actor="same-agent",
                reviewer_actor="same-agent",
            )
        self.assertEqual(raised.exception.code, "role_separation")
        session, entries, _clock = open_default()
        with self.assertRaises(ConvergenceError) as raised:
            ingest_review(
                session,
                entries,
                {"headSha": HEAD_A, "gitTree": TREE_A, "findings": []},
                actor=session.implementer_actor,
                role="implementer",
            )
        self.assertEqual(raised.exception.code, "role_separation")


class AcU0901ObservableLoopTests(unittest.TestCase):
    def test_session_always_has_status_and_no_terminal_cycle_cap(self) -> None:
        session, entries, _clock = open_default()
        review(session, entries, [finding("authz"), finding("hash")])
        self.assertEqual(session.status, "in_progress")
        self.assertIsNone(session.to_dict()["terminalCycleCap"])
        self.assertEqual(session.to_dict()["unattendedCheckpointCycles"], UNATTENDED_CHECKPOINT_CYCLES)
        packet = founder_decision_packet(session, entries)
        self.assertEqual(packet["status"], session.status)
        self.assertIn("ledger", packet)


class AcU0905ConsolidatedBatchTests(unittest.TestCase):
    def test_many_findings_one_batch_one_cycle(self) -> None:
        session, entries, _clock = open_default()
        review(session, entries, [finding("a"), finding("b"), finding("c")])
        batch, decision = cycle(
            session,
            entries,
            new_head=HEAD_B,
            new_tree=TREE_B,
            remaining=[],
        )
        self.assertEqual(len(batch.fingerprints), 3)
        self.assertEqual(session.repair_cycle_count, 1)
        self.assertEqual(decision.status, STATUS_REVIEW_CLEAN)
        self.assertTrue(batch.cycle_consumed)
        with self.assertRaises(ConvergenceError) as raised:
            apply_repair(session, entries, new_head=HEAD_C, new_tree=TREE_C, touched_paths=["src/a.py"])
        self.assertEqual(raised.exception.code, "duplicate_cycle")


class AcU0906StableFingerprintTests(unittest.TestCase):
    def test_wording_and_new_commit_cannot_hide_finding(self) -> None:
        session, entries, _clock = open_default()
        review(session, entries, [finding("authz", statement="missing tenant check on write")])
        consolidate_repair_batch(session, entries)
        apply_repair(session, entries, new_head=HEAD_B, new_tree=TREE_B, touched_paths=["src/authz.py"])
        review(
            session,
            entries,
            [
                finding(
                    "authz",
                    statement="The write path still misses a tenant authorization check",
                    paths=["src/authz.py"],
                )
            ],
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].classification, CLASS_REPEATED)
        self.assertEqual(entries[0].finding.paths, ["src/authz.py"])
        self.assertEqual(entries[0].first_seen_head, HEAD_A)
        self.assertEqual(entries[0].last_seen_head, HEAD_B)


class AcU0907InfrastructureBoundTests(unittest.TestCase):
    def test_two_preflight_failures_do_not_consume_cycles_third_rejected(self) -> None:
        session, entries, _clock = open_default()
        first = record_preflight(session, [{"path": "bundle/a", "problem": "secret"}])
        second = record_preflight(session, [{"path": "bundle/b", "problem": "secret"}])
        self.assertFalse(first["consumedRepairCycle"])
        self.assertFalse(second["consumedRepairCycle"])
        self.assertEqual(session.repair_cycle_count, 0)
        self.assertEqual(session.infrastructure_attempts, MAX_INFRASTRUCTURE_ATTEMPTS)
        with self.assertRaises(ConvergenceError) as raised:
            record_preflight(session, [{"path": "bundle/c", "problem": "secret"}])
        self.assertEqual(raised.exception.code, STALL_INFRA_EXHAUSTED)
        self.assertEqual(session.status, STATUS_REVIEW_STALLED)
        self.assertEqual(session.repair_cycle_count, 0)


class AcU0908UnattendedAndFounderContinueTests(unittest.TestCase):
    def test_unattended_pauses_after_three_then_continue_until_clean_has_no_cap(self) -> None:
        session, entries, _clock = open_default()
        current = finding("one")
        review(session, entries, [current])
        heads = [(HEAD_B, TREE_B), (HEAD_C, TREE_C), (HEAD_D, TREE_D)]
        next_names = ["two", "three", "four"]
        decision = None
        for (head, tree), name in zip(heads, next_names):
            nxt = finding(name, paths=[f"src/{name}.py"])
            _batch, decision = cycle(
                session,
                entries,
                new_head=head,
                new_tree=tree,
                remaining=[nxt],
                touched=current["paths"],
            )
            current = nxt
        self.assertEqual(session.repair_cycle_count, 3)
        self.assertEqual(decision.status, STATUS_UNATTENDED_CHECKPOINT)
        record_founder_authority(session, owner="founder", scope="this candidate")
        self.assertEqual(session.founder_authority["instruction"], CONTINUE_UNTIL_CLEAN)
        _batch, decision = cycle(session, entries, new_head=HEAD_E, new_tree=TREE_E, remaining=[])
        self.assertEqual(session.repair_cycle_count, 4)
        self.assertEqual(decision.status, STATUS_REVIEW_CLEAN)
        self.assertGreater(session.repair_cycle_count, UNATTENDED_CHECKPOINT_CYCLES)
        self.assertIsNone(TERMINAL_CYCLE_CAP)

    def test_continue_until_clean_keeps_progressing_past_three_without_new_approval(self) -> None:
        session, entries, _clock = open_default()
        record_founder_authority(session, owner="founder", scope="this candidate")
        current = finding("one")
        review(session, entries, [current])
        heads = [(HEAD_B, TREE_B), (HEAD_C, TREE_C), (HEAD_D, TREE_D), (HEAD_E, TREE_E)]
        next_names = ["two", "three", "four", None]
        decision = None
        for (head, tree), name in zip(heads, next_names):
            remaining = [finding(name, paths=[f"src/{name}.py"])] if name else []
            _batch, decision = cycle(
                session,
                entries,
                new_head=head,
                new_tree=tree,
                remaining=remaining,
                touched=current["paths"],
            )
            if remaining:
                current = remaining[0]
            self.assertNotEqual(decision.status, STATUS_UNATTENDED_CHECKPOINT)
        self.assertEqual(session.repair_cycle_count, 4)
        self.assertEqual(decision.status, STATUS_REVIEW_CLEAN)


class AcU0909StallConditionsTests(unittest.TestCase):
    def test_repeated_unresolved_after_two_repairs_stalls(self) -> None:
        session, entries, _clock = open_default()
        review(session, entries, [finding("authz")])
        cycle(session, entries, new_head=HEAD_B, new_tree=TREE_B, remaining=[finding("authz")])
        _batch, decision = cycle(session, entries, new_head=HEAD_C, new_tree=TREE_C, remaining=[finding("authz")])
        self.assertEqual(decision.status, STATUS_REVIEW_STALLED)
        self.assertEqual(decision.reason, STALL_REPEATED_UNRESOLVED)
        self.assertTrue(decision.founder_packet_required)

    def test_two_no_progress_cycles_stall(self) -> None:
        session, entries, _clock = open_default()
        review(session, entries, [finding("noise", severity="P3"), finding("churn", severity="P3")])
        cycle(
            session,
            entries,
            new_head=HEAD_B,
            new_tree=TREE_B,
            remaining=[finding("noise", severity="P3"), finding("churn", severity="P3")],
        )
        _batch, decision = cycle(
            session,
            entries,
            new_head=HEAD_C,
            new_tree=TREE_C,
            remaining=[finding("noise", severity="P3"), finding("churn", severity="P3")],
        )
        self.assertEqual(decision.status, STATUS_REVIEW_STALLED)
        self.assertEqual(decision.reason, STALL_NO_PROGRESS)
        self.assertEqual(session.no_progress_streak, 2)

    def test_repair_reintroduction_stalls(self) -> None:
        session, entries, _clock = open_default()
        review(session, entries, [finding("authz"), finding("extra")])
        cycle(session, entries, new_head=HEAD_B, new_tree=TREE_B, remaining=[finding("extra")])
        self.assertTrue(any(entry.classification == "corrected" for entry in entries))
        _batch, decision = cycle(
            session,
            entries,
            new_head=HEAD_C,
            new_tree=TREE_C,
            remaining=[finding("authz"), finding("extra")],
        )
        self.assertEqual(decision.status, STATUS_REVIEW_STALLED)
        self.assertEqual(decision.reason, STALL_REINTRODUCTION)

    def test_redesign_and_resource_limit_stall(self) -> None:
        session, entries, clock = open_default(resource_limit={"maxElapsedSeconds": 30})
        review(session, entries, [finding("redesign-me", redesign=True)])
        decision = evaluate_progress(session, entries, clock=clock)
        self.assertEqual(decision.status, STATUS_REVIEW_STALLED)
        self.assertEqual(decision.reason, STALL_REDESIGN)
        session, entries, clock = open_default(resource_limit={"maxElapsedSeconds": 10})
        review(session, entries, [finding("slow")])
        clock.advance(11)
        decision = evaluate_progress(session, entries, clock=clock)
        self.assertEqual(decision.status, STATUS_REVIEW_STALLED)
        self.assertEqual(decision.reason, STALL_RESOURCE_LIMIT)


class AcU0904And10SplitHistoryTests(unittest.TestCase):
    def test_split_retains_root_ledger_and_cannot_fabricate_progress(self) -> None:
        session, entries, _clock = open_default()
        review(session, entries, [finding("left"), finding("right")])
        units = authorize_split(
            session,
            entries,
            owner="founder",
            units=[{"unitId": "u1", "scope": ["src/left.py"]}, {"unitId": "u2", "scope": ["src/right.py"]}],
        )
        self.assertEqual(len(units), 2)
        self.assertTrue(all(unit["rootSessionId"] == session.root_session_id for unit in units))
        self.assertTrue(all(unit["repairCycleCount"] == 0 for unit in units))
        self.assertEqual(session.recovery_generation, 1)
        self.assertEqual([entry.finding.fingerprint for entry in entries], ["left", "right"])
        with self.assertRaises(ConvergenceError) as raised:
            authorize_split(session, entries, owner="founder", units=[{"unitId": "u3"}], recursive=True)
        self.assertEqual(raised.exception.code, "recursive_split_requires_new_authority")
        ingest_integration_review(
            session,
            entries,
            {
                "headSha": HEAD_A,
                "gitTree": TREE_A,
                "findings": [finding("left"), finding("right"), finding("join")],
            },
            actor=session.reviewer_actor,
            role="reviewer",
        )
        self.assertGreaterEqual(len(entries), 3)
        self.assertNotEqual(session.status, STATUS_REVIEW_CLEAN)
        packet = founder_decision_packet(session, entries)
        self.assertNotEqual(packet["status"], STATUS_REVIEW_CLEAN)
        self.assertEqual(len(packet["ledger"]["entries"]), len(entries))


class AcU0911SingleReviewerHoldTests(unittest.TestCase):
    def test_slow_reviewer_is_single_live_process_and_timeout_is_not_clean(self) -> None:
        session, _entries, clock = open_default()
        adapter = MemoryReviewer()
        lease = start_reviewer(session, adapter, wait_seconds=5, clock=clock)
        with self.assertRaises(ConvergenceError) as raised:
            start_reviewer(session, adapter, wait_seconds=5, clock=clock)
        self.assertEqual(raised.exception.code, "duplicate_reviewer")
        clock.advance(6)
        hold = timeout_reviewer(session, adapter, lease, clock=clock)
        self.assertEqual(hold["status"], STATUS_HOLD)
        self.assertEqual(hold["reason"], HOLD_REVIEWER_TIMEOUT)
        self.assertFalse(hold["clean"])
        self.assertNotEqual(session.status, STATUS_REVIEW_CLEAN)
        self.assertEqual(adapter.cancelled, [lease.lease_id])
        session, entries, _clock = open_default()
        with self.assertRaises(ConvergenceError) as raised:
            ingest_review(session, entries, None, actor=session.reviewer_actor, role="reviewer")
        self.assertEqual(raised.exception.code, HOLD_REVIEWER_SILENCE)
        self.assertEqual(session.status, STATUS_HOLD)


class AcU0912ExactHeadInvalidationTests(unittest.TestCase):
    def test_full_and_prior_review_become_stale_after_repair(self) -> None:
        session, entries, _clock = open_default(require_full_before_review=True)
        review(session, entries, [finding("authz")])
        self.assertTrue(session.prior_review["valid"])
        record_full_evidence(session, head_sha=HEAD_A)
        self.assertTrue(session.full_evidence["valid"])
        consolidate_repair_batch(session, entries)
        apply_repair(session, entries, new_head=HEAD_B, new_tree=TREE_B, touched_paths=["src/authz.py"])
        self.assertFalse(session.full_evidence["valid"])
        self.assertFalse(session.prior_review["valid"])
        self.assertTrue(session.prior_review["reusedForUnchangedPaths"])
        self.assertEqual(session.reusable_unchanged_evidence["invalidatedPaths"], ["src/authz.py"])
        self.assertEqual(session.full_evidence["headSha"], HEAD_B)
        review(session, entries, [])
        self.assertTrue(session.prior_review["valid"])
        self.assertEqual(session.prior_review["headSha"], HEAD_B)
        self.assertFalse(session.full_evidence["valid"])
        session, entries, _clock = open_default()
        review(session, entries, [finding("authz")])
        with self.assertRaises(ConvergenceError) as raised:
            record_full_evidence(session, head_sha=HEAD_A)
        self.assertEqual(raised.exception.code, "full_before_review")
        invalidate_evidence(session)
        self.assertFalse(session.prior_review["valid"])


class G0R5ADeliverySequencingTests(unittest.TestCase):
    def test_full_is_rejected_by_plan_and_transition_until_clean_review(self) -> None:
        session, entries, _clock = open_default()
        with self.assertRaises(ConvergenceError) as raised:
            plan_delivery(session, profile="full")
        self.assertEqual(raised.exception.code, "full_before_review")
        with self.assertRaises(ConvergenceError) as raised:
            transition_delivery(session, profile="full")
        self.assertEqual(raised.exception.code, "full_before_review")
        review(session, entries, [])
        self.assertEqual(plan_delivery(session, profile="full")["profile"], "full")
        record_full_evidence(session, head_sha=HEAD_A)
        with self.assertRaises(ConvergenceError) as raised:
            record_full_evidence(session, head_sha=HEAD_A, execution="hosted")
        self.assertEqual(raised.exception.code, "duplicate_full_execution")

    def test_full_first_requires_non_empty_policy_justification(self) -> None:
        with self.assertRaises(ConvergenceError) as raised:
            open_session(
                repository="linktrend/IDE-Development",
                base_sha=BASE,
                candidate_sha=HEAD_A,
                git_tree=TREE_A,
                scope=["src/"],
                reviewer_policy="default",
                implementer_actor="implementer",
                reviewer_actor="reviewer",
                require_full_before_review=True,
            )
        self.assertEqual(raised.exception.code, "full_first_justification_missing")
        session, _entries, _clock = open_default()
        with self.assertRaises(ConvergenceError) as raised:
            apply_repository_policy(session, {"requireFullBeforeReview": True})
        self.assertEqual(raised.exception.code, "full_first_justification_missing")
        apply_repository_policy(
            session,
            {
                "requireFullBeforeReview": True,
                "fullFirstJustification": "repository policy requires pre-review Full",
            },
        )
        record_full_evidence(session, head_sha=HEAD_A)

    def test_repaired_candidate_requires_focused_delta_review_and_reuses_unchanged_evidence(self) -> None:
        session, entries, _clock = open_default()
        review(session, entries, [finding("authz", paths=["src/authz.py"])])
        consolidate_repair_batch(session, entries)
        apply_repair(session, entries, new_head=HEAD_B, new_tree=TREE_B, touched_paths=["src/authz.py"])
        with self.assertRaises(ConvergenceError) as raised:
            plan_delivery(session, profile="full")
        self.assertEqual(raised.exception.code, "delta_review_required")
        with self.assertRaises(ConvergenceError) as raised:
            ingest_delta_review(
                session,
                entries,
                {"headSha": HEAD_B, "gitTree": TREE_B, "findings": []},
                actor=session.reviewer_actor,
                role="reviewer",
            )
        self.assertEqual(raised.exception.code, "focused_checks_required")
        record_focused_changed_path_checks(
            session,
            head_sha=HEAD_B,
            git_tree=TREE_B,
            changed_paths=["src/authz.py"],
            results=[{"command": "focused authz check", "exitCode": 0}],
        )
        ingest_delta_review(
            session,
            entries,
            {
                "headSha": HEAD_B,
                "gitTree": TREE_B,
                "changedPaths": ["src/authz.py"],
                "findings": [],
            },
            actor=session.reviewer_actor,
            role="reviewer",
            accepted_unchanged_evidence={
                "valid": True,
                "sourceHeadSha": HEAD_A,
                "paths": ["src/unchanged.py"],
            },
        )
        self.assertTrue(session.delta_review["valid"])
        self.assertTrue(session.delta_review["reusedUnchangedEvidence"])
        record_full_evidence(session, head_sha=HEAD_B)

    def test_local_cumulative_full_cannot_be_followed_by_hosted_full(self) -> None:
        session, entries, _clock = open_default()
        review(session, entries, [])
        record_full_evidence(session, head_sha=HEAD_A, execution="local")
        with self.assertRaises(ConvergenceError) as raised:
            record_full_evidence(session, head_sha=HEAD_A, execution="hosted")
        self.assertEqual(raised.exception.code, "duplicate_full_execution")


class AcU0913StopCannotBypassFindingsTests(unittest.TestCase):
    def test_stalled_packet_preserves_findings_and_cannot_be_clean(self) -> None:
        session, entries, _clock = open_default()
        review(session, entries, [finding("authz")])
        cycle(session, entries, new_head=HEAD_B, new_tree=TREE_B, remaining=[finding("authz")])
        cycle(session, entries, new_head=HEAD_C, new_tree=TREE_C, remaining=[finding("authz")])
        self.assertEqual(session.status, STATUS_REVIEW_STALLED)
        session.status = STATUS_REVIEW_CLEAN
        with self.assertRaises(ConvergenceError) as raised:
            evaluate_progress(session, entries)
        self.assertEqual(raised.exception.code, "findings_bypass")
        session.status = STATUS_REVIEW_STALLED
        packet = founder_decision_packet(session, entries)
        self.assertEqual(packet["status"], STATUS_REVIEW_STALLED)
        self.assertTrue(packet["ledger"]["entries"])
        self.assertTrue(packet["classes"]["repeated_findings"])
        apply_repository_policy(session, {"requireFullBeforeReview": False})
        with self.assertRaises(ConvergenceError) as raised:
            apply_repository_policy(session, {"terminalCycleCap": 3, "treatCycleCountAsTerminal": True})
        self.assertEqual(raised.exception.code, "arbitrary_terminal_cycle_cap")


class AcU0902And03PreservationTests(unittest.TestCase):
    def test_completed_work_and_findings_are_preserved_in_packet(self) -> None:
        session, entries, _clock = open_default()
        review(session, entries, [finding("keep"), finding("fix")])
        cycle(session, entries, new_head=HEAD_B, new_tree=TREE_B, remaining=[finding("keep")])
        packet = founder_decision_packet(session, entries)
        fingerprints = {row["fingerprint"] for row in packet["ledger"]["entries"]}
        self.assertEqual(fingerprints, {"keep", "fix"})
        self.assertTrue(any(row["classification"] == "corrected" for row in packet["ledger"]["entries"]))
        self.assertTrue(packet["tests"])
        self.assertEqual(ledger_to_dict(session, entries)["rootSessionId"], session.root_session_id)


class IndependentReviewRepairProbeTests(unittest.TestCase):
    """Adversarial regressions for each independent-review P1/P2 probe."""

    def test_p1_01_distinct_fingerprints_never_fuzzy_merge(self) -> None:
        session, entries, _clock = open_default()
        review(
            session,
            entries,
            [
                finding("authz", statement="missing tenant check on write", paths=["src/foo.py"]),
                finding("cache", statement="missing cache check on write", paths=["src/foo.py"]),
            ],
        )
        self.assertEqual(len(entries), 2)
        self.assertEqual([entry.finding.fingerprint for entry in entries], ["authz", "cache"])
        batch = consolidate_repair_batch(session, entries)
        self.assertEqual(batch.fingerprints, ["authz", "cache"])
        packet = founder_decision_packet(session, entries)
        self.assertEqual({row["fingerprint"] for row in packet["ledger"]["entries"]}, {"authz", "cache"})

    def test_p1_02_ingest_requires_exact_head_tree_and_path_list(self) -> None:
        session, entries, _clock = open_default()
        for payload in (
            {"findings": []},
            {"headSha": "", "gitTree": TREE_A, "findings": []},
            {"headSha": HEAD_A, "gitTree": "", "findings": []},
            {"headSha": HEAD_B, "gitTree": TREE_A, "findings": []},
            {"headSha": HEAD_A, "gitTree": TREE_B, "findings": []},
        ):
            with self.assertRaises(ConvergenceError) as raised:
                ingest_review(
                    session,
                    entries,
                    payload,
                    actor=session.reviewer_actor,
                    role="reviewer",
                )
            self.assertEqual(raised.exception.code, "stale_review")
            self.assertFalse(session.prior_review["valid"])
            self.assertEqual(session.repair_cycle_count, 0)
        with self.assertRaises(ConvergenceError) as raised:
            ingest_review(
                session,
                entries,
                {
                    "headSha": HEAD_A,
                    "gitTree": TREE_A,
                    "findings": [finding("authz", paths="src/authz.py")],
                },
                actor=session.reviewer_actor,
                role="reviewer",
            )
        self.assertEqual(raised.exception.code, HOLD_MALFORMED_OUTPUT)
        self.assertEqual(session.status, STATUS_HOLD)
        self.assertEqual(session.hold_reason, HOLD_MALFORMED_OUTPUT)
        self.assertEqual(session.repair_cycle_count, 0)
        self.assertFalse(session.prior_review["valid"])
        self.assertEqual(entries, [])

    def test_p1_02_repair_cancels_live_reviewer_and_rejects_omitted_head(self) -> None:
        session, entries, clock = open_default()
        review(session, entries, [finding("authz")])
        adapter = MemoryReviewer()
        lease = start_reviewer(session, adapter, wait_seconds=30, clock=clock)
        self.assertEqual(session.live_reviewer["status"], "running")
        consolidate_repair_batch(session, entries)
        apply_repair(
            session,
            entries,
            new_head=HEAD_B,
            new_tree=TREE_B,
            touched_paths=["src/authz.py"],
            reviewer_adapter=adapter,
        )
        self.assertIsNone(session.live_reviewer)
        self.assertEqual(adapter.cancelled, [lease.lease_id])
        self.assertFalse(session.prior_review["valid"])
        start_reviewer(session, adapter, wait_seconds=30, clock=clock)
        with self.assertRaises(ConvergenceError) as raised:
            ingest_review(
                session,
                entries,
                {"findings": []},
                actor=session.reviewer_actor,
                role="reviewer",
            )
        self.assertEqual(raised.exception.code, "stale_review")
        self.assertFalse(session.prior_review["valid"])

    def test_p1_03_apply_repair_fails_closed_after_unattended_and_stop_states(self) -> None:
        session, entries, _clock = open_default()
        current = finding("one")
        review(session, entries, [current])
        for (head, tree), name in zip(
            [(HEAD_B, TREE_B), (HEAD_C, TREE_C), (HEAD_D, TREE_D)],
            ["two", "three", "four"],
        ):
            nxt = finding(name, paths=[f"src/{name}.py"])
            cycle(
                session,
                entries,
                new_head=head,
                new_tree=tree,
                remaining=[nxt],
                touched=current["paths"],
            )
            current = nxt
        self.assertEqual(session.status, STATUS_UNATTENDED_CHECKPOINT)
        self.assertEqual(session.repair_cycle_count, 3)
        self.assertEqual(session.candidate_sha, HEAD_D)
        self.assertEqual(session.git_tree, TREE_D)
        stalled_head = session.candidate_sha
        stalled_tree = session.git_tree
        stalled_cycles = session.repair_cycle_count
        stalled_ledger = [entry.finding.fingerprint for entry in entries]
        consolidate_repair_batch(session, entries)
        with self.assertRaises(ConvergenceError) as raised:
            apply_repair(session, entries, new_head=HEAD_E, new_tree=TREE_E, touched_paths=["src/four.py"])
        self.assertEqual(raised.exception.code, "unattended_checkpoint")
        self.assertEqual(session.status, STATUS_UNATTENDED_CHECKPOINT)
        self.assertEqual(session.candidate_sha, stalled_head)
        self.assertEqual(session.git_tree, stalled_tree)
        self.assertEqual(session.repair_cycle_count, stalled_cycles)
        self.assertEqual([entry.finding.fingerprint for entry in entries], stalled_ledger)

        session, entries, _clock = open_default()
        review(session, entries, [finding("authz")])
        cycle(session, entries, new_head=HEAD_B, new_tree=TREE_B, remaining=[finding("authz")])
        cycle(session, entries, new_head=HEAD_C, new_tree=TREE_C, remaining=[finding("authz")])
        self.assertEqual(session.status, STATUS_REVIEW_STALLED)
        self.assertEqual(session.stall_reason, STALL_REPEATED_UNRESOLVED)
        consolidate_repair_batch(session, entries)
        with self.assertRaises(ConvergenceError) as raised:
            apply_repair(session, entries, new_head=HEAD_D, new_tree=TREE_D, touched_paths=["src/authz.py"])
        self.assertEqual(raised.exception.code, STATUS_REVIEW_STALLED)
        self.assertEqual(session.status, STATUS_REVIEW_STALLED)
        self.assertEqual(session.stall_reason, STALL_REPEATED_UNRESOLVED)
        self.assertEqual(session.candidate_sha, HEAD_C)
        self.assertEqual(session.git_tree, TREE_C)
        self.assertEqual(session.repair_cycle_count, 2)

        session, entries, _clock = open_default()
        review(session, entries, [finding("authz")])
        with self.assertRaises(ConvergenceError):
            ingest_review(session, entries, None, actor=session.reviewer_actor, role="reviewer")
        self.assertEqual(session.status, STATUS_HOLD)
        hold_head = session.candidate_sha
        consolidate_repair_batch(session, entries)
        with self.assertRaises(ConvergenceError) as raised:
            apply_repair(session, entries, new_head=HEAD_B, new_tree=TREE_B, touched_paths=["src/authz.py"])
        self.assertEqual(raised.exception.code, STATUS_HOLD)
        self.assertEqual(session.status, STATUS_HOLD)
        self.assertEqual(session.candidate_sha, hold_head)
        self.assertEqual(session.repair_cycle_count, 0)

    def test_p2_01_same_identity_severity_reduction_is_progress(self) -> None:
        session, entries, _clock = open_default()
        review(session, entries, [finding("authz", severity="P1")])
        cycle(
            session,
            entries,
            new_head=HEAD_B,
            new_tree=TREE_B,
            remaining=[finding("authz", severity="P2")],
        )
        decision = evaluate_progress(session, entries)
        self.assertTrue(decision.measurable_progress)
        self.assertEqual(session.no_progress_streak, 0)
        self.assertNotEqual(decision.reason, STALL_NO_PROGRESS)
        cycle(
            session,
            entries,
            new_head=HEAD_C,
            new_tree=TREE_C,
            remaining=[finding("authz", severity="P3")],
        )
        decision = evaluate_progress(session, entries)
        self.assertTrue(decision.measurable_progress)
        self.assertEqual(session.no_progress_streak, 0)
        self.assertNotEqual(session.status, STATUS_REVIEW_STALLED)
        self.assertEqual(entries[0].finding.severity, "P3")

    def test_p2_02_first_seen_on_touched_paths_is_introduced_by_repair(self) -> None:
        session, entries, _clock = open_default()
        review(session, entries, [finding("old", paths=["src/old.py"])])
        consolidate_repair_batch(session, entries)
        apply_repair(session, entries, new_head=HEAD_B, new_tree=TREE_B, touched_paths=["src/old.py"])
        review(
            session,
            entries,
            [
                finding("old", paths=["src/old.py"]),
                finding("new-on-touched", paths=["src/old.py"], statement="repair left a new defect"),
                finding("new-untouched", paths=["src/other.py"], statement="found on an untouched path"),
            ],
        )
        by_fp = {entry.finding.fingerprint: entry for entry in entries}
        self.assertEqual(by_fp["new-on-touched"].classification, CLASS_INTRODUCED_BY_REPAIR)
        self.assertEqual(by_fp["new-untouched"].classification, CLASS_NEWLY_DISCOVERED)
        self.assertEqual(by_fp["old"].classification, CLASS_REPEATED)

    def test_p2_03_compute_units_accounting_can_stall(self) -> None:
        session, entries, clock = open_default(resource_limit={"maxComputeUnits": 1})
        review(session, entries, [finding("slow")])
        accounted = record_compute_units(session, 1, clock=clock)
        self.assertEqual(accounted["status"], STATUS_REVIEW_STALLED)
        self.assertEqual(accounted["reason"], STALL_RESOURCE_LIMIT)
        self.assertEqual(session.compute_units, 1.0)
        decision = evaluate_progress(session, entries, clock=clock)
        self.assertEqual(decision.status, STATUS_REVIEW_STALLED)
        self.assertEqual(decision.reason, STALL_RESOURCE_LIMIT)
        packet = founder_decision_packet(session, entries, clock=clock)
        self.assertEqual(packet["status"], STATUS_REVIEW_STALLED)
        self.assertEqual(packet["reason"], STALL_RESOURCE_LIMIT)

    def test_p2_04_non_object_finding_is_hold_without_cycle(self) -> None:
        session, entries, _clock = open_default()
        with self.assertRaises(ConvergenceError) as raised:
            ingest_review(
                session,
                entries,
                {"headSha": HEAD_A, "gitTree": TREE_A, "findings": ["not-an-object"]},
                actor=session.reviewer_actor,
                role="reviewer",
            )
        self.assertEqual(raised.exception.code, HOLD_MALFORMED_OUTPUT)
        self.assertEqual(session.status, STATUS_HOLD)
        self.assertEqual(session.hold_reason, HOLD_MALFORMED_OUTPUT)
        self.assertEqual(session.repair_cycle_count, 0)
        self.assertFalse(session.prior_review["valid"])
        self.assertEqual(entries, [])

    def test_p1_04_empty_ledger_hold_stays_hold_and_blocks_evaluate_full_repair(self) -> None:
        session, entries, clock = open_default()
        adapter = MemoryReviewer()
        lease = start_reviewer(session, adapter, wait_seconds=5, clock=clock)
        clock.advance(6)
        hold = timeout_reviewer(session, adapter, lease, clock=clock)
        self.assertEqual(hold["status"], STATUS_HOLD)
        self.assertEqual(hold["reason"], HOLD_REVIEWER_TIMEOUT)
        self.assertFalse(hold["clean"])
        self.assertEqual(entries, [])
        decision = evaluate_progress(session, entries, clock=clock)
        self.assertEqual(decision.status, STATUS_HOLD)
        self.assertEqual(decision.reason, HOLD_REVIEWER_TIMEOUT)
        self.assertFalse(decision.continue_authorized)
        self.assertFalse(decision.measurable_progress)
        self.assertTrue(decision.founder_packet_required)
        self.assertEqual(session.status, STATUS_HOLD)
        self.assertEqual(session.hold_reason, HOLD_REVIEWER_TIMEOUT)
        self.assertNotEqual(session.status, STATUS_REVIEW_CLEAN)
        with self.assertRaises(ConvergenceError) as raised:
            record_full_evidence(session, head_sha=HEAD_A)
        self.assertEqual(raised.exception.code, STATUS_HOLD)
        consolidate_repair_batch(session, entries)
        with self.assertRaises(ConvergenceError) as raised:
            apply_repair(session, entries, new_head=HEAD_B, new_tree=TREE_B, touched_paths=["src/a.py"])
        self.assertEqual(raised.exception.code, STATUS_HOLD)
        self.assertEqual(session.candidate_sha, HEAD_A)
        self.assertEqual(session.git_tree, TREE_A)
        self.assertEqual(session.repair_cycle_count, 0)
        packet = founder_decision_packet(session, entries)
        self.assertEqual(packet["status"], STATUS_HOLD)
        self.assertNotEqual(packet["status"], STATUS_REVIEW_CLEAN)

        session, entries, _clock = open_default()
        with self.assertRaises(ConvergenceError) as raised:
            ingest_review(session, entries, None, actor=session.reviewer_actor, role="reviewer")
        self.assertEqual(raised.exception.code, HOLD_REVIEWER_SILENCE)
        self.assertEqual(session.status, STATUS_HOLD)
        decision = evaluate_progress(session, entries)
        self.assertEqual(decision.status, STATUS_HOLD)
        self.assertEqual(decision.reason, HOLD_REVIEWER_SILENCE)
        self.assertEqual(session.status, STATUS_HOLD)
        self.assertFalse(session.prior_review["valid"])
        with self.assertRaises(ConvergenceError) as raised:
            record_full_evidence(session, head_sha=HEAD_A)
        self.assertEqual(raised.exception.code, STATUS_HOLD)
        with self.assertRaises(ConvergenceError) as raised:
            apply_repair(session, entries, new_head=HEAD_B, new_tree=TREE_B, touched_paths=["src/a.py"])
        self.assertEqual(raised.exception.code, STATUS_HOLD)
        with self.assertRaises(ConvergenceError) as raised:
            review(session, entries, [])
        self.assertEqual(raised.exception.code, STATUS_HOLD)
        self.assertEqual(session.status, STATUS_HOLD)
        self.assertFalse(session.prior_review["valid"])

        session, entries, _clock = open_default()
        with self.assertRaises(ConvergenceError) as raised:
            ingest_review(
                session,
                entries,
                {
                    "headSha": HEAD_A,
                    "gitTree": TREE_A,
                    "findings": [finding("authz", paths="src/authz.py")],
                },
                actor=session.reviewer_actor,
                role="reviewer",
            )
        self.assertEqual(raised.exception.code, HOLD_MALFORMED_OUTPUT)
        decision = evaluate_progress(session, entries)
        self.assertEqual(decision.status, STATUS_HOLD)
        self.assertEqual(decision.reason, HOLD_MALFORMED_OUTPUT)
        self.assertEqual(session.status, STATUS_HOLD)
        self.assertEqual(entries, [])
        with self.assertRaises(ConvergenceError) as raised:
            record_full_evidence(session, head_sha=HEAD_A)
        self.assertEqual(raised.exception.code, STATUS_HOLD)
        with self.assertRaises(ConvergenceError) as raised:
            apply_repair(session, entries, new_head=HEAD_B, new_tree=TREE_B, touched_paths=["src/authz.py"])
        self.assertEqual(raised.exception.code, STATUS_HOLD)
        self.assertEqual(session.repair_cycle_count, 0)

    def test_p1_04_hold_with_findings_stays_hold_and_cannot_repair(self) -> None:
        session, entries, _clock = open_default()
        review(session, entries, [finding("authz")])
        with self.assertRaises(ConvergenceError):
            ingest_review(session, entries, None, actor=session.reviewer_actor, role="reviewer")
        self.assertEqual(session.status, STATUS_HOLD)
        self.assertEqual(session.hold_reason, HOLD_REVIEWER_SILENCE)
        self.assertEqual(entries[0].classification, CLASS_UNRESOLVED)
        decision = evaluate_progress(session, entries)
        self.assertEqual(decision.status, STATUS_HOLD)
        self.assertEqual(decision.reason, HOLD_REVIEWER_SILENCE)
        self.assertEqual(session.status, STATUS_HOLD)
        self.assertNotEqual(session.status, "in_progress")
        self.assertNotEqual(session.status, STATUS_REVIEW_CLEAN)
        consolidate_repair_batch(session, entries)
        with self.assertRaises(ConvergenceError) as raised:
            apply_repair(session, entries, new_head=HEAD_B, new_tree=TREE_B, touched_paths=["src/authz.py"])
        self.assertEqual(raised.exception.code, STATUS_HOLD)
        self.assertEqual(session.candidate_sha, HEAD_A)
        self.assertEqual(session.git_tree, TREE_A)
        self.assertEqual(session.repair_cycle_count, 0)
        self.assertEqual(entries[0].classification, CLASS_UNRESOLVED)
        with self.assertRaises(ConvergenceError) as raised:
            record_full_evidence(session, head_sha=HEAD_A)
        self.assertEqual(raised.exception.code, STATUS_HOLD)
        with self.assertRaises(ConvergenceError) as raised:
            review(session, entries, [])
        self.assertEqual(raised.exception.code, STATUS_HOLD)
        self.assertEqual(session.status, STATUS_HOLD)
        self.assertEqual(entries[0].classification, CLASS_UNRESOLVED)

    def test_p1_05_stalled_empty_ingest_preserves_repeated_and_infra_stops(self) -> None:
        session, entries, _clock = open_default()
        review(session, entries, [finding("authz")])
        cycle(session, entries, new_head=HEAD_B, new_tree=TREE_B, remaining=[finding("authz")])
        cycle(session, entries, new_head=HEAD_C, new_tree=TREE_C, remaining=[finding("authz")])
        self.assertEqual(session.status, STATUS_REVIEW_STALLED)
        self.assertEqual(session.stall_reason, STALL_REPEATED_UNRESOLVED)
        self.assertEqual(session.candidate_sha, HEAD_C)
        classifications = [entry.classification for entry in entries]
        fingerprints = [entry.finding.fingerprint for entry in entries]
        with self.assertRaises(ConvergenceError) as raised:
            review(session, entries, [])
        self.assertEqual(raised.exception.code, STATUS_REVIEW_STALLED)
        self.assertEqual(session.status, STATUS_REVIEW_STALLED)
        self.assertEqual(session.stall_reason, STALL_REPEATED_UNRESOLVED)
        self.assertNotEqual(session.status, STATUS_REVIEW_CLEAN)
        self.assertEqual([entry.classification for entry in entries], classifications)
        self.assertEqual([entry.finding.fingerprint for entry in entries], fingerprints)
        self.assertNotEqual(entries[0].classification, "corrected")
        self.assertEqual(session.candidate_sha, HEAD_C)
        self.assertEqual(session.git_tree, TREE_C)

        session, entries, _clock = open_default()
        record_preflight(session, [{"path": "bundle/a", "problem": "secret"}])
        record_preflight(session, [{"path": "bundle/b", "problem": "secret"}])
        with self.assertRaises(ConvergenceError):
            record_preflight(session, [{"path": "bundle/c", "problem": "secret"}])
        self.assertEqual(session.status, STATUS_REVIEW_STALLED)
        self.assertEqual(session.stall_reason, STALL_INFRA_EXHAUSTED)
        self.assertFalse(session.prior_review["valid"])
        with self.assertRaises(ConvergenceError) as raised:
            review(session, entries, [])
        self.assertEqual(raised.exception.code, STATUS_REVIEW_STALLED)
        self.assertEqual(session.status, STATUS_REVIEW_STALLED)
        self.assertEqual(session.stall_reason, STALL_INFRA_EXHAUSTED)
        self.assertNotEqual(session.status, STATUS_REVIEW_CLEAN)
        self.assertFalse(session.prior_review["valid"])
        self.assertEqual(entries, [])
        self.assertEqual(session.repair_cycle_count, 0)

    def test_p2_05_touched_paths_reject_string_empty_malformed_before_state_change(self) -> None:
        session, entries, _clock = open_default()
        review(session, entries, [finding("old", paths=["src/old.py"])])
        consolidate_repair_batch(session, entries)
        frozen_head = session.candidate_sha
        frozen_tree = session.git_tree
        frozen_cycles = session.repair_cycle_count
        frozen_touched = list(session.last_touched_paths)
        frozen_status = session.status
        frozen_batch = session.pending_batch
        for bad in (
            "src/old.py",
            "",
            [],
            [""],
            ["  "],
            ["src/old.py", ""],
            ["src/old.py", None],
            [["src/old.py"]],
            None,
            {"path": "src/old.py"},
        ):
            with self.assertRaises(ConvergenceError) as raised:
                apply_repair(
                    session,
                    entries,
                    new_head=HEAD_B,
                    new_tree=TREE_B,
                    touched_paths=bad,  # type: ignore[arg-type]
                )
            self.assertEqual(raised.exception.code, "invalid_touched_paths")
            self.assertEqual(session.candidate_sha, frozen_head)
            self.assertEqual(session.git_tree, frozen_tree)
            self.assertEqual(session.repair_cycle_count, frozen_cycles)
            self.assertEqual(session.last_touched_paths, frozen_touched)
            self.assertEqual(session.status, frozen_status)
            self.assertIs(session.pending_batch, frozen_batch)
            self.assertFalse(session.pending_batch.cycle_consumed)

        apply_repair(session, entries, new_head=HEAD_B, new_tree=TREE_B, touched_paths=["src/old.py"])
        review(
            session,
            entries,
            [
                finding("old", paths=["src/old.py"]),
                finding("new-on-touched", paths=["src/old.py"], statement="repair left a new defect"),
            ],
        )
        by_fp = {entry.finding.fingerprint: entry for entry in entries}
        self.assertEqual(by_fp["new-on-touched"].classification, CLASS_INTRODUCED_BY_REPAIR)
        self.assertEqual(by_fp["old"].classification, CLASS_REPEATED)
        decision = evaluate_progress(session, entries)
        self.assertEqual(decision.status, STATUS_REVIEW_STALLED)
        self.assertEqual(decision.reason, STALL_REINTRODUCTION)
        self.assertTrue(any(entry.classification == CLASS_INTRODUCED_BY_REPAIR for entry in entries))

    def test_p1_06_empty_ingest_after_consolidate_only_cannot_use_stale_pending_batch(self) -> None:
        """AC-U09-13 / AC-U09-06: consolidate-only empty ingest must not fabricate clean."""
        session, entries, _clock = open_default()
        review(session, entries, [finding("authz"), finding("hash")])
        self.assertEqual(session.status, STATUS_IN_PROGRESS)
        batch = consolidate_repair_batch(session, entries)
        self.assertFalse(batch.cycle_consumed)
        self.assertFalse(session.pending_batch.cycle_consumed)
        self.assertEqual(session.repair_cycle_count, 0)
        frozen_classifications = [entry.classification for entry in entries]
        frozen_fingerprints = [entry.finding.fingerprint for entry in entries]
        review(session, entries, [])
        self.assertNotEqual(session.status, STATUS_REVIEW_CLEAN)
        self.assertEqual(session.status, STATUS_IN_PROGRESS)
        self.assertEqual([entry.classification for entry in entries], frozen_classifications)
        self.assertEqual([entry.finding.fingerprint for entry in entries], frozen_fingerprints)
        self.assertTrue(all(entry.classification == CLASS_UNRESOLVED for entry in entries))
        self.assertFalse(any(entry.classification == CLASS_CORRECTED for entry in entries))
        self.assertEqual(session.candidate_sha, HEAD_A)
        self.assertEqual(session.git_tree, TREE_A)
        self.assertEqual(session.repair_cycle_count, 0)
        self.assertFalse(session.pending_batch.cycle_consumed)
        decision = evaluate_progress(session, entries)
        self.assertNotEqual(decision.status, STATUS_REVIEW_CLEAN)
        self.assertNotEqual(session.status, STATUS_REVIEW_CLEAN)

    def test_p1_06_repair_review_empty_ingest_still_marks_consumed_batch_corrected(self) -> None:
        """Legitimate apply_repair + empty review must still correct and clean."""
        session, entries, _clock = open_default()
        review(session, entries, [finding("authz"), finding("hash")])
        batch = consolidate_repair_batch(session, entries)
        apply_repair(
            session,
            entries,
            new_head=HEAD_B,
            new_tree=TREE_B,
            touched_paths=["src/authz.py", "src/hash.py"],
        )
        self.assertTrue(batch.cycle_consumed)
        self.assertEqual(session.repair_cycle_count, 1)
        review(session, entries, [])
        self.assertEqual(session.status, STATUS_REVIEW_CLEAN)
        self.assertTrue(all(entry.classification == CLASS_CORRECTED for entry in entries))
        decision = evaluate_progress(session, entries)
        self.assertEqual(decision.status, STATUS_REVIEW_CLEAN)
        self.assertEqual(session.candidate_sha, HEAD_B)
        self.assertEqual(session.git_tree, TREE_B)

    def test_p1_06_in_progress_empty_ingest_preserves_repeated_pending_batch(self) -> None:
        """in_progress + unconsumed pending_batch empty ingest must not erase repeated rows."""
        session, entries, _clock = open_default()
        review(session, entries, [finding("authz")])
        cycle(session, entries, new_head=HEAD_B, new_tree=TREE_B, remaining=[finding("authz")])
        self.assertEqual(entries[0].classification, CLASS_REPEATED)
        self.assertEqual(session.status, STATUS_IN_PROGRESS)
        batch = consolidate_repair_batch(session, entries)
        self.assertFalse(batch.cycle_consumed)
        self.assertIn("authz", batch.fingerprints)
        frozen_attempts = entries[0].repair_attempts
        review(session, entries, [])
        self.assertNotEqual(session.status, STATUS_REVIEW_CLEAN)
        self.assertEqual(session.status, STATUS_IN_PROGRESS)
        self.assertEqual(entries[0].classification, CLASS_REPEATED)
        self.assertEqual(entries[0].repair_attempts, frozen_attempts)
        self.assertEqual(session.candidate_sha, HEAD_B)
        self.assertEqual(session.git_tree, TREE_B)
        self.assertFalse(session.pending_batch.cycle_consumed)
        decision = evaluate_progress(session, entries)
        self.assertNotEqual(decision.status, STATUS_REVIEW_CLEAN)

    def test_p1_06_integration_empty_ingest_cannot_fabricate_clean_via_stale_batch(self) -> None:
        """Integration empty ingest must not erase ledger via stale pending_batch."""
        session, entries, _clock = open_default()
        review(session, entries, [finding("left"), finding("right")])
        authorize_split(
            session,
            entries,
            owner="founder",
            units=[{"unitId": "u1", "scope": ["src/left.py"]}, {"unitId": "u2", "scope": ["src/right.py"]}],
        )
        batch = consolidate_repair_batch(session, entries)
        self.assertFalse(batch.cycle_consumed)
        prior_count = len(entries)
        frozen_classifications = [entry.classification for entry in entries]
        ingest_integration_review(
            session,
            entries,
            {"headSha": HEAD_A, "gitTree": TREE_A, "findings": []},
            actor=session.reviewer_actor,
            role="reviewer",
        )
        self.assertEqual(len(entries), prior_count)
        self.assertEqual([entry.classification for entry in entries], frozen_classifications)
        self.assertTrue(all(entry.classification == CLASS_UNRESOLVED for entry in entries))
        self.assertNotEqual(session.status, STATUS_REVIEW_CLEAN)
        self.assertEqual(session.status, STATUS_IN_PROGRESS)
        self.assertEqual(session.repair_cycle_count, 0)
        self.assertFalse(session.pending_batch.cycle_consumed)
        packet = founder_decision_packet(session, entries)
        self.assertNotEqual(packet["status"], STATUS_REVIEW_CLEAN)
        self.assertEqual(len(packet["ledger"]["entries"]), len(entries))


if __name__ == "__main__":
    unittest.main()
