# GAP v0.1 migration inventory

**Status:** WP-01 inventory only. No workflow has been converted, moved, imported, activated, or retired by this document.

Every conversion preserves runtime behaviour first. A functional rewrite, new trigger, data change, credential change, or external integration change is a separate candidate release with separate evaluation evidence.

| Current top-level file | Current manifest workflow ID | Current state | Disposition | Required conversion evidence |
|---|---|---|---|---|
| `ritual-gates-unified.json` | `ritual-gates-unified` | `ops_approved` | Conversion candidate | Byte hash, schedule/Slack/event/gateway behaviour inventory, timezone evidence, synthetic and stage-safe eval plan. |
| `urgent-event-ingestion.json` | `urgent-event-ingestion` | `ops_approved` | Conversion candidate | Byte hash, signed ingress/input contract inventory, dirty-data scenarios mapped into executable cases, idempotency and rejected-input coverage. |
| `promotion-review-governance.json` | `promotion-review-governance` | `ops_approved` | Conversion candidate | Byte hash, protected lifecycle approval/transition behaviour inventory, non-destructive approval fixtures, persistence evidence. |
| `restore-authorization-governance.json` | `restore-authorization-governance` | `ops_approved` | Conversion candidate | Byte hash, restore and scoped kill-switch behaviour inventory, no-live-restore test harness, rollback/approval evaluation. |
| `daily-chairman-briefing.json` | `daily-chairman-briefing-legacy` | `deprecated` | Deprecated; retain traceability only | Record package/legacy replacement relation to `ritual-gates-unified`; do not create new bindings or instances. |

### Already archived top-level material

Files under `automations/templates/archive/` are outside the five-entry live manifest. They are not candidates for accidental reactivation. `security-exception-response.json`, `heartbeat-triage.json`, and `hot-cold-migration.json` require a new approved product brief, licence/provenance review where relevant, and a fresh GAP candidate before any future reuse.

### Legacy LiNKaios material

The archived legacy Program shells are retired historical evidence. They must not be migrated, regenerated, called, or used as a source of runtime contracts. A later legacy-removal packet may remove obsolete generators and stale documentation after an explicit repository-wide inventory; that cleanup is not part of WP-01.
