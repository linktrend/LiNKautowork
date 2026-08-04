# WP-01 — Product Contract and Golden Automation Package

## Objective

Freeze the product terminology, ownership boundaries, Golden Automation Package v0.1 contract, lifecycle, source-of-truth transition, and migration inventory that every later packet consumes.

## Inputs

- `docs/production-roadmap/LINKAUTOWORK-PRODUCTION-ROADMAP.md`
- Current five-entry `automations/templates/manifest.json`
- Current n8n pin and gateway contracts
- LiNKplatform `org_id` identity boundary
- LiNKskills Golden Template as a conceptual precedent only

## Owned paths

- `docs/specs/**`
- `docs/adr/**` for new LiNKautowork ADRs
- `automations/schemas/**`
- `automations/packages/_golden-template/**`
- Contract fixtures under `automations/fixtures/contracts/**`

Do not modify gateway behavior, migrations, UIs, live templates, or external repositories.

## Required implementation

1. Define Golden Automation Package v0.1 using versioned JSON documents. The first executable engine is exactly `n8n`; the engine field remains extensible.
2. Define JSON Schemas for package manifest, intake record, provenance sources, eval suite, monitoring profile, maintenance policy, and deployment profile.
3. Define lifecycle states: `draft`, `eval_pending`, `certified`, `deprecated`, `retired`; define release channels `development`, `canary`, `stable`.
4. Define immutable release identity using automation ID, SemVer, package digest, workflow digest, Git SHA, and n8n version.
5. Define required input/output/configuration schema references, secret reference declarations, criticality, side effects, approvals, retries, idempotency, telemetry redaction, retention, SLO, provenance/licensing, and system/product ownership.
6. Define the distinction between definition, release, instance, deployment, binding, product offering, execution receipt, eval result, and maintenance candidate.
7. Add a complete golden template directory with syntactically valid example files and no placeholder secrets.
8. Inventory every current top-level workflow and classify it as conversion candidate, deprecated, or retired. Preserve runtime behavior during later conversion.
9. Write an ADR declaring package source as the future workflow authority and the old manifest as a compatibility surface until migration completion.
10. Write the source-authority cutover and rollback rules so two competing editable authorities never exist.

## Validation and tests

- Parse every JSON Schema with the selected standards-compliant validator used by WP-02.
- Validate positive and negative fixtures for required fields, IDs, SemVer, lifecycle, engine, missing monitoring, missing evals, embedded secret-shaped values, and unresolved provenance.
- Hash the golden template twice and demonstrate deterministic results after generated/timestamp fields are excluded by contract.

## Acceptance criteria

- A less-capable agent can create a structurally complete package without reading LiNKskills or archived LiNKautowork documents.
- `engine=n8n` is the only v0.1 executable engine.
- No consumer discovery/search behavior appears in the contract.
- No raw secret field is permitted anywhere in package, config, provenance, eval, monitoring, or deployment documents.
- Existing workflows have an explicit migration disposition.
- Contract tests are automated and green.

## Evidence and handoff

Record changed files, schema version, fixture matrix, commands/results, unresolved contract questions, and digest rules. The packet is a contract freeze; later packets must request a new version rather than changing v0.1 incompatibly.
