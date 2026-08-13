# Autowork Provider Contract v1

`2026-08-13.v1` defines compact, exact-version provider metadata and reference-only request, receipt, event, callback, notification, cursor, and capability-status contracts.  It is source-contract evidence only; all stage, external-effect, consumer E2E, and production evidence remains HOLD.

The catalogue is metadata-first. A caller selects an exact automation ID and version; Autowork never chooses an automation for it. Requests bind Platform-derived identity facts, exact automation/configuration digests, opaque correlations, an expiry, cancellation facts, idempotency, and bounded input/artifact/result references. A governed external-assistance request additionally requires an exact opaque Brain handoff reference. Missing activation support is `unavailable` or `hold`, never evidence of dispatch.

Receipts are immutable, compact provider outcomes. They cannot prove or mutate a consumer decision, ledger, gate, approval, deployment, publication, legal/trading/campaign authority, E2E outcome, or production readiness. A same idempotency key must be compared with the canonical request fingerprint by later persistence/route packets; different canonical content must fail closed.

MCP is not added because AW-00 found no Autowork MCP surface. OKF v0.2 is deferred/not applicable pending a repository-owned knowledge-artifact mapping. This contract holds only immutable references and redacted metadata; raw payloads, credentials, prompts, logs, private health information, personal/case binary or text, source repositories, and consumer ledgers are prohibited.
