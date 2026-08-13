# Delivery modes

**Status:** Active. This document describes the hosted phase-integration
profile consumed by managed-core. The frozen field meanings are defined in
`../planning/github-compute-final-fix/FROZEN-INTERFACES.md`.

## Supported mode

`phase-integration` is the approved system profile. Issue branches are
checkpoint-only. Accepted issue commits are integrated serially into one
`phase/*` branch, and one Phase PR carries the combined result into
`development`.

The configuration is `.github/linktrend-delivery-mode.json`:

- provider: `github-hosted`
- runner: `ubuntu-24.04-arm`
- checkpoint CI: `false`
- obsolete cancellation: `true`
- infrastructure attempts: `2`
- sealed candidates: `2`
- full-suite review: final candidate only

Repository-owned fast, full, and release commands stay in the configuration.
The managed system validates their shape; it does not invent product
commands.

## Named gates

The stable checks are `Linktrend Fast Checks`, `Linktrend Full Suite`,
`Linktrend Receipt Gate`, and `Linktrend Branch Source Policy`, together with
consumer-owned required checks. Missing, stale, neutral, or wrong-SHA evidence
is not success.

## Promotion identity

Receipt reuse requires exact equality of repository, Git tree, dependency
digest, profile digest, and workflow digest. A different commit with the same
immutable content may reuse a valid receipt; changed content may not.

## Non-goals

This contract does not authorize live repository settings, credential,
service, host, Docker, billing, consumer, pull-request, merge, or release
operations. Those operations require the W3 external procedure and explicit
operator authority.
