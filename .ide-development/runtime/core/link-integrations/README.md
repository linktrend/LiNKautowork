# IDE Development five-provider consumer (pre-rollout source)

This directory is the **fail-closed consumer boundary** for exactly five
providers: LiNKplatform, LiNKlibraries, LiNKbrain, LiNKskills, and LiNKautowork.

| Module | Role |
|---|---|
| `pins.mjs` / `errors.mjs` | Frozen GitHub `development` tips and typed `ConsumerContractError` |
| `registry.mjs` / `config.mjs` | One pinned provider registry and non-secret runtime bindings |
| `transport.mjs` / `redaction.mjs` | Authenticated HTTPS JSON transport, bounded retries/timeouts, and safe diagnostics |
| `clients.mjs` | Bounded operation adapters composed with the validators |
| `platform.mjs` | Identity / permissions / capabilities (`AuthClaims 1.1.0`) |
| `libraries.mjs` | Revision-2 immutable library references |
| `brain.mjs` | Advisory knowledge / coordination projections |
| `skills.mjs` | Immutable skill release addressing and bounded telemetry |
| `autowork.mjs` | Request / status / handoff / receipt validators |
| `mcp.mjs` | Shared MCP `2026-07-28` modern negotiation and optional OKF `0.2` mapping |
| `index.mjs` | Public barrel after S1–S5 validators exist |

The validator modules do not mint credentials or grant authority. The runtime
foundation can call only registry-allowlisted HTTPS JSON operations using a
caller-supplied external credential resolver; it never stores or logs the
credential. Requests have bounded timeouts/retries and responses/errors are
bounded and redacted. No module has Git write, Ledger, Gate mutation, or nested
self-install APIs. Provider repositories are not modified by this work.

Autowork is explicitly availability-gated. If its configured runtime is absent,
the client returns a `HOLD` with `reason: live_runtime_unavailable`; it never
converts that condition into an accepted or successful result.

IDE Development is the system source. It must never receive a nested
`.ide-development/` install of itself. Do not run
`python3 scripts/ide-development.py install` against this repository.

## Pin authority

Pins are the GitHub `development` tip of each provider repository at freeze
time. They are **not** local sibling checkout HEADs, even when a sibling clone
is ahead of `origin/development`. Live `HEAD` or `latest` is not a pin.

Freeze command (read-only):

```bash
gh api repos/linktrend/<Provider>/commits/development --jq '{sha:.sha,tree:.commit.tree.sha}'
```

Frozen on 2026-08-17 (Asia/Taipei) from that GitHub API:

| Key | Repository | Commit | Tree |
|---|---|---|---|
| platform | `linktrend/LiNKplatform` | `2d5f37ef6b8e40ad47305adab47613d915967c1b` | `90b51726f7a77e4620151a463a10cfc3d2007c88` |
| libraries | `linktrend/LiNKlibraries` | `5901d111309543ed0839938d7217475e5d4b8ac4` | `185d7cf714777d60a2d01a4881bf1a11bc5018d9` |
| brain | `linktrend/LiNKbrain` | `77af7d02a76e6a8877d59fbd3d3e917ac6e830c5` | `0cae42d612342f5e52c7e2e0e76cb6fc2f6d81f3` |
| skills | `linktrend/LiNKskills` | `0d6bf34546f89c9beb7f05483a3ed4deeb3a5a67` | `6c36e6c98f90e55d957fba781327b1b0ef90860a` |
| autowork | `linktrend/LiNKautowork` | `9caab9aa33de5f96e33d67d880f2934dc6fd9fef` | `5f306d674780a5a26048017f916da6048d71e7a5` |

Issue 244 pin SHAs are refused and must not appear as pins in `pins.mjs`.

## MCP and OKF

`negotiateMcp('2026-07-28', 'modern')` is the only accepted negotiation.
Legacy or session `initialize` negotiation fails closed. Optional OKF `0.2`
mapping is field mapping only: it cannot override Brain
`authority=advisory` / `executionAuthority=none`.

Export: `FROZEN_PROVIDERS` from `pins.mjs` (also re-exported from `index.mjs`).
Typed failures use `ConsumerContractError` with a stable `code` from `errors.mjs`.

Runtime configuration uses `provider-runtime-config/v1` and contains endpoint
URLs, credential-reference names, enabled capabilities, and provider
availability only. Secret values remain outside Git and outside this package.

The installed Wave-1 `core/library/library-client.mjs` stays in place. This
directory does not replace it.

Managed-core materialization for the nine consumers is a later packet after
`v2.4.0`. Pre-rollout source stays under `core/link-integrations/` and
`tests/link-integrations/` only.
