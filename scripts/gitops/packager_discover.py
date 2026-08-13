#!/usr/bin/env python3
"""Packager discovery: ready tips → draft PRs. Preserves existing PR title/body.

Eligibility is the successful GitHub commit status ``Linktrend Review Ready`` on
the **exact** branch tip SHA (same contract whether published by the local gate
or the normal-token publisher). Later tips without that status are not eligible.

Updates only a delimited managed section. No Bugbot. No serial CI wait.
Requires:
  - GitHub automation token for reads / draft body refresh / non-create mutations
  - Carlos BUGBOT_USER_TOKEN for feature PR *creation* only (fail closed)
  - Existing/open Packager PRs must be authored by ``linktrend`` (fail closed)
"""

from __future__ import annotations

import json
import os
import re
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
    REQUIRED_PACKAGER_PR_AUTHOR,
    is_allowed_work_branch,
    require_packager_pr_author,
)
from delivery_modes import (  # noqa: E402
    PHASE_DELIVERY_REL,
    load_delivery_config,
    load_exception_for_tip,
    phase_draft_record_ready,
    should_open_pr_for_branch,
    validate_phase_delivery_record,
)
from readiness_status import is_sha_review_ready  # noqa: E402
from write_outcome import write_outcome  # noqa: E402

BEGIN = "<!-- linktrend-packager:begin -->"
END = "<!-- linktrend-packager:end -->"
SECTION_RE = re.compile(
    re.escape(BEGIN) + r".*?" + re.escape(END),
    re.DOTALL,
)

# Test hook: (args, env) -> stdout string. When set, skips real subprocess.
_RUN_HOOK: Callable[[list[str], dict[str, str]], str] | None = None
# Test hook: (token, repo) -> branch list. When set, skips live Branches API.
_LIST_BRANCHES_HOOK: Callable[[str, str], list[dict]] | None = None
# Test hook: (token, repo, sha) -> phase delivery record dict | None.
_PHASE_DELIVERY_HOOK: Callable[[str, str, str], dict[str, Any] | None] | None = None


class PackagerAuthorError(RuntimeError):
    """Open Packager PR is not authored by the required Carlos identity."""


def run(args: list[str], token: str, *, role: str = "automation") -> str:
    """Run a command with a scrubbed env; Carlos secret names never leak to automation child processes."""
    env = subprocess_env_for_token(token, role=role)
    if _RUN_HOOK is not None:
        return _RUN_HOOK(list(args), dict(env)).strip()
    return subprocess.check_output(args, text=True, env=env).strip()


def gh_api(method: str, url: str, token: str, body=None):
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


def fetch_issue_pr_exception(
    token: str, repo: str, sha: str
) -> dict[str, Any] | None:
    """Load `.linktrend/issue-pr-exception.json` from the exact tip SHA (fail closed)."""
    import base64

    url = (
        f"https://api.github.com/repos/{repo}/contents/"
        f".linktrend/issue-pr-exception.json?ref={sha}"
    )
    try:
        payload = gh_api("GET", url, token)
    except RuntimeError:
        return None
    if not isinstance(payload, dict):
        return None
    encoding = payload.get("encoding")
    content = payload.get("content")
    if encoding != "base64" or not isinstance(content, str):
        return None
    try:
        raw = base64.b64decode(content).decode("utf-8")
        data = json.loads(raw)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def fetch_phase_delivery_record(
    token: str, repo: str, sha: str
) -> dict[str, Any] | None:
    """Load `.linktrend/phase-delivery-record.json` from the exact tip SHA."""
    if _PHASE_DELIVERY_HOOK is not None:
        return _PHASE_DELIVERY_HOOK(token, repo, sha)
    import base64

    rel = PHASE_DELIVERY_REL.as_posix()
    url = f"https://api.github.com/repos/{repo}/contents/{rel}?ref={sha}"
    try:
        payload = gh_api("GET", url, token)
    except RuntimeError:
        return None
    if not isinstance(payload, dict):
        return None
    encoding = payload.get("encoding")
    content = payload.get("content")
    if encoding != "base64" or not isinstance(content, str):
        return None
    try:
        raw = base64.b64decode(content).decode("utf-8")
        data = json.loads(raw)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def managed_section(sha: str, branch: str) -> str:
    return (
        f"{BEGIN}\n"
        f"## Review Packager (managed)\n\n"
        f"- Candidate tip SHA: `{sha}`\n"
        f"- Branch: `{branch}`\n"
        f"- Phase: discovery — draft only; Bugbot is requested only after fast-gate "
        f"on this exact SHA (evaluate / workflow_run path).\n"
        f"{END}\n"
    )


def merge_body(existing: str, sha: str, branch: str) -> str:
    section = managed_section(sha, branch)
    if SECTION_RE.search(existing or ""):
        return SECTION_RE.sub(section.strip(), existing)
    base = (existing or "").rstrip()
    if base:
        return base + "\n\n" + section
    return section


def list_branches(token: str, repo: str) -> list[dict]:
    if _LIST_BRANCHES_HOOK is not None:
        return _LIST_BRANCHES_HOOK(token, repo)
    branches = []
    page = 1
    while True:
        chunk = gh_api(
            "GET",
            f"https://api.github.com/repos/{repo}/branches?per_page=100&page={page}",
            token,
        )
        if not chunk:
            break
        branches.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
    return branches


def record_author_blocked_repair(
    app_token: str,
    *,
    repo: str,
    pr: int,
    branch: str,
    head_sha: str,
    detail: str,
) -> None:
    """Durable automation-authored repair; never auto-close/recreate the unexpected PR."""
    env = subprocess_env_for_token(app_token, role="automation")
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
        branch,
        "--head-sha",
        head_sha,
        "--workflow",
        "Linktrend Review Packager",
        "--next-action",
        (
            f"Packager PR author invalid ({detail}). Expected login "
            f"`{REQUIRED_PACKAGER_PR_AUTHOR}`. Do not auto-close/recreate; "
            "supersede only via a separately proven safe lifecycle."
        ),
    ]
    if _RUN_HOOK is not None:
        _RUN_HOOK(cmd, dict(env))
        return
    subprocess.run(cmd, check=False, env=env, capture_output=True, text=True)


def ensure_draft_pr(app_token: str, branch: str, sha: str) -> dict:
    """Ensure an open development draft PR exists for branch@sha.

    Reads and draft-body refresh use the GitHub automation token.
    PR *creation* uses BUGBOT_USER_TOKEN only (Carlos identity) — fail closed.
    Existing PRs must already be authored by ``linktrend``.
    """
    existing = json.loads(
        run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch,
                "--base",
                "development",
                "--state",
                "open",
                "--json",
                "number,url,isDraft,headRefOid,title,body,author",
            ],
            app_token,
            role="automation",
        )
        or "[]"
    )
    if existing:
        pr = existing[0]
        ok_author, author_detail = require_packager_pr_author(pr)
        if not ok_author:
            raise PackagerAuthorError(
                f"existing_pr#{pr.get('number')}:{author_detail}"
            )
        # Ready/frozen PRs: never rewrite title/body (preserve human/agent content).
        if not bool(pr.get("isDraft")):
            return {
                "number": pr["number"],
                "url": pr["url"],
                "isDraft": False,
                "created": False,
                "title_preserved": True,
                "body_untouched": True,
                "author": author_detail,
                "author_token": "preexisting",
            }
        new_body = merge_body(pr.get("body") or "", sha, branch)
        if new_body != (pr.get("body") or ""):
            run(
                ["gh", "pr", "edit", str(pr["number"]), "--body", new_body],
                app_token,
                role="automation",
            )
        # Never overwrite title
        return {
            "number": pr["number"],
            "url": pr["url"],
            "isDraft": bool(pr.get("isDraft")),
            "created": False,
            "title_preserved": True,
            "author": author_detail,
            "author_token": "preexisting",
        }

    # Create path — Carlos user token only. Never normal automation or GITHUB_TOKEN.
    user_token = require_bugbot_user_token("pr_create")
    title = f"Review: {branch}"
    body = merge_body("", sha, branch)
    url = run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            "development",
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
            "--draft",
        ],
        user_token,
        role="pr_create",
    )
    meta = json.loads(
        run(
            [
                "gh",
                "pr",
                "view",
                url,
                "--json",
                "number,author,headRefOid",
            ],
            app_token,
            role="automation",
        )
    )
    ok_author, author_detail = require_packager_pr_author(meta)
    if not ok_author:
        raise PackagerAuthorError(f"created_pr_author_reread:{author_detail}")
    return {
        "number": int(meta["number"]),
        "url": url,
        "isDraft": True,
        "created": True,
        "title_preserved": True,
        "author": author_detail,
        "author_token": "bugbot_user",
    }


def main() -> int:
    token = os.environ.get("AUTOMATION_TOKEN") or ""
    if not token or os.environ.get("AUTOMATION_TOKEN_SOURCE") != "github_token":
        write_outcome(
            Path("gitops-outcome.json"),
            "automation_credentials_blocked",
            "Packager discover requires LINKTREND_AUTOMATION_TOKEN",
        )
        return 0

    # Fail closed before any create: Carlos user token required for PR authorship.
    try:
        require_bugbot_user_token("pr_create")
    except BugbotUserCredentialsError as e:
        write_outcome(
            Path("gitops-outcome.json"),
            "bugbot_user_credentials_blocked",
            f"Packager discover requires LINKTREND_BUGBOT_USER_TOKEN for PR create ({e})",
        )
        return 0

    repo = os.environ["GITHUB_REPOSITORY"]
    delivery = load_delivery_config(Path.cwd())
    report: list[dict[str, Any]] = []
    packaged = 0
    for b in list_branches(token, repo):
        name = b.get("name") or ""
        if not is_allowed_work_branch(name, delivery.phase_branch_prefix):
            continue
        sha = ((b.get("commit") or {}).get("sha") or "").lower()
        if not sha:
            continue
        phase_preview = None
        phase_draft = False
        if delivery.is_phase_integration and name.startswith(delivery.phase_branch_prefix):
            # An early Phase draft is visibility-only.  It may exist before the
            # sealed candidate receives Review Ready and must not trigger gates.
            phase_preview = fetch_phase_delivery_record(token, repo, sha)
            phase_draft = isinstance(phase_preview, dict) and not bool(phase_preview.get("sealed"))
        if phase_draft:
            ok, detail = phase_draft_record_ready(
                phase_preview,
                branch=name,
                head_sha=sha,
                phase_branch_prefix=delivery.phase_branch_prefix,
            )
        else:
            ok, detail = is_sha_review_ready(sha)
        entry: dict[str, Any] = {
            "branch": name,
            "headSha": sha,
            "ready": ok,
            "detail": detail,
            "deliveryMode": delivery.delivery_mode,
        }
        if not ok:
            entry["action"] = "skipped_not_ready"
            report.append(entry)
            continue

        risk_payload = fetch_issue_pr_exception(token, repo, sha)
        risk_class, risk_detail = load_exception_for_tip(
            repo_root=None,
            branch=name,
            sha=sha,
            payload=risk_payload,
        )
        decision = should_open_pr_for_branch(
            name,
            delivery,
            risk_class=risk_class,
            review_ready=True,
        )
        entry["prDecision"] = decision.reason
        if risk_class:
            entry["riskClass"] = risk_class
            entry["riskDetail"] = risk_detail
        if not decision.open_pr:
            entry["action"] = decision.reason
            report.append(entry)
            continue

        if decision.reason == "phase_branch_pr":
            phase_record = phase_preview or fetch_phase_delivery_record(token, repo, sha)
            if phase_draft:
                ok_phase, phase_detail = phase_draft_record_ready(
                    phase_record,
                    branch=name,
                    head_sha=sha,
                    phase_branch_prefix=delivery.phase_branch_prefix,
                )
            else:
                ok_phase, phase_detail = validate_phase_delivery_record(
                    phase_record,
                    branch=name,
                    head_sha=sha,
                    phase_branch_prefix=delivery.phase_branch_prefix,
                )
            entry["phaseDelivery"] = phase_detail
            if not ok_phase:
                entry["action"] = f"skipped_phase_delivery:{phase_detail}"
                report.append(entry)
                continue

        try:
            pr = ensure_draft_pr(token, name, sha)
            viewed = json.loads(
                run(
                    [
                        "gh",
                        "pr",
                        "view",
                        str(pr["number"]),
                        "--json",
                        "headRefOid,author",
                    ],
                    token,
                    role="automation",
                )
            )
            head = (viewed.get("headRefOid") or "").lower()
            ok_author, author_detail = require_packager_pr_author(viewed)
            if not ok_author:
                raise PackagerAuthorError(
                    f"post_ensure_reread:#{pr['number']}:{author_detail}"
                )
            if head != sha:
                entry.update({"action": "skipped_head_drift", "pr": pr["number"]})
            else:
                entry.update(
                    {
                        "action": "draft_ensured",
                        "pr": pr["number"],
                        "pr_url": pr["url"],
                        "author": author_detail,
                        "author_token": pr.get("author_token"),
                    }
                )
                packaged += 1
        except PackagerAuthorError as e:
            detail = str(e)
            entry.update(
                {
                    "action": "blocked_wrong_author",
                    "reason": detail,
                    "status": "blocked",
                }
            )
            # Best-effort PR number from detail
            pr_num = 0
            m = re.search(r"#(\d+)", detail)
            if m:
                pr_num = int(m.group(1))
            if pr_num:
                entry["pr"] = pr_num
                record_author_blocked_repair(
                    token,
                    repo=repo,
                    pr=pr_num,
                    branch=name,
                    head_sha=sha,
                    detail=detail,
                )
            report.append(entry)
            Path("packager-discover-report.json").write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
            write_outcome(
                Path("gitops-outcome.json"),
                "blocked",
                f"superseded_wrong_author:{detail}",
                report=report,
            )
            print(json.dumps(report, indent=2))
            return 0
        except BugbotUserCredentialsError as e:
            entry.update({"action": "bugbot_user_credentials_blocked", "reason": str(e)})
            report.append(entry)
            Path("packager-discover-report.json").write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
            write_outcome(
                Path("gitops-outcome.json"),
                "bugbot_user_credentials_blocked",
                str(e),
                report=report,
            )
            print(json.dumps(report, indent=2))
            return 0
        except Exception as e:  # noqa: BLE001
            entry.update({"action": "error", "reason": str(e)})
        report.append(entry)

    Path("packager-discover-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    status = "packaged" if packaged else "skipped"
    write_outcome(
        Path("gitops-outcome.json"),
        status,
        f"discover packaged_or_refreshed={packaged} deliveryMode={delivery.delivery_mode}",
        report=report,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
