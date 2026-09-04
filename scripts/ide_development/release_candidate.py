"""Deterministic release-candidate packaging for IDE Development managed-core v2.

Stdlib only. Builds reproducible portable archives under ignored ``build/``.
Never publishes tags, GitHub releases, or credentials.

Usage:
  python3 scripts/ide-development.py release-candidate create --json
  python3 scripts/ide-development.py release-candidate verify --archive build/.../pkg.tar.gz --json
  python3 -m ide_development.release_candidate create --json
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

from . import build_manifest as bm
from .constants import (
    EXIT_ERROR,
    EXIT_INVALID_PACKAGE,
    EXIT_OK,
    INSTALLER_VERSION,
    PACKAGE_NAME,
    PACKAGE_VERSION_TARGET,
    RC_ARCHIVE_EPOCH,
    RC_ARCHIVE_EPOCH_UTC,
    RC_BUILD_DIR_REL,
    RC_CHECKSUMS_NAME,
    RC_EXCLUSION_CLASSES,
    RC_KIND,
    RC_METADATA_NAME,
    RC_REQUIRED_EVIDENCE_RELS,
    RC_REQUIRED_SCHEMA_RELS,
    RC_REQUIRED_TEST_RELS,
    RC_SCHEMA_VERSION,
    SCHEMA_VERSION,
)
from .errors import InstallerError, InvalidPackageError
from .hashing import sha256_bytes, sha256_file

try:
    from scripts.gitops.generated_output_closure import ClosureError, finalize_candidate
except ModuleNotFoundError:  # pragma: no cover - package-style execution
    from gitops.generated_output_closure import ClosureError, finalize_candidate  # type: ignore

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]

# Credential / secret heuristics (content scan of staged package bytes).
# Require PEM-style material (not mere detector string literals).
_SECRET_PATTERNS = (
    re.compile(
        r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{64,}",
        re.I,
    ),
    re.compile(
        r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|private[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+=]{20,}"
    ),
    re.compile(r"(?i)github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?i)gh[pousr]_[A-Za-z0-9_]{36,}"),
    re.compile(r"(?i)xox[baprs]-[A-Za-z0-9-]{10,}"),
)


def _is_code_call_assignment(text: str, match: re.Match[str]) -> bool:
    """Recognize a multiline variable assignment to a function call.

    The package guard scans source bytes independently of the AST-based
    scanner. A line such as ``api_key = require_cursor_cloud_api_key(`` names
    a resolver and contains no secret literal. Only an open-call form whose
    balanced arguments contain no credential-looking literal is exempted.
    Literal values and completed calls remain covered.
    """
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    if line_end < 0:
        line_end = len(text)
    line = text[line_start:line_end].strip().strip("`").strip()
    call = re.search(
        r"(?:api[_-]?key|secret[_-]?key|access[_-]?token|private[_-]?key)"
        r"\s*[:=]\s*[A-Za-z_][A-Za-z0-9_.]*\(\s*",
        line,
        flags=re.IGNORECASE,
    )
    if call is None:
        return False
    opening = text.find("(", line_start + call.start())
    if opening < 0:
        return False

    # Find the matching close while respecting quoted strings. This keeps a
    # multiline resolver call exempt while allowing the guard to inspect its
    # arguments for a literal credential.
    depth = 0
    quote = ""
    escaped = False
    closing = -1
    for index in range(opening, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                closing = index
                break
    if closing < 0:
        return False

    arguments = text[opening + 1 : closing]
    if re.search(r"['\"][A-Za-z0-9_\-/+=]{20,}['\"]", arguments):
        return False
    for token_pattern in _SECRET_PATTERNS[2:]:
        if token_pattern.search(arguments):
            return False
    return True

_INSTALL_INSTRUCTIONS = f"""\
# Install from release candidate (extracted archive)

1. Extract the archive to a directory that is NOT the consumer repository.
   - macOS/Linux: tar -xzf ide-development-managed-core-{PACKAGE_VERSION_TARGET}.tar.gz
   - Windows: Expand-Archive ide-development-managed-core-{PACKAGE_VERSION_TARGET}.zip
2. Initialize or choose a consumer git repository (separate from the package root).
3. Install:
   python3 <extracted>/scripts/ide-development.py install \\
     --package <extracted> --target <consumer-repo> --json
4. Verify:
   python3 <extracted>/scripts/ide-development.py verify \\
     --package <extracted> --target <consumer-repo> --json
5. Confirm packageVersion is {PACKAGE_VERSION_TARGET} and verify reports ok.

Claude surfaces are out of scope. Secrets are never packaged.
"""

_ROLLBACK_INSTRUCTIONS = """\
# Rollback after a managed-core install/update

From the consumer repository (not the package root):

  python3 <package-or-system>/scripts/ide-development.py rollback --target <consumer-repo> --json

Rollback restores exact pre-change bytes from the last successful transaction
journal under .git/ide-development/. It does not delete consumer-owned files
outside managed ownership and never touches GitHub settings or credentials.

If rollback fails, stop and escalate — do not force-overwrite consumer bytes.
"""


class ReleaseCandidateError(InstallerError):
    """RC packaging refusal / failure."""

    exit_code = EXIT_INVALID_PACKAGE


def _repo_rel(path: Path, *, root: Path = REPO_ROOT) -> str:
    rel = path.resolve().relative_to(root.resolve())
    text = rel.as_posix()
    if text.startswith("/") or ".." in PurePosixPath(text).parts:
        raise ReleaseCandidateError(f"Path escapes repository root: {path}")
    return text


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _git_output(args: Sequence[str], *, cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise ReleaseCandidateError(
            f"git {' '.join(args)} failed",
            details={"stderr": (proc.stderr or "").strip()[:500]},
        )
    return (proc.stdout or "").strip()


def worktree_is_dirty(repo_root: Path = REPO_ROOT) -> bool:
    status = _git_output(["status", "--porcelain"], cwd=repo_root)
    return bool(status.strip())


def source_commit_sha(repo_root: Path = REPO_ROOT) -> str:
    sha = _git_output(["rev-parse", "HEAD"], cwd=repo_root)
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ReleaseCandidateError(f"Unexpected HEAD SHA: {sha!r}")
    return sha


def _normalize_version(text: str) -> str:
    return text.strip().lstrip("v")


def validate_versions(repo_root: Path = REPO_ROOT) -> str:
    root_ver = _normalize_version(_read_text(repo_root / "VERSION"))
    managed_ver = _normalize_version(_read_text(repo_root / "core" / "managed-core" / "VERSION"))
    errors: list[str] = []
    if root_ver != managed_ver:
        errors.append(f"VERSION alignment drift: root={root_ver!r} managed={managed_ver!r}")
    if managed_ver != PACKAGE_VERSION_TARGET:
        errors.append(
            f"package VERSION must be {PACKAGE_VERSION_TARGET} (got {managed_ver!r})"
        )
    if INSTALLER_VERSION != PACKAGE_VERSION_TARGET:
        errors.append(
            f"installer version must be {PACKAGE_VERSION_TARGET} (got {INSTALLER_VERSION!r})"
        )
    if errors:
        raise ReleaseCandidateError(
            "Version inconsistent",
            details={"errors": errors},
        )
    return managed_ver


def validate_schemas(repo_root: Path = REPO_ROOT) -> list[str]:
    missing: list[str] = []
    identities: list[str] = []
    for rel in RC_REQUIRED_SCHEMA_RELS:
        path = repo_root / rel
        if not path.is_file() or path.is_symlink():
            missing.append(rel)
            continue
        try:
            json.loads(_read_text(path))
        except json.JSONDecodeError as exc:
            raise ReleaseCandidateError(
                f"Schema JSON invalid: {rel}",
                details={"error": str(exc)},
            ) from exc
        identities.append(rel)
    if missing:
        raise ReleaseCandidateError(
            "Required schemas missing",
            details={"missing": missing},
        )
    return identities


def validate_tests_and_evidence(repo_root: Path = REPO_ROOT) -> list[str]:
    """Refuse when required packaging tests or evidence identities are absent."""
    missing: list[str] = []
    present: list[str] = []
    for rel in (*RC_REQUIRED_TEST_RELS, *RC_REQUIRED_EVIDENCE_RELS):
        path = repo_root / rel
        if path.is_file() and not path.is_symlink():
            present.append(rel)
            continue
        if path.is_dir() and not path.is_symlink():
            # Directory evidence/tests allowed when non-empty of regular files.
            has_file = any(p.is_file() and not p.is_symlink() for p in path.rglob("*"))
            if has_file:
                present.append(rel)
                continue
        missing.append(rel)
    if missing:
        raise ReleaseCandidateError(
            "Required tests/evidence missing",
            details={"missing": missing},
        )
    return present


def regenerate_manifest_deterministically(repo_root: Path = REPO_ROOT) -> tuple[bytes, str]:
    """Write MANIFEST twice; require byte-identical second run. Return bytes + hash.

    Supports an alternate source-tree root so App-backed release publication can
    rebuild from a data-only checkout while executing trusted packaging code.
    """
    with bm.repo_root_context(repo_root):
        bm.write_manifest()
        first = bm.MANIFEST_PATH.read_bytes()
        bm.write_manifest()
        second = bm.MANIFEST_PATH.read_bytes()
        if first != second:
            raise ReleaseCandidateError(
                "Manifest regeneration is not byte-identical across consecutive runs",
                details={"firstBytes": len(first), "secondBytes": len(second)},
            )
        errors = bm.verify_manifest()
        if errors:
            raise ReleaseCandidateError(
                "Manifest verify failed after regeneration",
                details={"errors": errors},
            )
        return first, sha256_bytes(first)


def _is_excluded_rel(rel: str) -> bool:
    lowered = rel.lower()
    parts = PurePosixPath(rel).parts
    if not parts:
        return True
    if parts[0] in {".git", "build", "node_modules", "dist", ".cache", ".linktrend", "__pycache__"}:
        return True
    if parts[0] in {"claude", ".claude"}:
        return True
    if any(p == "__pycache__" or p.endswith(".egg-info") for p in parts):
        return True
    name = parts[-1]
    if name in {".ds_store", ".env", ".env.local"} or name.startswith(".env."):
        return True
    if name.endswith((".pyc", ".pyo", ".log", ".tmp", ".swp")):
        return True
    if "secret" in lowered and lowered.endswith((".pem", ".key", ".p12", ".pfx")):
        return True
    return False


def collect_package_paths(repo_root: Path = REPO_ROOT) -> list[str]:
    """Repository-relative paths that belong in the portable RC archive."""
    manifest_path = repo_root / "core" / "managed-core" / "MANIFEST.json"
    if not manifest_path.is_file():
        raise ReleaseCandidateError("MANIFEST.json missing; regenerate first")
    obj = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths: set[str] = set()
    for row in obj.get("files") or []:
        src = row.get("source")
        if not isinstance(src, str):
            raise ReleaseCandidateError("Manifest entry missing source", details={"entry": row})
        paths.add(PurePosixPath(src).as_posix())

    # Always include package identity + schemas + root VERSION + MANIFEST.
    extras = [
        "VERSION",
        "core/managed-core/VERSION",
        "core/managed-core/MANIFEST.json",
        "core/managed-core/README.md",
        "core/managed-core/INDEX.yaml",
        *[str(PurePosixPath(r)) for r in RC_REQUIRED_SCHEMA_RELS],
        "INSTALL.md",
        "ROLLBACK.md",
    ]
    for rel in extras:
        paths.add(rel)

    ordered = sorted(p for p in paths if not _is_excluded_rel(p))
    return ordered


def _refuse_symlink(path: Path, rel: str) -> None:
    if path.is_symlink():
        raise ReleaseCandidateError(
            f"Refusing symlink in package: {rel}",
            details={"path": rel},
        )


def _scan_bytes_for_secrets(rel: str, data: bytes) -> None:
    # Skip binary-ish payloads
    if b"\0" in data[:4096]:
        return
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            for match in pattern.finditer(text):
                if pattern is _SECRET_PATTERNS[1] and _is_code_call_assignment(text, match):
                    continue
                raise ReleaseCandidateError(
                    f"Refusing to package credential-like content: {rel}",
                    details={"path": rel, "pattern": pattern.pattern},
                )


def _scan_bytes_for_host_paths(rel: str, data: bytes, *, repo_root: Path) -> None:
    if b"\0" in data[:4096]:
        return
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return
    abs_root = str(repo_root.resolve())
    # Only refuse when the absolute checkout path appears (host leakage).
    if re.search(rf"(?<![A-Za-z0-9_]){re.escape(abs_root)}(?:[/\\]|$)", text):
        raise ReleaseCandidateError(
            f"Refusing host absolute path in package content: {rel}",
            details={"path": rel},
        )
    # Windows drive-letter absolute paths
    if re.search(r"(?m)(?:^|[\"'\\s])[A-Za-z]:\\\\", text):
        # Allow docs that mention Windows paths abstractly via schema patterns only —
        # refuse concrete user home-style paths.
        if re.search(r"(?i)Users\\\\|\\\\Users\\\\|home\\\\", text):
            raise ReleaseCandidateError(
                f"Refusing host absolute Windows path in package content: {rel}",
                details={"path": rel},
            )


def stage_package_tree(
    *,
    repo_root: Path,
    staging_root: Path,
    paths: Iterable[str],
) -> list[str]:
    """Copy physical package files into staging with repo-relative layout."""
    staged: list[str] = []
    for rel in paths:
        src = repo_root / rel
        if rel in {"INSTALL.md", "ROLLBACK.md"} and not src.is_file():
            # Synthesize instructions into the archive only (not committed source).
            content = (
                _INSTALL_INSTRUCTIONS if rel == "INSTALL.md" else _ROLLBACK_INSTRUCTIONS
            ).encode("utf-8")
            dest = staging_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            staged.append(rel)
            continue
        if not src.exists():
            raise ReleaseCandidateError(f"Package source missing: {rel}")
        _refuse_symlink(src, rel)
        if not src.is_file():
            raise ReleaseCandidateError(f"Package source is not a regular file: {rel}")
        data = src.read_bytes()
        _scan_bytes_for_secrets(rel, data)
        _scan_bytes_for_host_paths(rel, data, repo_root=repo_root)
        dest = staging_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        # Preserve executable bit when present; otherwise 0644.
        mode = src.stat().st_mode
        if mode & stat.S_IXUSR:
            dest.chmod(0o755)
        else:
            dest.chmod(0o644)
        staged.append(rel)
    return sorted(staged)


def _fixed_tarinfo(name: str, size: int, mode: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=name)
    info.size = size
    info.mtime = int(RC_ARCHIVE_EPOCH)
    info.mode = mode & 0o777
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.type = tarfile.REGTYPE
    return info


def build_tar_gz(staging_root: Path, archive_path: Path, identities: Sequence[str]) -> int:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for rel in sorted(identities):
            path = staging_root / rel
            data = path.read_bytes()
            mode = 0o755 if (path.stat().st_mode & stat.S_IXUSR) else 0o644
            info = _fixed_tarinfo(rel, len(data), mode)
            tar.addfile(info, io.BytesIO(data))
    payload = raw.getvalue()
    # Deterministic gzip wrapper (mtime=0, fixed filename).
    with open(archive_path, "wb") as out:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=out,
            mtime=0,
            compresslevel=9,
        ) as gz:
            gz.write(payload)
    return archive_path.stat().st_size


def build_zip(staging_root: Path, archive_path: Path, identities: Sequence[str]) -> int:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    # ZipInfo date_time from deterministic epoch.
    dt = (2026, 8, 1, 0, 0, 0)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel in sorted(identities):
            path = staging_root / rel
            data = path.read_bytes()
            info = zipfile.ZipInfo(filename=rel, date_time=dt)
            mode = 0o755 if (path.stat().st_mode & stat.S_IXUSR) else 0o644
            info.external_attr = (mode & 0o777) << 16
            info.create_system = 3  # UNIX
            zf.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return archive_path.stat().st_size


def _archive_basename(version: str) -> str:
    return f"{PACKAGE_NAME}-{version}"


def write_checksums(*, output_dir: Path, version: str, archives: list[dict[str, Any]]) -> Path:
    files = []
    for row in archives:
        files.append(
            {
                "path": row["path"],
                "sha256": row["sha256"],
                "bytes": row["bytes"],
            }
        )
    # Also checksum the metadata file if present later — caller may append.
    payload = {
        "schemaVersion": RC_SCHEMA_VERSION,
        "kind": "ide-development-release-candidate-checksums",
        "packageVersion": version,
        "files": files,
    }
    path = output_dir / RC_CHECKSUMS_NAME
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_metadata(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_archive_install(
    *,
    archive_path: Path,
    format_name: str,
    expected_version: str,
    expected_archive_sha: str,
) -> dict[str, Any]:
    """Extract archive into a clean temp dir and install into a fresh git repo."""
    with tempfile.TemporaryDirectory(prefix="ide-rc-verify-") as tmp:
        tmp_path = Path(tmp)
        extract_root = tmp_path / "package"
        extract_root.mkdir()
        if format_name == "tar.gz":
            with tarfile.open(archive_path, "r:gz") as tar:
                # Fail closed on absolute / parent members.
                for member in tar.getmembers():
                    name = member.name.replace("\\", "/")
                    if name.startswith("/") or ".." in PurePosixPath(name).parts:
                        raise ReleaseCandidateError(
                            f"Archive member path unsafe: {member.name}"
                        )
                    if member.issym() or member.islnk():
                        raise ReleaseCandidateError(
                            f"Archive contains link (refused): {member.name}"
                        )
                tar.extractall(extract_root)
        elif format_name == "zip":
            with zipfile.ZipFile(archive_path, "r") as zf:
                for name in zf.namelist():
                    norm = name.replace("\\", "/")
                    if norm.startswith("/") or ".." in PurePosixPath(norm).parts:
                        raise ReleaseCandidateError(f"Archive member path unsafe: {name}")
                zf.extractall(extract_root)
        else:
            raise ReleaseCandidateError(f"Unknown archive format: {format_name}")

        # Package root is extract_root (repo-relative layout).
        package_root = extract_root
        if not (package_root / "core" / "managed-core" / "MANIFEST.json").is_file():
            raise ReleaseCandidateError(
                "Extracted archive missing core/managed-core/MANIFEST.json"
            )

        consumer = tmp_path / "consumer"
        consumer.mkdir()
        subprocess.run(["git", "init"], cwd=str(consumer), check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "rc-verify@example.com"],
            cwd=str(consumer),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "RC Verify"],
            cwd=str(consumer),
            check=True,
            capture_output=True,
        )
        (consumer / "README.md").write_text("# consumer\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(consumer), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(consumer),
            check=True,
            capture_output=True,
        )

        entry = package_root / "scripts" / "ide-development.py"
        if not entry.is_file():
            raise ReleaseCandidateError("Extracted archive missing scripts/ide-development.py")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(package_root / "scripts")
        install = subprocess.run(
            [
                sys.executable,
                str(entry),
                "install",
                "--package",
                str(package_root),
                "--target",
                str(consumer),
                "--json",
            ],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            env=env,
        )
        if install.returncode != 0:
            raise ReleaseCandidateError(
                "Install from extracted archive failed",
                details={
                    "exitCode": install.returncode,
                    "stdout": (install.stdout or "")[-2000:],
                    "stderr": (install.stderr or "")[-2000:],
                },
            )
        install_payload = json.loads(install.stdout)
        version_proc = subprocess.run(
            [
                sys.executable,
                str(entry),
                "version",
                "--package",
                str(package_root),
                "--target",
                str(consumer),
                "--json",
            ],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            env=env,
        )
        if version_proc.returncode != 0:
            raise ReleaseCandidateError(
                "version from extracted archive failed",
                details={"stderr": (version_proc.stderr or "")[-1000:]},
            )
        version_payload = json.loads(version_proc.stdout)
        installed_version = version_payload.get("packageVersion") or install_payload.get(
            "packageVersion"
        )
        if installed_version != expected_version:
            raise ReleaseCandidateError(
                "Installed version mismatch after archive install",
                details={
                    "expected": expected_version,
                    "actual": installed_version,
                },
            )
        return {
            "ok": True,
            "installedVersion": installed_version,
            "packageChecksum": expected_archive_sha,
            "archive": _safe_name(archive_path.name),
            "installExitCode": install.returncode,
        }


def _safe_name(name: str) -> str:
    # Filename only — never host paths in machine output.
    return PurePosixPath(name.replace("\\", "/")).name


def create_release_candidate(
    *,
    repo_root: Path = REPO_ROOT,
    output_dir: Path | None = None,
    allow_dirty: bool = False,
    skip_install_verify: bool = False,
    skip_evidence: bool = False,
    candidate_baseline_sha: str | None = None,
    candidate_baseline_ref: str | None = None,
) -> dict[str, Any]:
    """Create deterministic RC archives + metadata under build/."""
    try:
        finalize_candidate(
            repo_root,
            baseline_sha=candidate_baseline_sha,
            baseline_ref=candidate_baseline_ref,
        )
    except ClosureError as exc:
        raise ReleaseCandidateError(
            "Generated-output closure failed before candidate construction",
            details={"code": exc.code, **exc.diagnostics, "detail": exc.detail},
        ) from exc
    if not allow_dirty and worktree_is_dirty(repo_root):
        raise ReleaseCandidateError(
            "Refusing release-candidate creation: worktree is dirty",
            details={"hint": "Commit or stash changes, or pass --allow-dirty for local proofs only"},
        )

    version = validate_versions(repo_root)
    schema_ids = validate_schemas(repo_root)
    evidence_ids: list[str] = []
    if skip_evidence:
        # Still require core packaging unit tests to exist.
        for rel in RC_REQUIRED_TEST_RELS:
            if not (repo_root / rel).is_file():
                raise ReleaseCandidateError(
                    "Required packaging tests missing",
                    details={"missing": [rel]},
                )
            evidence_ids.append(rel)
    else:
        evidence_ids = validate_tests_and_evidence(repo_root)

    manifest_bytes, manifest_hash = regenerate_manifest_deterministically(repo_root)
    commit = source_commit_sha(repo_root)
    identities = collect_package_paths(repo_root)

    out = output_dir or (repo_root / RC_BUILD_DIR_REL)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ide-rc-stage-") as tmp:
        staging = Path(tmp) / "stage"
        staging.mkdir()
        staged = stage_package_tree(repo_root=repo_root, staging_root=staging, paths=identities)
        base = _archive_basename(version)
        tar_rel = f"{RC_BUILD_DIR_REL}/{base}.tar.gz"
        zip_rel = f"{RC_BUILD_DIR_REL}/{base}.zip"
        tar_path = out / f"{base}.tar.gz"
        zip_path = out / f"{base}.zip"
        tar_bytes = build_tar_gz(staging, tar_path, staged)
        zip_bytes = build_zip(staging, zip_path, staged)
        # Prove second archive build is byte-identical.
        tar_path_2 = out / f"{base}.tar.gz.repro"
        zip_path_2 = out / f"{base}.zip.repro"
        build_tar_gz(staging, tar_path_2, staged)
        build_zip(staging, zip_path_2, staged)
        if tar_path.read_bytes() != tar_path_2.read_bytes():
            raise ReleaseCandidateError("tar.gz archive is not reproducible across consecutive builds")
        if zip_path.read_bytes() != zip_path_2.read_bytes():
            raise ReleaseCandidateError("zip archive is not reproducible across consecutive builds")
        tar_path_2.unlink()
        zip_path_2.unlink()

        tar_sha = sha256_file(tar_path)
        zip_sha = sha256_file(zip_path)
        archives = [
            {
                "format": "tar.gz",
                "path": tar_rel,
                "sha256": tar_sha,
                "bytes": tar_bytes,
            },
            {
                "format": "zip",
                "path": zip_rel,
                "sha256": zip_sha,
                "bytes": zip_bytes,
            },
        ]

        install_verify: dict[str, Any] | None = None
        if not skip_install_verify:
            install_verify = verify_archive_install(
                archive_path=tar_path,
                format_name="tar.gz",
                expected_version=version,
                expected_archive_sha=tar_sha,
            )

        metadata = {
            "schemaVersion": RC_SCHEMA_VERSION,
            "kind": RC_KIND,
            "packageName": PACKAGE_NAME,
            "packageVersion": version,
            "sourceCommit": commit,
            "manifestHash": manifest_hash,
            "archives": archives,
            "supportedPlatforms": ["darwin", "linux", "windows"],
            "acceptanceEvidence": evidence_ids,
            "provenance": {
                "identities": staged,
                "exclusions": list(RC_EXCLUSION_CLASSES),
                "toolchain": {
                    "python": sys.version.split()[0],
                    "archiveEpochUtc": RC_ARCHIVE_EPOCH_UTC,
                },
            },
            "installInstructions": _INSTALL_INSTRUCTIONS.strip(),
            "rollbackInstructions": _ROLLBACK_INSTRUCTIONS.strip(),
            "createdAt": RC_ARCHIVE_EPOCH_UTC,
            "notes": (
                "Generated binary archives belong under ignored build/; "
                "never commit archives. No tag or GitHub release is created."
            ),
        }
        meta_path = out / RC_METADATA_NAME
        write_metadata(meta_path, metadata)
        # Checksums cover archives + metadata only (not the checksums file itself).
        checksum_payload = {
            "schemaVersion": RC_SCHEMA_VERSION,
            "kind": "ide-development-release-candidate-checksums",
            "packageVersion": version,
            "files": [
                {
                    "path": row["path"],
                    "sha256": row["sha256"],
                    "bytes": row["bytes"],
                }
                for row in archives
            ]
            + [
                {
                    "path": f"{RC_BUILD_DIR_REL}/{RC_METADATA_NAME}",
                    "sha256": sha256_file(meta_path),
                    "bytes": meta_path.stat().st_size,
                }
            ],
        }
        checksums_path = out / RC_CHECKSUMS_NAME
        checksums_path.write_text(
            json.dumps(checksum_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return {
        "schemaVersion": SCHEMA_VERSION,
        "ok": True,
        "command": "release-candidate",
        "action": "create",
        "packageVersion": version,
        "installerVersion": INSTALLER_VERSION,
        "sourceCommit": commit,
        "manifestHash": manifest_hash,
        "manifestBytes": len(manifest_bytes),
        "outputDir": RC_BUILD_DIR_REL,
        "archives": archives,
        "schemas": schema_ids,
        "acceptanceEvidence": evidence_ids,
        "installVerify": install_verify,
        "summary": {
            "archives": len(archives),
            "identities": len(staged),
            "reproducible": True,
            "dirtyAllowed": allow_dirty,
        },
    }


def verify_release_candidate_archive(
    *,
    archive_path: Path,
    expected_version: str = PACKAGE_VERSION_TARGET,
) -> dict[str, Any]:
    if not archive_path.is_file() or archive_path.is_symlink():
        raise ReleaseCandidateError(f"Archive not found: {archive_path.name}")
    name = archive_path.name.lower()
    if name.endswith(".tar.gz") or name.endswith(".tgz"):
        fmt = "tar.gz"
    elif name.endswith(".zip"):
        fmt = "zip"
    else:
        raise ReleaseCandidateError(f"Unsupported archive extension: {archive_path.name}")
    digest = sha256_file(archive_path)
    result = verify_archive_install(
        archive_path=archive_path,
        format_name=fmt,
        expected_version=expected_version,
        expected_archive_sha=digest,
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "ok": True,
        "command": "release-candidate",
        "action": "verify",
        "packageVersion": expected_version,
        "packageChecksum": digest,
        "installedVersion": result["installedVersion"],
        "archive": _safe_name(archive_path.name),
        "summary": result,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ide-development-release-candidate",
        description="Deterministic release-candidate packaging (stdlib only).",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only")
    sub = parser.add_subparsers(dest="action", required=True)

    create = sub.add_parser("create", help="Validate, regenerate manifest, build RC archives")
    create.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=f"Output directory (default: {RC_BUILD_DIR_REL})",
    )
    create.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow dirty worktree (local proofs only; production must be clean)",
    )
    create.add_argument(
        "--skip-install-verify",
        action="store_true",
        help="Skip extract+install verification (not for production RC)",
    )
    create.add_argument(
        "--skip-evidence",
        action="store_true",
        help="Skip lane evidence path checks (still requires packaging unit tests)",
    )
    create.add_argument("--baseline-sha", help="Runtime-supplied exact target baseline SHA")
    create.add_argument("--baseline-ref", help="Runtime-supplied authoritative remote target ref")

    verify = sub.add_parser("verify", help="Extract archive and install into a clean temp repo")
    verify.add_argument(
        "--archive",
        type=Path,
        required=True,
        help="Path to .tar.gz or .zip RC archive",
    )
    verify.add_argument(
        "--expected-version",
        default=PACKAGE_VERSION_TARGET,
        help=f"Expected package version (default {PACKAGE_VERSION_TARGET})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    as_json = bool(args.json)
    try:
        if args.action == "create":
            payload = create_release_candidate(
                output_dir=args.output_dir,
                allow_dirty=bool(args.allow_dirty),
                skip_install_verify=bool(args.skip_install_verify),
                skip_evidence=bool(args.skip_evidence),
                candidate_baseline_sha=args.baseline_sha,
                candidate_baseline_ref=args.baseline_ref,
            )
        elif args.action == "verify":
            payload = verify_release_candidate_archive(
                archive_path=Path(args.archive),
                expected_version=str(args.expected_version),
            )
        else:  # pragma: no cover
            parser.error(f"Unknown action: {args.action}")
            return EXIT_ERROR
    except InstallerError as exc:
        payload = {
            "schemaVersion": SCHEMA_VERSION,
            "ok": False,
            "command": "release-candidate",
            "action": getattr(args, "action", None),
            "error": exc.message,
            "details": exc.details,
            "exitCode": exc.exit_code,
        }
        if as_json:
            print(json.dumps(payload, indent=2, sort_keys=False))
        else:
            print(f"error={exc.message}", file=sys.stderr)
            print("--- json ---")
            print(json.dumps(payload, indent=2, sort_keys=False))
        return int(exc.exit_code)
    except Exception as exc:  # pragma: no cover
        payload = {
            "schemaVersion": SCHEMA_VERSION,
            "ok": False,
            "command": "release-candidate",
            "error": str(exc),
            "exitCode": EXIT_ERROR,
        }
        print(json.dumps(payload, indent=2, sort_keys=False))
        return EXIT_ERROR

    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=False))
    else:
        print(f"command=release-candidate action={payload.get('action')}")
        print(f"packageVersion={payload.get('packageVersion')}")
        if payload.get("packageChecksum"):
            print(f"packageChecksum={payload.get('packageChecksum')}")
        if payload.get("installedVersion"):
            print(f"installedVersion={payload.get('installedVersion')}")
        if payload.get("manifestHash"):
            print(f"manifestHash={payload.get('manifestHash')}")
        print("--- json ---")
        print(json.dumps(payload, indent=2, sort_keys=False))
    return EXIT_OK


if __name__ == "__main__":
    if str(SCRIPT_DIR.parent) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR.parent))
    raise SystemExit(main())
