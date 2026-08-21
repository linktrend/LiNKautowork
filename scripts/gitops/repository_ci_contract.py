#!/usr/bin/env python3
"""Repository-owned CI trigger contract (WP-U07).

Enforces when Fast, Full, promotion, and trusted-governance profiles may run,
validates Full coverage/artifact/preflight/cache/affected-surface evidence, and
audits repository workflow triggers. Does not dictate application test commands.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.gitops.promotion_receipt_gate import verify_receipt_file, verify_receipt_payload

CONTRACT_REL = ".github/linktrend-repository-ci-contract.json"
CONTRACT_KIND = "repository-ci-contract"
MANIFEST_KIND = "ci-component-manifest"
AGGREGATE_CONTEXT_DEFAULT = "Linktrend Repository CI Gate"
SCHEMA_VERSION = 1

PROFILE_NONE = "none"
PROFILE_FAST = "fast"
PROFILE_FULL = "full"
PROFILE_PROMOTION = "promotion"
PROFILE_TRUSTED = "trusted-governance"

CLASS_TRUSTED = "trusted_governance_only"
CLASS_APPLICATION = "application"
CLASS_MIXED = "mixed"
CLASS_UNKNOWN = "unknown"

EVENT_CHECKPOINT_PUSH = "checkpoint_push"
EVENT_PHASE_PR = "phase_pr"
EVENT_SEALED_FULL = "sealed_full"
EVENT_PROMOTION = "promotion"
EVENT_SCHEDULED = "scheduled"

DEFAULT_EXPENSIVE_MARKERS = (
    "full",
    "matrix",
    "e2e",
    "integration",
    "browser",
    "playwright",
    "cypress",
    "docker",
    "build-and-test",
)

BROAD_TRIGGER_RE = re.compile(
    r"(?ms)^on:\s*\n(?:(?:[ \t]+.*\n)|(?:[ \t]*\n))*?(?:[ \t]+(?:pull_request|push):\s*(?:\n(?:[ \t]+.*\n)+)?|(?:pull_request|push)\s*:)",
)
PATH_FILTER_RE = re.compile(r"(?m)^[ \t]+paths:|^[ \t]+paths-ignore:")
BRANCH_FILTER_RE = re.compile(r"(?m)^[ \t]+branches:|^[ \t]+branches-ignore:")


class ContractError(Exception):
    """Fail-closed contract failure with a stable machine code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


def digest_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def digest_text(text: str) -> str:
    return digest_bytes(text.encode("utf-8"))


def digest_json(value: Any) -> str:
    return digest_text(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _is_sha40(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{40}", value or ""))


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ContractError("invalid_json", f"{path}: {exc}") from exc


def default_contract() -> dict[str, Any]:
    """Built-in contract used when a repository has not yet authored one."""
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": CONTRACT_KIND,
        "aggregateContext": AGGREGATE_CONTEXT_DEFAULT,
        "profiles": {
            "fast": {
                "id": "fast",
                "commands": [],
                "requiredCheckContexts": ["Linktrend Fast Checks"],
                "timeoutMinutes": 5,
            },
            "full": {
                "id": "full",
                "commands": [],
                "requiredCheckContexts": [AGGREGATE_CONTEXT_DEFAULT],
            },
            "promotion": {
                "id": "promotion",
                "commands": [],
                "requiredCheckContexts": [
                    "Branch Source Policy",
                    "Linktrend Receipt Gate",
                ],
            },
            "trusted-governance": {
                "id": "trusted-governance",
                "commands": [],
                "requiredCheckContexts": [AGGREGATE_CONTEXT_DEFAULT],
            },
        },
        "coverageComponents": [
            {
                "id": "governance-gate-contract",
                "mandatory": True,
                "category": "governance",
            },
            {
                "id": "application-tests",
                "mandatory": True,
                "category": "test",
            },
        ],
        "trustedGovernance": {
            "pathPrefixes": [
                ".github/workflows/",
                "core/github/",
                "core/managed-core/schemas/",
                "scripts/gitops/",
                "docs/contracts/",
            ],
            "requiredProofs": [
                "gate-contract",
                "workflow-syntax",
                "identity-receipt",
                "ruleset-migration",
                "rollback",
                "no-application-path",
            ],
        },
        "expensiveWorkflowMarkers": list(DEFAULT_EXPENSIVE_MARKERS),
    }


def validate_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(contract, Mapping):
        raise ContractError("contract_invalid", "not an object")
    if contract.get("schemaVersion") != SCHEMA_VERSION:
        raise ContractError("contract_schema", f"schemaVersion={contract.get('schemaVersion')}")
    if contract.get("kind") != CONTRACT_KIND:
        raise ContractError("contract_kind", str(contract.get("kind")))
    aggregate = contract.get("aggregateContext")
    if not isinstance(aggregate, str) or not aggregate.strip():
        raise ContractError("contract_aggregate_missing")
    profiles = contract.get("profiles")
    if not isinstance(profiles, Mapping):
        raise ContractError("contract_profiles_missing")
    for name in (PROFILE_FAST, PROFILE_FULL, PROFILE_PROMOTION, PROFILE_TRUSTED):
        if name not in profiles or not isinstance(profiles[name], Mapping):
            raise ContractError("contract_profile_missing", name)
    components = contract.get("coverageComponents")
    if not isinstance(components, list) or not components:
        raise ContractError("contract_coverage_missing")
    ids: set[str] = set()
    for component in components:
        if not isinstance(component, Mapping):
            raise ContractError("contract_component_invalid")
        cid = component.get("id")
        if not isinstance(cid, str) or not cid:
            raise ContractError("contract_component_id")
        if cid in ids:
            raise ContractError("contract_component_duplicate", cid)
        ids.add(cid)
        if "mandatory" not in component:
            raise ContractError("contract_component_mandatory", cid)
    trusted = contract.get("trustedGovernance")
    if not isinstance(trusted, Mapping):
        raise ContractError("contract_trusted_missing")
    prefixes = trusted.get("pathPrefixes")
    proofs = trusted.get("requiredProofs")
    if not isinstance(prefixes, list) or not prefixes:
        raise ContractError("contract_trusted_paths")
    if not isinstance(proofs, list) or not proofs:
        raise ContractError("contract_trusted_proofs")
    return dict(contract)


def load_contract(root: Path, *, path: Path | None = None) -> dict[str, Any]:
    target = path or (root / CONTRACT_REL)
    if target.is_file():
        return validate_contract(load_json(target))
    return validate_contract(default_contract())


def normalize_repo_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def path_is_trusted(path: str, prefixes: Sequence[str]) -> bool:
    normalized = normalize_repo_path(path)
    return any(normalized == p.rstrip("/") or normalized.startswith(p) for p in prefixes)


def classify_changed_paths(
    changed_paths: Sequence[str],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    if not changed_paths:
        return {
            "classification": CLASS_UNKNOWN,
            "trustedPaths": [],
            "applicationPaths": [],
            "reason": "empty_or_unknown_change_set",
        }
    prefixes = list(contract["trustedGovernance"]["pathPrefixes"])
    trusted: list[str] = []
    application: list[str] = []
    for raw in changed_paths:
        path = normalize_repo_path(str(raw))
        if not path or path in {".", ".."} or any(part == ".." for part in path.split("/")):
            return {
                "classification": CLASS_UNKNOWN,
                "trustedPaths": trusted,
                "applicationPaths": application,
                "reason": "ambiguous_or_forged_path",
                "offender": path,
            }
        if path_is_trusted(path, prefixes):
            trusted.append(path)
        else:
            application.append(path)
    if trusted and not application:
        classification = CLASS_TRUSTED
    elif application and not trusted:
        classification = CLASS_APPLICATION
    else:
        classification = CLASS_MIXED
    return {
        "classification": classification,
        "trustedPaths": trusted,
        "applicationPaths": application,
        "reason": "classified",
    }


@dataclass
class ProfileDecision:
    profile: str
    startsManagedCompute: bool
    reason: str
    classification: str
    aggregateContext: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def select_profile(
    *,
    event: str,
    branch: str,
    changed_paths: Sequence[str] | None,
    contract: Mapping[str, Any],
    promotion_tree_unchanged: bool | None = None,
) -> ProfileDecision:
    aggregate = str(contract["aggregateContext"])
    branch_name = branch or ""

    if event == EVENT_CHECKPOINT_PUSH:
        if re.match(r"^issue/\d+-", branch_name) or branch_name.startswith("dev/"):
            return ProfileDecision(
                PROFILE_NONE,
                False,
                "checkpoint_push_no_managed_ci",
                CLASS_UNKNOWN,
                aggregate,
            )
        raise ContractError("checkpoint_branch_invalid", branch_name)

    classification_payload = classify_changed_paths(changed_paths or [], contract)
    classification = classification_payload["classification"]

    if event == EVENT_PHASE_PR:
        return ProfileDecision(
            PROFILE_FAST,
            True,
            "phase_pr_runs_fast",
            classification,
            aggregate,
        )

    if event == EVENT_PROMOTION:
        if promotion_tree_unchanged is False:
            raise ContractError("promotion_content_changed", "fail_before_merge")
        if promotion_tree_unchanged is not True:
            raise ContractError("promotion_identity_unknown")
        return ProfileDecision(
            PROFILE_PROMOTION,
            False,
            "unchanged_promotion_receipt_only",
            classification,
            aggregate,
        )

    if event == EVENT_SCHEDULED:
        return ProfileDecision(
            "scheduled",
            True,
            "scheduled_profile",
            classification,
            aggregate,
        )

    if event == EVENT_SEALED_FULL:
        if classification == CLASS_TRUSTED:
            return ProfileDecision(
                PROFILE_TRUSTED,
                True,
                "trusted_governance_only",
                classification,
                aggregate,
            )
        if classification in {CLASS_MIXED, CLASS_UNKNOWN, CLASS_APPLICATION}:
            return ProfileDecision(
                PROFILE_FULL,
                True,
                "full_required_for_classification",
                classification,
                aggregate,
            )
        return ProfileDecision(
            PROFILE_FULL,
            True,
            "full_default",
            classification,
            aggregate,
        )

    raise ContractError("event_unknown", event)


@dataclass
class AggregateGateResult:
    ok: bool
    code: str
    profile: str
    detail: str = ""
    labeledAsFull: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_aggregate_gate(
    *,
    contract: Mapping[str, Any],
    selected_profile: str,
    classification: str,
    governance_proofs: Sequence[str] | None = None,
    application_receipt: Mapping[str, Any] | None = None,
    coverage_manifest: Mapping[str, Any] | None = None,
    required_raw_full_context: bool = False,
    candidate_head: str | None = None,
) -> AggregateGateResult:
    aggregate = str(contract["aggregateContext"])
    if required_raw_full_context:
        return AggregateGateResult(
            False,
            "raw_full_context_forbidden",
            selected_profile,
            "branch protection must require the aggregate context only",
        )

    if selected_profile == PROFILE_TRUSTED:
        if classification != CLASS_TRUSTED:
            return AggregateGateResult(
                False,
                "trusted_profile_for_non_trusted_paths",
                selected_profile,
                classification,
            )
        required = set(contract["trustedGovernance"]["requiredProofs"])
        provided = set(governance_proofs or [])
        if not required.issubset(provided):
            return AggregateGateResult(
                False,
                "governance_profile_incomplete",
                selected_profile,
                ",".join(sorted(required - provided)),
            )
        if application_receipt is not None:
            # Prior application receipt may exist but must remain separately labeled.
            if application_receipt.get("profile") == PROFILE_TRUSTED:
                return AggregateGateResult(
                    False,
                    "governance_labeled_as_application",
                    selected_profile,
                )
        return AggregateGateResult(
            True,
            "trusted_governance_pass",
            selected_profile,
            aggregate,
            labeledAsFull=False,
        )

    if selected_profile != PROFILE_FULL:
        return AggregateGateResult(
            False,
            "aggregate_requires_full_or_trusted",
            selected_profile,
        )

    if classification == CLASS_TRUSTED:
        return AggregateGateResult(
            False,
            "trusted_must_not_use_full_label",
            selected_profile,
        )

    if not isinstance(application_receipt, Mapping):
        return AggregateGateResult(False, "application_receipt_missing", selected_profile)
    if application_receipt.get("conclusion") != "success":
        return AggregateGateResult(False, "application_receipt_unsuccessful", selected_profile)
    if application_receipt.get("profile") != PROFILE_FULL:
        return AggregateGateResult(False, "application_receipt_wrong_profile", selected_profile)
    receipt_head = application_receipt.get("candidateHead") or (
        (application_receipt.get("candidateIdentity") or {}).get("headCommit")
    )
    if candidate_head and receipt_head and receipt_head != candidate_head:
        return AggregateGateResult(False, "application_receipt_stale", selected_profile)
    if coverage_manifest is None:
        return AggregateGateResult(False, "coverage_manifest_missing", selected_profile)
    coverage = validate_coverage_manifest(
        contract,
        coverage_manifest,
        candidate_head=candidate_head or str(receipt_head or ""),
        candidate_tree=str(
            coverage_manifest.get("candidateTree")
            or (application_receipt.get("candidateIdentity") or {}).get("gitTree")
            or ""
        ),
    )
    if not coverage["ok"]:
        return AggregateGateResult(False, coverage["code"], selected_profile, coverage.get("detail", ""))
    return AggregateGateResult(
        True,
        "application_full_pass",
        selected_profile,
        aggregate,
        labeledAsFull=True,
    )


def validate_coverage_manifest(
    contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    candidate_head: str,
    candidate_tree: str,
) -> dict[str, Any]:
    if not isinstance(manifest, Mapping):
        return {"ok": False, "code": "coverage_manifest_invalid"}
    if manifest.get("schemaVersion") != SCHEMA_VERSION or manifest.get("kind") != MANIFEST_KIND:
        return {"ok": False, "code": "coverage_manifest_schema"}
    if not _is_sha40(str(manifest.get("candidateHead", ""))) or not _is_sha40(
        str(manifest.get("candidateTree", ""))
    ):
        return {"ok": False, "code": "coverage_manifest_identity"}
    if candidate_head and manifest.get("candidateHead") != candidate_head:
        return {"ok": False, "code": "coverage_manifest_wrong_head"}
    if candidate_tree and manifest.get("candidateTree") != candidate_tree:
        return {"ok": False, "code": "coverage_manifest_wrong_tree"}

    declared = {
        str(c["id"]): c
        for c in contract["coverageComponents"]
        if isinstance(c, Mapping) and c.get("mandatory")
    }
    rows = manifest.get("components")
    if not isinstance(rows, list):
        return {"ok": False, "code": "coverage_components_missing"}
    seen: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            return {"ok": False, "code": "coverage_component_row_invalid"}
        cid = row.get("id")
        if not isinstance(cid, str) or not cid:
            return {"ok": False, "code": "coverage_component_id"}
        seen[cid] = row

    for cid, declaration in declared.items():
        row = seen.get(cid)
        if row is None:
            return {"ok": False, "code": "coverage_component_absent", "detail": cid}
        status = row.get("status")
        if status == "passed":
            continue
        if status == "omitted":
            omission = row.get("omission")
            if not isinstance(omission, Mapping) or omission.get("authorized") is not True:
                return {"ok": False, "code": "coverage_omission_unauthorized", "detail": cid}
            for key in ("classifierDigest", "inputsDigest"):
                value = omission.get(key)
                if not isinstance(value, str) or not value.startswith("sha256:"):
                    return {"ok": False, "code": "coverage_omission_evidence", "detail": cid}
            continue
        return {"ok": False, "code": "coverage_component_unsuccessful", "detail": f"{cid}:{status}"}

    # Green wrapper alone is insufficient: every mandatory component must appear.
    if set(declared) - set(seen):
        return {"ok": False, "code": "coverage_incomplete"}
    return {"ok": True, "code": "coverage_ok", "mandatory": sorted(declared)}


def validate_artifact_file(
    *,
    artifact: Mapping[str, Any],
    file_path: Path | None,
    candidate_head: str,
    stdout_json: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    artifact_id = str(artifact.get("id") or "")
    if stdout_json is not None and file_path is None:
        return {
            "ok": False,
            "code": "artifact_stdout_only",
            "stdoutOnlyRejected": True,
            "artifactId": artifact_id,
        }
    if file_path is None or not file_path.is_file():
        return {"ok": False, "code": "artifact_missing", "artifactId": artifact_id}
    try:
        payload = load_json(file_path)
    except ContractError as exc:
        return {"ok": False, "code": exc.code, "detail": exc.detail, "artifactId": artifact_id}
    if not isinstance(payload, Mapping):
        return {"ok": False, "code": "artifact_not_object", "artifactId": artifact_id}
    expected_schema = artifact.get("schemaVersion")
    if expected_schema is not None and payload.get("schemaVersion") != expected_schema:
        return {"ok": False, "code": "artifact_wrong_schema", "artifactId": artifact_id}
    # Fail closed when the artifact itself omits identity. Never stamp the
    # caller's candidate_head as proof that the file was bound to the head.
    if "candidateHead" not in payload and "headCommit" not in payload:
        return {"ok": False, "code": "artifact_missing_head", "artifactId": artifact_id}
    head = payload.get("candidateHead") or payload.get("headCommit")
    if not isinstance(head, str) or not _is_sha40(head):
        return {"ok": False, "code": "artifact_missing_head", "artifactId": artifact_id}
    if not candidate_head or not _is_sha40(candidate_head):
        return {"ok": False, "code": "artifact_candidate_head_invalid", "artifactId": artifact_id}
    if head != candidate_head:
        return {"ok": False, "code": "artifact_wrong_head", "artifactId": artifact_id}
    return {
        "ok": True,
        "code": "artifact_ok",
        "artifactId": artifact_id,
        "path": str(file_path),
        "candidateHead": head,
    }


def run_component_preflight(
    *,
    component: Mapping[str, Any],
    environ: Mapping[str, str] | None = None,
    present_executables: Mapping[str, str] | None = None,
    successful_component_ids: Sequence[str] | None = None,
    invalidated_component_ids: Sequence[str] | None = None,
    bootstrap_runner: Any | None = None,
) -> dict[str, Any]:
    """Run declared runtime preflight, including bootstrap when required.

    When ``invalidated_component_ids`` is set, only those components are
    rechecked; unrelated successful component ids are retained and not resumed.
    """
    component_id = str(component.get("id") or "")
    retained = list(successful_component_ids or [])
    invalidated = {str(x) for x in (invalidated_component_ids or [])}
    if invalidated and component_id and component_id not in invalidated:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "kind": "ci-preflight-evidence",
            "componentId": component_id,
            "ok": True,
            "classification": "application",
            "bindings": [],
            "detail": "skipped_not_invalidated",
            "retainedComponentIds": retained,
            "resumedOnlyInvalidated": True,
            "bootstrap": {"ran": False},
        }

    env = dict(environ or os.environ)
    present = dict(present_executables or {})
    bindings: list[dict[str, Any]] = []
    ok = True
    detail = ""
    bootstrap_evidence: dict[str, Any] = {"ran": False}

    for requirement in component.get("runtime") or []:
        if not isinstance(requirement, Mapping):
            ok = False
            detail = "runtime_requirement_invalid"
            break
        binding = requirement.get("binding")
        rid = str(requirement.get("id") or "")
        kind = requirement.get("kind")
        bootstrap_cmd = requirement.get("bootstrapCommand")

        if isinstance(binding, Mapping):
            variable = str(binding.get("variable") or "")
            expected = str(binding.get("executablePath") or "")
            resolved = env.get(variable, "")
            matched = bool(resolved) and resolved == expected
            bindings.append(
                {
                    "variable": variable,
                    "resolvedPath": resolved,
                    "matched": matched,
                    "detail": rid,
                }
            )
            if not matched and rid not in present and isinstance(bootstrap_cmd, list) and bootstrap_cmd:
                runner = bootstrap_runner or _default_bootstrap_runner
                try:
                    result = runner(list(bootstrap_cmd), env=env)
                except Exception as exc:  # noqa: BLE001 - surface as infra failure
                    ok = False
                    detail = f"bootstrap_failed:{rid}:{exc}"
                    bootstrap_evidence = {
                        "ran": True,
                        "command": list(bootstrap_cmd),
                        "ok": False,
                        "detail": str(exc),
                    }
                    break
                bootstrap_evidence = {
                    "ran": True,
                    "command": list(bootstrap_cmd),
                    "ok": bool(result.get("ok")),
                    "verifiedVersion": result.get("verifiedVersion"),
                    "evidencePath": result.get("evidencePath"),
                    "resolvedPath": result.get("resolvedPath"),
                }
                if not result.get("ok"):
                    ok = False
                    detail = f"bootstrap_failed:{rid}"
                    break
                if result.get("resolvedPath"):
                    env[variable] = str(result["resolvedPath"])
                    resolved = env[variable]
                if result.get("verifiedVersion") and rid:
                    present[rid] = str(result["verifiedVersion"])
                matched = bool(resolved) and resolved == expected
                if expected and result.get("resolvedPath") and resolved == str(result["resolvedPath"]):
                    matched = True
                    expected = resolved
                bindings[-1] = {
                    "variable": variable,
                    "resolvedPath": resolved,
                    "matched": matched,
                    "detail": rid,
                    "bootstrap": True,
                }
                if not matched:
                    ok = False
                    detail = "binding_mismatch"
                    break
            elif not matched:
                ok = False
                detail = "binding_mismatch"
                break

        if kind in {"executable", "browser", "service"} and rid:
            if rid not in present:
                if isinstance(bootstrap_cmd, list) and bootstrap_cmd and not bootstrap_evidence.get("ran"):
                    runner = bootstrap_runner or _default_bootstrap_runner
                    try:
                        result = runner(list(bootstrap_cmd), env=env)
                    except Exception as exc:  # noqa: BLE001
                        ok = False
                        detail = f"bootstrap_failed:{rid}:{exc}"
                        bootstrap_evidence = {
                            "ran": True,
                            "command": list(bootstrap_cmd),
                            "ok": False,
                            "detail": str(exc),
                        }
                        break
                    bootstrap_evidence = {
                        "ran": True,
                        "command": list(bootstrap_cmd),
                        "ok": bool(result.get("ok")),
                        "verifiedVersion": result.get("verifiedVersion"),
                        "evidencePath": result.get("evidencePath"),
                        "resolvedPath": result.get("resolvedPath"),
                    }
                    if not result.get("ok"):
                        ok = False
                        detail = f"bootstrap_failed:{rid}"
                        break
                    if result.get("verifiedVersion"):
                        present[rid] = str(result["verifiedVersion"])
                if rid not in present:
                    ok = False
                    detail = f"missing_{kind}:{rid}"
                    break
            allowed = requirement.get("allowedVersions")
            if isinstance(allowed, list) and allowed:
                version = present[rid]
                if version not in allowed:
                    ok = False
                    detail = f"version_not_allowed:{rid}:{version}"
                    break

    classification = "infrastructure" if not ok else "application"
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "ci-preflight-evidence",
        "componentId": component_id,
        "ok": ok,
        "classification": classification,
        "bindings": bindings,
        "detail": detail,
        "retainedComponentIds": retained,
        "resumedOnlyInvalidated": bool(invalidated),
        "bootstrap": bootstrap_evidence,
    }


def _default_bootstrap_runner(command: list[str], *, env: Mapping[str, str]) -> dict[str, Any]:
    """Conservative default: refuse live bootstrap outside injected test runners."""
    del command, env
    return {
        "ok": False,
        "detail": "bootstrap_runner_required",
    }


def compute_cache_key(
    *,
    candidate_head: str,
    tracked_manifest_digest: str,
    lockfile_digest: str,
    workspace_mutated: bool = False,
) -> dict[str, Any]:
    if workspace_mutated:
        raise ContractError("cache_key_after_mutation")
    if not _is_sha40(candidate_head):
        raise ContractError("cache_key_candidate_invalid")
    if not tracked_manifest_digest.startswith("sha256:") or not lockfile_digest.startswith("sha256:"):
        raise ContractError("cache_key_input_digest")
    material = {
        "candidateHead": candidate_head,
        "trackedManifestDigest": tracked_manifest_digest,
        "lockfileDigest": lockfile_digest,
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "ci-cache-evidence",
        "candidateHead": candidate_head,
        "cacheKey": digest_json(material),
        "keyFixedBeforeMutation": True,
        "advisory": True,
        "warnings": [],
    }


def evaluate_cache_advisory(
    *,
    cache_key: str,
    restore_status: str,
    save_status: str,
    required_profile_ok: bool,
    required_component_failed: bool,
    broad_post_job_hash: bool = False,
) -> dict[str, Any]:
    warnings: list[str] = []
    rejected_broad = False
    if broad_post_job_hash:
        rejected_broad = True
        warnings.append("broad_post_job_cache_hash_rejected")
    if restore_status == "error":
        warnings.append("cache_restore_failed")
    if save_status == "error":
        warnings.append("cache_save_failed")
    if restore_status not in {"hit", "miss", "error", "skipped"}:
        warnings.append("cache_restore_unknown")
    # Cache never changes correctness conclusions.
    correctness_ok = required_profile_ok and not required_component_failed and not rejected_broad
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "ci-cache-evidence",
        "cacheKey": cache_key,
        "keyFixedBeforeMutation": True,
        "advisory": True,
        "restoreStatus": restore_status,
        "saveStatus": save_status,
        "warnings": warnings,
        "rejectedBroadHash": rejected_broad,
        "correctnessUnchanged": True,
        "ok": correctness_ok,
    }


def expand_reverse_dependencies(
    *,
    changed_paths: Sequence[str],
    dependency_graph: Mapping[str, Sequence[str]],
    package_export_paths: Sequence[str] | None = None,
    selected_profile: str = PROFILE_FULL,
) -> dict[str, Any]:
    """Expand shared-package changes through reverse dependencies.

    ``dependency_graph`` maps package -> consumers. Export-path hits force
    production-resolution and docker probes; typecheck alone is never enough.
    """
    if selected_profile not in {
        PROFILE_FAST,
        PROFILE_FULL,
        PROFILE_TRUSTED,
        PROFILE_PROMOTION,
        PROFILE_NONE,
    }:
        raise ContractError("affected_surface_profile_invalid", selected_profile)
    export_paths = [p.replace("\\", "/") for p in (package_export_paths or [])]
    normalized_paths = [normalize_repo_path(str(raw)) for raw in changed_paths]
    impacted: set[str] = set()
    export_hit = False
    for path in normalized_paths:
        for package, consumers in dependency_graph.items():
            package_prefix = package.rstrip("/") + "/"
            if path == package or path.startswith(package_prefix):
                impacted.update(consumers)
                if any(path == e or path.startswith(e.rstrip("/") + "/") or path.endswith(e) for e in export_paths) or any(
                    marker in path
                    for marker in (
                        "/exports/",
                        "package.json",
                        ".d.ts",
                        "/dist/",
                        "/build/",
                        "index.js",
                        "index.mjs",
                    )
                ):
                    export_hit = True
    required_probes: list[str] = []
    if export_hit or impacted:
        required_probes = ["production-resolution", "docker-import-build"]
    inputs = {
        "changedPaths": normalized_paths,
        "dependencyGraph": {k: list(v) for k, v in sorted(dependency_graph.items())},
        "packageExportPaths": export_paths,
    }
    evidence = {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "ci-affected-surface-evidence",
        "classifierDigest": digest_text("reverse-dependency-v1"),
        "inputsDigest": digest_json(inputs),
        "selectedProfile": selected_profile,
        "changedPaths": normalized_paths,
        "reverseDependencies": sorted(impacted),
        "requiredProbes": required_probes,
        "typecheckInsufficient": True,
        "exportHit": export_hit,
    }
    validate_affected_surface_evidence(evidence)
    return evidence


def validate_affected_surface_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Lightweight schema-complete check for affected-surface evidence."""
    required = (
        "schemaVersion",
        "kind",
        "classifierDigest",
        "inputsDigest",
        "selectedProfile",
        "changedPaths",
    )
    missing = [key for key in required if key not in evidence]
    if missing:
        raise ContractError("affected_surface_schema_incomplete", ",".join(missing))
    if evidence.get("schemaVersion") != SCHEMA_VERSION:
        raise ContractError("affected_surface_schema_version")
    if evidence.get("kind") != "ci-affected-surface-evidence":
        raise ContractError("affected_surface_kind")
    for digest_key in ("classifierDigest", "inputsDigest"):
        value = evidence.get(digest_key)
        if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
            raise ContractError("affected_surface_digest_invalid", digest_key)
    profile = evidence.get("selectedProfile")
    if profile not in {
        PROFILE_FAST,
        PROFILE_FULL,
        PROFILE_TRUSTED,
        PROFILE_PROMOTION,
        PROFILE_NONE,
    }:
        raise ContractError("affected_surface_profile_invalid", str(profile))
    paths = evidence.get("changedPaths")
    if not isinstance(paths, list) or not all(isinstance(p, str) and p for p in paths):
        raise ContractError("affected_surface_paths_invalid")
    return {"ok": True, "code": "affected_surface_schema_ok"}


def verify_promotion_exact_receipt(
    *,
    receipt_path: Path | None = None,
    receipt: Mapping[str, Any] | None = None,
    identity: Mapping[str, Any] | None = None,
    identity_path: Path | None = None,
    repo_path: Path | None = None,
    dependencies: Sequence[str] = (),
    expected_head: str | None = None,
) -> dict[str, Any]:
    """Promotion exact-receipt verification via promotion_receipt_gate.

    Missing, stale, and wrong-head receipts fail closed through the existing gate.
    """
    if receipt_path is None and receipt is None:
        return {
            "ok": False,
            "code": "promotion_receipt_missing",
            "accepted": False,
            "gate": "promotion_receipt_gate",
        }

    if receipt_path is not None:
        if not Path(receipt_path).is_file():
            return {
                "ok": False,
                "code": "promotion_receipt_missing",
                "accepted": False,
                "gate": "promotion_receipt_gate",
                "detail": str(receipt_path),
            }
        decision = verify_receipt_file(
            receipt_path,
            identity_path=identity_path,
            repo_path=repo_path,
            dependencies=list(dependencies),
            profile="full",
            required_gate="full-gate",
            workflow_head_commit=expected_head,
        )
    elif identity is None and identity_path is None and repo_path is None:
        return {
            "ok": False,
            "code": "promotion_receipt_missing",
            "accepted": False,
            "gate": "promotion_receipt_gate",
            "detail": "identity_missing",
        }
    else:
        assert receipt is not None
        if identity is None:
            return {
                "ok": False,
                "code": "promotion_receipt_missing",
                "accepted": False,
                "gate": "promotion_receipt_gate",
                "detail": "identity_missing",
            }
        decision = verify_receipt_payload(
            receipt,
            identity,
            "full-gate",
            workflow_head_commit=expected_head,
        )

    payload = decision.to_dict()
    code = str(payload.get("code") or "")
    if expected_head and payload.get("accepted"):
        receipt_head = None
        if receipt is not None:
            identity_obj = receipt.get("candidateIdentity")
            if isinstance(identity_obj, Mapping):
                receipt_head = identity_obj.get("headCommit")
        if identity is not None:
            receipt_head = receipt_head or identity.get("headCommit")
        if receipt_head and receipt_head != expected_head:
            return {
                "ok": False,
                "code": "promotion_receipt_wrong_head",
                "accepted": False,
                "gate": "promotion_receipt_gate",
                "detail": f"expected={expected_head}; receipt={receipt_head}",
            }
    if not payload.get("accepted"):
        mapped = code
        if code in {"invalid_receipt", "identity_missing"}:
            mapped = "promotion_receipt_missing"
        elif code in {"stale_head", "workflow_head_mismatch", "superseded_head"}:
            mapped = "promotion_receipt_stale"
        elif code in {"tree_mismatch", "head_mismatch"}:
            mapped = "promotion_receipt_wrong_head"
        return {
            "ok": False,
            "code": mapped,
            "accepted": False,
            "gate": "promotion_receipt_gate",
            "detail": payload.get("detail", ""),
            "upstreamCode": code,
        }
    return {
        "ok": True,
        "code": "promotion_receipt_accepted",
        "accepted": True,
        "gate": "promotion_receipt_gate",
        "detail": payload.get("detail", ""),
        "upstreamCode": code,
    }


def evaluate_promotion_with_receipt(
    *,
    contract: Mapping[str, Any],
    branch: str,
    promotion_tree_unchanged: bool,
    receipt_path: Path | None = None,
    receipt: Mapping[str, Any] | None = None,
    identity: Mapping[str, Any] | None = None,
    expected_head: str | None = None,
    repo_path: Path | None = None,
    dependencies: Sequence[str] = (),
) -> dict[str, Any]:
    """Select the promotion profile then enforce exact receipt via the gate."""
    decision = select_profile(
        event=EVENT_PROMOTION,
        branch=branch,
        changed_paths=[],
        contract=contract,
        promotion_tree_unchanged=promotion_tree_unchanged,
    )
    receipt_result = verify_promotion_exact_receipt(
        receipt_path=receipt_path,
        receipt=receipt,
        identity=identity,
        repo_path=repo_path,
        dependencies=dependencies,
        expected_head=expected_head,
    )
    return {
        "profile": decision.to_dict(),
        "receipt": receipt_result,
        "ok": decision.profile == PROFILE_PROMOTION and bool(receipt_result.get("ok")),
        "gate": "promotion_receipt_gate",
    }


def authorize_omission(
    *,
    classifier_digest: str | None,
    inputs_digest: str | None,
    authorized: bool,
    ambiguous: bool = False,
    forged: bool = False,
    stale: bool = False,
) -> dict[str, Any]:
    if forged:
        return {"ok": False, "code": "omission_forged"}
    if stale:
        return {"ok": False, "code": "omission_stale"}
    if ambiguous or not classifier_digest or not inputs_digest:
        return {"ok": False, "code": "omission_ambiguous_or_missing"}
    if not authorized:
        return {"ok": False, "code": "omission_unauthorized"}
    if not classifier_digest.startswith("sha256:") or not inputs_digest.startswith("sha256:"):
        return {"ok": False, "code": "omission_digest_invalid"}
    return {
        "ok": True,
        "code": "omission_authorized",
        "omission": {
            "authorized": True,
            "classifierDigest": classifier_digest,
            "inputsDigest": inputs_digest,
        },
    }


def innermost_diagnostic(failures: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Retain the innermost sanitized diagnostic rather than the outer wrapper."""
    if not failures:
        raise ContractError("diagnostic_missing")
    chosen = failures[-1]
    message = str(chosen.get("message") or "")
    if message.strip() in {"bash exited 1", "wrapper failed"}:
        # Prefer deeper evidence when the outer message is generic.
        for row in reversed(failures):
            if str(row.get("message") or "").strip() not in {"bash exited 1", "wrapper failed"}:
                chosen = row
                break
    return {
        "component": chosen.get("component"),
        "phase": chosen.get("phase"),
        "exit": chosen.get("exit"),
        "signal": chosen.get("signal"),
        "message": chosen.get("message"),
        "stdoutTail": chosen.get("stdoutTail"),
        "stderrTail": chosen.get("stderrTail"),
        "evidencePath": chosen.get("evidencePath"),
    }


def _workflow_looks_expensive(text: str, markers: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def _has_broad_promotion_trigger(text: str) -> bool:
    """Detect broad pull_request/push triggers that would fire on promotion PRs."""
    if "pull_request:" not in text and "push:" not in text:
        return False
    # Explicit promotion-only workflows are fine.
    if re.search(r"(?m)^[ \t]+branches:\s*\[?\s*['\"]?promote/", text):
        return False
    # An expensive PR workflow whose job is explicitly restricted to phase/*
    # heads cannot run for promote/* heads, even when its base is development.
    if re.search(
        r"startsWith\(github\.event\.pull_request\.head\.ref,\s*['\"]phase/['\"]\)",
        text,
    ):
        return False
    # Path filters alone do not protect promotion PRs that still match paths.
    has_pr_or_push = bool(re.search(r"(?m)^[ \t]*(pull_request|push)\s*:", text))
    if not has_pr_or_push:
        return False
    # If branches are limited to development-only without staging/main/promote, ok.
    branch_blocks = re.findall(
        r"(?ms)^[ \t]*(?:pull_request|push):\s*\n((?:[ \t]+.*\n)+)",
        text,
    )
    if not branch_blocks:
        # Bare `pull_request:` / `push:` without filters is broad.
        return True
    for block in branch_blocks:
        if "branches:" not in block and "branches-ignore:" not in block:
            return True
        if re.search(r"staging|main|promote/", block):
            return True
        # branches include only feature/development still fires for PRs into those bases.
        if "pull_request" in text and "branches:" in block:
            return True
    return False


def audit_workflow_triggers(
    workflows_dir: Path,
    *,
    contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    markers = list(
        (contract or default_contract()).get("expensiveWorkflowMarkers") or DEFAULT_EXPENSIVE_MARKERS
    )
    conflicts: list[dict[str, Any]] = []
    if not workflows_dir.is_dir():
        return {
            "ok": True,
            "conflicts": [],
            "scanned": 0,
            "detail": "workflows_dir_missing",
        }
    scanned = 0
    for path in sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml")):
        scanned += 1
        text = path.read_text(encoding="utf-8")
        expensive = _workflow_looks_expensive(text, markers)
        broad = _has_broad_promotion_trigger(text)
        if expensive and broad:
            conflicts.append(
                {
                    "path": str(path).replace("\\", "/"),
                    "code": "promotion_expensive_retrigger",
                    "detail": "broad pull_request/push would repeat expensive checks during promotion",
                }
            )
    return {
        "ok": not conflicts,
        "conflicts": conflicts,
        "scanned": scanned,
        "mayModify": False,
        "detail": "report_only_without_rollout_scope",
    }


def installer_audit_repository_ci_triggers(
    target_root: Path,
    *,
    mutate: bool = False,
    rollout_scope: bool = False,
) -> dict[str, Any]:
    """Installer-facing audit of repository-owned workflow triggers.

    Reports conflicts always. Mutates workflows only under explicit rollout scope.
    """
    contract = load_contract(target_root)
    result = audit_workflow_triggers(target_root / ".github" / "workflows", contract=contract)
    result["rolloutScope"] = bool(rollout_scope)
    result["mutated"] = False
    if mutate and not rollout_scope:
        raise ContractError("installer_mutate_requires_rollout_scope")
    if mutate and rollout_scope:
        # WP-U07 audits only; trigger rewrites belong to consumer rollout packets.
        result["mutated"] = False
        result["detail"] = "audit_only_preserve_test_commands"
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repository-owned CI trigger contract tools")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, default=Path.cwd())
    common.add_argument("--contract", type=Path)

    p = sub.add_parser("select-profile", parents=[common])
    p.add_argument("--event", required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--changed", action="append", default=[])
    p.add_argument("--promotion-tree-unchanged", choices=("true", "false"))

    g = sub.add_parser("evaluate-gate", parents=[common])
    g.add_argument("--profile", required=True)
    g.add_argument("--classification", required=True)
    g.add_argument("--proof", action="append", default=[])
    g.add_argument("--receipt", type=Path)
    g.add_argument("--manifest", type=Path)
    g.add_argument("--candidate-head")
    g.add_argument("--require-raw-full-context", action="store_true")

    c = sub.add_parser("validate-coverage", parents=[common])
    c.add_argument("--manifest", type=Path, required=True)
    c.add_argument("--candidate-head", required=True)
    c.add_argument("--candidate-tree", required=True)

    a = sub.add_parser("audit-triggers", parents=[common])
    a.add_argument("--workflows", type=Path)

    k = sub.add_parser("cache-key", parents=[common])
    k.add_argument("--candidate-head", required=True)
    k.add_argument("--tracked-digest", required=True)
    k.add_argument("--lockfile-digest", required=True)
    k.add_argument("--workspace-mutated", action="store_true")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    contract = load_contract(root, path=args.contract)
    try:
        if args.command == "select-profile":
            unchanged = None
            if args.promotion_tree_unchanged == "true":
                unchanged = True
            elif args.promotion_tree_unchanged == "false":
                unchanged = False
            decision = select_profile(
                event=args.event,
                branch=args.branch,
                changed_paths=args.changed,
                contract=contract,
                promotion_tree_unchanged=unchanged,
            )
            print(json.dumps(decision.to_dict(), sort_keys=True))
            return 0
        if args.command == "evaluate-gate":
            receipt = load_json(args.receipt) if args.receipt else None
            manifest = load_json(args.manifest) if args.manifest else None
            result = evaluate_aggregate_gate(
                contract=contract,
                selected_profile=args.profile,
                classification=args.classification,
                governance_proofs=args.proof,
                application_receipt=receipt,
                coverage_manifest=manifest,
                required_raw_full_context=args.require_raw_full_context,
                candidate_head=args.candidate_head,
            )
            print(json.dumps(result.to_dict(), sort_keys=True))
            return 0 if result.ok else 1
        if args.command == "validate-coverage":
            manifest = load_json(args.manifest)
            result = validate_coverage_manifest(
                contract,
                manifest,
                candidate_head=args.candidate_head,
                candidate_tree=args.candidate_tree,
            )
            print(json.dumps(result, sort_keys=True))
            return 0 if result.get("ok") else 1
        if args.command == "audit-triggers":
            workflows = args.workflows or (root / ".github" / "workflows")
            result = audit_workflow_triggers(workflows, contract=contract)
            print(json.dumps(result, sort_keys=True))
            return 0 if result.get("ok") else 1
        if args.command == "cache-key":
            result = compute_cache_key(
                candidate_head=args.candidate_head,
                tracked_manifest_digest=args.tracked_digest,
                lockfile_digest=args.lockfile_digest,
                workspace_mutated=args.workspace_mutated,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        raise ContractError("command_unknown", str(args.command))
    except ContractError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "detail": exc.detail}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
