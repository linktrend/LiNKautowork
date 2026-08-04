# Golden Automation Package v0.1

**Status:** Frozen by WP-01. Later packets consume this contract; incompatible changes require a new schema version and ADR.

## Purpose

A Golden Automation Package (GAP) is the complete source-controlled definition of one LiNKautowork automation release. It is more than a workflow export. It tells an operator, evaluator, and future agent what the automation does, which n8n version it needs, how it is safely invoked, what it returns, what it may change, how it is tested, how it is monitored, and where its source material came from.

The catalogue is for LiNKautowork builders and operators. A LiNKtrend system does not search it at runtime. It invokes the automation instance explicitly linked to one of its operations.

## Vocabulary

| Term | Exact meaning |
|---|---|
| Definition | Stable automation identity across releases, for example `client-invoice-reminder`. |
| Release | Immutable, versioned GAP source package identified by automation ID, SemVer, package digest, workflow digest, Git SHA, and n8n version. |
| Instance | One organisation-scoped, configured copy of a release in shared managed n8n. It has its own workflow ID, configuration reference, credentials scope, schedules, and telemetry. |
| Deployment | Evidence that a particular release was imported/promoted to a particular instance and environment. |
| Binding | Explicit configuration that connects a consumer Program operation to one instance. It is never an automation search query. |
| Product offering | A commercial description that a customer may choose on the website. It is not a workflow and not a client instance. |
| Execution receipt | Durable result/evidence record for one invocation, including the instance/release identity and redacted outcome. |
| Eval result | Hash-bound evidence from a controlled test run against a release. |
| Maintenance candidate | A proposed repair or improvement release; it has no production authority until separately evaluated and promoted. |

## Folder layout

The permanent release location defined by the production roadmap is:

```text
automations/catalog/<automation-id>/<version>/
├── automation.json
├── workflow.json
├── contracts/
│   ├── input.schema.json
│   ├── output.schema.json
│   └── configuration.schema.json
├── evals/
│   ├── suite.json
│   └── fixtures/
├── operations/
│   ├── monitoring.json
│   ├── maintenance.json
│   ├── deployment.json
│   └── runbook.md
├── provenance/sources.json
├── examples/
├── README.md
└── CHANGELOG.md
```

`automations/packages/_golden-template/` is the valid starter template for that layout. It is not a deployable definition and must never be imported into n8n as a live service.

## Versioned documents

| File | Schema | Required role |
|---|---|---|
| `automation.json` | `automation-package-v0.1.schema.json` | Release identity, ownership, runtime, contracts, risk, telemetry, and references. |
| Intake record | `automation-intake-v0.1.schema.json` | Quarantined source descriptor and source-to-target mapping. |
| `provenance/sources.json` | `provenance-sources-v0.1.schema.json` | Source hashes, licence conclusion, and review evidence. |
| `evals/suite.json` | `automation-eval-suite-v0.1.schema.json` | Executable evaluation cases and evidence policy. |
| `operations/monitoring.json` | `monitoring-profile-v0.1.schema.json` | SLO, health signals, alert rules, and health checks. |
| `operations/maintenance.json` | `maintenance-policy-v0.1.schema.json` | Bounded recovery and candidate-change policy. |
| `operations/deployment.json` | `deployment-profile-v0.1.schema.json` | Environments, canary/approval requirements, isolation, and rollback policy. |

The input, output, and configuration documents are JSON Schema Draft 2020-12 documents. They describe the automation's own validated business contract and must never include a `default`, `example`, or fixture containing a secret value.

## Runtime rule

GAP v0.1 requires `runtime.engine = "n8n"`. The engine field is intentionally a named discriminator so a later version can add another engine without changing definition, release, instance, binding, evaluation, telemetry, or provenance identity. It does **not** permit another executable engine in v0.1.

The release pin is the exact n8n SemVer in `release.identity.n8n_version`. n8n upgrades require a new release/evaluation evidence; a workflow is never assumed portable merely because its JSON imports.

## Required release identity and digest rules

Every release identity contains:

```text
automation_id + release.version + package_digest + workflow_digest
+ source_git_sha + n8n_version
```

`workflow_digest` is `sha256:` plus the lowercase SHA-256 hex digest of the exact UTF-8 bytes in `workflow.json`.

`package_digest` is calculated deterministically from these governed files only:

```text
automation.json                         (normalized as described below)
workflow.json
contracts/*.json
evals/**/*.json
operations/monitoring.json
operations/maintenance.json
operations/deployment.json
provenance/sources.json
```

`README.md`, `CHANGELOG.md`, generated evaluation receipts, and local/runtime artefacts are not governed inputs. They can document a release but cannot change its executable identity.

For every governed JSON file, the digest input is UTF-8 canonical JSON: recursively sorted object keys, no insignificant whitespace, and a final newline. For `automation.json` only, the value at `/release/identity/package_digest` is replaced with the literal `sha256:__excluded__` before canonicalization. This removes the otherwise self-referential field. For each sorted relative path, concatenate:

```text
<path UTF-8> + NUL + <lowercase SHA-256 hex of normalized file bytes> + NUL
```

The SHA-256 of that byte stream, prefixed with `sha256:`, is `package_digest`.

The builder must reject a declared digest that differs from the calculated value. It must calculate twice in the same clean checkout and obtain identical results. WP-02 owns the executable implementation; WP-01 provides this immutable contract.

## Lifecycle and promotion

| Lifecycle state | Meaning |
|---|---|
| `draft` | Package is being designed or adapted; cannot be bound or deployed. |
| `eval_pending` | Structure/provenance checks passed and executable evaluation is required or underway. |
| `certified` | Exact release has matching passing independent evaluation evidence. Certification does not itself deploy it. |
| `deprecated` | Existing instances may remain temporarily, but no new instance or binding targets it. Replacement guidance is required. |
| `retired` | Cannot be deployed, bound, or invoked. It remains for traceability only. |

Release channels are `development`, `canary`, and `stable`. A channel says where a certified release may be promoted; it does not bypass evaluation or independent approval.

## Secret, safety, and configuration rules

- GAP source may declare secret *references* only, using named GSM identifiers. It never contains a secret value, connection string, credential JSON object, private key, bearer value, or copy of a client credential.
- A configuration schema describes non-secret configuration. Secrets are supplied through separately authorised instance secret bindings.
- Required configuration, secret bindings, and credentials are scoped to the instance and organisation. They are never copied into a reusable definition.
- Every package declares criticality, side effects, approval mode, retry/backoff policy, idempotency policy, kill-switch scope, telemetry redaction, retention, SLO, monitoring, maintenance, deployment, and rollback handling.
- The validator must fail safe on credential-shaped content even where JSON Schema cannot express a content scan.

## Provenance and licence rules

Sources may include n8n, Make, Zapier, GitHub, OSS, documentation, and internal material. They are source material, not automatically reusable product code.

Before certification, every reused/adapted source has a locator, exact revision, SHA-256 digest, license record, commercial-use conclusion, review status, and a source-to-target mapping. Unknown, incompatible, or unreviewed licence status is a hard stop. For a commercial product, `commercial_use_clearance` must be `cleared`.

## Evaluation and monitoring rules

Certification needs actual workflow execution in a disposable n8n-plus-mock-services environment. Fixture counts, static JSON checks, and an Architect assertion do not certify a release. Eval evidence binds the exact package/workflow/suite/fixture digests and n8n version.

Every package must define at least a success path and safety coverage suitable to its side effects. A production-capable package must also cover input validation, idempotency when applicable, upstream failure/retry, absent configuration/secret reference, authorization/binding rejection, regression, and privacy/redaction.

The monitoring profile defines how healthy behaviour is recognised and alerted. The maintenance policy may allow bounded actions such as retry or rollback configuration, but workflow logic changes always create a new candidate release that receives independent evaluation.

## Source authority and cutover

The GAP becomes the sole editable workflow authority only after a package conversion passes the cutover rules in ADR 0002. Until then, current `automations/templates/manifest.json` and its listed workflow JSON remain the legacy compatibility authority for the five live governance workflows. A future conversion must never leave one release editable in both places.

## Explicit exclusions

- No runtime catalogue discovery or autonomous selection by consumer Programs.
- No raw secrets, client configurations, or production execution evidence in Git.
- No automatic production workflow rewrites by an Architect, Librarian, evaluator, or maintenance process.
- No extension of v0.1 to a second executable engine without a versioned contract change.
