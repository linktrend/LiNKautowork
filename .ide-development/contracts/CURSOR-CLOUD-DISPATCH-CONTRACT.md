# Cursor Cloud repository-bound dispatch contract

**Control:** `cursor-cloud-dispatch-v2`

This contract governs the implementation boundary for Cursor Cloud workers. It
does not perform the live routing canary or final Grok/Cursor acceptance proof;
those remain release acceptance work.

## Routing policy

- Gate 0 execution uses GPT-5.6 Luna High through Codex CLI.
- Post-Gate-0 ordinary development defaults to Grok 4.6 Medium through the
  direct Cursor SDK/API path, with Fast explicitly disabled.
- Luna is a fallback only after the Principal instructs the switch. Concurrent
  Luna work requires explicit Principal authorization for disjoint packets.
- This direct Cursor dispatcher rejects every other provider, model, effort, or
  Fast combination before an API key is read or capacity is consumed.

The versioned program-to-repository registry is
`core/managed-core/content/config/routing-registry.json`. Its current
`programs` list is intentionally empty: this packet does not invent repository
identities. Future entries must name every permitted repository, and a shared
entry must explicitly declare cross-repository scope.

## Repository binding and identity

Every direct REST request carries:

```json
{
  "repos": [{"url": "https://github.com/owner/name", "startingRef": "issue/123-slug"}]
}
```

The SDK path carries the equivalent `CloudAgentOptions.repos` list. A named
saved Cursor environment, display name, local checkout, or prompt text is not a
repository selector. The requested URL must match the logical repository
identity, and the request includes the exact 40-character starting commit and
tree in the durable PREPARED intent.

After creation, a mandatory provider readback must prove the exact repository,
ref, worker HEAD commit, and worker HEAD tree. It must also prove provider,
model, medium effort, and `fast=false`. Missing or mismatched fields fail
closed. The run is archived and the intent is marked `REJECTED`; it is never
counted as a worker.

## Durable and equivalent semantics

The intent store is read back before creation. The idempotency key and
client-supplied agent ID bind the complete repository/model/identity request.
Unknown API outcomes receive at most one retry with the same key. The SDK and
REST adapters share the same preflight, readback, archive-on-mismatch, and
durable-commit path, so choosing the SDK does not weaken the evidence contract.

API credentials are injected through `CURSOR_API_KEY`; CLI login is not Cloud
API authority. Credentials never appear in intents, receipts, logs, or
diagnostics.

The first prompt is attestation-only. It prohibits mutation and asks the worker
to report the explicit repository/ref/commit/tree matrix and clean workspace.
This packet supplies local implementation and focused tests only. No real
Cursor endpoint or live agent creation is part of source validation.
