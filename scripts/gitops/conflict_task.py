#!/usr/bin/env python3
"""Thin shim: promotion conflict_blocked tasks delegate to repair_task.

Kept for promote-script and historical caller compatibility.
New code should call repair_task.py directly with --failure-type promotion_conflict.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import repair_task as rt  # noqa: E402

MAX_ATTEMPTS = rt.MAX_ATTEMPTS
LABEL = "linktrend-conflict-blocked"  # legacy; repair uses linktrend-repair*


def task_key(repo: str, stage: str, source_sha: str, target_sha: str) -> str:
    """Legacy key — prefer repair_task.failure_id for new work.

    Promote scripts now pass stable branch identity via repair_task; this helper
    remains for any external callers that still hash by SHAs.
    """
    # Map into promotion_conflict identity (repo+type+pr+workflow+check+branch).
    # Prefer stage as branch key so tip advances update one task.
    return rt.failure_id(
        repo,
        "promotion_conflict",
        pr="",
        workflow="",
        check="",
        branch=f"promote/{stage}",
    )


def get_backend(repo: str):
    return rt.get_backend(repo)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    up = sub.add_parser("upsert")
    up.add_argument("--repo", required=True)
    up.add_argument("--stage", required=True)
    up.add_argument("--source-branch", required=True)
    up.add_argument("--target-branch", required=True)
    up.add_argument("--source-sha", required=True)
    up.add_argument("--target-sha", required=True)
    up.add_argument("--status", default="conflict_blocked")
    up.add_argument("--next-action", required=True)
    up.add_argument("--promote-pr", default="")
    up.add_argument("--increment-attempt", action="store_true")
    rs = sub.add_parser("resolve")
    rs.add_argument("--repo", required=True)
    rs.add_argument("--id", required=True)
    sh = sub.add_parser("show")
    sh.add_argument("--repo", required=True)
    sh.add_argument("--id", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "upsert":
        # Delegate to repair_task (promotion_conflict). Do not increment on upsert;
        # --increment-attempt maps to a follow-up dispatch-attempt for compat.
        fid = rt.failure_id(
            args.repo,
            "promotion_conflict",
            pr=args.promote_pr,
            workflow="",
            check="",
            branch=f"{args.source_branch}->{args.target_branch}",
        )
        task: dict[str, Any] = {
            "failureId": fid,
            "id": fid,
            "repository": args.repo,
            "failureType": "promotion_conflict",
            "prNumber": args.promote_pr,
            "pr": args.promote_pr,
            "branch": f"{args.source_branch}->{args.target_branch}",
            "headSha": args.source_sha,
            "baseSha": args.target_sha,
            "severity": "ordinary",
            "attemptCount": 0,
            "maxAttempts": rt.MAX_ATTEMPTS,
            "repairStatus": "recorded",
            "evidence": {},
            "nextAction": args.next_action,
            "lisaDispatchState": "pending",
            "resolutionState": "open",
            "stage": args.stage,
            "sourceBranch": args.source_branch,
            "targetBranch": args.target_branch,
            "sourceSha": args.source_sha,
            "targetSha": args.target_sha,
            "promotePr": args.promote_pr,
            "status": args.status,
        }
        out = rt.upsert_task(task, increment=False)
        if args.increment_attempt:
            out = get_backend(args.repo).dispatch_attempt(fid) or {}
        print(json.dumps(out, indent=2))
        return 0

    backend = get_backend(args.repo)
    if args.cmd == "resolve":
        out = backend.resolve(args.id)
        print(json.dumps(out or {}, indent=2))
        return 0 if out else 1
    if args.cmd == "show":
        out = backend.get(args.id)
        print(json.dumps(out or {}, indent=2))
        return 0 if out else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
