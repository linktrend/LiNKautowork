#!/usr/bin/env python3
"""Durable executable boundary for one v2.5 heartbeat controller turn.

The command uses JSON files as small compare-and-swap stores and a durable
outbox as its external dispatch boundary.  A scheduler/service may consume the
outbox, but a heartbeat can no longer report quiet success while a safe action
is merely sitting in the manifest.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import tempfile
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.execution.manifest_persistence import (
    MANIFEST_PERSISTENCE_FAILURE,
    ManifestPersistenceError,
    run_heartbeat_controller,
)
from core.execution.protocol import LeaseState
from core.execution.transactional_dispatch import DispatchBudget, TransactionalDispatchError


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _exclusive_controller_lock(path: Path):
    """Serialize a complete read/reconcile/dispatch/persist turn cross-platform."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    acquired = False
    try:
        if sys.platform == "win32":  # pragma: no cover - exercised in Windows matrix
            import msvcrt

            if os.lseek(descriptor, 0, os.SEEK_END) < 1:
                os.write(descriptor, b"\0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        acquired = True
        yield
    finally:
        if acquired:
            try:
                if sys.platform == "win32":  # pragma: no cover
                    import msvcrt

                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(descriptor)


def _read_json(path: Path, *, default: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not path.is_file():
        if default is None:
            raise ManifestPersistenceError(
                MANIFEST_PERSISTENCE_FAILURE, f"durable JSON file is missing: {path}"
            )
        return copy.deepcopy(dict(default))
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ManifestPersistenceError(
            MANIFEST_PERSISTENCE_FAILURE, f"durable JSON root is not an object: {path}"
        )
    return value


class JsonFileManifestStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def read(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        return _read_json(self.path)

    def compare_and_write(
        self,
        expected_revision: int,
        expected_digest: str | None,
        payload: Mapping[str, Any],
    ) -> None:
        current = self.read()
        revision = 0 if current is None else current.get("revision")
        digest = None if current is None else current.get("digest")
        if revision != expected_revision or digest != expected_digest:
            raise ManifestPersistenceError(
                MANIFEST_PERSISTENCE_FAILURE, "manifest file CAS collision"
            )
        _atomic_json(
            self.path,
            {
                "revision": expected_revision + 1,
                "digest": payload["digest"],
                "manifest": copy.deepcopy(payload["manifest"]),
            },
        )


class JsonFileAuthority:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def read_authoritative_state(self, identity: Mapping[str, str]) -> Mapping[str, Any]:
        snapshot = _read_json(self.path)
        if snapshot.get("identity") != dict(identity):
            raise ManifestPersistenceError(
                "authority_identity_mismatch", "authority snapshot identity differs"
            )
        return snapshot


class JsonFileDispatchIntentStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def _records(self) -> dict[str, Any]:
        return _read_json(self.path, default={"records": {}})

    def read_by_key(self, idempotency_key: str) -> dict[str, Any] | None:
        record = self._records().get("records", {}).get(idempotency_key)
        return copy.deepcopy(record) if isinstance(record, Mapping) else None

    def compare_and_write(
        self,
        idempotency_key: str,
        expected_revision: int,
        expected_digest: str | None,
        payload: Mapping[str, Any],
    ) -> None:
        document = self._records()
        records = document.get("records")
        if not isinstance(records, dict):
            raise TransactionalDispatchError("dispatch_store_invalid", "records must be an object")
        current = records.get(idempotency_key)
        revision = 0 if current is None else current.get("revision")
        digest = None if current is None else current.get("digest")
        if revision != expected_revision or digest != expected_digest:
            raise TransactionalDispatchError("cas_collision", "dispatch file CAS collision")
        records[idempotency_key] = {
            "revision": expected_revision + 1,
            "digest": _canonical_digest(payload),
            **copy.deepcopy(dict(payload)),
        }
        _atomic_json(self.path, document)


class JsonOutboxDispatchPort:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def _document(self) -> dict[str, Any]:
        return _read_json(self.path, default={"schemaVersion": 1, "dispatches": []})

    def read_by_idempotency_key(self, idempotency_key: str) -> Mapping[str, Any] | None:
        for row in self._document().get("dispatches", []):
            if isinstance(row, Mapping) and row.get("idempotencyKey") == idempotency_key:
                return copy.deepcopy(dict(row))
        return None

    def dispatch(self, request, idempotency_key: str) -> Mapping[str, Any]:
        document = self._document()
        dispatches = document.get("dispatches")
        if not isinstance(dispatches, list):
            raise TransactionalDispatchError("outbox_invalid", "dispatches must be an array")
        existing = self.read_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing
        dispatch_id = "outbox-" + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:24]
        row = {
            "dispatchId": dispatch_id,
            "idempotencyKey": idempotency_key,
            "statusCode": 201,
            "packetId": request.packet_id,
            "repository": request.repository,
            "commit": request.commit,
            "tree": request.tree,
            "action": request.action,
            "payload": copy.deepcopy(dict(request.payload)),
        }
        dispatches.append(row)
        _atomic_json(self.path, document)
        return row


def run_file_heartbeat(
    *,
    manifest_path: Path | str,
    authority_path: Path | str,
    outbox_path: Path | str,
    lease: LeaseState,
    holder: str,
    now: datetime | None = None,
    remaining_seconds: int = 30,
) -> dict[str, Any]:
    manifest_file = Path(manifest_path)
    with _exclusive_controller_lock(
        manifest_file.with_name(manifest_file.name + ".heartbeat.lock")
    ):
        result = run_heartbeat_controller(
            JsonFileManifestStore(manifest_file),
            JsonFileAuthority(authority_path),
            dispatch_store=JsonFileDispatchIntentStore(
                manifest_file.with_name(manifest_file.name + ".dispatch-intents.json")
            ),
            external_dispatch=JsonOutboxDispatchPort(outbox_path),
            lease=lease,
            holder=holder,
            budget=DispatchBudget(
                remaining_seconds=remaining_seconds,
                required_seconds=5,
            ),
            now=now or datetime.now(timezone.utc),
        )
    if result.get("requiredAction", {}).get("kind") != "DONT_NOTIFY" and not result.get(
        "dispatchPerformed"
    ):
        result = {**result, "quietAllowed": False}
    return result


def _lease(path: Path) -> LeaseState:
    payload = _read_json(path)
    return LeaseState(
        holder=str(payload["holder"]),
        packet_id=str(payload["packetId"]),
        repository=str(payload["repository"]),
        nonce=str(payload["nonce"]),
        expires_at=datetime.fromisoformat(str(payload["expiresAt"])),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--outbox", type=Path, required=True)
    parser.add_argument("--lease", type=Path, required=True)
    parser.add_argument("--holder", required=True)
    parser.add_argument("--remaining-seconds", type=int, default=30)
    args = parser.parse_args(argv)
    result = run_file_heartbeat(
        manifest_path=args.manifest,
        authority_path=args.authority,
        outbox_path=args.outbox,
        lease=_lease(args.lease),
        holder=args.holder,
        remaining_seconds=args.remaining_seconds,
    )
    print(json.dumps(result, sort_keys=True))
    if result.get("dispatchPerformed") or result.get("requiredAction", {}).get("kind") == "DONT_NOTIFY":
        return 0
    return 20


if __name__ == "__main__":
    raise SystemExit(main())
