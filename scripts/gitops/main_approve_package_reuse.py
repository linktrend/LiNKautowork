#!/usr/bin/env python3
"""Validate existing main promote PR reuse for promote_main.sh package mode.

Fail closed: do not report reuse based only on source/target marker fields.
Requires open same-repo PR, base main, expected promote branch, valid marker,
and live head == marker candidateHead.

Stdout JSON:
  {"action":"reuse","pr":N}
  {"action":"repackage","pr":N,"reason":"..."}
  {"action":"create"}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
PROMOTE_BRANCH_RE = re.compile(r"^promote/main/([0-9a-f]{12})$")
MARKER_RE = re.compile(r"<!--\s*linktrend-promote:\s*(\{.*?\})\s*-->", re.S)


def normalize_sha(value: Any) -> str | None:
    s = str(value or "").strip().lower()
    return s if SHA40_RE.match(s) else None


def parse_marker(body: str) -> tuple[dict[str, Any] | None, str]:
    m = MARKER_RE.search(body or "")
    if not m:
        return None, "marker_missing"
    try:
        meta = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None, "marker_json_invalid"
    if not isinstance(meta, dict):
        return None, "marker_not_object"
    try:
        if int(meta.get("schemaVersion") or 0) != 1:
            return None, "marker_schema_unsupported"
    except (TypeError, ValueError):
        return None, "marker_schema_unsupported"
    if meta.get("stage") != "main":
        return None, "marker_stage_not_main"
    if meta.get("sourceBranch") != "staging":
        return None, "marker_source_branch_not_staging"
    if meta.get("targetBranch") != "main":
        return None, "marker_target_branch_not_main"
    source = normalize_sha(meta.get("sourceSha"))
    target = normalize_sha(meta.get("targetSha"))
    candidate = normalize_sha(meta.get("candidateHead"))
    if not source:
        return None, "marker_source_sha_invalid"
    if not target:
        return None, "marker_target_sha_invalid"
    if not candidate:
        return None, "marker_candidate_sha_invalid"
    branch = str(meta.get("promoteBranch") or "").strip()
    bm = PROMOTE_BRANCH_RE.match(branch)
    if not bm:
        return None, "marker_promote_branch_invalid"
    if bm.group(1) != source[:12]:
        return None, "marker_promote_branch_prefix_mismatch"
    return {
        "schemaVersion": 1,
        "stage": "main",
        "sourceBranch": "staging",
        "targetBranch": "main",
        "sourceSha": source,
        "targetSha": target,
        "candidateHead": candidate,
        "promoteBranch": branch,
    }, ""


def head_repo_name(pr: dict[str, Any]) -> str:
    hr = pr.get("headRepository")
    if isinstance(hr, dict):
        nwo = hr.get("nameWithOwner")
        if nwo:
            return str(nwo)
        owner = hr.get("owner") if isinstance(hr.get("owner"), dict) else {}
        login = owner.get("login") if isinstance(owner, dict) else None
        name = hr.get("name")
        if login and name:
            return f"{login}/{name}"
    return str(pr.get("headRepositoryNameWithOwner") or "")


def evaluate_reuse(
    *,
    prs: list[dict[str, Any]],
    expected_source: str,
    expected_target: str,
    expected_branch: str,
    repository: str,
) -> dict[str, Any]:
    src = normalize_sha(expected_source)
    tgt = normalize_sha(expected_target)
    if not src or not tgt:
        return {"action": "repackage", "pr": None, "reason": "expected_sha_invalid"}
    if not PROMOTE_BRANCH_RE.match(expected_branch):
        return {"action": "repackage", "pr": None, "reason": "expected_branch_invalid"}
    if expected_branch != f"promote/main/{src[:12]}":
        return {"action": "repackage", "pr": None, "reason": "expected_branch_prefix_mismatch"}

    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    weak: list[tuple[int, str]] = []
    for pr in prs:
        meta, _reason = parse_marker(str(pr.get("body") or ""))
        if not meta:
            continue
        if meta["sourceSha"] != src or meta["targetSha"] != tgt:
            continue
        # source/target matched — must fully validate or fail closed
        pr_number = int(pr.get("number") or 0)
        state = str(pr.get("state") or "").upper()
        base = str(pr.get("baseRefName") or "")
        head_branch = str(pr.get("headRefName") or "")
        head_sha = normalize_sha(pr.get("headRefOid"))
        is_cross = bool(pr.get("isCrossRepository"))
        head_repo = head_repo_name(pr)

        if state and state not in {"OPEN", ""}:
            weak.append((pr_number, "pr_not_open"))
            continue
        if base and base != "main":
            weak.append((pr_number, "base_not_main"))
            continue
        if is_cross:
            weak.append((pr_number, "cross_repository_head"))
            continue
        if head_repo and head_repo.lower() != repository.lower():
            weak.append((pr_number, "head_repository_mismatch"))
            continue
        if head_branch != expected_branch:
            weak.append((pr_number, "head_branch_mismatch"))
            continue
        if meta["promoteBranch"] != expected_branch:
            weak.append((pr_number, "marker_promote_branch_mismatch"))
            continue
        if not head_sha or head_sha != meta["candidateHead"]:
            weak.append((pr_number, "candidate_head_drift"))
            continue
        matches.append((pr, meta))

    if len(matches) > 1:
        return {
            "action": "repackage",
            "pr": None,
            "reason": "ambiguous_duplicate_packages",
            "prs": [int(p["number"]) for p, _ in matches],
        }
    if len(matches) == 1:
        pr, _meta = matches[0]
        return {"action": "reuse", "pr": int(pr["number"])}
    if weak:
        pr_number, reason = weak[0]
        return {"action": "repackage", "pr": pr_number, "reason": reason}
    return {"action": "create"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--expected-target", required=True)
    ap.add_argument("--expected-branch", required=True)
    ap.add_argument("--repository", required=True)
    ap.add_argument(
        "--prs-json",
        default="",
        help="Path to gh pr list JSON; default stdin",
    )
    args = ap.parse_args(argv)
    raw = Path(args.prs_json).read_text(encoding="utf-8") if args.prs_json else sys.stdin.read()
    prs = json.loads(raw or "[]")
    if not isinstance(prs, list):
        print(json.dumps({"action": "repackage", "pr": None, "reason": "prs_json_invalid"}))
        return 2
    out = evaluate_reuse(
        prs=prs,
        expected_source=args.expected_source,
        expected_target=args.expected_target,
        expected_branch=args.expected_branch,
        repository=args.repository,
    )
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
