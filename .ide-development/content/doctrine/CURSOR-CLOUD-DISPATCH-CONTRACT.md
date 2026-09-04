# Cursor Cloud dispatch doctrine

Cursor Cloud is an API authority, not a synonym for an authenticated local
`cursor-agent` CLI. The reusable dispatcher requires `CURSOR_API_KEY`, targets
the exact cloud environment `{type: "cloud", name: "IDE Development 2.5.1"}`
and an exact non-Fast model, and never exposes the key in durable evidence.
The public API body is not treated as a repository checkout selector. The
saved multi-repo environment target is selected and validated as
`/agent/repos/<repo>`; LiNKbrain therefore requires `/agent/repos/LiNKbrain` and
remote `https://github.com/linktrend/LiNKbrain`, never the default LiNKharness
primary repository.

The dispatcher writes and reads back a durable `PREPARED` intent before
`POST /v1/agents`. Its deterministic idempotency key and client-supplied agent
ID suppress duplicate creation. Agent ID, run ID, environment, model, exact
repository path, remote, ref/commit/tree matrix, toolchain, and expected build
ID provenance plus the exact governed setup receipt digest are retained in the
committed record. The first prompt resolves
the target and performs fetch/checkout only under governed setup before
attestation. Build ID is provenance only, never an API selector. An unknown
API outcome gets at most one retry with the same idempotency key.

The initial prompt is attestation-only and explicitly forbids mutation. A
mutation gate requires an exact `PASS`, `noMutation: true`, and exact matches
for environment, repository/ref/commit/tree, and toolchain. Missing or
mismatched attestation fails closed. All tests use fake HTTP; no Cursor agent
is created by package validation.
