#!/usr/bin/env python3
"""WP-U05 atomic workflow / ruleset / label / evaluator migration.

Treats managed workflows, coordination labels, readiness evaluator check-name
contracts, and live development/staging/main rulesets as one versioned
migration. Capability preflight is mandatory before mutation. Trusted-verifier
installation is separated from sealed product candidates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1

# Active check contexts published by managed workflows (job display names).
SOURCE_POLICY_CHECK = "Linktrend Branch Source Policy"
REVIEW_GATE_CHECK = "Linktrend Review Gate"
FAST_CHECKS = "Linktrend Fast Checks"
FULL_SUITE = "Linktrend Full Suite"
RECEIPT_GATE = "Linktrend Receipt Gate"
DEFAULT_VERIFY = "Verify IDE Development"

# Obsolete managed contexts that must never remain required or evaluated.
OBSOLETE_TO_ACTIVE: dict[str, str] = {
    "Enforce allowed PR source branches": SOURCE_POLICY_CHECK,
    "Branch Source Policy": SOURCE_POLICY_CHECK,
    "Linktrend Repository CI Gate": FULL_SUITE,
}
OBSOLETE_REMOVED = frozenset({"Cursor Bugbot", REVIEW_GATE_CHECK, "Linktrend Review Ready"})

ACTIVE_MANAGED_CHECKS = frozenset(
    {
        SOURCE_POLICY_CHECK,
        FAST_CHECKS,
        FULL_SUITE,
        RECEIPT_GATE,
        DEFAULT_VERIFY,
    }
)

GOVERNED_BRANCHES = ("development", "staging", "main")

CHECK_VAR_NAMES = (
    "LINKTREND_INTEGRATOR_REQUIRED_CHECKS",
    "LINKTREND_STAGING_GATE_CHECKS",
    "LINKTREND_RELEASE_GATE_CHECKS",
)

FULL_SUITE_LABEL = {
    "name": "linktrend-full-suite",
    "description": "Dispatch Linktrend Full Suite on an exact eligible Phase PR head",
    "color": "0E8A16",
}

NATIVE_PROTECTION_UNVERIFIED = "native_protection_unverified"
TRUSTED_GATE_UNAVAILABLE = "trusted_gate_version_unavailable"
MIGRATION_INCOMPLETE = "migration_incomplete"
REDUCED_ASSURANCE = "reduced_assurance"


class MigrationError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail or code
        super().__init__(self.code if not detail else f"{self.code}:{self.detail}")


@dataclass
class CapabilityReport:
    ok: bool
    code: str = ""
    detail: str = ""
    assurance: str = "protected"  # protected | reduced_assurance | unverified
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "code": self.code,
            "detail": self.detail,
            "assurance": self.assurance,
            "findings": list(self.findings),
        }


def derive_active_check_contract(
    *,
    release_id: str = "v2.4.0",
    verify_check: str = DEFAULT_VERIFY,
) -> dict[str, Any]:
    """Derive the managed check-name contract from the exact release identity."""

    if not str(release_id or "").strip():
        raise MigrationError("release_id_missing", "immutable release id is required")
    verify = str(verify_check or "").strip() or DEFAULT_VERIFY
    return {
        "schemaVersion": SCHEMA_VERSION,
        "releaseId": release_id,
        "aggregateContext": FULL_SUITE,
        "checks": {
            "sourcePolicy": SOURCE_POLICY_CHECK,
            "fastChecks": FAST_CHECKS,
            "fullSuite": FULL_SUITE,
            "receiptGate": RECEIPT_GATE,
            "verify": verify,
        },
        "obsoleteManaged": dict(OBSOLETE_TO_ACTIVE),
        "removedManaged": sorted(OBSOLETE_REMOVED),
        "variables": {
            "integrator": CHECK_VAR_NAMES[0],
            "staging": CHECK_VAR_NAMES[1],
            "release": CHECK_VAR_NAMES[2],
        },
        "requiredByBranch": {
            "development": [DEFAULT_VERIFY, SOURCE_POLICY_CHECK],
            "staging": [DEFAULT_VERIFY, SOURCE_POLICY_CHECK],
            "main": [DEFAULT_VERIFY, SOURCE_POLICY_CHECK],
        },
        "emission": {
            "sourcePolicy": {
                "workflow": "branch-source-policy.yml",
                "job": SOURCE_POLICY_CHECK,
                "events": ["pull_request:development", "workflow_call:promotion"],
            },
            "fastChecks": {
                "workflow": "linktrend-review-packager.yml",
                "job": FAST_CHECKS,
                "events": ["pull_request:development/phase"],
            },
            "fullSuite": {
                "workflow": "linktrend-integrator-merge.yml",
                "job": FULL_SUITE,
                "events": ["pull_request:labeled", "workflow_dispatch"],
            },
            "receiptGate": {
                "workflow": "linktrend-development-to-staging.yml|linktrend-staging-to-main.yml",
                "job": RECEIPT_GATE,
                "events": ["pull_request_target:promotion"],
            },
        },
        "labels": [dict(FULL_SUITE_LABEL)],
    }


def replace_obsolete_checks(names: Sequence[str]) -> list[str]:
    """Replace obsolete managed contexts; preserve order; drop duplicates."""

    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = str(raw or "").strip()
        if not name:
            continue
        if name in OBSOLETE_REMOVED:
            continue
        mapped = OBSOLETE_TO_ACTIVE.get(name, name)
        if mapped in seen:
            continue
        seen.add(mapped)
        out.append(mapped)
    return out


def strip_obsolete_managed(names: Sequence[str]) -> list[str]:
    """Drop obsolete managed names that have an active replacement."""

    obsolete = set(OBSOLETE_TO_ACTIVE) | set(OBSOLETE_REMOVED)
    return [n for n in names if n not in obsolete]


def capability_preflight(probe: Mapping[str, Any]) -> CapabilityReport:
    """Probe native protection before mutation (AC-U05-04 / AC-U05-16).

    Distinguishes classic ``protected`` flags from ruleset availability and
    never treats successful application checks as proof of native enforcement.
    """

    findings: list[str] = []
    data = dict(probe or {})

    http_status = data.get("httpStatus")
    if http_status in (403, "403"):
        return CapabilityReport(
            ok=False,
            code=NATIVE_PROTECTION_UNVERIFIED,
            detail="ruleset or protection API returned HTTP 403",
            assurance="unverified",
            findings=["http_403"],
        )

    if data.get("administrator") is False or data.get("missingPermission"):
        perm = data.get("missingPermission") or "administrator"
        return CapabilityReport(
            ok=False,
            code=NATIVE_PROTECTION_UNVERIFIED,
            detail=f"missing administrator permission: {perm}",
            assurance="unverified",
            findings=["missing_permission"],
        )

    branches = data.get("branches") if isinstance(data.get("branches"), Mapping) else {}
    for branch in GOVERNED_BRANCHES:
        entry = branches.get(branch) if isinstance(branches.get(branch), Mapping) else {}
        protected = entry.get("protected")
        if protected is False:
            findings.append(f"{branch}:protected_false")
        if entry.get("rulesetVisible") is False and entry.get("organizationRulesPresent"):
            findings.append(f"{branch}:org_rules_invisible")

    if data.get("organizationRulesVisible") is False and data.get("organizationRulesPresent"):
        findings.append("organization_rules_invisible")

    if findings:
        return CapabilityReport(
            ok=False,
            code=NATIVE_PROTECTION_UNVERIFIED,
            detail=";".join(findings),
            assurance="unverified",
            findings=findings,
        )

    if data.get("mechanism") in (None, "", "unavailable"):
        return CapabilityReport(
            ok=False,
            code=NATIVE_PROTECTION_UNVERIFIED,
            detail="protection mechanism unavailable",
            assurance="unverified",
            findings=["mechanism_unavailable"],
        )

    if data.get("reducedAssuranceRequested"):
        if not data.get("founderApproved"):
            return CapabilityReport(
                ok=False,
                code=REDUCED_ASSURANCE,
                detail="reduced assurance requires recorded founder approval",
                assurance="unverified",
                findings=["reduced_assurance_unapproved"],
            )
        return CapabilityReport(
            ok=True,
            code=REDUCED_ASSURANCE,
            detail="founder-approved reduced-assurance delivery",
            assurance="reduced_assurance",
            findings=["reduced_assurance_explicit"],
        )

    return CapabilityReport(ok=True, assurance="protected")


def detect_context_defects(
    *,
    required: Sequence[str],
    published: Sequence[Mapping[str, Any]] | Sequence[str],
    expected_events: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Detect missing, misspelled, duplicate, stale, skipped-only, wrong-event contexts."""

    defects: list[dict[str, Any]] = []
    req = [str(x).strip() for x in required if str(x).strip()]
    req_set = set(req)

    # Normalize published entries.
    entries: list[dict[str, Any]] = []
    for item in published:
        if isinstance(item, str):
            entries.append({"name": item, "conclusion": "success", "event": ""})
        elif isinstance(item, Mapping):
            entries.append(
                {
                    "name": str(item.get("name") or item.get("context") or "").strip(),
                    "conclusion": str(item.get("conclusion") or item.get("state") or "").lower(),
                    "event": str(item.get("event") or item.get("eventName") or "").strip(),
                    "head": str(item.get("head") or item.get("sha") or "").strip().lower(),
                    "expectedHead": str(
                        item.get("expectedHead") or item.get("expected_head") or ""
                    )
                    .strip()
                    .lower(),
                }
            )

    names = [e["name"] for e in entries if e["name"]]
    counts: dict[str, int] = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1

    for name, count in counts.items():
        if count > 1:
            defects.append({"kind": "duplicate", "context": name, "count": count})

    published_set = set(names)
    for name in req:
        if name not in published_set:
            # Misspelled near-miss: same when lowercased/stripped punctuation? keep simple.
            lower_map = {n.lower(): n for n in published_set}
            if name.lower() in lower_map and lower_map[name.lower()] != name:
                defects.append(
                    {
                        "kind": "misspelled",
                        "context": name,
                        "observed": lower_map[name.lower()],
                    }
                )
            else:
                defects.append({"kind": "missing", "context": name})

    for entry in entries:
        name = entry["name"]
        if not name:
            continue
        if name in OBSOLETE_TO_ACTIVE:
            defects.append(
                {
                    "kind": "stale",
                    "context": name,
                    "replacement": OBSOLETE_TO_ACTIVE[name],
                }
            )
        elif name in OBSOLETE_REMOVED:
            defects.append({"kind": "stale", "context": name, "replacement": None})
        conclusion = entry["conclusion"]
        if name in req_set and conclusion in {"skipped", "neutral", "cancelled"}:
            # Only skipped/neutral and never success for this context.
            siblings = [e for e in entries if e["name"] == name]
            if all(
                e["conclusion"] in {"skipped", "neutral", "cancelled", ""}
                for e in siblings
            ):
                defects.append({"kind": "skipped_only", "context": name})
        expected_head = entry.get("expectedHead") or ""
        head = entry.get("head") or ""
        if expected_head and head and expected_head != head and name in req_set:
            defects.append(
                {
                    "kind": "stale",
                    "context": name,
                    "detail": "wrong_head",
                    "observed": head,
                    "expected": expected_head,
                }
            )
        if expected_events and entry.get("event"):
            if entry["event"] not in set(expected_events) and name in req_set:
                defects.append(
                    {
                        "kind": "wrong_event",
                        "context": name,
                        "event": entry["event"],
                        "expectedEvents": list(expected_events),
                    }
                )

    # De-dupe identical defect dicts while preserving order.
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for d in defects:
        key = json.dumps(d, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique.append(d)
    return unique


def plan_three_branch_rename(
    branch_checks: Mapping[str, Sequence[str]],
    *,
    rename_map: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Plan replacing obsolete managed checks on all three branches together."""

    mapping = dict(rename_map or OBSOLETE_TO_ACTIVE)
    branches: dict[str, Any] = {}
    missing = [b for b in GOVERNED_BRANCHES if b not in branch_checks]
    if missing:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "complete": False,
            "code": MIGRATION_INCOMPLETE,
            "detail": f"missing branch plans: {','.join(missing)}",
            "branches": {},
            "actions": [],
        }

    actions: list[str] = []
    for branch in GOVERNED_BRANCHES:
        before = [str(x) for x in branch_checks[branch]]
        after = replace_obsolete_checks(before)
        # Ensure active renamed targets are present when an obsolete name existed.
        for old, new in mapping.items():
            if old in before and new not in after:
                after.append(new)
        changed = before != after
        action = "update" if changed else "noop"
        actions.append(f"{branch}:{action}")
        branches[branch] = {
            "action": action,
            "before": before,
            "after": after,
            "removed": [c for c in before if c not in after],
            "added": [c for c in after if c not in before],
        }

    return {
        "schemaVersion": SCHEMA_VERSION,
        "complete": True,
        "code": "",
        "branches": branches,
        "actions": actions,
        "renameMap": dict(mapping),
    }


def apply_atomic_branch_updates(
    plan: Mapping[str, Any],
    *,
    apply_branch,
    restore_branch,
) -> dict[str, Any]:
    """Apply branch updates; rollback prior successes if any later branch fails.

    ``apply_branch(branch, after_checks)`` mutates one branch.
    ``restore_branch(branch, before_checks)`` restores archived before-state.
    """

    if not plan.get("complete"):
        raise MigrationError(MIGRATION_INCOMPLETE, str(plan.get("detail") or "incomplete plan"))

    applied: list[str] = []
    mutations: list[dict[str, Any]] = []
    branches = plan.get("branches") or {}
    try:
        for branch in GOVERNED_BRANCHES:
            detail = branches.get(branch) or {}
            if detail.get("action") == "noop":
                continue
            apply_branch(branch, list(detail.get("after") or []))
            applied.append(branch)
            mutations.append(
                {
                    "op": "update_checks",
                    "branch": branch,
                    "after": list(detail.get("after") or []),
                }
            )
    except Exception as exc:  # noqa: BLE001 — convert to fail-closed migration result
        rollback: list[dict[str, Any]] = []
        for branch in reversed(applied):
            before = list((branches.get(branch) or {}).get("before") or [])
            restore_branch(branch, before)
            rollback.append({"op": "restore_checks", "branch": branch, "before": before})
        before_state = {
            branch: list((branches.get(branch) or {}).get("before") or [])
            for branch in GOVERNED_BRANCHES
        }
        receipt = build_migration_receipt(
            before_state=before_state,
            after_state={"status": "incomplete", "appliedBranches": list(applied)},
            status="incomplete",
            plan=plan,
        )
        return {
            "ok": False,
            "code": MIGRATION_INCOMPLETE,
            "detail": str(exc),
            "mutations": mutations,
            "rollback": rollback,
            "receipt": receipt,
            "falseSuccess": False,
        }

    before_state = {
        branch: list((branches.get(branch) or {}).get("before") or [])
        for branch in GOVERNED_BRANCHES
    }
    after_state = {
        branch: list((branches.get(branch) or {}).get("after") or [])
        for branch in GOVERNED_BRANCHES
    }
    return {
        "ok": True,
        "code": "",
        "mutations": mutations,
        "rollback": [],
        "receipt": build_migration_receipt(
            before_state=before_state,
            after_state=after_state,
            status="applied",
            plan=plan,
        ),
        "falseSuccess": False,
    }


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_migration_receipt(
    *,
    before_state: Mapping[str, Any],
    after_state: Mapping[str, Any],
    status: str,
    plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a non-mutating, digest-bound before/after migration receipt."""

    if status not in {"planned", "applied", "rolled_back", "incomplete"}:
        raise MigrationError("migration_receipt_status_invalid", status)
    before = deepcopy(dict(before_state))
    after = deepcopy(dict(after_state))
    receipt = {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "workflow-ruleset-migration-receipt",
        "status": status,
        "before": before,
        "after": after,
        "beforeDigest": _canonical_digest(before),
        "afterDigest": _canonical_digest(after),
        "rollbackAvailable": True,
        "planComplete": bool((plan or {}).get("complete", True)),
    }
    if plan is not None:
        receipt["plan"] = deepcopy(dict(plan))
    return receipt


def verify_migration_receipt(
    receipt: Mapping[str, Any],
    *,
    before_state: Mapping[str, Any] | None = None,
    after_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify receipt digests and optional live readback without mutating it."""

    if receipt.get("schemaVersion") != SCHEMA_VERSION or receipt.get("kind") != "workflow-ruleset-migration-receipt":
        return {"ok": False, "code": "migration_receipt_schema"}
    before = receipt.get("before")
    after = receipt.get("after")
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return {"ok": False, "code": "migration_receipt_state_missing"}
    if receipt.get("beforeDigest") != _canonical_digest(before):
        return {"ok": False, "code": "migration_receipt_before_mismatch"}
    if receipt.get("afterDigest") != _canonical_digest(after):
        return {"ok": False, "code": "migration_receipt_after_mismatch"}
    if before_state is not None and dict(before_state) != dict(before):
        return {"ok": False, "code": "migration_receipt_before_readback_mismatch"}
    if after_state is not None and dict(after_state) != dict(after):
        return {"ok": False, "code": "migration_receipt_after_readback_mismatch"}
    return {
        "ok": True,
        "code": "migration_receipt_verified",
        "status": receipt.get("status"),
        "beforeDigest": receipt.get("beforeDigest"),
        "afterDigest": receipt.get("afterDigest"),
    }


def reconcile_managed_labels(
    existing: Sequence[Mapping[str, Any]],
    *,
    desired: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create or reconcile managed coordination labels (AC-U05-11 / AC-U05-12)."""

    wanted = [dict(x) for x in (desired or [FULL_SUITE_LABEL])]
    by_name = {
        str(item.get("name") or "").strip(): dict(item)
        for item in existing
        if str(item.get("name") or "").strip()
    }
    actions: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []

    for label in wanted:
        name = str(label.get("name") or "").strip()
        if not name:
            problems.append({"kind": "invalid_desired", "detail": "empty name"})
            continue
        current = by_name.get(name)
        if current is None:
            # Detect near-miss / wrong-name managed labels.
            lower = name.lower()
            for other in by_name:
                if other.lower() == lower and other != name:
                    problems.append(
                        {
                            "kind": "wrong_name",
                            "desired": name,
                            "observed": other,
                        }
                    )
                    break
            else:
                actions.append({"op": "create", "label": dict(label)})
            continue

        conflict_fields = []
        for key in ("description", "color"):
            want = str(label.get(key) or "")
            have = str(current.get(key) or "")
            if want and have and want.lstrip("#").lower() != have.lstrip("#").lower():
                conflict_fields.append(key)
        if conflict_fields:
            problems.append(
                {
                    "kind": "conflicting_metadata",
                    "name": name,
                    "fields": conflict_fields,
                    "desired": {k: label.get(k) for k in conflict_fields},
                    "observed": {k: current.get(k) for k in conflict_fields},
                }
            )
        else:
            actions.append({"op": "noop", "name": name})

    ok = not problems
    return {
        "ok": ok,
        "complete": ok and all(a.get("op") in {"create", "noop"} for a in actions),
        "actions": actions,
        "problems": problems,
        "desired": wanted,
    }


def evaluate_label_application(
    *,
    label_name: str,
    pr: Mapping[str, Any],
    expected_head: str,
    eligible_heads: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Allow label application only on the verified exact eligible PR/head."""

    name = str(label_name or "").strip()
    if name != FULL_SUITE_LABEL["name"]:
        return {
            "ok": False,
            "code": "wrong_name",
            "detail": f"refusing unmanaged or wrong label {name!r}",
        }

    head = str(
        (pr.get("head") or {}).get("sha")
        if isinstance(pr.get("head"), Mapping)
        else pr.get("headSha") or pr.get("head") or ""
    ).strip().lower()
    expected = str(expected_head or "").strip().lower()
    if not expected or len(expected) != 40:
        return {"ok": False, "code": "expected_head_invalid", "detail": "exact head required"}
    if head != expected:
        return {
            "ok": False,
            "code": "stale_or_ineligible",
            "detail": f"pr head {head or 'missing'} != expected {expected}",
        }
    if eligible_heads is not None:
        allowed = {str(h).strip().lower() for h in eligible_heads}
        if expected not in allowed:
            return {
                "ok": False,
                "code": "stale_or_ineligible",
                "detail": "head not in eligible set for Full dispatch",
            }
    if pr.get("merged") or pr.get("state") in {"closed", "merged"}:
        return {"ok": False, "code": "stale_or_ineligible", "detail": "PR is not open"}
    return {"ok": True, "code": "", "label": name, "head": expected}


def migrate_evaluator_check_names(
    config: Mapping[str, Any],
    *,
    variables: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Replace stale Integrator/Packager/Promoter defaults and LINKTREND_*_CHECKS."""

    before = deepcopy(dict(config))
    after = deepcopy(before)
    changes: list[str] = []

    for key in (
        "integratorRequiredChecks",
        "packagerRequiredChecks",
        "promoterRequiredChecks",
        "observerRequiredChecks",
        "plannerRequiredChecks",
        "requiredChecks",
        "checks",
    ):
        if key in after and isinstance(after[key], list):
            replaced = replace_obsolete_checks(after[key])
            if replaced != after[key]:
                changes.append(key)
                after[key] = replaced
        elif key in after and isinstance(after[key], str):
            parts = [p.strip() for p in after[key].split(",") if p.strip()]
            replaced_list = replace_obsolete_checks(parts)
            replaced = ",".join(replaced_list)
            if replaced != after[key]:
                changes.append(key)
                after[key] = replaced

    var_in = dict(variables or after.get("repositoryVariables") or {})
    var_out: dict[str, str] = {}
    for name, value in var_in.items():
        if name in CHECK_VAR_NAMES or name.startswith("LINKTREND_") and name.endswith("_CHECKS"):
            parts = [p.strip() for p in str(value).split(",") if p.strip()]
            replaced = ",".join(replace_obsolete_checks(parts))
            var_out[name] = replaced
            if replaced != value:
                changes.append(f"var:{name}")
        else:
            var_out[name] = value
    if var_in:
        after["repositoryVariables"] = var_out

    # Reject any retained obsolete raw names in string fields commonly used by evaluators.
    def contains_raw_name(value: Any, target: str) -> bool:
        if isinstance(value, Mapping):
            return any(contains_raw_name(item, target) for item in value.values())
        if isinstance(value, (list, tuple)):
            return any(contains_raw_name(item, target) for item in value)
        return isinstance(value, str) and value == target

    retained = [old for old in OBSOLETE_TO_ACTIVE if contains_raw_name(after, old)]
    if retained:
        raise MigrationError(
            "stale_evaluator_contract",
            f"obsolete managed names remain: {','.join(retained)}",
        )

    return {
        "ok": True,
        "changed": bool(changes),
        "changes": changes,
        "before": before,
        "after": after,
    }


def plan_trusted_verifier_migration(
    *,
    trusted_base_verifier: str,
    candidate_verifier: str,
    sealed_candidate_head: str,
    sealed_candidate_tree: str,
    trusted_install_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Separate trusted-verifier install from the sealed product candidate (AC-U05-06/14/15)."""

    trusted = str(trusted_base_verifier or "").strip()
    candidate = str(candidate_verifier or "").strip()
    head = str(sealed_candidate_head or "").strip().lower()
    tree = str(sealed_candidate_tree or "").strip().lower()
    if not head or len(head) != 40 or not tree or len(tree) != 40:
        raise MigrationError("sealed_candidate_identity_invalid", "exact head/tree required")

    if trusted == candidate:
        return {
            "ok": True,
            "action": "noop",
            "code": "",
            "candidateUnchanged": True,
            "sealedCandidate": {"head": head, "tree": tree},
            "trustedVerifier": trusted,
        }

    # Candidate-only gate logic is never authoritative.
    if not trusted_install_evidence:
        return {
            "ok": False,
            "action": "require_trusted_migration",
            "code": TRUSTED_GATE_UNAVAILABLE,
            "detail": "corrected verifier exists only on untrusted candidate",
            "candidateUnchanged": True,
            "sealedCandidate": {"head": head, "tree": tree},
            "trustedVerifier": trusted,
            "candidateVerifier": candidate,
            "recovery": [
                "Install and validate the trusted verifier through a separate protected migration",
                "Prove the new trusted base executes the verifier",
                "Resume the unchanged sealed candidate receipt/proof lane",
                "Never copy the verifier repair onto the sealed product candidate",
            ],
        }

    evidence = dict(trusted_install_evidence)
    if evidence.get("status") != "installed" or evidence.get("verified") is not True:
        return {
            "ok": False,
            "action": "trusted_migration_failed",
            "code": TRUSTED_GATE_UNAVAILABLE,
            "detail": str(evidence.get("detail") or "trusted verifier migration failed"),
            "candidateUnchanged": True,
            "sealedCandidate": {"head": head, "tree": tree},
            "priorTrustedPreserved": True,
            "recovery": [
                "Restore or preserve the prior trusted gate",
                "Do not weaken identity checks",
                "Do not mutate the sealed candidate head/tree",
            ],
        }

    if str(evidence.get("installedVerifier") or "").strip() != candidate:
        return {
            "ok": False,
            "action": "trusted_migration_mismatch",
            "code": TRUSTED_GATE_UNAVAILABLE,
            "detail": "installed trusted verifier does not match required correction",
            "candidateUnchanged": True,
            "sealedCandidate": {"head": head, "tree": tree},
        }

    return {
        "ok": True,
        "action": "resume_unchanged_candidate",
        "code": "",
        "candidateUnchanged": True,
        "sealedCandidate": {"head": head, "tree": tree},
        "trustedVerifier": candidate,
        "evidence": evidence,
    }


def installation_complete(
    *,
    branch_required: Mapping[str, Sequence[str]],
    published_by_branch: Mapping[str, Sequence[Any]],
    labels: Sequence[Mapping[str, Any]],
    evaluator_config: Mapping[str, Any],
    capability: CapabilityReport,
    live_consumer_verified: bool | None = None,
) -> dict[str, Any]:
    """AC-U05-01/02/03/04 aggregate completeness (live AC-U05-17 optional)."""

    problems: list[str] = []
    if not capability.ok and capability.assurance == "unverified":
        problems.append(capability.code or NATIVE_PROTECTION_UNVERIFIED)
    if capability.assurance == "reduced_assurance":
        # Explicit reduced assurance is reportable completeness for that mode only.
        pass

    for branch in GOVERNED_BRANCHES:
        required = list(branch_required.get(branch) or [])
        if any(name in OBSOLETE_TO_ACTIVE for name in required):
            problems.append(f"{branch}:obsolete_required")
        defects = detect_context_defects(
            required=required,
            published=list(published_by_branch.get(branch) or []),
        )
        blocking = [d for d in defects if d.get("kind") in {"missing", "stale", "skipped_only", "wrong_event"}]
        if blocking:
            problems.append(f"{branch}:context_defects")

    label_plan = reconcile_managed_labels(labels)
    if not label_plan["ok"]:
        problems.append("managed_label_incomplete")

    try:
        migrate_evaluator_check_names(evaluator_config)
    except MigrationError as exc:
        problems.append(exc.code)

    if live_consumer_verified is False:
        problems.append("live_consumer_verification_pending")

    return {
        "complete": not problems,
        "problems": problems,
        "assurance": capability.assurance,
        "labelPlan": label_plan,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=("contract", "preflight", "plan-rename", "labels", "evaluators", "receipt", "trusted"),
        help="read-only planning / validation mode (never mutates GitHub)",
    )
    parser.add_argument("--input", help="JSON payload path (default stdin)")
    parser.add_argument("--output", help="Write JSON result to path")
    return parser.parse_args(argv)


def _load_input(path: str | None) -> dict[str, Any]:
    raw = sys.stdin.read() if not path else open(path, encoding="utf-8").read()
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise MigrationError("invalid_input", "expected JSON object")
    return data


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = _load_input(args.input)
        if args.mode == "contract":
            result = derive_active_check_contract(
                release_id=str(payload.get("releaseId") or "v2.4.0"),
                verify_check=str(payload.get("verifyCheck") or DEFAULT_VERIFY),
            )
        elif args.mode == "preflight":
            result = capability_preflight(payload).to_dict()
        elif args.mode == "plan-rename":
            result = plan_three_branch_rename(payload.get("branches") or {})
        elif args.mode == "labels":
            result = reconcile_managed_labels(payload.get("existing") or [])
        elif args.mode == "evaluators":
            result = migrate_evaluator_check_names(
                payload.get("config") or payload,
                variables=payload.get("variables"),
            )
        elif args.mode == "receipt":
            result = build_migration_receipt(
                before_state=payload.get("before") or payload.get("beforeState") or {},
                after_state=payload.get("after") or payload.get("afterState") or {},
                status=str(payload.get("status") or "planned"),
                plan=payload.get("plan"),
            )
        else:
            result = plan_trusted_verifier_migration(
                trusted_base_verifier=str(payload.get("trustedBaseVerifier") or ""),
                candidate_verifier=str(payload.get("candidateVerifier") or ""),
                sealed_candidate_head=str(payload.get("sealedCandidateHead") or ""),
                sealed_candidate_tree=str(payload.get("sealedCandidateTree") or ""),
                trusted_install_evidence=payload.get("trustedInstallEvidence"),
            )
        text = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(text)
        else:
            sys.stdout.write(text)
        if isinstance(result, dict) and result.get("ok") is False:
            return 1
        if isinstance(result, dict) and result.get("complete") is False:
            return 1
        return 0
    except MigrationError as exc:
        sys.stderr.write(f"{exc.code}:{exc.detail}\n")
        return 1
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        sys.stderr.write(f"invalid_input:{exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
