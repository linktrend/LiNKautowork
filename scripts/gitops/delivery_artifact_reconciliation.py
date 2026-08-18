#!/usr/bin/env python3
"""Safe stale delivery-artifact reconciliation (WP-U08 / AC-U08-01–06).

Inventory JSON is a locator, not deletion authority. Controller ownership,
repository containment, ref existence and type, protected status, exact
ancestry tree-duplicate or empty/superseded classification, dirty state,
and attached-worktree state are derived from the target repository and
trusted controller state. Clean only controller-owned empty or
tree-equivalent superseded artifacts proven by that live evidence.
Reject or keep every unverifiable, external, protected, dirty, unique,
attached, or mismatched artifact. Never force-remove dirty unique
external worktrees and never force-delete from supplied JSON alone.

Preserve unique, uncommitted, partially integrated, unknown, worker, and
protected artifacts for an explicit decision. Never leave repository-root
runtime residue: success deletes transients; failure retains diagnostics
in the ignored controller state directory.

This module is fail-closed. It does not call GitHub unless a mutator is
injected. Fixtures, mocks, and disposable repositories are the supported
test surfaces.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

SCHEMA_VERSION = 1
STATE_REL = Path(".linktrend") / "controller-state"
PROTECTED_BRANCHES = frozenset({"main", "staging", "development", "HEAD"})
CONTROLLER_REF_PREFIXES = ("controller/", "promote/")
OWNED_REFS_FILENAME = "owned-refs.json"
INTEGRATION_REFS = (
    "refs/heads/development",
    "refs/remotes/origin/development",
    "refs/heads/main",
)
ROOT_RESIDUE_NAMES = frozenset({"gitops-outcome.json", "integrator-result.json"})
TRANSIENT_FILENAMES = frozenset({"outcome.json", "gate-wait.json", "run.json"})
REPORT_FILENAME = "reconciliation-report.json"
FAILURE_DIAGNOSTICS_FILENAME = "failure-diagnostics.json"
RETAINED_RESIDUE_DIRNAME = "retained-root-residue"
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
KIND_PR = "pr"
KIND_BRANCH = "branch"
KIND_WORKTREE = "worktree"
KIND_RUNTIME_RESIDUE = "runtime_residue"
KINDS = frozenset({KIND_PR, KIND_BRANCH, KIND_WORKTREE, KIND_RUNTIME_RESIDUE})
KIND_RANK = {
    KIND_WORKTREE: 0,
    KIND_BRANCH: 1,
    KIND_PR: 2,
    KIND_RUNTIME_RESIDUE: 3,
}
OWNER_CONTROLLER = "controller"
OWNER_WORKER = "worker"
OWNER_UNKNOWN = "unknown"
OWNERS = frozenset({OWNER_CONTROLLER, OWNER_WORKER, OWNER_UNKNOWN})
CLASS_EMPTY = "empty"
CLASS_TREE_EQUIVALENT_SUPERSEDED = "tree_equivalent_superseded"
CLASS_PARTIALLY_INTEGRATED = "partially_integrated"
CLASS_UNIQUE_WORK = "unique_work"
CLASS_UNCOMMITTED = "uncommitted"
CLASS_UNKNOWN = "unknown"
CLASS_PROTECTED = "protected"
CLEANABLE_CLASSES = frozenset({CLASS_EMPTY, CLASS_TREE_EQUIVALENT_SUPERSEDED})
ACTION_CLEAN = "clean"
ACTION_PRESERVE_FOR_DECISION = "preserve_for_decision"
ACTION_KEEP = "keep"
ACTION_ALREADY_ABSENT = "already_absent"
MAX_INFRASTRUCTURE_ATTEMPTS = 2


class ReconciliationError(Exception):
    """Structured fail-closed reconciliation error."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class IdentityUncertainty(ReconciliationError):
    """Missing or conflicting identity; never enters an automatic retry loop."""


class InfrastructureError(ReconciliationError):
    """Retryable infrastructure failure; at most two attempts."""


@dataclass(frozen=True)
class Artifact:
    """One inventoried PR, branch, worktree, or runtime residue item."""

    id: str
    kind: str
    name: str
    controller_owned: bool = False
    owner: str = OWNER_UNKNOWN
    head_sha: str | None = None
    tree_sha: str | None = None
    base_sha: str | None = None
    base_tree_sha: str | None = None
    integrated_trees: tuple[str, ...] = ()
    integrated_commits: tuple[str, ...] = ()
    changed_paths: tuple[str, ...] = ()
    unique_paths: tuple[str, ...] = ()
    integrated_paths: tuple[str, ...] = ()
    uncommitted: bool = False
    commits_ahead: int | None = None
    exists: bool = True
    path: str | None = None
    attached: bool = False
    derived: bool = False

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ReconciliationError("invalid_kind", f"unsupported artifact kind: {self.kind}")
        if self.owner not in OWNERS:
            raise ReconciliationError("invalid_owner", f"unsupported owner: {self.owner}")
        if not self.id or not self.name:
            raise ReconciliationError("invalid_artifact", "id and name are required")


@dataclass(frozen=True)
class Classification:
    classification: str
    reason: str
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    artifact: Artifact
    classification: Classification
    action: str


CleanFn = Callable[[Artifact], str]


def _valid_sha(value: str | None) -> bool:
    return isinstance(value, str) and bool(SHA40_RE.fullmatch(value))


def _is_protected(name: str) -> bool:
    raw = (name or "").strip()
    if raw in PROTECTED_BRANCHES:
        return True
    # refs/heads/main and origin/development stay protected.
    leaf = raw.rsplit("/", 1)[-1]
    return leaf in PROTECTED_BRANCHES and raw.startswith(("refs/heads/", "origin/", "refs/remotes/"))


def _git_at(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _rev_parse(path: Path, spec: str) -> str | None:
    result = _git_at(path, "rev-parse", "--verify", "--quiet", spec)
    out = (result.stdout or "").strip()
    if result.returncode != 0 or not SHA40_RE.fullmatch(out):
        return None
    return out


def _git_common_dir(path: Path) -> Path | None:
    result = _git_at(path, "rev-parse", "--git-common-dir")
    raw = (result.stdout or "").strip()
    if result.returncode != 0 or not raw:
        return None
    parsed = Path(raw)
    if not parsed.is_absolute():
        parsed = Path(path) / parsed
    try:
        return parsed.resolve()
    except OSError:
        return None


def _safe_branch_name(repo: Path, name: str) -> bool:
    if not name or name.strip() != name or "\x00" in name:
        return False
    result = _git_at(repo, "check-ref-format", "--branch", name)
    return result.returncode == 0


def _load_trusted_owned_refs(state_dir: Path) -> frozenset[str]:
    path = Path(state_dir) / OWNED_REFS_FILENAME
    if not path.is_file():
        return frozenset()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return frozenset()
    rows: list[Any]
    if isinstance(data, list):
        rows = data
    elif isinstance(data, Mapping):
        candidate = data.get("refs") or data.get("names") or data.get("owned") or []
        rows = candidate if isinstance(candidate, list) else []
    else:
        return frozenset()
    return frozenset(item.strip() for item in rows if isinstance(item, str) and item.strip())


def _derive_owner(name: str, trusted: frozenset[str]) -> tuple[bool, str]:
    # Worker issue branches stay worker-owned. Trusted controller state may
    # prove controller/promote refs, never reclassify issue/* as deletable.
    if name.startswith("issue/"):
        return False, OWNER_WORKER
    if name.startswith(CONTROLLER_REF_PREFIXES) or name in trusted:
        return True, OWNER_CONTROLLER
    return False, OWNER_UNKNOWN


def _require_live_controller_ref(repo: Path, name: str) -> None:
    """Refuse deletion unless live name + trusted state prove controller ownership."""
    if not name or _is_protected(name) or not _safe_branch_name(repo, name):
        raise IdentityUncertainty("unsafe_branch", name)
    owned, owner = _derive_owner(name, _load_trusted_owned_refs(resolve_state_dir(repo)))
    if not owned or owner != OWNER_CONTROLLER:
        raise IdentityUncertainty("not_controller_owned", name)


def _same_git_common_dir(repo: Path, path: Path) -> bool:
    repo_common = _git_common_dir(repo)
    other_common = _git_common_dir(path)
    return bool(repo_common) and bool(other_common) and repo_common == other_common


def _lineage_allows_clean(repo: Path, head: str) -> bool:
    """True only when live Git proves empty or tree-equivalent superseded lineage."""
    if not _valid_sha(head):
        return False
    tree_sha = _rev_parse(repo, f"{head}^{{tree}}")
    integration = _integration_ref(repo)
    if not _valid_sha(tree_sha) or not integration:
        return False
    base_tree = _rev_parse(repo, f"{integration}^{{tree}}")
    integrated = _collect_integrated_trees(repo, integration)
    ahead = _commits_ahead(repo, integration, head)
    if ahead == 0:
        return True
    if tree_sha in integrated:
        return True
    return bool(base_tree) and tree_sha == base_tree


def _list_worktrees(repo: Path) -> list[dict[str, Any]]:
    result = _git_at(repo, "worktree", "list", "--porcelain")
    if result.returncode != 0:
        return []
    repo_resolved = Path(repo).resolve()
    rows: list[dict[str, Any]] = []
    current: dict[str, Any] = {}

    def flush() -> None:
        path_raw = current.get("path")
        if not path_raw:
            return
        try:
            path = Path(str(path_raw)).resolve()
        except OSError:
            return
        current["path"] = str(path)
        current["primary"] = path == repo_resolved
        current["contained"] = _same_git_common_dir(repo, path)
        current.setdefault("locked", False)
        current.setdefault("branch", "")
        current.setdefault("head", None)
        rows.append(dict(current))

    for line in (result.stdout or "").splitlines():
        if not line.strip():
            flush()
            current = {}
            continue
        if line.startswith("worktree "):
            current["path"] = line[len("worktree ") :]
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD ") :].strip()
        elif line.startswith("branch "):
            ref = line[len("branch ") :].strip()
            current["branch"] = ref[len("refs/heads/") :] if ref.startswith("refs/heads/") else ref
        elif line == "locked" or line.startswith("locked "):
            current["locked"] = True
        elif line == "bare":
            current["bare"] = True
        elif line == "detached":
            current["detached"] = True
    flush()
    return rows


def _worktree_dirty(path: Path) -> bool:
    result = _git_at(path, "status", "--porcelain")
    if result.returncode != 0:
        return True
    return any(line.strip() for line in (result.stdout or "").splitlines())


def _integration_ref(repo: Path) -> str | None:
    for spec in INTEGRATION_REFS:
        if _rev_parse(repo, spec):
            return spec
    return None


def _collect_integrated_trees(repo: Path, integration_ref: str) -> tuple[str, ...]:
    result = _git_at(repo, "log", "--format=%T", "-n", "256", integration_ref)
    if result.returncode != 0:
        return ()
    trees: list[str] = []
    seen: set[str] = set()
    for line in (result.stdout or "").splitlines():
        value = line.strip()
        if _valid_sha(value) and value not in seen:
            seen.add(value)
            trees.append(value)
    return tuple(trees)


def _diff_names(repo: Path, base: str, head: str) -> tuple[str, ...]:
    result = _git_at(repo, "diff", "--name-only", f"{base}...{head}")
    if result.returncode != 0:
        return ()
    return tuple(line for line in (result.stdout or "").splitlines() if line.strip())


def _commits_ahead(repo: Path, base: str, head: str) -> int | None:
    result = _git_at(repo, "rev-list", "--count", f"{base}..{head}")
    text = (result.stdout or "").strip()
    if result.returncode != 0 or not text.isdigit():
        return None
    return int(text)


def _local_branch_sha(repo: Path, name: str) -> str | None:
    if not _safe_branch_name(repo, name):
        return None
    return _rev_parse(repo, f"refs/heads/{name}")


def _is_tag_only(repo: Path, name: str) -> bool:
    if not _safe_branch_name(repo, name):
        return False
    return _rev_parse(repo, f"refs/tags/{name}") is not None and _local_branch_sha(repo, name) is None


def _unverified(artifact: Artifact, **overrides: Any) -> Artifact:
    payload = {
        "id": artifact.id,
        "kind": artifact.kind,
        "name": artifact.name,
        "controller_owned": False,
        "owner": OWNER_UNKNOWN,
        "exists": True,
        "attached": True,
        "uncommitted": True,
        "derived": False,
    }
    payload.update(overrides)
    return Artifact(**payload)


def _materialize_ref(
    repo: Path,
    artifact: Artifact,
    trusted: frozenset[str],
    *,
    kind: str,
) -> Artifact:
    name = artifact.name
    owned, owner = _derive_owner(name, trusted)
    if not _safe_branch_name(repo, name):
        return _unverified(artifact, kind=kind, attached=kind == KIND_BRANCH)
    if _is_protected(name):
        head = _local_branch_sha(repo, name)
        tree_sha = _rev_parse(repo, f"{head}^{{tree}}") if head else None
        return Artifact(
            id=artifact.id,
            kind=kind,
            name=name,
            controller_owned=False,
            owner=owner,
            head_sha=head,
            tree_sha=tree_sha,
            exists=True,
            attached=True,
            derived=True,
        )
    if _is_tag_only(repo, name):
        return _unverified(artifact, kind=kind, owner=owner, attached=True)
    head = _local_branch_sha(repo, name)
    if head is None:
        if kind == KIND_PR:
            return Artifact(
                id=artifact.id,
                kind=kind,
                name=name,
                controller_owned=owned,
                owner=owner,
                exists=True,
                derived=True,
            )
        return Artifact(
            id=artifact.id,
            kind=kind,
            name=name,
            controller_owned=owned,
            owner=owner,
            exists=False,
            derived=True,
        )
    tree_sha = _rev_parse(repo, f"{head}^{{tree}}")
    integration = _integration_ref(repo)
    base_sha = _rev_parse(repo, integration) if integration else None
    base_tree = _rev_parse(repo, f"{integration}^{{tree}}") if integration else None
    integrated = _collect_integrated_trees(repo, integration) if integration else ()
    ahead = _commits_ahead(repo, integration, head) if integration else None
    changed = _diff_names(repo, integration, head) if integration else ()
    unique = changed if (tree_sha and base_tree and tree_sha != base_tree) else ()
    attached = kind == KIND_BRANCH and any(item.get("branch") == name for item in _list_worktrees(repo))
    return Artifact(
        id=artifact.id,
        kind=kind,
        name=name,
        controller_owned=owned and not _is_protected(name),
        owner=owner,
        head_sha=head,
        tree_sha=tree_sha,
        base_sha=base_sha,
        base_tree_sha=base_tree,
        integrated_trees=integrated,
        changed_paths=changed,
        unique_paths=unique,
        commits_ahead=ahead,
        uncommitted=False,
        exists=True,
        attached=attached,
        derived=True,
    )


def _materialize_worktree(repo: Path, artifact: Artifact, trusted: frozenset[str]) -> Artifact:
    name = artifact.name
    owned, owner = _derive_owner(name, trusted)
    listed = _list_worktrees(repo)
    caller_path: Path | None = None
    if artifact.path:
        try:
            caller_path = Path(artifact.path).resolve()
        except OSError:
            caller_path = None
    name_match = next((item for item in listed if item.get("branch") == name), None)
    path_match = None
    if caller_path is not None:
        path_match = next((item for item in listed if Path(item["path"]).resolve() == caller_path), None)
    if name_match and path_match and Path(name_match["path"]).resolve() != Path(path_match["path"]).resolve():
        return _unverified(artifact, kind=KIND_WORKTREE, path=path_match["path"])
    if name_match is None and path_match is not None:
        return _unverified(artifact, kind=KIND_WORKTREE, path=path_match["path"])
    if name_match is None:
        if caller_path is not None and caller_path.exists():
            return _unverified(artifact, kind=KIND_WORKTREE, path=str(caller_path))
        return Artifact(
            id=artifact.id,
            kind=KIND_WORKTREE,
            name=name,
            controller_owned=owned,
            owner=owner,
            exists=False,
            derived=True,
        )
    path = Path(name_match["path"])
    if not name_match.get("contained") or name_match.get("primary") or name_match.get("locked"):
        return _unverified(
            artifact,
            kind=KIND_WORKTREE,
            owner=owner,
            path=str(path),
            attached=True,
        )
    if _is_protected(name) or _is_protected(str(name_match.get("branch") or "")):
        return _unverified(artifact, kind=KIND_WORKTREE, path=str(path), attached=True)
    dirty = _worktree_dirty(path)
    head = _rev_parse(path, "HEAD")
    tree_sha = _rev_parse(path, "HEAD^{tree}")
    integration = _integration_ref(repo)
    base_sha = _rev_parse(repo, integration) if integration else None
    base_tree = _rev_parse(repo, f"{integration}^{{tree}}") if integration else None
    integrated = _collect_integrated_trees(repo, integration) if integration else ()
    ahead = _commits_ahead(repo, integration, head) if integration and head else None
    changed = _diff_names(repo, integration, head) if integration and head else ()
    unique = changed if (tree_sha and base_tree and tree_sha != base_tree) else ()
    return Artifact(
        id=artifact.id,
        kind=KIND_WORKTREE,
        name=name,
        controller_owned=owned,
        owner=owner,
        head_sha=head,
        tree_sha=tree_sha,
        base_sha=base_sha,
        base_tree_sha=base_tree,
        integrated_trees=integrated,
        changed_paths=changed,
        unique_paths=unique,
        uncommitted=dirty,
        commits_ahead=ahead,
        exists=True,
        path=str(path),
        attached=False,
        derived=True,
    )


def materialize_artifact(repo: Path, artifact: Artifact, *, state_dir: Path) -> Artifact:
    """Replace caller-authored inventory fields with live repository evidence."""
    trusted = _load_trusted_owned_refs(state_dir)
    if artifact.kind == KIND_RUNTIME_RESIDUE:
        if artifact.name not in ROOT_RESIDUE_NAMES:
            return _unverified(artifact, kind=KIND_RUNTIME_RESIDUE, attached=False, uncommitted=False)
        path = Path(repo) / artifact.name
        return Artifact(
            id=artifact.id,
            kind=KIND_RUNTIME_RESIDUE,
            name=artifact.name,
            controller_owned=True,
            owner=OWNER_CONTROLLER,
            path=str(path),
            exists=path.is_file(),
            derived=True,
        )
    if artifact.kind in {KIND_BRANCH, KIND_PR}:
        return _materialize_ref(repo, artifact, trusted, kind=artifact.kind)
    if artifact.kind == KIND_WORKTREE:
        return _materialize_worktree(repo, artifact, trusted)
    return _unverified(artifact)


def resolve_state_dir(repo: Path, override: str | os.PathLike[str] | None = None) -> Path:
    """Return the ignored controller diagnostic/state directory."""
    if override:
        return Path(override)
    env = (os.environ.get("LINKTREND_CONTROLLER_STATE_DIR") or "").strip()
    if env:
        return Path(env)
    return Path(repo) / STATE_REL


def ensure_state_dir(state_dir: Path) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def inventory_root_residue(repo: Path) -> list[Artifact]:
    """List known controller-generated files sitting on the repository root."""
    root = Path(repo)
    found: list[Artifact] = []
    for name in sorted(ROOT_RESIDUE_NAMES):
        path = root / name
        if path.is_file():
            found.append(
                Artifact(
                    id=f"residue:{name}",
                    kind=KIND_RUNTIME_RESIDUE,
                    name=name,
                    controller_owned=True,
                    owner=OWNER_CONTROLLER,
                    path=str(path),
                    exists=True,
                )
            )
    return found


def _move_root_residue_to_state(repo: Path, state_dir: Path) -> list[str]:
    retained: list[str] = []
    dest_root = state_dir / RETAINED_RESIDUE_DIRNAME
    for artifact in inventory_root_residue(repo):
        src = Path(artifact.path or (Path(repo) / artifact.name))
        if not src.is_file():
            continue
        dest_root.mkdir(parents=True, exist_ok=True)
        dest = dest_root / src.name
        shutil.move(str(src), str(dest))
        retained.append(src.name)
    return retained


def _delete_root_residue(repo: Path) -> list[str]:
    removed: list[str] = []
    for artifact in inventory_root_residue(repo):
        src = Path(artifact.path or (Path(repo) / artifact.name))
        if src.is_file():
            src.unlink()
            removed.append(src.name)
    return removed


def _clear_transients(state_dir: Path) -> None:
    for name in TRANSIENT_FILENAMES:
        (state_dir / name).unlink(missing_ok=True)


def finish_success(state_dir: Path, report: Mapping[str, Any]) -> Path:
    """Clean transients after success; keep the auditable report in state dir."""
    ensure_state_dir(state_dir)
    _clear_transients(state_dir)
    return write_json(state_dir / REPORT_FILENAME, report)


def finish_failure(state_dir: Path, report: Mapping[str, Any], *, diagnostics: Mapping[str, Any]) -> Path:
    """Retain diagnostics and the report; do not delete evidence."""
    ensure_state_dir(state_dir)
    write_json(state_dir / FAILURE_DIAGNOSTICS_FILENAME, diagnostics)
    return write_json(state_dir / REPORT_FILENAME, report)


def classify_artifact(artifact: Artifact) -> Classification:
    """Classify one artifact from exact commit/tree/path evidence."""
    evidence = {
        "headSha": artifact.head_sha,
        "treeSha": artifact.tree_sha,
        "baseSha": artifact.base_sha,
        "baseTreeSha": artifact.base_tree_sha,
        "integratedTrees": list(artifact.integrated_trees),
        "changedPaths": list(artifact.changed_paths),
        "uniquePaths": list(artifact.unique_paths),
        "integratedPaths": list(artifact.integrated_paths),
        "commitsAhead": artifact.commits_ahead,
        "uncommitted": artifact.uncommitted,
        "attached": artifact.attached,
        "derivedFromRepo": artifact.derived,
    }
    if _is_protected(artifact.name):
        return Classification(CLASS_PROTECTED, "protected_branch", evidence)
    if artifact.kind == KIND_RUNTIME_RESIDUE:
        return Classification(CLASS_EMPTY, "controller_runtime_residue", evidence)
    if artifact.uncommitted:
        return Classification(CLASS_UNCOMMITTED, "uncommitted_changes", evidence)
    if artifact.kind in {KIND_PR, KIND_BRANCH, KIND_WORKTREE}:
        if not _valid_sha(artifact.head_sha) or not _valid_sha(artifact.tree_sha):
            return Classification(CLASS_UNKNOWN, "missing_commit_or_tree", evidence)
        if not _valid_sha(artifact.base_tree_sha) and not artifact.integrated_trees:
            return Classification(CLASS_UNKNOWN, "missing_integration_identity", evidence)

    tree = artifact.tree_sha
    base_tree = artifact.base_tree_sha
    ahead = artifact.commits_ahead
    unique = artifact.unique_paths
    integrated_paths = artifact.integrated_paths
    changed = artifact.changed_paths

    if ahead == 0 or (
        tree == base_tree
        and not unique
        and not changed
        and (ahead in (0, None))
        and tree not in artifact.integrated_trees
    ):
        return Classification(CLASS_EMPTY, "empty_diff", evidence)

    if (tree and tree in artifact.integrated_trees) or (
        tree == base_tree and ahead is not None and ahead > 0
    ):
        return Classification(
            CLASS_TREE_EQUIVALENT_SUPERSEDED,
            "tree_matches_integrated_commit",
            evidence,
        )

    if unique and integrated_paths:
        return Classification(
            CLASS_PARTIALLY_INTEGRATED,
            "subset_of_paths_already_integrated",
            evidence,
        )

    if unique or (tree and base_tree and tree != base_tree):
        return Classification(CLASS_UNIQUE_WORK, "unique_tree_or_paths", evidence)

    return Classification(CLASS_UNKNOWN, "insufficient_path_evidence", evidence)


def decide_action(artifact: Artifact, classification: Classification) -> str:
    """Return the fail-closed action. Unique work never becomes a keep/delete choice."""
    if not artifact.exists:
        return ACTION_ALREADY_ABSENT
    if artifact.kind == KIND_PR:
        # Local Git cannot prove GitHub PR identity; never auto-close from inventory.
        return ACTION_PRESERVE_FOR_DECISION
    if artifact.attached or classification.classification == CLASS_PROTECTED:
        return ACTION_KEEP
    if artifact.owner == OWNER_WORKER:
        return ACTION_PRESERVE_FOR_DECISION
    if classification.classification in CLEANABLE_CLASSES and artifact.controller_owned and artifact.derived:
        return ACTION_CLEAN
    if classification.classification in {
        CLASS_UNIQUE_WORK,
        CLASS_UNCOMMITTED,
        CLASS_PARTIALLY_INTEGRATED,
        CLASS_UNKNOWN,
    }:
        return ACTION_PRESERVE_FOR_DECISION
    # Not controller-owned empty/superseded residue: preserve, never auto-delete.
    return ACTION_PRESERVE_FOR_DECISION


def classify_inventory(artifacts: Sequence[Artifact]) -> list[Decision]:
    decisions: list[Decision] = []
    for artifact in artifacts:
        classification = classify_artifact(artifact)
        decisions.append(Decision(artifact, classification, decide_action(artifact, classification)))
    return decisions


def _try_clean(mutator: CleanFn, artifact: Artifact) -> str:
    attempts = 0
    last: Exception | None = None
    while attempts < MAX_INFRASTRUCTURE_ATTEMPTS:
        attempts += 1
        try:
            return mutator(artifact)
        except IdentityUncertainty:
            raise
        except InfrastructureError as exc:
            last = exc
            continue
        except ReconciliationError:
            raise
    assert last is not None
    raise last


def default_mutator(repo: Path) -> CleanFn:
    """Filesystem/git mutator for disposable repos. Never calls GitHub."""

    def _clean(artifact: Artifact) -> str:
        if artifact.kind == KIND_RUNTIME_RESIDUE:
            if artifact.name not in ROOT_RESIDUE_NAMES:
                raise IdentityUncertainty("untrusted_residue_name", artifact.name)
            src = (Path(repo) / artifact.name).resolve()
            if src.parent != Path(repo).resolve() or src.name != artifact.name:
                raise IdentityUncertainty("unsafe_residue_path", f"{src} is not repository-root residue")
            if not src.is_file():
                return ACTION_ALREADY_ABSENT
            src.unlink()
            return ACTION_CLEAN
        if artifact.kind == KIND_WORKTREE:
            listed = _list_worktrees(repo)
            try:
                wt = Path(artifact.path or "").resolve()
            except OSError as exc:
                raise IdentityUncertainty("unsafe_worktree_path", str(exc)) from exc
            match = next((item for item in listed if Path(item["path"]).resolve() == wt), None)
            if match is None:
                raise IdentityUncertainty("unregistered_worktree", str(wt))
            if not wt.exists():
                return ACTION_ALREADY_ABSENT
            if match.get("primary") or match.get("locked") or not match.get("contained"):
                raise IdentityUncertainty("unsafe_worktree", str(wt))
            if not _same_git_common_dir(repo, wt):
                raise IdentityUncertainty("external_worktree", str(wt))
            live_branch = str(match.get("branch") or "")
            if artifact.name != live_branch:
                raise IdentityUncertainty("worktree_name_mismatch", f"{artifact.name} != {live_branch}")
            _require_live_controller_ref(repo, live_branch)
            if _worktree_dirty(wt):
                raise IdentityUncertainty("dirty_worktree", str(wt))
            head = _rev_parse(wt, "HEAD")
            if not head or not _lineage_allows_clean(repo, head):
                raise IdentityUncertainty("unproven_cleanable_lineage", str(wt))
            result = subprocess.run(
                ["git", "worktree", "remove", "--", str(wt)],
                cwd=repo,
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                raise InfrastructureError(
                    "worktree_remove_failed",
                    (result.stderr or result.stdout or "git worktree remove failed").strip(),
                )
            return ACTION_CLEAN
        if artifact.kind == KIND_BRANCH:
            _require_live_controller_ref(repo, artifact.name)
            if any(item.get("branch") == artifact.name for item in _list_worktrees(repo)):
                raise IdentityUncertainty("attached_worktree", artifact.name)
            head = _local_branch_sha(repo, artifact.name)
            if head is None:
                return ACTION_ALREADY_ABSENT
            if not _lineage_allows_clean(repo, head):
                raise IdentityUncertainty("unproven_cleanable_lineage", artifact.name)
            merged = subprocess.run(
                ["git", "branch", "-d", "--", artifact.name],
                cwd=repo,
                text=True,
                capture_output=True,
                check=False,
            )
            if merged.returncode == 0:
                return ACTION_CLEAN
            result = subprocess.run(
                ["git", "branch", "-D", "--", artifact.name],
                cwd=repo,
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                text = (result.stderr or result.stdout or merged.stderr or "").strip()
                if "not found" in text.lower() or "unknown" in text.lower():
                    return ACTION_ALREADY_ABSENT
                raise InfrastructureError("branch_delete_failed", text)
            return ACTION_CLEAN
        if artifact.kind == KIND_PR:
            raise IdentityUncertainty(
                "github_mutation_not_injected",
                "PR close requires an injected mutator; live GitHub is not called",
            )
        raise ReconciliationError("unsupported_clean", artifact.kind)

    return _clean


def _checkout_is_dirty(repo: Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def reconcile(
    *,
    repo: Path,
    artifacts: Sequence[Artifact],
    apply: bool = False,
    mutator: CleanFn | None = None,
    state_dir: Path | None = None,
    force_failure: str | None = None,
) -> dict[str, Any]:
    """Classify inventory, optionally clean allowed artifacts, and place transients in state dir."""
    repo = Path(repo)
    state = ensure_state_dir(state_dir or resolve_state_dir(repo))
    write_json(state / "run.json", {"schemaVersion": SCHEMA_VERSION, "apply": apply})
    write_json(state / "outcome.json", {"status": "running", "detail": "reconciliation_started"})

    combined: list[Artifact] = []
    seen_ids: set[str] = set()
    for item in artifacts:
        derived = materialize_artifact(repo, item, state_dir=state)
        combined.append(derived)
        seen_ids.add(derived.id)
    for residue in inventory_root_residue(repo):
        if residue.id not in seen_ids:
            combined.append(materialize_artifact(repo, residue, state_dir=state))
            seen_ids.add(residue.id)

    decisions = sorted(
        classify_inventory(combined),
        key=lambda decision: KIND_RANK.get(decision.artifact.kind, 9),
    )
    rows: list[dict[str, Any]] = []
    cleaned: list[str] = []
    preserved: list[str] = []
    kept: list[str] = []
    already: list[str] = []
    cleaner = mutator or default_mutator(repo)
    applied_any = False
    failure_code: str | None = None
    failure_detail: str | None = None

    try:
        if force_failure:
            raise InfrastructureError("forced_failure", force_failure)
        for decision in decisions:
            artifact = decision.artifact
            classification = decision.classification
            action = decision.action
            applied = False
            result_action = action
            # Root residue is always cleaned on a successful pass. Other
            # kinds require --apply and remain preserved unless allowed.
            should_apply = action == ACTION_CLEAN and (
                apply or artifact.kind == KIND_RUNTIME_RESIDUE
            )
            if should_apply:
                result_action = _try_clean(cleaner, artifact)
                applied = result_action in {ACTION_CLEAN, ACTION_ALREADY_ABSENT}
                applied_any = applied_any or result_action == ACTION_CLEAN
            row = {
                "id": artifact.id,
                "kind": artifact.kind,
                "name": artifact.name,
                "owner": artifact.owner,
                "controllerOwned": artifact.controller_owned,
                "classification": classification.classification,
                "reason": classification.reason,
                "action": result_action if apply else action,
                "plannedAction": action,
                "applied": applied,
                "preservedForDecision": action == ACTION_PRESERVE_FOR_DECISION,
                "evidence": dict(classification.evidence),
            }
            rows.append(row)
            if action == ACTION_PRESERVE_FOR_DECISION:
                preserved.append(artifact.id)
            elif action == ACTION_KEEP:
                kept.append(artifact.id)
            elif action == ACTION_ALREADY_ABSENT:
                already.append(artifact.id)
            elif action == ACTION_CLEAN:
                cleaned.append(artifact.id)

        # Root residue is always controller-generated. Success deletes it so
        # the checkout stays clean even when branch/PR apply is dry-run.
        _delete_root_residue(repo)

        report = _build_report(
            state_dir=state,
            ok=True,
            apply=apply,
            rows=rows,
            cleaned=cleaned,
            preserved=preserved,
            kept=kept,
            already=already,
            diagnostics_retained=False,
            replay=not applied_any and apply,
        )
        finish_success(state, report)
        porcelain = _checkout_is_dirty(repo)
        residue_left = [item.name for item in inventory_root_residue(repo)]
        report["rootResidue"] = residue_left
        report["checkoutDirty"] = porcelain
        if residue_left:
            raise ReconciliationError("root_residue_remaining", ",".join(residue_left))
        write_json(state / REPORT_FILENAME, report)
        return report
    except Exception as exc:
        if isinstance(exc, ReconciliationError):
            failure_code, failure_detail = exc.code, exc.detail
        else:
            failure_code, failure_detail = "reconciliation_failed", str(exc)
        retained = _move_root_residue_to_state(repo, state)
        report = _build_report(
            state_dir=state,
            ok=False,
            apply=apply,
            rows=rows,
            cleaned=cleaned,
            preserved=preserved,
            kept=kept,
            already=already,
            diagnostics_retained=True,
            replay=False,
            error={"code": failure_code, "detail": failure_detail},
        )
        finish_failure(
            state,
            report,
            diagnostics={
                "code": failure_code,
                "detail": failure_detail,
                "retainedRootResidue": retained,
            },
        )
        raise
    finally:
        # Running outcome is a transient; success path already cleared it.
        if failure_code:
            write_json(
                state / "outcome.json",
                {"status": "failed", "detail": failure_code, "message": failure_detail},
            )


def _build_report(
    *,
    state_dir: Path,
    ok: bool,
    apply: bool,
    rows: list[dict[str, Any]],
    cleaned: list[str],
    preserved: list[str],
    kept: list[str],
    already: list[str],
    diagnostics_retained: bool,
    replay: bool,
    error: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "ok": ok,
        "apply": apply,
        "idempotentReplay": replay,
        "stateDir": str(state_dir),
        "diagnosticsRetained": diagnostics_retained,
        "rootResidue": [],
        "checkoutDirty": [],
        "artifacts": rows,
        "cleaned": cleaned,
        "preservedForDecision": preserved,
        "kept": kept,
        "alreadyAbsent": already,
        "error": dict(error) if error else None,
    }


def artifact_from_dict(payload: Mapping[str, Any]) -> Artifact:
    if not isinstance(payload, Mapping):
        raise ReconciliationError("invalid_artifact", "artifact must be an object")
    return Artifact(
        id=str(payload.get("id") or payload.get("name") or ""),
        kind=str(payload.get("kind") or ""),
        name=str(payload.get("name") or ""),
        controller_owned=bool(payload.get("controllerOwned", False)),
        owner=str(payload.get("owner") or OWNER_UNKNOWN),
        head_sha=payload.get("headSha"),
        tree_sha=payload.get("treeSha"),
        base_sha=payload.get("baseSha"),
        base_tree_sha=payload.get("baseTreeSha"),
        integrated_trees=tuple(payload.get("integratedTrees") or ()),
        integrated_commits=tuple(payload.get("integratedCommits") or ()),
        changed_paths=tuple(payload.get("changedPaths") or ()),
        unique_paths=tuple(payload.get("uniquePaths") or ()),
        integrated_paths=tuple(payload.get("integratedPaths") or ()),
        uncommitted=bool(payload.get("uncommitted", False)),
        commits_ahead=payload.get("commitsAhead"),
        exists=bool(payload.get("exists", True)),
        path=payload.get("path"),
    )


def load_inventory(path: Path) -> list[Artifact]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, Mapping):
        rows = data.get("artifacts") or data.get("inventory") or []
    else:
        rows = data
    if not isinstance(rows, list):
        raise ReconciliationError("invalid_inventory", "inventory must be a list")
    return [artifact_from_dict(row) for row in rows]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safe stale delivery-artifact reconciliation")
    parser.add_argument("--repo", default=".", help="repository root")
    parser.add_argument("--inventory", help="JSON inventory of PRs/branches/worktrees")
    parser.add_argument("--state-dir", default="", help="override controller state directory")
    parser.add_argument("--apply", action="store_true", help="clean only allowed controller-owned artifacts")
    parser.add_argument("--json", action="store_true", help="print the reconciliation report")
    args = parser.parse_args(list(argv) if argv is not None else None)
    repo = Path(args.repo).resolve()
    artifacts = load_inventory(Path(args.inventory)) if args.inventory else []
    try:
        report = reconcile(
            repo=repo,
            artifacts=artifacts,
            apply=args.apply,
            state_dir=Path(args.state_dir) if args.state_dir else None,
        )
    except ReconciliationError as exc:
        print(f"FAIL: {exc.code}: {exc.detail}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"ok={report['ok']} cleaned={len(report['cleaned'])} preserved={len(report['preservedForDecision'])}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
