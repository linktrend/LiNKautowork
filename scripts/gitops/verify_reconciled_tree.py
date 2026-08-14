#!/usr/bin/env python3
"""Fail closed verification for a reconciled, already-installed delivery tree.

This is deliberately a *canary-only* verifier.  It emits no promotion marker
and cannot be used as a Full Suite receipt.  It exists for the one legitimate
case where target-history reconciliation has already made the exact managed
installation part of ``development`` and therefore leaves no truthful Phase
diff to seal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def fail(code: str) -> None:
    raise SystemExit(f"reconciled_canary_{code}")


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def state_digest(state: dict[str, object]) -> str:
    # installedAt is observational, never package identity.
    identity = {key: value for key, value in state.items() if key != "installedAt"}
    return "sha256:" + hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-tree", required=True)
    parser.add_argument("--package-version", required=True)
    parser.add_argument("--installed-state-digest", required=True)
    parser.add_argument("--checks-json", required=True, type=Path)
    parser.add_argument("--staging-tree", required=True)
    parser.add_argument("--main-tree", required=True)
    args = parser.parse_args(argv)
    root = args.repo.resolve()
    # A reconciled receipt is meaningful only for the exact installed tree; a
    # managed edit in the checkout is never an acceptable substitute.
    if git(root, "status", "--porcelain"):
        fail("managed_drift")
    if git(root, "rev-parse", "HEAD") != args.expected_commit:
        fail("commit_mismatch")
    if git(root, "rev-parse", "HEAD^{tree}") != args.expected_tree:
        fail("tree_mismatch")
    state_path = root / ".ide-development" / "installed-state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        fail("installed_state_invalid")
    if state.get("packageVersion") != args.package_version:
        fail("package_version_mismatch")
    if state_digest(state) != args.installed_state_digest:
        fail("manifest_digest_mismatch")
    try:
        checks = json.loads(args.checks_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        fail("checks_invalid")
    if not isinstance(checks, dict) or not all(checks.get(name) == "success" for name in ("fast", "ci", "security")):
        fail("checks_not_successful")
    if args.staging_tree != args.expected_tree or args.main_tree != args.expected_tree:
        fail("promotion_not_tree_neutral")
    print(json.dumps({"accepted": True, "kind": "reconciled-canary", "promotable": False, "tree": args.expected_tree}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
