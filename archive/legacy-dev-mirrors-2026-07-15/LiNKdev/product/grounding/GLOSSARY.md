# Glossary — LiNKautowork

Short terms for this execution-target repo. Platform-wide vocabulary: LiNKtrend-System `docs/terminology.md`.

| Term | Meaning |
|------|---------|
| **Principal** | Sole human authority; approves protected actions and promotion to staging/main |
| **Project** | Tenant live work instance in LiNKaios (legacy code may still say `missionId`) |
| **Phase** | Stage group inside a LiNKaios module |
| **Issue** | Atomic governed task with input/output contracts |
| **Assignee** | LiNKbot, **Automation** (LiNKautowork), or Human on an issue |
| **Run** | One pass through project modules (maps to Plane Cycle when synced) |
| **Automation** | User-facing label for LiNKautowork deterministic workflow execution |
| **Capability** | Governed integration to external software (LinkSkills lease) |
| **Template** | Canonical n8n workflow JSON under `automations/templates/` |
| **Gateway** | Policy ingress layer in `gateway/` — not the System SDK gateway package |
| **SDK surface** | `LiNKtrend-System/LiNKautowork/` — workflow handles LiNKaios invokes |
| **link-n8n** | Nested n8n fork; independent upstream boundary |
| **Execution target** | This repo runs workflows; program tracking lives in LiNKtrend-System |
| **GSM** | Google Secret Manager — authoritative secret store |
| **Audit RPC** | `public.linkautowork_write_audit_run` via Supabase |
| **Kill switch** | Scoped or global workflow stop — gateway enforced |
