# WP-02 — Catalogue, Publisher, and Validator

## Objective

Implement the deterministic package validation, release hashing, catalogue generation, and CI gates that turn Golden Automation Packages into a trusted source catalogue.

## Dependencies

WP-01 contract freeze.

## Owned paths

- `packages/automation-catalog/**`
- `scripts/validate-automation-packages.mjs`
- `scripts/build-automation-catalog.mjs`
- `automations/catalog/index.json`
- `automations/fixtures/validator/**`
- Root build/test configuration only where required
- `.github/workflows/ci.yml` only for new catalogue gates

Do not create database records, deploy n8n, or implement the Automation Architect.

## Required implementation

1. Add a justified, pinned JSON Schema validator dependency and lockfile update.
2. Load and execute every WP-01 schema; do not replace schema execution with regular expressions.
3. Validate required files, safe relative paths, declared references, SemVer, lifecycle, runtime, digests, and package completeness.
4. Validate n8n workflow portability invariants: parseable JSON, unique node IDs/names, valid connections, declared triggers, declared result/callback behavior, and supported node policy.
5. Scan package/intake files for private keys, access tokens, credential objects, connection strings, and other secret-like material. Produce safe findings without echoing detected values.
6. Validate provenance source hashes, licensing conclusion, source-to-target map, and commercial-use clearance for commercial offerings.
7. Validate catalogue consistency: unique automation/version, immutable package hash, certified-release evidence requirement, no new instances from deprecated/retired releases.
8. Build a deterministic operator catalogue index from valid packages. It contains metadata and paths, not secrets, workflow bodies, or mutable operational state.
9. Provide `--check` mode that fails when the committed index is stale.
10. Keep current template validation during conversion, but mark removal conditions precisely; CI runs both until all live workflows are packaged.

## Test matrix

- Valid minimal and complete packages.
- Missing file/reference/schema.
- Invalid version/ID/lifecycle/runtime.
- Workflow connection to missing node.
- Duplicate workflow node identity.
- Embedded credential/private key/token.
- Unknown or commercially incompatible licence.
- Hash mismatch and catalogue staleness.
- Certified state without exact eval receipt.
- Same input produces identical catalogue bytes.

## Acceptance criteria

- `npm run validate:automations` and `npm run catalog:check` exist and run in CI.
- Errors name the package, path, rule, and safe remediation without leaking sensitive text.
- A raw n8n JSON file alone cannot pass.
- The generated index is deterministic.
- The current template compatibility check still passes until deliberate cutover.
- Unit and regression tests are green from a clean install.

## Rollback

The old validation script remains callable during Wave 1. Reverting this packet must not delete packages or alter n8n. Catalogue generation is reproducible from source packages.
