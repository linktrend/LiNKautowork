# Hosted phase delivery contract

**Status:** Active W2-P3 doctrine for the managed-core delivery system.
**Authority:** `../planning/github-compute-final-fix/FROZEN-INTERFACES.md`.

IDE Development uses GitHub-hosted ARM64 checks as the delivery execution
boundary. The repository remains the source of truth for configuration, Git
history, receipts, and evidence; GitHub remains the authority for checks,
pull requests, branch protection, and promotion records.

## Commit-to-main flow

1. An implementer checkpoints on `issue/<number>-<slug>` (or an approved
   `dev/*` branch). A checkpoint push does not start managed CI.
2. The Phase Packager/Coordinator (`scripts/gitops/packager_coordinator.py`)
   integrates accepted issue SHAs serially on `phase/*` and opens or updates
   one draft Phase PR. Retained `packager_discover.py` is not that component.
3. The Phase PR runs `Linktrend Fast Checks` on hosted `ubuntu-24.04-arm`.
   Fast executes fixture-aware secret scanning of every tracked regular blob.
   Fast runs are scoped to repository, workflow, and PR number; a newer run
   cancels only an older run for that same PR.
4. Terra seals one exact candidate head. Required independent review must be
   clean on that exact head before `Linktrend Full Suite`, unless repository
   policy explicitly requires Full first. A later repair invalidates prior
   review and Full evidence. Only the final sealed candidate may run Full and
   the existing Bugbot final-candidate check. Full always binds the canonical
   PR head (never merge-ref identity). Ordinary Phase merge requires the exact
   retained Full receipt for that head/tree.
5. A successful full-suite receipt is reusable only when repository, Git tree,
   dependency, profile, and workflow identities match exactly. A changed tree
   or dependency invalidates reuse. Exceptional recovery may mint the same
   receipt schema for an unchanged integrated `development` tree without an
   empty commit or fake PR (`mode=recovery`).
6. Development, staging, and main promotion use the receipt and source-policy
   gates. Promotion does not rerun the full suite when the exact receipt is
   valid. Main still requires Carlos's explicit approval.

## Bounded failure policy

Infrastructure may be retried at most twice for a candidate. At most two
sealed candidates are admitted. A third attempt or candidate is a stop with a
durable, sanitized report. Obsolete work is cancelled; cancellation is not a
success signal.

## Authority and boundaries

The built-in workflow token may publish only the minimum native workflow
results required by the named checks. Credential names may appear in redacted
inventory evidence, but secret values never appear in logs or reports.

Emergency authority, external cleanup, billing configuration, and consumer
rollout are operator actions documented in
`../runbooks/hosted-delivery-operations.md`; this contract authorizes no
live mutation.

The former Streamlined Delivery planning set is historical and superseded. It
remains available for provenance under `../planning/streamlined-delivery/`
and is not an instruction source.
