#!/usr/bin/env python3
"""Fixture-aware secret scanner for managed Fast/Full.

Scans every tracked regular blob from git index/object identities. Synthetic
fixtures pass only through an exact versioned non-production declaration bound
to path, line/field, digest, optional bytes, candidate content tree, and
scanner policy. Realistic credential formats can never be approved.
Repository-owned scanners stay additive and blocking.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from scripts.gitops.generated_output_closure import ClosureError, candidate_source_tree as closure_candidate_source_tree
except ModuleNotFoundError:  # pragma: no cover - script-style execution
    from generated_output_closure import ClosureError, candidate_source_tree as closure_candidate_source_tree  # type: ignore

SCANNER_POLICY_VERSION = "secret-scan-policy/v1"
POLICY_SHAPE_RE = re.compile(r"^secret-scan-policy/[A-Za-z0-9._-]+$")
SYNTHETIC_PREFIX = "ltfx."
DECLARATION_REL = ".github/linktrend-secret-scan-fixtures.json"
REPO_SCANNERS_REL = ".github/linktrend-repository-secret-scanners.json"
MAX_FILE_BYTES = 1_048_576
REPO_SCANNER_TIMEOUT_SEC = 30.0
EMPTY_TREE = "0" * 40

KIND_CREDENTIAL = "credential_finding"
KIND_APPROVED = "approved_synthetic_fixture"
KIND_STALE = "stale_fixture_declaration"
KIND_SCOPE = "fixture_scope_violation"
BLOCKING_KINDS = frozenset({KIND_CREDENTIAL, KIND_STALE, KIND_SCOPE})

RULE_ASSIGNMENT = "assignment.secret"
RULE_FORMAT_GITHUB = "format.github"
RULE_FORMAT_CLOUD = "format.cloud"
RULE_FORMAT_SK = "format.token"
RULE_FORMAT_DATABASE = "format.database"
RULE_FORMAT_PEM = "format.private_key"
RULE_FORMAT_HIGH_ENTROPY = "format.high_entropy"
RULE_BINDING_TREE = "binding.candidate_tree"
RULE_BINDING_POLICY = "binding.scanner_policy"
RULE_UNKNOWN = "declaration.unknown_rule"
RULE_MALFORMED = "declaration.malformed"
RULE_REPO_SCANNER = "repository_scanner.failure"
RULE_REPO_TIMEOUT = "repository_scanner.timeout"
RULE_REPO_MALFORMED = "repository_scanner.malformed"
RULE_INPUT_UNDECODABLE = "input.undecodable"
RULE_INPUT_TOO_LARGE = "input.too_large"
RULE_GIT_FAILED = "git.failed"

KNOWN_RULES = frozenset(
    {
        RULE_ASSIGNMENT,
        RULE_FORMAT_GITHUB,
        RULE_FORMAT_CLOUD,
        RULE_FORMAT_SK,
        RULE_FORMAT_DATABASE,
        RULE_FORMAT_PEM,
        RULE_FORMAT_HIGH_ENTROPY,
    }
)

CREDENTIAL_FIELDS = (
    "secret",
    "token",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "api-key",
    "private_key",
    "private-key",
    "key",
    "url",
)
ANY_FIELD_RE = re.compile(r"(?i)\b(?P<field>[A-Za-z_][A-Za-z0-9_]*)\b")
FIELD_RE = re.compile(
    r"(?i)\b(?P<field>"
    + "|".join(re.escape(name) for name in CREDENTIAL_FIELDS)
    + r"|[A-Za-z_][A-Za-z0-9_]*(?:secret|token|password|passwd|api[_-]?key|private[_-]?key|apikey)"
    + r")\b"
)
MIN_ASSIGNMENT_LEN = 8
GITHUB_RE = re.compile(r"\b(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|gho_[A-Za-z0-9]{20,})\b")
CLOUD_RE = re.compile(r"\b(AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[0-9A-Za-z\-_]{20,})\b")
TOKEN_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b")
DATABASE_RE = re.compile(
    r"\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?)://[^\s'\"\\]+",
    re.IGNORECASE,
)
PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----")
OID_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ROOT_KEYS = frozenset(
    {"schemaVersion", "kind", "scannerPolicyVersion", "candidateTree", "fixtures"}
)
FIXTURE_REQUIRED = (
    "id",
    "path",
    "line",
    "field",
    "rule",
    "digest",
    "purpose",
    "production",
)
FIXTURE_OPTIONAL = frozenset({"bytes"})
REGULAR_MODES = frozenset({"100644", "100755"})


class SecretScanError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class IndexEntry:
    mode: str
    oid: str
    stage: str
    path: str

    @property
    def is_regular(self) -> bool:
        return self.mode in REGULAR_MODES


def digest_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _git(root: Path, *args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        input=input_text,
    )
    if result.returncode:
        raise SecretScanError("git_failed", (result.stderr or result.stdout).strip())
    return result.stdout


def _git_bytes(root: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        check=False,
        input=input_bytes,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise SecretScanError("git_failed", detail)
    return result.stdout


def tracked_entries(root: Path) -> list[IndexEntry]:
    """Index identities from `git ls-files -s`. Does not follow symlinks/gitlinks."""
    raw = _git_bytes(root, "ls-files", "-s", "-z", "--")
    entries: list[IndexEntry] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            meta, path_b = item.split(b"\t", 1)
            mode_b, oid_b, stage_b = meta.split(b" ", 2)
        except ValueError as exc:
            raise SecretScanError("git_failed", "ls-files parse") from exc
        path = path_b.decode("utf-8").replace("\\", "/")
        oid = oid_b.decode("ascii")
        if not OID_RE.fullmatch(oid):
            raise SecretScanError("git_failed", f"invalid oid {oid}")
        entries.append(
            IndexEntry(
                mode=mode_b.decode("ascii"),
                oid=oid,
                stage=stage_b.decode("ascii"),
                path=path,
            )
        )
    return entries


def tracked_files(root: Path) -> list[str]:
    return [entry.path for entry in tracked_entries(root)]


def candidate_content_tree(root: Path) -> str:
    """40-hex identity excluding every declaratively generated output."""
    graph_paths = (
        root / "core/managed-core/config/generated-output-closure.json",
        root / ".ide-development/config/generated-output-closure.json",
    )
    if any(path.is_file() for path in graph_paths):
        try:
            return closure_candidate_source_tree(root)
        except ClosureError as exc:
            raise SecretScanError("generated_output_graph_invalid", str(exc)) from exc
    return closure_candidate_source_tree(root, graph_path=None)


def _shannon(value: str) -> float:
    counts: dict[str, int] = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    length = len(value)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


def _is_reference_value(value: str) -> bool:
    stripped = value.strip()
    if not stripped or stripped == SYNTHETIC_PREFIX:
        return True
    if stripped.startswith(("(", "[", "{")):
        return True
    if stripped.startswith("${") or stripped.startswith("$("):
        return True
    if re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", stripped):
        return True
    if re.search(r"[A-Za-z_][A-Za-z0-9_]*\(", stripped):
        return True
    if re.match(r"(?i)(?:https?|git|ssh|file)://", stripped) and not DATABASE_RE.search(stripped):
        return True
    if stripped.startswith(("f\"", "f'", 'rf"', "fr\"", "F\"", "F'")):
        return True
    if stripped.startswith("`") or stripped.endswith("`"):
        return True
    if ".md`" in stripped or (".md" in stripped and "/" in stripped):
        return True
    if len(stripped.split()) >= 4:
        return True
    return False


def is_realistic_value(value: str) -> bool:
    if GITHUB_RE.search(value) or CLOUD_RE.search(value) or TOKEN_RE.search(value):
        return True
    if DATABASE_RE.search(value) or PRIVATE_KEY_RE.search(value):
        return True
    if _is_reference_value(value):
        return False
    compact = re.sub(r"\s+", "", value)
    if len(compact) >= 40 and _shannon(compact) >= 3.5 and not compact.startswith(SYNTHETIC_PREFIX):
        return True
    return False


def is_synthetic_value(value: str) -> bool:
    return (
        value.startswith(SYNTHETIC_PREFIX)
        and len(value) > len(SYNTHETIC_PREFIX)
        and not is_realistic_value(value)
    )


def _rule_for_value(value: str, *, assigned: bool) -> str:
    if GITHUB_RE.search(value):
        return RULE_FORMAT_GITHUB
    if CLOUD_RE.search(value):
        return RULE_FORMAT_CLOUD
    if TOKEN_RE.search(value):
        return RULE_FORMAT_SK
    if DATABASE_RE.search(value):
        return RULE_FORMAT_DATABASE
    if PRIVATE_KEY_RE.search(value):
        return RULE_FORMAT_PEM
    if len(value) >= 40 and _shannon(value) >= 3.5 and not value.startswith(SYNTHETIC_PREFIX):
        return RULE_FORMAT_HIGH_ENTROPY
    return RULE_ASSIGNMENT if assigned else RULE_FORMAT_HIGH_ENTROPY


def _add_detection(
    detections: list[dict[str, Any]],
    *,
    path: str,
    line: int,
    field: str,
    rule: str,
    value: str,
) -> None:
    key = (path, line, field, rule, value)
    if any((row["path"], row["line"], row["field"], row["rule"], row["value"]) == key for row in detections):
        return
    detections.append(
        {
            "path": path,
            "line": line,
            "field": field,
            "rule": rule,
            "value": value,
            "digest": digest_bytes(value.encode("utf-8")),
            "realistic": is_realistic_value(value),
        }
    )


def _skip_ws(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t":
        index += 1
    return index


def _read_quoted(text: str, index: int) -> tuple[str, int] | None:
    if index >= len(text) or text[index] not in {"'", '"'}:
        return None
    quote = text[index]
    index += 1
    chars: list[str] = []
    while index < len(text) and text[index] != "\n":
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            nxt = text[index + 1]
            mapped = {"\\": "\\", '"': '"', "'": "'", "n": "\n", "r": "\r", "t": "\t", "0": "\0"}
            chars.append(mapped.get(nxt, nxt))
            index += 2
            continue
        if char == quote:
            return "".join(chars), index + 1
        chars.append(char)
        index += 1
    return None


def _read_concat_quoted(text: str, index: int) -> tuple[str, int] | None:
    first = _read_quoted(text, index)
    if first is None:
        return None
    value, index = first
    while True:
        cursor = _skip_ws(text, index)
        if cursor < len(text) and text[cursor] == "+":
            cursor = _skip_ws(text, cursor + 1)
            nxt = _read_quoted(text, cursor)
            if nxt is None:
                break
            piece, index = nxt
            value += piece
            continue
        if cursor < len(text) and text[cursor] in {"'", '"'}:
            nxt = _read_quoted(text, cursor)
            if nxt is None:
                break
            piece, index = nxt
            value += piece
            continue
        break
    return value, index


def _read_unquoted(text: str, index: int) -> tuple[str, int]:
    cursor = index
    while cursor < len(text) and text[cursor] not in " \t\n,#;}]":
        cursor += 1
    return text[index:cursor], cursor


def _is_credential_field(name: str) -> bool:
    return FIELD_RE.fullmatch(name) is not None


def _is_code_expression(value: str) -> bool:
    stripped = value.strip()
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", stripped):
        return True
    if re.search(r"[\[\]+]|::", stripped):
        return True
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", stripped) and "." in stripped:
        return True
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*(?:\([^)]*\)|\))+", stripped):
        return True
    return False


def extract_assignments(line: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for match in ANY_FIELD_RE.finditer(line):
        raw_field = match.group("field")
        field = raw_field.lower().replace("-", "_")
        index = _skip_ws(line, match.end())
        if index < len(line) and line[index] in {"'", '"'}:
            index = _skip_ws(line, index + 1)
        if index >= len(line) or line[index] not in ":=":
            continue
        index = _skip_ws(line, index + 1)
        if index >= len(line):
            continue
        quoted = line[index] in {"'", '"'}
        if quoted:
            read = _read_concat_quoted(line, index)
            if read is None:
                continue
            value, _ = read
        else:
            value, _ = _read_unquoted(line, index)
            if not value:
                continue
        if not _is_credential_field(raw_field) and not is_synthetic_value(value):
            continue
        if _is_reference_value(value) and not is_realistic_value(value) and not is_synthetic_value(value):
            continue
        if (
            not quoted
            and _is_code_expression(value)
            and not is_realistic_value(value)
            and not is_synthetic_value(value)
        ):
            continue
        found.append((field, value))
    return found


def scan_text(path: str, text: str) -> list[dict[str, Any]]:
    detections: list[dict[str, Any]] = []
    for index, raw_line in enumerate(text.splitlines(), start=1):
        for field, value in extract_assignments(raw_line):
            if len(value) < MIN_ASSIGNMENT_LEN and not value.startswith(SYNTHETIC_PREFIX):
                continue
            _add_detection(
                detections,
                path=path,
                line=index,
                field=field,
                rule=_rule_for_value(value, assigned=True),
                value=value,
            )
        for match in GITHUB_RE.finditer(raw_line):
            _add_detection(
                detections,
                path=path,
                line=index,
                field="token",
                rule=RULE_FORMAT_GITHUB,
                value=match.group(0),
            )
        for match in CLOUD_RE.finditer(raw_line):
            _add_detection(
                detections,
                path=path,
                line=index,
                field="key",
                rule=RULE_FORMAT_CLOUD,
                value=match.group(0),
            )
        for match in TOKEN_RE.finditer(raw_line):
            _add_detection(
                detections,
                path=path,
                line=index,
                field="token",
                rule=RULE_FORMAT_SK,
                value=match.group(0),
            )
        for match in DATABASE_RE.finditer(raw_line):
            _add_detection(
                detections,
                path=path,
                line=index,
                field="url",
                rule=RULE_FORMAT_DATABASE,
                value=match.group(0),
            )
        if PRIVATE_KEY_RE.search(raw_line):
            _add_detection(
                detections,
                path=path,
                line=index,
                field="private_key",
                rule=RULE_FORMAT_PEM,
                value=raw_line.strip(),
            )
    return detections


def _nul_ratio(raw: bytes, offset: int) -> float:
    if len(raw) < 2:
        return 0.0
    pairs = (len(raw) - offset) // 2
    if pairs <= 0:
        return 0.0
    nuls = sum(1 for index in range(offset, len(raw), 2) if raw[index] == 0)
    return nuls / pairs


def decode_tracked_text(raw: bytes) -> tuple[str | None, str]:
    """Decode UTF-8 / UTF-16 / UTF-16LE / UTF-16BE. Never uses errors=ignore."""
    if raw.startswith(b"\xff\xfe"):
        try:
            return raw.decode("utf-16-le"), "utf-16-le"
        except UnicodeDecodeError:
            return None, "undecodable"
    if raw.startswith(b"\xfe\xff"):
        try:
            return raw.decode("utf-16-be"), "utf-16-be"
        except UnicodeDecodeError:
            return None, "undecodable"
    if raw.startswith(b"\xef\xbb\xbf"):
        try:
            return raw.decode("utf-8-sig"), "utf-8"
        except UnicodeDecodeError:
            return None, "undecodable"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    else:
        if "\x00" not in text:
            return text, "utf-8"
    if len(raw) >= 4 and len(raw) % 2 == 0:
        if _nul_ratio(raw, 1) >= 0.25:
            try:
                return raw.decode("utf-16-le"), "utf-16-le"
            except UnicodeDecodeError:
                return None, "undecodable"
        if _nul_ratio(raw, 0) >= 0.25:
            try:
                return raw.decode("utf-16-be"), "utf-16-be"
            except UnicodeDecodeError:
                return None, "undecodable"
    if b"\x00" in raw:
        return None, "undecodable"
    return raw.decode("latin-1"), "latin-1"


def _valid_relpath(path: str) -> bool:
    if not path or path.startswith("/") or "\\" in path or "\x00" in path:
        return False
    parts = path.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def _load_json_bytes(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SecretScanError("declaration_malformed", str(exc)) from exc


def _validate_declaration(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SecretScanError("declaration_malformed", "root must be an object")
    extra = set(payload) - ROOT_KEYS
    if extra:
        raise SecretScanError("declaration_malformed", f"extra {sorted(extra)}")
    missing = ROOT_KEYS - set(payload)
    if missing:
        raise SecretScanError("declaration_malformed", f"missing {sorted(missing)}")
    if payload.get("schemaVersion") != 1 or payload.get("kind") != "secret-scan-fixtures":
        raise SecretScanError("declaration_malformed", "schema or kind")
    if not isinstance(payload.get("scannerPolicyVersion"), str) or not POLICY_SHAPE_RE.fullmatch(
        payload["scannerPolicyVersion"]
    ):
        raise SecretScanError("declaration_malformed", "scannerPolicyVersion")
    if not isinstance(payload.get("candidateTree"), str) or not OID_RE.fullmatch(payload["candidateTree"]):
        raise SecretScanError("declaration_malformed", "candidateTree")
    fixtures = payload.get("fixtures")
    if not isinstance(fixtures, list):
        raise SecretScanError("declaration_malformed", "fixtures")
    seen_ids: set[str] = set()
    for row in fixtures:
        if not isinstance(row, dict):
            raise SecretScanError("declaration_malformed", "fixture")
        extra_row = set(row) - set(FIXTURE_REQUIRED) - FIXTURE_OPTIONAL
        if extra_row:
            raise SecretScanError("declaration_malformed", f"extra {sorted(extra_row)}")
        for key in FIXTURE_REQUIRED:
            if key not in row:
                raise SecretScanError("declaration_malformed", f"fixture.{key}")
        if row.get("production") is not False:
            raise SecretScanError("declaration_malformed", "production must be false")
        if not isinstance(row.get("purpose"), str) or not row["purpose"].strip():
            raise SecretScanError("declaration_malformed", "purpose")
        if not isinstance(row.get("id"), str) or not row["id"].strip():
            raise SecretScanError("declaration_malformed", "id")
        fixture_id = row["id"]
        if fixture_id in seen_ids:
            raise SecretScanError("declaration_malformed", "duplicate id")
        seen_ids.add(fixture_id)
        if not isinstance(row.get("field"), str) or not row["field"].strip():
            raise SecretScanError("declaration_malformed", "field")
        if not isinstance(row.get("rule"), str) or not row["rule"].strip():
            raise SecretScanError("declaration_malformed", "rule")
        if not isinstance(row.get("path"), str) or not _valid_relpath(row["path"]):
            raise SecretScanError("declaration_malformed", "path")
        if not isinstance(row.get("digest"), str) or not DIGEST_RE.fullmatch(row["digest"]):
            raise SecretScanError("declaration_malformed", "digest")
        if not isinstance(row.get("line"), int) or isinstance(row.get("line"), bool) or row["line"] < 1:
            raise SecretScanError("declaration_malformed", "line")
        if "bytes" in row and (not isinstance(row["bytes"], str) or not row["bytes"]):
            raise SecretScanError("declaration_malformed", "bytes")
    return payload


def _finding(
    *,
    kind: str,
    path: str,
    line: int | None,
    field: str | None,
    rule: str,
    digest: str | None,
    fixture_id: str | None = None,
    scanner_id: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"kind": kind, "path": path, "rule": rule}
    if line is not None:
        row["line"] = line
    if field is not None:
        row["field"] = field
    if digest is not None:
        row["digest"] = digest
    if fixture_id is not None:
        row["fixtureId"] = fixture_id
    if scanner_id is not None:
        row["scannerId"] = scanner_id
    if detail is not None:
        row["detail"] = detail
    return row


def _error_result(exc: SecretScanError, content_tree: str = EMPTY_TREE) -> dict[str, Any]:
    rule = {
        "git_failed": RULE_GIT_FAILED,
        "declaration_malformed": RULE_MALFORMED,
        "repository_scanners_malformed": RULE_REPO_MALFORMED,
    }.get(exc.code, exc.code.replace("_", "."))
    path = DECLARATION_REL if exc.code == "declaration_malformed" else (
        REPO_SCANNERS_REL if exc.code == "repository_scanners_malformed" else "."
    )
    return make_result(
        content_tree=content_tree,
        findings=[
            _finding(
                kind=KIND_CREDENTIAL,
                path=path,
                line=None,
                field=None,
                rule=rule,
                digest=None,
                detail=exc.detail or exc.code,
            )
        ],
    )


def make_result(*, content_tree: str, findings: list[dict[str, Any]]) -> dict[str, Any]:
    ok = not any(row["kind"] in BLOCKING_KINDS for row in findings)
    return {
        "schemaVersion": 1,
        "kind": "secret-scan-result",
        "scannerPolicyVersion": SCANNER_POLICY_VERSION,
        "candidateTree": content_tree if OID_RE.fullmatch(content_tree) else EMPTY_TREE,
        "ok": ok,
        "findings": findings,
    }


def _evaluate_declarations(
    detections: list[dict[str, Any]],
    declaration: dict[str, Any] | None,
    content_tree: str,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    fixtures = list((declaration or {}).get("fixtures") or [])
    bindings_valid = True
    if declaration is not None:
        if declaration.get("scannerPolicyVersion") != SCANNER_POLICY_VERSION:
            bindings_valid = False
            findings.append(
                _finding(
                    kind=KIND_STALE,
                    path=DECLARATION_REL,
                    line=None,
                    field=None,
                    rule=RULE_BINDING_POLICY,
                    digest=None,
                    detail="scannerPolicyVersion",
                )
            )
        if declaration.get("candidateTree") != content_tree:
            bindings_valid = False
            findings.append(
                _finding(
                    kind=KIND_STALE,
                    path=DECLARATION_REL,
                    line=None,
                    field=None,
                    rule=RULE_BINDING_TREE,
                    digest=None,
                    detail="candidateTree",
                )
            )
        for row in fixtures:
            if row["rule"] not in KNOWN_RULES:
                bindings_valid = False
                findings.append(
                    _finding(
                        kind=KIND_SCOPE,
                        path=str(row["path"]),
                        line=int(row["line"]),
                        field=str(row["field"]),
                        rule=RULE_UNKNOWN,
                        digest=str(row["digest"]),
                        fixture_id=str(row["id"]),
                    )
                )

    used: set[str] = set()
    for detection in detections:
        if (
            detection["path"] == DECLARATION_REL
            and is_synthetic_value(detection["value"])
            and not detection["realistic"]
        ):
            continue
        match = None
        if bindings_valid and detection["path"] != DECLARATION_REL:
            for row in fixtures:
                declared_bytes = row.get("bytes")
                bytes_ok = declared_bytes is None or declared_bytes == detection["value"]
                if (
                    bytes_ok
                    and row["path"] == detection["path"]
                    and int(row["line"]) == detection["line"]
                    and str(row["field"]) == detection["field"]
                    and str(row["rule"]) == detection["rule"]
                    and str(row["digest"]) == detection["digest"]
                ):
                    match = row
                    break
        if (
            match is not None
            and detection["path"] != DECLARATION_REL
            and not detection["realistic"]
            and is_synthetic_value(detection["value"])
        ):
            used.add(str(match["id"]))
            findings.append(
                _finding(
                    kind=KIND_APPROVED,
                    path=detection["path"],
                    line=detection["line"],
                    field=detection["field"],
                    rule=detection["rule"],
                    digest=detection["digest"],
                    fixture_id=str(match["id"]),
                )
            )
            continue
        kind = KIND_CREDENTIAL
        fixture_id = None
        if detection["path"] == DECLARATION_REL:
            kind = KIND_CREDENTIAL
        elif detection["realistic"]:
            kind = KIND_CREDENTIAL
            if match is not None:
                fixture_id = str(match["id"])
        elif match is not None and not is_synthetic_value(detection["value"]):
            kind = KIND_CREDENTIAL
            fixture_id = str(match["id"])
        elif declaration is not None and not bindings_valid:
            kind = KIND_STALE
        else:
            near = [
                row
                for row in fixtures
                if row["path"] == detection["path"] or str(row["digest"]) == detection["digest"]
            ]
            if near:
                kind = KIND_STALE if any(str(row["digest"]) != detection["digest"] for row in near) else KIND_SCOPE
                fixture_id = str(near[0]["id"])
        findings.append(
            _finding(
                kind=kind,
                path=detection["path"],
                line=detection["line"],
                field=detection["field"],
                rule=detection["rule"],
                digest=detection["digest"],
                fixture_id=fixture_id,
            )
        )

    if bindings_valid:
        for row in fixtures:
            if str(row["id"]) in used:
                continue
            findings.append(
                _finding(
                    kind=KIND_STALE,
                    path=str(row["path"]),
                    line=int(row["line"]),
                    field=str(row["field"]),
                    rule=str(row["rule"]),
                    digest=str(row["digest"]),
                    fixture_id=str(row["id"]),
                    detail="unused_or_stale_declaration",
                )
            )
    return findings


def _blob_types_and_sizes(root: Path, oids: list[str]) -> dict[str, tuple[str, int]]:
    if not oids:
        return {}
    payload = "".join(f"{oid}\n" for oid in oids)
    text = _git(root, "cat-file", "--batch-check", input_text=payload)
    info: dict[str, tuple[str, int]] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            raise SecretScanError("git_failed", f"cat-file check {line}")
        oid = parts[0]
        if parts[1] == "missing":
            raise SecretScanError("git_failed", f"missing {oid}")
        if len(parts) < 3:
            raise SecretScanError("git_failed", f"cat-file check {line}")
        info[oid] = (parts[1], int(parts[2]))
    return info


def _read_blobs(root: Path, oids: list[str]) -> dict[str, bytes]:
    if not oids:
        return {}
    payload = "".join(f"{oid}\n" for oid in oids).encode("ascii")
    raw = _git_bytes(root, "cat-file", "--batch", input_bytes=payload)
    out: dict[str, bytes] = {}
    cursor = 0
    while cursor < len(raw):
        newline = raw.find(b"\n", cursor)
        if newline < 0:
            break
        header = raw[cursor:newline].decode("ascii")
        parts = header.split()
        if len(parts) < 2:
            raise SecretScanError("git_failed", f"cat-file batch {header}")
        if parts[1] == "missing":
            raise SecretScanError("git_failed", f"missing {parts[0]}")
        if len(parts) < 3:
            raise SecretScanError("git_failed", f"cat-file batch {header}")
        oid, _kind, size_s = parts[0], parts[1], parts[2]
        size = int(size_s)
        start = newline + 1
        out[oid] = raw[start : start + size]
        cursor = start + size
        if cursor < len(raw) and raw[cursor : cursor + 1] == b"\n":
            cursor += 1
    return out


def _scan_declaration_values(payload: Any, detections: list[dict[str, Any]]) -> None:
    if not isinstance(payload, dict) or not isinstance(payload.get("fixtures"), list):
        return
    for row in payload["fixtures"]:
        if not isinstance(row, dict):
            continue
        for key in ("bytes", "purpose", "id"):
            value = row.get(key)
            if isinstance(value, str) and value:
                detections.extend(scan_text(DECLARATION_REL, f'{key}="{value}"'))


def _run_repository_scanners(root: Path) -> list[dict[str, Any]]:
    path = root / REPO_SCANNERS_REL
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SecretScanError("repository_scanners_malformed", str(exc)) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("scanners"), list):
        raise SecretScanError("repository_scanners_malformed", REPO_SCANNERS_REL)
    findings: list[dict[str, Any]] = []
    for row in payload["scanners"]:
        if not isinstance(row, dict) or not row.get("id") or not isinstance(row.get("command"), list):
            raise SecretScanError("repository_scanners_malformed", "scanner")
        command = [str(part) for part in row["command"]]
        if not command:
            raise SecretScanError("repository_scanners_malformed", "empty command")
        try:
            result = subprocess.run(
                command,
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
                timeout=REPO_SCANNER_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired:
            findings.append(
                _finding(
                    kind=KIND_CREDENTIAL,
                    path=REPO_SCANNERS_REL,
                    line=None,
                    field=None,
                    rule=RULE_REPO_TIMEOUT,
                    digest=None,
                    scanner_id=str(row["id"]),
                    detail=f"timeout={REPO_SCANNER_TIMEOUT_SEC}",
                )
            )
            continue
        if result.returncode != 0:
            findings.append(
                _finding(
                    kind=KIND_CREDENTIAL,
                    path=REPO_SCANNERS_REL,
                    line=None,
                    field=None,
                    rule=RULE_REPO_SCANNER,
                    digest=None,
                    scanner_id=str(row["id"]),
                    detail=f"exit={result.returncode}",
                )
            )
    return findings


def _scan_regular_blobs(
    root: Path,
    entries: list[IndexEntry],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    detections: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    regular = [entry for entry in entries if entry.is_regular]
    sizes = _blob_types_and_sizes(root, [entry.oid for entry in regular])
    readable: list[IndexEntry] = []
    for entry in regular:
        info = sizes.get(entry.oid)
        if info is None:
            findings.append(
                _finding(
                    kind=KIND_CREDENTIAL,
                    path=entry.path,
                    line=None,
                    field=None,
                    rule=RULE_GIT_FAILED,
                    digest=None,
                    detail="missing blob",
                )
            )
            continue
        _kind, size = info
        if _kind != "blob":
            continue
        if size > MAX_FILE_BYTES:
            findings.append(
                _finding(
                    kind=KIND_CREDENTIAL,
                    path=entry.path,
                    line=None,
                    field=None,
                    rule=RULE_INPUT_TOO_LARGE,
                    digest=None,
                    detail=f"size={size}:max={MAX_FILE_BYTES}",
                )
            )
            continue
        readable.append(entry)
    blobs = _read_blobs(root, [entry.oid for entry in readable])
    for entry in readable:
        raw = blobs.get(entry.oid)
        if raw is None:
            findings.append(
                _finding(
                    kind=KIND_CREDENTIAL,
                    path=entry.path,
                    line=None,
                    field=None,
                    rule=RULE_GIT_FAILED,
                    digest=None,
                    detail="unread blob",
                )
            )
            continue
        text, encoding = decode_tracked_text(raw)
        if text is None:
            findings.append(
                _finding(
                    kind=KIND_CREDENTIAL,
                    path=entry.path,
                    line=None,
                    field=None,
                    rule=RULE_INPUT_UNDECODABLE,
                    digest=None,
                    detail=encoding,
                )
            )
            continue
        detections.extend(scan_text(entry.path, text))
    return detections, findings


def _scan_repository(root: Path) -> dict[str, Any]:
    entries = tracked_entries(root)
    content_tree = candidate_content_tree(root)
    detections, findings = _scan_regular_blobs(root, entries)
    declaration = None
    decl_entry = next((entry for entry in entries if entry.path == DECLARATION_REL), None)
    if decl_entry is not None and decl_entry.is_regular:
        decl_blobs = _read_blobs(root, [decl_entry.oid])
        raw = decl_blobs.get(decl_entry.oid, b"")
        try:
            payload = _load_json_bytes(raw)
            _scan_declaration_values(payload, detections)
            declaration = _validate_declaration(payload)
        except SecretScanError as exc:
            findings.extend(_error_result(exc, content_tree)["findings"])
            declaration = None
    findings.extend(_evaluate_declarations(detections, declaration, content_tree))
    findings.extend(_run_repository_scanners(root))
    return make_result(content_tree=content_tree, findings=findings)


def scan_repository(root: Path) -> dict[str, Any]:
    root = root.resolve()
    try:
        return _scan_repository(root)
    except SecretScanError as exc:
        return _error_result(exc)


def identify_synthetic_candidates(root: Path) -> list[dict[str, Any]]:
    """Identify likely synthetic fixtures. Never writes an approval."""
    root = root.resolve()
    candidates: list[dict[str, Any]] = []
    try:
        entries = tracked_entries(root)
        detections, _findings = _scan_regular_blobs(root, entries)
    except SecretScanError:
        return []
    for detection in detections:
        if detection["path"] == DECLARATION_REL or detection["realistic"]:
            continue
        if is_synthetic_value(detection["value"]) or detection["rule"] == RULE_ASSIGNMENT:
            candidates.append(
                {
                    "path": detection["path"],
                    "line": detection["line"],
                    "field": detection["field"],
                    "rule": detection["rule"],
                    "digest": detection["digest"],
                }
            )
    return candidates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--json-output")
    args = parser.parse_args(argv)
    result = scan_repository(Path(args.repo))
    text = json.dumps(result, indent=2) + "\n"
    if args.json_output:
        Path(args.json_output).write_text(text, encoding="utf-8")
    print(text, end="")
    if result["ok"]:
        return 0
    if any(row["rule"] in {RULE_GIT_FAILED, RULE_MALFORMED, RULE_REPO_MALFORMED} for row in result["findings"]):
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
