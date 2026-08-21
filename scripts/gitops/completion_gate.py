#!/usr/bin/env python3
"""Authoritative agent completion gate.

Modes: checkpoint | review-ready | blocked | status | write-evidence

v2.5 (V25_BOOTSTRAP_LEAN): Issue checkpoints are accepted from exact pushed
commit/tree + scoped diff + focused tests + independent Terra verification +
manifest evidence. Review Ready publication, AUTOMATION_TOKEN, Issue PRs,
hosted completion status, and legacy publisher status are nonrequirements.

review-ready never publishes. Legacy publisher/status outcomes are
WAIVED_LEGACY_GATE, never PASS, and never bypass substantive proof.

Evidence JSON (COMPLETION_EVIDENCE_FILE, --evidence-file, or --evidence-json),
tied to HEAD. Local proof must not be labeled hosted or production.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    import readiness_status as rs
except ImportError:  # pragma: no cover
    rs = None  # type: ignore

try:
    from issue_checkpoint import (
        WAIVED_LEGACY_GATE,
        bind_issue_completion,
        classify_legacy_status,
        parse_immutable_evidence_payload,
        proof_class_of,
        reject_local_as_hosted,
    )
except ImportError:  # pragma: no cover
    from scripts.gitops.issue_checkpoint import (  # type: ignore
        WAIVED_LEGACY_GATE,
        bind_issue_completion,
        classify_legacy_status,
        parse_immutable_evidence_payload,
        proof_class_of,
        reject_local_as_hosted,
    )

try:
    from packager_logic import is_allowed_work_branch
except ImportError:  # pragma: no cover
    def is_allowed_work_branch(name: str, phase_branch_prefix: str = "phase/") -> bool:
        phase = (
            phase_branch_prefix
            if phase_branch_prefix.endswith("/")
            else f"{phase_branch_prefix}/"
        )
        prefixes = (
            "issue/",
            phase,
            "feature/",
            "fix/",
            "chore/",
            "codex/",
            "cursor/",
            "antigravity/",
            "dependabot/",
            "dev/",
        )
        return any(name.startswith(p) for p in prefixes)

try:
    from delivery_modes import load_delivery_config
except ImportError:  # pragma: no cover
    def load_delivery_config(repo_root=None, *, env=None):  # type: ignore[no-untyped-def]
        class _Cfg:
            phase_branch_prefix = "phase/"

        return _Cfg()

try:
    from review_ready_dispatch import (
        app_branch_migration_remediation,
        is_app_backed_issue_branch,
        is_app_backed_publish_branch,
    )
except ImportError:  # pragma: no cover
    _APP_ISSUE_RE = re.compile(
        r"^issue/([1-9][0-9]{0,8})-([a-z0-9]+(?:-[a-z0-9]+)*)$"
    )
    _PHASE_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

    def is_app_backed_issue_branch(name: str) -> bool:
        return bool(name) and bool(_APP_ISSUE_RE.fullmatch(str(name).strip()))

    def is_app_backed_publish_branch(name: str, phase_prefix: str = "phase/") -> bool:
        if is_app_backed_issue_branch(name):
            return True
        raw = str(name or "").strip()
        prefix = phase_prefix if phase_prefix.endswith("/") else f"{phase_prefix}/"
        if not raw.startswith(prefix):
            return False
        slug = raw[len(prefix) :]
        return bool(slug) and "/" not in slug and bool(_PHASE_SLUG_RE.fullmatch(slug))

    def app_branch_migration_remediation(branch: str) -> str:
        br = (branch or "").strip() or "<current-branch>"
        return (
            "normal-token publisher requires issue/<number>-<slug> or configured "
            f"phase/<slug>. Migrate {br!r} via create_issue_branch.py or /agentcomply."
        )

try:
    import repair_task as repair_task_mod
except ImportError:  # pragma: no cover
    repair_task_mod = None  # type: ignore

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_BLOCKED = 2
EXIT_INCOMPLETE = 78

BLOCKER_REL = Path(".linktrend/completion-blocker.json")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True)


def emit(payload: dict) -> None:
    print(json.dumps(payload, indent=2))


def tree_clean(workdir: Path) -> bool:
    p = run(["git", "status", "--porcelain"], cwd=workdir)
    return p.returncode == 0 and not (p.stdout or "").strip()


def head_sha(workdir: Path) -> str:
    p = run(["git", "rev-parse", "HEAD"], cwd=workdir)
    return (p.stdout or "").strip() if p.returncode == 0 else ""


def head_tree(workdir: Path) -> str:
    p = run(["git", "rev-parse", "HEAD^{tree}"], cwd=workdir)
    return (p.stdout or "").strip() if p.returncode == 0 else ""


def branch_name(workdir: Path) -> str:
    p = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=workdir)
    return (p.stdout or "").strip() if p.returncode == 0 else ""


def origin_tip_matches(workdir: Path) -> tuple[bool, str]:
    branch = branch_name(workdir)
    if not branch or branch == "HEAD":
        return False, "detached_or_missing_branch"
    if branch in {"development", "staging", "main"}:
        return False, f"protected_branch:{branch}"
    phase_prefix = load_delivery_config(workdir).phase_branch_prefix
    if not is_allowed_work_branch(branch, phase_prefix):
        return False, f"disallowed_branch:{branch}"
    # File-backend unit fixtures may omit a real origin remote.
    if os.environ.get("LINKTREND_STATUS_BACKEND") == "file":
        remotes = run(["git", "remote"], cwd=workdir)
        if remotes.returncode != 0 or "origin" not in (remotes.stdout or "").split():
            return True, head_sha(workdir)
    fetch = run(["git", "fetch", "origin", branch], cwd=workdir)
    if fetch.returncode != 0:
        err = ((fetch.stderr or fetch.stdout or "fetch_failed").strip())[:200]
        return False, f"fetch_failed:{err}"
    head = head_sha(workdir)
    p = run(["git", "rev-parse", f"origin/{branch}"], cwd=workdir)
    if p.returncode != 0:
        return False, "missing_origin_tip"
    tip = (p.stdout or "").strip()
    if head != tip:
        return False, f"head_ne_origin ({head[:8]}!={tip[:8]})"
    return True, head


def load_evidence(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"evidence file missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_evidence(evidence: dict, sha: str) -> list[str]:
    missing: list[str] = []
    if int(evidence.get("schemaVersion") or 0) < 1:
        missing.append("evidence_schemaVersion")
    ev_sha = str(evidence.get("headSha") or "")
    if not ev_sha or ev_sha != sha:
        missing.append(f"evidence_sha_mismatch:{ev_sha[:8] or 'empty'}!={sha[:8]}")
    acceptance = str(evidence.get("acceptance") or "").strip()
    if not acceptance:
        missing.append("acceptance_missing")
    classification = str(evidence.get("classification") or "").strip()
    if classification not in {"tests", "docs_only"}:
        missing.append("classification_invalid")
    if classification == "docs_only":
        just = str(evidence.get("docsOnlyJustification") or "").strip()
        if len(just) < 20:
            missing.append("docs_only_justification_too_short")
    cmds = evidence.get("commands")
    if not isinstance(cmds, list) or not cmds:
        missing.append("commands_missing")
    else:
        for i, c in enumerate(cmds):
            if not isinstance(c, dict):
                missing.append(f"command[{i}]_not_object")
                continue
            if not str(c.get("cmd") or "").strip():
                missing.append(f"command[{i}]_cmd_missing")
            try:
                code = int(c.get("exitCode"))
            except (TypeError, ValueError):
                missing.append(f"command[{i}]_exitCode_invalid")
                continue
            if code != 0:
                missing.append(f"command[{i}]_exitCode_{code}")
    return missing


def parse_evidence_commands(raw_commands: list[str]) -> tuple[list[dict], str]:
    cmds = []
    for raw in raw_commands:
        # format: exitCode|cmd  OR  exitCode|path|cmd
        parts = raw.split("|", 2)
        try:
            if len(parts) == 2:
                code_s, cmd = parts
                cmds.append({"cmd": cmd, "exitCode": int(code_s)})
            elif len(parts) == 3:
                code_s, path, cmd = parts
                cmds.append({"cmd": cmd, "exitCode": int(code_s), "evidencePath": path})
            else:
                return [], f"bad --command format: {raw}"
        except ValueError:
            return [], f"bad --command exit code: {raw}"
    return cmds, ""


def _phase_prefix_for_workdir(workdir: Path | None = None) -> str:
    """Resolve phaseBranchPrefix from the target repository root (not ambient cwd)."""
    root = workdir if workdir is not None else Path.cwd()
    return load_delivery_config(root).phase_branch_prefix


def app_backed_route(
    branch: str = "",
    sha: str = "",
    *,
    workdir: Path | None = None,
) -> str:
    """Exact safe normal-token publication route when local credentials are absent.

    Returns empty string when the branch is not publisher-eligible so callers never
    advertise a dispatch command that review_ready_dispatch would reject.
    Prefix eligibility follows the explicit --workdir repository config.
    """
    phase_prefix = _phase_prefix_for_workdir(workdir)
    if branch and not is_app_backed_publish_branch(branch, phase_prefix):
        return ""
    if rs is None:
        return (
            "gh workflow run linktrend-review-ready-publisher.yml "
            "-f branch=<issue/<number>-<slug>|phase/<slug>> "
            "-f sha=<40-char-immutable-sha> "
            "-f dry_run=false"
        )
    return rs.app_backed_review_ready_route(
        branch=branch, sha=sha, phase_prefix=phase_prefix
    )


def _status_backend_name() -> str:
    return (os.environ.get("LINKTREND_STATUS_BACKEND") or "github").strip().lower()


def _review_ready_publish_failure_payload(
    *,
    sha: str,
    branch: str,
    error: str,
    workdir: Path | None = None,
) -> dict:
    """Build fail-closed diagnostics: valid normal-token route or migration path."""
    payload: dict = {
        "mode": "review-ready",
        "state": "failed",
        "published": False,
        "error": error,
        "sha": sha,
        "branch": branch,
        "at": utc_now(),
    }
    phase_prefix = _phase_prefix_for_workdir(workdir)
    if is_app_backed_publish_branch(branch, phase_prefix):
        route = app_backed_route(branch, sha, workdir=workdir)
        payload["normalTokenRoute"] = route
        payload["detail"] = (
            "Local review-ready publish is fail-closed without normal GitHub automation "
            "credentials; use the normal-token workflow route"
        )
    else:
        remediation = app_branch_migration_remediation(branch)
        payload["remediation"] = remediation
        payload["detail"] = remediation
        if "app_publish_requires_issue_branch" not in error:
            payload["error"] = f"app_publish_requires_issue_branch:{branch}; {error}"
    return payload


def publish_ready(
    sha: str,
    issue_id: str,
    notes: str,
    *,
    branch: str = "",
    workdir: Path | None = None,
) -> tuple[bool, str]:
    if rs is None:
        return False, "readiness_status_unavailable"
    try:
        st = rs.mark_sha(sha, issue_id, notes, branch=branch)
        return True, str(st)
    except Exception as e:  # noqa: BLE001
        detail = str(e)
        # Ensure fail-closed credential errors always name the normal-token route.
        if "privileged_publish_requires_github_token" not in detail:
            if any(
                key in detail
                for key in (
                    "AUTOMATION_TOKEN",
                    "GITHUB_TOKEN",
                    "token",
                    "credentials",
                )
            ):
                detail = (
                    f"{detail}; Use normal-token route: "
                    f"{app_backed_route(branch, sha, workdir=workdir)}"
                )
        return False, detail


def ready_status_ok(sha: str) -> tuple[bool, str]:
    if rs is None:
        return False, "readiness_status_unavailable"
    return rs.is_sha_review_ready(sha)


def write_blocker(path: Path, blocker: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blocker, indent=2) + "\n", encoding="utf-8")


def _load_checkpoint_evidence(args: argparse.Namespace, workdir: Path, sha: str) -> tuple[dict | None, str]:
    raw_json = str(getattr(args, "evidence_json", "") or os.environ.get("COMPLETION_EVIDENCE_JSON") or "")
    if raw_json.strip():
        try:
            payload = parse_immutable_evidence_payload(raw_json)
        except Exception as exc:  # noqa: BLE001
            return None, str(getattr(exc, "code", None) or exc)
        return payload, ""
    ev_path = Path(
        args.evidence_file
        or os.environ.get("COMPLETION_EVIDENCE_FILE")
        or ""
    )
    if not str(ev_path):
        default = workdir / ".linktrend/completion-evidence.json"
        ev_path = default if default.is_file() else ev_path
    if not str(ev_path):
        return None, ""
    if not ev_path.is_absolute():
        ev_path = workdir / ev_path
    if not ev_path.is_file():
        return None, ""
    try:
        return load_evidence(ev_path), ""
    except (OSError, json.JSONDecodeError, FileNotFoundError) as exc:
        return None, f"evidence_unreadable:{exc}"


def cmd_write_evidence(args: argparse.Namespace) -> int:
    """Helper to write a valid evidence record for the current HEAD."""
    workdir = Path(args.workdir).resolve()
    sha = head_sha(workdir)
    if not sha:
        emit({"state": "failed", "error": "no_sha"})
        return EXIT_FAILED
    classification = args.classification
    tree = head_tree(workdir)
    payload: dict = {
        "schemaVersion": 1,
        "headSha": sha,
        "classification": classification,
        "acceptance": args.acceptance,
        "commands": [],
        "at": utc_now(),
    }
    cmds, error = parse_evidence_commands(args.command or [])
    if error:
        emit({"state": "failed", "error": error})
        return EXIT_FAILED
    if not cmds:
        emit({"state": "failed", "error": "at least one --command is required"})
        return EXIT_FAILED
    payload["commands"] = cmds
    if classification == "docs_only":
        payload["docsOnlyJustification"] = args.docs_justification
    if any(
        (
            getattr(args, "scoped_diff", False),
            getattr(args, "focused_tests", False),
            getattr(args, "terra_verified", False),
            getattr(args, "manifest_evidence", False),
            str(getattr(args, "proof_class", "") or ""),
        )
    ):
        payload["kind"] = "v25-issue-checkpoint"
        payload["amendment"] = "V25_BOOTSTRAP_LEAN"
        payload["gitTree"] = tree
        payload["pushed"] = True
        payload["scopedDiff"] = bool(getattr(args, "scoped_diff", False))
        payload["focusedTests"] = {"passed": bool(getattr(args, "focused_tests", False))}
        payload["independentTerraVerification"] = bool(getattr(args, "terra_verified", False))
        payload["manifestEvidence"] = bool(getattr(args, "manifest_evidence", False))
        payload["proofClass"] = str(getattr(args, "proof_class", "") or "local")
    rel = (
        args.evidence_file
        or os.environ.get("COMPLETION_EVIDENCE_FILE")
        or ".linktrend/completion-evidence.json"
    )
    out = Path(rel)
    if not out.is_absolute():
        out = workdir / out
    if out.exists() and out.is_dir():
        emit({"state": "failed", "error": f"evidence_file_is_directory:{out}"})
        return EXIT_FAILED
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    emit(
        {
            "mode": "write-evidence",
            "path": str(out),
            "headSha": sha,
            "gitTree": tree,
            "proofClass": payload.get("proofClass", "local"),
        }
    )
    return EXIT_OK


def cmd_checkpoint(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).resolve()
    sha = head_sha(workdir)
    tree = head_tree(workdir)
    tip_ok, tip_detail = origin_tip_matches(workdir)
    evidence, ev_error = _load_checkpoint_evidence(args, workdir, sha)
    payload = {
        "mode": "checkpoint",
        "state": "checkpointed_unfinished",
        "at": utc_now(),
        "branch": branch_name(workdir),
        "sha": sha,
        "gitTree": tree,
        "clean": tree_clean(workdir),
        "pushed": tip_ok,
        "originTipDetail": tip_detail,
        "reviewReadyRequired": False,
        "automationTokenRequired": False,
        "classification": WAIVED_LEGACY_GATE,
        "legacyPublisher": classify_legacy_status("missing"),
        "pass": False,
        "detail": "checkpoint only; no PR; no Review Ready publish",
    }
    if ev_error:
        payload["state"] = "failed"
        payload["error"] = ev_error
        emit(payload)
        return EXIT_FAILED
    if evidence is not None:
        claimed = str(getattr(args, "proof_class", "") or proof_class_of(evidence))
        try:
            reject_local_as_hosted(actual_proof_class=proof_class_of(evidence), claimed_proof_class=claimed)
        except Exception as exc:  # noqa: BLE001
            payload["state"] = "failed"
            payload["error"] = str(getattr(exc, "code", None) or exc)
            emit(payload)
            return EXIT_FAILED
        ok, detail, meta = bind_issue_completion(
            sha=sha,
            tree=tree,
            evidence=evidence,
            review_ready_state="missing",
            claimed_proof_class=claimed,
        )
        payload.update(meta)
        payload["detail"] = detail
        payload["proofClass"] = meta.get("proofClass") or proof_class_of(evidence)
        if ok:
            payload["state"] = "checkpoint_accepted"
            payload["accepted"] = True
            emit(payload)
            return EXIT_OK
        payload["state"] = "failed"
        payload["accepted"] = False
        emit(payload)
        return EXIT_INCOMPLETE
    emit(payload)
    return EXIT_OK


def cmd_review_ready(args: argparse.Namespace) -> int:
    """v2.5: validate substantive evidence, then waive legacy Review Ready publication.

    Never publishes, never PASSes publisher/status, and never bypasses proof.
    """
    workdir = Path(args.workdir).resolve()
    missing: list[str] = []
    sha = head_sha(workdir)
    tree = head_tree(workdir)
    if not sha:
        missing.append("no_sha")

    br = branch_name(workdir)
    phase_prefix = load_delivery_config(workdir).phase_branch_prefix
    if br in {"development", "staging", "main", "HEAD", ""}:
        missing.append("protected_or_detached_branch")
    elif not is_allowed_work_branch(br, phase_prefix):
        missing.append(f"disallowed_branch:{br}")

    if not tree_clean(workdir):
        missing.append("dirty_tree")

    tip_ok, tip_detail = origin_tip_matches(workdir)
    if not tip_ok:
        missing.append(f"origin_tip:{tip_detail}")

    evidence, ev_error = _load_checkpoint_evidence(args, workdir, sha)
    if ev_error:
        missing.append(ev_error)
    if evidence is None:
        ev_path = Path(
            args.evidence_file
            or os.environ.get("COMPLETION_EVIDENCE_FILE")
            or ".linktrend/completion-evidence.json"
        )
        if not ev_path.is_absolute():
            ev_path = workdir / ev_path
        try:
            evidence = load_evidence(ev_path)
        except (OSError, json.JSONDecodeError, FileNotFoundError) as e:
            missing.append(f"evidence_unreadable:{e}")
            evidence = None
    if evidence is not None:
        missing.extend(validate_evidence(evidence, sha))

    if args.tests_ok or os.environ.get("COMPLETION_TESTS_OK"):
        pass
    if evidence is None and (args.tests_ok or os.environ.get("COMPLETION_EVIDENCE")):
        missing.append("bare_flags_insufficient_use_evidence_file")

    if missing:
        payload: dict = {
            "mode": "review-ready",
            "state": "failed",
            "claim": "incomplete",
            "published": False,
            "pass": False,
            "classification": WAIVED_LEGACY_GATE,
            "missing": missing,
            "sha": sha,
            "at": utc_now(),
        }
        emit(payload)
        return EXIT_INCOMPLETE

    ok, detail, meta = bind_issue_completion(
        sha=sha,
        tree=tree,
        evidence=evidence,
        review_ready_state="missing",
    )
    legacy = classify_legacy_status("missing")
    emit(
        {
            "mode": "review-ready",
            "state": "waived_legacy_gate",
            "published": False,
            "pass": False,
            "classification": WAIVED_LEGACY_GATE,
            "checkpointAccepted": bool(ok),
            "checkpointDetail": detail,
            "sha": sha,
            "gitTree": tree,
            "branch": br,
            "at": utc_now(),
            "legacyPublisher": legacy,
            "detail": (
                "Review Ready publication is a waived v2.5 nonrequirement; "
                "Issue checkpoint acceptance does not use AUTOMATION_TOKEN or the legacy publisher"
            ),
            **{k: v for k, v in meta.items() if k not in {"legacyPublisher"}},
        }
    )
    return EXIT_OK


def resolve_repository(workdir: Path) -> tuple[str | None, str]:
    """Resolve owner/repo for durable repair records without printing secrets.

    Preference:
      1) env GITHUB_REPOSITORY / GH_REPO / LINKTREND_REPAIR_REPO
      2) authenticated `gh repo view --json nameWithOwner`
      3) validated `origin` remote URL (HTTPS or SSH), rejecting upstream-only remotes
    """
    for key in ("GITHUB_REPOSITORY", "GH_REPO", "LINKTREND_REPAIR_REPO"):
        val = (os.environ.get(key) or "").strip()
        if val and "/" in val and " " not in val and "local/" not in val:
            return val, f"env:{key}"

    gh = run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        cwd=workdir,
    )
    if gh.returncode == 0:
        name = (gh.stdout or "").strip()
        if name.count("/") == 1 and " " not in name:
            return name, "gh_repo_view"

    # origin only — never fall back to upstream (fork ambiguity)
    origin = run(["git", "remote", "get-url", "--push", "origin"], cwd=workdir)
    if origin.returncode != 0:
        origin = run(["git", "remote", "get-url", "origin"], cwd=workdir)
    if origin.returncode != 0:
        return None, "missing_origin_remote"
    url = (origin.stdout or "").strip()
    # Strip credentials if present in URL without echoing them
    # e.g. https://user:token@github.com/owner/repo.git
    sanitized = url
    owner_repo = ""
    scp_match = re.fullmatch(r"[A-Za-z0-9._-]+@github\.com:(.+)", sanitized)
    if scp_match:
        # GitHub supports both git@github.com and certificate-authority SSH
        # usernames such as org-123@github.com.
        owner_repo = scp_match.group(1)
    elif "://" in sanitized:
        parsed = urlparse(sanitized)
        if parsed.hostname != "github.com":
            return None, "origin_not_github_or_unrecognized"
        owner_repo = parsed.path.lstrip("/")
    elif sanitized.startswith("github.com:"):
        owner_repo = sanitized.split("github.com:", 1)[1]
    else:
        return None, "origin_not_github_or_unrecognized"
    owner_repo = owner_repo.strip()
    if owner_repo.endswith(".git"):
        owner_repo = owner_repo[:-4]
    owner_repo = owner_repo.strip("/")
    segments = owner_repo.split("/")
    if (
        len(segments) != 2
        or any(segment in {"", ".", ".."} for segment in segments)
        or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", segment) for segment in segments)
    ):
        return None, "origin_ambiguous_owner_repo"
    # Reject if both origin and upstream exist and disagree (ambiguous fork layout)
    upstream = run(["git", "remote", "get-url", "upstream"], cwd=workdir)
    if upstream.returncode == 0:
        return None, "ambiguous_origin_and_upstream"
    return owner_repo, "origin_remote"


def cmd_blocked(args: argparse.Namespace) -> int:
    """Write local cache AND attempt a durable repair-task record.

    `.linktrend/completion-blocker.json` is machine-local/gitignored — a cache only.
    Durable cross-machine state is the repair task (GitHub Issue or file backend).
    """
    workdir = Path(args.workdir).resolve()
    repo, repo_source = resolve_repository(workdir)
    reason = args.reason or os.environ.get("COMPLETION_BLOCKER_REASON") or "unspecified"
    next_action = (
        args.next_action
        or os.environ.get("COMPLETION_BLOCKER_NEXT")
        or "Resolve blocker then re-run completion_gate review-ready"
    )
    blocker = {
        "schemaVersion": 1,
        "state": "blocked",
        "at": utc_now(),
        "repository": repo or "",
        "repositorySource": repo_source,
        "branch": branch_name(workdir),
        "sha": head_sha(workdir),
        "failure": reason,
        "evidence": args.evidence or os.environ.get("COMPLETION_EVIDENCE") or "",
        "attemptedRepairs": int(args.attempted_repairs or 0),
        "owner": args.owner or "agent",
        "nextAction": next_action,
        "localCacheOnly": True,
        "durableRecord": False,
    }
    out = Path(args.blocker_file or os.environ.get("COMPLETION_BLOCKER_FILE") or str(BLOCKER_REL))
    if not out.is_absolute():
        out = workdir / out
    write_blocker(out, blocker)

    durable: dict | None = None
    durable_error = ""
    if not repo:
        durable_error = f"repository_unresolved:{repo_source}"
    elif repair_task_mod is None:
        durable_error = "repair_task_unavailable"
    else:
        try:
            fid = repair_task_mod.failure_id(
                repo,
                "immediate_approval_required",
                workflow="completion_gate",
                check="blocked",
                branch=str(blocker["branch"] or ""),
            )
            task = {
                "failureId": fid,
                "id": fid,
                "repository": repo,
                "failureType": "immediate_approval_required",
                "severity": "immediate",
                "branch": blocker["branch"],
                "headSha": blocker["sha"],
                "workflowName": "completion_gate",
                "workflowId": "completion_gate",
                "checkName": "blocked",
                "checkId": "blocked",
                "nextAction": next_action,
                "evidence": {"reason": reason, "localBlocker": str(out)},
            }
            durable = repair_task_mod.upsert_task(repair_task_mod.normalize_task(task))
            blocker["durableRecord"] = True
            blocker["durableFailureId"] = durable.get("failureId")
            blocker["localCacheOnly"] = False
            write_blocker(out, blocker)
        except Exception as exc:  # noqa: BLE001
            durable_error = str(exc)

    payload = {
        "mode": "blocked",
        "state": "blocked",
        "blockerFile": str(out),
        "durableRecord": bool(blocker.get("durableRecord")),
        "durableError": durable_error,
        "warning": (
            ""
            if blocker.get("durableRecord")
            else "LOCAL_CACHE_ONLY: do not claim durable GitHub blocker registration"
        ),
        **blocker,
    }
    if durable:
        payload["durableTask"] = {
            "failureId": durable.get("failureId"),
            "issueNumber": durable.get("issueNumber"),
            "status": durable.get("status") or durable.get("repairStatus"),
        }
    emit(payload)
    return EXIT_BLOCKED


def cmd_status(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).resolve()
    sha = head_sha(workdir)
    tree = head_tree(workdir)
    tip_ok, tip_detail = origin_tip_matches(workdir)
    evidence, _ev_error = _load_checkpoint_evidence(args, workdir, sha)
    checkpoint_ok = False
    checkpoint_detail = "no_evidence"
    if evidence is not None and sha:
        checkpoint_ok, checkpoint_detail, _meta = bind_issue_completion(
            sha=sha,
            tree=tree,
            evidence=evidence,
            review_ready_state="missing",
        )
    ready, ready_detail = ready_status_ok(sha) if sha else (False, "no_sha")
    legacy = classify_legacy_status("success" if ready else "missing")
    state = "checkpointed_unfinished"
    if checkpoint_ok and tip_ok and tree_clean(workdir):
        state = "checkpoint_accepted"
    emit(
        {
            "mode": "status",
            "state": state,
            "sha": sha,
            "gitTree": tree,
            "branch": branch_name(workdir),
            "clean": tree_clean(workdir),
            "originTipOk": tip_ok,
            "originTipDetail": tip_detail,
            "checkpointAccepted": checkpoint_ok,
            "checkpointDetail": checkpoint_detail,
            "reviewReady": False,
            "reviewReadyRequired": False,
            "reviewReadyDetail": ready_detail,
            "legacyPublisher": legacy,
            "classification": WAIVED_LEGACY_GATE,
            "pass": False,
            "at": utc_now(),
        }
    )
    return EXIT_OK


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "mode",
        choices=["checkpoint", "review-ready", "blocked", "status", "write-evidence"],
    )
    ap.add_argument("--workdir", default=os.environ.get("GITOPS_WORKDIR") or ".")
    ap.add_argument("--evidence-file", default="")
    ap.add_argument("--issue-id", default="")
    ap.add_argument("--notes", default="")
    ap.add_argument("--tests-ok", action="store_true", help="ignored alone; evidence file required")
    ap.add_argument("--evidence", default="", help="blocker evidence text")
    ap.add_argument("--reason", default="")
    ap.add_argument("--next-action", default="")
    ap.add_argument("--owner", default="")
    ap.add_argument("--attempted-repairs", default="0")
    ap.add_argument("--blocker-file", default="")
    # write-evidence
    ap.add_argument("--classification", choices=["tests", "docs_only"], default="tests")
    ap.add_argument("--acceptance", default="")
    ap.add_argument("--docs-justification", default="")
    ap.add_argument(
        "--command",
        action="append",
        default=[],
        help="exitCode|cmd  or  exitCode|evidencePath|cmd (repeatable)",
    )
    ap.add_argument("--evidence-json", default="", help="explicit immutable evidence payload JSON")
    ap.add_argument("--proof-class", default="", help="local | hosted | production")
    ap.add_argument("--scoped-diff", action="store_true")
    ap.add_argument("--focused-tests", action="store_true")
    ap.add_argument("--terra-verified", action="store_true")
    ap.add_argument("--manifest-evidence", action="store_true")
    args = ap.parse_args(argv)

    try:
        if args.mode == "checkpoint":
            return cmd_checkpoint(args)
        if args.mode == "review-ready":
            return cmd_review_ready(args)
        if args.mode == "blocked":
            return cmd_blocked(args)
        if args.mode == "status":
            return cmd_status(args)
        if args.mode == "write-evidence":
            return cmd_write_evidence(args)
    except Exception as e:  # noqa: BLE001
        emit({"mode": args.mode, "state": "failed", "error": str(e), "at": utc_now()})
        return EXIT_FAILED
    return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
