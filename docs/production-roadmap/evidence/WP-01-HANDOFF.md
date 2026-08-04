# WP-01 evidence and handoff — Product Contract and Golden Automation Package

**Status:** Implemented for source review; strengthened by C-W1-02/C-W1-04 catalogue-audit corrections. No deployment, migration, live-template, gateway, dependency, or external-system change was made.

## Contract freeze

- GAP schema version: `0.1`.
- The only v0.1 executable runtime is `n8n`.
- Lifecycle: `draft`, `eval_pending`, `certified`, `deprecated`, `retired`.
- Release channels: `development`, `canary`, `stable`.
- Source authority: a converted package is the only editable source. The legacy manifest remains compatibility-only until per-workflow cutover under ADR 0002.
- Consumer Programs use explicit bindings. No contract in this packet permits consumer runtime search or autonomous selection of automations.

## Files added

| Path | Purpose |
|---|---|
| `docs/specs/GOLDEN-AUTOMATION-PACKAGE-v0.1.md` | Self-contained GAP contract, terms, digest algorithm, security rules, lifecycle, and cutover boundary. |
| `docs/specs/GAP-v0.1-MIGRATION-INVENTORY.md` | Disposition of all five top-level manifest workflows and archived/legacy material. |
| `docs/adr/0002-golden-automation-package-source-authority.md` | Future package authority, atomic cutover, and rollback decision. |
| `automations/schemas/*.schema.json` | Seven versioned contract schemas: package, intake, provenance, eval suite, monitoring, maintenance, and deployment. |
| `automations/packages/_golden-template/**` | Complete, inactive, non-deployable, schema-valid GAP example with workflow, contracts, evals, operations, provenance, and docs. |
| `automations/fixtures/contracts/**` | Positive and named negative contract fixtures plus fixture matrix. |

## Fixture matrix

| Fixture | Expected result | Gate owner |
|---|---|---|
| `package-valid.json` | Accepted as a package-schema document | WP-02 |
| `package-invalid-id.json` | Reject malformed automation ID | WP-02 |
| `package-invalid-semver.json` | Reject malformed release version | WP-02 |
| `package-invalid-lifecycle.json` | Reject unsupported lifecycle | WP-02 |
| `package-invalid-engine.json` | Reject non-n8n engine | WP-02 |
| `package-missing-monitoring.json` | Reject missing monitoring declaration | WP-02 |
| `package-missing-evaluation.json` | Reject missing evaluation declaration | WP-02 |
| `package-embedded-secret-shaped.json` | Reject credential-like field without echoing its value | WP-02 |
| `provenance-unresolved.json` | Reject unresolved licence/commercial-use review | WP-02 |

## Golden template identity evidence

The golden example is a structural template, not a release eligible for certification or deployment. Its declared values demonstrate field shape. WP-02 must compute release digests for real package releases only after their source has an immutable Git commit.

The deterministic digest algorithm is defined in the GAP specification. Applied twice to the current golden template after excluding the self-referential package digest, it produced the same values:

```text
workflow_digest: sha256:18eab5107bde49c5783f20432de7e71c6db8f3d1cc83b69295d27aca69aa5d93
package_digest:  sha256:af07d5f3af85fac55fb548c46ce21a19a7176766a34a2a09ce84d80fbc7da6f6
```

Governed inputs are the manifest (with only `package_digest` normalized), workflow, contract JSON, eval JSON/fixtures, operational profile JSON, and provenance JSON. Documentation, changelog, generated evidence, and runtime artifacts are excluded. Provenance now carries the exact package automation/version/runtime identity plus a hash-bound source-to-target mapping for every declared source.

## Commands and results

| Command | Result |
|---|---|
| Node JSON parse of all WP-01 schema, fixture, and golden-package documents | Passed: 30 documents parsed. |
| Node deterministic digest calculation for golden template | Passed: workflow and package digests calculated. |
| Node deterministic digest calculation repeated | Passed: same package digest. |
| `npm run ci` | Passed: legacy template validation, 20 Vitest tests in 7 files, and TypeScript typecheck. Existing CI does not yet load GAP schemas. |

## Handoff to WP-02

WP-02 must add the selected pinned Draft 2020-12 JSON Schema validator and execute all seven schemas. It must convert fixture expectations into automated tests, implement the defined canonical digest algorithm, validate safe references and package completeness, scan secret-shaped content without exposing it, validate n8n graph invariants, and retain the old top-level template validator during conversion.

WP-02 must not silently change v0.1 required fields, enum values, file roles, digest exclusions, or source-authority rules. A requested incompatible change requires a new contract version and ADR. C-W1-02 makes one explicit v0.1 contract clarification: a provenance document must identify the same automation version and n8n runtime as its manifest and must include hash-bound source-to-target mappings.

## Unresolved implementation questions deliberately deferred

1. The exact operational secret-delivery pattern for n8n nodes remains a WP-05 security/runtime decision. This contract only permits secret references.
2. Live promotion approval thresholds and product entitlement rules are later control/product decisions. This contract requires independent approval where declared, but creates no approval service.
3. The permanent generated catalogue index location and production release import command are WP-02/WP-05 work.
4. Source licence decisions must be made from actual source artefacts during intake. The golden template contains no third-party source.

## Scope confirmation

WP-01 did not modify gateway code, Supabase migrations, `package.json`, the current live templates/manifest, deployment configuration, or another repository. No commit was created.
