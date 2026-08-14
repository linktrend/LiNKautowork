#!/usr/bin/env python3
"""Require a consumer-declared workflow to pass for one exact head.

This is deliberately data-only: workflow inputs never become shell fragments.
Tests may provide the API response through ``LINKTREND_ACTIONS_RUNS_JSON``;
production reads the same GitHub Actions runs endpoint with ``gh api``.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def declared_workflow_name(root: Path, config_key: str) -> str:
    path = root / ".github" / "linktrend-gitops-consumer.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))[config_key]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"consumer_ci_config_invalid:{path}:{exc}") from exc
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"consumer_ci_config_invalid:{path}:{config_key}")
    return value


def workflow_runs(repository: str, head: str) -> list[object]:
    supplied = os.environ.get("LINKTREND_ACTIONS_RUNS_JSON")
    if supplied is None:
        result = subprocess.run(
            # Fast/CI normally arrive as pull_request runs, but CodeQL records
            # PR analysis as ``dynamic``. Bind the exact head and declared
            # workflow name below instead of assuming one event type.
            ["gh", "api", f"repos/{repository}/actions/runs?head_sha={head}&per_page=100"],
            check=True,
            capture_output=True,
            text=True,
        )
        supplied = result.stdout
    try:
        payload = json.loads(supplied)
        runs = payload["workflow_runs"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"consumer_ci_runs_invalid:{exc}") from exc
    if not isinstance(runs, list):
        raise SystemExit("consumer_ci_runs_invalid:workflow_runs")
    return runs


def successful_check_run(repository: str, head: str, name: str) -> bool:
    """Return an exact-head completed check-run match.

    CodeQL PR analyses are represented as ``dynamic`` and may be absent from
    the Actions runs listing.  GitHub's commit check-runs endpoint is the
    authoritative exact-SHA record for those checks.
    """
    supplied = os.environ.get("LINKTREND_CHECK_RUNS_JSON")
    if supplied is None:
        result = subprocess.run(
            ["gh", "api", f"repos/{repository}/commits/{head}/check-runs?per_page=100"],
            check=True,
            capture_output=True,
            text=True,
        )
        supplied = result.stdout
    try:
        runs = json.loads(supplied)["check_runs"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"consumer_ci_check_runs_invalid:{exc}") from exc
    return isinstance(runs, list) and any(
        isinstance(run, dict) and run.get("name") == name and run.get("conclusion") == "success"
        for run in runs
    )


def require_success(repository: str, head: str, root: Path, config_key: str = "ciWorkflowName", workflow_name: str | None = None) -> str:
    if not repository or not head:
        raise SystemExit("consumer_ci_identity_invalid")
    name = workflow_name or declared_workflow_name(root, config_key)
    for run in workflow_runs(repository, head):
        if not isinstance(run, dict):
            continue
        if run.get("name") == name and run.get("head_sha") == head and run.get("conclusion") == "success":
            return name
    if workflow_name and successful_check_run(repository, head, name):
        return name
    raise SystemExit(f"full_suite_required_ci_missing_for_exact_head={head} workflow={name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument(
        "--config-key",
        choices=("fastWorkflowName", "ciWorkflowName", "branchPolicyWorkflowName"),
        default="ciWorkflowName",
    )
    parser.add_argument("--workflow-name", help="exact security workflow name; never inferred")
    args = parser.parse_args()
    print(require_success(args.repository, args.head, Path.cwd(), args.config_key, args.workflow_name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
