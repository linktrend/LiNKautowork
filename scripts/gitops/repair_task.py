#!/usr/bin/env python3
"""First-class GitHub Issues / file-backend repair task system.

IDE owns the schema (docs/contracts/REPAIR-DISPATCHER.md).
Lisa owns ACP dispatch. GitHub never spawns Cursor.

CLI: upsert | show | dispatch-attempt | resolve | list | plan-cleanup-completed

Identity (failureId) = hash(repo|type|pr|workflow|check|branch)
— headSha is stored/updated but NOT part of identity (same failure updates).

attemptCount increments ONLY on explicit dispatch-attempt (repairStatus=dispatched),
never on mere re-observation / upsert of the same failure.

plan-cleanup-completed: dry-run (default) lists resolved file-backend records;
--apply deletes those local JSON files only. Never mutates GitHub Issues.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_GITOPS_DIR = Path(__file__).resolve().parent
if str(_GITOPS_DIR) not in sys.path:
    sys.path.insert(0, str(_GITOPS_DIR))
from cleanup_controls import normalize_caller_repo, plan_completed_repair_cleanup

MAX_ATTEMPTS = 3
SCHEMA_VERSION = 2
LABEL_PRIMARY = "linktrend-repair"
MARKER_PREFIX = "<!-- linktrend-repair-task:"

ORDINARY_TYPES = frozenset(
    {
        "ci_failure",
        "bugbot_failure",
        "merge_conflict",
        "promotion_conflict",
    }
)
IMMEDIATE_TYPES = frozenset(
    {
        "automation_credentials_blocked",
        "usage_limit",
        "packager_author_blocked",
        "immediate_security",
        "immediate_destructive",
        "immediate_approval_required",
        "immediate_product_decision",
    }
)
KNOWN_TYPES = ORDINARY_TYPES | IMMEDIATE_TYPES

TYPE_LABELS = {
    "ci_failure": "linktrend-repair-ci",
    "bugbot_failure": "linktrend-repair-bugbot",
    "merge_conflict": "linktrend-repair-merge-conflict",
    "promotion_conflict": "linktrend-repair-promotion-conflict",
    "automation_credentials_blocked": "linktrend-repair-credentials",
    "usage_limit": "linktrend-repair-usage-limit",
    "packager_author_blocked": "linktrend-repair-packager-author",
    "immediate_security": "linktrend-repair-immediate-security",
    "immediate_destructive": "linktrend-repair-immediate-destructive",
    "immediate_approval_required": "linktrend-repair-immediate-approval",
    "immediate_product_decision": "linktrend-repair-immediate-product",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def failure_id(
    repository: str,
    failure_type: str,
    *,
    pr: str = "",
    workflow: str = "",
    check: str = "",
    branch: str = "",
) -> str:
    """Stable identity — excludes headSha so re-observation updates one record."""
    raw = "|".join(
        [
            repository.strip(),
            failure_type.strip(),
            str(pr or "").strip(),
            workflow.strip(),
            check.strip(),
            branch.strip(),
        ]
    ).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def is_immediate(failure_type: str) -> bool:
    return failure_type in IMMEDIATE_TYPES or failure_type.startswith("immediate_")


def type_label(failure_type: str) -> str:
    return TYPE_LABELS.get(failure_type, f"linktrend-repair-{failure_type.replace('_', '-')}")


def labels_for(failure_type: str) -> list[str]:
    return [LABEL_PRIMARY, type_label(failure_type)]


def marker(task: dict[str, Any]) -> str:
    return f"{MARKER_PREFIX} {json.dumps(task, separators=(',', ':'))} -->"


def parse_marker(body: str) -> dict[str, Any] | None:
    for line in (body or "").splitlines():
        if MARKER_PREFIX in line:
            try:
                raw = line.split(MARKER_PREFIX, 1)[1].strip()
                if raw.endswith("-->"):
                    raw = raw[:-3].strip()
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
    return None


def _token() -> str:
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""


def _api(method: str, url: str, token: str, body: dict | None = None) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "linktrend-repair-task",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> {e.code}: {detail}") from e


def normalize_task(task: dict[str, Any]) -> dict[str, Any]:
    out = dict(task)
    out["schemaVersion"] = SCHEMA_VERSION
    fid = out.get("failureId") or out.get("id") or ""
    out["failureId"] = fid
    out["id"] = fid  # conflict_task / promote-script compat
    ft = str(out.get("failureType") or "")
    out["failureType"] = ft
    # Canonical field names
    if out.get("pr") and not out.get("prNumber"):
        out["prNumber"] = out["pr"]
    if out.get("prNumber") and not out.get("pr"):
        out["pr"] = out["prNumber"]
    if out.get("workflowId") and not out.get("workflowName"):
        out["workflowName"] = out["workflowId"]
    if out.get("workflowName") and not out.get("workflowId"):
        out["workflowId"] = out["workflowName"]
    if out.get("checkId") and not out.get("checkName"):
        out["checkName"] = out["checkId"]
    if out.get("checkName") and not out.get("checkId"):
        out["checkId"] = out["checkName"]

    out.setdefault("maxAttempts", MAX_ATTEMPTS)
    out.setdefault("attemptCount", 0)
    sev = out.get("severity") or ("immediate" if is_immediate(ft) else "ordinary")
    out["severity"] = sev
    out.setdefault("repairStatus", "recorded")
    out.setdefault(
        "lisaDispatchState",
        "do_not_dispatch" if sev == "immediate" else "pending",
    )
    out.setdefault("resolutionState", "open")
    out.setdefault("evidence", {})
    out.setdefault("nextAction", "")

    if ft == "promotion_conflict":
        out.setdefault("status", "conflict_blocked")
        out.setdefault("stage", out.get("stage") or "staging")

    if is_immediate(ft):
        out["severity"] = "immediate"
        out["lisaDispatchState"] = "do_not_dispatch"
        if out.get("repairStatus") not in ("resolved", "escalated_issues"):
            out["repairStatus"] = "immediate_no_auto_repair"
        out["nextAction"] = out.get("nextAction") or (
            "Immediate failure — do not auto-repair; report Issues / await Principal."
        )
    return out


def escalate_if_needed(task: dict[str, Any]) -> dict[str, Any]:
    attempts = int(task.get("attemptCount") or 0)
    if attempts >= MAX_ATTEMPTS and task.get("resolutionState") not in ("resolved",):
        task["repairStatus"] = "escalated_issues"
        task["resolutionState"] = "Issues"
        task["lisaDispatchState"] = "exhausted"
        task["status"] = "Issues"
        task["nextAction"] = task.get("nextAction") or (
            "Max repair attempts reached. Report Issues to Principal."
        )
    return task


def can_dispatch(task: dict[str, Any]) -> tuple[bool, str]:
    task = normalize_task(task)
    if is_immediate(task.get("failureType", "")):
        return False, "immediate_do_not_dispatch"
    if task.get("resolutionState") == "Issues" or task.get("lisaDispatchState") == "exhausted":
        return False, "exhausted"
    if task.get("resolutionState") == "resolved":
        return False, "already_resolved"
    attempts = int(task.get("attemptCount") or 0)
    if attempts >= MAX_ATTEMPTS:
        return False, "max_attempts"
    return True, "ok"


def title_for(task: dict[str, Any]) -> str:
    ft = task.get("failureType") or "unknown"
    repo = task.get("repository") or ""
    pr = task.get("prNumber") or task.get("pr") or ""
    check = task.get("checkName") or task.get("checkId") or ""
    branch = task.get("branch") or ""
    if pr and check:
        return f"[repair:{ft}] {repo}#{pr} {check}"
    if pr:
        return f"[repair:{ft}] {repo}#{pr}"
    if check:
        return f"[repair:{ft}] {repo} {check}"
    if branch:
        return f"[repair:{ft}] {repo} {branch}"
    return f"[repair:{ft}] {repo} ({task.get('failureId')})"


def body_for(task: dict[str, Any]) -> str:
    return (
        f"## LiNKtrend repair task\n\n"
        f"- failureId: `{task.get('failureId')}`\n"
        f"- repository: `{task.get('repository')}`\n"
        f"- failureType: `{task.get('failureType')}`\n"
        f"- severity: `{task.get('severity')}`\n"
        f"- prNumber: `{task.get('prNumber') or 'n/a'}`\n"
        f"- workflowName: `{task.get('workflowName') or 'n/a'}`\n"
        f"- checkName: `{task.get('checkName') or 'n/a'}`\n"
        f"- branch: `{task.get('branch') or 'n/a'}`\n"
        f"- headSha: `{task.get('headSha') or 'n/a'}`\n"
        f"- baseSha: `{task.get('baseSha') or 'n/a'}`\n"
        f"- attemptCount: **{task.get('attemptCount')}** / {task.get('maxAttempts', MAX_ATTEMPTS)}\n"
        f"- repairStatus: **{task.get('repairStatus')}**\n"
        f"- lisaDispatchState: **{task.get('lisaDispatchState')}**\n"
        f"- resolutionState: **{task.get('resolutionState')}**\n"
        f"- nextAction: {task.get('nextAction')}\n\n"
        f"GitHub does **not** spawn Cursor agents. Lisa ACP Repair Dispatcher may "
        f"dispatch Cursor ACP for ordinary failures only (max {MAX_ATTEMPTS} attempts).\n\n"
        f"{marker(task)}\n"
    )


class FileBackend:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, tid: str) -> Path:
        return self.root / f"{tid}.json"

    def upsert(self, task: dict[str, Any], *, increment: bool = False) -> dict[str, Any]:
        task = normalize_task(task)
        tid = task["failureId"]
        path = self._path(tid)
        if path.is_file():
            existing = normalize_task(json.loads(path.read_text(encoding="utf-8")))
            attempts = int(existing.get("attemptCount") or 0)
            # Preserve attemptCount unless explicit dispatch increment
            head = task.get("headSha") or existing.get("headSha")
            existing.update({k: v for k, v in task.items() if v not in (None, "")})
            existing["attemptCount"] = attempts
            if head:
                existing["headSha"] = head
            if increment:
                existing["attemptCount"] = attempts + 1
                existing["repairStatus"] = "dispatched"
                if not is_immediate(existing.get("failureType", "")):
                    existing["lisaDispatchState"] = "dispatched"
            existing["updatedAt"] = utc_now()
            task = existing
        else:
            task = dict(task)
            task["attemptCount"] = 1 if increment else 0
            if increment:
                task["repairStatus"] = "dispatched"
                if not is_immediate(task.get("failureType", "")):
                    task["lisaDispatchState"] = "dispatched"
            task["createdAt"] = utc_now()
            task["updatedAt"] = utc_now()
        task = escalate_if_needed(normalize_task(task))
        path.write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
        return task

    def dispatch_attempt(self, tid: str) -> dict[str, Any] | None:
        path = self._path(tid)
        if not path.is_file():
            return None
        task = normalize_task(json.loads(path.read_text(encoding="utf-8")))
        ok, reason = can_dispatch(task)
        if not ok:
            task = escalate_if_needed(task)
            path.write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
            task["dispatchBlocked"] = reason
            return task
        return self.upsert(task, increment=True)

    def resolve(self, tid: str, *, head_sha: str = "") -> dict[str, Any] | None:
        path = self._path(tid)
        if not path.is_file():
            return None
        task = normalize_task(json.loads(path.read_text(encoding="utf-8")))
        if head_sha:
            stored = (task.get("headSha") or "").strip()
            # Resolve when repaired SHA matches the observed/recorded head,
            # or when caller asserts the repaired tip (same SHA or new tip after repair).
            # Contract: --resolve --head-sha=X closes when repaired SHA matches recorded headSha
            # OR when headSha is being updated to the repaired tip X (caller proves fix).
            if stored and stored != head_sha:
                # Allow resolve when caller provides the repaired SHA that supersedes failure head
                task["resolvedHeadSha"] = head_sha
            else:
                task["resolvedHeadSha"] = head_sha or stored
            task["headSha"] = head_sha or stored
        task["status"] = "resolved"
        task["resolutionState"] = "resolved"
        task["repairStatus"] = "resolved"
        task["lisaDispatchState"] = "do_not_dispatch"
        task["updatedAt"] = utc_now()
        path.write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
        return task

    def get(self, tid: str) -> dict[str, Any] | None:
        path = self._path(tid)
        if not path.is_file():
            return None
        return normalize_task(json.loads(path.read_text(encoding="utf-8")))

    def list_open(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                task = normalize_task(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
            if task.get("resolutionState") in ("resolved",):
                continue
            out.append(task)
        return out


class GitHubIssueBackend:
    def __init__(self, repo: str):
        self.repo = repo
        self.token = _token()
        if not self.token:
            raise RuntimeError("GH_TOKEN or GITHUB_TOKEN required for github backend")

    def _ensure_labels(self, failure_type: str) -> None:
        for name, color, desc in (
            (LABEL_PRIMARY, "B60205", "LiNKtrend repair task"),
            (type_label(failure_type), "D93F0B", f"repair:{failure_type}"),
        ):
            try:
                _api(
                    "GET",
                    f"https://api.github.com/repos/{self.repo}/labels/{urllib.parse.quote(name)}",
                    self.token,
                )
            except RuntimeError:
                try:
                    _api(
                        "POST",
                        f"https://api.github.com/repos/{self.repo}/labels",
                        self.token,
                        {"name": name, "color": color, "description": desc},
                    )
                except RuntimeError:
                    pass

    def _find(self, tid: str) -> dict | None:
        try:
            out = subprocess.check_output(
                [
                    "gh",
                    "issue",
                    "list",
                    "--repo",
                    self.repo,
                    "--label",
                    LABEL_PRIMARY,
                    "--state",
                    "open",
                    "--json",
                    "number,body,title,labels",
                    "--limit",
                    "100",
                ],
                text=True,
            )
            for row in json.loads(out or "[]"):
                parsed = parse_marker(row.get("body") or "")
                if parsed and (parsed.get("failureId") or parsed.get("id")) == tid:
                    return row
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        return None

    def upsert(self, task: dict[str, Any], *, increment: bool = False) -> dict[str, Any]:
        task = normalize_task(task)
        self._ensure_labels(task.get("failureType") or "ci_failure")
        tid = task["failureId"]
        existing_issue = self._find(tid)
        labs = labels_for(task.get("failureType") or "ci_failure")
        if existing_issue:
            parsed = normalize_task(parse_marker(existing_issue.get("body") or "") or {})
            attempts = int(parsed.get("attemptCount") or 0)
            head = task.get("headSha") or parsed.get("headSha")
            parsed.update({k: v for k, v in task.items() if v not in (None, "")})
            parsed["attemptCount"] = attempts
            if head:
                parsed["headSha"] = head
            if increment:
                parsed["attemptCount"] = attempts + 1
                parsed["repairStatus"] = "dispatched"
                if not is_immediate(parsed.get("failureType", "")):
                    parsed["lisaDispatchState"] = "dispatched"
            parsed["updatedAt"] = utc_now()
            parsed.setdefault("createdAt", task.get("createdAt") or utc_now())
            parsed = escalate_if_needed(normalize_task(parsed))
            _api(
                "PATCH",
                f"https://api.github.com/repos/{self.repo}/issues/{existing_issue['number']}",
                self.token,
                {"title": title_for(parsed), "body": body_for(parsed), "labels": labs},
            )
            parsed["issueNumber"] = existing_issue["number"]
            return parsed

        task = dict(task)
        task["attemptCount"] = 1 if increment else 0
        if increment:
            task["repairStatus"] = "dispatched"
            if not is_immediate(task.get("failureType", "")):
                task["lisaDispatchState"] = "dispatched"
        task["createdAt"] = utc_now()
        task["updatedAt"] = utc_now()
        task = escalate_if_needed(normalize_task(task))
        created = _api(
            "POST",
            f"https://api.github.com/repos/{self.repo}/issues",
            self.token,
            {"title": title_for(task), "body": body_for(task), "labels": labs},
        )
        task["issueNumber"] = created.get("number")
        return task

    def dispatch_attempt(self, tid: str) -> dict[str, Any] | None:
        issue = self._find(tid)
        if not issue:
            return None
        task = normalize_task(parse_marker(issue.get("body") or "") or {"failureId": tid})
        task["issueNumber"] = issue["number"]
        ok, reason = can_dispatch(task)
        if not ok:
            task = escalate_if_needed(task)
            labs = labels_for(task.get("failureType") or "ci_failure")
            _api(
                "PATCH",
                f"https://api.github.com/repos/{self.repo}/issues/{issue['number']}",
                self.token,
                {"title": title_for(task), "body": body_for(task), "labels": labs},
            )
            task["dispatchBlocked"] = reason
            return task
        return self.upsert(task, increment=True)

    def resolve(self, tid: str, *, head_sha: str = "") -> dict[str, Any] | None:
        issue = self._find(tid)
        if not issue:
            return None
        parsed = normalize_task(parse_marker(issue.get("body") or "") or {"failureId": tid, "id": tid})
        if head_sha:
            parsed["resolvedHeadSha"] = head_sha
            parsed["headSha"] = head_sha
        parsed["status"] = "resolved"
        parsed["resolutionState"] = "resolved"
        parsed["repairStatus"] = "resolved"
        parsed["lisaDispatchState"] = "do_not_dispatch"
        parsed["updatedAt"] = utc_now()
        _api(
            "PATCH",
            f"https://api.github.com/repos/{self.repo}/issues/{issue['number']}",
            self.token,
            {
                "state": "closed",
                "body": body_for(parsed),
                "title": title_for(parsed),
            },
        )
        parsed["issueNumber"] = issue["number"]
        return parsed

    def get(self, tid: str) -> dict[str, Any] | None:
        issue = self._find(tid)
        if not issue:
            return None
        parsed = parse_marker(issue.get("body") or "")
        if parsed:
            parsed = normalize_task(parsed)
            parsed["issueNumber"] = issue["number"]
        return parsed

    def list_open(self) -> list[dict[str, Any]]:
        try:
            out = subprocess.check_output(
                [
                    "gh",
                    "issue",
                    "list",
                    "--repo",
                    self.repo,
                    "--label",
                    LABEL_PRIMARY,
                    "--state",
                    "open",
                    "--json",
                    "number,body,title",
                    "--limit",
                    "100",
                ],
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []
        rows: list[dict[str, Any]] = []
        for row in json.loads(out or "[]"):
            parsed = parse_marker(row.get("body") or "")
            if parsed:
                t = normalize_task(parsed)
                t["issueNumber"] = row["number"]
                rows.append(t)
        return rows


def get_backend(repo: str):
    backend = (
        os.environ.get("LINKTREND_REPAIR_BACKEND")
        or os.environ.get("LINKTREND_CONFLICT_BACKEND")
        or "github"
    ).lower()
    if backend == "file":
        root = Path(
            os.environ.get("LINKTREND_REPAIR_DIR")
            or os.environ.get("LINKTREND_CONFLICT_DIR")
            or ".git/linktrend-repair-tasks"
        )
        return FileBackend(root)
    return GitHubIssueBackend(repo)


def upsert_task(task: dict[str, Any], *, increment: bool = False) -> dict[str, Any]:
    task = normalize_task(task)
    if is_immediate(task.get("failureType", "")):
        increment = False
    backend = get_backend(task["repository"])
    out = backend.upsert(task, increment=increment)
    return escalate_if_needed(normalize_task(out))


def resolve_task(
    repository: str,
    *,
    task_id: str = "",
    failure_type: str = "",
    pr: str = "",
    workflow: str = "",
    check: str = "",
    branch: str = "",
    head_sha: str = "",
) -> dict[str, Any] | None:
    tid = task_id or failure_id(
        repository,
        failure_type,
        pr=pr,
        workflow=workflow,
        check=check,
        branch=branch,
    )
    backend = get_backend(repository)
    return backend.resolve(tid, head_sha=head_sha)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("upsert", help="Record/update a failure (does not increment attempts)")
    up.add_argument("--repo", required=True)
    up.add_argument("--failure-type", required=True)
    up.add_argument("--branch", default="")
    up.add_argument("--head-sha", default="")
    up.add_argument("--base-sha", default="")
    up.add_argument("--pr", "--pr-number", dest="pr", default="")
    up.add_argument("--workflow", "--workflow-name", "--workflow-id", dest="workflow", default="")
    up.add_argument("--check", "--check-name", "--check-id", dest="check", default="")
    up.add_argument("--severity", choices=["ordinary", "immediate"], default="")
    up.add_argument("--next-action", default="")
    up.add_argument("--evidence-json", default="")
    up.add_argument("--stage", default="")
    up.add_argument("--source-branch", default="")
    up.add_argument("--target-branch", default="")
    up.add_argument("--promote-pr", default="")
    up.add_argument("--status", default="")
    # Compat: --increment-attempt alone is ignored on upsert; use dispatch-attempt.
    # Kept so old callers do not crash; prefer dispatch-attempt.
    up.add_argument(
        "--increment-attempt",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    da = sub.add_parser("dispatch-attempt", help="Increment attemptCount; set repairStatus=dispatched")
    da.add_argument("--repo", required=True)
    da.add_argument("--id", "--failure-id", dest="id", required=True)

    rs = sub.add_parser("resolve", help="Close when repaired; optional --head-sha of repaired tip")
    rs.add_argument("--repo", required=True)
    rs.add_argument("--id", "--failure-id", dest="id", default="")
    rs.add_argument("--failure-type", default="")
    rs.add_argument("--pr", "--pr-number", dest="pr", default="")
    rs.add_argument("--workflow", "--workflow-name", "--workflow-id", dest="workflow", default="")
    rs.add_argument("--check", "--check-name", "--check-id", dest="check", default="")
    rs.add_argument("--branch", default="")
    rs.add_argument("--head-sha", default="")

    sh = sub.add_parser("show")
    sh.add_argument("--repo", required=True)
    sh.add_argument("--id", "--failure-id", dest="id", required=True)

    ls = sub.add_parser("list")
    ls.add_argument("--repo", required=True)

    pc = sub.add_parser(
        "plan-cleanup-completed",
        help="Dry-run (default) completed repair file-backend cleanup; --apply deletes local resolved JSON only",
    )
    pc.add_argument("--repo", required=True, help="Repository (selects backend; GitHub never mutated)")
    pc.add_argument(
        "--repair-dir",
        default="",
        help="Override file-backend root (default LINKTREND_REPAIR_DIR / .git/linktrend-repair-tasks)",
    )
    pc.add_argument(
        "--apply",
        action="store_true",
        help="Delete resolved file-backend records only (refused for github backend)",
    )

    args = ap.parse_args(argv)

    if args.cmd == "upsert":
        ft = args.failure_type
        if ft not in KNOWN_TYPES and not ft.startswith("immediate_"):
            print(
                f"WARN: unrecognized failureType={ft!r}; proceeding",
                file=sys.stderr,
            )
        pr = args.pr or args.promote_pr
        branch = args.branch or args.source_branch
        fid = failure_id(
            args.repo,
            ft,
            pr=pr,
            workflow=args.workflow,
            check=args.check,
            branch=branch,
        )
        evidence: dict[str, Any] = {}
        if args.evidence_json:
            evidence = json.loads(args.evidence_json)
        sev = args.severity or ("immediate" if is_immediate(ft) else "ordinary")
        task: dict[str, Any] = {
            "failureId": fid,
            "id": fid,
            "repository": args.repo,
            "failureType": ft,
            "prNumber": pr,
            "pr": pr,
            "workflowName": args.workflow,
            "workflowId": args.workflow,
            "checkName": args.check,
            "checkId": args.check,
            "branch": branch,
            "headSha": args.head_sha,
            "baseSha": args.base_sha,
            "severity": sev,
            "attemptCount": 0,
            "maxAttempts": MAX_ATTEMPTS,
            "repairStatus": "recorded",
            "evidence": evidence,
            "nextAction": args.next_action
            or (
                "Immediate failure — do not auto-repair."
                if sev == "immediate"
                else "Lisa ACP Repair Dispatcher may dispatch Cursor ACP (ordinary only)."
            ),
            "lisaDispatchState": "do_not_dispatch" if sev == "immediate" else "pending",
            "resolutionState": "open",
            "stage": args.stage,
            "sourceBranch": args.source_branch or args.branch,
            "targetBranch": args.target_branch,
            "sourceSha": args.head_sha,
            "targetSha": args.base_sha,
            "promotePr": args.promote_pr or args.pr,
            "status": args.status
            or ("conflict_blocked" if ft == "promotion_conflict" else "open"),
        }
        # Upsert never increments; --increment-attempt is legacy no-op here.
        # (dispatch-attempt is the only increment path.)
        if args.increment_attempt:
            print(
                "WARN: --increment-attempt on upsert is ignored; use dispatch-attempt",
                file=sys.stderr,
            )
        out = upsert_task(task, increment=False)
        print(json.dumps(out, indent=2))
        return 0

    # plan-cleanup-completed does not use get_backend (avoids github token /
    # file-root mkdir side effects); validate caller --repo then plan/apply.
    if args.cmd == "plan-cleanup-completed":
        backend_name = (
            os.environ.get("LINKTREND_REPAIR_BACKEND")
            or os.environ.get("LINKTREND_CONFLICT_BACKEND")
            or "github"
        ).lower()
        if backend_name != "file":
            print(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "mode": "dry-run",
                        "backend": backend_name,
                        "completedCount": 0,
                        "actions": [],
                        "githubMutation": "none",
                        "refused": "github_completed_repair_cleanup_not_authorized",
                        "notes": [
                            "Completed GitHub repair issues are closed by resolve; "
                            "bulk delete of GitHub issues is not authorized by this control.",
                            "Use LINKTREND_REPAIR_BACKEND=file for local resolved-record cleanup.",
                        ],
                    },
                    indent=2,
                )
            )
            return 0 if not args.apply else 2
        # Caller --repo is required and authoritative for linked-PR evidence.
        # Empty/invalid must not fall through to implicit gh or per-row repository.
        repo_slug, repo_reason = normalize_caller_repo(args.repo)
        if repo_slug is None:
            print(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "mode": "apply" if args.apply else "dry-run",
                        "backend": "file",
                        "completedCount": 0,
                        "actions": [],
                        "githubMutation": "none",
                        "refused": f"caller_repo_{repo_reason}",
                        "notes": [
                            "REFUSED: --repo must be a valid owner/name for "
                            "PR-evidence authorization; refusing implicit gh / "
                            "per-row repository fallback.",
                        ],
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 2
        root = Path(
            args.repair_dir
            or os.environ.get("LINKTREND_REPAIR_DIR")
            or os.environ.get("LINKTREND_CONFLICT_DIR")
            or ".git/linktrend-repair-tasks"
        )
        plan = plan_completed_repair_cleanup(
            root, apply=bool(args.apply), repo=repo_slug
        )
        print(json.dumps(plan, indent=2))
        return 0

    backend = get_backend(args.repo)
    if args.cmd == "dispatch-attempt":
        out = backend.dispatch_attempt(args.id)
        if not out:
            print("{}", file=sys.stderr)
            return 1
        if out.get("dispatchBlocked"):
            print(json.dumps(out, indent=2))
            return 2
        print(json.dumps(out, indent=2))
        return 0
    if args.cmd == "resolve":
        if not args.id and not args.failure_type:
            print("resolve requires --id or --failure-type identity fields", file=sys.stderr)
            return 2
        out = resolve_task(
            args.repo,
            task_id=args.id,
            failure_type=args.failure_type,
            pr=args.pr,
            workflow=args.workflow,
            check=args.check,
            branch=args.branch,
            head_sha=args.head_sha,
        )
        print(json.dumps(out or {}, indent=2))
        return 0 if out else 1
    if args.cmd == "show":
        out = backend.get(args.id)
        print(json.dumps(out or {}, indent=2))
        return 0 if out else 1
    if args.cmd == "list":
        print(json.dumps(backend.list_open(), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
