# Streamlined delivery contract

**Status:** Active for managed-core v2.2.0.
**Scope:** Phase integration, local coordination, exact gate evidence, and
promotion reuse. Live GitHub settings, services, and releases remain external
operations and are never performed by package installation.

## Authority and trust boundary

Git history, pull requests, commit statuses, reviews, and releases remain
GitHub authorities. The local coordinator is a bounded scheduler and evidence
publisher; it is not a permission authority. It loads execution policy only
from the protected default branch and executes candidate commands only in
disposable Linux containers. Candidate branches are untrusted data and cannot
replace policy, credentials, or host commands.

The shared consumer surface is `scripts/gitops/coordinator/`. Host-only
execution, queue, and service code lives under `host/coordinator/` and is not
installed into consumers.

## Phase delivery

In `phase-integration` mode, Issue checkpoints are commit-and-push only. They
do not create pull requests or request Bugbot. The Integrator alone mutates a
`phase/*` branch. A Phase record proves each accepted exact Issue SHA is
included, records the immutable base, seal revision, candidate identity, gate
results, and promotion identities. One draft Phase PR is opened only after
the sealed candidate is proven.

The default candidate is the original seal (revision 1). One corrected seal
(revision 2) is allowed. A third seal requires explicit principal
authorization. A changed head invalidates all candidate gates and receipts.

## Candidate identity and gates

Candidate reuse requires the same repository, Git tree SHA, canonical
dependency digest set, and required test profile. A different commit SHA may
reuse evidence only when those identities match exactly. The stable status
contexts are `Linktrend Fast Gate`, `Linktrend Full Suite`, `Linktrend Phase
Ready`, `Linktrend Staging Gate`, `Linktrend Release Gate`, and `Linktrend
Coordinator`; `Cursor Bugbot` remains an independent external context.

Fast checks target 300 seconds or less. A full suite is repository-owned and
runs only for the final candidate when required. Staging and main run only
short release checks when the exact receipt matches; they must not rerun the
full suite for matching content.

Receipts are atomic, canonical JSON records. Only a passed receipt is
reusable. Receipt verification fails closed for a repository, gate, tree,
dependency, profile, status, evidence, or SHA mismatch.

## Attempts and bounded resources

An attempt increments only after a job starts. Queueing, observation,
deduplication, pre-start cancellation, and obsolete-job removal do not count.
Each exact candidate has at most two execution attempts; the second failure
transitions to `stopped` and produces one durable alert keyed by candidate
identity. No third dispatch is permitted.

The coordinator admits at most two fast jobs and one heavy job, never overlaps
heavy jobs, pauses under CPU, memory, disk, Docker, or interactive-use
pressure, and removes completed, cancelled, timed-out, and obsolete scoped
resources. The host Docker socket and broad cleanup targets are prohibited.

## Promotion and approval

Development requires the current seal, exact fast/Bugbot/full evidence, no
conflict, and an unchanged live head. Staging uses the matching receipt and
short release gate. Main defaults to `principal-approval`; automatic mode is
also supported but still requires every exact gate. Principal approval binds
the exact staging source SHA, current main base SHA, promotion PR head, and
receipt identity. Ruleset changes are dry-run/reversible plans owned by the
operator, not by a consumer package.

## Compatibility and rollback

`issue-pr` and `github-actions` remain supported compatibility profiles.
`local-coordinator` is the recommended v2 profile and does not depend on
GitHub Actions scheduling. Normal GitHub credentials are used; no custom
LiNKtrend GitHub App credential is packaged. Rollback restores the previous
coordinator/package version and exact consumer bytes through the existing
transaction journal. A failed trust, identity, cleanup, or protection check
stops promotion.

## W4 multi-host capacity

The local coordinator owns one global queue and durable isolated-worker
registry. The current Mac Mini fixture is the sole enabled production worker;
future Mac/Linux/VPS workers may register only as `isolated-candidate` workers
with explicit platform, architecture, capabilities, resource/concurrency
limits, heartbeat, state, and repository allowlist. Privileged coordinator
operations never run candidate code, and VPS registration cannot gain a
privileged role. Capability matching, pressure admission, repository-fair
priority selection, lease renewal/expiry, fenced stale results, and global
attempt preservation are covered by the W4 focused tests. See
[`MULTI-HOST-COORDINATOR.md`](MULTI-HOST-COORDINATOR.md).
