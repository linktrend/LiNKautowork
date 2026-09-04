#!/usr/bin/env python3
"""Managed repository protection planner / verifier / applier.

External-state tool for development, staging, and main protections.
Default mode is plan (no mutation). Apply requires an explicit --apply flag.

Live GitHub calls are skipped when --fixture-dir is set (tests / offline).
Never creates credentials or reads secret values.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_DRIFT = 3
EXIT_UNAVAILABLE = 4
EXIT_REFUSED = 5

RULESET_NAMES = {
    "development": "development-autonomous-merge",
    "staging": "staging-autonomous-promote",
    "main": "main-autonomous-release",
}

DEFAULT_FAST_GATE = ["Verify IDE Development"]
DEFAULT_STAGING_GATE = ["Verify IDE Development"]
DEFAULT_RELEASE_GATE = ["Verify IDE Development"]
# Active workflow job display name (WP-U05). Obsolete step title must not remain required.
SOURCE_POLICY_CHECK = "Linktrend Branch Source Policy"
REVIEW_GATE_CHECK = "Linktrend Review Gate"
BUGBOT_CHECK = REVIEW_GATE_CHECK  # compatibility name; never a required v2.5.1 gate
OBSOLETE_MANAGED_CHECKS = frozenset(
    {"Cursor Bugbot", "Linktrend Review Gate", "Linktrend Review Ready"}
)
RENAMED_MANAGED_CHECKS = {"Enforce allowed PR source branches": SOURCE_POLICY_CHECK}

GOVERNED = ("development", "staging", "main")


class ProtectionError(Exception):
    def __init__(self, message: str, exit_code: int = EXIT_FAILED) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _split_checks(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _unique_ordered(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def managed_baseline(
    branch: str,
    *,
    integrator_checks: list[str] | None = None,
    staging_checks: list[str] | None = None,
    release_checks: list[str] | None = None,
) -> list[str]:
    if branch == "development":
        fast = integrator_checks if integrator_checks else list(DEFAULT_FAST_GATE)
        return _unique_ordered([*fast, SOURCE_POLICY_CHECK])
    if branch == "staging":
        gate = staging_checks if staging_checks else list(DEFAULT_STAGING_GATE)
        return _unique_ordered([*gate, SOURCE_POLICY_CHECK])
    if branch == "main":
        gate = release_checks if release_checks else list(DEFAULT_RELEASE_GATE)
        return _unique_ordered([*gate, SOURCE_POLICY_CHECK])
    raise ProtectionError(f"ungoverned branch: {branch}")


def union_checks(managed: list[str], existing: list[str], extra: list[str] | None = None) -> dict[str, list[str]]:
    managed_u = _unique_ordered(managed)
    # Obsolete managed contexts are removed; renamed active checks are reconciled.
    mapped_existing = _unique_ordered(
        [RENAMED_MANAGED_CHECKS.get(c, c) for c in existing if c not in OBSOLETE_MANAGED_CHECKS]
    )
    extras = _unique_ordered(
        [*(extra or []), *[c for c in mapped_existing if c not in managed_u]]
    )
    preserved = [c for c in extras if c not in managed_u]
    preserved_sorted = sorted(preserved)
    desired = _unique_ordered([*managed_u, *preserved_sorted])
    return {
        "managed": managed_u,
        "preserved": preserved_sorted,
        "desired": desired,
    }


STATUS_CHECK_RULE_TYPE = "required_status_checks"

# Review / restriction (and similar) fields preserved from before-state on update.
_CLASSIC_PRESERVE_KEYS = (
    "required_pull_request_reviews",
    "restrictions",
    "required_conversation_resolution",
    "required_linear_history",
    "allow_fork_syncing",
    "lock_branch",
    "block_creations",
)


def _status_check_rule(checks: list[str]) -> dict[str, Any]:
    return {
        "type": STATUS_CHECK_RULE_TYPE,
        "parameters": {
            "strict_required_status_checks_policy": True,
            "do_not_enforce_on_create": False,
            "required_status_checks": [{"context": c} for c in checks],
        },
    }


def _writeable_ruleset_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Strip read-only identity fields; keep type + parameters (+ known extras)."""
    out: dict[str, Any] = {"type": rule["type"]}
    if "parameters" in rule:
        out["parameters"] = deepcopy(rule["parameters"])
    # Preserve optional flags GitHub accepts on write (e.g. ruleset rule metadata).
    for key in ("name", "ruleset_source_type", "ruleset_source"):
        if key in rule:
            out[key] = deepcopy(rule[key])
    return out


def merge_ruleset_rules(
    existing_rules: list[Any] | None,
    managed_check_rule: dict[str, Any],
) -> list[dict[str, Any]]:
    """Replace required_status_checks rules; preserve all other legitimate rules.

    Fail closed if a rule cannot be classified (missing/blank type) — never silently
    drop unknown rules when updating a managed check rule.
    """
    if existing_rules is None:
        return [deepcopy(managed_check_rule)]
    if not isinstance(existing_rules, list):
        raise ProtectionError(
            "ruleset rules must be a list; refusing update that would drop non-check rules",
            EXIT_FAILED,
        )

    preserved: list[dict[str, Any]] = []
    for idx, rule in enumerate(existing_rules):
        if not isinstance(rule, dict):
            raise ProtectionError(
                f"ruleset rule[{idx}] is not an object; refusing to drop non-check rules",
                EXIT_FAILED,
            )
        rtype = rule.get("type")
        if not isinstance(rtype, str) or not rtype.strip():
            raise ProtectionError(
                f"ruleset rule[{idx}] missing type; refusing to drop unclassified rule",
                EXIT_FAILED,
            )
        if rtype == STATUS_CHECK_RULE_TYPE:
            continue
        preserved.append(_writeable_ruleset_rule(rule))

    return [deepcopy(managed_check_rule), *preserved]


def ruleset_body(
    name: str,
    branch: str,
    checks: list[str],
    bypass_actors: list[Any] | None = None,
    *,
    existing_ruleset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    managed_rule = _status_check_rule(checks)
    if existing_ruleset is None:
        existing_rules: list[Any] | None = None
    elif "rules" not in existing_ruleset:
        raise ProtectionError(
            "existing ruleset missing rules array; refusing update that would drop non-check rules",
            EXIT_FAILED,
        )
    else:
        existing_rules = existing_ruleset.get("rules")
    rules = merge_ruleset_rules(existing_rules, managed_rule)
    return {
        "name": name,
        "target": "branch",
        "enforcement": "active",
        "conditions": {
            "ref_name": {
                "include": [f"refs/heads/{branch}"],
                "exclude": [],
            }
        },
        "rules": rules,
        "bypass_actors": list(bypass_actors or []),
    }


_CLASSIC_MANAGED_BOOL_KEYS = ("enforce_admins", "allow_force_pushes", "allow_deletions")
_CLASSIC_REVIEW_RESTRICTION_KEYS = ("required_pull_request_reviews", "restrictions")


def _classic_actor_id(item: Any, *, id_keys: tuple[str, ...], field: str) -> str:
    """Extract a PUT-ready actor id from a GET nested object or bare string."""
    if isinstance(item, str):
        if not item.strip():
            raise ProtectionError(
                f"classic protection field {field!r} has empty actor id; "
                "refusing to invent or drop actors on update",
                EXIT_FAILED,
            )
        return item
    if not isinstance(item, dict):
        raise ProtectionError(
            f"classic protection field {field!r} actor has unexpected type "
            f"{type(item).__name__}; refusing to null it on update",
            EXIT_FAILED,
        )
    for key in id_keys:
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val
    raise ProtectionError(
        f"classic protection field {field!r} actor missing "
        f"{'/'.join(id_keys)}; refusing to drop actors on update",
        EXIT_FAILED,
    )


def _classic_actor_list(items: Any, *, id_keys: tuple[str, ...], field: str) -> list[str]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise ProtectionError(
            f"classic protection field {field!r} must be a list; "
            f"got {type(items).__name__}",
            EXIT_FAILED,
        )
    return [_classic_actor_id(item, id_keys=id_keys, field=field) for item in items]


def _classic_bypass_allowances_for_put(value: Any) -> dict[str, list[str]]:
    if value is None:
        return {"users": [], "teams": [], "apps": []}
    if not isinstance(value, dict):
        raise ProtectionError(
            "bypass_pull_request_allowances has unexpected type "
            f"{type(value).__name__}; refusing to null it on update",
            EXIT_FAILED,
        )
    return {
        "users": _classic_actor_list(
            value.get("users"), id_keys=("login",), field="bypass_pull_request_allowances.users"
        ),
        "teams": _classic_actor_list(
            value.get("teams"), id_keys=("slug",), field="bypass_pull_request_allowances.teams"
        ),
        "apps": _classic_actor_list(
            value.get("apps"),
            id_keys=("slug", "login"),
            field="bypass_pull_request_allowances.apps",
        ),
    }


def _classic_field_for_put(key: str, value: Any) -> Any:
    """Normalize GET-shaped classic protection fields into PUT-compatible values."""
    if value is None:
        return None
    # PUT accepts bare booleans for several review-adjacent toggles.
    if isinstance(value, bool):
        return value
    if not isinstance(value, dict):
        raise ProtectionError(
            f"classic protection field {key!r} has unexpected type "
            f"{type(value).__name__}; refusing to null it on update",
            EXIT_FAILED,
        )

    if key == "required_pull_request_reviews":
        allowed = (
            "dismiss_stale_reviews",
            "require_code_owner_reviews",
            "required_approving_review_count",
            "require_last_push_approval",
            "bypass_pull_request_allowances",
        )
        out: dict[str, Any] = {}
        for k in allowed:
            if k not in value:
                continue
            if k == "bypass_pull_request_allowances":
                out[k] = _classic_bypass_allowances_for_put(value[k])
            else:
                out[k] = deepcopy(value[k])
        # Ignore url/html_url/enabled noise when real review fields are present.
        # Sparse GET shells (url/enabled only) have no preservable review policy —
        # fail closed rather than inventing required_approving_review_count.
        if not out:
            noise = {"url", "html_url", "enabled"}
            if set(value.keys()) <= noise and (
                "url" in value or "html_url" in value or "enabled" in value
            ):
                raise ProtectionError(
                    "classic required_pull_request_reviews GET payload has no "
                    "preservable review fields (url/enabled only); refusing to "
                    "invent required_approving_review_count on update",
                    EXIT_FAILED,
                )
            raise ProtectionError(
                "classic required_pull_request_reviews has no recognized "
                "preservable fields; refusing to null or invent policy on update",
                EXIT_FAILED,
            )
        return out

    if key == "restrictions":
        # Nested user/team/app objects + url noise are normal on GET; PUT wants ids only.
        return {
            "users": _classic_actor_list(
                value.get("users"), id_keys=("login",), field="restrictions.users"
            ),
            "teams": _classic_actor_list(
                value.get("teams"), id_keys=("slug",), field="restrictions.teams"
            ),
            "apps": _classic_actor_list(
                value.get("apps"), id_keys=("slug", "login"), field="restrictions.apps"
            ),
        }

    # Boolean-ish settings sometimes arrive as {"enabled": bool, "url": ...} from GET.
    if "enabled" in value and set(value.keys()) <= {"enabled", "url", "html_url"}:
        return bool(value.get("enabled"))

    return deepcopy(value)


def _classic_comparable_value(key: str, value: Any) -> Any:
    """Normalize a single classic field for semantic equality checks."""
    if value is None:
        return None
    if key == "required_status_checks":
        if not isinstance(value, dict):
            raise ProtectionError(
                f"classic protection field {key!r} has unexpected type "
                f"{type(value).__name__}; refusing update",
                EXIT_FAILED,
            )
        return {
            "strict": bool(value.get("strict", True)),
            "contexts": extract_classic_checks({"required_status_checks": value}),
        }
    if key in _CLASSIC_MANAGED_BOOL_KEYS:
        if isinstance(value, bool):
            return value
        return _classic_field_for_put(key, value)
    if key in _CLASSIC_PRESERVE_KEYS:
        return _classic_field_for_put(key, value)
    return deepcopy(value)


def classic_bodies_need_write(
    existing: dict[str, Any],
    desired: dict[str, Any],
) -> tuple[bool, str]:
    """Return whether a PUT is required to make existing match desired.

    Compares **semantic** equality only: desired PUT fields versus a normalized
    view of existing (GET or PUT shaped). Nested actors, url/html_url noise, and
    ``{enabled: bool}`` wrappers that normalize to the same values are **not**
    drift — live GitHub re-GETs stay nested, so structural inequality must not
    force perpetual update/verify failure.
    """
    drifted: list[str] = []

    for key, want in desired.items():
        raw = existing[key] if key in existing else None
        if raw is None and want is None:
            continue
        have = _classic_comparable_value(key, raw) if raw is not None else None
        if have != want:
            drifted.append(key)

    if not drifted:
        return False, ""

    if any(k in _CLASSIC_REVIEW_RESTRICTION_KEYS for k in drifted):
        return True, "review/restriction drift"
    return True, "classic protection drift: " + ",".join(drifted)


def classic_protection_body(
    checks: list[str],
    *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "required_status_checks": {
            "strict": True,
            "contexts": list(checks),
        },
        "enforce_admins": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }

    if existing is None:
        body["required_pull_request_reviews"] = None
        body["restrictions"] = None
        return body

    for key in _CLASSIC_PRESERVE_KEYS:
        if key not in existing:
            # Only force null for the historical PUT-required pair when absent on create.
            if key in ("required_pull_request_reviews", "restrictions"):
                body[key] = None
            continue
        body[key] = _classic_field_for_put(key, existing.get(key))

    # Always emit the PUT-required pair even if somehow omitted above.
    body.setdefault("required_pull_request_reviews", None)
    body.setdefault("restrictions", None)
    return body


def extract_ruleset_checks(ruleset: dict[str, Any] | None) -> list[str]:
    if not ruleset:
        return []
    out: list[str] = []
    for rule in ruleset.get("rules") or []:
        if rule.get("type") != STATUS_CHECK_RULE_TYPE:
            continue
        params = rule.get("parameters") or {}
        for item in params.get("required_status_checks") or []:
            ctx = item.get("context") if isinstance(item, dict) else None
            if ctx:
                out.append(ctx)
    return _unique_ordered(out)


def extract_classic_checks(protection: dict[str, Any] | None) -> list[str]:
    if not protection:
        return []
    rsc = protection.get("required_status_checks") or {}
    contexts = rsc.get("contexts") or rsc.get("checks") or []
    out: list[str] = []
    for item in contexts:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and item.get("context"):
            out.append(item["context"])
    return _unique_ordered(out)


class GitHubClient:
    """Thin gh api wrapper. FixtureClient replaces this in tests."""

    def __init__(self, repo: str) -> None:
        self.repo = repo

    def _api(self, method: str, path: str, input_obj: Any | None = None) -> tuple[int, Any, str]:
        cmd = ["gh", "api", "--method", method, path]
        if input_obj is not None:
            cmd.extend(["--input", "-"])
        proc = subprocess.run(
            cmd,
            input=json.dumps(input_obj) if input_obj is not None else None,
            text=True,
            capture_output=True,
        )
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return proc.returncode, None, err or (proc.stdout or "").strip()
        text = (proc.stdout or "").strip()
        if not text:
            return 0, None, ""
        try:
            return 0, json.loads(text), ""
        except json.JSONDecodeError:
            return 0, text, ""

    def list_rulesets(self) -> tuple[str, list[dict[str, Any]] | None, str]:
        code, data, err = self._api("GET", f"repos/{self.repo}/rulesets")
        if code != 0:
            low = err.lower()
            if "404" in low or "not found" in low or "ruleset" in low and "not available" in low:
                return "unavailable", None, err
            if "403" in low or "permission" in low:
                return "forbidden", None, err
            return "error", None, err
        if not isinstance(data, list):
            return "error", None, "unexpected rulesets payload"
        return "ok", data, ""

    def get_ruleset(self, ruleset_id: int) -> dict[str, Any] | None:
        code, data, _ = self._api("GET", f"repos/{self.repo}/rulesets/{ruleset_id}")
        if code != 0 or not isinstance(data, dict):
            return None
        return data

    def create_ruleset(self, body: dict[str, Any]) -> dict[str, Any]:
        code, data, err = self._api("POST", f"repos/{self.repo}/rulesets", body)
        if code != 0 or not isinstance(data, dict):
            raise ProtectionError(f"create ruleset failed: {err or data}")
        return data

    def update_ruleset(self, ruleset_id: int, body: dict[str, Any]) -> dict[str, Any]:
        code, data, err = self._api("PUT", f"repos/{self.repo}/rulesets/{ruleset_id}", body)
        if code != 0 or not isinstance(data, dict):
            raise ProtectionError(f"update ruleset {ruleset_id} failed: {err or data}")
        return data

    def delete_ruleset(self, ruleset_id: int) -> None:
        code, _, err = self._api("DELETE", f"repos/{self.repo}/rulesets/{ruleset_id}")
        if code != 0:
            raise ProtectionError(f"delete ruleset {ruleset_id} failed: {err}")

    def get_branch_protection(self, branch: str) -> tuple[str, dict[str, Any] | None, str]:
        code, data, err = self._api("GET", f"repos/{self.repo}/branches/{branch}/protection")
        if code != 0:
            low = err.lower()
            if "404" in low or "not protected" in low or "branch not protected" in low:
                return "absent", None, err
            if "403" in low:
                return "forbidden", None, err
            return "error", None, err
        if not isinstance(data, dict):
            return "error", None, "unexpected protection payload"
        return "ok", data, ""

    def put_branch_protection(self, branch: str, body: dict[str, Any]) -> dict[str, Any]:
        code, data, err = self._api("PUT", f"repos/{self.repo}/branches/{branch}/protection", body)
        if code != 0:
            raise ProtectionError(f"put branch protection {branch} failed: {err or data}")
        return data if isinstance(data, dict) else body

    def delete_branch_protection(self, branch: str) -> None:
        code, _, err = self._api("DELETE", f"repos/{self.repo}/branches/{branch}/protection")
        if code != 0 and "404" not in err.lower():
            raise ProtectionError(f"delete branch protection {branch} failed: {err}")

    def get_repo(self) -> dict[str, Any]:
        code, data, err = self._api("GET", f"repos/{self.repo}")
        if code != 0 or not isinstance(data, dict):
            raise ProtectionError(f"get repo failed: {err or data}")
        return data

    def patch_repo(self, fields: dict[str, Any]) -> dict[str, Any]:
        code, data, err = self._api("PATCH", f"repos/{self.repo}", fields)
        if code != 0 or not isinstance(data, dict):
            raise ProtectionError(f"patch repo failed: {err or data}")
        return data


class FixtureClient(GitHubClient):
    """Offline client driven by JSON fixtures. Never shells out to gh.

    When ``read_only=True`` (WP1 external-state plan/verify), all mutating
    methods raise ``ProtectionError`` with ``EXIT_REFUSED`` and never persist.
    """

    def __init__(self, repo: str, fixture_dir: Path, *, read_only: bool = False) -> None:
        super().__init__(repo)
        self.fixture_dir = fixture_dir
        self.read_only = read_only
        self.state = self._load()
        self.mutations: list[dict[str, Any]] = []

    def _refuse_mutation(self, op: str) -> None:
        if self.read_only:
            raise ProtectionError(
                f"repository_protection FixtureClient read_only refuses {op}",
                EXIT_REFUSED,
            )

    def _load(self) -> dict[str, Any]:
        path = self.fixture_dir / "state.json"
        if not path.is_file():
            raise ProtectionError(f"fixture state missing: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _persist(self) -> None:
        path = self.fixture_dir / "state.json"
        path.write_text(json.dumps(self.state, indent=2) + "\n", encoding="utf-8")

    def list_rulesets(self) -> tuple[str, list[dict[str, Any]] | None, str]:
        cap = self.state.get("capability", {})
        status = cap.get("rulesets", "ok")
        if status != "ok":
            return status, None, str(cap.get("rulesets_error", "rulesets unavailable"))
        return "ok", deepcopy(self.state.get("rulesets") or []), ""

    def get_ruleset(self, ruleset_id: int) -> dict[str, Any] | None:
        detail = (self.state.get("ruleset_details") or {}).get(str(ruleset_id))
        if detail:
            return deepcopy(detail)
        for rs in self.state.get("rulesets") or []:
            if rs.get("id") == ruleset_id:
                return deepcopy(rs)
        return None

    def create_ruleset(self, body: dict[str, Any]) -> dict[str, Any]:
        self._refuse_mutation("create_ruleset")
        new_id = int(self.state.get("next_ruleset_id") or 1000)
        self.state["next_ruleset_id"] = new_id + 1
        record = deepcopy(body)
        record["id"] = new_id
        self.state.setdefault("rulesets", []).append({"id": new_id, "name": body["name"]})
        self.state.setdefault("ruleset_details", {})[str(new_id)] = record
        self.mutations.append({"op": "create_ruleset", "body": deepcopy(body), "id": new_id})
        self._persist()
        return deepcopy(record)

    def update_ruleset(self, ruleset_id: int, body: dict[str, Any]) -> dict[str, Any]:
        self._refuse_mutation("update_ruleset")
        record = deepcopy(body)
        record["id"] = ruleset_id
        details = self.state.setdefault("ruleset_details", {})
        details[str(ruleset_id)] = record
        for rs in self.state.get("rulesets") or []:
            if rs.get("id") == ruleset_id:
                rs["name"] = body["name"]
        self.mutations.append({"op": "update_ruleset", "id": ruleset_id, "body": deepcopy(body)})
        self._persist()
        return deepcopy(record)

    def delete_ruleset(self, ruleset_id: int) -> None:
        self._refuse_mutation("delete_ruleset")
        self.state["rulesets"] = [r for r in (self.state.get("rulesets") or []) if r.get("id") != ruleset_id]
        (self.state.get("ruleset_details") or {}).pop(str(ruleset_id), None)
        self.mutations.append({"op": "delete_ruleset", "id": ruleset_id})
        self._persist()

    def get_branch_protection(self, branch: str) -> tuple[str, dict[str, Any] | None, str]:
        cap = self.state.get("capability", {})
        status = cap.get("branch_protection", "ok")
        if status == "forbidden":
            return "forbidden", None, "forbidden"
        if status == "unavailable":
            return "error", None, "branch protection unavailable"
        protections = self.state.get("branch_protections") or {}
        if branch not in protections:
            return "absent", None, "not protected"
        return "ok", deepcopy(protections[branch]), ""

    def put_branch_protection(self, branch: str, body: dict[str, Any]) -> dict[str, Any]:
        self._refuse_mutation("put_branch_protection")
        self.state.setdefault("branch_protections", {})[branch] = deepcopy(body)
        self.mutations.append({"op": "put_branch_protection", "branch": branch, "body": deepcopy(body)})
        self._persist()
        return deepcopy(body)

    def delete_branch_protection(self, branch: str) -> None:
        self._refuse_mutation("delete_branch_protection")
        (self.state.get("branch_protections") or {}).pop(branch, None)
        self.mutations.append({"op": "delete_branch_protection", "branch": branch})
        self._persist()

    def get_repo(self) -> dict[str, Any]:
        return deepcopy(self.state.get("repo") or {"allow_auto_merge": False})

    def patch_repo(self, fields: dict[str, Any]) -> dict[str, Any]:
        self._refuse_mutation("patch_repo")
        repo = self.state.setdefault("repo", {})
        repo.update(fields)
        self.mutations.append({"op": "patch_repo", "fields": deepcopy(fields)})
        self._persist()
        return deepcopy(repo)


def detect_mechanism(client: GitHubClient) -> dict[str, Any]:
    rs_status, rulesets, rs_err = client.list_rulesets()
    if rs_status == "ok":
        return {
            "rulesets": True,
            "branchProtection": "unknown",
            "mechanism": "rulesets",
            "rulesetsError": "",
            "rulesetSummaries": rulesets or [],
        }

    # Fail closed on permission/probe errors — do not invent classic BP while
    # rulesets may still exist but be unlistable with the current identity.
    if rs_status in {"forbidden", "error"}:
        return {
            "rulesets": False,
            "branchProtection": False,
            "mechanism": "unavailable",
            "rulesetsError": rs_err,
            "branchProtectionError": "",
            "rulesetSummaries": [],
        }

    bp_ok = False
    bp_err = ""
    # Probe one governed branch for classic protection capability.
    status, _, err = client.get_branch_protection("development")
    if status in ("ok", "absent"):
        bp_ok = True
    else:
        bp_err = err

    if bp_ok:
        return {
            "rulesets": False,
            "branchProtection": True,
            "mechanism": "branch_protection",
            "rulesetsError": rs_err,
            "branchProtectionError": "",
            "rulesetSummaries": [],
        }

    return {
        "rulesets": False,
        "branchProtection": False,
        "mechanism": "unavailable",
        "rulesetsError": rs_err,
        "branchProtectionError": bp_err,
        "rulesetSummaries": [],
    }


def _find_ruleset(
    client: GitHubClient,
    summaries: list[dict[str, Any]],
    name: str,
) -> dict[str, Any] | None:
    for item in summaries:
        if item.get("name") == name:
            rid = item.get("id")
            if rid is None:
                return deepcopy(item)
            detail = client.get_ruleset(int(rid))
            if detail is None:
                raise ProtectionError(
                    f"ruleset detail fetch failed for {name!r} (id={rid}); "
                    "refusing to treat missing rules as empty (would drop preserved checks)",
                    EXIT_UNAVAILABLE,
                )
            return detail
    return None


def build_plan(
    client: GitHubClient,
    *,
    branches: tuple[str, ...] = GOVERNED,
    integrator_checks: list[str] | None = None,
    staging_checks: list[str] | None = None,
    release_checks: list[str] | None = None,
    extra_checks: dict[str, list[str]] | None = None,
    development_checks_override: list[str] | None = None,
) -> dict[str, Any]:
    capability = detect_mechanism(client)
    mechanism = capability["mechanism"]
    repo = client.get_repo()
    allow_before = bool(repo.get("allow_auto_merge"))

    branch_plans: dict[str, Any] = {}
    rollback_branches: dict[str, Any] = {}
    actions_global: list[str] = []

    for branch in branches:
        name = RULESET_NAMES[branch]
        if development_checks_override is not None and branch == "development":
            # Compatibility path: caller supplied the full active check list.
            managed = _unique_ordered(
                [item for item in development_checks_override if item not in OBSOLETE_MANAGED_CHECKS]
            )
        else:
            managed = managed_baseline(
                branch,
                integrator_checks=integrator_checks,
                staging_checks=staging_checks,
                release_checks=release_checks,
            )

        extras = (extra_checks or {}).get(branch, [])
        action_reason = ""

        if mechanism == "rulesets":
            existing = _find_ruleset(client, capability.get("rulesetSummaries") or [], name)
            existing_checks = extract_ruleset_checks(existing)
            union = union_checks(managed, existing_checks, extras)
            bypass = list((existing or {}).get("bypass_actors") or [])
            desired_body = ruleset_body(
                name,
                branch,
                union["desired"],
                bypass_actors=bypass,
                existing_ruleset=existing,
            )
            before = {
                "exists": existing is not None,
                "id": (existing or {}).get("id"),
                "requiredChecks": existing_checks,
                "bypassActors": bypass,
                "body": existing,
            }
            if existing is None:
                action = "create"
            elif (
                existing_checks == union["desired"]
                and (existing or {}).get("enforcement", "active") == "active"
            ):
                action = "noop"
            else:
                action = "update"
            after = {
                "exists": True,
                "id": before["id"],
                "requiredChecks": union["desired"],
                "bypassActors": bypass,
                "body": desired_body,
            }
            rollback_branches[branch] = {
                "mechanism": "rulesets",
                "rulesetName": name,
                "before": before,
            }
        elif mechanism == "branch_protection":
            status, existing, _ = client.get_branch_protection(branch)
            existing_body = existing if status == "ok" else None
            existing_checks = extract_classic_checks(existing_body)
            union = union_checks(managed, existing_checks, extras)
            desired_body = classic_protection_body(
                union["desired"],
                existing=existing_body,
            )
            before = {
                "exists": existing_body is not None,
                "requiredChecks": existing_checks,
                "body": existing_body,
            }
            if existing_body is None:
                action = "create"
            elif existing_checks != union["desired"]:
                action = "update"
                action_reason = "required checks drift"
            else:
                needs_write, drift_reason = classic_bodies_need_write(
                    existing_body, desired_body
                )
                if needs_write:
                    action = "update"
                    action_reason = drift_reason or "classic protection drift"
                else:
                    action = "noop"
            after = {
                "exists": True,
                "requiredChecks": union["desired"],
                "body": desired_body,
            }
            rollback_branches[branch] = {
                "mechanism": "branch_protection",
                "before": before,
            }
        else:
            union = union_checks(managed, [], extras)
            before = {"exists": False, "requiredChecks": [], "body": None}
            after = {
                "exists": False,
                "requiredChecks": union["desired"],
                "body": ruleset_body(name, branch, union["desired"]),
            }
            action = "unavailable"
            rollback_branches[branch] = {"mechanism": "unavailable", "before": before}

        actions_global.append(f"{branch}:{action}")
        branch_entry: dict[str, Any] = {
            "rulesetName": name,
            "action": action,
            "requiredChecks": union,
            "before": before,
            "after": after,
        }
        if mechanism == "branch_protection" and action_reason:
            branch_entry["actionReason"] = action_reason
        branch_plans[branch] = branch_entry

    allow_action = "noop" if allow_before else "update"
    if "development" not in branches:
        allow_action = "noop"

    plan = {
        "schemaVersion": SCHEMA_VERSION,
        "repo": client.repo,
        "capability": {
            "rulesets": capability.get("rulesets"),
            "branchProtection": capability.get("branchProtection"),
            "mechanism": mechanism,
            "rulesetsError": capability.get("rulesetsError", ""),
            "branchProtectionError": capability.get("branchProtectionError", ""),
        },
        "branches": branch_plans,
        "repoSettings": {
            "allow_auto_merge": {
                "before": allow_before,
                "after": True if "development" in branches else allow_before,
                "action": allow_action if "development" in branches else "noop",
            }
        },
        "actions": actions_global,
        "rollback": {
            "snapshot": {
                "schemaVersion": SCHEMA_VERSION,
                "repo": client.repo,
                "mechanism": mechanism,
                "branches": rollback_branches,
                "repoSettings": {"allow_auto_merge": allow_before},
            },
            "instructions": [
                "Keep the plan JSON (especially rollback.snapshot) before any apply.",
                "To restore prior protections: "
                "./scripts/manage-repository-protections.sh --repo "
                f"{client.repo} rollback --snapshot <plan.json> --apply",
                "If mechanism was unavailable, restore manually in GitHub settings using the before payloads.",
                "Tools never store credentials; re-authenticate with an admin-capable operator identity if needed.",
            ],
        },
        "mutations": [],
    }
    return plan


def verify_plan(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    problems: list[str] = []
    mechanism = (plan.get("capability") or {}).get("mechanism")
    if mechanism == "unavailable":
        problems.append("protection mechanism unavailable")
        return False, problems
    for branch, detail in (plan.get("branches") or {}).items():
        action = detail.get("action")
        if action not in ("noop",):
            problems.append(f"{branch}: action={action} (not matched)")
        # Classic path: fail closed on review/restriction (and related) drift even when
        # required check contexts already match and action was misclassified as noop.
        if mechanism == "branch_protection":
            before_body = (detail.get("before") or {}).get("body")
            after_body = (detail.get("after") or {}).get("body")
            if before_body is not None and isinstance(after_body, dict):
                needs_write, drift_reason = classic_bodies_need_write(before_body, after_body)
                if needs_write:
                    reason = drift_reason or "classic protection drift"
                    msg = f"{branch}: {reason}"
                    if msg not in problems:
                        problems.append(msg)
    allow = (plan.get("repoSettings") or {}).get("allow_auto_merge") or {}
    if allow.get("action") not in ("noop",):
        problems.append(f"allow_auto_merge: action={allow.get('action')}")
    return len(problems) == 0, problems


def _apply_branch_mutation(
    client: GitHubClient,
    *,
    mechanism: str,
    branch: str,
    detail: dict[str, Any],
) -> dict[str, Any]:
    action = detail.get("action")
    if action == "noop":
        return {}
    if action == "unavailable":
        raise ProtectionError(f"cannot apply unavailable branch plan: {branch}", EXIT_UNAVAILABLE)
    after_body = (detail.get("after") or {}).get("body")
    if not after_body:
        raise ProtectionError(f"missing after body for {branch}")

    if mechanism == "rulesets":
        before = detail.get("before") or {}
        if action == "create" or before.get("id") is None:
            created = client.create_ruleset(after_body)
            return {"op": "create_ruleset", "branch": branch, "id": created.get("id")}
        rid = int(before["id"])
        client.update_ruleset(rid, after_body)
        return {"op": "update_ruleset", "branch": branch, "id": rid}
    if mechanism == "branch_protection":
        client.put_branch_protection(branch, after_body)
        return {"op": "put_branch_protection", "branch": branch}
    raise ProtectionError(f"unknown mechanism: {mechanism}")


def apply_plan(client: GitHubClient, plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply all governed branch mutations atomically (WP-U05).

    On failure after one or more branch updates, restore archived before-state
    for already-applied branches and refuse a false success.
    """

    mechanism = (plan.get("capability") or {}).get("mechanism")
    if mechanism == "unavailable":
        raise ProtectionError("cannot apply: protection mechanism unavailable", EXIT_UNAVAILABLE)

    mutations: list[dict[str, Any]] = []
    applied_branches: list[str] = []
    branch_details = plan.get("branches") or {}
    # Stable three-branch order — never claim success with only development updated.
    ordered = [b for b in GOVERNED if b in branch_details] + [
        b for b in branch_details if b not in GOVERNED
    ]

    try:
        for branch in ordered:
            detail = branch_details[branch]
            mutation = _apply_branch_mutation(
                client, mechanism=mechanism, branch=branch, detail=detail
            )
            if mutation:
                mutations.append(mutation)
                applied_branches.append(branch)

        allow = (plan.get("repoSettings") or {}).get("allow_auto_merge") or {}
        if allow.get("action") == "update" and allow.get("after") is True:
            client.patch_repo({"allow_auto_merge": True})
            mutations.append({"op": "patch_repo", "fields": {"allow_auto_merge": True}})
    except Exception as exc:
        snapshot = (plan.get("rollback") or {}).get("snapshot") or {}
        if applied_branches and snapshot:
            try:
                rollback_from_snapshot(client, snapshot)
            except Exception as rollback_exc:  # noqa: BLE001
                raise ProtectionError(
                    f"migration_incomplete after {applied_branches}: {exc}; "
                    f"rollback also failed: {rollback_exc}",
                    EXIT_FAILED,
                ) from rollback_exc
            raise ProtectionError(
                f"migration_incomplete after {applied_branches}: {exc}; rolled back",
                EXIT_FAILED,
            ) from exc
        raise

    return mutations


def rollback_from_snapshot(client: GitHubClient, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    mechanism = snapshot.get("mechanism")
    if mechanism == "unavailable":
        raise ProtectionError("cannot rollback: original mechanism unavailable", EXIT_UNAVAILABLE)

    mutations: list[dict[str, Any]] = []
    branches = snapshot.get("branches") or {}

    for branch, detail in branches.items():
        before = detail.get("before") or {}
        if mechanism == "rulesets":
            name = detail.get("rulesetName") or RULESET_NAMES[branch]
            # Refresh current id by name.
            cap = detect_mechanism(client)
            current = _find_ruleset(client, cap.get("rulesetSummaries") or [], name)
            if not before.get("exists"):
                if current and current.get("id") is not None:
                    client.delete_ruleset(int(current["id"]))
                    mutations.append({"op": "delete_ruleset", "branch": branch, "id": current["id"]})
                continue
            body = before.get("body")
            if not isinstance(body, dict):
                raise ProtectionError(f"rollback snapshot missing body for {branch}")
            # Strip id for write payload.
            write_body = {k: v for k, v in body.items() if k != "id"}
            if current and current.get("id") is not None:
                client.update_ruleset(int(current["id"]), write_body)
                mutations.append({"op": "update_ruleset", "branch": branch, "id": current["id"]})
            else:
                created = client.create_ruleset(write_body)
                mutations.append({"op": "create_ruleset", "branch": branch, "id": created.get("id")})
        elif mechanism == "branch_protection":
            if not before.get("exists"):
                client.delete_branch_protection(branch)
                mutations.append({"op": "delete_branch_protection", "branch": branch})
            else:
                body = before.get("body")
                if not isinstance(body, dict):
                    # Reconstruct from checks if only contexts known.
                    body = classic_protection_body(before.get("requiredChecks") or [])
                client.put_branch_protection(branch, body)
                mutations.append({"op": "put_branch_protection", "branch": branch})
        else:
            raise ProtectionError(f"unknown mechanism: {mechanism}")

    allow = (snapshot.get("repoSettings") or {}).get("allow_auto_merge")
    if allow is not None:
        client.patch_repo({"allow_auto_merge": bool(allow)})
        mutations.append({"op": "patch_repo", "fields": {"allow_auto_merge": bool(allow)}})

    return mutations


def resolve_check_overrides(args: argparse.Namespace) -> dict[str, Any]:
    integrator = _split_checks(
        args.integrator_checks
        or os.environ.get("LINKTREND_INTEGRATOR_REQUIRED_CHECKS")
    ) or None
    staging = _split_checks(
        args.staging_checks
        or os.environ.get("LINKTREND_STAGING_GATE_CHECKS")
    ) or None
    release = _split_checks(
        args.release_checks
        or os.environ.get("LINKTREND_RELEASE_GATE_CHECKS")
    ) or None
    return {
        "integrator_checks": integrator,
        "staging_checks": staging,
        "release_checks": release,
    }


def build_client(args: argparse.Namespace) -> GitHubClient:
    if args.fixture_dir:
        return FixtureClient(args.repo, Path(args.fixture_dir))
    return GitHubClient(args.repo)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan / verify / apply managed protections for development, staging, and main."
    )
    parser.add_argument(
        "mode",
        choices=("plan", "verify", "apply", "rollback"),
        help="plan (default intent), verify, apply, or rollback",
    )
    parser.add_argument("--repo", default=os.environ.get("GH_REPO", "linktrend/IDE-Development"))
    parser.add_argument(
        "--branches",
        default="development,staging,main",
        help="Comma-separated governed branches (default: all three)",
    )
    parser.add_argument("--integrator-checks", default=None, help="Comma-separated fast-gate checks")
    parser.add_argument("--staging-checks", default=None, help="Comma-separated staging-gate checks")
    parser.add_argument("--release-checks", default=None, help="Comma-separated release-gate checks")
    parser.add_argument(
        "--extra-checks",
        action="append",
        default=[],
        metavar="BRANCH=CHECK",
        help="Preserve/add a check on a branch (repeatable). Example: development=lint",
    )
    parser.add_argument(
        "--development-checks",
        nargs="*",
        default=None,
        help="Compatibility: full active development check list; obsolete managed gates are removed",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Required confirmation flag for apply/rollback mutations",
    )
    parser.add_argument(
        "--fixture-dir",
        default=None,
        help="Offline fixture directory (no live GitHub calls)",
    )
    parser.add_argument(
        "--snapshot",
        default=None,
        help="Path to a prior plan JSON for rollback mode",
    )
    parser.add_argument(
        "--json-output",
        default=None,
        help="Optional path to write the full JSON result",
    )
    return parser.parse_args(argv)


def _parse_extra_checks(items: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for raw in items:
        if "=" not in raw:
            raise ProtectionError(f"invalid --extra-checks value: {raw}")
        branch, check = raw.split("=", 1)
        branch = branch.strip()
        check = check.strip()
        if branch not in GOVERNED or not check:
            raise ProtectionError(f"invalid --extra-checks value: {raw}")
        out.setdefault(branch, []).append(check)
    return out


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        branches = tuple(
            b.strip() for b in args.branches.split(",") if b.strip()
        )
        for b in branches:
            if b not in GOVERNED:
                raise ProtectionError(f"ungoverned branch: {b}")

        client = build_client(args)
        overrides = resolve_check_overrides(args)
        extras = _parse_extra_checks(args.extra_checks)

        if args.mode == "rollback":
            if not args.apply:
                raise ProtectionError(
                    "rollback refuses to mutate without --apply (dry-run-first contract)",
                    EXIT_REFUSED,
                )
            if not args.snapshot:
                raise ProtectionError("--snapshot is required for rollback")
            payload = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
            snapshot = payload.get("rollback", {}).get("snapshot") or payload.get("snapshot") or payload
            mutations = rollback_from_snapshot(client, snapshot)
            result = {
                "schemaVersion": SCHEMA_VERSION,
                "mode": "rollback",
                "repo": args.repo,
                "dryRun": False,
                "mutations": mutations,
            }
            if isinstance(client, FixtureClient):
                result["fixtureMutations"] = client.mutations
            _emit(result, args.json_output)
            return EXIT_OK

        plan = build_plan(
            client,
            branches=branches,
            integrator_checks=overrides["integrator_checks"],
            staging_checks=overrides["staging_checks"],
            release_checks=overrides["release_checks"],
            extra_checks=extras,
            development_checks_override=args.development_checks,
        )
        plan["mode"] = args.mode
        plan["dryRun"] = args.mode in ("plan", "verify") or not args.apply

        if args.mode == "plan":
            _emit(plan, args.json_output)
            if (plan.get("capability") or {}).get("mechanism") == "unavailable":
                return EXIT_UNAVAILABLE
            return EXIT_OK

        if args.mode == "verify":
            ok, problems = verify_plan(plan)
            plan["verify"] = {"ok": ok, "problems": problems}
            _emit(plan, args.json_output)
            if (plan.get("capability") or {}).get("mechanism") == "unavailable":
                return EXIT_UNAVAILABLE
            return EXIT_OK if ok else EXIT_DRIFT

        if args.mode == "apply":
            if not args.apply:
                raise ProtectionError(
                    "apply refuses to mutate without --apply (dry-run-first contract)",
                    EXIT_REFUSED,
                )
            # Re-plan intent is already computed; mutate then re-verify via fresh plan.
            mutations = apply_plan(client, plan)
            plan["dryRun"] = False
            plan["mutations"] = mutations
            # Post-apply verification against the same client state.
            post = build_plan(
                client,
                branches=branches,
                integrator_checks=overrides["integrator_checks"],
                staging_checks=overrides["staging_checks"],
                release_checks=overrides["release_checks"],
                extra_checks=extras,
                development_checks_override=args.development_checks,
            )
            ok, problems = verify_plan(post)
            plan["verify"] = {"ok": ok, "problems": problems, "post": post}
            if isinstance(client, FixtureClient):
                plan["fixtureMutations"] = client.mutations
            _emit(plan, args.json_output)
            if not ok:
                return EXIT_DRIFT
            return EXIT_OK

        raise ProtectionError(f"unknown mode: {args.mode}")
    except ProtectionError as exc:
        err = {
            "schemaVersion": SCHEMA_VERSION,
            "error": str(exc),
            "exitCode": exc.exit_code,
        }
        print(json.dumps(err, indent=2), file=sys.stderr)
        return exc.exit_code


def _emit(payload: dict[str, Any], path: str | None) -> None:
    text = json.dumps(payload, indent=2)
    print(text)
    if path:
        Path(path).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
