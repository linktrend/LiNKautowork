---
name: model-routing
description: >-
  Select the governed IDE Development execution route. Gate 0 uses Luna High
  through Codex CLI; ordinary post-Gate-0 work uses Grok 4.6 Medium through the
  direct Cursor SDK with explicit repository binding.
version: 2.5.2
status: active
---

# Model routing

Independent narrow review is provider-neutral: use the ordinary routed
reviewer by default, or Principal-authorized Luna when explicitly selected.
Checkpoint acceptance binds the reviewer result to the exact commit/tree and
forbids self-review; it does not require a particular vendor or model.

The versioned route policy is in
`core/managed-core/content/config/routing-registry.json`.

| Route | Provider and model | Execution |
|---|---|---|
| `gate-0` | Codex CLI, GPT-5.6 Luna High, Fast off | Gate 0 only |
| `ordinary-development` | Cursor SDK, Grok 4.6 Medium, Fast off | Default after Gate 0 |
| `luna-fallback` | Codex CLI, GPT-5.6 Luna High, Fast off | Principal-instructed fallback |

Ordinary development dispatches through the direct Cursor SDK/API with an
explicit repository URL and starting ref in `repos[]` (or the SDK's exact
`CloudAgentOptions.repos` equivalent). A named saved Cursor environment is
never a routing input. The provider must read back the repository, ref, exact
40-character commit, and exact 40-character tree before the run is credited.
Any mismatch, missing identity, unsupported model/effort/provider combination,
or Fast mode causes a fail-closed rejection and archive attempt.

Luna is not an automatic Cursor fallback. Use it only when the Principal
instructs a switch. Concurrent Luna execution requires explicit Principal
authorization and disjoint independent packets. The canary for every configured
registry repository is release acceptance work and is not performed by this
skill or by local focused tests.

## Failure handling

Record a failed route and reason in the active packet evidence. Retry at most
once with the declared policy route; a second model-quality failure is surfaced
to the Principal. Infrastructure failures retain the same exact checkpoint and
remain subject to the declared retry bound.
