# C-W1-02 and C-W1-04 correction evidence — catalogue integrity and CI coverage

**Scope:** Correct the independent Wave 1 audit findings in the Golden Automation Package validator and official test pipeline. This change does not modify the Automation Architect implementation, database migration, gateway, live systems, deployment configuration, or existing n8n workflow inventory.

## Corrected guarantees

1. A package with lifecycle `certified` is rejected unconditionally until WP-06 implements verifiable independent evaluation receipts. A local JSON assertion such as `passed: true` cannot certify a release.
2. The intake schema is executed against every checked-in intake JSON record. Together with package validation this executes all seven GAP v0.1 schemas.
3. Provenance requires the same automation ID, release version, engine, and n8n version as the package manifest. Each declared source has at least one source-to-target mapping and the mapping carries the exact declared SHA-256 source digest.
4. Evaluation suite ID/version/runtime declarations are checked against the package manifest.
5. References are checked after filesystem real-path resolution. A symlink that would escape the package is rejected.
6. `automations/catalog/<automation_id>/<version>` must equal the package manifest identity. The package graph must match the declared result mode: a synchronous response requires one webhook trigger and one Respond to Webhook node; other result modes may not contain that node.
7. Official root CI now executes the Automation Architect and Automation Contracts package tests and typechecks in addition to the root suite.

## Adversarial coverage

The catalogue tests now exercise a copied receipt claiming success, source hash mismatch, evaluation identity drift, response-mode/graph mismatch, symlink escape, and directory identity drift. The positive Golden template remains inactive, `draft`, internal-only, and validates with zero errors.

## Validation evidence

`npm run test:catalog` passed: 34 tests across 8 files. `npm run ci` was started after these changes and correctly surfaced a separate WP-03 Automation Architect incompatibility: its candidate generator has not yet emitted the strengthened provenance fields and can request a synchronous response while generating a manual-only workflow. This correction packet intentionally does not edit WP-03 implementation. The package tests/typechecks are now wired into official CI and will pass once that independently owned generator is corrected.

## Handoff boundary

WP-03 must update generated candidates to use `result_mode: none` for manual-only candidates (or generate the required webhook/respond graph) and produce the required provenance identity/mappings. WP-06 alone may introduce the verifiable receipt implementation that re-enables certified releases. A fresh Sol Medium audit must verify both corrections before Wave 1 is accepted.
