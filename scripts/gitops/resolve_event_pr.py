#!/usr/bin/env python3
"""Trusted read-only candidate resolver for GitOps privileged workflows.

Used by a resolve job that:
  - checks out the default branch (trusted scripts)
  - uses ordinary GITHUB_TOKEN (read-only)
  - exposes only non-secret outputs (relevant, pr, base, head_ref, head_sha, reason)

The privileged mutation job must depend on this job and mint the App token only when
relevant=true. Empty pull_requests arrays are resolved via the commits/pulls API
(fail closed if zero or ambiguous matches).

Roles: packager | integrator | staging | main
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

OUTCOME_CHECKS = frozenset(
    {
        "Linktrend Packager Result",
        "Linktrend Integrator Result",
        "Linktrend Staging Outcome",
        "Linktrend Main Outcome",
        "evaluate",
        "enable-auto-merge",
        "merge-when-ready",
    }
)


def api_get(url: str, token: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "linktrend-gitops-resolve",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _write_outputs(payload: dict[str, str]) -> None:
    lines = [f"{k}={v}" for k, v in payload.items()]
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    for line in lines:
        print(line)


def _result(
    *,
    relevant: bool,
    pr: str = "",
    base: str = "",
    head_ref: str = "",
    head_sha: str = "",
    reason: str = "",
    is_fork: str = "false",
) -> dict[str, str]:
    return {
        "relevant": "true" if relevant else "false",
        "pr": pr,
        "base": base,
        "head_ref": head_ref,
        "head_sha": head_sha,
        "reason": reason,
        "is_fork": is_fork,
    }


def _from_pr_obj(pr: dict) -> dict[str, str]:
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    head_repo = head.get("repo") or {}
    base_repo = base.get("repo") or {}
    is_fork = "false"
    if head_repo and base_repo:
        if (head_repo.get("full_name") or "") != (base_repo.get("full_name") or ""):
            is_fork = "true"
    elif head.get("repo") is None and head.get("ref"):
        # Detached / incomplete payload — treat as unknown, not necessarily fork
        is_fork = "unknown"
    return {
        "pr": str(pr.get("number") or ""),
        "base": str(base.get("ref") or ""),
        "head_ref": str(head.get("ref") or ""),
        "head_sha": str(head.get("sha") or ""),
        "is_fork": is_fork,
    }


def _prs_for_sha(token: str, repo: str, sha: str) -> list[dict]:
    if not token or not repo or not sha:
        return []
    try:
        rows = api_get(f"https://api.github.com/repos/{repo}/commits/{sha}/pulls", token)
    except (urllib.error.HTTPError, TimeoutError, OSError):
        return []
    return rows if isinstance(rows, list) else []


def _match_role(role: str, base: str, head_ref: str, *, draft: bool | None = None) -> tuple[bool, str]:
    if role == "packager":
        if base != "development":
            return False, f"base_not_development:{base}"
        if head_ref.startswith("promote/"):
            return False, "promote_head_excluded"
        return True, "ok"
    if role == "integrator":
        if draft is True:
            return False, "draft_pr"
        if base != "development":
            return False, f"base_not_development:{base}"
        if head_ref.startswith("promote/"):
            return False, "promote_head_excluded"
        return True, "ok"
    if role == "staging":
        if base != "staging":
            return False, f"base_not_staging:{base}"
        if not head_ref.startswith("promote/staging/"):
            return False, "not_staging_promote_head"
        return True, "ok"
    if role == "main":
        if base != "main":
            return False, f"base_not_main:{base}"
        if not head_ref.startswith("promote/main/"):
            return False, "not_main_promote_head"
        return True, "ok"
    return False, f"unknown_role:{role}"


def _select_matching(role: str, prs: list[dict]) -> tuple[dict | None, str]:
    matches: list[dict] = []
    for pr in prs:
        meta = _from_pr_obj(pr)
        draft = pr.get("draft")
        ok, _ = _match_role(role, meta["base"], meta["head_ref"], draft=draft)
        if ok and str(pr.get("state") or "open").lower() in {"open", ""}:
            matches.append(pr)
    if not matches:
        return None, "no_matching_open_pr"
    if len(matches) > 1:
        return None, f"ambiguous_prs:{len(matches)}"
    return matches[0], "ok"


def resolve_candidate(
    event_name: str,
    event: dict,
    token: str,
    repo: str,
    *,
    role: str,
) -> dict[str, str]:
    """Pure-ish resolver used by production and tests."""

    # Schedule / discover / promote build windows always relevant for their roles
    if event_name in {"schedule", "workflow_dispatch"} and role in {"staging", "main", "packager"}:
        if role == "packager" and event_name in {"schedule", "workflow_dispatch"}:
            # Discover path — not an evaluate candidate
            return _result(relevant=False, reason="discover_not_evaluate")
        if role in {"staging", "main"}:
            inputs = event.get("inputs") or {}
            return _result(
                relevant=True,
                pr=str(inputs.get("promote_pr_number") or inputs.get("pr_number") or ""),
                head_sha=str(
                    inputs.get("expected_head_sha")
                    or inputs.get("expected_promote_head")
                    or ""
                ),
                reason="schedule_or_dispatch",
            )

    if event_name == "workflow_dispatch" and role == "integrator":
        inputs = event.get("inputs") or {}
        pr = str(inputs.get("pr_number") or "")
        if not pr:
            return _result(relevant=False, reason="dispatch_missing_pr")
        return _result(relevant=True, pr=pr, reason="dispatch_pr")

    if event_name in {"pull_request", "pull_request_target"}:
        pr = event.get("pull_request") or {}
        meta = _from_pr_obj(pr)
        ok, reason = _match_role(
            role, meta["base"], meta["head_ref"], draft=pr.get("draft")
        )
        if not ok:
            return _result(relevant=False, reason=reason, **meta)
        return _result(relevant=True, reason="pull_request_event", **meta)

    if event_name == "workflow_run":
        wr = event.get("workflow_run") or {}
        if str(wr.get("conclusion") or "") != "success":
            return _result(relevant=False, reason="workflow_run_not_success")
        head_sha = str(wr.get("head_sha") or "")
        head_branch = str(wr.get("head_branch") or "")
        # Push CI with no PR association: fail closed unless API finds a matching PR
        prs = list(wr.get("pull_requests") or [])
        source = "event_pull_requests"
        if not prs:
            prs = _prs_for_sha(token, repo, head_sha)
            source = "api_commits_pulls"
        chosen, why = _select_matching(role, prs)
        if not chosen:
            # Staging/main may also accept head_branch filter when push builds promote branch
            if role == "staging" and head_branch.startswith("promote/staging/"):
                # Still need a PR number for reevaluate — fail closed if API found none
                return _result(
                    relevant=False,
                    head_sha=head_sha,
                    head_ref=head_branch,
                    reason=f"empty_pr_array_unresolved:{why}",
                )
            if role == "main" and head_branch.startswith("promote/main/"):
                return _result(
                    relevant=False,
                    head_sha=head_sha,
                    head_ref=head_branch,
                    reason=f"empty_pr_array_unresolved:{why}",
                )
            return _result(
                relevant=False,
                head_sha=head_sha,
                head_ref=head_branch,
                reason=f"{source}:{why}",
            )
        meta = _from_pr_obj(chosen)
        if head_sha and meta["head_sha"] and head_sha != meta["head_sha"]:
            # Prefer event head SHA (candidate under test)
            meta["head_sha"] = head_sha
        return _result(relevant=True, reason=f"{source}:matched", **meta)

    if event_name == "check_run":
        cr = event.get("check_run") or {}
        slug = str((cr.get("app") or {}).get("slug") or "")
        name = str(cr.get("name") or "")
        if slug == "github-actions":
            return _result(relevant=False, reason="github_actions_check_filtered")
        if name in OUTCOME_CHECKS:
            return _result(relevant=False, reason=f"outcome_check_filtered:{name}")
        head_sha = str(cr.get("head_sha") or "")
        prs = list(cr.get("pull_requests") or [])
        source = "event_pull_requests"
        if not prs:
            prs = _prs_for_sha(token, repo, head_sha)
            source = "api_commits_pulls"
        chosen, why = _select_matching(role, prs)
        if not chosen:
            return _result(
                relevant=False,
                head_sha=head_sha,
                reason=f"{source}:{why}",
            )
        meta = _from_pr_obj(chosen)
        if head_sha:
            meta["head_sha"] = head_sha
        return _result(relevant=True, reason=f"{source}:matched", **meta)

    return _result(relevant=False, reason=f"unsupported_event:{event_name}")


def main() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH") or ""
    event_name = os.environ.get("GITHUB_EVENT_NAME") or os.environ.get("EVENT_NAME") or ""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    repo = os.environ.get("GITHUB_REPOSITORY") or ""
    role = (os.environ.get("RESOLVE_ROLE") or "packager").strip()

    if not event_path or not Path(event_path).is_file():
        _write_outputs(_result(relevant=False, reason="missing_event_path"))
        return 0

    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    payload = resolve_candidate(event_name, event, token, repo, role=role)
    _write_outputs(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
