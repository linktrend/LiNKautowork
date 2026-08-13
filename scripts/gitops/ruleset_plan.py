#!/usr/bin/env python3
"""Create a dry-run, reversible branch-ruleset plan.

The plan is data only.  It never calls GitHub and has no apply operation.  A
principal can review the exact required contexts before a separate authorized
operator performs any live ruleset change.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CONTEXTS = {
    "development": [
        "Linktrend Phase Ready",
        "Linktrend Fast Gate",
        "Cursor Bugbot",
        "Linktrend Full Suite",
    ],
    "staging": ["Linktrend Staging Gate"],
    "main": ["Linktrend Release Gate"],
}


def build_plan(branches: list[str], *, operation: str = "plan") -> dict[str, Any]:
    unknown = sorted(set(branches) - set(CONTEXTS))
    if unknown:
        raise ValueError(f"unsupported protected branch: {', '.join(unknown)}")
    selected = branches or ["development", "staging", "main"]
    rules = [
        {
            "branch": branch,
            "requiredStatusChecks": list(CONTEXTS[branch]),
            "requirePullRequest": True,
            "requireConversationResolution": True,
        }
        for branch in selected
    ]
    return {
        "schemaVersion": 1,
        "operation": operation,
        "dryRun": True,
        "reversible": True,
        "applied": False,
        "provider": "github",
        "rules": rules,
        "rollback": {
            "dryRun": True,
            "applied": False,
            "action": "restore prior captured ruleset snapshot",
            "requiresPrincipalApproval": True,
        },
        "prohibitedActions": ["apply-ruleset", "mutate-branch-protection"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", action="append", dest="branches", choices=sorted(CONTEXTS))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = build_plan(args.branches or [], operation="rollback-plan" if args.rollback else "plan")
    except ValueError as exc:
        parser.error(str(exc))
    rendered = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.is_symlink():
            raise SystemExit("refuse symlink output")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
