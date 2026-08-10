"""Deterministic builder/verifier for core/managed-core/MANIFEST.json.

Generates the live Wave 1 package manifest with sha256 source hashes for the
approved shared lifecycle (doctrine content, Cursor/Codex entrypoints, GitOps
scripts, and approved skills) — not only the sparse GitOps subset.

Usage:
  python3 -m ide_development.build_manifest            # write MANIFEST.json
  python3 -m ide_development.build_manifest --verify   # exit 1 on drift
  python3 scripts/ide_development/build_manifest.py --write
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .constants import (
    DEFAULT_MARKER_BEGIN,
    DEFAULT_MARKER_END,
    PACKAGE_NAME,
    PACKAGE_VERSION_TARGET,
    SCHEMA_VERSION,
)
from .hashing import sha256_file

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
MANAGED = REPO_ROOT / "core" / "managed-core"
MANIFEST_PATH = MANAGED / "MANIFEST.json"
VERSION_PATH = MANAGED / "VERSION"


def _apply_repo_root(root: Path) -> None:
    """Retarget module globals so packaging can rebuild from a data checkout."""
    global REPO_ROOT, MANAGED, MANIFEST_PATH, VERSION_PATH
    REPO_ROOT = root.resolve()
    MANAGED = REPO_ROOT / "core" / "managed-core"
    MANIFEST_PATH = MANAGED / "MANIFEST.json"
    VERSION_PATH = MANAGED / "VERSION"


@contextmanager
def repo_root_context(root: Path) -> Iterator[Path]:
    """Temporarily point build_manifest at an alternate repository root.

    Trusted packaging code may rebuild from a separate source-SHA checkout
    (data-only path) without executing that tree's scripts.
    """
    global REPO_ROOT, MANAGED, MANIFEST_PATH, VERSION_PATH
    saved = (REPO_ROOT, MANAGED, MANIFEST_PATH, VERSION_PATH)
    _apply_repo_root(root)
    try:
        yield REPO_ROOT
    finally:
        REPO_ROOT, MANAGED, MANIFEST_PATH, VERSION_PATH = saved

# Cursor lifecycle rules beyond the GitOps pair already under platforms/.
LIFECYCLE_CURSOR_RULES = (
    "00-bootstrap.mdc",
    "01-identity.mdc",
    "02-autonomous-ship-pull.mdc",
    "03-secrets-security.mdc",
    "05-security-cost-and-side-effects.mdc",
)

# Doctrine files mirrored into .ide-development/content/ for consumer offline use.
CONTENT_DOCTRINE = (
    ("docs/contracts/AGENT-COMPLETION.md", "content/doctrine/AGENT-COMPLETION.md"),
    ("docs/contracts/DELIVERY-MODES.md", "content/doctrine/DELIVERY-MODES.md"),
    ("docs/contracts/MANAGED-CORE-V2.md", "content/doctrine/MANAGED-CORE-V2.md"),
    ("docs/contracts/REPOSITORY-PROTECTION.md", "content/doctrine/REPOSITORY-PROTECTION.md"),
    ("docs/adr/0003-autonomous-ship-pull-promote.md", "content/doctrine/0003-autonomous-ship-pull-promote.md"),
    ("docs/adr/0004-portable-managed-core-v2.md", "content/doctrine/0004-portable-managed-core-v2.md"),
    ("docs/AUTONOMOUS-GIT-OPERATIONS.md", "content/doctrine/AUTONOMOUS-GIT-OPERATIONS.md"),
)

ID_SAFE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    out = ID_SAFE.sub("-", text.lower()).strip("-")
    return out or "entry"


def _entry(
    *,
    entry_id: str,
    ownership: str,
    source: str,
    destination: str,
    mode: str,
    platform: str,
    merge: str,
    source_hash: str,
    os_filter: str = "all",
    marker_begin: str | None = None,
    marker_end: str | None = None,
    notes: str | None = None,
    supersession: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": entry_id,
        "ownershipClass": ownership,
        "source": source,
        "sourceHash": source_hash,
        "destination": destination,
        "mode": mode,
        "platform": platform,
        "os": os_filter,
        "mergeStrategy": merge,
    }
    if marker_begin is not None:
        row["markerBegin"] = marker_begin
    if marker_end is not None:
        row["markerEnd"] = marker_end
    if notes is not None:
        row["notes"] = notes
    if supersession is not None:
        row["supersessionIdentity"] = supersession
    return row


def _hash_rel(rel: str) -> str:
    path = REPO_ROOT / rel
    if not path.is_file():
        raise FileNotFoundError(rel)
    if path.is_symlink():
        raise ValueError(f"Refusing symlink source: {rel}")
    return sha256_file(path)


def _mode_for(path: Path) -> str:
    if path.suffix in {".sh", ".py"} or path.name.endswith(".py"):
        # Preserve executable bit for shell wrappers; python scripts stay 0644
        # unless already executable in the system tree.
        mode = path.stat().st_mode & 0o777
        if mode & 0o111:
            return "0755"
    return "0644"


def _sync_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def sync_package_payload() -> None:
    """Materialize approved lifecycle payload under core/managed-core/."""
    # Content doctrine copies (self-contained for consumers).
    for src_rel, dest_rel in CONTENT_DOCTRINE:
        _sync_file(REPO_ROOT / src_rel, MANAGED / dest_rel)

    content_readme = MANAGED / "content" / "README.md"
    content_readme.write_text(
        "# Managed content payload\n\n"
        "Approved shared development lifecycle doctrine and indexes packaged for\n"
        "consumer `.ide-development/content/`. No secrets. No absolute host paths.\n"
        "Claude runtime files are out of scope.\n",
        encoding="utf-8",
    )

    # Lifecycle Cursor rules copied into platforms for packaging identity.
    rules_dir = MANAGED / "platforms" / "cursor" / "rules"
    for name in LIFECYCLE_CURSOR_RULES:
        src = REPO_ROOT / ".cursor" / "rules" / name
        if src.is_file():
            _sync_file(src, rules_dir / name)

    # Approved remaining skills → managed-core/skills/<name>/SKILL.md
    skills_manifest = json.loads(
        (MANAGED / "platforms" / "codex" / "skills-manifest.json").read_text(encoding="utf-8")
    )
    for item in skills_manifest.get("approvedRemainingSkills") or []:
        name = item["name"]
        src = REPO_ROOT / "core" / "skills" / name / "SKILL.md"
        if not src.is_file():
            continue
        _sync_file(src, MANAGED / "skills" / name / "SKILL.md")

    # Also mirror agentsetup/agentcomply skill bodies for package completeness.
    for name in ("agentsetup", "agentcomply"):
        src = REPO_ROOT / "core" / "skills" / name / "SKILL.md"
        if src.is_file():
            _sync_file(src, MANAGED / "skills" / name / "SKILL.md")


def _gitops_script_sources() -> list[str]:
    manifest = json.loads(
        (REPO_ROOT / "core" / "github" / "managed-runtime" / "MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )
    return list(manifest.get("files") or [])


def build_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    # --- Package identity / schemas / migrations inside .ide-development/ ---
    identity_files = [
        ("VERSION", ".ide-development/VERSION"),
        ("README.md", ".ide-development/README.md"),
        ("INDEX.yaml", ".ide-development/INDEX.yaml"),
        ("content/README.md", ".ide-development/content/README.md"),
        ("migrations/catalog.json", ".ide-development/migrations/catalog.json"),
        ("migrations/schema.json", ".ide-development/migrations/schema.json"),
        ("migrations/README.md", ".ide-development/migrations/README.md"),
        ("schemas/manifest.schema.json", ".ide-development/schemas/manifest.schema.json"),
        ("schemas/installed-state.schema.json", ".ide-development/schemas/installed-state.schema.json"),
        ("schemas/transaction.schema.json", ".ide-development/schemas/transaction.schema.json"),
        (
            "schemas/release-candidate.schema.json",
            ".ide-development/schemas/release-candidate.schema.json",
        ),
        (
            "schemas/release-candidate-checksums.schema.json",
            ".ide-development/schemas/release-candidate-checksums.schema.json",
        ),
        (
            "schemas/delivery-modes.schema.json",
            ".ide-development/schemas/delivery-modes.schema.json",
        ),
        (
            "schemas/managed-core-release.schema.json",
            ".ide-development/schemas/managed-core-release.schema.json",
        ),
        ("platforms/README.md", ".ide-development/platforms/README.md"),
        ("platforms/codex/README.md", ".ide-development/platforms/codex/README.md"),
        ("platforms/cursor/README.md", ".ide-development/platforms/cursor/README.md"),
        (
            "platforms/codex/AGENTS.managed-section.md",
            ".ide-development/platforms/codex/AGENTS.managed-section.md",
        ),
        (
            "platforms/codex/skills-manifest.json",
            ".ide-development/platforms/codex/skills-manifest.json",
        ),
        (
            "platforms/cursor/materialization-manifest.json",
            ".ide-development/platforms/cursor/materialization-manifest.json",
        ),
    ]
    for src_tail, dest in identity_files:
        source = f"core/managed-core/{src_tail}"
        entries.append(
            _entry(
                entry_id=f"core-{_slug(src_tail)}",
                ownership="managed-core",
                source=source,
                destination=dest,
                mode="0644",
                platform="all",
                merge="replace",
                source_hash=_hash_rel(source),
            )
        )

    for src_rel, dest_rel in CONTENT_DOCTRINE:
        source = f"core/managed-core/{dest_rel}"
        entries.append(
            _entry(
                entry_id=f"doctrine-{_slug(Path(dest_rel).name)}",
                ownership="managed-core",
                source=source,
                destination=f".ide-development/{dest_rel}",
                mode="0644",
                platform="all",
                merge="replace",
                source_hash=_hash_rel(source),
            )
        )

    # Known-bytes for migration catalog (package completeness).
    for known in sorted((MANAGED / "migrations" / "known-bytes").glob("*")):
        if not known.is_file():
            continue
        rel = f"core/managed-core/migrations/known-bytes/{known.name}"
        entries.append(
            _entry(
                entry_id=f"known-bytes-{_slug(known.name)}",
                ownership="managed-core",
                source=rel,
                destination=f".ide-development/migrations/known-bytes/{known.name}",
                mode="0644",
                platform="all",
                merge="replace",
                source_hash=_hash_rel(rel),
            )
        )

    # --- Codex AGENTS.md marker ---
    agents_src = "core/managed-core/platforms/codex/AGENTS.managed-section.md"
    entries.append(
        _entry(
            entry_id="agents-managed-section",
            ownership="managed-marker",
            source=agents_src,
            destination="AGENTS.md",
            mode="0644",
            platform="codex",
            merge="marker-upsert",
            source_hash=_hash_rel(agents_src),
            marker_begin=DEFAULT_MARKER_BEGIN,
            marker_end=DEFAULT_MARKER_END,
            notes="Upserts managed lifecycle block; preserves consumer text outside markers.",
        )
    )

    # --- Required Codex skills ---
    for name in ("agentsetup", "agentcomply"):
        source = f"core/managed-core/platforms/codex/skills/{name}/SKILL.md"
        entries.append(
            _entry(
                entry_id=f"codex-skill-{name}",
                ownership="managed-entrypoint",
                source=source,
                destination=f".agents/skills/{name}/SKILL.md",
                mode="0644",
                platform="codex",
                merge="replace",
                source_hash=_hash_rel(source),
            )
        )
        # Package mirror under .ide-development
        pkg_src = f"core/managed-core/skills/{name}/SKILL.md"
        if (REPO_ROOT / pkg_src).is_file():
            entries.append(
                _entry(
                    entry_id=f"pkg-skill-{name}",
                    ownership="managed-core",
                    source=pkg_src,
                    destination=f".ide-development/skills/{name}/SKILL.md",
                    mode="0644",
                    platform="all",
                    merge="replace",
                    source_hash=_hash_rel(pkg_src),
                )
            )

    # --- Required Cursor entrypoints ---
    cursor_required = [
        (
            "platforms/cursor/rules/cursor-gitops-bootstrap.mdc",
            ".cursor/rules/cursor-gitops-bootstrap.mdc",
        ),
        (
            "platforms/cursor/rules/linktrend-git-branching.mdc",
            ".cursor/rules/linktrend-git-branching.mdc",
        ),
        ("platforms/cursor/commands/agentsetup.md", ".cursor/commands/agentsetup.md"),
        ("platforms/cursor/commands/agentcomply.md", ".cursor/commands/agentcomply.md"),
        ("platforms/cursor/skills/agentsetup/SKILL.md", ".cursor/skills/agentsetup/SKILL.md"),
        ("platforms/cursor/skills/agentcomply/SKILL.md", ".cursor/skills/agentcomply/SKILL.md"),
    ]
    for src_tail, dest in cursor_required:
        source = f"core/managed-core/{src_tail}"
        entries.append(
            _entry(
                entry_id=f"cursor-{_slug(dest)}",
                ownership="managed-entrypoint",
                source=source,
                destination=dest,
                mode="0644",
                platform="cursor",
                merge="replace",
                source_hash=_hash_rel(source),
            )
        )
        # Also keep under .ide-development/platforms
        entries.append(
            _entry(
                entry_id=f"pkg-{_slug(src_tail)}",
                ownership="managed-core",
                source=source,
                destination=f".ide-development/{src_tail}",
                mode="0644",
                platform="all",
                merge="replace",
                source_hash=_hash_rel(source),
            )
        )

    # --- Additional lifecycle Cursor rules ---
    for name in LIFECYCLE_CURSOR_RULES:
        source = f"core/managed-core/platforms/cursor/rules/{name}"
        if not (REPO_ROOT / source).is_file():
            continue
        dest = f".cursor/rules/{name}"
        entries.append(
            _entry(
                entry_id=f"cursor-rule-{_slug(name)}",
                ownership="managed-entrypoint",
                source=source,
                destination=dest,
                mode="0644",
                platform="cursor",
                merge="replace",
                source_hash=_hash_rel(source),
            )
        )
        entries.append(
            _entry(
                entry_id=f"pkg-rule-{_slug(name)}",
                ownership="managed-core",
                source=source,
                destination=f".ide-development/platforms/cursor/rules/{name}",
                mode="0644",
                platform="all",
                merge="replace",
                source_hash=_hash_rel(source),
            )
        )

    # --- Approved remaining skills (Codex + Cursor discovery) ---
    skills_root = MANAGED / "skills"
    if skills_root.is_dir():
        for skill_dir in sorted(skills_root.iterdir()):
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            name = skill_dir.name
            if name in {"agentsetup", "agentcomply"}:
                continue  # already handled as required entrypoints
            source = f"core/managed-core/skills/{name}/SKILL.md"
            digest = _hash_rel(source)
            entries.append(
                _entry(
                    entry_id=f"codex-skill-{_slug(name)}",
                    ownership="managed-entrypoint",
                    source=source,
                    destination=f".agents/skills/{name}/SKILL.md",
                    mode="0644",
                    platform="codex",
                    merge="replace",
                    source_hash=digest,
                )
            )
            entries.append(
                _entry(
                    entry_id=f"cursor-skill-{_slug(name)}",
                    ownership="managed-entrypoint",
                    source=source,
                    destination=f".cursor/skills/{name}/SKILL.md",
                    mode="0644",
                    platform="cursor",
                    merge="replace",
                    source_hash=digest,
                )
            )
            entries.append(
                _entry(
                    entry_id=f"pkg-skill-{_slug(name)}",
                    ownership="managed-core",
                    source=source,
                    destination=f".ide-development/skills/{name}/SKILL.md",
                    mode="0644",
                    platform="all",
                    merge="replace",
                    source_hash=digest,
                )
            )

    # --- GitOps scripts (preserve existing consumer GitOps behavior) ---
    for rel in _gitops_script_sources():
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        entries.append(
            _entry(
                entry_id=f"gitops-{_slug(rel)}",
                ownership="managed",
                source=rel,
                destination=rel,
                mode=_mode_for(path),
                platform="github",
                merge="replace",
                source_hash=_hash_rel(rel),
                notes="Managed GitOps script; never overwrites consumer ci.yml.",
            )
        )

    # Also ship repository protection tooling as managed scripts.
    for rel in (
        "scripts/gitops/repository_protection.py",
        "scripts/manage-repository-protections.sh",
        "scripts/ide-development.py",
    ):
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        # Avoid duplicate if already in gitops list
        if any(e["destination"] == rel for e in entries):
            continue
        entries.append(
            _entry(
                entry_id=f"tooling-{_slug(rel)}",
                ownership="managed",
                source=rel,
                destination=rel,
                mode=_mode_for(path),
                platform="all",
                merge="replace",
                source_hash=_hash_rel(rel),
            )
        )

    # Package the ide_development Python module for consumers that need the installer.
    pkg_dir = REPO_ROOT / "scripts" / "ide_development"
    for path in sorted(pkg_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        entries.append(
            _entry(
                entry_id=f"installer-{_slug(rel)}",
                ownership="managed",
                source=rel,
                destination=rel,
                mode="0644",
                platform="all",
                merge="replace",
                source_hash=_hash_rel(rel),
            )
        )

    # Deterministic order
    entries.sort(key=lambda e: (e["destination"], e["id"]))
    # Deduplicate destinations (keep first after sort by id stability)
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in entries:
        dest = row["destination"]
        if dest in seen:
            continue
        seen.add(dest)
        unique.append(row)
    return unique


def build_manifest_object() -> dict[str, Any]:
    version = VERSION_PATH.read_text(encoding="utf-8").strip().lstrip("v")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "packageName": PACKAGE_NAME,
        "packageVersion": version,
        "description": (
            "Portable IDE Development managed-core v2 — approved shared lifecycle "
            "(doctrine, Cursor/Codex entrypoints, GitOps scripts, skills). "
            "Physical files only. No Claude. No secrets."
        ),
        "createdAt": "2026-08-01T00:00:00Z",
        "files": build_entries(),
    }


def write_manifest(path: Path | None = None) -> dict[str, Any]:
    target = MANIFEST_PATH if path is None else path
    sync_package_payload()
    obj = build_manifest_object()
    # MANIFEST.json itself is copied into consumers by the installer apply step
    # (not listed in files[] to avoid self-hash circularity).
    text = json.dumps(obj, indent=2, sort_keys=False) + "\n"
    target.write_text(text, encoding="utf-8")
    return obj


def _version_alignment_errors() -> list[str]:
    """Ensure root VERSION, managed VERSION, and packageVersion stay aligned."""
    errors: list[str] = []
    root_ver_path = REPO_ROOT / "VERSION"
    if not root_ver_path.is_file():
        return ["VERSION missing at repo root"]
    if not VERSION_PATH.is_file():
        return ["core/managed-core/VERSION missing"]
    root_ver = root_ver_path.read_text(encoding="utf-8").strip()
    pkg_ver = VERSION_PATH.read_text(encoding="utf-8").strip()
    root_norm = root_ver.lstrip("v")
    pkg_norm = pkg_ver.lstrip("v")
    if root_norm != pkg_norm:
        errors.append(f"VERSION alignment drift: root={root_ver!r} managed={pkg_ver!r}")
    if pkg_norm != PACKAGE_VERSION_TARGET:
        errors.append(
            f"package VERSION must remain {PACKAGE_VERSION_TARGET} identity "
            f"(got {pkg_ver!r})"
        )
    return errors


def _doctrine_sync_errors() -> list[str]:
    """Ensure CONTENT_DOCTRINE docs sources match packaged content/doctrine bytes."""
    errors: list[str] = []
    for src_rel, dest_rel in CONTENT_DOCTRINE:
        src = REPO_ROOT / src_rel
        dest = MANAGED / dest_rel
        if not src.is_file():
            errors.append(f"doctrine source missing: {src_rel}")
            continue
        if not dest.is_file():
            errors.append(f"doctrine package missing: core/managed-core/{dest_rel}")
            continue
        if sha256_file(src) != sha256_file(dest):
            errors.append(f"doctrine sync drift: {src_rel} → core/managed-core/{dest_rel}")
    return errors


def verify_manifest(path: Path | None = None) -> list[str]:
    """Read-only verify: compare on-disk MANIFEST hashes to source files.

    Does **not** call ``sync_package_payload()`` — verify must not mutate the tree.
    Use ``--write`` / ``write_manifest`` to sync payload then regenerate.

    Also checks VERSION alignment and CONTENT_DOCTRINE docs→package sync.
    """
    target = MANIFEST_PATH if path is None else path
    errors: list[str] = []
    errors.extend(_version_alignment_errors())
    errors.extend(_doctrine_sync_errors())
    if not target.is_file():
        errors.append("MANIFEST.json missing")
        return errors
    expected = build_manifest_object()
    actual = json.loads(target.read_text(encoding="utf-8"))
    if actual.get("packageVersion") != expected["packageVersion"]:
        errors.append("packageVersion drift")
    if actual.get("packageVersion") != PACKAGE_VERSION_TARGET:
        errors.append(
            f"packageVersion must remain {PACKAGE_VERSION_TARGET} identity "
            f"(got {actual.get('packageVersion')!r})"
        )
    if actual.get("schemaVersion") != expected["schemaVersion"]:
        errors.append("schemaVersion drift")
    exp_files = {(f["id"], f["destination"], f["sourceHash"]) for f in expected["files"]}
    act_files = {(f["id"], f["destination"], f["sourceHash"]) for f in actual.get("files") or []}
    missing = sorted(exp_files - act_files)
    extra = sorted(act_files - exp_files)
    if missing:
        errors.append(f"missing/changed entries: {len(missing)}")
    if extra:
        errors.append(f"extra/stale entries: {len(extra)}")
    # Hash every declared source
    for row in actual.get("files") or []:
        src = row.get("source")
        digest = row.get("sourceHash")
        try:
            actual_hash = _hash_rel(src)
        except (FileNotFoundError, ValueError) as exc:
            errors.append(f"{src}: {exc}")
            continue
        if actual_hash != digest:
            errors.append(f"hash mismatch: {src}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write MANIFEST.json (default)")
    parser.add_argument("--verify", action="store_true", help="Verify existing MANIFEST.json")
    parser.add_argument("--json", action="store_true", help="Print manifest JSON to stdout")
    args = parser.parse_args(argv)

    if args.verify:
        errors = verify_manifest()
        if errors:
            print("MANIFEST verify FAILED:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 1
        print("MANIFEST verify OK")
        return 0

    obj = write_manifest()
    print(f"Wrote {MANIFEST_PATH.relative_to(REPO_ROOT)} with {len(obj['files'])} files")
    if args.json:
        print(json.dumps(obj, indent=2))
    return 0


if __name__ == "__main__":
    # Allow `python3 scripts/ide_development/build_manifest.py`
    if str(SCRIPT_DIR.parent) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR.parent))
    raise SystemExit(main())
