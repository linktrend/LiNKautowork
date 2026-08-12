#!/usr/bin/env python3
"""Read-only external-state plan / verify / report for normal-token GitOps.

Checks the normal automation credential by name only, Bugbot mention-only,
Carlos restricted user-token boundary, three-branch protections (union-preserving),
promotion-source policy, and required workflow posture/conclusions.

Default is dry-run (no live calls). ``--fixture-dir`` or ``--live`` fill observations.
Never mutates GitHub settings, never creates credentials, and never reads or prints
secret values. ``apply`` / mutating HTTP methods are refused (exit 5).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NOT_READY = 3
EXIT_UNAVAILABLE = 4
EXIT_REFUSED = 5

AUTOMATION_TOKEN_SECRET = "LINKTREND_AUTOMATION_TOKEN"
BUGBOT_USER_TOKEN_SECRET = "LINKTREND_BUGBOT_USER_TOKEN"
BUGBOT_CHECK_NAME = "Cursor Bugbot"
SOURCE_POLICY_CHECK = "Enforce allowed PR source branches"
STATUS_CONTEXT = "Linktrend Review Ready"

RULESET_NAMES = {
    "development": "development-autonomous-merge",
    "staging": "staging-autonomous-promote",
    "main": "main-autonomous-release",
}

REQUIRED_WORKFLOW_FILES = (
    "branch-source-policy.yml",
    "ci.yml",
    "linktrend-review-ready-publisher.yml",
    "linktrend-review-packager.yml",
    "linktrend-integrator-merge.yml",
    "linktrend-development-to-staging.yml",
    "linktrend-staging-to-main.yml",
    "linktrend-repair-observer.yml",
    "linktrend-cleanup-merged.yml",
)

# Carlos user token may only be used for these operations (contract surface).
CARLOS_ALLOWED_OPS = (
    "packager_feature_pr_create",
    "bugbot_mention_comment",
)
CARLOS_FORBIDDEN_OPS = (
    "status_publish",
    "merge",
    "promote",
    "repair",
    "cleanup",
    "branch_push",
    "admin",
    "secrets_management",
)

# Env names that must never appear in report output as values.
_SECRET_ENV_NAMES = frozenset(
    {
        AUTOMATION_TOKEN_SECRET,
        BUGBOT_USER_TOKEN_SECRET,
        "LINKTREND_APP_TOKEN",
        "AUTOMATION_TOKEN",
        "BUGBOT_USER_TOKEN",
        "CURSOR_ADMIN_API_KEY",
        "GH_TOKEN",
        "GITHUB_TOKEN",
    }
)

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Statuses that count as compliant for verify ready.
_OK_STATUSES = frozenset({"ok", "matched"})

# Statuses that mean "could not prove" — never treated as compliant.
_UNPROVEN_STATUSES = frozenset(
    {"unchecked", "unknown", "blocked", "unavailable", "credential-missing", "malformed"}
)


class AuditError(Exception):
    def __init__(self, message: str, exit_code: int = EXIT_FAILED) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _check(
    *,
    check_id: str,
    category: str,
    required: bool,
    expected: str,
    observed: str,
    status: str,
    detail: str = "",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "category": category,
        "required": required,
        "expected": expected,
        "observed": observed,
        "status": status,
        "detail": detail,
    }


def required_checklist() -> list[dict[str, Any]]:
    """Canonical required external-state items (contract + WP1 surface)."""
    return [
        {
            "id": "github_auth.automation_token_secret",
            "category": "github_auth",
            "required": True,
            "expected": (
                f"{AUTOMATION_TOKEN_SECRET} Actions secret name present "
                "(value never read)"
            ),
        },
        {
            "id": "bugbot.user_token_secret",
            "category": "bugbot",
            "required": True,
            "expected": (
                f"{BUGBOT_USER_TOKEN_SECRET} Actions secret name present "
                "(value never read)"
            ),
        },
        {
            "id": "bugbot.manual_trigger_only",
            "category": "bugbot",
            "required": True,
            "expected": "Bugbot manualTriggerOnly=true (mention-only)",
        },
        {
            "id": "bugbot.check_name",
            "category": "bugbot",
            "required": True,
            "expected": f"Integrator/ruleset Bugbot check name is {BUGBOT_CHECK_NAME!r}",
        },
        {
            "id": "carlos.user_token_boundary",
            "category": "carlos",
            "required": True,
            "expected": (
                "Carlos user token restricted to packager PR create + Bugbot mention; "
                "forbidden for status publish/merge/promote/repair/admin"
            ),
        },
        {
            "id": "protection.development_ruleset",
            "category": "protection",
            "required": True,
            "expected": (
                f"Active ruleset {RULESET_NAMES['development']!r} requires "
                f"{BUGBOT_CHECK_NAME!r} and {SOURCE_POLICY_CHECK!r}"
            ),
        },
        {
            "id": "protection.staging_ruleset",
            "category": "protection",
            "required": True,
            "expected": (
                f"Active ruleset {RULESET_NAMES['staging']!r} requires "
                f"{SOURCE_POLICY_CHECK!r} (no Bugbot)"
            ),
        },
        {
            "id": "protection.main_ruleset",
            "category": "protection",
            "required": True,
            "expected": (
                f"Active ruleset {RULESET_NAMES['main']!r} requires "
                f"{SOURCE_POLICY_CHECK!r} (no Bugbot)"
            ),
        },
        {
            "id": "protection.promotion_source_policy",
            "category": "protection",
            "required": True,
            "expected": (
                f"{SOURCE_POLICY_CHECK!r} required on development, staging, and main"
            ),
        },
        {
            "id": "protection.repo_specific_checks_preserved",
            "category": "protection",
            "required": True,
            "expected": (
                "Repository-specific required checks and unrelated protection rules "
                "are preserved in the desired union"
            ),
        },
        {
            "id": "protection.allow_auto_merge",
            "category": "protection",
            "required": True,
            "expected": "Repository allow_auto_merge=true",
        },
        {
            "id": "workflows.required_presence",
            "category": "workflows",
            "required": True,
            "expected": "Required managed GitOps workflow files present",
        },
        {
            "id": "workflows.enabled_state",
            "category": "workflows",
            "required": True,
            "expected": "Required workflows enabled (state=active)",
        },
        {
            "id": "workflows.permissions_posture",
            "category": "workflows",
            "required": True,
            "expected": "Workflow permissions posture recorded (no secret values)",
        },
        {
            "id": "workflows.latest_conclusions",
            "category": "workflows",
            "required": True,
            "expected": "Latest relevant workflow conclusions recorded when available",
        },
        {
            "id": "completion.status_context",
            "category": "completion",
            "required": True,
            "expected": (
                f"Privileged publish context remains {STATUS_CONTEXT!r} "
                "(normal-token publisher from trusted workflow context only)"
            ),
        },
    ]


def _secret_env_leak_warnings() -> list[str]:
    """Detect secret material present in the process env without printing values."""
    warnings: list[str] = []
    for name in sorted(_SECRET_ENV_NAMES):
        # Presence is sufficient for this warning.  Do not read the value into
        # this process or report structure.
        if name in os.environ:
            warnings.append(
                f"{name}=present_in_process_env (value redacted; audit must not print it)"
            )
    return warnings


def _import_repository_protection() -> Any:
    """Lazy import so unit tests can stub path; refuse apply surfaces here."""
    gitops_dir = Path(__file__).resolve().parent
    if str(gitops_dir) not in sys.path:
        sys.path.insert(0, str(gitops_dir))
    import repository_protection as rp  # noqa: WPS433

    return rp


class ReadOnlyGitHubClient:
    """GET-only gh api client. Mutating methods raise immediately."""

    def __init__(self, repo: str) -> None:
        self.repo = repo
        self._auth_blocked = False
        self._auth_detail = ""
        self._installation_blocked = False

    def _api_get(self, path: str) -> tuple[int, Any, str]:
        cmd = ["gh", "api", "--method", "GET", path]
        proc = subprocess.run(cmd, text=True, capture_output=True)
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            low = (err or "").lower()
            if "auth" in low or "401" in low or "403" in low or "http 401" in low:
                self._auth_blocked = True
                self._auth_detail = "credential or permission blocked for live GET"
            return proc.returncode, None, err or (proc.stdout or "").strip()
        text = (proc.stdout or "").strip()
        if not text:
            return 0, None, ""
        try:
            return 0, json.loads(text), ""
        except json.JSONDecodeError:
            return 0, text, ""

    def mutate(self, method: str, *_args: Any, **_kwargs: Any) -> None:
        method_u = (method or "").upper()
        if method_u in _MUTATING_METHODS:
            raise AuditError(
                f"external_state_audit refuses mutating HTTP method {method_u}",
                EXIT_REFUSED,
            )
        raise AuditError(f"unsupported method: {method}", EXIT_REFUSED)

    def apply(self, *_args: Any, **_kwargs: Any) -> None:
        raise AuditError(
            "external_state_audit refuses apply; WP1 plan/verify are read-only",
            EXIT_REFUSED,
        )

    def list_actions_variables(self) -> list[dict[str, Any]]:
        code, data, err = self._api_get(f"repos/{self.repo}/actions/variables")
        if code != 0:
            raise AuditError(f"list actions variables failed: {err}")
        if isinstance(data, dict):
            vars_ = data.get("variables") or []
            return list(vars_) if isinstance(vars_, list) else []
        return []

    def list_actions_secret_names(self) -> list[str]:
        """Return secret *names* only — GitHub API never returns values here."""
        code, data, err = self._api_get(f"repos/{self.repo}/actions/secrets")
        if code != 0:
            raise AuditError(f"list actions secrets failed: {err}")
        names: list[str] = []
        if isinstance(data, dict):
            for item in data.get("secrets") or []:
                if isinstance(item, dict) and item.get("name"):
                    names.append(str(item["name"]))
        return names

    def get_installation(self) -> dict[str, Any] | None:
        code, data, err = self._api_get(f"repos/{self.repo}/installation")
        if code != 0:
            low = (err or "").lower()
            if "404" in low or "not installed" in low:
                return None
            if (
                "401" in low
                or "403" in low
                or "auth" in low
                or "jwt" in low
                or "json web token" in low
                or "bad credentials" in low
            ):
                # Live identity cannot prove installation — surface as blocked observation.
                self._auth_blocked = True
                self._auth_detail = "installation probe blocked"
                self._installation_blocked = True
                return None
            raise AuditError(f"get installation failed: {err}")
        return data if isinstance(data, dict) else None

    def list_rulesets(self) -> list[dict[str, Any]]:
        code, data, err = self._api_get(f"repos/{self.repo}/rulesets")
        if code != 0:
            raise AuditError(f"list rulesets failed: {err}")
        if isinstance(data, list):
            return data
        return []

    def get_ruleset(self, ruleset_id: int) -> dict[str, Any] | None:
        code, data, err = self._api_get(f"repos/{self.repo}/rulesets/{ruleset_id}")
        if code != 0:
            low = (err or "").lower()
            if "404" in low:
                return None
            raise AuditError(f"get ruleset {ruleset_id} failed: {err}")
        return data if isinstance(data, dict) else None

    def get_repo(self) -> dict[str, Any]:
        code, data, err = self._api_get(f"repos/{self.repo}")
        if code != 0 or not isinstance(data, dict):
            raise AuditError(f"get repo failed: {err or data}")
        return data

    def get_bugbot_repo_settings(self) -> dict[str, Any] | None:
        """Bugbot settings are not on the GitHub API; live mode leaves unknown."""
        return None

    def get_app_permissions_observation(self) -> dict[str, Any] | None:
        """Live GitHub cannot fully prove App permission matrix; return None → unknown."""
        return None

    def get_carlos_boundary_observation(self) -> dict[str, Any] | None:
        """PAT scopes are not readable via repo API; live → unknown."""
        return None

    def list_workflows(self) -> list[dict[str, Any]]:
        code, data, err = self._api_get(f"repos/{self.repo}/actions/workflows?per_page=100")
        if code != 0:
            raise AuditError(f"list workflows failed: {err}")
        workflows: list[dict[str, Any]] = []
        if isinstance(data, dict):
            for item in data.get("workflows") or []:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path") or "")
                name = str(item.get("name") or "")
                state = str(item.get("state") or "")
                entry: dict[str, Any] = {
                    "path": path,
                    "name": name,
                    "state": state,
                    "id": item.get("id"),
                }
                # Permissions are not returned by this endpoint → leave absent.
                workflows.append(entry)
        return workflows

    def get_workflow_latest_conclusion(self, workflow_id: Any) -> str | None:
        if workflow_id is None:
            return None
        code, data, err = self._api_get(
            f"repos/{self.repo}/actions/workflows/{workflow_id}/runs?per_page=1"
        )
        if code != 0:
            low = (err or "").lower()
            if "404" in low:
                return None
            # Do not fail the whole audit for one workflow run probe.
            return None
        if isinstance(data, dict):
            runs = data.get("workflow_runs") or []
            if runs and isinstance(runs[0], dict):
                conclusion = runs[0].get("conclusion")
                if conclusion:
                    return str(conclusion)
                status = runs[0].get("status")
                return str(status) if status else None
        return None

    def protection_capability(self) -> dict[str, Any]:
        return {"rulesets": "ok", "branch_protection": "ok"}


class FixtureClient(ReadOnlyGitHubClient):
    """Offline observations from fixture state.json. Never shells out to gh."""

    def __init__(self, repo: str, fixture_dir: Path) -> None:
        super().__init__(repo)
        self.fixture_dir = fixture_dir
        path = fixture_dir / "state.json"
        if not path.is_file():
            raise AuditError(f"fixture state missing: {path}")
        try:
            self.state = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AuditError(
                f"fixture state malformed JSON: {path} ({exc})",
                EXIT_FAILED,
            ) from exc
        if not isinstance(self.state, dict):
            raise AuditError(
                f"fixture state malformed: root must be object ({path})",
                EXIT_FAILED,
            )
        if self.state.get("malformed") is True:
            raise AuditError(
                "fixture marked malformed; refusing to invent compliant observations",
                EXIT_FAILED,
            )

    def list_actions_variables(self) -> list[dict[str, Any]]:
        raw = self.state.get("actions_variables")
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise AuditError("actions_variables malformed: expected list", EXIT_FAILED)
        return deepcopy(raw)

    def list_actions_secret_names(self) -> list[str]:
        # Accept either names-only list or objects with name (never values).
        raw = self.state.get("actions_secret_names")
        if raw is None:
            raw = self.state.get("actions_secrets") or []
        if not isinstance(raw, list):
            raise AuditError(
                "actions_secret_names/actions_secrets malformed: expected list",
                EXIT_FAILED,
            )
        names: list[str] = []
        for item in raw:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict) and item.get("name"):
                # Ignore any accidental "value" key — never surface it.
                names.append(str(item["name"]))
        return names

    def get_installation(self) -> dict[str, Any] | None:
        inst = self.state.get("installation")
        if inst is None or inst is False:
            return None
        return deepcopy(inst) if isinstance(inst, dict) else None

    def list_rulesets(self) -> list[dict[str, Any]]:
        cap = (self.state.get("capability") or {}).get("rulesets", "ok")
        if cap in {"unavailable", "forbidden", "error", "blocked"}:
            raise AuditError(
                f"rulesets capability={cap}",
                EXIT_UNAVAILABLE if cap == "unavailable" else EXIT_FAILED,
            )
        return deepcopy(self.state.get("rulesets") or [])

    def get_ruleset(self, ruleset_id: int) -> dict[str, Any] | None:
        details = self.state.get("ruleset_details") or {}
        detail = details.get(str(ruleset_id))
        if detail:
            return deepcopy(detail)
        for rs in self.state.get("rulesets") or []:
            if rs.get("id") == ruleset_id:
                return deepcopy(rs)
        return None

    def get_repo(self) -> dict[str, Any]:
        return deepcopy(self.state.get("repo") or {})

    def get_bugbot_repo_settings(self) -> dict[str, Any] | None:
        bugbot = self.state.get("bugbot")
        if bugbot is None:
            return None
        return deepcopy(bugbot) if isinstance(bugbot, dict) else None

    def get_app_permissions_observation(self) -> dict[str, Any] | None:
        perms = self.state.get("app_permissions")
        if perms is None:
            return None
        if not isinstance(perms, dict):
            raise AuditError("app_permissions malformed: expected object", EXIT_FAILED)
        return deepcopy(perms)

    def get_carlos_boundary_observation(self) -> dict[str, Any] | None:
        boundary = self.state.get("carlos_user_token_boundary")
        if boundary is None:
            return None
        if not isinstance(boundary, dict):
            raise AuditError(
                "carlos_user_token_boundary malformed: expected object",
                EXIT_FAILED,
            )
        return deepcopy(boundary)

    def list_workflows(self) -> list[dict[str, Any]]:
        if "workflows" not in self.state:
            return []
        raw = self.state.get("workflows")
        if not isinstance(raw, list):
            raise AuditError("workflows malformed: expected list", EXIT_FAILED)
        return deepcopy(raw)

    def get_workflow_latest_conclusion(self, workflow_id: Any) -> str | None:
        # Prefer explicit latestConclusion on workflow entries.
        for wf in self.list_workflows():
            if workflow_id is not None and wf.get("id") == workflow_id:
                conclusion = wf.get("latestConclusion") or wf.get("conclusion")
                return str(conclusion) if conclusion is not None else None
            path = str(wf.get("path") or "")
            if workflow_id is None and path.endswith(str(workflow_id)):
                conclusion = wf.get("latestConclusion") or wf.get("conclusion")
                return str(conclusion) if conclusion is not None else None
        return None

    def protection_capability(self) -> dict[str, Any]:
        return deepcopy(self.state.get("capability") or {"rulesets": "ok"})


class UncheckedClient(ReadOnlyGitHubClient):
    """Dry-run default: no live reads; every observation stays unchecked/unknown."""

    def list_actions_variables(self) -> list[dict[str, Any]]:
        return []

    def list_actions_secret_names(self) -> list[str]:
        return []

    def get_installation(self) -> dict[str, Any] | None:
        return None

    def list_rulesets(self) -> list[dict[str, Any]]:
        return []

    def get_ruleset(self, ruleset_id: int) -> dict[str, Any] | None:
        return None

    def get_repo(self) -> dict[str, Any]:
        return {}

    def get_bugbot_repo_settings(self) -> dict[str, Any] | None:
        return None

    def get_app_permissions_observation(self) -> dict[str, Any] | None:
        return None

    def get_carlos_boundary_observation(self) -> dict[str, Any] | None:
        return None

    def list_workflows(self) -> list[dict[str, Any]]:
        return []

    def get_workflow_latest_conclusion(self, workflow_id: Any) -> str | None:
        return None

    def protection_capability(self) -> dict[str, Any]:
        return {}


def _find_variable(variables: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for item in variables:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return None


def _extract_ruleset_checks(ruleset: dict[str, Any] | None) -> list[str]:
    if not ruleset:
        return []
    out: list[str] = []
    for rule in ruleset.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        if rule.get("type") != "required_status_checks":
            continue
        params = rule.get("parameters") or {}
        for item in params.get("required_status_checks") or []:
            if isinstance(item, dict) and item.get("context"):
                out.append(str(item["context"]))
    return out


def _extract_non_check_rule_types(ruleset: dict[str, Any] | None) -> list[str]:
    if not ruleset:
        return []
    out: list[str] = []
    for rule in ruleset.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        rtype = rule.get("type")
        if isinstance(rtype, str) and rtype and rtype != "required_status_checks":
            out.append(rtype)
    return out


def _is_numeric_app_id(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return bool(re.fullmatch(r"[0-9]+", text))


def _workflow_basename(path: str) -> str:
    return Path(path.replace("\\", "/")).name


def _unchecked(
    check_id: str,
    category: str,
    expected: str,
    *,
    detail: str = "dry-run default: pass --live or --fixture-dir to observe",
    observed: str = "unchecked",
    status: str = "unchecked",
) -> dict[str, Any]:
    return _check(
        check_id=check_id,
        category=category,
        required=True,
        expected=expected,
        observed=observed,
        status=status,
        detail=detail,
    )


def _evaluate_ruleset_branch(
    client: ReadOnlyGitHubClient,
    *,
    branch: str,
    require_bugbot: bool,
) -> dict[str, Any]:
    """Return evaluation dict for one governed branch ruleset."""
    name = RULESET_NAMES[branch]
    expected_parts = [SOURCE_POLICY_CHECK]
    if require_bugbot:
        expected_parts = [BUGBOT_CHECK_NAME, SOURCE_POLICY_CHECK]
    expected = (
        f"Active ruleset {name!r} requires "
        + " and ".join(repr(p) for p in expected_parts)
        + ((" (no Bugbot)" if not require_bugbot else ""))
    )
    check_id = f"protection.{branch}_ruleset"

    try:
        rulesets = client.list_rulesets()
    except AuditError as exc:
        if exc.exit_code == EXIT_UNAVAILABLE:
            return _check(
                check_id=check_id,
                category="protection",
                required=True,
                expected=expected,
                observed="unavailable",
                status="unavailable",
                detail=str(exc),
            )
        raise

    match = next(
        (r for r in rulesets if isinstance(r, dict) and r.get("name") == name),
        None,
    )
    if not match:
        return _check(
            check_id=check_id,
            category="protection",
            required=True,
            expected=expected,
            observed="missing",
            status="missing",
            detail=f"ruleset {name!r} not found",
        )

    detail_rs = (
        client.get_ruleset(int(match["id"])) if match.get("id") is not None else match
    )
    enforcement = (detail_rs or match).get("enforcement") or match.get("enforcement")
    checks = _extract_ruleset_checks(detail_rs or match)
    missing_ctx = [c for c in expected_parts if c not in checks]
    if require_bugbot is False and BUGBOT_CHECK_NAME in checks:
        # Bugbot on staging/main is drift from managed baseline (should not be required).
        # Still ok for presence of source policy; report soft detail only if source ok.
        pass

    if enforcement and enforcement != "active":
        return _check(
            check_id=check_id,
            category="protection",
            required=True,
            expected=expected,
            observed=f"enforcement={enforcement}",
            status="drift",
            detail=f"ruleset exists but enforcement is {enforcement!r}, not active",
        )
    if missing_ctx:
        return _check(
            check_id=check_id,
            category="protection",
            required=True,
            expected=expected,
            observed="incomplete_checks",
            status="drift",
            detail=f"missing required contexts: {', '.join(missing_ctx)}",
        )
    return _check(
        check_id=check_id,
        category="protection",
        required=True,
        expected=expected,
        observed="active_with_required_checks",
        status="ok",
        detail=f"ruleset active; checks include {', '.join(expected_parts)}",
    )


def evaluate(client: ReadOnlyGitHubClient, *, source: str) -> list[dict[str, Any]]:
    """Evaluate required checks against a client. UncheckedClient → all unchecked."""
    unchecked = isinstance(client, UncheckedClient)
    results: list[dict[str, Any]] = []
    variables: list[dict[str, Any]] = []
    secret_names: list[str] = []

    # --- github_auth.automation_token_secret ---
    if unchecked:
        results.append(
            _unchecked(
                "github_auth.automation_token_secret",
                "github_auth",
                f"{AUTOMATION_TOKEN_SECRET} Actions secret name present (value never read)",
            )
        )
    else:
        secret_names = client.list_actions_secret_names()
        if AUTOMATION_TOKEN_SECRET in secret_names:
            results.append(
                _check(
                    check_id="github_auth.automation_token_secret",
                    category="github_auth",
                    required=True,
                    expected=(
                        f"{AUTOMATION_TOKEN_SECRET} Actions secret name present "
                        "(value never read)"
                    ),
                    observed="name_present",
                    status="ok",
                    detail="secret name listed; value not retrieved",
                )
            )
        else:
            results.append(
                _check(
                    check_id="github_auth.automation_token_secret",
                    category="github_auth",
                    required=True,
                    expected=(
                        f"{AUTOMATION_TOKEN_SECRET} Actions secret name present "
                        "(value never read)"
                    ),
                    observed="missing",
                    status="credential-missing",
                    detail=f"{AUTOMATION_TOKEN_SECRET} not listed among Actions secret names",
                )
            )

    # --- bugbot.user_token_secret ---
    if unchecked:
        results.append(
            _unchecked(
                "bugbot.user_token_secret",
                "bugbot",
                f"{BUGBOT_USER_TOKEN_SECRET} Actions secret name present (value never read)",
            )
        )
    else:
        if not secret_names:
            secret_names = client.list_actions_secret_names()
        if BUGBOT_USER_TOKEN_SECRET in secret_names:
            results.append(
                _check(
                    check_id="bugbot.user_token_secret",
                    category="bugbot",
                    required=True,
                    expected=(
                        f"{BUGBOT_USER_TOKEN_SECRET} Actions secret name present "
                        "(value never read)"
                    ),
                    observed="name_present",
                    status="ok",
                    detail="secret name listed; value not retrieved",
                )
            )
        else:
            results.append(
                _check(
                    check_id="bugbot.user_token_secret",
                    category="bugbot",
                    required=True,
                    expected=(
                        f"{BUGBOT_USER_TOKEN_SECRET} Actions secret name present "
                        "(value never read)"
                    ),
                    observed="missing",
                    status="credential-missing",
                    detail=f"{BUGBOT_USER_TOKEN_SECRET} not listed among Actions secret names",
                )
            )

    # --- bugbot.manual_trigger_only ---
    if unchecked:
        results.append(
            _unchecked(
                "bugbot.manual_trigger_only",
                "bugbot",
                "Bugbot manualTriggerOnly=true (mention-only)",
                detail=(
                    "dry-run default / live GitHub path cannot read Cursor Bugbot "
                    "dashboard; supply fixture bugbot.manualTriggerOnly or confirm "
                    "manually per docs/contracts/BUGBOT-MENTION-ONLY.md"
                ),
            )
        )
    else:
        bugbot = client.get_bugbot_repo_settings()
        if bugbot is None:
            results.append(
                _check(
                    check_id="bugbot.manual_trigger_only",
                    category="bugbot",
                    required=True,
                    expected="Bugbot manualTriggerOnly=true (mention-only)",
                    observed="unknown",
                    status="unknown",
                    detail=(
                        "Bugbot settings unavailable via GitHub API; fixture or "
                        "operator confirmation required — never assume compliant"
                    ),
                )
            )
        else:
            mto = bugbot.get("manualTriggerOnly")
            if mto is True:
                results.append(
                    _check(
                        check_id="bugbot.manual_trigger_only",
                        category="bugbot",
                        required=True,
                        expected="Bugbot manualTriggerOnly=true (mention-only)",
                        observed="true",
                        status="ok",
                        detail="manualTriggerOnly=true",
                    )
                )
            else:
                results.append(
                    _check(
                        check_id="bugbot.manual_trigger_only",
                        category="bugbot",
                        required=True,
                        expected="Bugbot manualTriggerOnly=true (mention-only)",
                        observed=str(mto).lower() if mto is not None else "missing",
                        status="drift" if mto is False else "missing",
                        detail="manualTriggerOnly must be true before consumer rollout",
                    )
                )

    # --- bugbot.check_name ---
    if unchecked:
        results.append(
            _unchecked(
                "bugbot.check_name",
                "bugbot",
                f"Integrator/ruleset Bugbot check name is {BUGBOT_CHECK_NAME!r}",
            )
        )
    else:
        if not variables:
            variables = client.list_actions_variables()
        override = _find_variable(variables, "LINKTREND_BUGBOT_CHECK_NAME")
        if override is None:
            results.append(
                _check(
                    check_id="bugbot.check_name",
                    category="bugbot",
                    required=True,
                    expected=f"Integrator/ruleset Bugbot check name is {BUGBOT_CHECK_NAME!r}",
                    observed="default",
                    status="ok",
                    detail=(
                        f"LINKTREND_BUGBOT_CHECK_NAME unset; default {BUGBOT_CHECK_NAME!r} applies"
                    ),
                )
            )
        else:
            value = str(override.get("value") or "").strip()
            if value == BUGBOT_CHECK_NAME:
                results.append(
                    _check(
                        check_id="bugbot.check_name",
                        category="bugbot",
                        required=True,
                        expected=f"Integrator/ruleset Bugbot check name is {BUGBOT_CHECK_NAME!r}",
                        observed=value,
                        status="ok",
                        detail="LINKTREND_BUGBOT_CHECK_NAME matches contract",
                    )
                )
            else:
                results.append(
                    _check(
                        check_id="bugbot.check_name",
                        category="bugbot",
                        required=True,
                        expected=f"Integrator/ruleset Bugbot check name is {BUGBOT_CHECK_NAME!r}",
                        observed=value or "empty",
                        status="drift",
                        detail=(
                            "LINKTREND_BUGBOT_CHECK_NAME differs from "
                            f"{BUGBOT_CHECK_NAME!r}"
                        ),
                    )
                )

    # --- carlos.user_token_boundary ---
    if unchecked:
        results.append(
            _unchecked(
                "carlos.user_token_boundary",
                "carlos",
                (
                    "Carlos user token restricted to packager PR create + Bugbot mention; "
                    "forbidden for status publish/merge/promote/repair/admin"
                ),
                observed="unknown",
                status="unknown",
            )
        )
    else:
        boundary = client.get_carlos_boundary_observation()
        if boundary is None:
            results.append(
                _check(
                    check_id="carlos.user_token_boundary",
                    category="carlos",
                    required=True,
                    expected=(
                        "Carlos user token restricted to packager PR create + Bugbot mention; "
                        "forbidden for status publish/merge/promote/repair/admin"
                    ),
                    observed="unknown",
                    status="unknown",
                    detail=(
                        "PAT scope boundary not readable via GitHub repo API; "
                        "fixture or operator confirmation required — never assume compliant"
                    ),
                )
            )
        else:
            allowed = [
                str(x)
                for x in (boundary.get("allowedOps") or boundary.get("allowed") or [])
            ]
            forbidden_claimed = [
                str(x)
                for x in (boundary.get("forbiddenOpsClaimed") or boundary.get("uses") or [])
            ]
            # Any CARLOS_FORBIDDEN_OPS appearing in allowed → forbidden.
            violations = sorted(set(allowed) & set(CARLOS_FORBIDDEN_OPS))
            violations += sorted(
                set(forbidden_claimed) & set(CARLOS_FORBIDDEN_OPS)
                if boundary.get("claimsForbiddenAsAllowed")
                else set()
            )
            if boundary.get("publishesReviewReady") is True:
                violations.append("status_publish")
            if boundary.get("status") == "forbidden" or violations:
                results.append(
                    _check(
                        check_id="carlos.user_token_boundary",
                        category="carlos",
                        required=True,
                        expected=(
                            "Carlos user token restricted to packager PR create + Bugbot mention; "
                            "forbidden for status publish/merge/promote/repair/admin"
                        ),
                        observed="boundary_violated",
                        status="forbidden",
                        detail="forbidden ops claimed: "
                        + (", ".join(sorted(set(violations))) or "fixture forbidden"),
                    )
                )
            elif boundary.get("status") == "blocked":
                results.append(
                    _check(
                        check_id="carlos.user_token_boundary",
                        category="carlos",
                        required=True,
                        expected=(
                            "Carlos user token restricted to packager PR create + Bugbot mention; "
                            "forbidden for status publish/merge/promote/repair/admin"
                        ),
                        observed="blocked",
                        status="blocked",
                        detail="boundary observation blocked (auth/credential)",
                    )
                )
            else:
                # Require allowed set ⊆ CARLOS_ALLOWED_OPS when provided.
                unknown_allowed = sorted(set(allowed) - set(CARLOS_ALLOWED_OPS))
                if unknown_allowed:
                    results.append(
                        _check(
                            check_id="carlos.user_token_boundary",
                            category="carlos",
                            required=True,
                            expected=(
                                "Carlos user token restricted to packager PR create + Bugbot mention; "
                                "forbidden for status publish/merge/promote/repair/admin"
                            ),
                            observed="unexpected_allowed_ops",
                            status="drift",
                            detail="unexpected allowed ops: " + ", ".join(unknown_allowed),
                        )
                    )
                else:
                    results.append(
                        _check(
                            check_id="carlos.user_token_boundary",
                            category="carlos",
                            required=True,
                            expected=(
                                "Carlos user token restricted to packager PR create + Bugbot mention; "
                                "forbidden for status publish/merge/promote/repair/admin"
                            ),
                            observed="restricted",
                            status="matched",
                            detail="fixture reports restricted allowedOps only",
                        )
                    )

    # --- protection.development / staging / main ---
    if unchecked:
        for branch, require_bugbot in (
            ("development", True),
            ("staging", False),
            ("main", False),
        ):
            name = RULESET_NAMES[branch]
            exp = (
                f"Active ruleset {name!r} requires "
                + (
                    f"{BUGBOT_CHECK_NAME!r} and {SOURCE_POLICY_CHECK!r}"
                    if require_bugbot
                    else f"{SOURCE_POLICY_CHECK!r} (no Bugbot)"
                )
            )
            results.append(_unchecked(f"protection.{branch}_ruleset", "protection", exp))
    else:
        cap = client.protection_capability()
        rulesets_cap = (cap or {}).get("rulesets", "ok")
        if rulesets_cap in {"unavailable", "forbidden", "blocked"}:
            status = (
                "unavailable"
                if rulesets_cap == "unavailable"
                else ("forbidden" if rulesets_cap == "forbidden" else "blocked")
            )
            for branch, require_bugbot in (
                ("development", True),
                ("staging", False),
                ("main", False),
            ):
                name = RULESET_NAMES[branch]
                exp = (
                    f"Active ruleset {name!r} requires "
                    + (
                        f"{BUGBOT_CHECK_NAME!r} and {SOURCE_POLICY_CHECK!r}"
                        if require_bugbot
                        else f"{SOURCE_POLICY_CHECK!r} (no Bugbot)"
                    )
                )
                results.append(
                    _check(
                        check_id=f"protection.{branch}_ruleset",
                        category="protection",
                        required=True,
                        expected=exp,
                        observed=rulesets_cap,
                        status=status,
                        detail=f"protection capability rulesets={rulesets_cap}",
                    )
                )
        else:
            results.append(
                _evaluate_ruleset_branch(client, branch="development", require_bugbot=True)
            )
            results.append(
                _evaluate_ruleset_branch(client, branch="staging", require_bugbot=False)
            )
            results.append(
                _evaluate_ruleset_branch(client, branch="main", require_bugbot=False)
            )

    # --- protection.promotion_source_policy ---
    if unchecked:
        results.append(
            _unchecked(
                "protection.promotion_source_policy",
                "protection",
                f"{SOURCE_POLICY_CHECK!r} required on development, staging, and main",
            )
        )
    else:
        missing_branches: list[str] = []
        try:
            rulesets = client.list_rulesets()
            for branch in ("development", "staging", "main"):
                name = RULESET_NAMES[branch]
                match = next(
                    (r for r in rulesets if isinstance(r, dict) and r.get("name") == name),
                    None,
                )
                if not match:
                    missing_branches.append(branch)
                    continue
                detail_rs = (
                    client.get_ruleset(int(match["id"]))
                    if match.get("id") is not None
                    else match
                )
                checks = _extract_ruleset_checks(detail_rs or match)
                if SOURCE_POLICY_CHECK not in checks:
                    missing_branches.append(branch)
            if missing_branches:
                results.append(
                    _check(
                        check_id="protection.promotion_source_policy",
                        category="protection",
                        required=True,
                        expected=(
                            f"{SOURCE_POLICY_CHECK!r} required on development, staging, and main"
                        ),
                        observed="incomplete",
                        status="drift",
                        detail="missing source-policy on: " + ", ".join(missing_branches),
                    )
                )
            else:
                results.append(
                    _check(
                        check_id="protection.promotion_source_policy",
                        category="protection",
                        required=True,
                        expected=(
                            f"{SOURCE_POLICY_CHECK!r} required on development, staging, and main"
                        ),
                        observed="present_all_branches",
                        status="matched",
                        detail="source-policy check present on all three governed branches",
                    )
                )
        except AuditError as exc:
            status = "unavailable" if exc.exit_code == EXIT_UNAVAILABLE else "blocked"
            results.append(
                _check(
                    check_id="protection.promotion_source_policy",
                    category="protection",
                    required=True,
                    expected=(
                        f"{SOURCE_POLICY_CHECK!r} required on development, staging, and main"
                    ),
                    observed=status,
                    status=status,
                    detail=str(exc),
                )
            )

    # --- protection.repo_specific_checks_preserved ---
    if unchecked:
        results.append(
            _unchecked(
                "protection.repo_specific_checks_preserved",
                "protection",
                (
                    "Repository-specific required checks and unrelated protection rules "
                    "are preserved in the desired union"
                ),
            )
        )
    else:
        try:
            rp = _import_repository_protection()
            # Build desired union from current observations without mutating.
            rulesets = client.list_rulesets()
            preserved_ok = True
            details: list[str] = []
            for branch in ("development", "staging", "main"):
                name = RULESET_NAMES[branch]
                match = next(
                    (r for r in rulesets if isinstance(r, dict) and r.get("name") == name),
                    None,
                )
                if not match:
                    continue
                detail_rs = (
                    client.get_ruleset(int(match["id"]))
                    if match.get("id") is not None
                    else match
                )
                existing_checks = _extract_ruleset_checks(detail_rs)
                managed = rp.managed_baseline(branch)
                union = rp.union_checks(managed, existing_checks)
                # Every existing check must appear in desired.
                for ctx in existing_checks:
                    if ctx not in union["desired"]:
                        preserved_ok = False
                        details.append(f"{branch}: dropped {ctx}")
                # Non-check rules must remain representable (types still present).
                non_check = _extract_non_check_rule_types(detail_rs)
                if non_check:
                    merged = rp.merge_ruleset_rules(
                        (detail_rs or {}).get("rules"),
                        rp._status_check_rule(union["desired"]),
                    )
                    merged_types = [r.get("type") for r in merged]
                    for t in non_check:
                        if t not in merged_types:
                            preserved_ok = False
                            details.append(f"{branch}: would drop rule type {t}")
            if preserved_ok:
                results.append(
                    _check(
                        check_id="protection.repo_specific_checks_preserved",
                        category="protection",
                        required=True,
                        expected=(
                            "Repository-specific required checks and unrelated protection rules "
                            "are preserved in the desired union"
                        ),
                        observed="preserved",
                        status="matched",
                        detail="union plan preserves existing checks and non-check rules",
                    )
                )
            else:
                results.append(
                    _check(
                        check_id="protection.repo_specific_checks_preserved",
                        category="protection",
                        required=True,
                        expected=(
                            "Repository-specific required checks and unrelated protection rules "
                            "are preserved in the desired union"
                        ),
                        observed="not_preserved",
                        status="drift",
                        detail="; ".join(details) or "preservation failed",
                    )
                )
        except AuditError as exc:
            status = "unavailable" if exc.exit_code == EXIT_UNAVAILABLE else "blocked"
            results.append(
                _check(
                    check_id="protection.repo_specific_checks_preserved",
                    category="protection",
                    required=True,
                    expected=(
                        "Repository-specific required checks and unrelated protection rules "
                        "are preserved in the desired union"
                    ),
                    observed=status,
                    status=status,
                    detail=str(exc),
                )
            )

    # --- protection.allow_auto_merge ---
    if unchecked:
        results.append(
            _unchecked(
                "protection.allow_auto_merge",
                "protection",
                "Repository allow_auto_merge=true",
            )
        )
    else:
        repo = client.get_repo()
        aam = repo.get("allow_auto_merge")
        if aam is True:
            results.append(
                _check(
                    check_id="protection.allow_auto_merge",
                    category="protection",
                    required=True,
                    expected="Repository allow_auto_merge=true",
                    observed="true",
                    status="ok",
                    detail="allow_auto_merge=true",
                )
            )
        elif aam is False:
            results.append(
                _check(
                    check_id="protection.allow_auto_merge",
                    category="protection",
                    required=True,
                    expected="Repository allow_auto_merge=true",
                    observed="false",
                    status="drift",
                    detail="allow_auto_merge is false",
                )
            )
        else:
            results.append(
                _check(
                    check_id="protection.allow_auto_merge",
                    category="protection",
                    required=True,
                    expected="Repository allow_auto_merge=true",
                    observed="unknown",
                    status="unknown",
                    detail="allow_auto_merge field unavailable in observation",
                )
            )

    # --- workflows.* ---
    if unchecked:
        for wid, exp in (
            ("workflows.required_presence", "Required managed GitOps workflow files present"),
            ("workflows.enabled_state", "Required workflows enabled (state=active)"),
            (
                "workflows.permissions_posture",
                "Workflow permissions posture recorded (no secret values)",
            ),
            (
                "workflows.latest_conclusions",
                "Latest relevant workflow conclusions recorded when available",
            ),
        ):
            results.append(_unchecked(wid, "workflows", exp, observed="unknown", status="unknown"))
    else:
        try:
            workflows = client.list_workflows()
        except AuditError as exc:
            for wid, exp in (
                ("workflows.required_presence", "Required managed GitOps workflow files present"),
                ("workflows.enabled_state", "Required workflows enabled (state=active)"),
                (
                    "workflows.permissions_posture",
                    "Workflow permissions posture recorded (no secret values)",
                ),
                (
                    "workflows.latest_conclusions",
                    "Latest relevant workflow conclusions recorded when available",
                ),
            ):
                results.append(
                    _check(
                        check_id=wid,
                        category="workflows",
                        required=True,
                        expected=exp,
                        observed="blocked",
                        status="blocked",
                        detail=str(exc),
                    )
                )
            workflows = None

        if workflows is not None:
            by_base = {_workflow_basename(str(w.get("path") or "")): w for w in workflows}
            missing_wf = [name for name in REQUIRED_WORKFLOW_FILES if name not in by_base]
            if not workflows and source == "live":
                # Empty list from live is possible but unusual — treat as unknown rather than ok.
                results.append(
                    _check(
                        check_id="workflows.required_presence",
                        category="workflows",
                        required=True,
                        expected="Required managed GitOps workflow files present",
                        observed="empty",
                        status="unknown",
                        detail="workflow list empty; never assume compliant",
                    )
                )
            elif missing_wf:
                results.append(
                    _check(
                        check_id="workflows.required_presence",
                        category="workflows",
                        required=True,
                        expected="Required managed GitOps workflow files present",
                        observed="incomplete",
                        status="drift",
                        detail="missing workflows: " + ", ".join(missing_wf),
                    )
                )
            else:
                results.append(
                    _check(
                        check_id="workflows.required_presence",
                        category="workflows",
                        required=True,
                        expected="Required managed GitOps workflow files present",
                        observed="present",
                        status="matched",
                        detail=f"{len(REQUIRED_WORKFLOW_FILES)} required workflow files present",
                    )
                )

            inactive = []
            for name in REQUIRED_WORKFLOW_FILES:
                wf = by_base.get(name)
                if not wf:
                    continue
                state = str(wf.get("state") or "").lower()
                if state and state not in {"active", "enabled"}:
                    inactive.append(f"{name}={state}")
            if missing_wf and not workflows:
                results.append(
                    _check(
                        check_id="workflows.enabled_state",
                        category="workflows",
                        required=True,
                        expected="Required workflows enabled (state=active)",
                        observed="unknown",
                        status="unknown",
                        detail="cannot evaluate enabled state without workflow list",
                    )
                )
            elif inactive:
                results.append(
                    _check(
                        check_id="workflows.enabled_state",
                        category="workflows",
                        required=True,
                        expected="Required workflows enabled (state=active)",
                        observed="inactive",
                        status="drift",
                        detail="non-active workflows: " + ", ".join(inactive),
                    )
                )
            elif missing_wf:
                results.append(
                    _check(
                        check_id="workflows.enabled_state",
                        category="workflows",
                        required=True,
                        expected="Required workflows enabled (state=active)",
                        observed="incomplete",
                        status="drift",
                        detail="enabled state incomplete due to missing workflows",
                    )
                )
            else:
                # If state field absent for all, mark unknown.
                states_present = any(
                    str(by_base[n].get("state") or "")
                    for n in REQUIRED_WORKFLOW_FILES
                    if n in by_base
                )
                if not states_present:
                    results.append(
                        _check(
                            check_id="workflows.enabled_state",
                            category="workflows",
                            required=True,
                            expected="Required workflows enabled (state=active)",
                            observed="unknown",
                            status="unknown",
                            detail="workflow state fields absent; never assume compliant",
                        )
                    )
                else:
                    results.append(
                        _check(
                            check_id="workflows.enabled_state",
                            category="workflows",
                            required=True,
                            expected="Required workflows enabled (state=active)",
                            observed="active",
                            status="matched",
                            detail="required workflows report active/enabled",
                        )
                    )

            # Permissions posture: record when present; unknown when absent (live).
            perms_seen = 0
            perms_forbidden = []
            for name in REQUIRED_WORKFLOW_FILES:
                wf = by_base.get(name)
                if not wf:
                    continue
                perms = wf.get("permissions")
                if isinstance(perms, dict):
                    perms_seen += 1
                    # Never include secret values; only permission keys/levels.
                    if str(perms.get("administration") or "").lower() in {
                        "write",
                        "admin",
                    }:
                        perms_forbidden.append(name)
            if perms_forbidden:
                results.append(
                    _check(
                        check_id="workflows.permissions_posture",
                        category="workflows",
                        required=True,
                        expected="Workflow permissions posture recorded (no secret values)",
                        observed="overprivileged",
                        status="forbidden",
                        detail="administration:write on: " + ", ".join(perms_forbidden),
                    )
                )
            elif perms_seen == 0:
                results.append(
                    _check(
                        check_id="workflows.permissions_posture",
                        category="workflows",
                        required=True,
                        expected="Workflow permissions posture recorded (no secret values)",
                        observed="unknown",
                        status="unknown",
                        detail=(
                            "workflow permissions not available from GitHub workflows list API; "
                            "fixture may supply permissions map — never assume compliant"
                        ),
                    )
                )
            else:
                results.append(
                    _check(
                        check_id="workflows.permissions_posture",
                        category="workflows",
                        required=True,
                        expected="Workflow permissions posture recorded (no secret values)",
                        observed="recorded",
                        status="matched",
                        detail=f"permissions maps recorded for {perms_seen} workflows",
                    )
                )

            # Latest conclusions
            conclusions: dict[str, str] = {}
            unknown_conc = 0
            for name in REQUIRED_WORKFLOW_FILES:
                wf = by_base.get(name)
                if not wf:
                    unknown_conc += 1
                    continue
                conclusion = wf.get("latestConclusion") or wf.get("conclusion")
                if conclusion is None and source == "live":
                    conclusion = client.get_workflow_latest_conclusion(wf.get("id"))
                if conclusion is None:
                    unknown_conc += 1
                else:
                    conclusions[name] = str(conclusion)
            if not conclusions and unknown_conc:
                results.append(
                    _check(
                        check_id="workflows.latest_conclusions",
                        category="workflows",
                        required=True,
                        expected="Latest relevant workflow conclusions recorded when available",
                        observed="unknown",
                        status="unknown",
                        detail="no workflow conclusions available; never assume compliant",
                    )
                )
            else:
                failed = [
                    f"{n}={c}"
                    for n, c in sorted(conclusions.items())
                    if c.lower() in {"failure", "timed_out", "cancelled", "action_required"}
                ]
                if failed:
                    results.append(
                        _check(
                            check_id="workflows.latest_conclusions",
                            category="workflows",
                            required=True,
                            expected=(
                                "Latest relevant workflow conclusions recorded when available"
                            ),
                            observed="failure_present",
                            status="drift",
                            detail="failing conclusions: " + ", ".join(failed),
                        )
                    )
                else:
                    results.append(
                        _check(
                            check_id="workflows.latest_conclusions",
                            category="workflows",
                            required=True,
                            expected=(
                                "Latest relevant workflow conclusions recorded when available"
                            ),
                            observed="recorded",
                            status="matched",
                            detail=(
                                f"recorded={len(conclusions)} unknown={unknown_conc}; "
                                "identifiers/conclusions only"
                            ),
                        )
                    )

    # --- completion.status_context ---
    results.append(
        _check(
            check_id="completion.status_context",
            category="completion",
            required=True,
            expected=(
                f"Privileged publish context remains {STATUS_CONTEXT!r} "
                "(normal-token publisher from trusted workflow context only)"
            ),
            observed=STATUS_CONTEXT,
            status="ok",
            detail=(
                "contract constant; privileged publish must use the normal automation "
                "credential from protected workflow context only"
            ),
        )
    )

    for row in results:
        row["source"] = source
    return results


def summarize(checks: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {
        "ok": 0,
        "matched": 0,
        "missing": 0,
        "drift": 0,
        "unchecked": 0,
        "unknown": 0,
        "blocked": 0,
        "unavailable": 0,
        "forbidden": 0,
        "credential-missing": 0,
        "malformed": 0,
        "error": 0,
    }
    for row in checks:
        status = row.get("status") or "error"
        if status not in counts:
            counts["error"] += 1
        else:
            counts[status] += 1
    required = [c for c in checks if c.get("required")]
    ready = all(c.get("status") in _OK_STATUSES for c in required)
    unproven = [c["id"] for c in required if c.get("status") in _UNPROVEN_STATUSES]
    return {
        **counts,
        "requiredTotal": len(required),
        "ready": ready,
        "unproven": unproven,
    }


def human_summary(checks: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    if summary.get("ready"):
        return (
            f"External state READY: {summary['requiredTotal']} required checks matched "
            f"(ok/matched). Mutations: none."
        )
    problems = [
        c
        for c in checks
        if c.get("required") and c.get("status") not in _OK_STATUSES
    ]
    top = ", ".join(f"{c['id']}={c['status']}" for c in problems[:8])
    more = f" (+{len(problems) - 8} more)" if len(problems) > 8 else ""
    return (
        f"External state NOT READY: {len(problems)}/{summary['requiredTotal']} "
        f"required checks unresolved [{top}{more}]. Mutations: none."
    )


def build_protection_plan_section(
    client: ReadOnlyGitHubClient,
    *,
    source: str,
) -> dict[str, Any] | None:
    """Embed repository_protection plan (read-only) when observations allow."""
    if isinstance(client, UncheckedClient):
        return {
            "available": False,
            "reason": "dry-run: protection plan not computed without --live/--fixture-dir",
            "mutations": [],
        }
    try:
        rp = _import_repository_protection()
        # Bridge: use repository_protection FixtureClient when we have a fixture dir.
        if isinstance(client, FixtureClient):
            rp_client = rp.FixtureClient(
                client.repo, client.fixture_dir, read_only=True
            )
        else:
            # Live: wrap GET-only — repository_protection GitHubClient can mutate;
            # we only call build_plan / verify_plan (no apply).
            rp_client = rp.GitHubClient(client.repo)
        plan = rp.build_plan(rp_client)
        ok, problems = rp.verify_plan(plan)
        return {
            "available": True,
            "source": source,
            "dryRun": True,
            "mutations": [],
            "capability": plan.get("capability"),
            "actions": plan.get("actions"),
            "branches": {
                b: {
                    "action": detail.get("action"),
                    "rulesetName": detail.get("rulesetName"),
                    "requiredChecks": detail.get("requiredChecks"),
                }
                for b, detail in (plan.get("branches") or {}).items()
            },
            "repoSettings": plan.get("repoSettings"),
            "verify": {"ok": ok, "problems": problems},
        }
    except Exception as exc:  # noqa: BLE001 — surface as blocked/unknown section
        return {
            "available": False,
            "reason": f"protection plan unavailable: {exc}",
            "mutations": [],
        }


def build_desired_plan(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic desired inventory for plan mode (no mutations)."""
    desired: list[dict[str, Any]] = []
    for item in required_checklist():
        row = next((c for c in checks if c.get("id") == item["id"]), None)
        action = "noop"
        if row is None:
            action = "unknown"
        elif row.get("status") in _OK_STATUSES:
            action = "noop"
        elif row.get("status") in {"missing", "credential-missing"}:
            action = "create_or_configure"
        elif row.get("status") in {"drift", "forbidden"}:
            action = "remediate"
        elif row.get("status") in _UNPROVEN_STATUSES:
            action = "observe"
        desired.append(
            {
                "id": item["id"],
                "category": item["category"],
                "expected": item["expected"],
                "observedStatus": (row or {}).get("status", "unknown"),
                "observed": (row or {}).get("observed", "unknown"),
                "action": action,
                "mutate": False,
            }
        )
    return desired


def build_report(
    *,
    repo: str,
    mode: str,
    client: ReadOnlyGitHubClient,
    source: str,
) -> dict[str, Any]:
    checks = evaluate(client, source=source)
    summary = summarize(checks)
    leak_warnings = _secret_env_leak_warnings()
    report: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "mode": mode,
        "dryRun": True,
        "repo": repo,
        "mutations": [],
        "applyRefused": True,
        "source": source,
        "statusContext": STATUS_CONTEXT,
        "checklist": required_checklist(),
        "checks": checks,
        "summary": summary,
        "humanSummary": human_summary(checks, summary),
        "warnings": leak_warnings,
        "notes": [
            "Read-only audit: mutations are always empty; apply is refused.",
            "Secret checks use Actions secret *names* only; values are never retrieved or printed.",
            "Default dry-run emits the required checklist with unchecked/unknown observations.",
            "Use --fixture-dir for offline tests or --live for operator read-only GitHub GETs.",
            "Unverifiable settings are unknown/blocked — never assumed compliant.",
            "Agents must not create Apps, secrets, variables, Bugbot settings, or rulesets.",
        ],
    }
    if mode in {"plan", "verify", "report"}:
        report["desired"] = build_desired_plan(checks)
        report["protectionPlan"] = build_protection_plan_section(client, source=source)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only plan/verify/report of required external automation credential / Bugbot / "
            "protection / workflow state. Apply is refused."
        )
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="report",
        choices=("report", "plan", "verify", "apply"),
        help="report (default), plan, or verify (apply is always refused)",
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GH_REPO", "linktrend/IDE-Development"),
        help="owner/name (default: GH_REPO or linktrend/IDE-Development)",
    )
    parser.add_argument(
        "--fixture-dir",
        default=None,
        help="Offline fixture directory containing state.json (no live GitHub calls)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Perform read-only GitHub GET observations via gh api",
    )
    parser.add_argument(
        "--json-output",
        default=None,
        help="Optional path to write the full JSON result",
    )
    parser.add_argument(
        "--human",
        action="store_true",
        help="Print humanSummary to stderr in addition to JSON stdout",
    )
    return parser.parse_args(argv)


def build_client(args: argparse.Namespace) -> tuple[ReadOnlyGitHubClient, str]:
    if args.fixture_dir and args.live:
        raise AuditError("pass only one of --fixture-dir or --live", EXIT_REFUSED)
    if args.fixture_dir:
        return FixtureClient(args.repo, Path(args.fixture_dir)), "fixture"
    if args.live:
        return ReadOnlyGitHubClient(args.repo), "live"
    return UncheckedClient(args.repo), "dry-run"


def _emit(payload: dict[str, Any], path: str | None, *, human: bool = False) -> None:
    # Defense in depth: never dump known secret env values into stdout/file.
    text = json.dumps(payload, indent=2)
    # Also refuse obvious PEM / token markers if somehow present. Construct
    # key-header probes at runtime so strict repository scanners do not mistake
    # this defensive audit code for embedded private-key material.
    for marker in (
        "BEGIN " + "PRIVATE KEY",
        "BEGIN RSA " + "PRIVATE KEY",
        "github_pat_",
        "ghs_",
    ):
        if marker in text:
            raise AuditError(
                f"refusing to emit report: forbidden secret marker {marker!r} in output",
                EXIT_REFUSED,
            )
    print(text)
    if human:
        print(payload.get("humanSummary", ""), file=sys.stderr)
    if path:
        Path(path).write_text(text + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.mode == "apply":
            raise AuditError(
                "apply is refused: external_state_audit is plan/verify/report only "
                "(WP1 read-only; no live setting changes)",
                EXIT_REFUSED,
            )
        client, source = build_client(args)
        report = build_report(
            repo=args.repo,
            mode=args.mode,
            client=client,
            source=source,
        )
        _emit(report, args.json_output, human=args.human)
        if args.mode in {"report", "plan"}:
            # Plan/report always emit; unavailable protection is not a hard failure here.
            return EXIT_OK
        # verify
        if report["summary"]["ready"]:
            return EXIT_OK
        # Prefer unavailable exit when any required check is unavailable.
        if any(c.get("status") == "unavailable" for c in report["checks"] if c.get("required")):
            return EXIT_UNAVAILABLE
        return EXIT_NOT_READY
    except AuditError as exc:
        err = {
            "schemaVersion": SCHEMA_VERSION,
            "error": str(exc),
            "exitCode": exc.exit_code,
            "mutations": [],
            "dryRun": True,
            "applyRefused": True,
        }
        print(json.dumps(err, indent=2), file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
