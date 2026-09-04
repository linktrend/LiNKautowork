#!/usr/bin/env python3
"""Narrow local validation for the PKT-03/XPKT-03 planning-only HOLD handoff.

Does not run Full suites, hosted CI, or mutate managed IDE files.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "docs/planning/pkt-03-xpkt-03/CONSUMER-HANDOFF-SPEC.md"
HANDOFF = ROOT / "docs/planning/pkt-03-xpkt-03/provider-consumer-handoff.hold.json"
SCHEMA = ROOT / ".ide-development/schemas/provider-consumer-handoff.schema.json"
LOCK = ROOT / ".cursor/skills-lock.json"
INSTALLED = ROOT / ".ide-development/installed-state.json"

SHA40 = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
REPO = re.compile(r"^[^/\s]+/[^/\s]+$")

CONSUMER = {
    "repository": "linktrend/LiNKautowork",
    "commit": "f75656930eb4d82827e480f00a435069c501503e",
    "tree": "013f609cc432e7194388b6ffd09e32f71ac6e672",
}
PRODUCER = {
    "repository": "linktrend/LiNKskills",
    "commit": "4324d41fe6a7a6883075e9baa9a5a7f71dd13b3d",
    "tree": "7c5a36f8773ebe9bac417d42a8a48a286fe5968d",
}

MANAGED_PREFIXES = (
    ".ide-development/",
    ".cursor/skills-lock.json",
    ".agents/skills-lock.json",
    "core/managed-core/",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def fail(message: str) -> None:
    print(f"HOLD-VALIDATION FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_identity(value: object, expected: dict[str, str], label: str) -> None:
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
    for key in ("repository", "commit", "tree"):
        if value.get(key) != expected[key]:
            fail(f"{label}.{key} expected {expected[key]!r}, got {value.get(key)!r}")
        if key == "repository" and not REPO.match(str(value[key])):
            fail(f"{label}.repository malformed")
        if key in {"commit", "tree"} and not SHA40.match(str(value[key])):
            fail(f"{label}.{key} must be a 40-character lowercase SHA")


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def main() -> None:
    for path in (SPEC, HANDOFF, SCHEMA, LOCK, INSTALLED):
        if not path.is_file():
            fail(f"missing {path.relative_to(ROOT)}")

    installed = json.loads(INSTALLED.read_text(encoding="utf-8"))
    if installed.get("packageVersion") != "2.5.2":
        fail(f"installed packageVersion must remain 2.5.2, got {installed.get('packageVersion')!r}")

    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    proof = lock.get("dualAppProof") if isinstance(lock.get("dualAppProof"), dict) else {}
    if lock.get("packet") != "PKT-03":
        fail("consumer skills-lock packet must remain PKT-03")
    if proof.get("codex") != "HOLD" or proof.get("cursor") != "HOLD":
        fail("dualAppProof must remain HOLD/HOLD on this planning packet")
    if lock.get("physicalRemovalAuthorized") is not False:
        fail("physicalRemovalAuthorized must remain false")

    handoff = json.loads(HANDOFF.read_text(encoding="utf-8"))
    if handoff.get("schemaVersion") != 1 or handoff.get("kind") != "provider-consumer-handoff":
        fail("handoff schemaVersion/kind invalid")
    extra = set(handoff) - {
        "schemaVersion",
        "kind",
        "producer",
        "provider",
        "consumer",
        "artifactDigest",
        "contractDigest",
        "verdict",
        "lifecycleState",
        "acceptedReceipt",
        "blocker",
        "independentPreparationAllowed",
        "integrationClaimed",
    }
    if extra:
        fail(f"handoff additional properties: {sorted(extra)}")

    if handoff.get("verdict") != "blocked" or handoff.get("lifecycleState") != "blocked":
        fail("planning packet must remain verdict=blocked lifecycleState=blocked")
    if handoff.get("independentPreparationAllowed") is not True:
        fail("independentPreparationAllowed must be true")
    if handoff.get("integrationClaimed") is not False:
        fail("integrationClaimed must be false")
    if handoff.get("acceptedReceipt") is not None:
        fail("acceptedReceipt must be null on HOLD")

    require_identity(handoff.get("producer"), PRODUCER, "producer")
    require_identity(handoff.get("provider"), PRODUCER, "provider")
    require_identity(handoff.get("consumer"), CONSUMER, "consumer")

    contract_digest = sha256_file(SCHEMA)
    artifact_digest = sha256_file(SPEC)
    if handoff.get("contractDigest") != contract_digest:
        fail(f"contractDigest mismatch: expected {contract_digest}")
    if handoff.get("artifactDigest") != artifact_digest:
        fail(f"artifactDigest mismatch: expected {artifact_digest}")
    if not DIGEST.match(str(handoff.get("contractDigest"))) or not DIGEST.match(str(handoff.get("artifactDigest"))):
        fail("digests must use sha256:<64 hex>")

    blocker = handoff.get("blocker")
    if not isinstance(blocker, dict):
        fail("blocker required")
    if blocker.get("blockingRepository") != "linktrend/LiNKskills":
        fail("blocker.blockingRepository must be linktrend/LiNKskills")
    if blocker.get("handoffClass") != "provider-consumer":
        fail("blocker.handoffClass must be provider-consumer")
    if not isinstance(blocker.get("owner"), str) or not blocker.get("owner"):
        fail("blocker.owner required")
    if not isinstance(blocker.get("nextAction"), str) or "HOLD" not in str(blocker.get("nextAction")):
        fail("blocker.nextAction must state HOLD")

    head = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    ancestor = subprocess.run(
        ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", CONSUMER["commit"], "HEAD"],
        check=False,
    )
    if ancestor.returncode != 0:
        fail("candidate HEAD must contain consumer baseline commit")
    dirty = git("status", "--porcelain")
    for line in dirty.splitlines():
        path = line[3:].strip()
        if path.startswith(MANAGED_PREFIXES) or path in MANAGED_PREFIXES:
            fail(f"managed path is dirty: {path}")

    print("HOLD-VALIDATION PASS")
    print(f"consumer.repository={CONSUMER['repository']}")
    print(f"consumer.ref=development")
    print(f"consumer.baselineCommit={CONSUMER['commit']}")
    print(f"consumer.baselineTree={CONSUMER['tree']}")
    print(f"candidate.head={head}")
    print(f"candidate.tree={tree}")
    print(f"producer.repository={PRODUCER['repository']}")
    print(f"producer.commit={PRODUCER['commit']}")
    print(f"producer.tree={PRODUCER['tree']}")
    print(f"verdict=blocked")
    print(f"lifecycleState=blocked")
    print(f"integrationClaimed=false")
    print(f"dualAppProof.codex=HOLD")
    print(f"dualAppProof.cursor=HOLD")
    print(f"ide.packageVersion=2.5.2")
    print(f"artifactDigest={artifact_digest}")
    print(f"contractDigest={contract_digest}")
    print("decision=HOLD")


if __name__ == "__main__":
    main()
