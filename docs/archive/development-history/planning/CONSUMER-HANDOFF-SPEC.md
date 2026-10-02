# LiNKautowork consumer handoff — LiNKskills PKT-03 / XPKT-03 (planning-only HOLD)

- **Packet class:** planning-only consumer specification
- **Decision:** **HOLD**
- **Acceptance claimed:** no
- **Implementation claimed:** no
- **Activation claimed:** no
- **Principal planning authorization:** granted by the controlling PLAN-AUTOWORK-SKILLS-HANDOFF task (no repeated magic word). This authorizes **planning records only**. It does not accept a provider release, dual-app proof, polling implementation, or live operation.

IDE Development managed-core **v2.5.2** files remain **read-only**. This packet does not install, repair, activate, or rewrite `.ide-development/`, installer sources, or managed `skills-lock.json` copies.

## Exact consumer baseline (verified)

| Field | Value |
|---|---|
| Repository | `linktrend/LiNKautowork` |
| Protected ref | `development` |
| Commit | `f75656930eb4d82827e480f00a435069c501503e` |
| Tree | `013f609cc432e7194388b6ffd09e32f71ac6e672` |
| Isolated candidate branch | `dev/cloudcursor/plan-autowork-skills-handoff-acc3` |
| Merge to `development` | **not requested** (planning-only; do not treat this branch as accepted) |
| Staging / main / VPS / production / Full CI | **out of scope** |

Verified by `git fetch origin development` and `gh api repos/linktrend/LiNKautowork/commits/development`. Local `HEAD` and `origin/development` both equal the commit above.

## Packet identities (do not collapse)

Three different “PKT-03” surfaces exist. This specification names them and keeps them separate.

| Name | Owner | What it is | Observed state used here |
|---|---|---|---|
| **LiNKskills PKT-03** | `linktrend/LiNKskills` | Provider packet “External collection vendor/adaptation/update lifecycle” (`ISS-03`). Must define the **signed idempotent candidate contract** Autowork will later consume. | `executionState: PLAN` in LiNKskills `docs/planning/governed-skill-expansion/EXECUTION-MANIFEST.json` on protected `development`. **Not an accepted provider release.** |
| **IDE skills.lock PKT-03** | IDE managed-core v2.5.2 (installed in this consumer) | Consumer lock `skills.lock.v0.2` / `ISS-04`. Dual-app retrieval proof before any physical skill-copy removal. | `dualAppProof.codex = HOLD`, `dualAppProof.cursor = HOLD`, `physicalRemovalAuthorized = false`. |
| **XPKT-03** | `linktrend/LiNKautowork` | Cross-repository packet “LiNKautowork upstream polling” (`docs/planning/governed-skill-expansion/cross-repository/HANDOFF-PACKETS.md` in LiNKskills). | **Not implemented.** Inputs (PKT-03 signed contract) are not frozen. Founder confirmation of the polling **implementation** boundary remains required before any later execute packet; this file is not that confirmation. |

## Observed provider identities (inventory, not pins, not acceptance)

Live `HEAD` / `latest` is not a pin. These rows are read-only observations for HOLD diagnostics.

| Label | Repository | Commit | Tree | Use |
|---|---|---|---|---|
| LiNKskills protected `development` (observed 2026-08-31) | `linktrend/LiNKskills` | `4324d41fe6a7a6883075e9baa9a5a7f71dd13b3d` | `7c5a36f8773ebe9bac417d42a8a48a286fe5968d` | Current provider HEAD. **Not** an accepted PKT-03 release for Autowork. |
| IDE skills.lock provider pin (managed, read-only) | `linktrend/LiNKskills` | `e3d80fd22a05a4f68207e130c50b772b5acffda4` | `69a131b46a73a4ef724694bfe240b1a11652bcc9` | Lock inventory only. `providerLockDigest` `sha256:67df14f6b376063dd049dfd4138aa7f723cedf8af800e66666f5110c7c68ddac`. |
| IDE S0 frozen skills pin (`pins.mjs`, 2026-08-17) | `linktrend/LiNKskills` | `0d6bf34546f89c9beb7f05483a3ed4deeb3a5a67` | `6c36e6c98f90e55d957fba781327b1b0ef90860a` | Frozen consumer pin. Must not be rewritten by this packet. |

Mismatch among these three identities is expected. It is **not** authorization to retarget pins, merge a lock, or implement polling.

## Required freeze before any later XPKT-03 execute packet

XPKT-03 remains HOLD until **all** of the following are exact and independently recorded. Absence of any one item keeps this consumer **blocked**.

1. **Exact LiNKskills PKT-03 provider release** on a protected ref, with commit + tree, for the signed idempotent candidate contract (inventory/content/licence/diff facts → one candidate; no qualify/publish/pointer/activate). `executionState: PLAN` is not that release.
2. **Dual-app proofs** on the consumer lock: `dualAppProof.codex` and `dualAppProof.cursor` both proven (not `HOLD`). Physical copy removal stays unauthorized until those proofs **and** `physicalRemovalAuthorized === true`. `planPhysicalSkillRemoval` currently returns `authorized: false` / `reason: dual_app_proof_hold`.
3. **Schema-valid provider-consumer handoff** with `verdict: accepted`, protected `acceptedReceipt`, and producer identity equal to the exact PKT-03 release — not this HOLD document.
4. **No substitution:** source tests, file presence, lock rows, or this planning spec must not be treated as consumer, hosted, VPS, E2E, or production evidence.

## XPKT-03 intended boundary (planning text only — do not implement)

From LiNKskills `HANDOFF-PACKETS.md` (provider roadmap dependency, not Autowork execution authority):

- **Owner:** LiNKautowork.
- **Inputs:** PKT-03 signed idempotent candidate contract (missing as an accepted identity).
- **Intended work (later packet):** deterministically poll configured upstreams on a bounded schedule; calculate inventory/content/licence/diff facts; submit **one** idempotent candidate. Do not qualify, publish, change current pointers, or activate.
- **Intended acceptance (later packet):** duplicate polls do not duplicate candidates; failed/partial scans fail closed; credentials/logs redacted; Skills readback binds the accepted candidate.
- **Prohibited in this packet:** pollers, schedules, credentials, n8n/gateway activation, catalogue mutation, Librarian qualification, pointer changes, skill-copy deletion, pin rewrites, managed-core edits, staging/main/VPS/production.

Autowork already owns a **separate** automation-domain Librarian (WP-07). XPKT-03 must not merge Skills/Brain/automation catalogues or identities.

## Handoff receipt (machine)

Canonical blocked receipt: [`provider-consumer-handoff.hold.json`](./provider-consumer-handoff.hold.json).

| Field | Value |
|---|---|
| `schemaVersion` | `1` |
| `kind` | `provider-consumer-handoff` |
| `verdict` | `blocked` |
| `lifecycleState` | `blocked` |
| `independentPreparationAllowed` | `true` |
| `integrationClaimed` | `false` |
| `acceptedReceipt` | `null` |

Schema (read-only managed): `.ide-development/schemas/provider-consumer-handoff.schema.json`.

## Validation (narrow, local)

Run only:

```bash
python3 docs/planning/pkt-03-xpkt-03/validate_hold.py
```

Do **not** run Full/`npm run ci`/browser/e2e suites, hosted Broad checks, or any deploy profile for this packet.

## Governance vs planning

| Candidate class | This packet |
|---|---|
| Governance (reuse independent PASS, official issue/Phase PR, narrow hosted checks, merge to protected `development`) | **Not this packet.** No independent PASS exists for XPKT-03 implementation. Draft PR **#111** and IDE Group B Fast failures are out of scope and must not be reopened here. |
| Planning-only | **This packet.** Isolated candidate branch, exact HOLD validation, no acceptance, no implementation, no merge claim. |

## Rollback

Discard the candidate branch. Protected `development` remains `f75656930eb4d82827e480f00a435069c501503e`. No runtime, pin, lock, or managed-file rollback is required because none of those were mutated.
