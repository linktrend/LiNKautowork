#!/usr/bin/env python3
"""CLI for exact-content gate receipt identities and verification.

Examples:
  gate_receipt.py identity --repo . --dependency package-lock.json
  gate_receipt.py write --input result.json --output build/full-receipt.json
  gate_receipt.py verify --receipt build/full-receipt.json --repo . \
      --dependency package-lock.json --gate full-gate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Direct script execution puts scripts/gitops, rather than scripts/, on
# sys.path.  Keep the CLI usable both as a script and as a module.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gitops.coordinator.receipts import (
    ReceiptError,
    compute_candidate_identity,
    load_json,
    verify_receipt,
    write_receipt,
)


def _json_output(value: Any) -> None:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    elif hasattr(value, "__dict__"):
        value = vars(value)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create and verify deterministic exact-content gate receipts."
    )
    commands = parser.add_subparsers(dest="operation", required=True)

    identity = commands.add_parser("identity", help="compute a candidate identity from a Git checkout")
    identity.add_argument("--repo", required=True, type=Path, help="Git checkout path")
    identity.add_argument(
        "--dependency", "--dependency-file", dest="dependencies", action="append", default=[],
        help="repository-relative dependency file; repeat for multiple files",
    )
    identity.add_argument("--profile", choices=("fast", "full", "release"), default="full")

    write = commands.add_parser("write", help="atomically write a completed passed receipt")
    write.add_argument("--input", "--result", dest="input_path", required=True, type=Path)
    write.add_argument("--output", required=True, type=Path)

    verify = commands.add_parser("verify", help="verify a receipt against a fresh candidate identity")
    verify.add_argument("--receipt", required=True, type=Path)
    verify.add_argument("--identity", type=Path, help="precomputed candidate identity JSON")
    verify.add_argument("--repo", type=Path, help="Git checkout path when --identity is omitted")
    verify.add_argument(
        "--dependency", "--dependency-file", dest="dependencies", action="append", default=[],
        help="repository-relative dependency file; repeat for multiple files",
    )
    verify.add_argument("--profile", choices=("fast", "full", "release"), default="full")
    verify.add_argument("--gate", required=True, help="required gate id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.operation == "identity":
            _json_output(compute_candidate_identity(args.repo, args.dependencies, args.profile))
            return 0
        if args.operation == "write":
            receipt = write_receipt(load_json(args.input_path), args.output)
            _json_output(receipt)
            return 0
        if args.operation == "verify":
            receipt = load_json(args.receipt)
            if args.identity:
                identity = load_json(args.identity)
            else:
                if args.repo is None:
                    raise ReceiptError("invalid_path", "--repo or --identity is required")
                identity = compute_candidate_identity(args.repo, args.dependencies, args.profile)
            verdict = verify_receipt(receipt, identity, args.gate)
            _json_output(
                {
                    "accepted": verdict.accepted,
                    "code": verdict.code,
                    "message": verdict.message,
                }
            )
            return 0 if verdict.accepted else 1
    except ReceiptError as error:
        _json_output({"accepted": False, "code": error.code, "message": str(error)})
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
