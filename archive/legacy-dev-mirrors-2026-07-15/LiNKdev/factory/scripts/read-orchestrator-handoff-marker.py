#!/usr/bin/env python3
"""Emit GITHUB_ENV lines from .linkdev/handoff/orchestrator-wave-ready.json."""
import json
import sys
from pathlib import Path


def main() -> None:
    path = Path(sys.argv[1])
    data = json.loads(path.read_text())
    for key in ("program_id", "branch", "head_sha", "created_at"):
        if key not in data or not str(data[key]).strip():
            raise SystemExit(f"missing required field: {key}")
    print(f"PROGRAM_ID={data['program_id']}")
    print(f"HANDOFF_BRANCH={data['branch']}")
    print(f"HANDOFF_SHA={data['head_sha']}")
    pr = data.get("pr_number")
    if pr:
        print(f"PR_NUMBER={int(pr)}")


if __name__ == "__main__":
    main()
