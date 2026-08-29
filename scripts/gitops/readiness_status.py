#!/usr/bin/env python3
"""Out-of-diff review-ready signal via GitHub commit statuses (or test file backend).

Context: Linktrend Review Ready
Success on exact SHA ⇒ branch tip is packager-eligible.
Later commits are automatically unready (new SHA has no success status).
Withdrawal posts a non-success status for the same context.

Privileged publish (mark/withdraw) requires a trusted publisher context
(``LINKTREND_TRUSTED_REVIEW_READY_PUBLISHER=1``) plus a resolved token.

Canonical token-resolution contract (documentation, diagnostics, resolver,
and tests must agree):

* Documented input: ``AUTOMATION_TOKEN``.
* Aliases: ``GH_TOKEN``, ``GITHUB_TOKEN``.
* Deterministic precedence: ``AUTOMATION_TOKEN`` then ``GH_TOKEN`` then
  ``GITHUB_TOKEN``. A non-empty documented token is forwarded onto both
  aliases so it cannot be silently discarded.
* Ordinary alias values without the trusted flag never authorize status
  publication. Local implementers without a trusted context use the
  normal-token workflow dispatch route (see app_backed_review_ready_route;
  action=publish or action=withdraw). Token values are never logged.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

CONTEXT = "Linktrend Review Ready"
DEFAULT_BACKEND = "github"  # or "file" for tests (LINKTREND_STATUS_DIR)

# Exact safe normal-token publication route (trusted workflow on default branch).
REVIEW_READY_PUBLISHER_WORKFLOW = "linktrend-review-ready-publisher.yml"
REVIEW_READY_PUBLISHER_WORKFLOW_NAME = "Linktrend Review Ready Publisher"
TRUSTED_PUBLISHER_FLAG = "LINKTREND_TRUSTED_REVIEW_READY_PUBLISHER"
# Canonical first; aliases follow. Do not reorder without updating docs/tests.
PUBLISH_TOKEN_ENVS = ("AUTOMATION_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
APP_PUBLISH_TOKEN_ENVS = PUBLISH_TOKEN_ENVS

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from review_ready_dispatch import (
        app_branch_migration_remediation,
        is_app_backed_issue_branch,
        is_app_backed_publish_branch,
        resolve_phase_branch_prefix,
    )
except ImportError:  # pragma: no cover
    import re

    _ISSUE_BRANCH_RE = re.compile(
        r"^issue/([1-9][0-9]{0,8})-([a-z0-9]+(?:-[a-z0-9]+)*)$"
    )
    _PHASE_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

    def is_app_backed_issue_branch(name: str) -> bool:
        return bool(name) and bool(_ISSUE_BRANCH_RE.fullmatch(str(name).strip()))

    def is_app_backed_publish_branch(name: str, phase_prefix: str = "phase/") -> bool:
        raw = str(name or "").strip()
        if is_app_backed_issue_branch(raw):
            return True
        prefix = phase_prefix if phase_prefix.endswith("/") else f"{phase_prefix}/"
        if not raw.startswith(prefix):
            return False
        slug = raw[len(prefix) :]
        return bool(slug) and "/" not in slug and bool(_PHASE_SLUG_RE.fullmatch(slug))

    def resolve_phase_branch_prefix(repo_root=None) -> str:  # type: ignore[no-untyped-def]
        return "phase/"

    def app_branch_migration_remediation(branch: str) -> str:
        br = (branch or "").strip() or "<current-branch>"
        return (
            "normal-token Linktrend Review Ready publisher accepts verified "
            "issue/<number>-<slug> branches and configured phase/<slug> tips. "
            f"Migrate branch {br!r} via create_issue_branch.py or /agentcomply."
        )


@dataclass
class ReadyStatus:
    state: str  # success | pending | failure | error
    description: str
    target_url: str
    context: str = CONTEXT
    created_at: float = 0.0

    @property
    def is_ready(self) -> bool:
        return self.state == "success"


def build_portfolio_status(
    state: Mapping[str, Any],
    *,
    protected_truth: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the finite, founder-readable status from durable state only."""

    lanes = state.get("lanes") if isinstance(state.get("lanes"), Mapping) else {}
    workers = state.get("workers") if isinstance(state.get("workers"), Mapping) else {}
    lane_rows = list(lanes.values())
    completed = sum(
        1 for lane in lane_rows if isinstance(lane, Mapping) and lane.get("state") == "COMPLETE"
    )
    active = [
        worker
        for worker in workers.values()
        if isinstance(worker, Mapping)
        and str(worker.get("state") or worker.get("status") or "").upper()
        in {"RUNNING", "STARTED", "LIVE", "RESTARTED"}
    ]
    blockers = [str(item) for item in (state.get("blockers") or []) if str(item)]
    rejected = [
        str(lane.get("laneId") or lane_id)
        for lane_id, lane in lanes.items()
        if isinstance(lane, Mapping) and lane.get("state") == "TERMINAL_REJECT"
    ]
    blockers.extend(f"lane={lane_id}:terminal_reject" for lane_id in rejected)
    blocked = [
        str(lane.get("laneId") or lane_id)
        for lane_id, lane in lanes.items()
        if isinstance(lane, Mapping) and lane.get("state") == "BLOCKED"
    ]
    blockers.extend(f"lane={lane_id}:blocked" for lane_id in blocked)
    if protected_truth:
        blockers.extend(str(item) for item in (protected_truth.get("blockers") or []) if str(item))
    total = len(lane_rows)
    percentage = 100 if total == 0 else int(completed * 100 / total)
    if blockers:
        status = "HOLD"
        language = "NOT ISSUED"
        blocker = blockers[0]
    elif completed == total and total > 0:
        status = "DONE"
        language = "FINISHED"
        blocker = ""
    elif active:
        status = "RUNNING"
        language = "RUNNING"
        blocker = ""
    elif total:
        status = "RUNNING"
        language = "ISSUED"
        blocker = ""
    else:
        status = "HOLD"
        language = "NOT ISSUED"
        blocker = "no_canonical_lanes"
    providers = sorted(
        {
            str(worker.get("provider"))
            for worker in active
            if worker.get("provider")
        }
    )
    raw_capacity = state.get("capacity")
    if isinstance(raw_capacity, Mapping):
        capacity = sum(
            int(raw_capacity.get(provider) or 0) if str(raw_capacity.get(provider) or "").lstrip("-").isdigit() else 0
            for provider in ("cursor", "luna")
        )
    else:
        capacity = int(raw_capacity or 0)
    maximum_parallelism = bool(capacity and len(active) >= capacity)
    return {
        "schemaVersion": 1,
        "status": status,
        "language": language,
        "percentage": percentage,
        "completedCanonicalPackets": [
            str(lane.get("packetId") or lane_id)
            for lane_id, lane in lanes.items()
            if isinstance(lane, Mapping) and lane.get("state") == "COMPLETE"
        ],
        "activePartialPackets": [
            str(lane.get("packetId") or lane_id)
            for lane_id, lane in lanes.items()
            if isinstance(lane, Mapping) and lane.get("state") not in {"COMPLETE", "BLOCKED"}
        ],
        "currentWork": [str(worker.get("laneId") or worker.get("workerId")) for worker in active],
        "nextWork": [
            str(lane.get("laneId") or lane_id)
            for lane_id, lane in lanes.items()
            if isinstance(lane, Mapping) and lane.get("state") == "PREPARED"
        ],
        "blocker": blocker,
        "blockers": blockers,
        "dependency": state.get("dependencyGraph") or {},
        "workerProvider": providers,
        "maximumSafeParallelismInUse": maximum_parallelism,
        "safeCapacity": dict(state.get("safeCapacity") or {}),
        "utilizationGap": dict(state.get("utilizationGap") or {}),
        "protectedTruth": dict(protected_truth or {}),
        "heartbeatContinuity": dict(state.get("heartbeatAcceptance") or {
            "status": "PENDING",
            "confirmedScheduledInvocations": 0,
            "consecutiveScheduledInvocations": 0,
            "terminalWorkerReconciled": False,
            "dependencyReadyPacketDispatched": False,
            "requirements": ["consecutive_scheduled_invocations"],
        }),
    }


portfolio_status = build_portfolio_status


def _nonempty_token(raw: str | None) -> str:
    if raw is None:
        return ""
    return str(raw).strip()


def _present_publish_tokens(env: dict[str, str] | None = None) -> dict[str, str]:
    """Return non-empty token env names → values. Never log the values."""
    source = os.environ if env is None else env
    found: dict[str, str] = {}
    for key in PUBLISH_TOKEN_ENVS:
        token = _nonempty_token(source.get(key))
        if token:
            found[key] = token
    return found


def trusted_publisher_context(env: dict[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return (source.get(TRUSTED_PUBLISHER_FLAG) or "").strip() == "1"


def forward_automation_token(
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Forward documented AUTOMATION_TOKEN onto GH_TOKEN/GITHUB_TOKEN aliases.

    Deterministic precedence: a non-empty AUTOMATION_TOKEN always wins and is
    copied onto both aliases so gh CLI / HTTP helpers cannot silently discard
    it in favor of an absent or human alias. When AUTOMATION_TOKEN is unset,
    existing alias values are preserved (trusted workflow github.token path).
    Never logs token values.
    """
    out = dict(os.environ if env is None else env)
    auto = _nonempty_token(out.get("AUTOMATION_TOKEN"))
    if auto:
        out["AUTOMATION_TOKEN"] = auto
        out["GH_TOKEN"] = auto
        out["GITHUB_TOKEN"] = auto
    return out


def automation_token_present(env: dict[str, str] | None = None) -> bool:
    """True when the documented privileged input is set. Does not return the value."""
    source = os.environ if env is None else env
    return bool(_nonempty_token(source.get("AUTOMATION_TOKEN")))


def resolve_app_publish_token() -> str:
    """Return the privileged token for status publication, or empty.

    Requires ``LINKTREND_TRUSTED_REVIEW_READY_PUBLISHER=1``. Resolves
    AUTOMATION_TOKEN then GH_TOKEN then GITHUB_TOKEN. Does not log values.
    """
    if not trusted_publisher_context():
        return ""
    forwarded = forward_automation_token()
    for key in PUBLISH_TOKEN_ENVS:
        token = _nonempty_token(forwarded.get(key))
        if token:
            return token
    return ""


def normalize_status_action(action: str = "publish") -> str:
    """Normalize privileged status action to publish|withdraw."""
    act = (action or "publish").strip().lower()
    if act in {"", "publish", "mark"}:
        return "publish"
    if act == "withdraw":
        return "withdraw"
    return "publish"


def app_backed_review_ready_route(
    *,
    branch: str = "",
    sha: str = "",
    dry_run: bool = False,
    action: str = "publish",
    reason: str = "",
    phase_prefix: str | None = None,
) -> str:
    """Exact safe normal-token route for publishing or withdrawing Review Ready.

    Only embeds a concrete branch when it matches verified issue/<number>-<slug>
    or a configured phase/<slug> tip. Legacy allowed prefixes (feature/, dev/, …)
    must never appear as a runnable dispatch command — those inputs are rejected
    by review_ready_dispatch.
    """
    raw = (branch or "").strip()
    prefix = (
        phase_prefix
        if phase_prefix is not None
        else resolve_phase_branch_prefix()
    )
    if is_app_backed_publish_branch(raw, prefix):
        br = raw
    else:
        br = "<issue/<number>-<slug>|phase/<slug>>"
    tip = (sha or "").strip() or "<40-char-immutable-sha>"
    dry = "true" if dry_run else "false"
    act = normalize_status_action(action)
    parts = [
        f"gh workflow run {REVIEW_READY_PUBLISHER_WORKFLOW}",
        f"-f branch={br}",
        f"-f sha={tip}",
        f"-f action={act}",
        f"-f dry_run={dry}",
    ]
    if act == "withdraw":
        why = (reason or "withdrawn").strip() or "withdrawn"
        # Keep reason token-safe for copy/paste diagnostics (no spaces/newlines).
        why = why.replace("\n", " ").replace("\r", " ").strip()[:140] or "withdrawn"
        if " " in why:
            why = why.replace(" ", "-")
        parts.append(f"-f reason={why}")
    return " ".join(parts)


def missing_app_publish_token_error(
    *,
    branch: str = "",
    sha: str = "",
    action: str = "publish",
    reason: str = "",
    phase_prefix: str | None = None,
) -> str:
    """Fail closed when the local status write lacks automation credentials."""
    act = normalize_status_action(action)
    raw = (branch or "").strip()
    prefix = (
        phase_prefix
        if phase_prefix is not None
        else resolve_phase_branch_prefix()
    )
    prefix_msg = (
        "privileged_publish_requires_github_token: "
        "AUTOMATION_TOKEN required in trusted publisher context "
        f"({TRUSTED_PUBLISHER_FLAG}=1); "
        "GH_TOKEN/GITHUB_TOKEN are aliases (AUTOMATION_TOKEN precedes); "
        "no human-token fallback for Linktrend Review Ready status writes. "
        "no GH_TOKEN/GITHUB_TOKEN fallback for untrusted local publish. "
    )
    if raw and not is_app_backed_publish_branch(raw, prefix):
        return (
            prefix_msg
            + f"app_publish_requires_issue_branch:{raw}. "
            + app_branch_migration_remediation(raw)
        )
    route = app_backed_review_ready_route(
        branch=branch,
        sha=sha,
        action=act,
        reason=reason,
        phase_prefix=prefix,
    )
    present = automation_token_present()
    present_note = (
        "Documented AUTOMATION_TOKEN is present and must be forwarded to gh "
        "via forward_automation_token (never log the value). "
        if present
        else ""
    )
    return prefix_msg + present_note + f"Use normal-token route: {route}"


def _read_status_token() -> str:
    """Return a token for status reads (aliases allowed; no trusted flag)."""
    forwarded = forward_automation_token()
    for key in PUBLISH_TOKEN_ENVS:
        token = _nonempty_token(forwarded.get(key))
        if token:
            return token
    return ""


def _gh_token() -> str:
    """Backward-compatible alias for the explicit job-scoped token."""
    return _read_status_token()


def _repo_slug() -> str:
    if os.environ.get("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    try:
        url = subprocess.check_output(
            ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
            text=True,
        ).strip()
        return url
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError("cannot resolve repository slug") from e


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
            "User-Agent": "linktrend-review-ready",
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


class FileStatusBackend:
    """Test/offline backend storing statuses under LINKTREND_STATUS_DIR/<sha>.json."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, sha: str) -> Path:
        return self.root / f"{sha.lower()}.json"

    def get_latest(self, sha: str) -> ReadyStatus | None:
        p = self._path(sha)
        if not p.is_file():
            return None
        rows = json.loads(p.read_text(encoding="utf-8"))
        if not rows:
            return None
        last = rows[-1]
        return ReadyStatus(
            state=last["state"],
            description=last.get("description") or "",
            target_url=last.get("target_url") or "",
            created_at=float(last.get("created_at") or 0),
        )

    def post(self, sha: str, state: str, description: str, target_url: str = "") -> ReadyStatus:
        p = self._path(sha)
        rows = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else []
        entry = {
            "state": state,
            "description": description,
            "target_url": target_url,
            "context": CONTEXT,
            "created_at": time.time(),
        }
        # Idempotent success: do not duplicate identical success
        if rows:
            last = rows[-1]
            if (
                last.get("state") == state
                and last.get("description") == description
                and state == "success"
            ):
                return ReadyStatus(
                    state=state,
                    description=description,
                    target_url=target_url,
                    created_at=float(last.get("created_at") or 0),
                )
        rows.append(entry)
        p.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        return ReadyStatus(state=state, description=description, target_url=target_url, created_at=entry["created_at"])


class GitHubStatusBackend:
    def __init__(self, repo: str | None = None, token: str | None = None):
        self.repo = repo or _repo_slug()
        # Explicit/ambient token is for reads only. Publish ignores it.
        self._read_token = (token or _read_status_token()).strip()
        # Compat attribute: never use for privileged publish.
        self.token = self._read_token

    def get_latest(self, sha: str) -> ReadyStatus | None:
        if not self._read_token:
            raise RuntimeError(
                "status read token missing "
                "(AUTOMATION_TOKEN preferred; "
                "GH_TOKEN/GITHUB_TOKEN allowed for reads only)"
            )
        url = f"https://api.github.com/repos/{self.repo}/commits/{sha}/statuses"
        rows = _api("GET", url, self._read_token)
        mine = [r for r in rows if (r.get("context") or "") == CONTEXT]
        if not mine:
            return None
        # API returns newest first
        last = mine[0]
        return ReadyStatus(
            state=last.get("state") or "error",
            description=last.get("description") or "",
            target_url=last.get("target_url") or "",
            created_at=0.0,
        )

    def post(
        self,
        sha: str,
        state: str,
        description: str,
        target_url: str = "",
        *,
        branch: str = "",
        action: str = "publish",
        reason: str = "",
    ) -> ReadyStatus:
        # Privileged publish/withdraw is available only inside the trusted workflow.
        pub = resolve_app_publish_token()
        if not pub:
            raise RuntimeError(
                missing_app_publish_token_error(
                    branch=branch,
                    sha=sha,
                    action=action,
                    reason=reason or description,
                )
            )
        existing = self.get_latest(sha) if self._read_token else None
        if (
            existing
            and existing.state == state
            and existing.description == description
            and state == "success"
        ):
            return existing
        # Idempotent success without a read token: still POST (GitHub accepts duplicates).
        body = {
            "state": state,
            "description": description[:140],
            "context": CONTEXT,
        }
        if target_url:
            body["target_url"] = target_url
        _api("POST", f"https://api.github.com/repos/{self.repo}/statuses/{sha}", pub, body)
        return ReadyStatus(state=state, description=description, target_url=target_url)


def get_backend():
    backend = (os.environ.get("LINKTREND_STATUS_BACKEND") or DEFAULT_BACKEND).lower()
    if backend == "file":
        root = Path(os.environ.get("LINKTREND_STATUS_DIR") or ".git/linktrend-ready-status")
        return FileStatusBackend(root)
    return GitHubStatusBackend()


def is_sha_review_ready(sha: str) -> tuple[bool, str]:
    st = get_backend().get_latest(sha)
    if not st:
        return False, "no_ready_status"
    if st.is_ready:
        return True, st.description or "ready"
    return False, f"status_{st.state}"


def publish_review_ready(
    sha: str,
    issue_id: str,
    notes: str = "",
    target_url: str = "",
    *,
    branch: str = "",
) -> ReadyStatus:
    """Reusable privileged publication helper (normal automation token or file backend only)."""
    desc = f"issue={issue_id}"
    if notes:
        desc = f"{desc}; {notes}"[:140]
    backend = get_backend()
    if isinstance(backend, GitHubStatusBackend):
        return backend.post(sha, "success", desc, target_url=target_url, branch=branch)
    return backend.post(sha, "success", desc, target_url=target_url)


def mark_sha(
    sha: str,
    issue_id: str,
    notes: str = "",
    target_url: str = "",
    *,
    branch: str = "",
) -> ReadyStatus:
    return publish_review_ready(
        sha, issue_id, notes, target_url=target_url, branch=branch
    )


def withdraw_sha(sha: str, reason: str = "withdrawn", *, branch: str = "") -> ReadyStatus:
    why = (reason or "withdrawn")[:140]
    backend = get_backend()
    if isinstance(backend, GitHubStatusBackend):
        return backend.post(
            sha,
            "failure",
            why,
            branch=branch,
            action="withdraw",
            reason=why,
        )
    return backend.post(sha, "failure", why)


def _parse_cli_options(argv: list[str]) -> tuple[list[str], str, Path | None]:
    """Extract optional --branch / --workdir from argv; return (remaining, branch, workdir)."""
    out: list[str] = []
    branch = ""
    workdir: Path | None = None
    i = 0
    while i < len(argv):
        if argv[i] == "--branch" and i + 1 < len(argv):
            branch = argv[i + 1]
            i += 2
            continue
        if argv[i].startswith("--branch="):
            branch = argv[i].split("=", 1)[1]
            i += 1
            continue
        if argv[i] == "--workdir" and i + 1 < len(argv):
            workdir = Path(argv[i + 1]).resolve()
            i += 2
            continue
        if argv[i].startswith("--workdir="):
            workdir = Path(argv[i].split("=", 1)[1]).resolve()
            i += 1
            continue
        out.append(argv[i])
        i += 1
    if workdir is None:
        env_wd = (os.environ.get("GITOPS_WORKDIR") or "").strip()
        if env_wd:
            workdir = Path(env_wd).resolve()
    return out, branch, workdir


def _cli_phase_prefix(workdir: Path | None) -> str:
    """Resolve configured phaseBranchPrefix for CLI mark/withdraw eligibility."""
    return resolve_phase_branch_prefix(workdir)


def main(argv: list[str]) -> int:
    args, branch, workdir = _parse_cli_options(argv)
    if len(args) < 2:
        print(
            "Usage: readiness_status.py <get|mark|withdraw> <sha> [issue_id|reason] "
            "[notes] [--branch issue/<n>-<slug>] [--workdir <repo>]",
            file=sys.stderr,
        )
        return 2
    cmd = args[1]
    phase_prefix = _cli_phase_prefix(workdir)
    if cmd == "get":
        sha = args[2]
        ok, detail = is_sha_review_ready(sha)
        print(json.dumps({"sha": sha, "ready": ok, "detail": detail}))
        return 0 if ok else 1
    if cmd == "mark":
        sha, issue_id = args[2], args[3]
        notes = args[4] if len(args) > 4 else ""
        try:
            st = mark_sha(sha, issue_id, notes, branch=branch)
        except RuntimeError as e:
            payload: dict[str, Any] = {
                "ok": False,
                "sha": sha,
                "error": str(e),
            }
            if is_app_backed_publish_branch(branch, phase_prefix):
                payload["normalTokenRoute"] = app_backed_review_ready_route(
                    branch=branch,
                    sha=sha,
                    action="publish",
                    phase_prefix=phase_prefix,
                )
            else:
                payload["remediation"] = app_branch_migration_remediation(
                    branch or "<issue/<number>-<slug>|phase/<slug>>"
                )
            print(json.dumps(payload, indent=2))
            return 78
        print(json.dumps({"sha": sha, "state": st.state, "description": st.description}))
        return 0
    if cmd == "withdraw":
        sha = args[2]
        reason = args[3] if len(args) > 3 else "withdrawn"
        try:
            st = withdraw_sha(sha, reason, branch=branch)
        except RuntimeError as e:
            payload = {
                "ok": False,
                "sha": sha,
                "error": str(e),
            }
            if is_app_backed_publish_branch(branch, phase_prefix):
                payload["normalTokenRoute"] = app_backed_review_ready_route(
                    branch=branch,
                    sha=sha,
                    action="withdraw",
                    reason=reason,
                    phase_prefix=phase_prefix,
                )
            else:
                payload["remediation"] = app_branch_migration_remediation(
                    branch or "<issue/<number>-<slug>|phase/<slug>>"
                )
            print(json.dumps(payload, indent=2))
            return 78
        print(
            json.dumps(
                {
                    "ok": True,
                    "sha": sha,
                    "state": st.state,
                    "description": st.description,
                }
            )
        )
        return 0
    print(f"unknown command {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
