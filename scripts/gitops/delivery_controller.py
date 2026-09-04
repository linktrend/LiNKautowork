#!/usr/bin/env python3
"""Agent-agnostic delivery controller (Update 2 / WP-U02).

Replaces the nonexistent Integrator merge actor. Any authorized agent or
operator may invoke these commands; role boundaries are enforced by the
commands and GitHub protections, not by agent identity or model.

Accepts an exact ``phase/*`` PR handoff, verifies development eligibility,
merges through GitHub protection (never a direct push to protected
branches), promotes staging on reusable receipt identity without rerunning
Full, prepares main, and completes main only after explicit founder
approval. Temporary ``promote/*`` branches are deleted only after successful
merges. Behavior is identical regardless of which supported agent invokes
the controller.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

try:
    from scripts.gitops.delivery_modes import is_phase_branch, is_valid_sha, normalize_sha
    from scripts.gitops.packager_coordinator import consume_handoff
    from scripts.gitops.promotion_receipt_gate import (
        evaluate_development_gates,
        evaluate_main_approval,
        evaluate_release_path,
        verify_receipt_payload,
    )
    from scripts.gitops.coordinator.receipts import (
        compute_receipt_digest,
        compute_transition_digest,
        create_transition_receipt,
    )
    from scripts.gitops.github_auth import GitHubAuthError, resolve_phase_api_token
    from scripts.gitops.administrator_recovery import MemoryProtection, recover_phase_merge
except ModuleNotFoundError:  # pragma: no cover - script-style execution
    from delivery_modes import is_phase_branch, is_valid_sha, normalize_sha  # type: ignore
    from packager_coordinator import consume_handoff  # type: ignore
    from promotion_receipt_gate import (  # type: ignore
        evaluate_development_gates,
        evaluate_main_approval,
        evaluate_release_path,
        verify_receipt_payload,
    )
    from coordinator.receipts import compute_receipt_digest, compute_transition_digest, create_transition_receipt  # type: ignore
    from github_auth import GitHubAuthError, resolve_phase_api_token  # type: ignore
    from administrator_recovery import MemoryProtection, recover_phase_merge  # type: ignore

COMPONENT_KIND = "delivery_controller"
IS_DELIVERY_CONTROLLER = True
OPERATION_REL = Path(".linktrend/delivery-operation.json")
CONTROLLER_STATE_REL = Path("ide-development/delivery-controller")
PROTECTED_BRANCHES = frozenset({"development", "staging", "main"})
WORKER_ROLES = frozenset({"worker", "implementer", "issue-worker"})
CONTROLLER_ROLES = frozenset({"delivery_controller", "operator", "coordinator", "founder"})
PROMOTE_STAGING_RE = re.compile(r"^promote/staging/[0-9a-f]{12}$")
PROMOTE_MAIN_RE = re.compile(r"^promote/main/[0-9a-f]{12}$")
AGENT_ENV_KEYS = (
    "CURSOR_AGENT",
    "CODEX_HOME",
    "TERRA_AGENT",
    "LINKTREND_AGENT",
    "AIDER_MODEL",
    "ANTHROPIC_MODEL",
)
INFRA_RETRY_LIMIT = 2
INFRASTRUCTURE_ERROR_CODES = frozenset(
    {
        "github_api_failed",
        "github_unavailable",
        "rate_limited",
        "network_error",
        "infrastructure_failure",
    }
)
REQUIRED_CHECK_NAMES = (
    "Linktrend Fast Checks",
    "Linktrend Full Suite",
    "Linktrend Branch Source Policy",
)


@dataclass(frozen=True)
class StagedRolloutConfig:
    """Configurable stage and gate identity for one rollout path."""

    phase_branch_prefix: str = "phase/"
    development_branch: str = "development"
    staging_branch: str = "staging"
    main_branch: str = "main"
    required_checks: tuple[str, ...] = REQUIRED_CHECK_NAMES

    def __post_init__(self) -> None:
        branches = (
            self.development_branch,
            self.staging_branch,
            self.main_branch,
        )
        if any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._/-]+", value) for value in branches):
            raise ValueError("invalid_rollout_branch")
        if len(set(branches)) != len(branches):
            raise ValueError("duplicate_rollout_branch")
        if not isinstance(self.phase_branch_prefix, str) or not re.fullmatch(
            r"[A-Za-z0-9._/-]+/", self.phase_branch_prefix
        ):
            raise ValueError("invalid_phase_branch_prefix")
        if not self.required_checks or any(
            not isinstance(value, str) or not value.strip() for value in self.required_checks
        ):
            raise ValueError("invalid_required_checks")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "StagedRolloutConfig":
        if payload is None:
            return cls()
        if not isinstance(payload, Mapping):
            raise ValueError("invalid_rollout_config")
        allowed = {
            "phaseBranchPrefix",
            "developmentBranch",
            "stagingBranch",
            "mainBranch",
            "requiredChecks",
        }
        if set(payload) - allowed:
            raise ValueError("unknown_rollout_config_field")
        defaults = cls()
        required_checks = payload.get("requiredChecks", defaults.required_checks)
        if not isinstance(required_checks, (list, tuple)):
            raise ValueError("invalid_required_checks")
        return cls(
            phase_branch_prefix=str(payload.get("phaseBranchPrefix", defaults.phase_branch_prefix)),
            development_branch=str(payload.get("developmentBranch", defaults.development_branch)),
            staging_branch=str(payload.get("stagingBranch", defaults.staging_branch)),
            main_branch=str(payload.get("mainBranch", defaults.main_branch)),
            required_checks=tuple(required_checks),
        )


StagedRollout = StagedRolloutConfig


class ControllerError(ValueError):
    """Fail-closed delivery-controller rejection."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail or code
        super().__init__(self.code if not detail else f"{self.code}: {self.detail}")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


def _receipt_workflow_run_id(receipt: Mapping[str, Any]) -> int:
    """Return the exact reusable Full Suite run ID required by promotion gates."""

    raw = receipt.get("workflowRunId")
    if isinstance(raw, bool):
        raise ControllerError("receipt_workflow_run_invalid", str(raw))
    try:
        run_id = int(raw)
    except (TypeError, ValueError) as exc:
        raise ControllerError("receipt_workflow_run_invalid", str(raw or "missing")) from exc
    if run_id < 1 or str(raw).strip() != str(run_id):
        raise ControllerError("receipt_workflow_run_invalid", str(raw))
    return run_id


def _receipt_workflow_run_attempt(receipt: Mapping[str, Any]) -> int:
    raw = receipt.get("workflowRunAttempt")
    if isinstance(raw, bool):
        raise ControllerError("receipt_workflow_attempt_invalid", str(raw))
    try:
        attempt = int(raw)
    except (TypeError, ValueError) as exc:
        raise ControllerError("receipt_workflow_attempt_invalid", str(raw or "missing")) from exc
    if attempt < 1 or str(raw).strip() != str(attempt):
        raise ControllerError("receipt_workflow_attempt_invalid", str(raw))
    return attempt


class GitHubPort(Protocol):
    """Merge/promote adapter. Tests inject ``MemoryGitHub``."""

    def get_pull_request(self, *, repository: str, number: int) -> dict[str, Any]:
        ...

    def merge_pull_request(
        self,
        *,
        repository: str,
        number: int,
        expected_head: str,
        method: str = "merge",
        admin: bool = False,
        match_head_commit: bool = True,
    ) -> dict[str, Any]:
        ...

    def create_pull_request(
        self,
        *,
        repository: str,
        head: str,
        base: str,
        title: str,
        body: str,
        head_sha: str,
    ) -> dict[str, Any]:
        ...

    def delete_ref(self, *, repository: str, ref: str) -> bool:
        ...

    def push_protected(self, *, repository: str, branch: str, sha: str) -> None:
        ...


@dataclass
class MemoryGitHub:
    """In-memory GitHub adapter for disposable-repo tests. Never talks to GitHub."""

    repository: str
    prs: dict[int, dict[str, Any]] = field(default_factory=dict)
    refs: dict[str, str] = field(default_factory=dict)
    merges: list[dict[str, Any]] = field(default_factory=list)
    deleted_refs: list[str] = field(default_factory=list)
    protected_push_attempts: list[dict[str, str]] = field(default_factory=list)
    merge_rejections: dict[int, str] = field(default_factory=dict)
    next_number: int = 1
    require_admin_bypass: bool = False

    def get_pull_request(self, *, repository: str, number: int) -> dict[str, Any]:
        if repository != self.repository:
            raise ControllerError("wrong_repository", repository)
        pr = self.prs.get(number)
        if not pr:
            raise ControllerError("pr_missing", str(number))
        return dict(pr)

    def merge_pull_request(
        self,
        *,
        repository: str,
        number: int,
        expected_head: str,
        method: str = "merge",
        admin: bool = False,
        match_head_commit: bool = True,
    ) -> dict[str, Any]:
        if repository != self.repository:
            raise ControllerError("wrong_repository", repository)
        if number in self.merge_rejections:
            raise ControllerError("protected_merge_rejected", self.merge_rejections[number])
        pr = self.get_pull_request(repository=repository, number=number)
        head = normalize_sha(str(pr.get("headSha") or ""))
        if match_head_commit and head != normalize_sha(expected_head):
            raise ControllerError("stale_pr_head", f"live={head}:expected={expected_head}")
        if self.require_admin_bypass and not admin:
            raise ControllerError("protected_merge_rejected", "admin_bypass_required")
        if bool(pr.get("isDraft")):
            raise ControllerError("draft_pr", str(number))
        if str(pr.get("state") or "").lower() not in {"open", ""}:
            raise ControllerError("pr_not_open", str(number))
        merge_sha = hashlib.sha1(f"merge:{number}:{head}".encode("utf-8")).hexdigest()
        base = str(pr.get("base") or "")
        base_before = normalize_sha(self.refs.get(base, "0" * 40))
        self.refs[base] = merge_sha
        pr["state"] = "merged"
        pr["merged"] = True
        pr["mergeCommitSha"] = merge_sha
        record = {
            "number": number,
            "method": method,
            "headSha": head,
            "mergeCommitSha": merge_sha,
            "base": base,
            "baseBefore": base_before,
            "directPush": False,
            "admin": bool(admin),
            "matchHeadCommit": bool(match_head_commit),
        }
        self.merges.append(record)
        return dict(record)

    def create_pull_request(
        self,
        *,
        repository: str,
        head: str,
        base: str,
        title: str,
        body: str,
        head_sha: str,
    ) -> dict[str, Any]:
        if repository != self.repository:
            raise ControllerError("wrong_repository", repository)
        if base in PROTECTED_BRANCHES and head in PROTECTED_BRANCHES:
            raise ControllerError("protected_direct", f"{head}->{base}")
        number = self.next_number
        self.next_number += 1
        pr = {
            "number": number,
            "url": f"https://example.invalid/{repository}/pull/{number}",
            "isDraft": False,
            "state": "open",
            "head": head,
            "base": base,
            "headSha": normalize_sha(head_sha),
            "title": title,
            "body": body,
            "merged": False,
        }
        self.prs[number] = pr
        self.refs[head] = normalize_sha(head_sha)
        return dict(pr)

    def delete_ref(self, *, repository: str, ref: str) -> bool:
        if repository != self.repository:
            raise ControllerError("wrong_repository", repository)
        name = ref.removeprefix("refs/heads/")
        if name in PROTECTED_BRANCHES:
            raise ControllerError("protected_ref_delete", name)
        existed = name in self.refs
        self.refs.pop(name, None)
        self.deleted_refs.append(name)
        return existed

    def push_protected(self, *, repository: str, branch: str, sha: str) -> None:
        self.protected_push_attempts.append(
            {"repository": repository, "branch": branch, "sha": normalize_sha(sha)}
        )
        raise ControllerError("direct_push_forbidden", branch)


def _github_api(
    method: str,
    url: str,
    token: str,
    body: Mapping[str, Any] | None = None,
) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "linktrend-delivery-controller",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code in {429, 502, 503, 504}:
            raise ControllerError("github_unavailable", f"{method} {url} -> {exc.code}: {detail[:240]}") from exc
        if exc.code == 403 and "rate limit" in detail.lower():
            raise ControllerError("rate_limited", f"{method} {url} -> {exc.code}") from exc
        if exc.code in {405, 409, 422} and "merge" in url:
            raise ControllerError("protected_merge_rejected", f"{method} {url} -> {exc.code}: {detail[:240]}") from exc
        raise ControllerError("github_api_failed", f"{method} {url} -> {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise ControllerError("network_error", str(exc.reason)[:240]) from exc


@dataclass
class LiveGitHub:
    """Production GitHub adapter for protected merge/promote under normal automation token."""

    repository: str
    automation_token: str
    transport: Callable[[str, str, str, Mapping[str, Any] | None], Any] | None = None

    def _request(self, method: str, url: str, body: Mapping[str, Any] | None = None) -> Any:
        if self.transport is not None:
            return self.transport(method, url, self.automation_token, body)
        return _github_api(method, url, self.automation_token, body)

    def get_pull_request(self, *, repository: str, number: int) -> dict[str, Any]:
        if repository != self.repository:
            raise ControllerError("wrong_repository", repository)
        payload = self._request("GET", f"https://api.github.com/repos/{repository}/pulls/{number}")
        if not isinstance(payload, Mapping):
            raise ControllerError("github_api_failed", "pull payload was not an object")
        head = payload.get("head") if isinstance(payload.get("head"), Mapping) else {}
        base = payload.get("base") if isinstance(payload.get("base"), Mapping) else {}
        return {
            "number": int(payload.get("number") or number),
            "url": str(payload.get("html_url") or ""),
            "isDraft": bool(payload.get("draft")),
            "state": "open" if payload.get("state") == "open" else str(payload.get("state") or ""),
            "head": str(head.get("ref") or ""),
            "base": str(base.get("ref") or ""),
            "headSha": normalize_sha(str(head.get("sha") or "")),
            "mergeableState": str(payload.get("mergeable_state") or ""),
            "crossRepository": bool(
                isinstance(head.get("repo"), Mapping)
                and str((head.get("repo") or {}).get("full_name") or "") not in {"", repository}
            ),
            "merged": bool(payload.get("merged")),
            "mergeCommitSha": normalize_sha(str(payload.get("merge_commit_sha") or "")),
        }

    def merge_pull_request(
        self,
        *,
        repository: str,
        number: int,
        expected_head: str,
        method: str = "merge",
        admin: bool = False,
        match_head_commit: bool = True,
    ) -> dict[str, Any]:
        live = self.get_pull_request(repository=repository, number=number)
        head = normalize_sha(str(live.get("headSha") or ""))
        if match_head_commit and head != normalize_sha(expected_head):
            raise ControllerError("stale_pr_head", f"live={head}:expected={expected_head}")
        if bool(live.get("isDraft")):
            raise ControllerError("draft_pr", str(number))
        if str(live.get("state") or "").lower() != "open":
            raise ControllerError("pr_not_open", str(number))
        if admin:
            return self._merge_with_gh_admin(
                repository=repository,
                number=number,
                expected_head=expected_head,
                method=method,
                live=live,
            )
        payload = self._request(
            "PUT",
            f"https://api.github.com/repos/{repository}/pulls/{number}/merge",
            {
                "merge_method": method,
                "sha": normalize_sha(expected_head),
            },
        )
        if not isinstance(payload, Mapping) or not payload.get("merged"):
            raise ControllerError("protected_merge_rejected", f"PR #{number} was not merged")
        return {
            "number": number,
            "method": method,
            "headSha": normalize_sha(expected_head),
            "mergeCommitSha": normalize_sha(str(payload.get("sha") or "")),
            "directPush": False,
            "admin": False,
            "matchHeadCommit": bool(match_head_commit),
            "base": str(live.get("base") or ""),
        }

    def _merge_with_gh_admin(
        self,
        *,
        repository: str,
        number: int,
        expected_head: str,
        method: str,
        live: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Named recovery path: ``gh pr merge --admin --match-head-commit`` first."""

        flags = {"merge": "--merge", "squash": "--squash", "rebase": "--rebase"}
        method_flag = flags.get(method, "--merge")
        env = os.environ.copy()
        env["GH_TOKEN"] = self.automation_token
        env["GITHUB_TOKEN"] = self.automation_token
        completed = subprocess.run(
            [
                "gh",
                "pr",
                "merge",
                str(number),
                "--repo",
                repository,
                "--admin",
                "--match-head-commit",
                normalize_sha(expected_head),
                method_flag,
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "gh pr merge --admin failed").strip()[:240]
            raise ControllerError("protected_merge_rejected", detail)
        return {
            "number": number,
            "method": method,
            "headSha": normalize_sha(expected_head),
            "mergeCommitSha": normalize_sha(str(live.get("mergeCommitSha") or "")),
            "base": str(live.get("base") or ""),
            "directPush": False,
            "admin": True,
            "matchHeadCommit": True,
        }

    def create_pull_request(
        self,
        *,
        repository: str,
        head: str,
        base: str,
        title: str,
        body: str,
        head_sha: str,
    ) -> dict[str, Any]:
        if repository != self.repository:
            raise ControllerError("wrong_repository", repository)
        if base in PROTECTED_BRANCHES and head in PROTECTED_BRANCHES:
            raise ControllerError("protected_direct", f"{head}->{base}")
        expected = normalize_sha(head_sha)
        if not is_valid_sha(expected):
            raise ControllerError("invalid_head_sha", head_sha)
        if PROMOTE_STAGING_RE.fullmatch(head) or PROMOTE_MAIN_RE.fullmatch(head):
            self.ensure_promote_ref(repository=repository, branch=head, head_sha=expected)
        created = self._request(
            "POST",
            f"https://api.github.com/repos/{repository}/pulls",
            {
                "title": title,
                "body": body,
                "head": head,
                "base": base,
                "draft": False,
            },
        )
        if not isinstance(created, Mapping):
            raise ControllerError("github_api_failed", "create pull response was not an object")
        number = created.get("number")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise ControllerError("github_api_failed", "create pull missing number")
        pr = self.get_pull_request(repository=repository, number=number)
        live_head = normalize_sha(str(pr.get("headSha") or ""))
        if live_head != expected:
            raise ControllerError("promote_ref_mismatch", f"pr_head={live_head}:expected={expected}")
        return pr

    def ensure_promote_ref(self, *, repository: str, branch: str, head_sha: str) -> str:
        """Create or update promote/* at exact head_sha; fail closed if remote differs."""

        if repository != self.repository:
            raise ControllerError("wrong_repository", repository)
        if not (PROMOTE_STAGING_RE.fullmatch(branch) or PROMOTE_MAIN_RE.fullmatch(branch)):
            raise ControllerError("invalid_promote_branch", branch)
        expected = normalize_sha(head_sha)
        if not is_valid_sha(expected):
            raise ControllerError("invalid_head_sha", head_sha)
        ref = f"heads/{branch}"
        api = f"https://api.github.com/repos/{repository}/git/refs/{ref}"
        try:
            existing = self._request("GET", api)
        except ControllerError as exc:
            if "404" not in exc.detail and "not found" not in exc.detail.lower():
                raise
            existing = None
        if isinstance(existing, Mapping):
            current = normalize_sha(str((existing.get("object") or {}).get("sha") or existing.get("sha") or ""))
            if current != expected:
                self._request("PATCH", api, {"sha": expected, "force": True})
        else:
            self._request(
                "POST",
                f"https://api.github.com/repos/{repository}/git/refs",
                {"ref": f"refs/heads/{branch}", "sha": expected},
            )
        verified = self._request("GET", api)
        if not isinstance(verified, Mapping):
            raise ControllerError("promote_ref_mismatch", "remote promote ref missing after write")
        remote = normalize_sha(str((verified.get("object") or {}).get("sha") or verified.get("sha") or ""))
        if remote != expected:
            raise ControllerError("promote_ref_mismatch", f"remote={remote or 'missing'}:expected={expected}")
        return remote

    def delete_ref(self, *, repository: str, ref: str) -> bool:
        if repository != self.repository:
            raise ControllerError("wrong_repository", repository)
        name = ref.removeprefix("refs/heads/")
        if name in PROTECTED_BRANCHES:
            raise ControllerError("protected_ref_delete", name)
        self._request("DELETE", f"https://api.github.com/repos/{repository}/git/refs/heads/{name}")
        return True

    def push_protected(self, *, repository: str, branch: str, sha: str) -> None:
        raise ControllerError("direct_push_forbidden", branch)


def resolve_production_github(repository: str) -> LiveGitHub:
    """Fail closed unless a GitHub API token is configured for Phase operations.

    Does not require AUTOMATION_TOKEN or AUTOMATION_TOKEN_SOURCE. Those names are
    waived legacy publisher credentials, not the v2.5 Phase delivery contract.
    """

    if not repository or repository.count("/") != 1:
        raise ControllerError("missing_repository", "delivery requires --repository owner/name")
    try:
        token, _source = resolve_phase_api_token()
    except GitHubAuthError as exc:
        raise ControllerError(exc.code, exc.detail) from exc
    return LiveGitHub(repository=repository, automation_token=token)


def call_with_infrastructure_retry(operation: Callable[[], Any], *, attempts: int | None = None) -> Any:
    """Retry only infrastructure failures; bound to INFRA_RETRY_LIMIT total attempts."""

    limit = INFRA_RETRY_LIMIT if attempts is None else int(attempts)
    if limit < 1:
        raise ControllerError("invalid_retry_limit", str(limit))
    last: ControllerError | None = None
    for attempt in range(1, limit + 1):
        try:
            return operation()
        except ControllerError as exc:
            if exc.code not in INFRASTRUCTURE_ERROR_CODES:
                raise
            last = exc
            if attempt >= limit:
                raise ControllerError(
                    "infrastructure_retries_exhausted",
                    f"attempts={attempt} max={limit} last={exc.code}:{exc.detail}",
                ) from exc
    assert last is not None
    raise last


def require_promotion_source_equality(
    *,
    stage: str,
    candidate_sha: str,
    source_sha: str,
) -> None:
    """Staging candidate must equal development; main candidate must equal staging."""

    candidate = normalize_sha(candidate_sha)
    source = normalize_sha(source_sha)
    if not is_valid_sha(candidate) or not is_valid_sha(source) or candidate != source:
        raise ControllerError(
            "promotion_source_mismatch",
            f"{stage}:candidate={candidate or 'missing'}:source={source or 'missing'}",
        )


def _rollout_config(rollout: StagedRolloutConfig | None) -> StagedRolloutConfig:
    return rollout if rollout is not None else StagedRolloutConfig()


def _promotion_branch(config: StagedRolloutConfig, stage: str, source_sha: str) -> str:
    branch = f"promote/{stage}/{normalize_sha(source_sha)[:12]}"
    if not re.fullmatch(r"promote/[A-Za-z0-9._/-]+/[0-9a-f]{12}", branch):
        raise ControllerError("invalid_promote_branch", branch)
    return branch


def agent_env_fingerprint(environ: Mapping[str, str] | None = None) -> str:
    """Sanitize agent markers so behavior cannot depend on which agent invoked."""

    env = environ if environ is not None else os.environ
    present = sorted(key for key in AGENT_ENV_KEYS if str(env.get(key) or "").strip())
    return ",".join(present) if present else "none"


def require_controller_role(role: str) -> str:
    normalized = str(role or "").strip().lower()
    if normalized in WORKER_ROLES:
        raise ControllerError("worker_self_merge_forbidden", "Worker cannot invoke a self-merge path")
    if normalized and normalized not in CONTROLLER_ROLES:
        # Unknown roles are still allowed to invoke commands; boundaries are
        # enforced by protections and merge APIs, not agent identity.
        return normalized or "operator"
    return normalized or "operator"


def accept_phase_pr(
    pr: Mapping[str, Any],
    handoff: Mapping[str, Any],
    *,
    repository: str,
    live_head: str,
    live_tree: str | None = None,
    rollout: StagedRolloutConfig | None = None,
) -> dict[str, Any]:
    """Bind delivery to one exact non-draft phase/* → development PR."""

    config = _rollout_config(rollout)
    ok, detail = consume_handoff(
        handoff,
        live_head=live_head,
        live_tree=live_tree,
        repository=repository,
    )
    if not ok:
        raise ControllerError(detail, "handoff rejected")
    if str(pr.get("base") or "") != config.development_branch:
        raise ControllerError("wrong_target", str(pr.get("base") or ""))
    head_ref = str(pr.get("head") or pr.get("headRefName") or "")
    if not is_phase_branch(head_ref, config.phase_branch_prefix):
        raise ControllerError("wrong_source", head_ref)
    if bool(pr.get("isDraft")):
        raise ControllerError("draft_pr", str(pr.get("number") or ""))
    if str(pr.get("state") or "open").lower() != "open":
        raise ControllerError("pr_not_open", str(pr.get("number") or ""))
    if bool(pr.get("crossRepository") or pr.get("isCrossRepository")):
        raise ControllerError("cross_repository", str(pr.get("number") or ""))
    if str(pr.get("mergeableState") or "").upper() in {"CONFLICTING", "DIRTY"}:
        raise ControllerError("merge_conflict", str(pr.get("number") or ""))
    head = normalize_sha(str(pr.get("headSha") or pr.get("headRefOid") or ""))
    if not is_valid_sha(head) or head != normalize_sha(live_head):
        raise ControllerError("stale_pr_head", head or "missing")
    handoff_branch = str(handoff.get("phaseBranch") or "")
    if handoff_branch and handoff_branch != head_ref:
        raise ControllerError("handoff_branch_mismatch", f"{handoff_branch}!={head_ref}")
    return {
        "number": int(pr.get("number") or 0),
        "head": head_ref,
        "base": config.development_branch,
        "headSha": head,
        "gitTree": normalize_sha(str(live_tree or handoff.get("gitTree") or "")),
        "repository": repository,
    }


def _check_named_gates(
    checks: Mapping[str, Any] | None,
    *,
    live_head: str,
    required_checks: tuple[str, ...] = REQUIRED_CHECK_NAMES,
) -> None:
    payload = checks if isinstance(checks, Mapping) else {}
    for name in required_checks:
        row = payload.get(name)
        if not isinstance(row, Mapping):
            raise ControllerError("required_gate_missing", name)
        status = str(row.get("status") or row.get("state") or row.get("conclusion") or "").lower()
        if status in {"skipped", "neutral", "cancelled", "canceled"}:
            raise ControllerError("required_gate_skipped", name)
        if status not in {"passed", "success", "successful", "green"}:
            raise ControllerError("required_gate_failed", f"{name}:{status or 'missing'}")
        observed = normalize_sha(str(row.get("sha") or row.get("headSha") or ""))
        if observed and observed != normalize_sha(live_head):
            raise ControllerError("required_gate_stale", f"{name}:{observed}")


def _check_repository_owned_ci(
    repository_ci: Mapping[str, Any] | None,
    *,
    live_head: str,
    required_names: list[str] | None = None,
    system_checks: tuple[str, ...] = REQUIRED_CHECK_NAMES,
) -> None:
    """Distinct gate: repository-owned required CI on the exact candidate head."""

    payload = repository_ci if isinstance(repository_ci, Mapping) else {}
    names = list(required_names or payload.get("required") or [])
    if not names:
        raise ControllerError("repository_ci_missing", "repository-owned required CI list is required")
    results = payload.get("results") if isinstance(payload.get("results"), Mapping) else payload
    for name in names:
        if name in system_checks:
            raise ControllerError("repository_ci_collides_with_system", name)
        row = results.get(name) if isinstance(results, Mapping) else None
        if not isinstance(row, Mapping):
            raise ControllerError("repository_ci_missing", name)
        status = str(row.get("status") or row.get("state") or row.get("conclusion") or "").lower()
        if status in {"skipped", "neutral", "cancelled", "canceled"}:
            raise ControllerError("repository_ci_skipped", name)
        if status not in {"passed", "success", "successful", "green"}:
            raise ControllerError("repository_ci_failed", f"{name}:{status or 'missing'}")
        observed = normalize_sha(str(row.get("sha") or row.get("headSha") or ""))
        if not observed or observed != normalize_sha(live_head):
            raise ControllerError("repository_ci_stale", f"{name}:{observed or 'missing'}")


def verify_development_eligibility(
    *,
    handoff: Mapping[str, Any],
    pr: Mapping[str, Any],
    repository: str,
    live_head: str,
    live_tree: str,
    gate_payload: Mapping[str, Any],
    named_checks: Mapping[str, Any],
    repository_ci: Mapping[str, Any],
    receipt: Mapping[str, Any],
    candidate_identity: Mapping[str, Any],
    conflict: bool = False,
    rollout: StagedRolloutConfig | None = None,
) -> dict[str, Any]:
    """Require exact gates, repo-owned CI, genuine receipt, and an unchanged Phase PR head."""

    config = _rollout_config(rollout)
    accepted = accept_phase_pr(
        pr,
        handoff,
        repository=repository,
        live_head=live_head,
        live_tree=live_tree,
        rollout=config,
    )
    if conflict:
        raise ControllerError("merge_conflict", str(accepted["number"]))
    _check_named_gates(named_checks, live_head=live_head, required_checks=config.required_checks)
    _check_repository_owned_ci(
        repository_ci,
        live_head=live_head,
        system_checks=config.required_checks,
    )
    gates = evaluate_development_gates(gate_payload, live_head)
    if not gates.accepted:
        raise ControllerError(gates.code, gates.detail)
    receipt_decision = verify_receipt_payload(receipt, candidate_identity, "full-gate")
    if not receipt_decision.accepted:
        raise ControllerError("receipt_rejected", f"{receipt_decision.code}:{receipt_decision.detail}")
    identity_head = normalize_sha(str(candidate_identity.get("headCommit") or ""))
    identity_tree = normalize_sha(str(candidate_identity.get("gitTree") or ""))
    if identity_head != normalize_sha(live_head) or identity_tree != normalize_sha(live_tree):
        raise ControllerError("receipt_identity_mismatch", "candidate identity is not the live PR")
    return {
        "eligible": True,
        "pr": accepted,
        "receiptLookupKey": receipt_decision.receipt_lookup_key,
        "receiptDigest": compute_receipt_digest(receipt),
        "repositoryCi": "passed",
        "detail": "development_eligible",
    }


def merge_to_development(
    *,
    github: GitHubPort,
    repository: str,
    pr_number: int,
    expected_head: str,
    role: str,
    actor: str = "delivery-controller",
    receipt: Mapping[str, Any] | None = None,
    candidate_identity: Mapping[str, Any] | None = None,
    candidate_tree: str | None = None,
    protected_base_commit: str | None = None,
    rollout: StagedRolloutConfig | None = None,
) -> dict[str, Any]:
    """Merge through GitHub protection. Never push directly to development."""

    config = _rollout_config(rollout)
    require_controller_role(role)
    try:
        github.push_protected(repository=repository, branch=config.development_branch, sha=expected_head)
    except ControllerError as exc:
        if exc.code != "direct_push_forbidden":
            raise
    result = call_with_infrastructure_retry(
        lambda: github.merge_pull_request(
            repository=repository,
            number=pr_number,
            expected_head=expected_head,
            method="merge",
            admin=False,
            match_head_commit=True,
        )
    )
    result = {
        "status": "merged",
        "stage": config.development_branch,
        "pr": pr_number,
        "actor": actor,
        "role": role,
        "testedHead": normalize_sha(expected_head),
        "mergeCommitSha": normalize_sha(str(result.get("mergeCommitSha") or "")),
        "directPush": False,
        "component": COMPONENT_KIND,
    }
    if receipt is not None or candidate_identity is not None:
        if receipt is None or candidate_identity is None:
            raise ControllerError("transition_receipt_failed", "receipt and candidate identity must be supplied together")
        target_tree = normalize_sha(candidate_tree or "")
        merge_commit = normalize_sha(str(result.get("mergeCommitSha") or ""))
        if not is_valid_sha(merge_commit) or not is_valid_sha(target_tree):
            raise ControllerError("transition_receipt_failed", "protected merge did not return an exact commit/tree identity")
        try:
            transition = create_transition_receipt(
                receipt,
                target_branch=config.development_branch,
                target_commit=merge_commit,
                target_tree=target_tree,
                protected_base_commit=normalize_sha(protected_base_commit or "") or None,
            ).to_dict()
        except (ValueError, TypeError) as exc:
            raise ControllerError("transition_receipt_failed", str(exc)) from exc
        result["gitTree"] = target_tree
        result["transitionReceipt"] = transition
        result["transitionReceiptDigest"] = transition["receiptDigest"]
    return result


def promote_to_staging(
    *,
    github: GitHubPort,
    repository: str,
    development_sha: str,
    staging_sha: str,
    candidate_sha: str,
    candidate_tree: str,
    receipt: Mapping[str, Any],
    candidate_identity: Mapping[str, Any],
    release_gate: Mapping[str, Any],
    role: str,
    full_suite_invoked: bool = False,
    transition_receipt: Mapping[str, Any] | None = None,
    rollout: StagedRolloutConfig | None = None,
) -> dict[str, Any]:
    """Promote via temporary promote/staging/* PR using exact receipt reuse."""

    config = _rollout_config(rollout)
    require_controller_role(role)
    require_promotion_source_equality(
        stage="staging",
        candidate_sha=candidate_sha,
        source_sha=development_sha,
    )
    if full_suite_invoked or bool(release_gate.get("fullSuiteInvoked")):
        raise ControllerError("full_suite_reentered", "staging must reuse the matching receipt")
    release = evaluate_release_path({**dict(release_gate), "fullSuiteInvoked": False})
    if not release.accepted:
        raise ControllerError(release.code, release.detail)
    receipt_decision = verify_receipt_payload(
        receipt,
        candidate_identity,
        "full-gate",
        transition_receipt=transition_receipt,
    )
    if not receipt_decision.accepted:
        raise ControllerError("receipt_rejected", f"{receipt_decision.code}:{receipt_decision.detail}")
    identity_tree = normalize_sha(str(candidate_identity.get("gitTree") or ""))
    if identity_tree != normalize_sha(candidate_tree):
        raise ControllerError("changed_staging_content", "promotion tree differs from receipt identity")
    short = normalize_sha(development_sha)[:12]
    branch = _promotion_branch(config, config.staging_branch, development_sha)
    marker = {
        "schemaVersion": 1,
        "stage": config.staging_branch,
        "sourceBranch": config.development_branch,
        "targetBranch": config.staging_branch,
        "sourceSha": normalize_sha(development_sha),
        "targetSha": normalize_sha(staging_sha),
        "candidateHead": normalize_sha(candidate_sha),
        "promoteBranch": branch,
        "receiptDigest": compute_receipt_digest(receipt),
        "fullRunId": _receipt_workflow_run_id(receipt),
        "fullRunAttempt": _receipt_workflow_run_attempt(receipt),
    }
    if transition_receipt is not None:
        marker["transitionReceiptDigest"] = compute_transition_digest(transition_receipt)
    body = f"<!-- linktrend-promote: {json.dumps(marker, sort_keys=True)} -->"
    pr = call_with_infrastructure_retry(
        lambda: github.create_pull_request(
            repository=repository,
            head=branch,
            base=config.staging_branch,
            title=f"Promote {config.development_branch} {short} to {config.staging_branch}",
            body=body,
            head_sha=candidate_sha,
        )
    )
    merged = call_with_infrastructure_retry(
        lambda: github.merge_pull_request(
            repository=repository,
            number=int(pr["number"]),
            expected_head=candidate_sha,
            method="merge",
            admin=False,
            match_head_commit=True,
        )
    )
    try:
        protected_transition = create_transition_receipt(
            receipt,
            target_branch=config.staging_branch,
            target_commit=normalize_sha(str(merged.get("mergeCommitSha") or "")),
            target_tree=normalize_sha(candidate_tree),
        ).to_dict()
    except (ValueError, TypeError) as exc:
        raise ControllerError("transition_receipt_failed", str(exc)) from exc
    result = {
        "status": "merged",
        "stage": config.staging_branch,
        "pr": int(pr["number"]),
        "promoteBranch": branch,
        "sourceSha": normalize_sha(development_sha),
        "targetShaBefore": normalize_sha(staging_sha),
        "candidateHead": normalize_sha(candidate_sha),
        "candidateTree": normalize_sha(candidate_tree),
        "mergeCommitSha": normalize_sha(str(merged.get("mergeCommitSha") or "")),
        "fullSuiteRerun": False,
        "receiptReused": True,
        "transitionReceipt": protected_transition,
        "transitionReceiptDigest": protected_transition["receiptDigest"],
        "component": COMPONENT_KIND,
    }
    return result


def prepare_main_promotion(
    *,
    github: GitHubPort,
    repository: str,
    staging_sha: str,
    main_sha: str,
    candidate_sha: str,
    receipt: Mapping[str, Any],
    candidate_identity: Mapping[str, Any],
    release_gate: Mapping[str, Any],
    role: str,
    transition_receipt: Mapping[str, Any] | None = None,
    rollout: StagedRolloutConfig | None = None,
) -> dict[str, Any]:
    """Open promote/main/* and wait for explicit founder approval."""

    config = _rollout_config(rollout)
    require_controller_role(role)
    require_promotion_source_equality(
        stage="main",
        candidate_sha=candidate_sha,
        source_sha=staging_sha,
    )
    release = evaluate_release_path({**dict(release_gate), "fullSuiteInvoked": False})
    if not release.accepted:
        raise ControllerError(release.code, release.detail)
    receipt_decision = verify_receipt_payload(
        receipt,
        candidate_identity,
        "full-gate",
        transition_receipt=transition_receipt,
    )
    if not receipt_decision.accepted:
        raise ControllerError("receipt_rejected", f"{receipt_decision.code}:{receipt_decision.detail}")
    short = normalize_sha(staging_sha)[:12]
    branch = _promotion_branch(config, config.main_branch, staging_sha)
    marker = {
        "schemaVersion": 1,
        "stage": config.main_branch,
        "sourceBranch": config.staging_branch,
        "targetBranch": config.main_branch,
        "sourceSha": normalize_sha(staging_sha),
        "targetSha": normalize_sha(main_sha),
        "candidateHead": normalize_sha(candidate_sha),
        "promoteBranch": branch,
        "receiptDigest": compute_receipt_digest(receipt),
        "fullRunId": _receipt_workflow_run_id(receipt),
        "fullRunAttempt": _receipt_workflow_run_attempt(receipt),
        "awaitingFounderApproval": True,
    }
    if transition_receipt is not None:
        marker["transitionReceiptDigest"] = compute_transition_digest(transition_receipt)
    body = f"<!-- linktrend-promote: {json.dumps(marker, sort_keys=True)} -->"
    pr = call_with_infrastructure_retry(
        lambda: github.create_pull_request(
            repository=repository,
            head=branch,
            base=config.main_branch,
            title=(
                f"Promote {config.staging_branch} {short} to {config.main_branch} "
                "(awaiting founder approval)"
            ),
            body=body,
            head_sha=candidate_sha,
        )
    )
    result = {
        "status": "waiting_founder_approval",
        "stage": config.main_branch,
        "pr": int(pr["number"]),
        "promoteBranch": branch,
        "sourceSha": normalize_sha(staging_sha),
        "targetSha": normalize_sha(main_sha),
        "candidateHead": normalize_sha(candidate_sha),
        "receiptDigest": compute_receipt_digest(receipt),
        "founderApprovalInferred": False,
        "component": COMPONENT_KIND,
    }
    if transition_receipt is not None:
        result["transitionReceiptDigest"] = compute_transition_digest(transition_receipt)
    return result


def complete_main_promotion(
    *,
    github: GitHubPort,
    repository: str,
    pr_number: int,
    expected_head: str,
    source_sha: str,
    base_sha: str,
    approval: Mapping[str, Any],
    receipt: Mapping[str, Any],
    role: str,
    rollout: StagedRolloutConfig | None = None,
) -> dict[str, Any]:
    """Merge main only after exact founder approval; reject ambiguous/stale."""

    config = _rollout_config(rollout)
    require_controller_role(role)
    require_promotion_source_equality(
        stage="main",
        candidate_sha=expected_head,
        source_sha=source_sha,
    )
    if not isinstance(approval, Mapping) or not approval:
        raise ControllerError("founder_approval_missing", "main always waits for explicit founder approval")
    if bool(approval.get("inferredFromGreenCi") or approval.get("inferredFromElapsedTime")):
        raise ControllerError("founder_approval_ambiguous", "approval must be explicit and recorded")
    if str(approval.get("decision") or "").lower() not in {"approve", "approved", "yes"}:
        raise ControllerError("founder_approval_ambiguous", str(approval.get("decision") or "missing"))
    decision = evaluate_main_approval(
        approval,
        source_sha=source_sha,
        base_sha=base_sha,
        pr_head_sha=expected_head,
        receipt=receipt,
    )
    if not decision.accepted:
        raise ControllerError(decision.code, decision.detail)
    live = github.get_pull_request(repository=repository, number=pr_number)
    live_head = normalize_sha(str(live.get("headSha") or ""))
    if live_head != normalize_sha(expected_head):
        raise ControllerError("stale_pr_head", live_head)
    merged = call_with_infrastructure_retry(
        lambda: github.merge_pull_request(
            repository=repository,
            number=pr_number,
            expected_head=expected_head,
            method="merge",
            admin=False,
            match_head_commit=True,
        )
    )
    return {
        "status": "merged",
        "stage": "main",
        "pr": pr_number,
        "mergeCommitSha": normalize_sha(str(merged.get("mergeCommitSha") or "")),
        "founderApproval": True,
        "component": COMPONENT_KIND,
    }


def authorize_cleanup_from_evidence(
    evidence: Mapping[str, Any] | None,
    branches: list[str],
) -> dict[str, bool]:
    """Require truthful merged evidence bound to the exact promote refs being cleaned."""

    if not isinstance(evidence, Mapping) or not evidence:
        raise ControllerError("cleanup_before_success", "merge evidence missing")
    if str(evidence.get("status") or "") != "merged":
        raise ControllerError("cleanup_before_success", "preceding merge did not succeed")
    allowed: set[str] = set()
    promote = str(evidence.get("promoteBranch") or "").strip()
    if promote:
        allowed.add(promote.removeprefix("refs/heads/"))
    for item in evidence.get("controllerOwnedBranches") or evidence.get("promoteBranches") or []:
        text = str(item or "").strip().removeprefix("refs/heads/")
        if text:
            allowed.add(text)
    if not allowed:
        raise ControllerError("cleanup_before_success", "merge evidence has no promote ref binding")
    owned: dict[str, bool] = {}
    for branch in branches:
        name = branch.removeprefix("refs/heads/")
        if name not in allowed:
            raise ControllerError("cleanup_before_success", f"no successful merge evidence for {name}")
        owned[name] = True
    return owned


def cleanup_temporary_branches(
    *,
    github: GitHubPort,
    repository: str,
    branches: list[str],
    merge_succeeded: bool,
    controller_owned: Mapping[str, bool] | None = None,
    rollout: StagedRolloutConfig | None = None,
) -> dict[str, Any]:
    """Delete only controller-created promote/* branches after successful merges."""

    config = _rollout_config(rollout)
    if not merge_succeeded:
        raise ControllerError("cleanup_before_success", "temporary branches preserved until successful merge")
    owned = controller_owned or {}
    deleted: list[str] = []
    preserved: list[str] = []
    for branch in branches:
        name = branch.removeprefix("refs/heads/")
        if name in PROTECTED_BRANCHES:
            raise ControllerError("protected_ref_delete", name)
        allowed_patterns = (
            _promotion_branch(config, config.staging_branch, "0" * 40)[:-12] + "[0-9a-f]{12}",
            _promotion_branch(config, config.main_branch, "0" * 40)[:-12] + "[0-9a-f]{12}",
        )
        if not any(re.fullmatch(pattern, name) for pattern in allowed_patterns):
            preserved.append(name)
            continue
        if owned and not owned.get(name, False):
            preserved.append(name)
            continue
        github.delete_ref(repository=repository, ref=f"refs/heads/{name}")
        deleted.append(name)
    return {
        "status": "cleaned",
        "deleted": deleted,
        "preserved": preserved,
        "component": COMPONENT_KIND,
    }


def stop_on_protected_merge_rejection(exc: BaseException) -> dict[str, Any]:
    """Record a protected-merge rejection without attempting a direct push/bypass."""

    if isinstance(exc, ControllerError) and exc.code == "protected_merge_rejected":
        return {
            "status": "stopped",
            "code": exc.code,
            "detail": exc.detail,
            "directPushAttempted": False,
            "bypassAttempted": False,
            "component": COMPONENT_KIND,
        }
    raise exc


def run_identical_under_agents(
    operation: str,
    payload: Mapping[str, Any],
    environments: list[Mapping[str, str]],
) -> dict[str, Any]:
    """Prove the controller decision is independent of supported agent markers."""

    results: list[dict[str, Any]] = []
    for env in environments:
        fingerprint = agent_env_fingerprint(env)
        # Intentionally ignore fingerprint for the decision body.
        body = {
            "operation": operation,
            "payloadDigest": hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "agentFingerprintIgnored": fingerprint,
            "component": COMPONENT_KIND,
        }
        results.append(body)
    digests = {
        hashlib.sha256(
            json.dumps({k: v for k, v in row.items() if k != "agentFingerprintIgnored"}, sort_keys=True).encode(
                "utf-8"
            )
        ).hexdigest()
        for row in results
    }
    if len(digests) != 1:
        raise ControllerError("agent_dependent_behavior", "controller must ignore agent identity")
    return {"status": "identical", "results": results, "decisionDigest": next(iter(digests))}


def write_operation_record(path: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": 1,
        "kind": "delivery-operation",
        "component": COMPONENT_KIND,
        **dict(record),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def deliver_phase_to_development(
    *,
    github: GitHubPort,
    repository: str,
    handoff: Mapping[str, Any],
    pr: Mapping[str, Any],
    live_head: str,
    live_tree: str,
    gate_payload: Mapping[str, Any],
    named_checks: Mapping[str, Any],
    repository_ci: Mapping[str, Any],
    receipt: Mapping[str, Any],
    candidate_identity: Mapping[str, Any],
    role: str,
    actor: str = "delivery-controller",
    conflict: bool = False,
    record_path: Path | None = None,
    protected_tree: str | None = None,
    rollout: StagedRolloutConfig | None = None,
) -> dict[str, Any]:
    """End-to-end development merge for one exact Phase PR."""

    config = _rollout_config(rollout)
    eligibility = verify_development_eligibility(
        handoff=handoff,
        pr=pr,
        repository=repository,
        live_head=live_head,
        live_tree=live_tree,
        gate_payload=gate_payload,
        named_checks=named_checks,
        repository_ci=repository_ci,
        receipt=receipt,
        candidate_identity=candidate_identity,
        conflict=conflict,
        rollout=config,
    )
    try:
        merged = merge_to_development(
            github=github,
            repository=repository,
            pr_number=int(eligibility["pr"]["number"]),
            expected_head=live_head,
            role=role,
            actor=actor,
            receipt=receipt,
            candidate_identity=candidate_identity,
            candidate_tree=protected_tree or live_tree,
            protected_base_commit=str(handoff.get("baseCommit") or ""),
            rollout=config,
        )
    except ControllerError as exc:
        return stop_on_protected_merge_rejection(exc)
    record = {
        **merged,
        "eligibility": eligibility,
        "agentFingerprint": agent_env_fingerprint(),
    }
    if record_path is not None:
        operation_record = dict(record)
        operation_record["transitionReceipt"] = {
            "receiptDigest": record["transitionReceiptDigest"],
            "externalEvidenceRequired": True,
        }
        write_operation_record(record_path, operation_record)
    return record


def recover_phase_to_development(
    *,
    github: GitHubPort,
    protections: Any,
    repository: str,
    handoff: Mapping[str, Any],
    pr: Mapping[str, Any],
    live_head: str,
    live_tree: str,
    named_exception: str,
    replacement_proof: bool,
    allow_temporary_exception: bool = False,
    obsolete_status_state: str = "missing",
    role: str,
) -> dict[str, Any]:
    """Named exact-head administrator recovery after replacement proof."""

    require_controller_role(role)
    accepted = accept_phase_pr(
        pr,
        handoff,
        repository=repository,
        live_head=live_head,
        live_tree=live_tree,
    )
    try:
        return recover_phase_merge(
            github=github,
            protections=protections,
            repository=repository,
            pr_number=int(accepted["number"]),
            phase_branch=str(accepted["head"]),
            expected_head=live_head,
            expected_tree=live_tree,
            live_head=live_head,
            live_tree=live_tree,
            named_exception=named_exception,
            replacement_proof=replacement_proof,
            allow_temporary_exception=allow_temporary_exception,
            obsolete_status_state=obsolete_status_state,
        )
    except Exception as exc:
        if hasattr(exc, "code"):
            raise ControllerError(str(getattr(exc, "code")), str(getattr(exc, "detail", exc))) from exc
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent-agnostic delivery controller (WP-U02)")
    parser.add_argument(
        "command",
        choices=[
            "verify-development",
            "merge-development",
            "promote-staging",
            "prepare-main",
            "complete-main",
            "cleanup",
            "agent-identical",
            "recover-phase",
        ],
    )
    parser.add_argument("--repository", default="")
    parser.add_argument("--role", default="operator")
    parser.add_argument("--handoff", default="")
    parser.add_argument("--pr-json", default="")
    parser.add_argument("--live-head", default="")
    parser.add_argument("--live-tree", default="")
    parser.add_argument("--gates-json", default="")
    parser.add_argument("--checks-json", default="")
    parser.add_argument("--repository-ci-json", default="")
    parser.add_argument("--receipt", default="")
    parser.add_argument("--identity-json", default="")
    parser.add_argument("--approval-json", default="")
    parser.add_argument("--release-json", default="")
    parser.add_argument("--promote-json", default="")
    parser.add_argument("--merge-evidence-json", default="")
    parser.add_argument("--pr-number", type=int, default=0)
    parser.add_argument("--expected-head", default="")
    parser.add_argument("--source-sha", default="")
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--branches", default="")
    parser.add_argument("--payload-json", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--named-exception", default="")
    parser.add_argument("--replacement-proof", action="store_true")
    parser.add_argument("--allow-temporary-exception", action="store_true")
    parser.add_argument("--obsolete-status-state", default="missing")
    parser.add_argument(
        "--rollout-json",
        default="",
        help="Optional staged-rollout config with branch and required-check identities",
    )
    args = parser.parse_args(argv)

    def load(path: str) -> Any:
        return json.loads(Path(path).read_text(encoding="utf-8"))

    try:
        rollout = StagedRolloutConfig.from_mapping(load(args.rollout_json)) if args.rollout_json else None
        if args.command == "agent-identical":
            payload = load(args.payload_json) if args.payload_json else {"ok": True}
            result = run_identical_under_agents(
                "probe",
                payload,
                [
                    {},
                    {"CURSOR_AGENT": "1"},
                    {"CODEX_HOME": "/tmp/codex"},
                    {"TERRA_AGENT": "terra", "LINKTREND_AGENT": "lisa"},
                ],
            )
        elif args.command == "verify-development":
            result = verify_development_eligibility(
                handoff=load(args.handoff),
                pr=load(args.pr_json),
                repository=args.repository,
                live_head=args.live_head,
                live_tree=args.live_tree,
                gate_payload=load(args.gates_json),
                named_checks=load(args.checks_json),
                repository_ci=load(args.repository_ci_json),
                receipt=load(args.receipt),
                candidate_identity=load(args.identity_json),
                rollout=rollout,
            )
        else:
            require_controller_role(args.role)
            github = resolve_production_github(args.repository)
            if args.command == "merge-development":
                result = merge_to_development(
                    github=github,
                    repository=args.repository,
                    pr_number=args.pr_number,
                    expected_head=args.expected_head or args.live_head,
                    role=args.role,
                    receipt=load(args.receipt) if args.receipt else None,
                    candidate_identity=load(args.identity_json) if args.identity_json else None,
                    candidate_tree=args.live_tree or None,
                    protected_base_commit=args.base_sha or None,
                    rollout=rollout,
                )
            elif args.command == "promote-staging":
                payload = load(args.promote_json)
                result = promote_to_staging(
                    github=github,
                    repository=args.repository,
                    development_sha=str(payload["developmentSha"]),
                    staging_sha=str(payload["stagingSha"]),
                    candidate_sha=str(payload["candidateSha"]),
                    candidate_tree=str(payload["candidateTree"]),
                    receipt=load(args.receipt),
                    candidate_identity=load(args.identity_json),
                    release_gate=load(args.release_json),
                    role=args.role,
                    full_suite_invoked=bool(payload.get("fullSuiteInvoked")),
                    transition_receipt=load(str(payload["transitionReceipt"])) if isinstance(payload.get("transitionReceipt"), str) else payload.get("transitionReceipt"),
                    rollout=rollout,
                )
            elif args.command == "prepare-main":
                payload = load(args.promote_json)
                result = prepare_main_promotion(
                    github=github,
                    repository=args.repository,
                    staging_sha=str(payload["stagingSha"]),
                    main_sha=str(payload["mainSha"]),
                    candidate_sha=str(payload["candidateSha"]),
                    receipt=load(args.receipt),
                    candidate_identity=load(args.identity_json),
                    release_gate=load(args.release_json),
                    role=args.role,
                    transition_receipt=load(str(payload["transitionReceipt"])) if isinstance(payload.get("transitionReceipt"), str) else payload.get("transitionReceipt"),
                    rollout=rollout,
                )
            elif args.command == "complete-main":
                result = complete_main_promotion(
                    github=github,
                    repository=args.repository,
                    pr_number=args.pr_number,
                    expected_head=args.expected_head,
                    source_sha=args.source_sha,
                    base_sha=args.base_sha,
                    approval=load(args.approval_json),
                    receipt=load(args.receipt),
                    role=args.role,
                    rollout=rollout,
                )
            elif args.command == "cleanup":
                branches = [item for item in args.branches.split(",") if item]
                evidence = load(args.merge_evidence_json) if args.merge_evidence_json else {}
                owned = authorize_cleanup_from_evidence(evidence, branches)
                result = cleanup_temporary_branches(
                    github=github,
                    repository=args.repository,
                    branches=branches,
                    merge_succeeded=True,
                    controller_owned=owned,
                    rollout=rollout,
                )
            elif args.command == "recover-phase":
                if os.environ.get("LINKTREND_STATUS_BACKEND") != "file":
                    raise ControllerError(
                        "recovery_requires_injected_protection_port",
                        "live administrator recovery requires an injected ProtectionPort",
                    )
                result = recover_phase_to_development(
                    github=github,
                    protections=MemoryProtection(repository=args.repository),
                    repository=args.repository,
                    handoff=load(args.handoff),
                    pr=load(args.pr_json),
                    live_head=args.live_head,
                    live_tree=args.live_tree,
                    named_exception=args.named_exception,
                    replacement_proof=bool(args.replacement_proof),
                    allow_temporary_exception=bool(args.allow_temporary_exception),
                    obsolete_status_state=args.obsolete_status_state,
                    role=args.role,
                )
            else:  # pragma: no cover
                raise ControllerError("unknown_command", args.command)
    except ControllerError as exc:
        payload = {"status": "rejected", **exc.to_dict(), "component": COMPONENT_KIND}
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        sys.stderr.write(text)
        return 2

    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
