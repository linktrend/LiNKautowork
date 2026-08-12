#!/usr/bin/env python3
"""Honest outcome helper for GitOps automation jobs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bugbot_user_credentials import scrub_carlos_token_env  # noqa: E402

VALID = {
    "packaged",
    "waiting",
    "skipped",
    "blocked",
    "failed",
    "bugbot_requested",
    "merged",
    "automation_credentials_blocked",
    "bugbot_user_credentials_blocked",
}


def write_outcome(path: Path, status: str, detail: str, **extra: Any) -> dict[str, Any]:
    if status not in VALID:
        raise SystemExit(f"invalid status {status}")
    payload = {"status": status, "detail": detail, **extra}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"OUTCOME_STATUS={status}")
    print(f"OUTCOME_DETAIL={detail}")
    return payload


def commit_status_state(status: str) -> str | None:
    """Map an internal outcome to an honest terminal GitHub commit status."""
    if status in {"merged", "bugbot_requested", "packaged"}:
        return "success"
    if status == "waiting":
        return "pending"
    if status == "skipped":
        # A stale-event skip says nothing about the live head. Publishing any
        # terminal state would overwrite valid evidence for that head.
        return None
    if status == "blocked":
        return "error"
    return "failure"


def post_check_run(
    *,
    name: str,
    head_sha: str,
    status: str,
    detail: str,
    repo: str,
    token: str,
) -> None:
    """Publish the outcome as a normal GitHub commit status.

    Keep the historical function name for callers, but deliberately avoid the
    Checks API: GitHub restricts creating check runs to GitHub Apps. Commit
    statuses support the same named gate contexts with the normal automation
    token used by IDE Development.
    """
    if not head_sha or not token or not repo:
        return
    env = scrub_carlos_token_env(os.environ)
    env["GH_TOKEN"] = token
    env["GITHUB_TOKEN"] = token
    # Blocked is terminal and unsuccessful. A stale-event skip is not evidence
    # about the live head at all, so it must leave that head's status untouched.
    state = commit_status_state(status)
    if state is None:
        print(
            f"SKIP_STATUS_POST context={name} head_sha={head_sha} "
            f"outcome={status}",
            file=sys.stderr,
        )
        return
    body = {
        "state": state,
        "context": name,
        "description": f"{status}: {detail}"[:140],
    }
    subprocess.run(
        [
            "gh",
            "api",
            "--method",
            "POST",
            f"repos/{repo}/statuses/{head_sha}",
            "--input",
            "-",
        ],
        input=json.dumps(body),
        text=True,
        check=False,
        env=env,
    )


def resolve_check_token(token_env: str) -> str | None:
    """Return token from the exact env name only — no ambient fallbacks.

    Autonomous check mutations must be authorized solely by ``token_env``
    (normally ``AUTOMATION_TOKEN``). Never fall back to ``GH_TOKEN``,
    ``GITHUB_TOKEN``, or any other ambient credential.
    """
    name = (token_env or "").strip()
    if not name:
        return None
    raw = os.environ.get(name)
    if raw is None:
        return None
    token = raw.strip()
    return token or None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="gitops-outcome.json")
    ap.add_argument("--status", required=True)
    ap.add_argument("--detail", required=True)
    ap.add_argument("--check-name", default="")
    ap.add_argument("--head-sha", default="")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument(
        "--token-env",
        default="AUTOMATION_TOKEN",
        help="Exact env var name whose non-empty value authorizes commit-status posts",
    )
    args = ap.parse_args()
    write_outcome(Path(args.file), args.status, args.detail)
    if args.check_name and args.head_sha:
        token = resolve_check_token(args.token_env)
        if not token:
            # Local outcome already written. Failed workflow / redacted warn only.
            print(
                "WARN: skipping commit-status post; "
                f"--token-env={args.token_env} empty or unset "
                "(no ambient GH_TOKEN/GITHUB_TOKEN fallback)",
                file=sys.stderr,
            )
        else:
            post_check_run(
                name=args.check_name,
                head_sha=args.head_sha,
                status=args.status,
                detail=args.detail,
                repo=args.repo,
                token=token,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
