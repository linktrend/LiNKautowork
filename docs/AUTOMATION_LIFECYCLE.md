# Automation Lifecycle

## Source of Truth

`automations/templates/` is authoritative.

- LiNKautowork templates are canonical.
- AIOS workflow files are mirror copies only.
- `automations/live/dev` and `automations/live/prod` contain exported evidence of deployed runtime state.

## Lifecycle State Machine

`draft -> dev_tested -> qa_approved -> ops_approved -> prod_deployed -> deprecated -> archived`

Promotion requirements:

1. `qa_approved`: Auditor recommendation + Head of Quality approval.
2. `ops_approved`: Auditor + Head of Quality + COO approval.
3. Protected actions (promotion/restore decisions): Principal approval required.

## Operational Ritual Alignment (Asia/Taipei)

One unified scheduler template publishes gate outputs at:

- `08:00` Strategic Gate feed.
- `10:45` Operational Gate (COO operational pulse) feed.
- `14:45` Quality Gate feed.

Each gate output publishes to Slack + NATS + canonical audit path.

If source data is degraded, output still ships on schedule with explicit confidence flag.
