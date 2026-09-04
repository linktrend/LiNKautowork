#!/usr/bin/env python3
"""PKT-08 declarative generated-output closure and finalization gate."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping

GRAPH_RELATIVE_PATH = "core/managed-core/config/generated-output-closure.json"
PACKAGED_GRAPH_RELATIVE_PATH = ".ide-development/config/generated-output-closure.json"
DEFAULT_GRAPH_EXCLUSIONS = frozenset({".github/linktrend-secret-scan-fixtures.json"})
DEFAULT_MAX_PASSES = 3
BASELINE_SHA_ENV = "LINKTREND_TARGET_BASELINE_SHA"
BASELINE_REF_ENV = "LINKTREND_TARGET_BASELINE_REF"
SHA40 = r"[0-9a-f]{40}"
PUSH_BRANCH = r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*"


class ClosureError(ValueError):
    """Fail-closed generated-output closure diagnostic."""

    def __init__(self, code: str, detail: str, **diagnostics: Any) -> None:
        self.code = code
        self.detail = detail
        self.diagnostics = diagnostics
        suffix = f" {json.dumps(diagnostics, sort_keys=True)}" if diagnostics else ""
        super().__init__(f"{code}: {detail}{suffix}")


@dataclass(frozen=True)
class OutputSpec:
    id: str
    output: str
    generator: tuple[str, ...]
    invalidating_sources: tuple[str, ...]
    depends_on: tuple[str, ...]
    additional_outputs: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeneratedOutputGraph:
    schema_version: int
    max_passes: int
    outputs: tuple[OutputSpec, ...]
    audits: Mapping[str, Any]

    @property
    def output_paths(self) -> frozenset[str]:
        return frozenset(item.output for item in self.outputs)

    def ordered_outputs(self) -> tuple[OutputSpec, ...]:
        by_id = {item.id: item for item in self.outputs}
        pending = {item.id: set(item.depends_on) for item in self.outputs}
        ordered: list[OutputSpec] = []
        while pending:
            ready = sorted(item_id for item_id, deps in pending.items() if not deps)
            if not ready:
                raise ClosureError(
                    "ambiguous_dependency",
                    "generated-output dependency graph contains a cycle",
                    outputs=sorted(pending),
                )
            for item_id in ready:
                ordered.append(by_id[item_id])
                pending.pop(item_id)
            for deps in pending.values():
                deps.difference_update(ready)
        return tuple(ordered)


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _safe_relative(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClosureError("ambiguous_dependency", f"{label} must be non-empty")
    rel = PurePosixPath(value)
    if rel.is_absolute() or ".." in rel.parts or "\\" in value:
        raise ClosureError("ambiguous_dependency", f"{label} must be repository-relative", value=value)
    return rel.as_posix()


def _resolve_graph_path(root: Path, graph_path: str) -> Path:
    requested = root / graph_path
    if requested.is_file() or graph_path != GRAPH_RELATIVE_PATH:
        return requested
    packaged = root / PACKAGED_GRAPH_RELATIVE_PATH
    return packaged if packaged.is_file() else requested


def load_graph(repo_root: Path | str, graph_path: str = GRAPH_RELATIVE_PATH) -> GeneratedOutputGraph:
    root = Path(repo_root).resolve()
    path = _resolve_graph_path(root, graph_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClosureError("graph_invalid", f"cannot read generated-output graph: {graph_path}") from exc
    if not isinstance(payload, Mapping) or payload.get("schemaVersion") != 1 or payload.get("kind") != "generated-output-closure":
        raise ClosureError("graph_invalid", "generated-output graph identity is invalid")
    raw_outputs = payload.get("outputs")
    if not isinstance(raw_outputs, list) or not raw_outputs:
        raise ClosureError("graph_invalid", "generated-output graph requires outputs")
    max_passes = payload.get("maxPasses", DEFAULT_MAX_PASSES)
    if not isinstance(max_passes, int) or isinstance(max_passes, bool) or max_passes < 1 or max_passes > 10:
        raise ClosureError("graph_invalid", "maxPasses must be between one and ten")

    outputs: list[OutputSpec] = []
    ids: set[str] = set()
    paths: set[str] = set()
    for index, raw in enumerate(raw_outputs):
        if not isinstance(raw, Mapping):
            raise ClosureError("graph_invalid", f"outputs[{index}] must be an object")
        output_id = raw.get("id")
        if not isinstance(output_id, str) or not output_id.strip() or output_id in ids:
            raise ClosureError("ambiguous_dependency", f"duplicate or invalid output id at outputs[{index}]")
        output_rel = _safe_relative(raw.get("output"), f"outputs[{index}].output")
        if output_rel in paths:
            raise ClosureError("ambiguous_dependency", f"multiple generators own {output_rel}")
        command = raw.get("generator")
        if not isinstance(command, list) or not command or any(not isinstance(item, str) or not item for item in command):
            raise ClosureError("ambiguous_dependency", f"outputs[{index}].generator must be an argv array")
        sources = raw.get("invalidatingSources")
        if not isinstance(sources, list) or not sources or any(not isinstance(item, str) or not item for item in sources):
            raise ClosureError("ambiguous_dependency", f"invalidating source set missing for {output_rel}")
        safe_sources = tuple(_safe_relative(item, f"outputs[{index}].invalidatingSources") for item in sources)
        depends = raw.get("dependsOn", [])
        if not isinstance(depends, list) or any(not isinstance(item, str) or not item for item in depends):
            raise ClosureError("ambiguous_dependency", f"dependsOn must be an array for {output_rel}")
        additional = raw.get("additionalOutputs", [])
        if not isinstance(additional, list) or any(not isinstance(item, str) or not item for item in additional):
            raise ClosureError("ambiguous_dependency", f"additionalOutputs must be an array for {output_rel}")
        safe_additional = tuple(_safe_relative(item, f"outputs[{index}].additionalOutputs") for item in additional)
        ids.add(output_id)
        paths.add(output_rel)
        outputs.append(
            OutputSpec(
                id=output_id,
                output=output_rel,
                generator=tuple(command),
                invalidating_sources=safe_sources,
                depends_on=tuple(depends),
                additional_outputs=safe_additional,
            )
        )
    unknown = sorted({dep for item in outputs for dep in item.depends_on if dep not in ids})
    if unknown:
        raise ClosureError("ambiguous_dependency", "dependency references unknown output", dependencies=unknown)
    audits = payload.get("audits", {})
    if not isinstance(audits, Mapping):
        raise ClosureError("graph_invalid", "audits must be an object when provided")
    graph = GeneratedOutputGraph(1, max_passes, tuple(outputs), dict(audits))
    graph.ordered_outputs()
    return graph


def _audit_command(root: Path, command: Iterable[str], *, label: str) -> None:
    argv = tuple(command)
    if not argv or any(not isinstance(item, str) or not item.strip() for item in argv):
        raise ClosureError("dogfood_command_invalid", f"{label} must be a non-empty argv array")
    command_start = 0
    search_paths = [root]
    if argv[0] == "env":
        command_start = 1
        while command_start < len(argv) and "=" in argv[command_start]:
            name, value = argv[command_start].split("=", 1)
            if name == "PYTHONPATH":
                search_paths = [
                    root / Path(item)
                    for item in value.split(os.pathsep)
                    if item
                ] or [root]
            command_start += 1
        if command_start >= len(argv):
            raise ClosureError("dogfood_command_invalid", f"{label} has no executable")
    executable = argv[command_start]
    if "/" in executable or "\\" in executable:
        candidate = root / executable
        if not candidate.is_file() or candidate.is_symlink():
            raise ClosureError(
                "dogfood_command_missing",
                f"{label} executable does not exist",
                command=list(argv),
            )
        return
    if shutil.which(executable) is None:
        raise ClosureError(
            "dogfood_command_missing",
            f"{label} executable is unavailable",
            command=list(argv),
        )
    command_args = argv[command_start + 1 :]
    if "-m" in command_args:
        module_index = command_args.index("-m")
        if module_index + 1 >= len(command_args):
            raise ClosureError(
                "dogfood_command_invalid",
                f"{label} -m requires a module reference",
                command=list(argv),
            )
        module = command_args[module_index + 1]
        if (
            not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", module)
            or not any(
                (search / Path(*module.split("."))).with_suffix(".py").is_file()
                or (search / Path(*module.split(".")) / "__init__.py").is_file()
                for search in search_paths
            )
        ):
            raise ClosureError(
                "dogfood_command_missing",
                f"{label} module reference does not exist",
                command=list(argv),
                module=module,
            )
    for argument in command_args:
        if argument.endswith((".py", ".sh", ".mjs")) and "/" in argument:
            candidate = root / argument
            if not candidate.is_file() or candidate.is_symlink():
                raise ClosureError(
                    "dogfood_command_missing",
                    f"{label} command path does not exist",
                    command=list(argv),
                    path=argument,
                )


def audit_dogfood_improvement_closure(
    repo_root: Path | str,
    *,
    graph: GeneratedOutputGraph | None = None,
    graph_path: str = GRAPH_RELATIVE_PATH,
) -> dict[str, Any]:
    """Audit corrective-event coverage and executable closure commands.

    The graph is the only declaration authority.  This audit validates that
    each declared event maps to a callable already present in the component
    source and that every generator command is executable in the current
    source, managed, or extracted tree.
    """
    root = Path(repo_root).resolve()
    loaded = graph or load_graph(root, graph_path)
    dogfood = loaded.audits.get("DOGFOOD_IMPROVEMENT_CLOSURE")
    lean = loaded.audits.get("LEAN_DESIGN")
    if dogfood is None and lean is None:
        return {"ok": True, "status": "not-configured"}
    if not isinstance(dogfood, Mapping) or not isinstance(lean, Mapping):
        raise ClosureError(
            "dogfood_audit_invalid",
            "DOGFOOD_IMPROVEMENT_CLOSURE and LEAN_DESIGN must be configured together",
        )

    mappings = dogfood.get("correctiveEventMappings")
    if not isinstance(mappings, list) or not mappings:
        raise ClosureError(
            "dogfood_mapping_missing",
            "systemic corrective event mappings are required",
        )
    seen_ids: set[str] = set()
    seen_events: set[tuple[str, str]] = set()
    mapping_results: list[dict[str, Any]] = []
    total_events = 0
    for index, raw in enumerate(mappings):
        if not isinstance(raw, Mapping):
            raise ClosureError("dogfood_mapping_invalid", f"mapping[{index}] must be an object")
        mapping_id = raw.get("id")
        source = raw.get("source")
        events = raw.get("events")
        control = raw.get("control")
        if (
            not isinstance(mapping_id, str)
            or not mapping_id
            or mapping_id in seen_ids
            or not isinstance(source, str)
            or not source
            or not isinstance(events, Mapping)
            or not events
            or not isinstance(control, str)
            or not control
        ):
            raise ClosureError("dogfood_mapping_invalid", f"mapping[{index}] has incomplete identity")
        source_rel = _safe_relative(source, f"mapping[{index}].source")
        source_path = root / source_rel
        if not source_path.is_file() or source_path.is_symlink():
            raise ClosureError(
                "dogfood_mapping_source_missing",
                f"corrective mapping source does not exist: {source_rel}",
                mapping=mapping_id,
            )
        source_text = source_path.read_text(encoding="utf-8")
        if control not in source_text:
            raise ClosureError(
                "dogfood_control_missing",
                f"corrective control is not present in {source_rel}",
                mapping=mapping_id,
                control=control,
            )
        event_names: list[str] = []
        for event, corrective in sorted(events.items()):
            if (
                not isinstance(event, str)
                or not event
                or not isinstance(corrective, str)
                or not corrective
                or (mapping_id, event) in seen_events
            ):
                raise ClosureError(
                    "dogfood_mapping_invalid",
                    f"mapping[{index}] contains an invalid or duplicate event",
                )
            if event not in source_text or corrective not in source_text:
                raise ClosureError(
                    "dogfood_event_uncovered",
                    f"corrective event mapping is not covered by {source_rel}",
                    mapping=mapping_id,
                    event=event,
                    corrective=corrective,
                )
            seen_events.add((mapping_id, event))
            event_names.append(event)
        seen_ids.add(mapping_id)
        total_events += len(event_names)
        mapping_results.append(
            {
                "id": mapping_id,
                "source": source_rel,
                "control": control,
                "events": event_names,
            }
        )

    for index, spec in enumerate(loaded.outputs):
        _audit_command(root, spec.generator, label=f"outputs[{index}].generator")
    declared_commands = dogfood.get("executableCommands", [])
    if not isinstance(declared_commands, list):
        raise ClosureError("dogfood_command_invalid", "executableCommands must be an array")
    for index, raw in enumerate(declared_commands):
        if not isinstance(raw, Mapping):
            raise ClosureError("dogfood_command_invalid", f"executableCommands[{index}] must be an object")
        command = raw.get("command")
        if not isinstance(command, list):
            raise ClosureError("dogfood_command_invalid", f"executableCommands[{index}].command must be argv")
        _audit_command(root, command, label=f"executableCommands[{index}]")

    limits = lean.get("limits")
    if not isinstance(limits, Mapping):
        raise ClosureError("lean_design_invalid", "LEAN_DESIGN limits are required")
    max_mappings = limits.get("maxCorrectiveMappings")
    max_events = limits.get("maxCorrectiveEvents")
    if (
        isinstance(max_mappings, bool)
        or not isinstance(max_mappings, int)
        or isinstance(max_events, bool)
        or not isinstance(max_events, int)
        or len(mapping_results) > max_mappings
        or total_events > max_events
    ):
        raise ClosureError(
            "lean_design_complexity",
            "corrective-event coverage exceeds configured complexity limits",
            mappings=len(mapping_results),
            events=total_events,
            limits=dict(limits),
        )
    pairs = [(row["source"], row["control"]) for row in mapping_results]
    if len(pairs) != len(set(pairs)):
        raise ClosureError(
            "lean_design_redundancy",
            "multiple corrective mappings duplicate one source/control authority",
        )
    return {
        "ok": True,
        "status": "audited",
        "dogfood": {
            "mappings": mapping_results,
            "executableCommands": len(declared_commands) + len(loaded.outputs),
        },
        "leanDesign": {
            "mappingCount": len(mapping_results),
            "eventCount": total_events,
            "limits": dict(limits),
        },
    }


def _git_index_entries(root: Path) -> list[tuple[str, str, str]]:
    result = subprocess.run(
        ["git", "ls-files", "-s", "-z", "--"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ClosureError("git_identity_failure", (result.stderr or result.stdout).decode("utf-8", "replace").strip())
    entries: list[tuple[str, str, str]] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            meta, path_bytes = raw.split(b"\t", 1)
            mode, oid, stage = meta.split(b" ", 2)
        except ValueError as exc:
            raise ClosureError("git_identity_failure", "cannot parse git index identity") from exc
        entries.append((path_bytes.decode("utf-8"), mode.decode("ascii"), f"{oid.decode('ascii')}:{stage.decode('ascii')}"))
    return entries


def _expanded_exclusions(root: Path, graph: GeneratedOutputGraph) -> frozenset[str]:
    exact = set(graph.output_paths)
    for rel in _walk_files(root, exact):
        if any(_glob_matches(rel, pattern) for spec in graph.outputs for pattern in spec.additional_outputs):
            exact.add(rel)
    return frozenset(exact)


def _graph_exclusions(root: Path, graph_path: str | None) -> frozenset[str]:
    if graph_path is None:
        return DEFAULT_GRAPH_EXCLUSIONS
    try:
        return _expanded_exclusions(root, load_graph(root, graph_path))
    except ClosureError:
        return DEFAULT_GRAPH_EXCLUSIONS


def candidate_source_tree(root: Path | str, graph_path: str | None = GRAPH_RELATIVE_PATH) -> str:
    """Return a stable tracked-content identity excluding generated outputs."""
    checkout = Path(root).resolve()
    exclusions = _graph_exclusions(checkout, graph_path)
    digest = hashlib.sha1()
    for path, mode, identity in sorted(_git_index_entries(checkout)):
        if path in exclusions:
            continue
        oid = identity.split(":", 1)[0]
        digest.update(mode.encode("ascii"))
        digest.update(b" ")
        digest.update(oid.encode("ascii"))
        digest.update(b" ")
        digest.update(path.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _walk_files(root: Path, exclusions: Iterable[str]) -> list[str]:
    excluded = set(exclusions)
    result: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = _relative(root, path)
        if rel in excluded or any(part in {".git", "build", "__pycache__", ".linktrend"} for part in PurePosixPath(rel).parts):
            continue
        result.append(rel)
    return sorted(result)


def _glob_matches(rel: str, pattern: str) -> bool:
    normalized = pattern.replace("\\", "/")
    if normalized in {"**", "**/*"}:
        return True
    if normalized.startswith("**/"):
        normalized = normalized[3:]
        if fnmatch.fnmatchcase(rel, normalized) or PurePosixPath(rel).match(normalized):
            return True
    if normalized.endswith("/**"):
        return rel == normalized[:-3].rstrip("/") or rel.startswith(normalized[:-2])
    return fnmatch.fnmatchcase(rel, normalized) or PurePosixPath(rel).match(normalized)


def _source_paths(root: Path, spec: OutputSpec, exclusions: frozenset[str]) -> list[str]:
    files = _walk_files(root, exclusions)
    paths = [rel for rel in files if any(_glob_matches(rel, pattern) for pattern in spec.invalidating_sources)]
    if not paths:
        raise ClosureError(
            "ambiguous_dependency",
            f"invalidating source set matches no files for {spec.output}",
            output=spec.output,
            sourceSet=list(spec.invalidating_sources),
        )
    return paths


def _digest_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _source_digest(root: Path, paths: Iterable[str]) -> str:
    values = {rel: _digest_file(root / rel) for rel in paths}
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _output_digests(root: Path, graph: GeneratedOutputGraph) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for spec in graph.outputs:
        path = root / spec.output
        result[spec.output] = _digest_file(path) if path.is_file() and not path.is_symlink() else None
        for rel in _walk_files(root, {spec.output}):
            if any(_glob_matches(rel, pattern) for pattern in spec.additional_outputs):
                result[rel] = _digest_file(root / rel)
    return result


def _declared_output_paths(root: Path, graph: GeneratedOutputGraph) -> list[str]:
    return sorted(_expanded_exclusions(root, graph))


def _git_dirty(root: Path, rel: str) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", rel],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return bool(result.returncode == 0 and result.stdout.strip())


def _diagnostic(
    code: str,
    spec: OutputSpec,
    *,
    expected_digest: str | None,
    observed_digest: str | None,
    expected_tree: str,
    observed_tree: str,
    detail: str,
) -> ClosureError:
    return ClosureError(
        code,
        detail,
        output=spec.output,
        generator=list(spec.generator),
        expectedDigest=expected_digest,
        observedDigest=observed_digest,
        expectedTree=expected_tree,
        observedTree=observed_tree,
        invalidatingSources=list(spec.invalidating_sources),
    )


def close_generated_outputs(
    repo_root: Path | str,
    *,
    graph_path: str = GRAPH_RELATIVE_PATH,
    post_generation_hook: Callable[[], None] | None = None,
    _require_clean_outputs: bool = True,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    graph = load_graph(root, graph_path)
    audit = audit_dogfood_improvement_closure(root, graph=graph, graph_path=graph_path)
    exclusions = _expanded_exclusions(root, graph)
    if _require_clean_outputs:
        dirty = sorted(rel for rel in _declared_output_paths(root, graph) if _git_dirty(root, rel))
        if dirty:
            raise ClosureError("dirty_output", "generated output is already dirty", outputs=dirty)
    source_maps = {
        spec.id: _source_paths(root, spec, exclusions)
        for spec in graph.outputs
    }
    source_before = {
        spec.id: _source_digest(root, source_maps[spec.id])
        for spec in graph.outputs
    }
    tree_before = candidate_source_tree(root, graph_path)
    output_before = _output_digests(root, graph)
    observed_tree = tree_before
    passes = 0
    for passes in range(1, graph.max_passes + 1):
        for spec in graph.ordered_outputs():
            try:
                completed = subprocess.run(
                    list(spec.generator),
                    cwd=root,
                    text=True,
                    capture_output=True,
                    check=False,
                )
            except OSError as exc:
                raise _diagnostic(
                    "generator_failure",
                    spec,
                    expected_digest=output_before.get(spec.output),
                    observed_digest=_output_digests(root, graph).get(spec.output),
                    expected_tree=tree_before,
                    observed_tree=observed_tree,
                    detail=str(exc),
                ) from exc
            if completed.returncode:
                detail = (completed.stderr or completed.stdout or "generator failed").strip()[-1000:]
                raise _diagnostic(
                    "generator_failure",
                    spec,
                    expected_digest=output_before.get(spec.output),
                    observed_digest=_output_digests(root, graph).get(spec.output),
                    expected_tree=tree_before,
                    observed_tree=observed_tree,
                    detail=detail,
                )
            path = root / spec.output
            if not path.is_file() or path.is_symlink():
                raise _diagnostic(
                    "generator_failure",
                    spec,
                    expected_digest=output_before.get(spec.output),
                    observed_digest=None,
                    expected_tree=tree_before,
                    observed_tree=observed_tree,
                    detail="generator did not produce a physical output",
                )

        if post_generation_hook is not None:
            command_output_digests = _output_digests(root, graph)
            post_generation_hook()
            after_hook_outputs = _output_digests(root, graph)
            if command_output_digests != after_hook_outputs:
                changed = sorted(
                    path for path in command_output_digests
                    if command_output_digests[path] != after_hook_outputs[path]
                )
                raise ClosureError(
                    "post_generation_mutation",
                    "generated output changed after generator closure",
                    outputs=changed,
                    expectedDigest=command_output_digests,
                    observedDigest=after_hook_outputs,
                    expectedTree=tree_before,
                    observedTree=candidate_source_tree(root, graph_path),
                )

        tree_after = candidate_source_tree(root, graph_path)
        source_after = {
            spec.id: _source_digest(root, source_maps[spec.id])
            for spec in graph.outputs
        }
        if source_after != source_before or tree_after != tree_before:
            raise ClosureError(
                "post_generation_mutation",
                "invalidating source changed during generator closure",
                expectedTree=tree_before,
                observedTree=tree_after,
                expectedDigest=source_before,
                observedDigest=source_after,
            )
        output_after = _output_digests(root, graph)
        if output_after == output_before:
            return {
                "ok": True,
                "passes": passes,
                "generatorOrder": [spec.id for spec in graph.ordered_outputs()],
                "sourceTree": tree_after,
                "invalidatingSources": {
                    spec.id: source_maps[spec.id] for spec in graph.outputs
                },
                "outputDigests": output_after,
                "dogfoodImprovementClosure": audit,
            }
        output_before = output_after
        observed_tree = tree_after
    raise ClosureError(
        "non_convergence",
        "generated outputs did not reach a fixed point",
        expectedTree=tree_before,
        observedTree=observed_tree,
        expectedDigest=source_before,
        observedDigest=output_before,
        passes=graph.max_passes,
    )


def _resolve_commit(root: Path, value: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{value}^{{commit}}"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        return None
    return result.stdout.strip()


def _remote_target_ref(root: Path, ref: str) -> str | None:
    if ref.startswith("refs/remotes/"):
        candidate = ref[len("refs/remotes/") :]
    else:
        candidate = ref
    parts = candidate.split("/")
    if len(parts) < 2 or any(not part for part in parts):
        return None
    remote = parts[0]
    remotes = subprocess.run(
        ["git", "remote"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if remotes.returncode or remote not in remotes.stdout.splitlines():
        return None
    return f"refs/remotes/{candidate}"


def _ensure_remote_target_ref(root: Path, remote_ref: str) -> None:
    """Materialize a configured remote target in shallow checkouts only."""
    if _resolve_commit(root, remote_ref) is not None:
        return
    candidate = remote_ref.removeprefix("refs/remotes/")
    remote, branch = candidate.split("/", 1)
    fetched = subprocess.run(
        [
            "git",
            "fetch",
            "--no-tags",
            remote,
            f"{branch}:refs/remotes/{remote}/{branch}",
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if fetched.returncode or _resolve_commit(root, remote_ref) is None:
        raise ClosureError(
            "candidate_baseline_invalid",
            "authoritative remote target ref does not resolve to a commit",
            ref=remote_ref.removeprefix("refs/remotes/"),
            diagnostics=(fetched.stderr or fetched.stdout or "").strip()[-1000:],
        )


def bind_push_event_baseline(
    repo_root: Path | str,
    *,
    branch: str,
    before_sha: str,
    after_sha: str | None = None,
) -> str:
    """Bind a push predecessor to an exact event-scoped remote target."""
    root = Path(repo_root).resolve()
    if (
        not isinstance(branch, str)
        or not re.fullmatch(PUSH_BRANCH, branch)
        or branch.startswith("refs/")
        or ".." in branch
    ):
        raise ClosureError(
            "candidate_baseline_ref_invalid",
            "push branch must be a safe named branch",
            branch=branch,
        )
    if not isinstance(before_sha, str) or not re.fullmatch(SHA40, before_sha) or set(before_sha) == {"0"}:
        raise ClosureError(
            "candidate_baseline_invalid",
            "push predecessor SHA must be a non-zero 40-character lowercase hexadecimal identity",
        )
    head = _resolve_commit(root, "HEAD")
    before = _resolve_commit(root, before_sha)
    if head is None or before is None:
        raise ClosureError(
            "candidate_baseline_invalid",
            "push predecessor or candidate HEAD does not resolve to a commit",
            before=before_sha,
            head=head,
        )
    if after_sha is not None:
        if not isinstance(after_sha, str) or not re.fullmatch(SHA40, after_sha):
            raise ClosureError("candidate_baseline_invalid", "push after SHA is invalid")
        if after_sha != head:
            raise ClosureError(
                "candidate_baseline_stale",
                "push after SHA does not match the checked-out candidate HEAD",
                after=after_sha,
                head=head,
            )
    if before == head:
        raise ClosureError(
            "candidate_baseline_equal_head",
            "push predecessor must be distinct from the candidate HEAD",
            baseline=before,
            head=head,
        )
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", before, head],
        cwd=root,
        check=False,
    )
    if ancestor.returncode:
        raise ClosureError(
            "candidate_baseline_stale",
            "push predecessor is not an ancestor of the checked-out candidate",
            baseline=before,
            head=head,
        )
    target = f"refs/remotes/origin/{branch}-before"
    updated = subprocess.run(
        ["git", "update-ref", target, before],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if updated.returncode or _resolve_commit(root, target) != before:
        raise ClosureError(
            "candidate_baseline_invalid",
            "event-bound remote target could not be materialized",
            ref=target.removeprefix("refs/remotes/"),
            diagnostics=(updated.stderr or updated.stdout or "").strip()[-1000:],
        )
    return target.removeprefix("refs/remotes/")


def resolve_candidate_baseline(
    repo_root: Path | str,
    *,
    baseline_sha: str | None = None,
    baseline_ref: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve a distinct candidate baseline from the runtime remote target tip.

    A directly supplied baseline SHA is an exact assertion and remains strict.
    An environment SHA is a refreshable runtime hint: a fast-forwarded remote
    target may supersede it, but unrelated, non-ancestor, or already-at-HEAD
    moves remain fail-closed.
    """
    root = Path(repo_root).resolve()
    runtime = os.environ if environ is None else environ
    explicit_sha = baseline_sha is not None
    sha = baseline_sha if explicit_sha else runtime.get(BASELINE_SHA_ENV)
    ref = baseline_ref or runtime.get(BASELINE_REF_ENV)
    if not ref:
        raise ClosureError(
            "candidate_baseline_missing",
            "exact baseline SHA and authoritative remote ref are required at runtime",
            shaProvided=bool(sha),
            refProvided=bool(ref),
        )
    if sha is not None and (not isinstance(sha, str) or not re.fullmatch(SHA40, sha)):
        raise ClosureError(
            "candidate_baseline_invalid",
            "baseline SHA must be exactly 40 lowercase hexadecimal characters",
        )
    if (
        not isinstance(ref, str)
        or not ref.strip()
        or ref.startswith("-")
        or re.fullmatch(SHA40, ref)
        or any(character.isspace() for character in ref)
    ):
        raise ClosureError(
            "candidate_baseline_ref_invalid",
            "authoritative baseline must be a named configured remote ref",
        )
    remote_ref = _remote_target_ref(root, ref)
    if remote_ref is None:
        raise ClosureError(
            "candidate_baseline_ref_invalid",
            "authoritative baseline must identify a configured remote target",
            ref=ref,
        )
    _ensure_remote_target_ref(root, remote_ref)
    resolved_sha = _resolve_commit(root, sha)
    if resolved_sha != sha:
        raise ClosureError(
            "candidate_baseline_invalid",
            "baseline SHA does not resolve to an available commit",
        )
    resolved_ref = _resolve_commit(root, remote_ref)
    if resolved_ref is None:
        raise ClosureError(
            "candidate_baseline_invalid",
            "authoritative remote target ref does not resolve to a commit",
            ref=ref,
        )
    head = _resolve_commit(root, "HEAD")
    if head is None:
        raise ClosureError("candidate_baseline_invalid", "candidate HEAD does not resolve to a commit")
    if sha is not None:
        resolved_sha = _resolve_commit(root, sha)
        if resolved_sha != sha:
            raise ClosureError(
                "candidate_baseline_invalid",
                "baseline SHA does not resolve to an available commit",
            )
        if resolved_ref != sha:
            if explicit_sha:
                raise ClosureError(
                    "candidate_baseline_stale",
                    "runtime baseline SHA does not match the authoritative remote target tip",
                    ref=ref,
                    expected=resolved_ref,
                    supplied=sha,
                )
            refreshed = subprocess.run(
                ["git", "merge-base", "--is-ancestor", sha, resolved_ref],
                cwd=root,
                check=False,
            )
            if refreshed.returncode or resolved_ref == head:
                raise ClosureError(
                    "candidate_baseline_stale",
                    "runtime baseline SHA cannot be reconciled to the authoritative remote target tip",
                    ref=ref,
                    expected=resolved_ref,
                    supplied=sha,
                )
            sha = resolved_ref
    else:
        sha = resolved_ref
    if head == sha:
        raise ClosureError(
            "candidate_baseline_equal_head",
            "candidate HEAD must be a distinct commit from the target baseline",
            baseline=sha,
            head=head,
        )
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, head],
        cwd=root,
        check=False,
    )
    if ancestor.returncode:
        raise ClosureError(
            "candidate_baseline_stale",
            "authoritative baseline is not an ancestor of the candidate HEAD",
            baseline=sha,
            head=head,
        )
    return sha


def candidate_diff_check(
    repo_root: Path | str,
    *,
    baseline_sha: str | None = None,
    baseline_ref: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Reject whitespace errors in the candidate delta from an exact baseline."""
    root = Path(repo_root).resolve()
    baseline = resolve_candidate_baseline(
        root,
        baseline_sha=baseline_sha,
        baseline_ref=baseline_ref,
        environ=environ,
    )
    checked = subprocess.run(
        ["git", "diff", "--check", "--no-ext-diff", baseline, "--"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    output = (checked.stdout + checked.stderr).strip()
    if checked.returncode:
        raise ClosureError(
            "candidate_whitespace",
            "candidate diff contains trailing whitespace",
            baseline=baseline,
            diagnostics=output[-4000:],
        )
    return {"ok": True, "baseline": baseline, "diagnostics": output}


def finalize_candidate(
    repo_root: Path | str,
    *,
    baseline_sha: str | None = None,
    baseline_ref: str | None = None,
    environ: Mapping[str, str] | None = None,
    graph_path: str = GRAPH_RELATIVE_PATH,
) -> dict[str, Any]:
    """Close generated outputs before the exact runtime-baseline whitespace gate."""
    baseline = resolve_candidate_baseline(
        repo_root,
        baseline_sha=baseline_sha,
        baseline_ref=baseline_ref,
        environ=environ,
    )
    # Finalization is a read-only admission gate. Repair is an explicit
    # separate operation (`--close`) so stale output cannot be regenerated and
    # then accepted by the same invocation (GEN-05).
    closure = verify_generated_outputs(repo_root, graph_path=graph_path)
    whitespace = candidate_diff_check(
        repo_root,
        baseline_sha=baseline,
        baseline_ref=baseline_ref,
        environ=environ,
    )
    return {
        "ok": True,
        "generatedOutputClosure": closure,
        "candidateDiffCheck": whitespace,
    }


def _copy_for_verify(source: Path, destination: Path) -> None:
    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name in {"build", "__pycache__"}}

    shutil.copytree(source, destination, symlinks=True, ignore=ignore)


def verify_generated_outputs(
    repo_root: Path | str,
    *,
    graph_path: str = GRAPH_RELATIVE_PATH,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    graph = load_graph(root, graph_path)
    audit = audit_dogfood_improvement_closure(root, graph=graph, graph_path=graph_path)
    dirty = sorted(rel for rel in _declared_output_paths(root, graph) if _git_dirty(root, rel))
    if dirty:
        raise ClosureError("dirty_output", "generated output is dirty before finalization", outputs=dirty)
    observed = _output_digests(root, graph)
    with tempfile.TemporaryDirectory(prefix="pkt08-closure-") as temp:
        clone = Path(temp) / "repo"
        _copy_for_verify(root, clone)
        expected_result = close_generated_outputs(
            clone,
            graph_path=graph_path,
            _require_clean_outputs=False,
        )
        expected = _output_digests(clone, graph)
    mismatched_paths = sorted(
        path
        for path in set(observed) | set(expected)
        if observed.get(path) != expected.get(path)
    )
    if mismatched_paths:
        path = mismatched_paths[0]
        spec = next((item for item in graph.outputs if item.output == path), graph.outputs[0])
        raise _diagnostic(
            "stale_output",
            spec,
            expected_digest=expected.get(path),
            observed_digest=observed.get(path),
            expected_tree=str(expected_result.get("sourceTree") or ""),
            observed_tree=candidate_source_tree(root, graph_path),
            detail=f"working-tree generated output does not match deterministic generator result: {path}",
        )
    return {
        "ok": True,
        "generatorOrder": expected_result["generatorOrder"],
        "sourceTree": expected_result["sourceTree"],
        "outputDigests": observed,
        "dogfoodImprovementClosure": audit,
    }


def _generate_secret_scan_fixtures(repo_root: Path) -> int:
    try:
        from secret_scan import identify_synthetic_candidates
    except ModuleNotFoundError:  # pragma: no cover - package import path
        from scripts.gitops.secret_scan import identify_synthetic_candidates

    declaration = repo_root / ".github" / "linktrend-secret-scan-fixtures.json"
    payload = json.loads(declaration.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("kind") != "secret-scan-fixtures":
        raise ClosureError("fixture_input_invalid", "secret-scan fixture declaration identity is invalid")
    candidates = identify_synthetic_candidates(repo_root)
    by_identity: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in candidates:
        identity = (row.get("path"), row.get("field"), row.get("rule"), row.get("digest"))
        by_identity.setdefault(identity, []).append(row)
    fixtures_by_identity: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for fixture in payload.get("fixtures", []):
        identity = (
            fixture.get("path"),
            fixture.get("field"),
            fixture.get("rule"),
            fixture.get("digest"),
        )
        fixtures_by_identity.setdefault(identity, []).append(fixture)
    for identity, declared in fixtures_by_identity.items():
        matches = by_identity.get(identity, [])
        if len(matches) != len(declared) or not matches:
            continue
        # Relocate an existing approval only when the immutable detection
        # identity and its cardinality are unchanged. Repeated identical
        # fixtures are paired in source order, which handles line-only shifts
        # without approving new bytes, paths, fields, rules, or digests.
        for fixture, match in zip(
            sorted(declared, key=lambda row: int(row["line"])),
            sorted(matches, key=lambda row: int(row["line"])),
        ):
            fixture["line"] = match["line"]
    payload["candidateTree"] = candidate_source_tree(repo_root)
    declaration.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default=GRAPH_RELATIVE_PATH)
    parser.add_argument("--close", action="store_true")
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="close generated outputs, then run the runtime exact-baseline diff gate",
    )
    parser.add_argument("--baseline-sha", help="runtime-supplied exact baseline SHA")
    parser.add_argument("--baseline-ref", help="runtime-supplied authoritative remote ref")
    parser.add_argument("--bind-push-baseline", action="store_true", help="bind a push predecessor to a named remote target")
    parser.add_argument("--push-branch", help="push event branch name")
    parser.add_argument("--push-before", help="push event predecessor SHA")
    parser.add_argument("--push-after", help="push event candidate SHA")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--generate-fixtures", action="store_true")
    args = parser.parse_args(argv)
    root = Path.cwd().resolve()
    try:
        if args.generate_fixtures:
            return _generate_secret_scan_fixtures(root)
        if args.bind_push_baseline:
            result = bind_push_event_baseline(
                root,
                branch=args.push_branch or "",
                before_sha=args.push_before or "",
                after_sha=args.push_after,
            )
            print(json.dumps({"ok": True, "baselineRef": result}, sort_keys=True))
            return 0
        if args.finalize:
            result = finalize_candidate(
                root,
                baseline_sha=args.baseline_sha,
                baseline_ref=args.baseline_ref,
                graph_path=args.graph,
            )
        elif args.close:
            result = close_generated_outputs(root, graph_path=args.graph)
        else:
            result = verify_generated_outputs(root, graph_path=args.graph)
    except ClosureError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "detail": exc.detail, **exc.diagnostics}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
