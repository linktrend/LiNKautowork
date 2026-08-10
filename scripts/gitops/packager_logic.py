#!/usr/bin/env python3
"""Packager helpers: discovery validation, Bugbot request policy, fast-gate wait.

Pure-ish functions for behavioral tests. Workflows call CLI entrypoints.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

MARKER_PREFIX = "<!-- linktrend-bugbot-requested:"
DEFAULT_BUGBOT_COMMAND = "@cursor review"
MAX_BUGBOT_REQUESTS = 2
# Packager feature PRs into development must be authored by Carlos (human user).
REQUIRED_PACKAGER_PR_AUTHOR = "linktrend"

# Executable Bugbot triggers (Cursor Manual Only). Bare "cursor review" is NOT executable.
_EXECUTABLE_TRIGGER_RE = re.compile(
    r"(?im)^\s*(?:@cursor\s+review|bugbot\s+run)\s*$"
)


def packager_pr_author_login(pr_payload: dict[str, Any] | None) -> str | None:
    """Extract GitHub login from gh/API PR payload (author or user)."""
    if not isinstance(pr_payload, dict):
        return None
    for key in ("author", "user"):
        node = pr_payload.get(key)
        if isinstance(node, dict):
            login = node.get("login")
            if isinstance(login, str) and login.strip():
                return login.strip()
        elif isinstance(node, str) and node.strip():
            return node.strip()
    return None


def require_packager_pr_author(pr_payload: dict[str, Any] | None) -> tuple[bool, str]:
    """Require exact Packager PR author login ``linktrend``.

    Returns (ok, detail). detail is the login on success, or an error code.
    """
    login = packager_pr_author_login(pr_payload)
    if not login:
        return False, "missing_packager_pr_author"
    if login != REQUIRED_PACKAGER_PR_AUTHOR:
        return (
            False,
            f"wrong_packager_pr_author:expected={REQUIRED_PACKAGER_PR_AUTHOR}:got={login}",
        )
    return True, login



def marker_for(sha: str) -> str:
    return f"{MARKER_PREFIX} {sha.lower()} -->"


def has_executable_bugbot_trigger(body: str) -> bool:
    """True when the comment includes a trigger Bugbot can actually execute."""
    return bool(_EXECUTABLE_TRIGGER_RE.search(body or ""))


def count_bugbot_requests(comments: list[dict[str, Any]], sha: str | None = None) -> int:
    """Count genuine Bugbot request comments.

    A slot is consumed only when the comment contains:
      - an executable trigger line (`@cursor review` or `bugbot run`), AND
      - the SHA marker (`<!-- linktrend-bugbot-requested: … -->`).

    Historical invalid `cursor review` + marker pairs do NOT count.
    Optional ``sha`` restricts to markers mentioning that full SHA.
    """
    n = 0
    sha_l = (sha or "").lower()
    for c in comments:
        body = c.get("body") or ""
        if MARKER_PREFIX not in body:
            continue
        if not has_executable_bugbot_trigger(body):
            continue
        if sha_l and sha_l not in body.lower():
            continue
        n += 1
    return n


def should_request_bugbot(
    *,
    comments: list[dict[str, Any]],
    head_sha: str,
    fast_gate_ok: bool,
) -> tuple[bool, str]:
    if not fast_gate_ok:
        return False, "fast_gate_not_green"
    needle = marker_for(head_sha)
    for c in comments:
        body = c.get("body") or ""
        # Same-SHA idempotency: only a genuine prior request blocks a duplicate.
        if needle in body and has_executable_bugbot_trigger(body):
            return False, "skipped_duplicate_marker"
    if count_bugbot_requests(comments) >= MAX_BUGBOT_REQUESTS:
        return False, "skipped_max_requests"
    return True, "request"


def build_bugbot_comment(command: str, sha: str) -> str:
    cmd = (command or DEFAULT_BUGBOT_COMMAND).strip() or DEFAULT_BUGBOT_COMMAND
    return f"{cmd}\n\n{marker_for(sha)}\n"


def latest_checks_by_name(checks: list[dict[str, Any]]) -> dict[str, str]:
    """Map check name -> latest state/conclusion (uppercase)."""
    # Prefer completedAt ordering when present
    grouped: dict[str, list[dict[str, Any]]] = {}
    for c in checks:
        name = c.get("name") or ""
        if not name:
            continue
        grouped.setdefault(name, []).append(c)

    out: dict[str, str] = {}
    for name, rows in grouped.items():
        rows_sorted = sorted(
            rows,
            key=lambda r: r.get("completedAt") or r.get("completed_at") or r.get("startedAt") or r.get("started_at") or "",
        )
        last = rows_sorted[-1]
        state = (
            last.get("state")
            or last.get("conclusion")
            or last.get("status")
            or "missing"
        )
        out[name] = str(state).upper()
    return out


def fast_gate_status(
    checks: list[dict[str, Any]],
    required: list[str],
) -> tuple[str, str]:
    """Return (status, detail) where status is success|pending|failed|missing."""
    latest = latest_checks_by_name(checks)
    req = [r.strip() for r in required if r.strip()]
    if not req:
        return "failed", "REQUIRED_CHECKS empty"
    for name in req:
        state = latest.get(name, "MISSING")
        if state in {"PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED"}:
            return "pending", f"{name}={state}"
        if state in {"MISSING", ""}:
            return "missing", f"{name}=missing"
        if state != "SUCCESS":
            return "failed", f"{name}={state}"
    return "success", "all required success"


def parse_required_checks(raw: str) -> list[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def is_allowed_work_branch(
    name: str,
    phase_branch_prefix: str = "phase/",
) -> bool:
    """Return True if *name* is an allowlisted short-lived work branch.

    ``phase_branch_prefix`` comes from delivery-mode config (default ``phase/``)
    so Packager discovery can see Phase tips under a custom prefix.
    """
    phase = phase_branch_prefix if phase_branch_prefix.endswith("/") else f"{phase_branch_prefix}/"
    prefixes = (
        "issue/",
        phase,
        "feature/",
        "fix/",
        "chore/",
        "codex/",
        "cursor/",
        "antigravity/",
        "dependabot/",
        "dev/",
    )
    return any(name.startswith(p) for p in prefixes)


# --- CLI helpers used by workflow ---

def cmd_should_request(argv: list[str]) -> int:
    # stdin: JSON {comments, head_sha, fast_gate_ok}
    data = json.load(sys.stdin)
    ok, reason = should_request_bugbot(
        comments=data.get("comments") or [],
        head_sha=data["head_sha"],
        fast_gate_ok=bool(data.get("fast_gate_ok")),
    )
    json.dump({"request": ok, "reason": reason}, sys.stdout)
    print()
    return 0 if ok else 2


def cmd_fast_gate(argv: list[str]) -> int:
    data = json.load(sys.stdin)
    status, detail = fast_gate_status(
        data.get("checks") or [],
        parse_required_checks(data.get("required") or ""),
    )
    json.dump({"status": status, "detail": detail}, sys.stdout)
    print()
    return 0 if status == "success" else 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: packager_logic.py <should-request|fast-gate|build-comment>", file=sys.stderr)
        return 2
    cmd = argv[1]
    if cmd == "should-request":
        return cmd_should_request(argv[2:])
    if cmd == "fast-gate":
        return cmd_fast_gate(argv[2:])
    if cmd == "build-comment":
        command = argv[2] if len(argv) > 2 else DEFAULT_BUGBOT_COMMAND
        sha = argv[3] if len(argv) > 3 else ""
        sys.stdout.write(build_bugbot_comment(command, sha))
        return 0
    if cmd == "marker":
        print(marker_for(argv[2]))
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
