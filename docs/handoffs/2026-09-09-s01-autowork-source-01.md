# S01-AUTOWORK-SOURCE-01 handoff

**Date:** 2026-09-09 (Asia/Taipei)
**Status:** Implemented on issue branch; independent review required
**Base:** `a13a6467fc9bc2fccdddd1de8d9e258c78e57fdd` / tree `10e6b59394bfd57703d6f3cee5d7bcda3aa7342f`

## Source repairs

- `qs` is overridden to `^6.16.0` and the lockfile resolves all consumers to `6.16.0`.
- Root package metadata now includes version `0.1.0`.
- `npm run sbom` generates a validated, lockfile-based CycloneDX 1.6 JSON document with reproducible output. `npm run sbom:check` generates twice and compares the bytes.
- Development/staging NATS uses JetStream storage at `/data` on `nats_jetstream_dev` and has no host port. Production remains private and persistent on `nats_jetstream_prod`.
- Migration preflight is POSIX `sh` compatible and accepts either `shasum` or `sha256sum`; it retains the dry-run default and the explicitly supplied authorized command path.
- Release readiness now validates both private persistent NATS Compose blocks and the existing provider-neutral Traefik/Tailscale placeholder markers. No provider values were added.

## Verification and boundaries

Focused shell, SBOM, audit, release, and Compose checks passed. Heavy browser/full builds, image builds, live deployment, provider/authentication, credentials, databases, Server01, protected refs, and implementer PRs remain out of scope. Independent review and governed integration are still required.
