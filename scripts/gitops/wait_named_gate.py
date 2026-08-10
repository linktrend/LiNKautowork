#!/usr/bin/env python3
"""Wait until named gate checks are SUCCESS on a PR head. Missing ≠ success."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from typing import Any

# Reuse packager fast-gate logic
sys.path.insert(0, str(__file__).rsplit("/", 1)[0])
from packager_logic import fast_gate_status, parse_required_checks  # noqa: E402


def gh_pr_checks(pr: str) -> list[dict[str, Any]]:
    proc = subprocess.run(
        ["gh", "pr", "checks", pr, "--json", "name,state,completedAt,startedAt"],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "gh pr checks failed")
    return json.loads(proc.stdout or "[]")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pr", required=True)
    ap.add_argument("--required", required=True)
    ap.add_argument("--timeout-seconds", type=int, default=900)
    ap.add_argument("--poll-seconds", type=int, default=20)
    ap.add_argument("--report-file", default="")
    args = ap.parse_args()

    deadline = time.time() + args.timeout_seconds
    last: dict[str, Any] = {}
    while True:
        try:
            checks = gh_pr_checks(args.pr)
            status, detail = fast_gate_status(checks, parse_required_checks(args.required))
        except Exception as e:  # noqa: BLE001 — surface and retry
            status, detail = "pending", str(e)
            checks = []
        last = {"status": status, "detail": detail, "checks": checks}
        if args.report_file:
            with open(args.report_file, "w", encoding="utf-8") as f:
                json.dump(last, f, indent=2)
                f.write("\n")
        print(f"gate status={status} detail={detail}")
        if status == "success":
            return 0
        if status == "failed":
            return 1
        if time.time() >= deadline:
            print("timeout waiting for named gate", file=sys.stderr)
            return 2
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
