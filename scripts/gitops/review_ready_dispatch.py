#!/usr/bin/env python3
"""Validate workflow_dispatch inputs for normal-token Review Ready publisher.

Pure, unit-testable input validation only. Does not mint tokens, publish
statuses, read secrets, or execute untrusted branch code.

Trusted workflow: .github/workflows/linktrend-review-ready-publisher.yml
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Studio normal-token publisher accepts verified issue/<number>-<slug> (digits)
# and configured phase/<slug> Phase-integration tips. Legacy allowlist prefixes
# (feature/, dev/, …) remain rejected.
ISSUE_BRANCH_RE = re.compile(r"^issue/([1-9][0-9]{0,8})-([a-z0-9]+(?:-[a-z0-9]+)*)$")
PHASE_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

PROTECTED_BRANCHES = frozenset({"development", "staging", "main", "HEAD"})
DEFAULT_EVIDENCE_PATH = ".linktrend/completion-evidence.json"
MAX_EVIDENCE_JSON_BYTES = 256_000
DEFAULT_PHASE_PREFIX = "phase/"
BRANCH_KIND_ISSUE = "issue"
BRANCH_KIND_PHASE = "phase"


def normalize_phase_prefix(prefix: str | None) -> str:
    raw = (prefix or DEFAULT_PHASE_PREFIX).strip() or DEFAULT_PHASE_PREFIX
    return raw if raw.endswith("/") else f"{raw}/"


def resolve_phase_branch_prefix(repo_root: Path | None = None) -> str:
    """Resolve phaseBranchPrefix from delivery-mode config (default phase/)."""
    try:
        from delivery_modes import load_delivery_config

        root = repo_root if repo_root is not None else Path.cwd()
        return normalize_phase_prefix(load_delivery_config(root).phase_branch_prefix)
    except Exception:  # noqa: BLE001 — fail closed to default prefix
        return DEFAULT_PHASE_PREFIX


def is_app_backed_issue_branch(name: str) -> bool:
    """True only for verified issue/<number>-<slug> (issue-branch safeguard)."""
    return bool(name) and bool(ISSUE_BRANCH_RE.fullmatch(str(name).strip()))


def is_app_backed_phase_branch(
    name: str, phase_prefix: str = DEFAULT_PHASE_PREFIX
) -> bool:
    """True for configured phase/<lowercase-slug> Phase-integration tips."""
    raw = str(name or "").strip()
    prefix = normalize_phase_prefix(phase_prefix)
    if not raw or not raw.startswith(prefix):
        return False
    slug = raw[len(prefix) :]
    return bool(slug) and "/" not in slug and bool(PHASE_SLUG_RE.fullmatch(slug))


def is_app_backed_publish_branch(
    name: str, phase_prefix: str = DEFAULT_PHASE_PREFIX
) -> bool:
    """True when the normal-token publisher may bind this branch (issue slug or Phase tip)."""
    return is_app_backed_issue_branch(name) or is_app_backed_phase_branch(
        name, phase_prefix
    )


def app_branch_migration_remediation(branch: str) -> str:
    """Actionable migration path when a legacy allowed branch cannot use normal-token publish."""
    br = (branch or "").strip() or "<current-branch>"
    return (
        "normal-token Linktrend Review Ready publisher accepts verified "
        "issue/<number>-<slug> branches (digits + lowercase slug) and configured "
        "phase/<slug> Phase-integration tips. "
        f"Branch {br!r} may still be allowed for ordinary work/Pull but cannot "
        "dispatch linktrend-review-ready-publisher. "
        "Migrate: run `python3 scripts/gitops/create_issue_branch.py \"…\"` "
        "or `/agentcomply` onto issue/<n>-<slug>, move the tip there, push, "
        "rewrite completion evidence for the new HEAD SHA, then re-run "
        "`python3 scripts/gitops/completion_gate.py review-ready`. "
        "For Phase tips, use the configured phaseBranchPrefix slug form."
    )


class DispatchValidationError(ValueError):
    """Fail-closed validation error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ValidatedDispatch:
    branch: str
    sha: str
    issue_number: int
    issue_slug: str
    evidence_path: str
    dry_run: bool
    repository: str
    evidence_json: str  # empty when not supplied; raw JSON text when supplied
    action: str  # publish | withdraw
    reason: str  # withdrawal reason when action=withdraw; else empty
    branch_kind: str = BRANCH_KIND_ISSUE  # issue | phase


def _reject(code: str, message: str) -> None:
    raise DispatchValidationError(code, message)


def parse_dry_run(raw: Any) -> bool:
    """Parse Actions boolean / CLI dry-run values. Fail closed on ambiguity."""
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return False
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", ""}:
        return False
    _reject("dry_run_invalid", f"dry_run must be boolean-like, got {raw!r}")
    raise AssertionError("unreachable")


def validate_branch(
    branch: str,
    *,
    phase_prefix: str = DEFAULT_PHASE_PREFIX,
) -> tuple[str, int, str]:
    """Return (branch_kind, issue_number, slug).

    issue_number is 0 for Phase branches. Legacy allowlist prefixes are rejected.
    """
    if branch is None:
        _reject("branch_missing", "branch is required")
    name = str(branch).strip()
    if not name:
        _reject("branch_missing", "branch is required")
    if any(ch.isspace() for ch in name):
        _reject("branch_whitespace", "branch must not contain whitespace")
    if name.startswith("refs/") or name.startswith("origin/"):
        _reject(
            "branch_mutable_ref",
            "branch must be a bare issue/<n>-<slug> or phase/<slug> name, not a ref",
        )
    if ".." in name or name.startswith("/") or "\\" in name:
        _reject("branch_path_illegal", "branch must not look like a path")
    if name in PROTECTED_BRANCHES or name.split("/", 1)[0] in {
        "development",
        "staging",
        "main",
    }:
        _reject("branch_protected", f"protected or non-issue branch forbidden: {name}")

    m = ISSUE_BRANCH_RE.fullmatch(name)
    if m:
        issue_number = int(m.group(1))
        slug = m.group(2)
        if issue_number <= 0:
            _reject("branch_issue_number_invalid", "issue number must be positive")
        return BRANCH_KIND_ISSUE, issue_number, slug

    prefix = normalize_phase_prefix(phase_prefix)
    if name.startswith(prefix):
        slug = name[len(prefix) :]
        if slug and "/" not in slug and PHASE_SLUG_RE.fullmatch(slug):
            return BRANCH_KIND_PHASE, 0, slug
        _reject(
            "branch_not_issue_slug",
            "phase branch must match <phaseBranchPrefix><lowercase-slug>",
        )

    _reject(
        "branch_not_issue_slug",
        "branch must match issue/<number>-<slug> or configured phase/<slug>",
    )
    raise AssertionError("unreachable")


def validate_sha(sha: str) -> str:
    if sha is None:
        _reject("sha_missing", "sha is required")
    tip = str(sha).strip()
    if not tip:
        _reject("sha_missing", "sha is required")
    if any(ch.isspace() for ch in tip):
        _reject("sha_whitespace", "sha must not contain whitespace")
    if tip.startswith("refs/") or tip in {"HEAD", "FETCH_HEAD"} or "/" in tip:
        _reject("sha_not_immutable", "sha must be an immutable 40-char commit id, not a ref")
    if len(tip) != 40 or not FULL_SHA_RE.fullmatch(tip):
        _reject("sha_not_full", "sha must be exactly 40 hexadecimal characters")
    return tip.lower()


def validate_evidence_path(path: str | None) -> str:
    raw = DEFAULT_EVIDENCE_PATH if path is None else str(path).strip()
    if not raw:
        raw = DEFAULT_EVIDENCE_PATH
    if any(ch.isspace() for ch in raw):
        _reject("evidence_path_whitespace", "evidence_path must not contain whitespace")
    if raw.startswith("/") or raw.startswith("~") or re.match(r"^[A-Za-z]:[\\/]", raw):
        _reject("evidence_path_absolute", "evidence_path must be a relative path in the tip tree")
    parts = Path(raw).parts
    if not parts or any(p in {"", ".", ".."} for p in parts):
        _reject("evidence_path_illegal", "evidence_path must not contain . or .. segments")
    if raw.endswith("/") or raw.endswith("\\"):
        _reject("evidence_path_illegal", "evidence_path must be a file path")
    return raw


def validate_repository(*, github_repository: str, requested_repository: str | None) -> str:
    expected = (github_repository or "").strip()
    if not expected or not REPO_SLUG_RE.fullmatch(expected):
        _reject(
            "repository_context_invalid",
            "GITHUB_REPOSITORY must be set to owner/repo for this dispatch",
        )
    if requested_repository is None:
        return expected
    requested = str(requested_repository).strip()
    if not requested:
        return expected
    if not REPO_SLUG_RE.fullmatch(requested):
        _reject("repository_format_invalid", "repository must look like owner/repo")
    if requested.lower() != expected.lower():
        _reject(
            "repository_mismatch",
            "dispatch cannot publish for another repository "
            f"(requested={requested}, context={expected})",
        )
    return expected


def validate_evidence_json(raw: str | None) -> str:
    """Optional inline evidence JSON. Empty string means 'use tip file'."""
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_EVIDENCE_JSON_BYTES:
        _reject("evidence_json_too_large", "evidence_json exceeds size limit")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        _reject("evidence_json_invalid", f"evidence_json is not valid JSON: {e}")
    if not isinstance(payload, dict):
        _reject("evidence_json_not_object", "evidence_json must be a JSON object")
    # Structural minimum only; full schema check happens in the trusted workflow
    # against the immutable SHA after tip verification.
    if "schemaVersion" not in payload or "headSha" not in payload:
        _reject(
            "evidence_json_missing_fields",
            "evidence_json must include schemaVersion and headSha",
        )
    return text


def validate_issue_number_binding(
    issue_number: int,
    explicit_issue: str | None,
    *,
    branch_kind: str = BRANCH_KIND_ISSUE,
) -> None:
    if explicit_issue is None:
        return
    text = str(explicit_issue).strip()
    if not text:
        return
    if branch_kind == BRANCH_KIND_PHASE:
        _reject(
            "issue_number_not_applicable",
            "issue_number is only valid for issue/<number>-<slug> branches",
        )
    if not re.fullmatch(r"[1-9][0-9]{0,8}", text):
        _reject("issue_number_invalid", "issue_number must be a positive integer string")
    if int(text) != issue_number:
        _reject(
            "issue_branch_mismatch",
            f"issue_number {text} does not match branch issue/{issue_number}-…",
        )


def validate_action(raw: Any) -> str:
    """Normalize action to publish|withdraw. Fail closed on unknown values."""
    if raw is None:
        return "publish"
    text = str(raw).strip().lower()
    if text in {"", "publish", "mark"}:
        return "publish"
    if text == "withdraw":
        return "withdraw"
    _reject("action_invalid", f"action must be publish or withdraw, got {raw!r}")
    raise AssertionError("unreachable")


def validate_reason(raw: Any, *, action: str) -> str:
    """Withdrawal reason; ignored for publish. Fail closed on newlines."""
    if action != "withdraw":
        return ""
    if raw is None:
        return "withdrawn"
    text = str(raw).strip() or "withdrawn"
    if "\n" in text or "\r" in text:
        _reject("reason_invalid", "reason must be a single line")
    return text[:140]


def validate_dispatch_inputs(
    *,
    branch: str,
    sha: str,
    dry_run: Any = False,
    evidence_path: str | None = None,
    evidence_json: str | None = None,
    github_repository: str,
    repository: str | None = None,
    issue_number: str | None = None,
    action: Any = "publish",
    reason: Any = None,
    phase_prefix: str | None = None,
    repo_root: Path | None = None,
) -> ValidatedDispatch:
    """Validate and normalize all dispatch inputs. Raises DispatchValidationError."""
    prefix = (
        normalize_phase_prefix(phase_prefix)
        if phase_prefix is not None
        else resolve_phase_branch_prefix(repo_root)
    )
    kind, issue_num, slug = validate_branch(branch, phase_prefix=prefix)
    tip = validate_sha(sha)
    act = validate_action(action)
    why = validate_reason(reason, action=act)
    dry = parse_dry_run(dry_run)
    repo = validate_repository(
        github_repository=github_repository,
        requested_repository=repository,
    )
    validate_issue_number_binding(issue_num, issue_number, branch_kind=kind)
    # Withdraw does not require completion evidence; publish still does.
    if act == "withdraw":
        path = DEFAULT_EVIDENCE_PATH
        ev_json = ""
    else:
        path = validate_evidence_path(evidence_path)
        ev_json = validate_evidence_json(evidence_json)
    if kind == BRANCH_KIND_ISSUE:
        canonical = f"issue/{issue_num}-{slug}"
    else:
        canonical = f"{prefix}{slug}"
    return ValidatedDispatch(
        branch=canonical,
        sha=tip,
        issue_number=issue_num,
        issue_slug=slug,
        evidence_path=path,
        dry_run=dry,
        repository=repo,
        evidence_json=ev_json,
        action=act,
        reason=why,
        branch_kind=kind,
    )


def _write_github_output(validated: ValidatedDispatch) -> None:
    out_path = os.environ.get("GITHUB_OUTPUT")
    if not out_path:
        return
    lines = [
        f"branch={validated.branch}",
        f"sha={validated.sha}",
        f"issue_number={validated.issue_number}",
        f"issue_slug={validated.issue_slug}",
        f"branch_kind={validated.branch_kind}",
        f"evidence_path={validated.evidence_path}",
        f"dry_run={'true' if validated.dry_run else 'false'}",
        f"repository={validated.repository}",
        f"action={validated.action}",
        f"reason={validated.reason}",
        f"has_evidence_json={'true' if validated.evidence_json else 'false'}",
    ]
    with open(out_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
        if validated.evidence_json:
            # Multiline safe output for Actions.
            fh.write("evidence_json<<LINKTREND_EVIDENCE_EOF\n")
            fh.write(validated.evidence_json)
            if not validated.evidence_json.endswith("\n"):
                fh.write("\n")
            fh.write("LINKTREND_EVIDENCE_EOF\n")


def _resolve_evidence_json_arg(args: argparse.Namespace) -> str | None:
    env_name = (args.evidence_json_env or "").strip()
    if env_name:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env_name):
            raise DispatchValidationError(
                "evidence_json_env_invalid",
                "evidence_json_env must be a simple environment variable name",
            )
        return os.environ.get(env_name)
    if args.evidence_json:
        return args.evidence_json
    return None


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        evidence_json = _resolve_evidence_json_arg(args)
        validated = validate_dispatch_inputs(
            branch=args.branch,
            sha=args.sha,
            dry_run=args.dry_run,
            evidence_path=args.evidence_path,
            evidence_json=evidence_json,
            github_repository=args.github_repository
            or os.environ.get("GITHUB_REPOSITORY", ""),
            repository=args.repository,
            issue_number=args.issue_number,
            action=args.action,
            reason=args.reason,
        )
    except DispatchValidationError as e:
        payload = {"ok": False, "error": e.code, "detail": e.message}
        print(json.dumps(payload, indent=2))
        return 78
    payload = {"ok": True, **asdict(validated)}
    # Avoid dumping potentially large evidence into step summaries by default.
    if not args.include_evidence_json and "evidence_json" in payload:
        payload["evidence_json"] = bool(validated.evidence_json)
    print(json.dumps(payload, indent=2))
    if args.github_output:
        _write_github_output(validated)
    return 0


def _self_test() -> int:
    """Lightweight unit checks for CI/local proof without network."""
    failures: list[str] = []

    def expect_ok(**kwargs: Any) -> ValidatedDispatch | None:
        try:
            return validate_dispatch_inputs(
                github_repository="linktrend/IDE-Development",
                **kwargs,
            )
        except DispatchValidationError as e:
            failures.append(f"unexpected fail {e.code}: {e.message} for {kwargs!r}")
            return None

    def expect_err(code: str, **kwargs: Any) -> None:
        try:
            validate_dispatch_inputs(
                github_repository="linktrend/IDE-Development",
                **kwargs,
            )
            failures.append(f"expected {code} for {kwargs!r}")
        except DispatchValidationError as e:
            if e.code != code:
                failures.append(f"expected {code}, got {e.code} for {kwargs!r}")

    good_sha = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    ok = expect_ok(
        branch="issue/44-add-app-backed-review-ready-publisher-and-produc",
        sha=good_sha,
        dry_run="false",
    )
    if ok:
        assert ok.issue_number == 44
        assert ok.sha == good_sha
        assert ok.dry_run is False
        assert ok.repository == "linktrend/IDE-Development"

    expect_ok(
        branch="issue/44-add-app-backed-review-ready-publisher-and-produc",
        sha=good_sha.upper(),
        dry_run=True,
        evidence_json=json.dumps(
            {"schemaVersion": 1, "headSha": good_sha, "classification": "tests"}
        ),
    )

    expect_err("branch_not_issue_slug", branch="feature/44-x", sha=good_sha)
    expect_err("branch_not_issue_slug", branch="dev/macmini", sha=good_sha)
    expect_err("branch_not_issue_slug", branch="issue/44-Bad_Slug", sha=good_sha)
    if is_app_backed_issue_branch("feature/44-x") or is_app_backed_issue_branch("dev/x"):
        failures.append("legacy allowed prefixes must not be publisher-eligible")
    if not is_app_backed_issue_branch(
        "issue/44-add-app-backed-review-ready-publisher-and-produc"
    ):
        failures.append("canonical issue branch must be publisher-eligible")
    if not is_app_backed_phase_branch("phase/wp-01-demo"):
        failures.append("default phase branch must be publisher-eligible")
    if not is_app_backed_publish_branch("phase/wp-01-demo"):
        failures.append("phase tip must be normal-token publish eligible")
    if is_app_backed_phase_branch("wave/wp-01-demo"):
        failures.append("custom prefix wave/ must not match default phase/")
    if not is_app_backed_phase_branch("wave/wp-01-demo", phase_prefix="wave/"):
        failures.append("custom phaseBranchPrefix must be publisher-eligible")
    if is_app_backed_publish_branch("feature/44-x"):
        failures.append("feature/* must remain publisher-ineligible")
    phase_ok = expect_ok(branch="phase/wp-01-demo", sha=good_sha, dry_run="false")
    if phase_ok:
        if phase_ok.branch_kind != BRANCH_KIND_PHASE:
            failures.append("phase branch_kind expected")
        if phase_ok.issue_number != 0:
            failures.append("phase issue_number must be 0")
        if phase_ok.issue_slug != "wp-01-demo":
            failures.append("phase slug mismatch")
    expect_err(
        "issue_number_not_applicable",
        branch="phase/wp-01-demo",
        sha=good_sha,
        issue_number="44",
    )
    rem = app_branch_migration_remediation("feature/44-x")
    if "create_issue_branch.py" not in rem or "feature/44-x" not in rem:
        failures.append("migration remediation missing actionable path")
    expect_err("branch_protected", branch="development", sha=good_sha)
    expect_err("branch_mutable_ref", branch="refs/heads/issue/44-x", sha=good_sha)
    expect_err("sha_not_full", branch="issue/44-x", sha="abc")
    expect_err("sha_not_immutable", branch="issue/44-x", sha="HEAD")
    expect_err(
        "repository_mismatch",
        branch="issue/44-x",
        sha=good_sha,
        repository="evil/other",
    )
    expect_err(
        "issue_branch_mismatch",
        branch="issue/44-x",
        sha=good_sha,
        issue_number="99",
    )
    expect_err(
        "evidence_path_absolute",
        branch="issue/44-x",
        sha=good_sha,
        evidence_path="/tmp/evil.json",
    )
    expect_err(
        "evidence_path_illegal",
        branch="issue/44-x",
        sha=good_sha,
        evidence_path="../secrets.json",
    )
    expect_err(
        "evidence_json_not_object",
        branch="issue/44-x",
        sha=good_sha,
        evidence_json="[]",
    )
    expect_err("dry_run_invalid", branch="issue/44-x", sha=good_sha, dry_run="maybe")
    expect_err("action_invalid", branch="issue/44-x", sha=good_sha, action="delete")
    ok_w = expect_ok(
        branch="issue/44-add-app-backed-review-ready-publisher-and-produc",
        sha=good_sha,
        action="withdraw",
        reason="rollback",
    )
    if ok_w:
        assert ok_w.action == "withdraw"
        assert ok_w.reason == "rollback"
        assert ok_w.evidence_json == ""

    if failures:
        print(json.dumps({"ok": False, "failures": failures}, indent=2))
        return 1
    print(json.dumps({"ok": True, "tests": "review_ready_dispatch.self_test"}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="Validate dispatch inputs (fail closed)")
    v.add_argument("--branch", required=True)
    v.add_argument("--sha", required=True)
    v.add_argument("--dry-run", default="false")
    v.add_argument(
        "--action",
        default="publish",
        help="publish (default) or withdraw Linktrend Review Ready",
    )
    v.add_argument(
        "--reason",
        default="withdrawn",
        help="Withdrawal reason when --action withdraw",
    )
    v.add_argument("--evidence-path", default=DEFAULT_EVIDENCE_PATH)
    v.add_argument(
        "--evidence-json",
        default="",
        help="Optional inline completion evidence JSON when tip file is unavailable",
    )
    v.add_argument(
        "--evidence-json-env",
        default="",
        help="Read evidence JSON from this environment variable name (avoids shell quoting)",
    )
    v.add_argument(
        "--github-repository",
        default="",
        help="Owning repo context (defaults to GITHUB_REPOSITORY)",
    )
    v.add_argument(
        "--repository",
        default="",
        help="Optional explicit repo; must match GITHUB_REPOSITORY when set",
    )
    v.add_argument(
        "--issue-number",
        default="",
        help="Optional explicit issue number; must match branch",
    )
    v.add_argument(
        "--github-output",
        action="store_true",
        help="Append validated fields to GITHUB_OUTPUT",
    )
    v.add_argument(
        "--include-evidence-json",
        action="store_true",
        help="Include full evidence_json in stdout JSON (default: boolean only)",
    )

    sub.add_parser("self-test", help="Run built-in unit checks")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "self-test":
        return _self_test()
    if args.cmd == "validate":
        # Normalize empty optional strings to None/""
        if not args.repository:
            args.repository = None
        if not args.issue_number:
            args.issue_number = None
        return cmd_validate(args)
    print(f"unknown command {args.cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
