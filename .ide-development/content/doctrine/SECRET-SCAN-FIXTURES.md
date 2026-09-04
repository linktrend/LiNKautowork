# Fixture-aware secret scanning

**Status:** Active for `v2.4.0` Update 10.
**Scanner:** `scripts/gitops/secret_scan.py`
**Migration helper:** `scripts/gitops/secret_scan_migrate.py`
**Declaration:** `.github/linktrend-secret-scan-fixtures.json`
**Schemas:** `core/managed-core/schemas/secret-scan-fixtures.schema.json`,
`core/managed-core/schemas/secret-scan-result.schema.json`,
`core/managed-core/schemas/change-scoped-secret-scan.schema.json`

Managed Fast and Full execute `python3 scripts/gitops/secret_scan.py` over
every tracked regular blob. The candidate tree is computed from git index
object identities (`ls-files -s`) so directory symlinks, gitlinks, and
option-like paths are not followed. Suffix classes are never skipped.
Text is decoded as UTF-8 or UTF-16 (LE/BE, BOM or heuristic). Undecodable
or oversized blobs and repository-scanner timeouts are aggregated typed
failures, not silent ignores.

A synthetic value may pass only through an exact versioned non-production
declaration bound to repository path, line and field, content digest, and
optional `bytes` that must equal the detected value when present. The
declaration file itself is scanned, including `bytes` and notes; a
declaration cannot approve or suppress credentials found in its own
contents.

## Synthetic namespace

Approves only values in the `ltfx.` namespace. Realistic GitHub, cloud,
`sk-*`, database, private-key, and high-entropy token formats cannot be
approved, even if declared, including unquoted env/YAML assignments and
escaped or concatenated quoted forms. Negative detector coverage for those
realistic forms must use runtime-generated isolated temp-repo vectors (or
equivalent in-test assembly) so the factory tree never stores an approvable
realistic credential.

## Result kinds

One run reports every finding and fixture error together:

- `credential_finding`
- `approved_synthetic_fixture`
- `stale_fixture_declaration`
- `fixture_scope_violation`

One-byte changes, stale digests, renamed files, duplicated values, duplicate fixture ids,
unknown rules, undeclared fixtures, and candidate-tree or scanner-policy drift fail
closed until the declaration is intentionally refreshed and reviewed.

## Large-fork change-scoped evidence

Large forks may pass `--baseline-evidence <json>` to reuse inherited findings.
Reuse is permitted only when the evidence binds the exact repository,
authoritative remote ref, baseline commit/tree, candidate commit/tree, scanner
policy version, explicit managed scanner/policy path set, and configuration
digest. The scanner computes `changed paths ∪ managed paths`; unchanged
findings are inherited only from that exact baseline and are never treated as
proof for changed, deleted, renamed, or ambiguous paths. Missing or stale
identity, policy/path/config mismatch, unreadable relevant text, and real
credentials block. Source checkouts and extracted `.ide-development` packages
resolve their own managed path layout; there is no broad upstream-path ignore.

### Transactional managed upgrades

A managed-upgrade resolution may include `verification.changeScopedSecretScan`
with the complete evidence object and its canonical `sha256:` digest. The
installer validates that binding before writing anything, then supplies the
evidence to the installed scanner through a private temporary file during
post-install verification. The scanner still evaluates changed paths plus all
managed scanner/policy paths, while only unchanged findings from the exact
baseline evidence are inherited. A missing, stale, malformed, or timed-out
scoped run aborts and rolls back the transaction. Resolutions without this
binding deliberately retain the full-repository scan.

## Repository-owned scanners

`.github/linktrend-repository-secret-scanners.json` may name additional
scanners such as GitHub secret scanning, CodeQL, or gitleaks. They remain
additive and blocking. The managed fixture mechanism cannot suppress them.

## Migration helper

`python3 scripts/gitops/secret_scan_migrate.py --repo .` identifies likely
synthetic candidates only. It never writes an approval and never auto-approve.
