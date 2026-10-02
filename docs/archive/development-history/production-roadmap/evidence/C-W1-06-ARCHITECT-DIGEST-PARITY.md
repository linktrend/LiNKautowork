# C-W1-06 correction evidence — Architect digest parity

**Scope:** Wave 1 Sol audit correction within the Automation Architect package only. No catalogue release, credential, live n8n workflow, deployment pointer, certification, or external service was changed.

## Correction

`calculatePackageDigest` now uses the same governed-file selection as the frozen WP-01/WP-02 catalogue implementation:

- It includes `automation.json`, `workflow.json`, JSON contracts, JSON evaluation suite and fixtures, operations profiles, and `provenance/sources.json`.
- It excludes generated/non-governed evaluation material: `evals/certification-receipt.json`, `evals/evidence/**`, and `evals/receipts/**`.
- It still excludes the declared package digest value from the digest calculation itself.

## Regression proof

The package integration test creates a candidate in a disposable directory and compares the Architect digest directly with WP-02's exported `calculatePackageDigest` function. It proves that:

1. Adding each excluded receipt/evidence category does not change either digest.
2. A governed fixture change changes the Architect digest.
3. The changed Architect digest exactly equals the WP-02 catalogue digest.

## Validation

| Command | Result |
|---|---|
| `npm --prefix packages/automation-architect run typecheck` | Passed. |
| `npm --prefix packages/automation-architect test` | Passed, including WP-02 digest-parity regression coverage. |
| `npm run ci` | Passed. |
| `git diff --check` | Passed. |
