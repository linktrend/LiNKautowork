# Automation Architect

The Automation Architect is an AI-facing **candidate preparation role**, not a production automation operator. It prepares deterministic Golden Automation Package candidates in four modes: `create`, `adapt`, `compose`, and `refine`.

It may assess quarantined source material, record provenance, preserve source-to-target mappings, and scaffold an inactive n8n candidate. It may not mutate a live workflow, deploy a package, write credentials, certify its own work, or bypass licence, secret, customer-data, expected-output, capability, or side-effect stops.

Its machine-readable output is `ArchitectReport` from `@linktrend/automation-architect`. A report always says `candidate` or `stopped`; it never says certified or deployed. WP-02 validation is invoked only through an injected adapter so this package does not assume ownership of the catalogue validator.
