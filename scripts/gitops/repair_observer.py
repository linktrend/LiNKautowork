#!/usr/bin/env python3
"""Observe GitHub lifecycle events and maintain repair tasks.

CLI:
  python3 scripts/gitops/repair_observer.py handle-event --event-path PATH --repo OWNER/REPO
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import repair_task

USAGE_LIMIT_PATTERNS = (
    "billing",
    "insufficient funds",
    "usage limit",
    "quota",
    "rate limit exhausted",
    "out of credits",
    "payment required",
    "plan limit",
)


@dataclass(frozen=True)
class ObserverConfig:
    ci_workflow_name: str = "CI"
    branch_policy_workflow_name: str = "Branch Source Policy"
    bugbot_check_name: str = "Cursor Bugbot"  # provider check_run name
    review_gate_check_name: str = "Linktrend Review Gate"

    @property
    def workflow_names(self) -> set[str]:
        return {self.ci_workflow_name, self.branch_policy_workflow_name}


def _config_value(raw: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def load_config(env: dict[str, str] | None = None) -> ObserverConfig:
    source = dict(os.environ if env is None else env)
    raw: dict[str, Any] = {}
    config_path = source.get("LINKTREND_CONSUMER_GITOPS_CONFIG", "").strip()
    if config_path:
        try:
            raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"failed to read LINKTREND_CONSUMER_GITOPS_CONFIG: {exc}") from exc

    ci = (
        source.get("LINKTREND_CI_WORKFLOW_NAME")
        or _config_value(raw, "LINKTREND_CI_WORKFLOW_NAME", "ciWorkflowName", "ci_workflow_name")
        or "CI"
    )
    branch_policy = (
        source.get("LINKTREND_BRANCH_POLICY_WORKFLOW_NAME")
        or _config_value(
            raw,
            "LINKTREND_BRANCH_POLICY_WORKFLOW_NAME",
            "branchPolicyWorkflowName",
            "branch_policy_workflow_name",
        )
        or "Branch Source Policy"
    )
    bugbot = (
        source.get("LINKTREND_BUGBOT_PROVIDER_CHECK_NAME")
        or "Cursor Bugbot"
    )
    review_gate = (
        source.get("LINKTREND_REVIEW_GATE_CHECK_NAME")
        or source.get("LINKTREND_BUGBOT_CHECK_NAME")
        or _config_value(raw, "reviewGateCheckName", "bugbotCheckName", "review_gate_check_name")
        or "Linktrend Review Gate"
    )
    if review_gate == "Cursor Bugbot":
        raise RuntimeError(
            "raw_bugbot_required: managed review gate must be 'Linktrend Review Gate'"
        )
    return ObserverConfig(
        ci_workflow_name=ci,
        branch_policy_workflow_name=branch_policy,
        bugbot_check_name=bugbot,
        review_gate_check_name=review_gate,
    )


def _payload_repo(payload: dict[str, Any]) -> str:
    repo = payload.get("repository") or {}
    if isinstance(repo, dict):
        return str(repo.get("full_name") or "").strip()
    return ""


def _repo_matches(payload: dict[str, Any], repo: str) -> bool:
    payload_repo = _payload_repo(payload)
    return not payload_repo or payload_repo.lower() == repo.lower()


def _event_name(payload: dict[str, Any], explicit: str = "") -> str:
    if explicit:
        return explicit
    if "workflow_run" in payload:
        return "workflow_run"
    if "check_run" in payload:
        return "check_run"
    return ""


def _first_pr(prs: list[dict[str, Any]]) -> tuple[str, str]:
    if not prs:
        return "", ""
    first = prs[0]
    pr = str(first.get("number") or "")
    head = first.get("head") if isinstance(first.get("head"), dict) else {}
    branch = str(head.get("ref") or first.get("headRefName") or "")
    return pr, branch


def _check_output_text(check_run: dict[str, Any]) -> str:
    output = check_run.get("output") if isinstance(check_run.get("output"), dict) else {}
    parts = [
        check_run.get("title"),
        check_run.get("summary"),
        check_run.get("text"),
        output.get("title"),
        output.get("summary"),
        output.get("text"),
    ]
    return "\n".join(str(part) for part in parts if part)


def usage_limit_keywords(text: str) -> list[str]:
    lower = text.lower()
    return [pattern for pattern in USAGE_LIMIT_PATTERNS if pattern in lower]


def _task_pr(task: dict[str, Any]) -> str:
    return str(task.get("prNumber") or task.get("pr") or "").strip()


def _task_workflow(task: dict[str, Any]) -> str:
    return str(task.get("workflowName") or task.get("workflowId") or "").strip()


def _task_check(task: dict[str, Any]) -> str:
    return str(task.get("checkName") or task.get("checkId") or "").strip()


def _task_branch(task: dict[str, Any]) -> str:
    return str(task.get("branch") or "").strip()


def _gh_json(args: list[str]) -> Any:
    out = subprocess.check_output(["gh", *args], text=True)
    return json.loads(out or "{}")


def lookup_pr_for_sha(repo: str, head_sha: str) -> tuple[str, str]:
    if not head_sha:
        return "", ""
    try:
        rows = _gh_json(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--search",
                head_sha,
                "--json",
                "number,headRefName,headRefOid",
                "--limit",
                "10",
            ]
        )
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return "", ""
    matches = [row for row in rows if row.get("headRefOid") == head_sha]
    if len(matches) != 1:
        return "", ""
    return str(matches[0].get("number") or ""), str(matches[0].get("headRefName") or "")


def current_pr_head(repo: str, pr: str) -> tuple[str, str]:
    try:
        row = _gh_json(
            [
                "pr",
                "view",
                pr,
                "--repo",
                repo,
                "--json",
                "headRefName,headRefOid,state",
            ]
        )
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return "", ""
    if row.get("state") and row.get("state") != "OPEN":
        return "", ""
    return str(row.get("headRefOid") or ""), str(row.get("headRefName") or "")


def current_branch_head(repo: str, branch: str) -> str:
    if not branch:
        return ""
    try:
        row = _gh_json(["api", f"repos/{repo}/git/ref/heads/{branch}"])
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return ""
    obj = row.get("object") if isinstance(row.get("object"), dict) else {}
    return str(obj.get("sha") or "")


def _current_head_proven(repo: str, head_sha: str, pr: str, branch: str) -> tuple[bool, str]:
    if not head_sha:
        return False, "missing_event_head_sha"
    if pr:
        current_sha, current_branch = current_pr_head(repo, pr)
        if not current_sha:
            return False, "current_pr_head_unresolved"
        if current_sha != head_sha:
            return False, "event_head_not_current_pr_head"
        if branch and current_branch and current_branch != branch:
            return False, "event_branch_not_current_pr_branch"
        return True, "current_pr_head"
    current_sha = current_branch_head(repo, branch)
    if not current_sha:
        return False, "current_branch_head_unresolved"
    if current_sha != head_sha:
        return False, "event_head_not_current_branch_head"
    return True, "current_branch_head"


def _matches_task(
    task: dict[str, Any],
    *,
    repo: str,
    failure_type: str,
    pr: str,
    workflow: str,
    check: str,
    branch: str,
) -> bool:
    if str(task.get("repository") or "").lower() != repo.lower():
        return False
    if str(task.get("failureType") or "") != failure_type:
        return False

    task_workflow = _task_workflow(task)
    task_check = _task_check(task)
    if failure_type == "ci_failure":
        if task_workflow and task_workflow != workflow:
            return False
        if task_check and task_check != workflow:
            return False
        if not task_workflow and not task_check:
            return False
    elif failure_type == "bugbot_failure":
        if task_check != check:
            return False
        if task_workflow and workflow and task_workflow != workflow:
            return False
    elif failure_type == "usage_limit":
        # Funding/usage tasks are keyed by Bugbot check (+ optional PR/branch).
        if task_check and task_check != check:
            return False
    else:
        return False

    task_pr = _task_pr(task)
    if task_pr:
        return bool(pr) and task_pr == pr
    return bool(branch) and _task_branch(task) == branch


def _resolve_matching(
    *,
    repo: str,
    failure_type: str,
    head_sha: str,
    pr: str,
    workflow: str = "",
    check: str = "",
    branch: str = "",
) -> dict[str, Any]:
    proven, reason = _current_head_proven(repo, head_sha, pr, branch)
    if not proven:
        return {"action": "skip", "reason": reason}

    backend = repair_task.get_backend(repo)
    matches = [
        task
        for task in backend.list_open()
        if _matches_task(
            task,
            repo=repo,
            failure_type=failure_type,
            pr=pr,
            workflow=workflow,
            check=check,
            branch=branch,
        )
    ]
    if not matches:
        return {"action": "skip", "reason": "no_matching_open_task"}
    if len(matches) > 1:
        return {"action": "skip", "reason": "ambiguous_matching_tasks", "count": len(matches)}

    task = matches[0]
    resolved = repair_task.resolve_task(
        repo,
        task_id=str(task.get("failureId") or task.get("id") or ""),
        head_sha=head_sha,
    )
    if not resolved:
        return {"action": "skip", "reason": "resolve_returned_empty"}
    return {
        "action": "resolved",
        "failureId": resolved.get("failureId"),
        "headSha": resolved.get("headSha"),
        "proof": reason,
    }


def _workflow_event(payload: dict[str, Any], repo: str, config: ObserverConfig) -> dict[str, Any]:
    wr = payload.get("workflow_run") if isinstance(payload.get("workflow_run"), dict) else {}
    conclusion = str(wr.get("conclusion") or "")
    workflow = str(wr.get("name") or "")
    if workflow not in config.workflow_names:
        return {"action": "skip", "reason": "workflow_not_configured", "workflow": workflow}
    if conclusion not in {"failure", "success"}:
        return {"action": "skip", "reason": "workflow_conclusion_ignored", "conclusion": conclusion}

    head_sha = str(wr.get("head_sha") or "")
    branch = str(wr.get("head_branch") or "")
    pr, pr_branch = _first_pr(list(wr.get("pull_requests") or []))
    branch = pr_branch or branch

    if conclusion == "failure":
        fid = repair_task.failure_id(repo, "ci_failure", pr=pr, workflow=workflow, check=workflow, branch=branch)
        out = repair_task.upsert_task(
            {
                "failureId": fid,
                "id": fid,
                "repository": repo,
                "failureType": "ci_failure",
                "prNumber": pr,
                "pr": pr,
                "workflowName": workflow,
                "workflowId": workflow,
                "checkName": workflow,
                "checkId": workflow,
                "branch": branch,
                "headSha": head_sha,
                "severity": "ordinary",
                "repairStatus": "recorded",
                "lisaDispatchState": "pending",
                "resolutionState": "open",
                "evidence": {"event": "workflow_run", "conclusion": conclusion},
                "nextAction": f"Investigate CI/gate failure in workflow {workflow!r}; ordinary Lisa dispatch allowed.",
            },
            increment=False,
        )
        return {"action": "upserted", "failureId": out.get("failureId"), "failureType": "ci_failure"}

    return _resolve_matching(
        repo=repo,
        failure_type="ci_failure",
        head_sha=head_sha,
        pr=pr,
        workflow=workflow,
        check=workflow,
        branch=branch,
    )


def _check_event(payload: dict[str, Any], repo: str, config: ObserverConfig) -> dict[str, Any]:
    cr = payload.get("check_run") if isinstance(payload.get("check_run"), dict) else {}
    conclusion = str(cr.get("conclusion") or "")
    check = str(cr.get("name") or "")
    if check != config.bugbot_check_name:
        return {"action": "skip", "reason": "check_not_bugbot", "check": check}
    if conclusion not in {"failure", "success", "neutral"}:
        return {"action": "skip", "reason": "check_conclusion_ignored", "conclusion": conclusion}

    head_sha = str(cr.get("head_sha") or "")
    check_suite = cr.get("check_suite") if isinstance(cr.get("check_suite"), dict) else {}
    branch = str(check_suite.get("head_branch") or "")
    pr, pr_branch = _first_pr(list(cr.get("pull_requests") or []))
    branch = pr_branch or branch
    if not pr and head_sha:
        pr, lookup_branch = lookup_pr_for_sha(repo, head_sha)
        branch = branch or lookup_branch

    if conclusion == "neutral":
        text = _check_output_text(cr)
        matches = usage_limit_keywords(text)
        if not matches:
            return {"action": "skip", "reason": "neutral_without_usage_limit"}
        fid = repair_task.failure_id(repo, "usage_limit", pr=pr, check=check, branch=branch)
        out = repair_task.upsert_task(
            {
                "failureId": fid,
                "id": fid,
                "repository": repo,
                "failureType": "usage_limit",
                "prNumber": pr,
                "pr": pr,
                "checkName": check,
                "checkId": check,
                "branch": branch,
                "headSha": head_sha,
                "severity": "immediate",
                "repairStatus": "immediate_no_auto_repair",
                "lisaDispatchState": "do_not_dispatch",
                "resolutionState": "open",
                "evidence": {"event": "check_run", "conclusion": conclusion, "matchedKeywords": matches},
                "nextAction": "Cursor Bugbot usage/billing limit observed; do not auto-repair.",
            },
            increment=False,
        )
        return {"action": "upserted", "failureId": out.get("failureId"), "failureType": "usage_limit"}

    if conclusion == "failure":
        fid = repair_task.failure_id(repo, "bugbot_failure", pr=pr, check=check, branch=branch)
        out = repair_task.upsert_task(
            {
                "failureId": fid,
                "id": fid,
                "repository": repo,
                "failureType": "bugbot_failure",
                "prNumber": pr,
                "pr": pr,
                "checkName": check,
                "checkId": check,
                "branch": branch,
                "headSha": head_sha,
                "severity": "ordinary",
                "repairStatus": "recorded",
                "lisaDispatchState": "pending",
                "resolutionState": "open",
                "evidence": {"event": "check_run", "conclusion": conclusion},
                "nextAction": "Address Cursor Bugbot findings; ordinary Lisa dispatch allowed.",
            },
            increment=False,
        )
        return {"action": "upserted", "failureId": out.get("failureId"), "failureType": "bugbot_failure"}

    # Success: resolve matching bugbot_failure AND matching usage_limit (funding recovery).
    results = []
    for ft in ("bugbot_failure", "usage_limit"):
        results.append(
            _resolve_matching(
                repo=repo,
                failure_type=ft,
                head_sha=head_sha,
                pr=pr,
                check=check,
                branch=branch,
            )
        )
    resolved = [r for r in results if r.get("action") == "resolved"]
    if resolved:
        return {
            "action": "resolved",
            "resolved": resolved,
            "alsoTried": results,
            "headSha": head_sha,
        }
    # Prefer the most informative skip reason
    return {
        "action": "skip",
        "reason": "no_matching_open_bugbot_or_usage_task",
        "attempts": results,
    }


def handle_event(payload: dict[str, Any], repo: str, event_name: str = "") -> dict[str, Any]:
    config = load_config()
    if not _repo_matches(payload, repo):
        return {"action": "skip", "reason": "repository_mismatch"}
    name = _event_name(payload, event_name or os.environ.get("GITHUB_EVENT_NAME", ""))
    if name == "workflow_run":
        return _workflow_event(payload, repo, config)
    if name == "check_run":
        return _check_event(payload, repo, config)
    return {"action": "skip", "reason": "unsupported_event", "event": name}


def handle_event_path(event_path: str, repo: str) -> dict[str, Any]:
    payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    return handle_event(payload, repo)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    handle = sub.add_parser("handle-event")
    handle.add_argument("--event-path", required=True)
    handle.add_argument("--repo", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "handle-event":
        out = handle_event_path(args.event_path, args.repo)
        print(json.dumps(out, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
