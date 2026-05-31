# Peer repo borrow review

Version: 1.0  
Status: active (2026-05-30)

Tiered review of LiNKtrend peer factories and agent stacks. LiNKdev **borrows verification discipline**, not a second orchestration brain. See [BORROW-PACK.md](BORROW-PACK.md) for active item IDs.

## Sources reviewed

| Repo / stack | What we looked at | LiNKdev posture |
|--------------|-------------------|-------------------|
| **UBS / build-anything-claude** | 28-gate per-issue bundle, cosign witness, container sandbox v1, per-atom orchestrator, adversarial multi-model review | **Partial borrow** — see tiers below |
| **gstack** | `/ship`, proof blocks, trajectory logging, release discipline | **Skills only** — catalog under `LiNKdev/skills/gstack/`; no mandatory `/ship` on every issue |
| **open-swe / container executors** | Isolated runner containers for parallel agents | **Rejected v1** — see [docs/LINKDEV_SANDBOX.md](docs/LINKDEV_SANDBOX.md) |
| **LiNKtrend legacy `.ai-swarm/`** | Branch-per-packet, verify-before-merge, Principal gates | **Retained** — folded into DS-B9, DS-B12, branch law (worktrees dropped) |

## Tier A — Adopted (per issue)

Mechanical gates every executor must pass before `linkdev:merge-ready`.

| Pattern | Peer origin | LiNKdev item |
|---------|-------------|----------------|
| Mechanical verify + secrets scan | UBS subset | DS-B1, DS-B4 → tier A `verify_subset`, `secrets_scan` |
| Proof block in agent report | UBS + gstack | DS-B5 → tier A `proof_block_present` |
| Allowed-files enforcement | UBS | tier A `allowed_files_respected` |
| Clean working tree at handoff | LiNKtrend packets | DS-B12, LAW-05 → tier A `working_tree_clean` |
| Trajectory / debug in reports | gstack session logs | DS-B10 |
| Reviewer rejects vacuous PASS | UBS | DS-B2, LAW-01 |

**Catalog:** `LiNKdev/factory/gates/catalog.json` tier **A**.  
**Runner:** `LiNKdev/factory/scripts/run-gates.sh --tier A` (invoked from `verify.sh` unless `LINKDEV_SKIP_GATES=1`).

## Tier B — Adopted (module phase)

Gates when a module phase completes (Integrator / Orchestrator boundary).

| Pattern | Peer origin | LiNKdev item |
|---------|-------------|----------------|
| DAG validation | UBS | DS-B4 → tier B `validate_dag` |
| Integration smoke | gstack `/ship` smoke subset | tier B `integration_smoke` (reads `STACK.md`) |
| Architecture gate (JS/TS) | UBS typecheck/lint | tier B `architecture_gate` |
| Council at phase boundary | UBS advisory panels (lightweight) | Council **G3** → tier B `council_g3_report` |

**Catalog:** tier **B**. Principal may proceed on WARN at G3; any BLOCKER stops progress (LAW-07).

## Tier C — Adopted (program release)

Gates for release-phase **critical** issues and Principal Release OK prerequisite.

| Pattern | Peer origin | LiNKdev item |
|---------|-------------|----------------|
| Full-repo critical verify | UBS release gate | DS-B16 → tier C `verify_critical` |
| Program SHA256 manifest | UBS artifact hashing | DS-B23, LAW-08 → tier C `program_proof_manifest` (**no cosign**) |
| Merge replay traceability | UBS replay | DS-B11 → tier C `replay_merge_verify` |
| Ship criteria checklist | gstack release + LiNKtrend MVO | DS-B14 → tier C `ship_criteria_check` |
| Council at release | UBS pre-ship review | Council **G4** → tier C `council_g4_report` |

Per-issue `proof-manifest.sh` remains required for **critical** issues (DS-B7); program manifest aggregates at release (DS-B23).

## Laws and intent (cross-tier)

| Pattern | Peer origin | LiNKdev item |
|---------|-------------|----------------|
| Eight enforceable laws | UBS law table (reduced set) | `LiNKdev/factory/laws/LINKDEV_LAWS.md` (DS-B19) |
| Intent verdict before execution | UBS intent gate | DS-B20, LAW-02 → `validate-intent.sh` blocks `linkdev:ready` |
| Council G1–G2 at program start | UBS design review | DS-B24 — Planner; Orchestrator blocked until G2 PASS |

## Council G1–G4 (adopted)

Multi-advisor review with five personas (security, architecture, DX, QA, product). **Any BLOCKER halts progress** until resolved or Principal waives.

| Gate | When | Borrow note |
|------|------|-------------|
| **G1** | After Principal OK on finished-product narrative | Replaces mandatory multi-Opus adversarial review with structured council |
| **G2** | Before STATE `phase: running` | Intent + program plan; feeds `intent-verdict.json` |
| **G3** | Module phase complete | Phase integration proof; tier B gate |
| **G4** | Program release | Release proof; tier C gate; PASS required before staging |

See `LiNKdev/factory/prompts/council/ROLE.md`.

## Rejected — not adopted

| Pattern | Peer origin | Reason |
|---------|-------------|--------|
| **Full 28-gate per-issue bundle** | UBS build-anything-claude | Ops and model cost too high for meta-factory + product velocity; replaced by tier A/B/C subset |
| **Mandatory cosign witness** | UBS release signing | GSM + git audit sufficient for MVO; SHA256 manifest without witness chain (LAW-08 explicit rejection) |
| **Container sandbox v1** | open-swe / UBS executor isolation | Branch-per-issue + allowlists sufficient for Phase 1; revisit when untrusted multi-tenant execution or live side effects without leases ([docs/LINKDEV_SANDBOX.md](docs/LINKDEV_SANDBOX.md)) |
| **Git worktrees per issue** | Legacy `.ai-swarm/` parallel packets | **Rejected** — handoff failures; one checkout + issue branches only |
| **Per-atom orchestrator** | UBS atom-level scheduling | LiNKdev uses issue-level Orchestrator + PROGRAM.md DAG; no sub-issue atom scheduler |
| **Mandatory multi-Opus adversarial review** | UBS | Replaced by council G1–G4 with five fixed personas |
| **Antigravity in core factory** | Peer automation experiments | Optional peer executor only; not in factory install manifest |
| **Second orchestration stack** | CrewAI / LangGraph / n8n brain | GitHub + STATE + labels remain control plane |
| **Mandatory gstack `/ship` on every issue** | gstack | Release phase and critical tier only |

## Isolation (DS-B12, DS-B25)

**Adopted:** one repo checkout; branch `issue/<issue-id>-<slug>` per issue (LAW-05). Parallel waves never share one checkout between concurrent executors.  
**Rejected:** git worktrees; container sandbox v1 as mandatory executor envelope.

## Traceability

| Document | Purpose |
|----------|---------|
| [BORROW-PACK.md](BORROW-PACK.md) | Active borrow IDs DS-B1 … DS-B25 |
| [SPEC.md](SPEC.md) §17–22 | Normative factory spec for laws, intent, tiers, council, manifest, branch isolation |
| [laws/LINKDEV_LAWS.md](laws/LINKDEV_LAWS.md) | LAW-01 … LAW-08 |
| [gates/catalog.json](gates/catalog.json) | Tier A/B/C gate definitions |
