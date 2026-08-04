# WP-12 legacy-retirement inventory

Dependency searches were completed before retirement. The only retained historical references are archives, the roadmap packet, and this inventory; none are deployable or imported by a supported command.

| Former supported-looking path | Disposition | Dependency result |
| --- | --- | --- |
| `scripts/scaffold-linkdeveloper-templates.mjs` | removed | generated only historical invoke workflow JSON |
| `scripts/scaffold-linksuitegen-templates.mjs` | removed | generated only historical invoke workflow JSON |
| `ops/generate-linksites-n8n-templates.mjs` | removed | generated only historical invoke workflow JSON |
| `ops/sync-templates-from-aios.sh` and `ops/sync-templates-to-aios.sh` | removed | no current CI/package/runtime caller |
| target-specific import/runbook commands | replaced | no command now embeds a host, project, or secret value |
| `automations/templates/archive/**` and `archive/**` | retained | clearly historical, excluded from validator/import/release support |

The former `aios.*` NATS compatibility namespace and mirror subject are removed from current gateway configuration, tests, templates, and documentation. Current events use the versioned `linkautowork.v1.*` namespace only.

Rollback: restoring retired material is prohibited as an operational rollback. Restore the last release manifest, database evidence, and certified workflow export instead.
