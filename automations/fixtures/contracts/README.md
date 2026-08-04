# WP-01 contract fixtures

These fixtures are contract inputs for WP-02's standards-compliant JSON Schema validator and LiNKautowork-specific semantic checks. They contain no credentials or secret values.

`package-valid.json` is a schema-valid minimal release manifest. Negative fixtures are intentionally invalid and must be rejected for the named rule in `fixture-matrix.json`. `provenance-unresolved.json` is structurally parseable but intentionally violates the required provenance/licence acceptance policy; WP-02 must reject it without leaking source data.

WP-01 can parse and lint these JSON documents with repository-provided tooling. Actual Draft 2020-12 execution, exact-digest verification, secret-shaped-content scanning, and graph validation belong to WP-02 because this packet is not authorised to add the pinned validator dependency or its test runner.
