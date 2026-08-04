# Archived automation templates

**Archived:** 2026-07-15; retirement boundary strengthened 2026-08-04.
**Reason:** Orphaned / speculative — reference RPCs that were never defined anywhere in this codebase or any sibling Program's applied schema, and serve no current, real Program need.
**Authority:** Principal instruction (2026-07-15): drop the speculative automations that reference undefined RPCs, and keep only what is actually needed to run the real Programs that exist today (LiNKsites, LiNKplatform, LiNKskills, LiNKbrain, LiNKautowork).

These files were moved here with `git mv` (history preserved, not deleted). They are intentionally **not** listed in `automations/templates/manifest.json` and are **not** scanned by `scripts/validate-templates.mjs` (the validator reads only the top-level `automations/templates/` directory, not this subfolder).

This entire directory is unsupported historical evidence. Nothing below it may be imported, activated, published, or used as a production source. In particular, legacy runtime names, routes, environment variables, and invoke handlers recorded here are prohibited from supported surfaces.

## What's here and why

Each archived workflow calls a Supabase RPC through an env var that is **not** part of the gateway env contract (`gateway/src/config/env.ts` defines only `SUPABASE_AUDIT_RPC` → `public.linkautowork_write_audit_run`) and that has **no** matching SQL function in `supabase/migrations/` (the applied `lautowork` schema exposes only `linkautowork_write_audit_run` and the tables `audit_runs`, `lifecycle_transitions`, `killswitch_events`).

| File | Undefined RPC (env var → intended function) | Why orphaned |
|------|---------------------------------------------|--------------|
| `heartbeat-triage.json` | `SUPABASE_HEALTH_RPC` → `linkautowork_health` | "Load Mission Health" node calls a mission-health RPC that was never created; no current Program needs it. |
| `security-exception-response.json` | `SUPABASE_INCIDENT_RPC` → `linkautowork_open_incident` | "Open Incident" node calls an incident-open RPC that was never created; the real scoped kill-switch path it also used is already covered by governed templates. |
| `hot-cold-migration.json` | `SUPABASE_INACTIVE_FILES_RPC` → `linkautowork_find_inactive_files`, `SUPABASE_POINTER_RPC` → `linkautowork_persist_pointer`, `SUPABASE_DELETE_FILE_RPC` → `linkautowork_delete_file` | Hot/cold archival flow depends on three RPCs plus a storage-tiering scheme that do not exist; speculative future ops need, no current Program. |

These are exactly the five orphaned RPCs identified in the audit (`linkautowork_health`, `linkautowork_open_incident`, `linkautowork_find_inactive_files`, `linkautowork_persist_pointer`, `linkautowork_delete_file`), which live across these three template files. An independent sweep of all remaining templates (`grep` for `$env.SUPABASE_*_RPC` and every `url` node) found **no other** templates referencing undefined RPCs or non-existent schema — every other live template targets a real gateway endpoint (`/v1/events/publish`, `/v1/lifecycle/transition`, `/v1/control/killswitch/scoped`) or the real `LINKAIOS_AUTOWORK_INVOKE_URL` invoke handler.

## Restoring

If a real Program need ever materializes, define the backing RPC + schema first (with a dated migration), then `git mv` the template back into `automations/templates/`, add it to `manifest.json`, and re-run `npm run validate:templates`.
