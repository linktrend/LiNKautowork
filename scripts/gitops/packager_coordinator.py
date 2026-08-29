#!/usr/bin/env python3
"""Agent-agnostic Phase Packager/Coordinator (Update 3 / WP-U03).

Assembles one or more accepted remote issue commits into exactly one ordered
``phase/*`` branch and one draft Phase PR. Retained ``packager_discover.py`` is
not this component: it still discovers Review-Ready tips into ordinary draft
PRs and must not be treated as the Phase Packager.

Production ``assemble`` uses a bounded live GitHub adapter and a bounded push
adapter, or refuses without credentials and configuration. Success requires a
verified remote ``phase/*`` ref at the exact assembled head plus one real draft
Phase PR identity. Tests inject ``MemoryGitHub``; the production CLI never
does. Existing Phase state is preserved: unique or drifted Phase work is
rejected instead of reset. Assembly runs in an isolated worktree and writes
coordinator state under the git common directory, outside the caller
checkout. This module never pushes
``development``/``staging``/``main``, never seals a candidate, and never
starts Full.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

try:
    from scripts.gitops.delivery_modes import (
        DEFAULT_PHASE_PREFIX,
        MODE_PHASE_INTEGRATION,
        is_issue_branch,
        is_phase_branch,
        is_valid_sha,
        normalize_sha,
    )
    from scripts.gitops.phase_integrator import (
        PHASE_RECORD_REL,
        IssueTip,
        PhaseLifecycleError,
        invalidate_candidate_gates,
        phase_full_suite_dispatch_allowed,
    )
except ModuleNotFoundError:  # pragma: no cover - script-style execution
    from delivery_modes import (  # type: ignore
        DEFAULT_PHASE_PREFIX,
        MODE_PHASE_INTEGRATION,
        is_issue_branch,
        is_phase_branch,
        is_valid_sha,
        normalize_sha,
    )
    from phase_integrator import (  # type: ignore
        PHASE_RECORD_REL,
        IssueTip,
        PhaseLifecycleError,
        invalidate_candidate_gates,
        phase_full_suite_dispatch_allowed,
    )

try:
    from scripts.gitops.github_auth import GitHubAuthError, resolve_phase_api_token
    from scripts.gitops.issue_checkpoint import bind_issue_completion, parse_immutable_evidence_payload
    from core.execution.rollout import (
        build_provider_consumer_handoff,
        consume_provider_consumer_handoff,
        evaluate_provider_consumer_handoff,
    )
except ModuleNotFoundError:  # pragma: no cover - script-style execution
    from github_auth import GitHubAuthError, resolve_phase_api_token  # type: ignore
    from issue_checkpoint import bind_issue_completion, parse_immutable_evidence_payload  # type: ignore
    from core.execution.rollout import (  # type: ignore
        build_provider_consumer_handoff,
        consume_provider_consumer_handoff,
        evaluate_provider_consumer_handoff,
    )

COMPONENT_KIND = "phase_packager_coordinator"
IS_PHASE_PACKAGER = True
HANDOFF_REL = Path(".linktrend/phase-handoff.json")
COORDINATOR_STATE_REL = Path("ide-development/phase-packager")
PROTECTED_BRANCHES = frozenset({"development", "staging", "main"})
ISSUE_BRANCH_RE = re.compile(r"^issue/([1-9][0-9]{0,8})-[a-z0-9]+(?:-[a-z0-9]+)*$")
ACCEPT_RE = re.compile(r"^([^@=]+)[@=]([0-9a-fA-F]{40})$")
LIVE_PR_URL_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+/pull/[1-9][0-9]*$")
AGENT_ENV_KEYS = (
    "CURSOR_AGENT",
    "CODEX_HOME",
    "TERRA_AGENT",
    "LINKTREND_AGENT",
    "AIDER_MODEL",
    "ANTHROPIC_MODEL",
)
FAST_WORKFLOW_REL = Path("core/github/managed-workflows/linktrend-review-packager.yml")
FULL_WORKFLOW_REL = Path("core/github/managed-workflows/linktrend-integrator-merge.yml")


class CoordinatorError(ValueError):
    """Fail-closed Phase Packager/Coordinator rejection."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


class GitHubPort(Protocol):
    """PR and evidence adapter. Tests inject ``MemoryGitHub``."""

    def ensure_draft_phase_pr(
        self,
        *,
        repository: str,
        head: str,
        base: str,
        head_sha: str,
        title: str,
        body: str,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        ...

    def list_open_phase_prs(self, *, repository: str, head: str, base: str) -> list[dict[str, Any]]:
        ...

    def completion_bound(
        self,
        sha: str,
        evidence_payload: Mapping[str, Any] | None = None,
    ) -> tuple[bool, str]:
        ...

    def add_label(self, pr_number: int, label: str) -> None:
        ...

    def dispatch_workflow(self, name: str, inputs: Mapping[str, Any]) -> None:
        ...


class PushPort(Protocol):
    """Bounded phase-ref push. Production uses ``GitPushAdapter``."""

    def push_phase_ref(self, repo: Path, remote: str, branch: str, sha: str) -> str:
        ...


@dataclass
class MemoryGitHub:
    """In-memory GitHub adapter for disposable-repo tests. Never talks to GitHub."""

    repository: str
    prs: dict[str, dict[str, Any]] = field(default_factory=dict)
    ready_shas: set[str] = field(default_factory=set)
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    labels: list[tuple[int, str]] = field(default_factory=list)
    workflow_dispatches: list[dict[str, Any]] = field(default_factory=list)
    ensure_calls: int = 0
    next_number: int = 1

    def _key(self, repository: str, head: str, base: str) -> str:
        return f"{repository}|{head}|{base}"

    def ensure_draft_phase_pr(
        self,
        *,
        repository: str,
        head: str,
        base: str,
        head_sha: str,
        title: str,
        body: str,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        if repository != self.repository:
            raise CoordinatorError("wrong_repository", repository)
        self.ensure_calls += 1
        key = self._key(repository, head, base)
        existing = self.prs.get(key)
        if existing:
            existing["headSha"] = normalize_sha(head_sha)
            existing["body"] = body
            existing["record"] = dict(record)
            existing["created"] = False
            return dict(existing)
        pr = {
            "number": self.next_number,
            "url": f"https://example.invalid/{repository}/pull/{self.next_number}",
            "isDraft": True,
            "head": head,
            "base": base,
            "headSha": normalize_sha(head_sha),
            "title": title,
            "body": body,
            "record": dict(record),
            "created": True,
        }
        self.next_number += 1
        self.prs[key] = pr
        return dict(pr)

    def list_open_phase_prs(self, *, repository: str, head: str, base: str) -> list[dict[str, Any]]:
        key = self._key(repository, head, base)
        found = self.prs.get(key)
        return [dict(found)] if found else []

    def completion_bound(
        self,
        sha: str,
        evidence_payload: Mapping[str, Any] | None = None,
    ) -> tuple[bool, str]:
        subject = normalize_sha(sha)
        payload = evidence_payload if isinstance(evidence_payload, Mapping) else self.evidence.get(subject)
        review_state = (
            "success"
            if subject in {normalize_sha(item) for item in self.ready_shas}
            else "missing"
        )
        ok, detail, _meta = bind_issue_completion(
            sha=subject,
            evidence=dict(payload) if isinstance(payload, Mapping) else None,
            review_ready_state=review_state,
        )
        return ok, detail

    def add_label(self, pr_number: int, label: str) -> None:
        self.labels.append((pr_number, label))

    def dispatch_workflow(self, name: str, inputs: Mapping[str, Any]) -> None:
        self.workflow_dispatches.append({"name": name, "inputs": dict(inputs)})


class GitPushAdapter:
    """Push exactly one ``phase/*`` ref and verify the remote SHA. Never force."""

    def push_phase_ref(self, repo: Path, remote: str, branch: str, sha: str) -> str:
        if branch in PROTECTED_BRANCHES or not is_phase_branch(branch, DEFAULT_PHASE_PREFIX):
            raise CoordinatorError("protected_push", branch)
        subject = normalize_sha(sha)
        if not is_valid_sha(subject):
            raise CoordinatorError("invalid_sha", sha)
        _git(repo, "push", "--", remote, f"{subject}:refs/heads/{branch}")
        verified = _remote_sha(repo, remote, branch)
        if verified != subject:
            raise CoordinatorError("unverified_phase_ref", f"{branch}:remote={verified}:expected={subject}")
        _git(repo, "update-ref", f"refs/remotes/{remote}/{branch}", verified, check=False)
        return verified


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
            "User-Agent": "linktrend-phase-packager-coordinator",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise CoordinatorError("github_api_failed", f"{method} {url} -> {exc.code}: {detail[:300]}") from exc


@dataclass
class LiveGitHub:
    """Bounded live GitHub adapter. Opens or updates one draft Phase PR only."""

    repository: str
    automation_token: str
    user_token: str
    transport: Callable[[str, str, str, Mapping[str, Any] | None], Any] | None = None
    ensure_calls: int = 0
    labels: list[tuple[int, str]] = field(default_factory=list)
    workflow_dispatches: list[dict[str, Any]] = field(default_factory=list)

    def _request(self, method: str, url: str, token: str, body: Mapping[str, Any] | None = None) -> Any:
        if self.transport is not None:
            return self.transport(method, url, token, body)
        return _github_api(method, url, token, body)

    def _pr_identity(self, payload: Mapping[str, Any], *, created: bool) -> dict[str, Any]:
        html_url = str(payload.get("html_url") or payload.get("url") or "")
        number = payload.get("number")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise CoordinatorError("invalid_phase_pr", "missing live pull number")
        draft = payload.get("draft", payload.get("isDraft"))
        return {
            "number": number,
            "url": html_url,
            "isDraft": bool(draft),
            "head": (payload.get("head") or {}).get("ref") if isinstance(payload.get("head"), Mapping) else payload.get("head"),
            "base": (payload.get("base") or {}).get("ref") if isinstance(payload.get("base"), Mapping) else payload.get("base"),
            "headSha": normalize_sha(str((payload.get("head") or {}).get("sha") or payload.get("headSha") or "")),
            "created": created,
        }

    def ensure_draft_phase_pr(
        self,
        *,
        repository: str,
        head: str,
        base: str,
        head_sha: str,
        title: str,
        body: str,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        if repository != self.repository:
            raise CoordinatorError("wrong_repository", repository)
        if not self.automation_token or not self.user_token:
            raise CoordinatorError("missing_github_credentials", "live GitHub adapter requires automation and PR-create tokens")
        self.ensure_calls += 1
        owner = repository.split("/", 1)[0]
        listed = self._request(
            "GET",
            (
                f"https://api.github.com/repos/{repository}/pulls?"
                + urllib.parse.urlencode({"head": f"{owner}:{head}", "base": base, "state": "open"})
            ),
            self.automation_token,
        )
        if not isinstance(listed, list):
            raise CoordinatorError("github_api_failed", "pull list was not an array")
        if len(listed) > 1:
            raise CoordinatorError("duplicate_phase_pr", json.dumps([row.get("number") for row in listed]))
        if listed:
            existing = listed[0]
            if not isinstance(existing, Mapping):
                raise CoordinatorError("invalid_phase_pr", "existing pull was not an object")
            number = existing.get("number")
            if not existing.get("draft", existing.get("isDraft")):
                raise CoordinatorError("phase_pr_not_draft", str(number))
            updated = self._request(
                "PATCH",
                f"https://api.github.com/repos/{repository}/pulls/{number}",
                self.automation_token,
                {"title": title, "body": body},
            )
            if not isinstance(updated, Mapping):
                updated = existing
            identity = self._pr_identity(updated if isinstance(updated, Mapping) else existing, created=False)
            return self._bound_live_pr(identity, head_sha)
        created = self._request(
            "POST",
            f"https://api.github.com/repos/{repository}/pulls",
            self.user_token,
            {
                "title": title,
                "body": body,
                "head": head,
                "base": base,
                "draft": True,
            },
        )
        if not isinstance(created, Mapping):
            raise CoordinatorError("invalid_phase_pr", "create response was not an object")
        identity = self._pr_identity(created, created=True)
        return self._bound_live_pr(identity, head_sha)

    def _bound_live_pr(self, identity: dict[str, Any], head_sha: str) -> dict[str, Any]:
        """Keep GitHub's draft/URL identity; never forge a successful draft PR."""

        expected = normalize_sha(head_sha)
        reported = normalize_sha(str(identity.get("headSha") or ""))
        if is_valid_sha(reported) and reported != expected:
            raise CoordinatorError("unverified_phase_ref", f"pr_head={reported}:expected={expected}")
        if not identity.get("isDraft"):
            raise CoordinatorError("phase_pr_not_draft", str(identity.get("number")))
        identity["headSha"] = expected
        assert_live_phase_pr(identity)
        return identity

    def list_open_phase_prs(self, *, repository: str, head: str, base: str) -> list[dict[str, Any]]:
        if repository != self.repository:
            raise CoordinatorError("wrong_repository", repository)
        owner = repository.split("/", 1)[0]
        listed = self._request(
            "GET",
            (
                f"https://api.github.com/repos/{repository}/pulls?"
                + urllib.parse.urlencode({"head": f"{owner}:{head}", "base": base, "state": "open"})
            ),
            self.automation_token,
        )
        if not isinstance(listed, list):
            raise CoordinatorError("github_api_failed", "pull list was not an array")
        return [self._pr_identity(row, created=False) for row in listed if isinstance(row, Mapping)]

    def completion_bound(
        self,
        sha: str,
        evidence_payload: Mapping[str, Any] | None = None,
    ) -> tuple[bool, str]:
        subject = normalize_sha(sha)
        ok, detail, _meta = bind_issue_completion(
            sha=subject,
            evidence=dict(evidence_payload) if isinstance(evidence_payload, Mapping) else None,
            review_ready_state="missing",
        )
        return ok, detail

    def add_label(self, pr_number: int, label: str) -> None:
        raise CoordinatorError("label_not_permitted", f"{pr_number}:{label}")

    def dispatch_workflow(self, name: str, inputs: Mapping[str, Any]) -> None:
        raise CoordinatorError("workflow_dispatch_not_permitted", name)


def resolve_production_adapters(repository: str) -> tuple[LiveGitHub, GitPushAdapter]:
    """Fail closed unless live GitHub and push configuration are present.

    Phase API credentials are GH_TOKEN/GITHUB_TOKEN. AUTOMATION_TOKEN is a
    waived legacy publisher token and is not canonical for v2.5.
    """

    if not repository or "/" not in repository or repository.count("/") != 1:
        raise CoordinatorError("missing_repository", "assemble requires --repository owner/name")
    try:
        token, _source = resolve_phase_api_token()
    except GitHubAuthError as exc:
        raise CoordinatorError(exc.code, exc.detail) from exc
    return (
        LiveGitHub(repository=repository, automation_token=token, user_token=token),
        GitPushAdapter(),
    )


def assert_live_phase_pr(pr: Mapping[str, Any]) -> None:
    url = str(pr.get("url") or "")
    number = pr.get("number")
    if "example.invalid" in url or not LIVE_PR_URL_RE.fullmatch(url):
        raise CoordinatorError("invalid_phase_pr", url or "missing live pull URL")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise CoordinatorError("invalid_phase_pr", "live pull number is required")
    if not bool(pr.get("isDraft", False)):
        raise CoordinatorError("phase_pr_not_draft", str(number))


@dataclass(frozen=True)
class AcceptedSource:
    branch: str
    sha: str
    order: int

    def to_dict(self) -> dict[str, Any]:
        return {"branch": self.branch, "sha": normalize_sha(self.sha), "order": self.order}


def _git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        detail = (result.stderr or result.stdout or "git command failed").strip()
        raise CoordinatorError("git_failed", detail[:400])
    return (result.stdout or "").strip()


def parse_accept(raw: str, order: int) -> AcceptedSource:
    match = ACCEPT_RE.fullmatch((raw or "").strip())
    if not match:
        raise CoordinatorError("invalid_accept", raw)
    branch, sha = match.group(1), normalize_sha(match.group(2))
    if not ISSUE_BRANCH_RE.fullmatch(branch) and not is_issue_branch(branch):
        raise CoordinatorError("invalid_issue_branch", branch)
    if not ISSUE_BRANCH_RE.fullmatch(branch):
        raise CoordinatorError("invalid_issue_branch", branch)
    if not is_valid_sha(sha):
        raise CoordinatorError("invalid_sha", sha)
    return AcceptedSource(branch=branch, sha=sha, order=order)


def parse_fast_trigger_contract(text: str) -> dict[str, Any]:
    """Structural Fast-trigger contract used by tests (no live workflow runs)."""

    push = bool(re.search(r"(?m)^\s+push:", text))
    pull = bool(re.search(r"(?m)^\s+pull_request:", text))
    named = "name: Linktrend Fast Checks" in text
    phase_only = "startsWith(github.event.pull_request.head.ref, 'phase/')" in text
    full_profile = "run_delivery_profile.py full" in text
    full_label = "linktrend-full-suite" in text
    result = {
        "namedFast": named,
        "checkpointPush": push,
        "phasePullRequest": pull,
        "phaseHeadOnly": phase_only,
        "startsFull": full_profile or full_label,
        "cancelObsolete": "cancel-in-progress: true" in text,
        "checksExactHead": "github.event.pull_request.head.sha" in text,
    }
    return result


def full_may_start(
    *,
    sealed: bool,
    fast_status: str,
    required_ci: Mapping[str, str],
    live_head_sha: str,
    record: Mapping[str, Any] | None = None,
    pr_number: int | None = None,
) -> tuple[bool, str]:
    """Full cannot start before Fast and required repository CI pass on this head."""

    if not sealed:
        return False, "unsealed"
    if fast_status not in {"passed", "success"}:
        return False, f"fast_not_passed:{fast_status or 'missing'}"
    if not required_ci:
        return False, "required_ci_missing"
    for name, status in required_ci.items():
        if status not in {"passed", "success"}:
            return False, f"required_ci_not_passed:{name}={status or 'missing'}"
    if record is not None and pr_number is not None:
        allowed, detail, _payload = phase_full_suite_dispatch_allowed(
            record, live_head_sha=live_head_sha, pr_number=pr_number
        )
        if not allowed:
            return False, detail
    return True, "eligible"


def consume_handoff(
    handoff: Mapping[str, Any],
    *,
    live_head: str,
    live_tree: str | None = None,
    repository: str | None = None,
    protected_provider_identity: Mapping[str, Any] | None = None,
    accepted_receipt: Mapping[str, Any] | None = None,
    consumer_identity: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    """Update 2 consumes this exact identity; a later head invalidates it."""

    if not isinstance(handoff, Mapping):
        return False, "handoff_missing"
    if handoff.get("kind") == "provider-consumer-handoff":
        return consume_provider_consumer_handoff(
            handoff,
            protected_provider_identity=protected_provider_identity,
            accepted_receipt=accepted_receipt,
            consumer_identity=consumer_identity,
        )
    if handoff.get("schemaVersion") != 1 or handoff.get("kind") != "phase-handoff":
        return False, "handoff_schema_invalid"
    if repository and str(handoff.get("repository") or "") != repository:
        return False, "handoff_repository_mismatch"
    if not bool(handoff.get("valid")):
        return False, "handoff_invalid"
    head = normalize_sha(str(handoff.get("headCommit") or ""))
    if not is_valid_sha(head) or head != normalize_sha(live_head):
        return False, "handoff_stale_head"
    tree = normalize_sha(str(handoff.get("gitTree") or ""))
    if live_tree is not None and tree != normalize_sha(live_tree):
        return False, "handoff_stale_tree"
    return True, "ok"


def _remote_sha(repo: Path, remote: str, branch: str) -> str:
    output = _git(repo, "ls-remote", "--heads", remote, f"refs/heads/{branch}", check=False)
    if not output:
        return ""
    return normalize_sha(output.split()[0])


def _object_exists(repo: Path, sha: str) -> bool:
    result = _git(repo, "cat-file", "-t", sha, check=False)
    return result == "commit"


def _changed_paths(repo: Path, base: str, sha: str) -> set[str]:
    output = _git(repo, "diff-tree", "--no-commit-id", "-r", "--name-only", f"{base}..{sha}")
    return {line.strip() for line in output.splitlines() if line.strip()}


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _probe_conflicts(repo: Path, development: str, sources: list[AcceptedSource]) -> None:
    overlapping: list[dict[str, Any]] = []
    for left, right in (
        (sources[i], sources[j]) for i in range(len(sources)) for j in range(i + 1, len(sources))
    ):
        related = _is_ancestor(repo, left.sha, right.sha) or _is_ancestor(repo, right.sha, left.sha)
        if related:
            continue
        shared = sorted(_changed_paths(repo, development, left.sha) & _changed_paths(repo, development, right.sha))
        if shared:
            overlapping.append(
                {
                    "left": left.to_dict(),
                    "right": right.to_dict(),
                    "paths": shared,
                }
            )
    if overlapping:
        raise CoordinatorError("overlapping_commits", json.dumps(overlapping, sort_keys=True))

    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / "probe"
        _git(repo, "worktree", "add", "--detach", str(probe), development)
        try:
            _git(probe, "checkout", "-B", "phase-probe", development)
            for source in sources:
                merge = subprocess.run(
                    ["git", "merge", "--no-ff", "--no-edit", source.sha],
                    cwd=probe,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if merge.returncode:
                    subprocess.run(
                        ["git", "merge", "--abort"],
                        cwd=probe,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    raise CoordinatorError(
                        "conflicting_commits",
                        f"{source.branch}@{source.sha}:{(merge.stderr or merge.stdout or 'merge conflict').strip()[:240]}",
                    )
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(probe)],
                cwd=repo,
                text=True,
                capture_output=True,
                check=False,
            )


def _validate_source(
    repo: Path,
    source: AcceptedSource,
    *,
    github: GitHubPort,
    remote: str,
    require_evidence: bool,
    evidence_payloads: Mapping[str, Any] | None = None,
) -> None:
    if not _object_exists(repo, source.sha):
        raise CoordinatorError("missing_commit", source.sha)
    local = _git(repo, "rev-parse", f"refs/heads/{source.branch}", check=False)
    current = _git(repo, "rev-parse", "--abbrev-ref", "HEAD", check=False)
    porcelain = _git(repo, "status", "--porcelain", "--untracked-files=all", check=False)
    if current == source.branch and porcelain:
        raise CoordinatorError("uncommitted", source.branch)
    if local and normalize_sha(local) != source.sha:
        raise CoordinatorError("stale_commit", f"{source.branch}:local={local}:accepted={source.sha}")
    remote_sha = _remote_sha(repo, remote, source.branch)
    if not remote_sha:
        raise CoordinatorError("unpushed", source.branch)
    if remote_sha != source.sha:
        if local and normalize_sha(local) == source.sha:
            raise CoordinatorError("unpushed", f"{source.branch}:local={source.sha}:remote={remote_sha}")
        raise CoordinatorError("stale_commit", f"{source.branch}:remote={remote_sha}:accepted={source.sha}")
    if not _is_ancestor(repo, source.sha, remote_sha) and remote_sha != source.sha:
        raise CoordinatorError("stale_commit", source.branch)
    if require_evidence:
        payload = None
        if evidence_payloads:
            payload = (
                evidence_payloads.get(source.sha)
                or evidence_payloads.get(normalize_sha(source.sha))
                or evidence_payloads.get("*")
            )
        ok, detail = github.completion_bound(source.sha, evidence_payload=payload)
        if not ok:
            raise CoordinatorError("evidence_missing", f"{source.branch}:{detail}")


def _git_common_dir(repo: Path) -> Path:
    value = _git(repo, "rev-parse", "--git-common-dir")
    path = Path(value)
    if not path.is_absolute():
        path = (repo / path).resolve()
    return path


def _coordinator_state_dir(repo: Path, phase_branch: str) -> Path:
    phase_id = phase_branch.split("/", 1)[-1]
    return _git_common_dir(repo) / COORDINATOR_STATE_REL / phase_id


def _local_sha(repo: Path, branch: str) -> str:
    value = _git(repo, "rev-parse", "--verify", f"refs/heads/{branch}", check=False)
    return normalize_sha(value) if is_valid_sha(value) else ""


def _assert_live_phase_pr_optional(pr: Mapping[str, Any], *, require_live_pr: bool) -> None:
    if require_live_pr:
        assert_live_phase_pr(pr)


def _unique_phase_commits(
    repo: Path,
    *,
    development_sha: str,
    phase_sha: str,
    accepted_shas: set[str],
) -> list[str]:
    output = _git(repo, "rev-list", "--parents", f"{development_sha}..{phase_sha}", check=False)
    unique: list[str] = []
    for line in output.splitlines():
        parts = line.split()
        if not parts:
            continue
        commit = normalize_sha(parts[0])
        parents = [normalize_sha(item) for item in parts[1:]]
        if commit in accepted_shas:
            continue
        if len(parents) == 2 and parents[1] in accepted_shas:
            continue
        unique.append(commit)
    return unique


def _existing_phase_shas(repo: Path, remote: str, phase_branch: str) -> tuple[str, str]:
    local = _local_sha(repo, phase_branch)
    remote_sha = _remote_sha(repo, remote, phase_branch)
    if local and remote_sha and local != remote_sha:
        raise CoordinatorError("phase_ref_drift", f"{phase_branch}:local={local}:remote={remote_sha}")
    return local, remote_sha


def _remaining_sources(repo: Path, start_sha: str, sources: list[AcceptedSource]) -> list[AcceptedSource]:
    remaining: list[AcceptedSource] = []
    for source in sources:
        if _is_ancestor(repo, source.sha, start_sha):
            continue
        remaining.append(source)
    return remaining


def _assemble_in_worktree(
    repo: Path,
    *,
    start_sha: str,
    sources: list[AcceptedSource],
) -> str:
    remaining = _remaining_sources(repo, start_sha, sources)
    if not remaining:
        return normalize_sha(start_sha)
    with tempfile.TemporaryDirectory(prefix="phase-assemble-") as tmp:
        probe = Path(tmp) / "work"
        _git(repo, "worktree", "add", "--detach", str(probe), start_sha)
        try:
            for source in remaining:
                merge = subprocess.run(
                    [
                        "git",
                        "merge",
                        "--no-ff",
                        "--no-edit",
                        "-m",
                        f"phase: include {source.branch}",
                        source.sha,
                    ],
                    cwd=probe,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if merge.returncode:
                    subprocess.run(
                        ["git", "merge", "--abort"],
                        cwd=probe,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    raise CoordinatorError("conflicting_commits", source.branch)
            head = normalize_sha(_git(probe, "rev-parse", "HEAD"))
            _git(repo, "update-ref", "refs/phase-packager/assemble", head)
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(probe)],
                cwd=repo,
                text=True,
                capture_output=True,
                check=False,
            )
    return head


def _write_isolated_state(
    repo: Path,
    phase_branch: str,
    record: Mapping[str, Any],
    handoff: Mapping[str, Any],
    provider_consumer_handoff: Mapping[str, Any] | None = None,
) -> Path:
    state_dir = _coordinator_state_dir(repo, phase_branch)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "phase-delivery-record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (state_dir / "phase-handoff.json").write_text(
        json.dumps(handoff, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if provider_consumer_handoff is not None:
        (state_dir / "provider-consumer-handoff.json").write_text(
            json.dumps(provider_consumer_handoff, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return state_dir


def _stable_title(phase_branch: str) -> str:
    return f"Phase: {phase_branch}"


def _candidate_revision(repository: str, phase_branch: str, base: str, sources: list[AcceptedSource]) -> str:
    payload = json.dumps(
        {
            "repository": repository,
            "phaseBranch": phase_branch,
            "base": normalize_sha(base),
            "accepted": [source.to_dict() for source in sources],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _phase_record(
    *,
    repository: str,
    phase_branch: str,
    base: str,
    head: str,
    tree: str,
    sources: list[AcceptedSource],
    pr: Mapping[str, Any] | None,
    revision: str,
    previous: Mapping[str, Any] | None,
) -> dict[str, Any]:
    accepted = [
        {
            "branch": source.branch,
            "sha": source.sha,
            "order": source.order,
            "accepted": True,
            "included": True,
            "acceptanceSha": source.sha,
        }
        for source in sources
    ]
    record: dict[str, Any] = {
        "schemaVersion": 1,
        "kind": "phase-record",
        "deliveryMode": MODE_PHASE_INTEGRATION,
        "repository": repository,
        "phaseId": phase_branch.split("/", 1)[-1],
        "phaseBranch": phase_branch,
        "baseSha": normalize_sha(base),
        "immutableBaseSha": normalize_sha(base),
        "headSha": normalize_sha(head),
        "gitTree": normalize_sha(tree),
        "candidateRevision": revision,
        "acceptedIssues": accepted,
        "acceptedCommits": [source.to_dict() for source in sources],
        "dependencyOrder": [source.branch for source in sources],
        "phasePr": dict(pr) if pr else None,
        "sealed": False,
        "sealRevision": 0,
        "fast": {"status": "not-run"},
        "full": {"status": "not-run"},
        "namedGateEvidence": {
            "gate": "fast-gate",
            "sha": normalize_sha(head),
            "status": "missing",
            "detail": "unsealed_phase_pr",
            "checks": [],
        },
        "component": COMPONENT_KIND,
    }
    if previous and normalize_sha(str(previous.get("headSha") or "")) != normalize_sha(head):
        record = invalidate_candidate_gates(record, old_head_sha=str(previous.get("headSha")), new_head_sha=head)
        record["previousCandidateRevision"] = previous.get("candidateRevision")
        record["invalidatedFromSha"] = normalize_sha(str(previous.get("headSha") or ""))
        record["sealed"] = False
        record["fast"] = {"status": "invalidated", "detail": "phase_head_changed"}
        record["full"] = {"status": "invalidated", "detail": "phase_head_changed"}
    return record


def _handoff_from(
    record: Mapping[str, Any],
    *,
    valid: bool = True,
    provider_consumer_handoff: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    pr = record.get("phasePr") if isinstance(record.get("phasePr"), Mapping) else {}
    result = {
        "schemaVersion": 1,
        "kind": "phase-handoff",
        "repository": record.get("repository"),
        "phaseBranch": record.get("phaseBranch"),
        "phasePr": {
            "number": pr.get("number"),
            "url": pr.get("url"),
            "isDraft": pr.get("isDraft", True),
        },
        "headCommit": record.get("headSha"),
        "gitTree": record.get("gitTree"),
        "baseCommit": record.get("baseSha"),
        "candidateRevision": record.get("candidateRevision"),
        "acceptedCommits": list(record.get("acceptedCommits") or []),
        "evidenceLocations": {
            "phaseRecord": PHASE_RECORD_REL.as_posix(),
            "handoff": HANDOFF_REL.as_posix(),
        },
        "valid": bool(valid),
        "component": COMPONENT_KIND,
    }
    if provider_consumer_handoff is not None:
        result["providerConsumerHandoff"] = dict(provider_consumer_handoff)
        result["evidenceLocations"]["providerConsumerHandoff"] = (
            ".linktrend/provider-consumer-handoff.json"
        )
    return result


def assemble_phase(
    *,
    repo: Path,
    repository: str,
    sources: list[AcceptedSource],
    github: GitHubPort,
    phase_branch: str,
    development: str = "development",
    remote: str = "origin",
    require_evidence: bool = True,
    expected_repository: str | None = None,
    pusher: PushPort | None = None,
    require_live_pr: bool = False,
    evidence_payloads: Mapping[str, Any] | None = None,
    provider_consumer_handoff: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create or update exactly one Phase branch and draft PR representation."""

    if expected_repository and expected_repository != repository:
        raise CoordinatorError("wrong_repository", f"expected={expected_repository}:got={repository}")
    if repository != getattr(github, "repository", repository):
        raise CoordinatorError("wrong_repository", repository)
    if pusher is None:
        raise CoordinatorError("missing_push_adapter", "assemble requires a bounded push adapter")
    if require_live_pr and not isinstance(github, LiveGitHub):
        raise CoordinatorError("invalid_phase_pr", "production assemble requires a live GitHub adapter")
    if not sources:
        raise CoordinatorError("no_accepted_issues", "at least one accepted issue commit is required")
    if phase_branch in PROTECTED_BRANCHES or not is_phase_branch(phase_branch, DEFAULT_PHASE_PREFIX):
        raise CoordinatorError("invalid_phase_branch", phase_branch)
    if development in {"staging", "main"}:
        raise CoordinatorError("protected_base", development)

    seen_branches: set[str] = set()
    seen_numbers: set[str] = set()
    seen_shas: set[str] = set()
    ordered: list[AcceptedSource] = []
    for source in sources:
        issue = IssueTip(source.branch, source.sha, acceptance_sha=source.sha, live_sha=source.sha)
        number = issue.issue_number
        if source.branch in seen_branches or number in seen_numbers:
            raise CoordinatorError("duplicate_issue", source.branch)
        if source.sha in seen_shas:
            raise CoordinatorError("duplicate_issue_sha", source.sha)
        seen_branches.add(source.branch)
        seen_numbers.add(number)
        seen_shas.add(source.sha)
        ordered.append(source)
        _validate_source(
            repo,
            source,
            github=github,
            remote=remote,
            require_evidence=require_evidence,
            evidence_payloads=evidence_payloads,
        )

    development_sha = _remote_sha(repo, remote, development) or _git(repo, "rev-parse", development)
    if not is_valid_sha(development_sha):
        raise CoordinatorError("missing_commit", development)
    live_development = _git(repo, "rev-parse", development)
    if normalize_sha(live_development) != normalize_sha(development_sha):
        raise CoordinatorError("stale_commit", f"{development}:local={live_development}:remote={development_sha}")

    _probe_conflicts(repo, development_sha, ordered)

    state_dir = _coordinator_state_dir(repo, phase_branch)
    record_path = state_dir / "phase-delivery-record.json"
    previous = None
    if record_path.is_file():
        previous = json.loads(record_path.read_text(encoding="utf-8"))
        if previous.get("phaseBranch") not in {None, phase_branch} and previous.get("phaseBranch") != phase_branch:
            raise CoordinatorError("duplicate_active_phase", str(previous.get("phaseBranch")))

    local_phase, remote_phase = _existing_phase_shas(repo, remote, phase_branch)
    existing_phase = remote_phase or local_phase
    accepted_shas = {source.sha for source in ordered}
    if existing_phase:
        unique = _unique_phase_commits(
            repo,
            development_sha=development_sha,
            phase_sha=existing_phase,
            accepted_shas=accepted_shas,
        )
        remaining = _remaining_sources(repo, existing_phase, ordered)
        if unique:
            raise CoordinatorError(
                "unique_phase_divergence",
                f"{phase_branch}:{existing_phase}:{','.join(unique)}",
            )
        start_sha = existing_phase
    else:
        remaining = list(ordered)
        start_sha = development_sha

    revision = _candidate_revision(repository, phase_branch, development_sha, ordered)
    identical = not remaining
    if identical:
        head = existing_phase or development_sha
    else:
        head = _assemble_in_worktree(repo, start_sha=start_sha, sources=ordered)
    tree = _git(repo, "rev-parse", f"{head}^{{tree}}")
    for source in ordered:
        if not _is_ancestor(repo, source.sha, head):
            raise CoordinatorError("unrelated_commits", source.branch)

    if remote_phase == head:
        verified = remote_phase
    else:
        verified = pusher.push_phase_ref(repo, remote, phase_branch, head)
    if verified != normalize_sha(head):
        raise CoordinatorError("unverified_phase_ref", f"{phase_branch}:remote={verified}:expected={head}")

    current = _git(repo, "rev-parse", "--abbrev-ref", "HEAD", check=False)
    if current != phase_branch:
        if local_phase:
            _git(repo, "update-ref", f"refs/heads/{phase_branch}", head, local_phase)
        elif not _local_sha(repo, phase_branch):
            _git(repo, "update-ref", f"refs/heads/{phase_branch}", head)

    record = _phase_record(
        repository=repository,
        phase_branch=phase_branch,
        base=development_sha,
        head=head,
        tree=tree,
        sources=ordered,
        pr=None,
        revision=revision,
        previous=None if identical else previous,
    )
    title = _stable_title(phase_branch)
    body = (
        "<!-- linktrend-phase-packager:begin -->\n"
        + json.dumps({"phaseRecord": record, "component": COMPONENT_KIND}, indent=2, sort_keys=True)
        + "\n<!-- linktrend-phase-packager:end -->\n"
    )
    pr = github.ensure_draft_phase_pr(
        repository=repository,
        head=phase_branch,
        base=development,
        head_sha=head,
        title=title,
        body=body,
        record=record,
    )
    _assert_live_phase_pr_optional(pr, require_live_pr=require_live_pr)
    open_prs = github.list_open_phase_prs(repository=repository, head=phase_branch, base=development)
    if len(open_prs) != 1:
        raise CoordinatorError("duplicate_phase_pr", json.dumps([row.get("number") for row in open_prs]))
    if open_prs[0].get("number") != pr.get("number"):
        raise CoordinatorError("duplicate_phase_pr", "stable Phase PR identity drifted")
    record["phasePr"] = {
        "number": pr["number"],
        "url": pr["url"],
        "isDraft": bool(pr.get("isDraft", True)),
        "base": development,
        "head": phase_branch,
    }
    record["status"] = "draft-phase-pr"
    record["fastTrigger"] = "phase_pr"
    record["checkpointCI"] = False
    record["fullDispatchAllowed"] = False
    allowed, detail = full_may_start(
        sealed=False,
        fast_status=str((record.get("fast") or {}).get("status") or ""),
        required_ci={},
        live_head_sha=head,
        record=record,
        pr_number=int(pr["number"]),
    )
    record["fullMayStart"] = {"allowed": allowed, "detail": detail}
    handoff = _handoff_from(
        record,
        valid=True,
        provider_consumer_handoff=provider_consumer_handoff,
    )
    written = _write_isolated_state(
        repo,
        phase_branch,
        record,
        handoff,
        provider_consumer_handoff=provider_consumer_handoff,
    )
    result = {
        "component": COMPONENT_KIND,
        "action": "reused" if identical else ("updated" if existing_phase else "created"),
        "repository": repository,
        "phaseBranch": phase_branch,
        "phasePr": record["phasePr"],
        "headSha": head,
        "gitTree": tree,
        "baseSha": normalize_sha(development_sha),
        "remoteSha": verified,
        "candidateRevision": revision,
        "acceptedCommits": [source.to_dict() for source in ordered],
        "idempotent": identical,
        "githubEnsureCalls": getattr(github, "ensure_calls", 1),
        "labels": list(getattr(github, "labels", [])),
        "workflowDispatches": list(getattr(github, "workflow_dispatches", [])),
        "fastTrigger": "phase_pr",
        "checkpointCI": False,
        "fullDispatchAllowed": False,
        "handoff": handoff,
        "record": record,
        "stateDir": str(written),
        "agentEnvIgnored": [key for key in AGENT_ENV_KEYS if os.environ.get(key)],
    }
    if provider_consumer_handoff is not None:
        result["providerConsumerHandoff"] = dict(provider_consumer_handoff)
    return result


def invalidate_handoff_if_head_changed(handoff: Mapping[str, Any], *, live_head: str) -> dict[str, Any]:
    result = dict(handoff)
    ok, detail = consume_handoff(result, live_head=live_head)
    if not ok:
        result["valid"] = False
        result["invalidReason"] = detail
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["assemble", "consume-handoff", "full-may-start", "fast-contract"])
    parser.add_argument("--repository", default="")
    parser.add_argument("--repo-path", default=".")
    parser.add_argument("--phase-branch", default="phase/next")
    parser.add_argument("--development", default="development")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--accept", action="append", default=[])
    parser.add_argument("--handoff", default="")
    parser.add_argument("--live-head", default="")
    parser.add_argument("--fast-status", default="")
    parser.add_argument("--required-ci", default="{}")
    parser.add_argument("--workflow", default="")
    parser.add_argument("--no-evidence", action="store_true")
    parser.add_argument(
        "--evidence-json",
        default="",
        help="Explicit immutable evidence payload (JSON object or sha->payload map) for out-of-tree hosted validation",
    )
    args = parser.parse_args(argv)

    if args.command == "fast-contract":
        path = Path(args.workflow) if args.workflow else FAST_WORKFLOW_REL
        contract = parse_fast_trigger_contract(path.read_text(encoding="utf-8"))
        json.dump(contract, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0 if contract["namedFast"] and not contract["checkpointPush"] and not contract["startsFull"] else 1

    if args.command == "consume-handoff":
        payload = json.loads(Path(args.handoff).read_text(encoding="utf-8"))
        ok, detail = consume_handoff(payload, live_head=args.live_head, repository=args.repository or None)
        json.dump({"ok": ok, "detail": detail}, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
        return 0 if ok else 2

    if args.command == "full-may-start":
        required = json.loads(args.required_ci)
        allowed, detail = full_may_start(
            sealed=False,
            fast_status=args.fast_status,
            required_ci=required,
            live_head_sha=args.live_head or ("0" * 40),
        )
        json.dump({"allowed": allowed, "detail": detail}, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
        return 0 if allowed else 2

    if not args.repository or not args.accept:
        print("assemble requires --repository and one or more --accept branch@sha", file=sys.stderr)
        return 2
    sources = [parse_accept(raw, order) for order, raw in enumerate(args.accept, start=1)]
    evidence_payloads: dict[str, Any] | None = None
    if args.evidence_json:
        try:
            loaded = parse_immutable_evidence_payload(args.evidence_json)
        except Exception as exc:  # noqa: BLE001
            print(f"assemble --evidence-json invalid: {exc}", file=sys.stderr)
            return 2
        if not isinstance(loaded, dict):
            print("assemble --evidence-json must be a JSON object", file=sys.stderr)
            return 2
        if loaded.get("headSha") or loaded.get("kind"):
            sha = normalize_sha(str(loaded.get("headSha") or ""))
            evidence_payloads = {sha: loaded} if sha else {"*": loaded}
        else:
            evidence_payloads = {
                normalize_sha(str(key)): value
                for key, value in loaded.items()
                if isinstance(value, dict)
            }
    try:
        github, pusher = resolve_production_adapters(args.repository)
        result = assemble_phase(
            repo=Path(args.repo_path).resolve(),
            repository=args.repository,
            sources=sources,
            github=github,
            pusher=pusher,
            phase_branch=args.phase_branch,
            development=args.development,
            remote=args.remote,
            require_evidence=not args.no_evidence,
            expected_repository=args.repository,
            require_live_pr=True,
            evidence_payloads=evidence_payloads,
        )
    except (CoordinatorError, PhaseLifecycleError) as exc:
        payload = exc.to_dict() if hasattr(exc, "to_dict") else {"code": "failed", "detail": str(exc)}
        json.dump({"ok": False, **payload}, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    json.dump({"ok": True, **{k: v for k, v in result.items() if k != "record"}}, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
