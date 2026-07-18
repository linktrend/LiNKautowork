# LiNKdev Laws

Version: 1.0  
Status: active (2026-05-30)

UBS-adapted, **deterministic and enforceable** laws for LiNKdev. Full 28-gate UBS is **rejected** (see `LiNKdev/factory/BORROW-PACK.md`). These eight laws are the mandatory gate set for program intent and release.

Each law maps to an ID checked in `intent-verdict.json` (`laws_checked[]`) and enforced by scripts, roles, or Principal action.

| ID | Law | Enforcement |
|----|-----|-------------|
| **LAW-01** | **No vacuous proof** | Reviewer rejects PASS without command output, artifact path, or trace. Integrator rejects program complete without proof manifest (DS-B2, DS-B17). |
| **LAW-02** | **Intent must pass before execution** | `validate-intent.sh` exits 0 only on PASS. Orchestrator must not set `linkdev:ready` until intent verdict PASS (DS-B19). |
| **LAW-03** | **Tier gates mandatory** | `LINKDEV_TIER=critical` required for release-phase issues. `verify.sh` tier extras must pass before `linkdev:merge-ready` on critical issues (DS-B6, DS-B16). |
| **LAW-04** | **No secrets in repo** | No API keys, tokens, passwords, or private keys committed. Use `.env.example` placeholders only. `verify.sh` scans scope for secret patterns (DS-B1). |
| **LAW-05** | **One branch per issue; one checkout** | Each issue runs on branch `issue/<issue-id>-<slug>` from `development`. No git worktrees. Never two concurrent executors on the same checkout; parallel work uses separate machines/IDEs or sequential waves. |
| **LAW-06** | **No merge to staging/main without Principal Release OK** | Integrator merges only to `development`. `staging` and `main` are Principal-only after explicit Release OK recorded in program STATUS (DS-B14). |
| **LAW-07** | **Council BLOCKER stops progress** | Any council verdict with severity `BLOCKER` halts Planner handoff and Orchestrator advance until resolved or waived by Principal. |
| **LAW-08** | **Program release requires SHA256 manifest** | Release phase must emit `proof-manifest.json` with per-artifact SHA256 hashes. **No cosign witness** required (explicitly rejected from UBS). |

## Deterministic checks

| Check | Script / role | Exit / outcome |
|-------|---------------|----------------|
| Intent PASS | `LiNKdev/factory/scripts/validate-intent.sh <program-id>` | 0 = PASS; non-zero = blocked |
| Mechanical verify | `LiNKdev/factory/scripts/verify.sh` | 0 required for merge-ready |
| DAG valid | `LiNKdev/factory/scripts/validate-dag.sh PROGRAM.md` | 0 required at program create + critical tier |
| Proof manifest | `LiNKdev/factory/scripts/proof-manifest.sh` | SHA256 manifest written |
| Vacuous proof | Reviewer ROLE | FAIL review, not PASS |

## Intent verdict contract

- Schema: `LiNKdev/factory/contracts/intent-verdict.schema.json`
- Template: `LiNKdev/factory/templates/intent-verdict.json`
- Verdict paths (newest wins if both exist):
  - `LiNKdev/product/reports/<program-id>/intent-verdict.json`
  - `LiNKdev/product/programs/<program-id>/intent-verdict.json`

## Council gates (Planner)

| Gate | When | Outcome |
|------|------|---------|
| **G1** | After Principal OK on finished-product narrative | Council review; any BLOCKER → stop |
| **G2** | Before STATE `phase: running` | Write intent verdict; PASS only if all laws + requirements pass; run `validate-intent.sh` |

Orchestrator **must not** set `linkdev:ready` until G2 intent verdict is PASS and `validate-intent.sh` exits 0.

## Related borrow-pack items

- DS-B1 … DS-B18: `LiNKdev/factory/BORROW-PACK.md`
- Rejected: 28-gate bundle, mandatory cosign, mandatory multi-Opus adversarial review
