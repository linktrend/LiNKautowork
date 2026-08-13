#!/usr/bin/env python3
"""Safe cleanup controls for merged/abandoned branches and completed repair records.

Default posture is dry-run / plan-only. Never invent authority to close or delete
live GitHub PRs, issues, or remote branches — that remains gated by
cleanup-merged-branches.sh evidence (MERGED / abandoned) or explicit file-backend
completed-repair --apply after plan review.

Preserve policy (Issue #51 / #53): committed defaults in cleanup_preserve.defaults.json,
optionally overlaid by CLEANUP_PRESERVE_JSON path or LINKTREND_CLEANUP_PRESERVE_FILE.
An overlay with ``"defaults": false`` disables the committed defaults list entirely
(local ``.linktrend/cleanup-preserve.json`` included).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SCHEMA_VERSION = 1
ISSUE_BRANCH_RE = re.compile(r"^issue/(\d+)(?:-|$)")
# owner/name — same shape used by repair_task / cleanup_stale_records callers.
REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

_HERE = Path(__file__).resolve().parent
DEFAULT_PRESERVE_PATH = _HERE / "cleanup_preserve.defaults.json"

PrStateFn = Callable[[str], str]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_valid_repo_slug(repo: str) -> bool:
    """True when ``repo`` is a non-empty owner/name slug suitable for ``gh --repo``."""
    slug = (repo or "").strip()
    return bool(slug and REPO_SLUG_RE.fullmatch(slug))


def normalize_caller_repo(repo: str) -> tuple[str | None, str]:
    """Validate caller-supplied repository for PR-evidence authorization.

    Returns ``(slug, "explicit")`` or ``(None, reason)`` where reason is
    ``repo_missing`` / ``repo_invalid``. Empty or invalid values must not fall
    through to implicit ``gh`` or per-row repository when authorizing deletes.
    """
    slug = (repo or "").strip()
    if not slug:
        return None, "repo_missing"
    if not REPO_SLUG_RE.fullmatch(slug):
        return None, "repo_invalid"
    return slug, "explicit"


def _read_policy_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "schemaVersion" in data and int(data.get("schemaVersion") or 0) != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported preserve schemaVersion={data.get('schemaVersion')!r}; "
            f"expected {SCHEMA_VERSION}"
        )
    return data


def load_preserve_policy(path: Path | None = None) -> dict[str, Any]:
    """Load preserve policy; fail closed on missing/invalid schema.

    Merge order (later overlays win for additive sets):
      1. cleanup_preserve.defaults.json (committed) — skipped when any overlay
         sets ``"defaults": false``
      2. LINKTREND_CLEANUP_PRESERVE_FILE or --policy path
      3. .linktrend/cleanup-preserve.json (local overlay; gitignored)
      4. LINKTREND_CLEANUP_PRESERVE env (comma-separated exact branch names)
    """
    issues: set[int] = set()
    prs: set[int] = set()
    exact: set[str] = set()
    sources: list[str] = []

    def _merge(data: dict[str, Any], src: str) -> None:
        nonlocal issues, prs, exact
        for key_a, key_b in (
            ("preserveIssueNumbers", "issueNumbers"),
            ("preservePrNumbers", "prNumbers"),
            ("preserveBranchExact", "branches"),
        ):
            raw = data.get(key_a)
            if raw is None:
                raw = data.get(key_b)
            if raw is None:
                continue
            if key_a == "preserveIssueNumbers":
                issues |= {int(x) for x in raw}
            elif key_a == "preservePrNumbers":
                prs |= {int(x) for x in raw}
            else:
                exact |= {str(x) for x in raw}
        sources.append(src)

    # Resolve explicit path / env file first (needed to detect defaults:false).
    candidate = path
    if candidate is None:
        env = (os.environ.get("LINKTREND_CLEANUP_PRESERVE_FILE") or "").strip()
        if env:
            candidate = Path(env)

    overlays: list[tuple[dict[str, Any], str]] = []
    defaults_disabled = False

    if candidate is not None:
        if not candidate.is_file():
            raise FileNotFoundError(f"preserve policy missing: {candidate}")
        data = _read_policy_file(candidate)
        overlays.append((data, str(candidate)))
        if data.get("defaults") is False:
            defaults_disabled = True

    local = Path(".linktrend/cleanup-preserve.json")
    if local.is_file():
        local_data = _read_policy_file(local)
        overlays.append((local_data, str(local)))
        if local_data.get("defaults") is False:
            defaults_disabled = True

    # 1) Committed defaults — omitted entirely when any overlay disables them.
    if not defaults_disabled and DEFAULT_PRESERVE_PATH.is_file():
        defaults = _read_policy_file(DEFAULT_PRESERVE_PATH)
        if defaults.get("defaults") is not False:
            _merge(defaults, str(DEFAULT_PRESERVE_PATH))

    # 2–3) Explicit + local overlays (entries always apply)
    for data, src in overlays:
        _merge(data, src)

    # 4) Env branch list
    env_branches = (os.environ.get("LINKTREND_CLEANUP_PRESERVE") or "").strip()
    if env_branches:
        exact |= {b.strip() for b in env_branches.split(",") if b.strip()}
        sources.append("env:LINKTREND_CLEANUP_PRESERVE")

    if not sources and not DEFAULT_PRESERVE_PATH.is_file():
        raise FileNotFoundError(f"preserve policy missing: {DEFAULT_PRESERVE_PATH}")

    return {
        "schemaVersion": SCHEMA_VERSION,
        "path": sources[0] if sources else str(DEFAULT_PRESERVE_PATH),
        "sources": sources,
        "defaultsDisabled": defaults_disabled,
        "preserveIssueNumbers": sorted(issues),
        "preservePrNumbers": sorted(prs),
        "preserveBranchExact": sorted(exact),
        "issue_set": issues,
        "pr_set": prs,
        "exact_set": exact,
    }


def issue_number_from_branch(branch: str) -> int | None:
    m = ISSUE_BRANCH_RE.match((branch or "").strip())
    if not m:
        return None
    return int(m.group(1))


def preserve_reason(
    branch: str,
    *,
    policy: dict[str, Any] | None = None,
    pr_number: int | None = None,
) -> str | None:
    """Return KEEP reason if branch/PR is explicitly preserved; else None."""
    pol = policy or load_preserve_policy()
    name = (branch or "").strip()
    if not name:
        return None
    if name in pol["exact_set"]:
        return "preserve_branch_exact"
    issue_n = issue_number_from_branch(name)
    if issue_n is not None and issue_n in pol["issue_set"]:
        return f"preserve_issue_number:{issue_n}"
    if pr_number is not None and int(pr_number) in pol["pr_set"]:
        return f"preserve_pr_number:{int(pr_number)}"
    return None


def classify_branch_decision(
    branch: str,
    *,
    evidence: str,
    pr_number: int | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure decision helper used by tests and planners.

    evidence: OPEN | MERGED | ABANDONED | NONE (cleanup-merged-branches.sh vocabulary)
    """
    pol = policy or load_preserve_policy()
    reason = preserve_reason(branch, policy=pol, pr_number=pr_number)
    if reason:
        return {
            "branch": branch,
            "decision": "KEEP",
            "reason": reason,
            "evidence": evidence,
            "authorized_delete": False,
        }
    if evidence == "OPEN":
        return {
            "branch": branch,
            "decision": "KEEP",
            "reason": f"open_pr:{pr_number or ''}".rstrip(":"),
            "evidence": evidence,
            "authorized_delete": False,
        }
    if evidence in ("MERGED", "ABANDONED"):
        return {
            "branch": branch,
            "decision": "ELIGIBLE",
            "reason": f"{evidence.lower()}_pr_evidence",
            "evidence": evidence,
            "authorized_delete": True,
        }
    return {
        "branch": branch,
        "decision": "KEEP",
        "reason": "no_merged_or_abandoned_pr_evidence",
        "evidence": evidence,
        "authorized_delete": False,
    }


def _gh_json(args: list[str]) -> Any:
    try:
        out = subprocess.check_output(["gh", *args], text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    try:
        return json.loads(out or "null")
    except json.JSONDecodeError:
        return None


def default_pr_state(pr: str, *, repo: str = "") -> str:
    """Resolve PR state via ``gh pr view`` (OPEN|MERGED|CLOSED|NONE|UNKNOWN).

    Requires an explicit valid ``owner/name`` ``repo``. Empty/invalid repo returns
    ``UNKNOWN`` (fail closed) — never query implicit ``gh`` cwd/remote context,
    which can mis-authorize file deletes against the wrong repository.
    """
    if not pr or str(pr) in ("", "0", "null", "None"):
        return "NONE"
    repo_slug = (repo or "").strip()
    if not is_valid_repo_slug(repo_slug):
        return "UNKNOWN"
    args = [
        "pr",
        "view",
        str(pr),
        "--json",
        "number,state,mergedAt,headRefName",
        "--repo",
        repo_slug,
    ]
    data = _gh_json(args)
    if not isinstance(data, dict):
        return "UNKNOWN"
    if data.get("state") == "OPEN":
        return "OPEN"
    if data.get("state") == "MERGED" or data.get("mergedAt"):
        return "MERGED"
    if data.get("state") == "CLOSED":
        return "CLOSED"
    return "UNKNOWN"


def _owner_repo_from_github_url(url: str) -> str | None:
    """Parse owner/repo from a GitHub HTTPS or SSH remote URL; else None."""
    sanitized = (url or "").strip()
    owner_repo: str

    # Git's scp-like SSH syntax is not understood by urlsplit. Match the
    # complete, trusted host instead of accepting a github.com substring.
    scp_match = re.fullmatch(r"git@github\.com:(.+)", sanitized, re.IGNORECASE)
    if scp_match:
        owner_repo = scp_match.group(1)
    else:
        try:
            parsed = urlsplit(sanitized)
            port = parsed.port  # Force validation of malformed ports.
        except ValueError:
            return None
        if (
            parsed.scheme.lower() not in {"https", "ssh"}
            or (parsed.hostname or "").lower() != "github.com"
            or parsed.query
            or parsed.fragment
        ):
            return None
        if parsed.scheme.lower() == "https" and port not in {None, 443}:
            return None
        if parsed.scheme.lower() == "ssh" and port not in {None, 22}:
            return None
        owner_repo = parsed.path
    owner_repo = owner_repo.strip()
    if owner_repo.endswith(".git"):
        owner_repo = owner_repo[:-4]
    owner_repo = owner_repo.strip("/")
    if owner_repo.count("/") != 1 or " " in owner_repo:
        return None
    return owner_repo


def _remote_get_url_ok(cwd: Path, name: str) -> bool:
    """True when ``git remote get-url <name>`` succeeds in cwd."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", name],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return False
    return result.returncode == 0


def resolve_cleanup_repo(
    explicit: str = "",
    *,
    workdir: Path | None = None,
) -> tuple[str | None, str]:
    """Resolve owner/repo for cleanup preserve PR head lookups.

    Preference (deterministic, no silent ambiguity):
      1) explicit ``--repo`` / non-empty argument (authoritative)
      2) env ``GITHUB_REPOSITORY`` (authoritative)
      3) env ``GH_REPO`` (authoritative)
      4) if neither explicit nor env: when BOTH ``origin`` and ``upstream``
         remotes exist (get-url succeeds for both) → fail closed with
         ``ambiguous_origin_and_upstream`` immediately — do NOT call
         ``gh repo view`` and do NOT return an origin slug
      5) only if not ambiguous: ``gh repo view --json nameWithOwner``
      6) only if not ambiguous: validated ``origin`` remote URL → owner/repo
         (still reject if ``upstream`` appears at this stage)

    Explicit/env remain authoritative even when origin+upstream both exist.
    """
    cwd = workdir if workdir is not None else Path.cwd()

    explicit_slug = (explicit or "").strip()
    if explicit_slug:
        if "/" in explicit_slug and " " not in explicit_slug:
            return explicit_slug, "explicit"
        return None, "explicit_invalid"

    for key in ("GITHUB_REPOSITORY", "GH_REPO"):
        val = (os.environ.get(key) or "").strip()
        if val and "/" in val and " " not in val and "local/" not in val:
            return val, f"env:{key}"

    # Fail closed before any gh/origin guess when remotes are ambiguous.
    if _remote_get_url_ok(cwd, "origin") and _remote_get_url_ok(cwd, "upstream"):
        return None, "ambiguous_origin_and_upstream"

    try:
        out = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        out = None
    if out is not None and out.returncode == 0:
        name = (out.stdout or "").strip()
        if name.count("/") == 1 and " " not in name:
            return name, "gh_repo_view"

    try:
        origin = subprocess.run(
            ["git", "remote", "get-url", "--push", "origin"],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=False,
        )
        if origin.returncode != 0:
            origin = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(cwd),
                text=True,
                capture_output=True,
                check=False,
            )
    except (FileNotFoundError, OSError):
        return None, "missing_origin_remote"
    if origin.returncode != 0:
        return None, "missing_origin_remote"

    owner_repo = _owner_repo_from_github_url(origin.stdout or "")
    if not owner_repo:
        return None, "origin_not_github_or_unrecognized"

    # Belt-and-suspenders: reject if upstream appeared since the early check.
    if _remote_get_url_ok(cwd, "upstream"):
        return None, "ambiguous_origin_and_upstream"
    return owner_repo, "origin"


def _pr_head_ref(pr: str | int, *, repo: str = "") -> str | None:
    """Best-effort headRefName for a preserved PR in any resolvable state.

    Returns the non-empty ``headRefName`` for OPEN, CLOSED, or MERGED PRs.
    Returns None on gh failures, missing data, or empty head.
    Callers must treat None as fail-closed for preserve policy (do not
    silently drop unresolved preserve PRs).
    """
    args = ["pr", "view", str(pr), "--json", "number,state,headRefName"]
    if repo:
        args.extend(["--repo", repo])
    data = _gh_json(args)
    if not isinstance(data, dict):
        return None
    head = str(data.get("headRefName") or "").strip()
    return head or None


def export_preserve_for_shell(
    *,
    policy: dict[str, Any] | None = None,
    repo: str = "",
    repo_source: str = "",
    pr_head_fn: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    """JSON payload consumable by bash (cleanup-merged-branches.sh).

    ``branches`` = exact preserve names plus preserved-PR head refs (any
    resolvable state with a non-empty head: OPEN, CLOSED, or MERGED).
    ``prHeads`` = headRefName for preserved PRs with a resolvable head.
    Unresolved preserve PR numbers are collected in ``unresolvedPrNumbers``;
    ``preserveResolutionOk`` is True only when that list is empty.

    When ``repo_source`` is ``ambiguous_origin_and_upstream``, do not call the
    PR head resolver / implicit gh: all preserve PR numbers are unresolved,
    ``prHeads`` is empty, ``preserveResolutionOk`` is False, and ``repo`` is
    cleared. Exact preserve branch names from policy still appear in ``branches``.
    """
    pol = policy or load_preserve_policy()
    exact = sorted(str(x) for x in pol["exact_set"])
    issue_numbers = sorted(int(x) for x in pol["issue_set"])
    pr_numbers = sorted(int(x) for x in pol["pr_set"])
    repo_slug = (repo or "").strip()
    source = (repo_source or "").strip()

    # Ambiguous remotes: fail closed — never guess via empty-repo implicit gh.
    if source == "ambiguous_origin_and_upstream":
        return {
            "branches": list(exact),
            "issueNumbers": issue_numbers,
            "prHeads": [],
            "prNumbers": pr_numbers,
            "unresolvedPrNumbers": list(pr_numbers),
            "preserveResolutionOk": False,
            "repo": "",
            "repoSource": "ambiguous_origin_and_upstream",
            "sources": list(pol.get("sources") or []),
            "defaultsDisabled": bool(pol.get("defaultsDisabled")),
        }

    pr_heads: list[str] = []
    unresolved: list[int] = []

    # Prefer a deterministic --repo when available; still attempt head lookup
    # without a slug (gh cwd context) rather than bulk-failing before any call.
    # Each preservePrNumber that cannot resolve a non-empty head is unresolved
    # (fail-closed — never silently dropped).
    resolver = pr_head_fn or (lambda p: _pr_head_ref(p, repo=repo_slug))
    for n in pr_numbers:
        try:
            head = resolver(str(n))
        except Exception:  # noqa: BLE001 — treat resolver failures as unresolved
            head = None
        if head:
            pr_heads.append(head)
        else:
            unresolved.append(n)

    unresolved = sorted(unresolved)
    # Dedupe while preserving order: exact first, then resolved heads.
    branches: list[str] = []
    seen: set[str] = set()
    for name in exact + pr_heads:
        if name and name not in seen:
            seen.add(name)
            branches.append(name)
    return {
        "branches": branches,
        "issueNumbers": issue_numbers,
        "prHeads": pr_heads,
        "prNumbers": pr_numbers,
        "unresolvedPrNumbers": unresolved,
        "preserveResolutionOk": not unresolved,
        "repo": repo_slug,
        "repoSource": source,
        "sources": list(pol.get("sources") or []),
        "defaultsDisabled": bool(pol.get("defaultsDisabled")),
    }


def list_completed_file_tasks(root: Path) -> list[dict[str, Any]]:
    """List resolved repair task JSON files under a file-backend root."""
    out: list[dict[str, Any]] = []
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*.json")):
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if task.get("resolutionState") != "resolved":
            continue
        pr_raw = task.get("prNumber") if task.get("prNumber") is not None else task.get("pr")
        out.append(
            {
                "failureId": task.get("failureId") or task.get("id") or path.stem,
                "path": str(path),
                "repository": task.get("repository") or "",
                "failureType": task.get("failureType") or "",
                "branch": task.get("branch") or "",
                "updatedAt": task.get("updatedAt") or "",
                "issueNumber": task.get("issueNumber"),
                "prNumber": pr_raw,
            }
        )
    return out


def classify_file_repair(
    row: dict[str, Any],
    *,
    policy: dict[str, Any],
    pr_state_fn: PrStateFn | None = None,
    repo: str = "",
) -> dict[str, Any]:
    """Classify one resolved file-backend row for KEEP vs delete authorization.

    Mirrors ``cleanup_stale_records.classify_repair`` keep rules without importing
    that module (circular risk). Injectable ``pr_state_fn(pr) -> str`` for tests.

    Caller-supplied ``repo`` is authoritative for linked-PR evidence. Per-row
    ``repository`` is never used as a silent fallback for authorization queries.
    Missing/invalid caller repo fails closed (KEEP, not authorized).
    """
    issue_n = row.get("issueNumber")
    branch = str(row.get("branch") or "")
    pr_raw = row.get("prNumber") if row.get("prNumber") is not None else row.get("pr")
    pr = str(pr_raw) if pr_raw is not None else ""
    # Authoritative caller repo only — no per-row / implicit gh fallback.
    repo_name, repo_reason = normalize_caller_repo(repo)

    result: dict[str, Any] = {
        "failureId": row.get("failureId"),
        "path": row.get("path"),
        "branch": branch,
        "issueNumber": issue_n,
        "pr": pr,
    }

    if issue_n is not None and str(issue_n).isdigit() and int(issue_n) in policy["issue_set"]:
        result.update(
            {
                "decision": "KEEP",
                "reason": f"preserve_issue_number:{int(issue_n)}",
                "authorized": False,
            }
        )
        return result

    branch_issue = issue_number_from_branch(branch)
    if branch_issue is not None and branch_issue in policy["issue_set"]:
        result.update(
            {
                "decision": "KEEP",
                "reason": f"preserve_issue_number:{branch_issue}",
                "authorized": False,
            }
        )
        return result

    pr_num = int(pr) if pr.isdigit() else None
    reason = preserve_reason(branch, policy=policy, pr_number=pr_num)
    if reason:
        result.update({"decision": "KEEP", "reason": reason, "authorized": False})
        return result

    if repo_name is None:
        # Fail closed before any PR evidence / authorize path.
        result.update(
            {
                "decision": "KEEP",
                "reason": f"caller_repo_{repo_reason}",
                "authorized": False,
            }
        )
        return result

    if pr_state_fn is not None:
        state = pr_state_fn(pr)
    else:
        state = default_pr_state(pr, repo=repo_name) if pr else "NONE"
    result["prState"] = state

    if state == "OPEN":
        result.update(
            {
                "decision": "KEEP",
                "reason": f"open_pr:{pr}",
                "authorized": False,
            }
        )
        return result

    if state == "UNKNOWN":
        # Fail closed: do not authorize delete when PR state cannot be resolved.
        result.update(
            {
                "decision": "KEEP",
                "reason": "pr_state_unknown",
                "authorized": False,
            }
        )
        return result

    # MERGED / CLOSED / NONE (and not preserved) → authorize file delete only.
    result.update(
        {
            "decision": "WOULD_DELETE_FILE",
            "reason": f"resolved_file_pr_{state.lower()}",
            "authorized": True,
        }
    )
    return result


def plan_completed_repair_cleanup(
    root: Path,
    *,
    apply: bool = False,
    policy: dict[str, Any] | None = None,
    pr_state_fn: PrStateFn | None = None,
    repo: str = "",
) -> dict[str, Any]:
    """Plan (default) or apply file-backend cleanup of completed repair records.

    Honors preserve policy and OPEN linked PRs (same keep rules as
    cleanup_stale_records.classify_repair). GitHub Issue records are never
    closed/deleted here. Apply removes only authorized local resolved JSON files.

    ``repo`` (caller ``owner/name``) is required and authoritative for linked-PR
    evidence used to authorize file deletes. Missing/invalid ``repo`` fails
    closed: every row stays KEEP / not authorized; apply never unlinks.
    """
    pol = policy or load_preserve_policy()
    completed = list_completed_file_tasks(root)
    repo_slug, repo_reason = normalize_caller_repo(repo)
    actions: list[dict[str, Any]] = []
    # Even with injectable pr_state_fn, refuse authorize/apply without a valid
    # caller repo so wrong ambient context cannot authorize deletes.
    authorize_ok = repo_slug is not None
    for row in completed:
        if not authorize_ok:
            classified = {
                "reason": f"caller_repo_{repo_reason}",
                "authorized": False,
                "prState": None,
            }
        else:
            classified = classify_file_repair(
                row,
                policy=pol,
                pr_state_fn=pr_state_fn,
                repo=repo_slug or "",
            )
        authorized = bool(classified.get("authorized")) and authorize_ok
        if authorized:
            decision = "DELETED_FILE" if apply else "WOULD_DELETE_FILE"
            if apply:
                Path(row["path"]).unlink(missing_ok=True)
        else:
            decision = "KEEP"
        actions.append(
            {
                "failureId": row["failureId"],
                "path": row["path"],
                "branch": row.get("branch") or "",
                "decision": decision,
                "reason": classified.get("reason") or "",
                "authorized": authorized,
                "prState": classified.get("prState"),
                "scope": "file_backend_resolved_only",
            }
        )
    out: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "mode": "apply" if apply else "dry-run",
        "backend": "file",
        "root": str(root),
        "repo": repo_slug or (repo or "").strip(),
        "completedCount": len(completed),
        "actions": actions,
        "githubMutation": "none",
        "notes": [
            "GitHub closed repair issues are not deleted by this control.",
            "Remote branch/PR cleanup remains scripts/cleanup-merged-branches.sh "
            "(MERGED/abandoned evidence + preserve policy).",
            "File deletes require no preserve match and linked PR not OPEN.",
            "Caller --repo is authoritative for linked-PR evidence; "
            "implicit gh / per-row repository never authorize apply deletes.",
        ],
        "generatedAt": utc_now(),
    }
    if not authorize_ok:
        out["refused"] = f"caller_repo_{repo_reason}"
        out["notes"].append(
            "REFUSED: valid caller owner/name --repo required for PR-evidence "
            "authorization; no WOULD_DELETE_FILE / DELETED_FILE authorized."
        )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sh = sub.add_parser("show-preserve", help="Print active preserve policy")
    sh.add_argument("--policy", default="", help="Override preserve JSON path")

    exp = sub.add_parser(
        "export-preserve",
        help=(
            "Print shell-consumable JSON (branches/issues/prHeads/sources); "
            "unresolved preserve PR heads fail closed (exit 1, JSON still printed)"
        ),
    )
    exp.add_argument("--policy", default="", help="Override preserve JSON path")
    exp.add_argument(
        "--repo",
        default="",
        help=(
            "Optional owner/name for gh pr view when resolving preserve PR heads "
            "(else GITHUB_REPOSITORY / GH_REPO; if neither explicit nor env and "
            "both origin+upstream remotes exist, fail closed before gh/origin "
            "guess; otherwise gh repo view / origin-only)"
        ),
    )

    ck = sub.add_parser("check-branch", help="Classify one branch against preserve + evidence")
    ck.add_argument("--branch", required=True)
    ck.add_argument(
        "--evidence",
        default="NONE",
        choices=["OPEN", "MERGED", "ABANDONED", "NONE"],
    )
    ck.add_argument("--pr", type=int, default=0)
    ck.add_argument("--policy", default="")

    pl = sub.add_parser(
        "plan-completed-repairs",
        help="Dry-run (default) or apply file-backend completed repair cleanup",
    )
    pl.add_argument(
        "--repair-dir",
        default="",
        help="File-backend root (default: LINKTREND_REPAIR_DIR or .git/linktrend-repair-tasks)",
    )
    pl.add_argument(
        "--apply",
        action="store_true",
        help="Delete resolved file-backend JSON records only (never GitHub)",
    )
    pl.add_argument("--policy", default="", help="Override preserve JSON path")
    pl.add_argument(
        "--repo",
        default="",
        help="Optional owner/name for gh pr view when classifying linked PRs",
    )

    args = ap.parse_args(argv)
    policy_path = Path(args.policy) if getattr(args, "policy", "") else None

    if args.cmd == "show-preserve":
        pol = load_preserve_policy(policy_path)
        print(
            json.dumps(
                {
                    "schemaVersion": pol["schemaVersion"],
                    "path": pol["path"],
                    "sources": pol["sources"],
                    "defaultsDisabled": pol["defaultsDisabled"],
                    "preserveIssueNumbers": pol["preserveIssueNumbers"],
                    "preservePrNumbers": pol["preservePrNumbers"],
                    "preserveBranchExact": pol["preserveBranchExact"],
                },
                indent=2,
            )
        )
        return 0

    if args.cmd == "export-preserve":
        pol = load_preserve_policy(policy_path)
        repo_slug, repo_source = resolve_cleanup_repo(str(getattr(args, "repo", "") or ""))
        payload = export_preserve_for_shell(
            policy=pol,
            repo=repo_slug or "",
            repo_source=repo_source,
        )
        print(json.dumps(payload, indent=2))
        if not payload.get("preserveResolutionOk", True):
            return 1
        return 0

    if args.cmd == "check-branch":
        pol = load_preserve_policy(policy_path)
        pr = int(args.pr) if args.pr else None
        print(
            json.dumps(
                classify_branch_decision(
                    args.branch,
                    evidence=args.evidence,
                    pr_number=pr,
                    policy=pol,
                ),
                indent=2,
            )
        )
        return 0

    if args.cmd == "plan-completed-repairs":
        root = Path(
            args.repair_dir
            or os.environ.get("LINKTREND_REPAIR_DIR")
            or os.environ.get("LINKTREND_CONFLICT_DIR")
            or ".git/linktrend-repair-tasks"
        )
        pol = load_preserve_policy(policy_path) if policy_path else load_preserve_policy()
        repo_slug, _repo_reason = normalize_caller_repo(
            str(getattr(args, "repo", "") or "")
        )
        # Missing/invalid --repo: plan still runs (all KEEP / refused); never apply.
        plan = plan_completed_repair_cleanup(
            root,
            apply=bool(args.apply) if repo_slug else False,
            policy=pol,
            repo=repo_slug or "",
        )
        print(json.dumps(plan, indent=2))
        return 0 if repo_slug else 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
