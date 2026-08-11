#!/usr/bin/env python3
"""Packager evaluate: wake on PR / workflow_run / external check_run.

Trusted scripts only (caller must checkout default branch). Race-safe head rereads.
Readiness is re-checked on the exact live head SHA (``Linktrend Review Ready``),
whether that status came from the local gate or the App-backed publisher.

Credentials:
  - GitHub App (AUTOMATION_TOKEN): reads, undraft, freeze comment, check-runs, repair
  - Carlos BUGBOT_USER_TOKEN: the single `@cursor review` comment only (fail closed)

PR author must be exactly ``linktrend`` before undraft or Bugbot request.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bugbot_user_credentials import (  # noqa: E402
    BugbotUserCredentialsError,
    require_bugbot_user_token,
    subprocess_env_for_token,
)
from packager_logic import (  # noqa: E402
    DEFAULT_BUGBOT_COMMAND,
    REQUIRED_PACKAGER_PR_AUTHOR,
    build_bugbot_comment,
    fast_gate_status,
    parse_required_checks,
    require_packager_pr_author,
    should_request_bugbot,
)
from readiness_status import is_sha_review_ready  # noqa: E402
from write_outcome import post_check_run, write_outcome  # noqa: E402

# Test hook: (args, env) -> stdout string.
_RUN_HOOK: Callable[[list[str], dict[str, str]], str] | None = None
# Test hook for HTTP API: (method, url, token, body, env_snapshot) -> payload
_API_HOOK: Callable[[str, str, str, Any, dict[str, str]], Any] | None = None


def run(args: list[str], token: str, *, role: str = "app") -> str:
    env = subprocess_env_for_token(token, role=role)
    if _RUN_HOOK is not None:
        return _RUN_HOOK(list(args), dict(env)).strip()
    return subprocess.check_output(args, text=True, env=env).strip()


def _parent_env_snapshot() -> dict[str, str]:
    """Snapshot whether Carlos secret names are present in *this* process.

    API calls are in-process; child scrubbing is enforced on subprocesses.
    Hooks record this snapshot so tests can assert comment ops do not spawn
    a gh child that inherits Carlos env names.
    """
    return {
        k: ("set" if os.environ.get(k) else "absent")
        for k in ("LINKTREND_BUGBOT_USER_TOKEN", "BUGBOT_USER_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
    }


def gh_api(method: str, url: str, token: str, body=None):
    if _API_HOOK is not None:
        return _API_HOOK(method, url, token, body, _parent_env_snapshot())
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "linktrend-review-packager",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> {e.code}: {detail}") from e


def pr_head(pr: int, token: str) -> str:
    return run(
        ["gh", "pr", "view", str(pr), "--json", "headRefOid", "--jq", ".headRefOid"],
        token,
        role="app",
    ).lower()


def pr_meta(pr: int, token: str) -> dict:
    return json.loads(
        run(
            [
                "gh",
                "pr",
                "view",
                str(pr),
                "--json",
                "number,url,isDraft,headRefOid,baseRefName,state,headRefName,author",
            ],
            token,
            role="app",
        )
    )


def pr_checks(pr: int, token: str) -> list[dict]:
    return json.loads(
        run(
            ["gh", "pr", "checks", str(pr), "--json", "name,state,completedAt,startedAt"],
            token,
            role="app",
        )
        or "[]"
    )


def list_comments(token: str, repo: str, pr: int) -> list[dict]:
    return gh_api(
        "GET",
        f"https://api.github.com/repos/{repo}/issues/{pr}/comments?per_page=100",
        token,
    )


def post_comment(token: str, repo: str, pr: int, body: str) -> None:
    gh_api(
        "POST",
        f"https://api.github.com/repos/{repo}/issues/{pr}/comments",
        token,
        {"body": body},
    )


def record_author_blocked_repair(
    app_token: str,
    *,
    repo: str,
    pr: int,
    branch: str,
    head_sha: str,
    detail: str,
) -> None:
    env = subprocess_env_for_token(app_token, role="app")
    script = str(Path(__file__).resolve().parent / "repair_task.py")
    cmd = [
        sys.executable,
        script,
        "upsert",
        "--repo",
        repo,
        "--failure-type",
        "packager_author_blocked",
        "--severity",
        "immediate",
        "--pr",
        str(pr),
        "--branch",
        branch or "",
        "--head-sha",
        head_sha,
        "--workflow",
        "Linktrend Review Packager",
        "--next-action",
        (
            f"Packager PR author invalid ({detail}). Expected `{REQUIRED_PACKAGER_PR_AUTHOR}`. "
            "Do not post @cursor review. Do not auto-close/recreate without a proven lifecycle."
        ),
    ]
    if _RUN_HOOK is not None:
        _RUN_HOOK(cmd, dict(env))
        return
    subprocess.run(cmd, check=False, env=env, capture_output=True, text=True)


def resolve_pr_number(token: str) -> int | None:
    if os.environ.get("PR_NUMBER"):
        return int(os.environ["PR_NUMBER"])
    head = (os.environ.get("HEAD_SHA") or "").lower()
    if head:
        out = run(
            [
                "gh",
                "pr",
                "list",
                "--base",
                "development",
                "--state",
                "open",
                "--json",
                "number,headRefOid",
                "--jq",
                f'[.[] | select(.headRefOid=="{head}")][0].number // empty',
            ],
            token,
            role="app",
        )
        return int(out) if out else None
    return None


def _block_wrong_author(
    *,
    app_token: str,
    repo: str,
    pr: int,
    branch: str,
    head_sha: str,
    detail: str,
    result: dict,
) -> dict:
    result["status"] = "blocked"
    result["detail"] = f"superseded_wrong_author:{detail}"
    result["headSha"] = head_sha
    record_author_blocked_repair(
        app_token,
        repo=repo,
        pr=pr,
        branch=branch,
        head_sha=head_sha,
        detail=detail,
    )
    return result


def evaluate_pr(pr: int, app_token: str) -> dict:
    repo = os.environ["GITHUB_REPOSITORY"]
    command = (
        os.environ.get("BUGBOT_REVIEW_COMMAND")
        or os.environ.get("LINKTREND_BUGBOT_REVIEW_COMMAND")
        or DEFAULT_BUGBOT_COMMAND
    ).strip()
    required = (
        os.environ.get("FAST_GATE_CHECKS")
        or os.environ.get("LINKTREND_INTEGRATOR_REQUIRED_CHECKS")
        or "Verify IDE Development"
    )

    meta = pr_meta(pr, app_token)
    result: dict = {"pr": pr}
    if meta.get("baseRefName") != "development" or meta.get("state") != "OPEN":
        result["status"] = "skipped"
        result["detail"] = "not_open_development_pr"
        return result

    sha1 = (meta.get("headRefOid") or "").lower()
    event_head = (os.environ.get("HEAD_SHA") or "").lower()
    if event_head and event_head != sha1:
        result["status"] = "skipped"
        result["detail"] = f"stale_event_head:{event_head}!={sha1}"
        result["headSha"] = sha1
        return result

    ok_author, author_detail = require_packager_pr_author(meta)
    if not ok_author:
        return _block_wrong_author(
            app_token=app_token,
            repo=repo,
            pr=pr,
            branch=str(meta.get("headRefName") or ""),
            head_sha=sha1,
            detail=author_detail,
            result=result,
        )
    result["author"] = author_detail

    ready, detail = is_sha_review_ready(sha1)
    result["headSha"] = sha1
    if not ready:
        result["status"] = "waiting"
        result["detail"] = f"not_ready:{detail}"
        return result

    checks = pr_checks(pr, app_token)
    gate_status, gate_detail = fast_gate_status(checks, parse_required_checks(required))
    result["fast_gate"] = {"status": gate_status, "detail": gate_detail}
    if gate_status != "success":
        result["status"] = "waiting" if gate_status == "pending" else "blocked"
        result["detail"] = f"fast_gate:{gate_status}:{gate_detail}"
        return result

    sha2 = pr_head(pr, app_token)
    if sha2 != sha1:
        result["status"] = "skipped"
        result["detail"] = f"abort_head_changed_after_gate:{sha2}"
        return result

    ready2, _ = is_sha_review_ready(sha2)
    if not ready2:
        result["status"] = "skipped"
        result["detail"] = "readiness_lost"
        return result

    # Live author reread before undraft — never undraft a bot/App PR.
    pre_ready = pr_meta(pr, app_token)
    ok_author, author_detail = require_packager_pr_author(pre_ready)
    if not ok_author:
        return _block_wrong_author(
            app_token=app_token,
            repo=repo,
            pr=pr,
            branch=str(pre_ready.get("headRefName") or meta.get("headRefName") or ""),
            head_sha=(pre_ready.get("headRefOid") or sha1).lower(),
            detail=f"before_undraft:{author_detail}",
            result=result,
        )

    if pre_ready.get("isDraft"):
        run(["gh", "pr", "ready", str(pr)], app_token, role="app")

    sha3 = pr_head(pr, app_token)
    if sha3 != sha1:
        result["status"] = "skipped"
        result["detail"] = f"abort_head_changed_before_bugbot:{sha3}"
        return result

    comments = list_comments(app_token, repo, pr)
    ok, reason = should_request_bugbot(comments=comments, head_sha=sha3, fast_gate_ok=True)
    if not ok:
        result["status"] = "skipped" if reason.startswith("skipped_") else "blocked"
        result["detail"] = reason
        return result

    # Final live author reread immediately before Bugbot comment.
    final_meta = pr_meta(pr, app_token)
    ok_author, author_detail = require_packager_pr_author(final_meta)
    if not ok_author:
        return _block_wrong_author(
            app_token=app_token,
            repo=repo,
            pr=pr,
            branch=str(final_meta.get("headRefName") or ""),
            head_sha=(final_meta.get("headRefOid") or sha3).lower(),
            detail=f"before_bugbot:{author_detail}",
            result=result,
        )
    final_sha = (final_meta.get("headRefOid") or "").lower()
    if final_sha != sha3:
        result["status"] = "skipped"
        result["detail"] = f"abort_head_changed_author_reread:{final_sha}"
        return result

    # Bugbot trigger comment — Carlos user token only (API header, not gh child).
    try:
        user_token = require_bugbot_user_token("bugbot_comment")
    except BugbotUserCredentialsError as e:
        result["status"] = "bugbot_user_credentials_blocked"
        result["detail"] = str(e)
        return result

    post_comment(user_token, repo, pr, build_bugbot_comment(command, sha3))
    result["status"] = "bugbot_requested"
    result["detail"] = f"requested_for_{sha3}"
    result["headSha"] = sha3
    result["author"] = author_detail
    result["bugbot_comment_token"] = "bugbot_user"
    # Freeze comment remains App-authored (not a Bugbot trigger).
    post_comment(
        app_token,
        repo,
        pr,
        (
            f"## Review freeze\n\n"
            f"Branch `{final_meta.get('headRefName')}` is frozen at `{sha3}` for review.\n"
            f"Continue only on another work branch or worktree.\n"
        ),
    )
    return result


def main() -> int:
    token = os.environ.get("AUTOMATION_TOKEN") or ""
    source = os.environ.get("AUTOMATION_TOKEN_SOURCE") or ""
    if source != "github_app" or not token:
        # Fail closed: no GITHUB_TOKEN mutations when App is unavailable.
        write_outcome(
            Path("gitops-outcome.json"),
            "automation_credentials_blocked",
            "Packager evaluate requires GitHub App token",
        )
        return 0

    # Fail closed early: Bugbot comment path requires Carlos user token.
    # App is available → repair/check use App token only (never workflow GITHUB_TOKEN).
    try:
        require_bugbot_user_token("bugbot_comment")
    except BugbotUserCredentialsError as e:
        write_outcome(
            Path("gitops-outcome.json"),
            "bugbot_user_credentials_blocked",
            f"Packager evaluate requires LINKTREND_BUGBOT_USER_TOKEN for Bugbot comment ({e})",
        )
        head = os.environ.get("HEAD_SHA") or ""
        post_check_run(
            name="Linktrend Packager Result",
            head_sha=head,
            status="bugbot_user_credentials_blocked",
            detail=str(e),
            repo=os.environ.get("GITHUB_REPOSITORY") or "",
            token=token,
        )
        return 0

    pr = resolve_pr_number(token)
    if not pr:
        write_outcome(Path("gitops-outcome.json"), "skipped", "no_pr_candidate")
        return 0

    report = evaluate_pr(pr, token)
    status = report.get("status") or "failed"
    detail = report.get("detail") or ""
    write_outcome(Path("gitops-outcome.json"), status, detail, report=report)
    head = report.get("headSha") or os.environ.get("HEAD_SHA") or ""
    # Check-run always uses App token (AUTOMATION_TOKEN), never workflow GITHUB_TOKEN.
    post_check_run(
        name="Linktrend Packager Result",
        head_sha=head,
        status=status,
        detail=detail,
        repo=os.environ.get("GITHUB_REPOSITORY") or "",
        token=token,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
