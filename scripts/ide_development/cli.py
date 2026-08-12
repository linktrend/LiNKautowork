"""CLI for the IDE Development installer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .constants import (
    EXIT_CONFLICT,
    EXIT_DRIFT,
    EXIT_ERROR,
    EXIT_INVALID_PACKAGE,
    EXIT_OK,
    EXIT_ROLLBACK_FAILURE,
)
from .engine import (
    run_drift,
    run_install_or_update,
    run_plan,
    run_rollback,
    run_verify,
    run_version,
)
from .errors import InstallerError
from .release_candidate import (
    create_release_candidate,
    verify_release_candidate_archive,
)


def _emit(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=False))
        return
    # Human-readable compact summary plus JSON block for agents
    command = payload.get("command")
    summary = payload.get("summary") or payload.get("verify") or {}
    print(f"command={command}")
    if "packageVersion" in payload:
        print(f"packageVersion={payload.get('packageVersion')}")
    if "installerVersion" in payload:
        print(f"installerVersion={payload.get('installerVersion')}")
    if summary:
        print(f"summary={json.dumps(summary, sort_keys=True)}")
    if payload.get("conflicts"):
        print(f"conflicts={len(payload['conflicts'])}")
    if payload.get("drift") and command in {"drift", "verify", "plan", "install", "update"}:
        print(f"drift={len(payload['drift'])}")
    print("--- json ---")
    print(json.dumps(payload, indent=2, sort_keys=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ide-development",
        description=(
            "Transactional cross-platform installer for IDE Development managed core v2. "
            "Stdlib only. Physical files. Fail-closed conflicts."
        ),
    )

    # Common options are attached to each subparser so `cmd --package ...` works
    # on Python 3.9 (parent optionals after the subcommand are otherwise rejected).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON only",
    )
    common.add_argument(
        "--package",
        type=Path,
        default=None,
        help="Package/system repository root (default: detect from this script)",
    )
    common.add_argument(
        "--target",
        "--repo",
        dest="target",
        type=Path,
        default=None,
        help="Target consumer git repository (default: cwd for most commands). --repo is an alias.",
    )
    common.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan only; guarantee no repository or git-metadata writes",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "plan",
        parents=[common],
        help="Build a deterministic install/update plan (always dry-run)",
    )
    sub.add_parser(
        "install",
        parents=[common],
        help="Install managed core into a consumer repository",
    )
    sub.add_parser(
        "update",
        parents=[common],
        help="Update an existing managed-core installation",
    )
    sub.add_parser(
        "drift",
        parents=[common],
        help="Report precise managed-file drift categories",
    )
    sub.add_parser(
        "verify",
        parents=[common],
        help="Verify installation matches package + installed-state",
    )
    sub.add_parser(
        "version",
        parents=[common],
        help="Show installer and package versions",
    )
    sub.add_parser(
        "rollback",
        parents=[common],
        help="Restore exact pre-change bytes from last transaction",
    )

    # Release-candidate packaging (Lane D) — nested actions; not a consumer install.
    rc = sub.add_parser(
        "release-candidate",
        help="Deterministic release-candidate packaging (create/verify archives)",
    )
    rc_sub = rc.add_subparsers(dest="rc_action", required=True)
    rc_common = argparse.ArgumentParser(add_help=False)
    rc_common.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON only",
    )
    rc_create = rc_sub.add_parser(
        "create",
        parents=[rc_common],
        help="Validate, regenerate manifest, build RC archives",
    )
    rc_create.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: build/release-candidate)",
    )
    rc_create.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow dirty worktree (local proofs only; production must be clean)",
    )
    rc_create.add_argument(
        "--skip-install-verify",
        action="store_true",
        help="Skip extract+install verification",
    )
    rc_create.add_argument(
        "--skip-evidence",
        action="store_true",
        help="Skip lane evidence path checks (still requires packaging unit tests)",
    )
    rc_verify = rc_sub.add_parser(
        "verify",
        parents=[rc_common],
        help="Extract an RC archive and install into a clean temp repo",
    )
    rc_verify.add_argument(
        "--archive",
        type=Path,
        required=True,
        help="Path to .tar.gz or .zip RC archive",
    )
    rc_verify.add_argument(
        "--expected-version",
        default="2.1.5",
        help="Expected package version (default 2.1.5)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    as_json = bool(getattr(args, "json", False))
    dry_run = bool(getattr(args, "dry_run", False))
    target_arg = getattr(args, "target", None)
    package_arg = getattr(args, "package", None)
    target = Path(target_arg) if target_arg is not None else Path.cwd()
    package = Path(package_arg) if package_arg is not None else None

    try:
        if args.command == "release-candidate":
            if args.rc_action == "create":
                payload = create_release_candidate(
                    output_dir=Path(args.output_dir) if args.output_dir else None,
                    allow_dirty=bool(args.allow_dirty),
                    skip_install_verify=bool(args.skip_install_verify),
                    skip_evidence=bool(args.skip_evidence),
                )
                _emit(payload, as_json=as_json)
                return EXIT_OK
            if args.rc_action == "verify":
                payload = verify_release_candidate_archive(
                    archive_path=Path(args.archive),
                    expected_version=str(args.expected_version),
                )
                _emit(payload, as_json=as_json)
                return EXIT_OK
            parser.error(f"Unknown release-candidate action: {args.rc_action}")
            return EXIT_ERROR
        if args.command == "plan":
            result = run_plan(target=target, package=package, command="plan", dry_run=True)
        elif args.command == "install":
            result = run_install_or_update(
                target=target,
                package=package,
                command="install",
                dry_run=dry_run,
            )
        elif args.command == "update":
            result = run_install_or_update(
                target=target,
                package=package,
                command="update",
                dry_run=dry_run,
            )
        elif args.command == "drift":
            result = run_drift(target=target, package=package)
        elif args.command == "verify":
            result = run_verify(target=target, package=package)
        elif args.command == "version":
            result = run_version(target=target if target_arg else None, package=package)
        elif args.command == "rollback":
            result = run_rollback(target=target)
        else:  # pragma: no cover
            parser.error(f"Unknown command: {args.command}")
            return EXIT_ERROR
    except InstallerError as exc:
        payload = {
            "schemaVersion": 1,
            "ok": False,
            "command": args.command,
            "error": exc.message,
            "details": exc.details,
            "exitCode": exc.exit_code,
        }
        _emit(payload, as_json=as_json)
        return int(exc.exit_code)
    except BrokenPipeError:  # pragma: no cover
        return EXIT_OK
    except Exception as exc:  # pragma: no cover
        payload = {
            "schemaVersion": 1,
            "ok": False,
            "command": args.command,
            "error": str(exc),
            "exitCode": EXIT_ERROR,
        }
        _emit(payload, as_json=as_json)
        return EXIT_ERROR

    _emit(result.payload, as_json=as_json)
    return int(result.exit_code)


# Re-export exit codes for wrappers/tests
__all__ = [
    "main",
    "build_parser",
    "EXIT_OK",
    "EXIT_ERROR",
    "EXIT_DRIFT",
    "EXIT_CONFLICT",
    "EXIT_INVALID_PACKAGE",
    "EXIT_ROLLBACK_FAILURE",
]


if __name__ == "__main__":
    sys.exit(main())
