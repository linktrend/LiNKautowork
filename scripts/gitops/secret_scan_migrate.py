#!/usr/bin/env python3
"""Identify likely synthetic secret-scan fixtures. Never writes an approval."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from secret_scan import identify_synthetic_candidates  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    args = parser.parse_args(argv)
    candidates = identify_synthetic_candidates(Path(args.repo))
    print(
        json.dumps(
            {
                "approved": False,
                "wroteApproval": False,
                "candidates": candidates,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
