#!/usr/bin/env python3
"""Fail-closed identity verifier for a reconciled-tree Fast dispatch.

This is deliberately not a general manual Fast trigger.  It admits only the
already-installed, clean ``development`` checkout identified by the caller's
repository, commit, tree, package version, and canonical installed-state
digest.  The workflow then runs the normal argv-only Fast profile without any
write credential or cache authority.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    from .verify_reconciled_tree import state_digest
except ImportError:  # Direct script invocation from a managed consumer.
    from verify_reconciled_tree import state_digest


def fail(code: str) -> None:
    raise SystemExit(f"reconciled_fast_{code}")


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--actual-repository", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-tree", required=True)
    parser.add_argument("--package-version", required=True)
    parser.add_argument("--installed-state-digest", required=True)
    args = parser.parse_args(argv)
    root = args.repo.resolve()
    if args.expected_repository != args.actual_repository:
        fail("repository_mismatch")
    if args.ref != "development":
        fail("ref_invalid")
    if git(root, "status", "--porcelain"):
        fail("managed_drift")
    if git(root, "branch", "--show-current") != "development":
        fail("ref_mismatch")
    if git(root, "rev-parse", "HEAD") != args.expected_commit:
        fail("commit_mismatch")
    if git(root, "rev-parse", "HEAD^{tree}") != args.expected_tree:
        fail("tree_mismatch")
    try:
        state = json.loads((root / ".ide-development" / "installed-state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        fail("installed_state_invalid")
    if state.get("packageVersion") != args.package_version:
        fail("package_version_mismatch")
    if state_digest(state) != args.installed_state_digest:
        fail("manifest_digest_mismatch")
    print(json.dumps({"accepted": True, "kind": "reconciled-fast", "ref": args.ref, "tree": args.expected_tree}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
