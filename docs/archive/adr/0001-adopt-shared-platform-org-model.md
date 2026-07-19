# ADR 0001 — Adopt the Shared `platform` Org Model and Confirm `lautowork_` Schema Isolation

- **Status:** Accepted — migration promoted from `DRAFT_` to a real dated file, `link-n8n` converted to a git submodule (both executed 2026-07-15, see Update below)
- **Date:** 2026-07-15
- **Decided by:** LiNKplatform build sequence step 5 (`LiNKplatform/docs/specs/shared-foundation-spec.md` §10), executed as a LiNKautowork-side retrofit, mirroring the LiNKsites-side retrofit in `LiNKsites/docs/adr/0003-retire-mirror-pattern-and-adopt-shared-platform-org-model.md`
- **Context source:** `LiNKplatform/docs/specs/shared-foundation-spec.md` (§1–4, §10), `LiNKplatform/supabase/migrations/20260714_000001_platform_foundation.sql` (the shared foundation this retrofit depends on), this repo's `ops/sql/001_mvo_schema.sql` (current control/audit schema), `README.md` §"Supabase Schema Standard", `HOW_THIS_PROJECT_WORKS_PLAIN_ENGLISH.md`, `260319 - PRD_ LiNKautowork Automation Engine.md` §2.3, `docs/runbooks/WAVE4_AUTOMATION_PROOF.md`, `docs/UPSTREAM.md`, `docs/DOCUMENTATION_GOVERNANCE.md`

This is LiNKautowork's first ADR. No prior ADR numbering convention exists in this repo (there was no `docs/adr/` directory before this file), so numbering starts at `0001`.

## Update (2026-07-15) — both open verification items closed by the Principal directly

The two open items that kept the migration in `DRAFT_` state are now closed, by direct confirmation rather than by inspecting a live database:

- **The VPS running the n8n container (`linkdroplet-00`, `prod-n8n-1`) was destroyed.** It no longer exists.
- **The Supabase project that VPS's n8n container and `ops/sql/001_mvo_schema.sql` pointed at is the same old, abandoned project the Principal already instructed be disregarded when LiNKsites started fresh on `linkplatform-stage`/`linkplatform-prod`** (see `LiNKsites/docs/adr/0003-…`'s equivalent finding). It holds no data relevant to the new architecture and is out of scope, exactly as it was for LiNKsites.
- **No LiNKautowork-related schema or tables exist in `linkplatform-stage`/`linkplatform-prod`** (confirmed directly by the Principal; no query was run to check this).

This resolves the "elevated uncertainty relative to LiNKsites" the Finding below describes. The draft migration is promoted to a real dated file (`supabase/migrations/20260715_000001_lautowork_control_core.sql`) and `ops/sql/001_mvo_schema.sql` is archived, exactly as originally planned for this close-out. The `link-n8n` submodule conversion (documented as a deliberately-deferred "dedicated pass" below) was also executed in this same update, per the Principal's explicit direction and agreement with the target architecture recommended below.

The Finding, Decisions, and Alternatives below are left as originally written — they're the reasoning that led here, not stale content.

## Context

`LiNKplatform` has shipped the shared cross-Program foundation (`LiNKplatform/supabase/migrations/20260714_000001_platform_foundation.sql`): `platform.organizations`, `platform.org_members`, `platform.capabilities`, `platform.capability_grants`, `platform.handoff_envelopes`, and the `platform.has_org_access(org_id, min_role)` RLS helper. Spec §10 step 5 names LiNKautowork's onboarding: "bring in its repo + `link-n8n`, schema `lautowork_` + isolated `lautowork_n8n_`, apply Harness doctrine." LiNKsites has already completed the equivalent step 2 retrofit (its ADR 0003), which is the worked example this ADR follows.

Three things had to be established before deciding how to retrofit LiNKautowork onto the shared project:

1. whether LiNKautowork's own control/ledger schema is wired into any running application today (the live-vs-dormant question, same rigor as the LiNKsites investigation);
2. how the `link-n8n` fork duplication (an embedded nested git repo inside this tree, plus a near-identical standalone top-level repo) should be resolved;
3. what LiNKautowork's own tenant-scoped concept is, where `org_id` should land, and how its schema naming should be reconciled with spec §3.

## Finding: LiNKautowork's own control/ledger schema is dormant scaffolding, but a live n8n runtime already exists

LiNKautowork's own database surface is defined in exactly one place: `ops/sql/001_mvo_schema.sql`. It declares four schemas — `lautowork_n8n_dev`, `lautowork_n8n_prod` (n8n's own runtime schemas) and `linkautowork_audit`, `linkautowork_control` (LiNKautowork's own control/ledger) — and three control/ledger tables: `linkautowork_audit.audit_runs`, `linkautowork_control.lifecycle_transitions`, `linkautowork_control.killswitch_events`, plus the `public.linkautowork_write_audit_run` RPC.

A repo-wide investigation of how this schema is applied and consumed found:

1. **No automated applier anywhere.** `ops/sql/001_mvo_schema.sql` is referenced only in documentation (`IMPLEMENTATION_AGAINST_PRD.md` §2.3/§6.1). It is **not** applied by CI (`.github/workflows/ci.yml` only validates templates, checks the env contract, lints shell, runs the secret scan, tests, and typecheck — no DB step), **not** applied by any `ops/*.sh` deploy script (`ops/deploy-stack.sh` builds/starts the Docker stack; nothing runs `psql`/`supabase db` against the schema file), and **not** invoked by the gateway at boot. The only scripts that touch a database at all are `ops/run-backup.sh` and `ops/restore-drill.sh` (operator-run backup/restore drills, not schema application).
2. **Only one of the three control tables has a code writer, and it isn't deployed.** `audit_runs` is written via the RPC by `gateway/src/integrations/supabase-rpc.ts` (`writeAudit`). `lifecycle_transitions` and `killswitch_events` have **no writer anywhere in the gateway** — a repo search for inserts/RPC calls against them found only a Prometheus counter named `linkautowork_killswitch_events_total` (`gateway/src/services/metrics.ts`), which is in-memory telemetry, not a DB write. Those two tables are pure forward-looking scaffolding.
3. **The gateway (the only writer) is not deployed.** Per `docs/runbooks/WAVE4_AUTOMATION_PROOF.md` (2026-06-06), the VPS `linkdroplet-00` runs a bare `prod-n8n-1` n8n container only; the LiNKautowork repo is **"not at `/opt/linkautowork` on VPS"**, templates were never rsynced, and even template import was **BLOCKED** (`N8N_PUBLIC_API_DISABLED=true`). If the repo isn't on the VPS, the gateway (built from the repo via `deploy/*/docker-compose.yml`) is not running there, so no live `audit_runs` writes are occurring.
4. **The DB surface is visibly mid-build.** `deploy/prod/.env.example` references five RPCs used by workflow templates — `linkautowork_health`, `linkautowork_open_incident`, `linkautowork_find_inactive_files`, `linkautowork_persist_pointer`, `linkautowork_delete_file` — none of which are defined in `001_mvo_schema.sql`. The control-plane database is partially specified, not a finished, deployed store.

**Conclusion: LiNKautowork's own control/ledger schema (`linkautowork_audit`/`linkautowork_control`) is dormant, unused-in-production scaffolding** — the same category as LiNKsites' `lsites_core`. No deployed writer, no automated apply path, no confirmed live rows.

**Material difference from the LiNKsites case (why the migration ships as `DRAFT_`, not a real dated file):** LiNKsites was able to positively confirm that its old migration *was never applied to any Supabase project* and that no live data existed anywhere, which is what let `20260715_000001_lsites_sites_core.sql` become a real fresh-create migration. LiNKautowork cannot make that same clean assertion yet, for two reasons this investigation surfaced:

- A **live n8n runtime container already exists** on `linkdroplet-00`, and `deploy/prod/.env.example` points n8n at a Supabase pooler host with `DB_POSTGRESDB_SCHEMA=lautowork_n8n_prod`. n8n auto-creates its own internal tables in that schema on first boot against Postgres, so **live n8n operational data very likely already exists in the shared Supabase Postgres** — in n8n's own schema (out of scope for this migration; see Decision 3), but it means the shared database is *not* a clean slate the way LiNKsites' target project was.
- Because a DB connection is out of scope for this task (and forbidden here), it could **not be positively verified** whether `001_mvo_schema.sql` was ever manually applied to the shared Supabase project that n8n is already using. Manual application (`psql -f ops/sql/001_mvo_schema.sql`) is exactly the kind of step an operator could have run once by hand, and it would leave no trace in the repo.

This elevated uncertainty changes the risk calculus relative to LiNKsites. The correct, conservative move — matching the LiNKsites *process* before its dormancy was positively confirmed — is to ship the retrofit as a clearly-marked `DRAFT_`, non-appliable migration, pending a one-time DB-state verification pass (below). If that verification confirms the `lautowork`/`linkautowork_*` control schema is absent or empty in both `linkplatform-stage` and `linkplatform-prod`, the draft is promoted to a real dated `YYYYMMDD_HHMMSS_lautowork_control_core.sql` fresh-create (per this repo's migration-naming standard in `README.md`) exactly as LiNKsites did. If it finds an already-applied `001_mvo_schema.sql` with rows, the draft must be reworked as a data-preserving `ALTER`/rename before it is safe to apply.

## Finding: `link-n8n` — the standalone top-level repo is ahead only in fork-governance plumbing; recommend eventual submodule, documented interim now

Two working copies of LiNKtrend's n8n fork exist:

| | Embedded (`LiNKautowork/link-n8n`) | Standalone (`~/Projects/link-n8n`) |
|---|---|---|
| `origin` | `github.com/linktrend/link-n8n.git` | `github.com/linktrend/link-n8n.git` (same) |
| `upstream` | `github.com/n8n-io/n8n.git` (`no_push`) | **not configured** |
| Branch | `master` | `development` |
| Latest commit | `7192b24e` — **2026-03-31** — "Merge PR #3 … upstream-260331-graph" | `406f1b65` — **2026-05-31** — "docs(fork): record branch reconciliation and default branch" |
| Working tree | dirty: `M AGENTS.md`, `?? .cursor/` | clean |
| Tracked in LiNKautowork git? | **No — `link-n8n/` is gitignored** (`.gitignore` line 12, "Explicit nested fork boundary (managed independently)") | n/a |

The standalone is ~2 months ahead on its `development` branch, but **the delta is entirely fork-governance metadata, not n8n product code.** The three development-only commits touch only: `docs/BRANCH_RECONCILIATION.md` (new, 64 lines — this is the "one extra `docs` folder/file" a prior diff spotted), an updated `docs/UPSTREAM.md`, and `.github/workflows/` fork-policy files (`block-upstream-prs.yml`, `branch-source-policy.yml`, `upstream-sync.yml` replacing `upstream-sync-staging.yml`). Both copies share the same upstream n8n sync point (2026-03-31); the standalone simply also carries LiNKdev-aligned fork CI/branching hygiene and sits on the canonical `development` integration branch.

So the "extra docs folder" (`docs/BRANCH_RECONCILIATION.md` + the updated `UPSTREAM.md`/CI) is **worth keeping but not worth hand-porting**: it is fork-management hygiene that already lives in the canonical standalone repo, not functional n8n code the embedded copy is missing.

**Recommendation (documentation only — no git surgery in this change):**

- **Target architecture: (a) convert the embedded copy into a proper git submodule** pointing at the canonical standalone repo (`github.com/linktrend/link-n8n`, branch `development`), pinned to a specific commit. This is the cleanest long-term shape — one canonical source, referenced not duplicated — and it directly serves spec §10 step 5 ("bring in its repo + `link-n8n`"). It is especially clean here because `link-n8n/` is **already gitignored** in LiNKautowork, so today LiNKautowork tracks *nothing* about the fork; a submodule would replace an untracked, silently-drifting working copy with a pinned, auditable reference. The drift is already real (embedded `master`@2026-03-31 vs standalone `development`@2026-05-31, plus uncommitted edits in the embedded copy), which is exactly the failure mode a submodule prevents.
- **Interim state until that dedicated pass happens: (c) both continue to exist, with the standalone declared authoritative.** `~/Projects/link-n8n` (branch `development`, commit `406f1b65`) is canonical; the embedded `LiNKautowork/link-n8n` is a behind-by-fork-governance working copy that must not be treated as the source of truth. Do not delete either copy and do not treat the embedded copy's `master`/uncommitted state as canonical.
- **Explicitly not now:** converting the embedded nested git repo into a submodule rewrites refs/remotes and deserves a dedicated, careful pass (fetch/verify parity, choose the pinned commit, replace the `.gitignore` boundary with a `.gitmodules` entry, re-run LiNKautowork gates). It is deliberately out of scope for this retrofit and must not happen as a side effect.

## Decision 1 — LiNKautowork's tenant-scoped concept is the managed-automation tenant; `org_id` lands on each control/ledger table directly

LiNKautowork's tenant scoping today is a bare `tenant_id uuid` column on each control/ledger table, referencing nothing (no FK), populated in practice only with the canonical internal tenant `00000000-0000-0000-0000-000000000001` (`linktrend_internal`, per `HOW_THIS_PROJECT_WORKS_PLAIN_ENGLISH.md` §3 and `gateway/src/constants/tenant.ts`). The PRD (§2.3) frames the eventual multi-tenant unit as a **managed-automation client** ("Managed Service (SaaS): high-value n8n workflows hosted on LiNKtrend infrastructure for external clients"; "every client execution must be tagged with a unique `tenant_id`"; "RLS on the `audit_runs` table … so Client A cannot access Client B's metadata").

**Decision: adopt `platform.organizations` as the tenant identity, and replace the bare `tenant_id uuid` with `org_id uuid references platform.organizations(id)` on each of the three control/ledger tables** (`audit_runs`, `lifecycle_transitions`, `killswitch_events`).

Rationale — and why this differs from the LiNKsites split:

- LiNKsites had a real **parent→child hierarchy** (`sites` → `pages`/`articles`/… via `site_id … on delete cascade`), so ADR 0003 correctly put `org_id` on the top-level `sites` table *only* and let children inherit through the existing FK, avoiding a redundant, drift-prone `org_id` on every child.
- LiNKautowork's control tables are the **opposite shape**: three flat, independent, append-only ledger tables with **no parent table and no FK between them**. There is nothing for them to inherit `org_id` *through*. Each row's tenant is only knowable from its own `tenant_id`/`org_id` column today.
- This makes them structurally identical to the shared spec's own worked examples — `platform.capability_grants` and `platform.handoff_envelopes` — which each carry `org_id` directly because they too are top-level tenant-scoped records, not children of a tenant-scoped parent. So `org_id` on each LiNKautowork ledger table is faithful to spec §4, **not** a violation of ADR 0003's "don't repeat `org_id` on children" rule (that rule is about children with an unambiguous FK path to a parent; these tables have neither).
- RLS on each table OR's two independent checks (either sufficient, matching the LiNKsites pattern), adapted to LiNKautowork's *own* existing fast-path mechanism: the JWT tenant claim `current_setting('request.jwt.claim.tenant_id', true)` that the archived `001_mvo_schema.sql` already used, OR'd with a real `platform.has_org_access(org_id, 'client_viewer')` membership check. This widens the *definition of who is allowed in* from a single unverified session/claim value to a real, auditable org-membership check, while keeping the claim path as a scoping convenience.

**Open question (flagged, deliberately not built):** the PRD's "managed automation" unit has no DB-backed registry today — automations live as JSON templates in `automations/templates/` plus a free-text `workflow_id` string on `lifecycle_transitions`. A future `lautowork.managed_automations` registry table (carrying `org_id`, with the ledger tables gaining an FK to it) would give LiNKautowork the same clean top-level-parent shape LiNKsites has. This ADR does **not** create it, because no such registry exists or is concretely specified — building one now would be inventing business logic beyond what the current docs describe. It is recorded here as the natural next structural step whenever a real workflow registry is designed.

## Decision 2 — Consolidate to a single `lautowork_` control schema; ship as `DRAFT_`

Spec §3 assigns LiNKautowork exactly **one** control/ledger schema, `lautowork_`, and **one** logically-isolated n8n schema, `lautowork_n8n_`. The current repo diverges: it uses two control schemas (`linkautowork_audit` + `linkautowork_control`, and with the longer `linkautowork_` prefix, not `lautowork_`) and environment-split n8n schemas (`lautowork_n8n_dev`/`lautowork_n8n_prod`).

**Decision:**

- **Consolidate the control/ledger tables into a single `lautowork` schema** (`lautowork.audit_runs`, `lautowork.lifecycle_transitions`, `lautowork.killswitch_events`), per spec §3's one-schema-per-Program rule. The `audit`-vs-`control` two-schema split predates the shared convention and carries no benefit that a single schema doesn't — they are all LiNKautowork control data under one least-privilege role.
- **Keep the exposed RPC in `public`** as `public.linkautowork_write_audit_run`, repointed to `search_path = lautowork, public`. Spec §3 explicitly allows `public` to hold functions/views meant to be exposed, and keeping the RPC name preserves the deployed gateway's env contract (`SUPABASE_AUDIT_RPC=linkautowork_write_audit_run`). The RPC keeps its wire parameter name `tenant_id` for the same contract-compat reason but writes into the `org_id` column; renaming the wire field to `org_id` is a coordinated gateway change left as an open item, not forced here.
- **Least-privilege runtime role** `svc_lautowork_runtime` (nologin) owning access to the `lautowork` schema, plus a read-only `svc_observer`, matching the role pattern in `LiNKplatform/…/20260714_000001_platform_foundation.sql` and `LiNKsites/…/20260715_000001_lsites_sites_core.sql`.
- **Ship as `DRAFT_lautowork_control_core.sql` (non-appliable)** under `supabase/migrations/`, for the reasons in the Finding above (live n8n runtime already against the shared Postgres + inability to verify prior manual application without a DB connection). Promotion to a real dated migration follows the same path LiNKsites used once dormancy is positively confirmed by the verification step in Consequences.

Environment separation note: under the shared two-project topology (spec §2 / LiNKplatform ADR 0002 — `linkplatform-stage` vs `linkplatform-prod`), env separation lives at the **Supabase-project** level, not the schema level. The target model therefore has a single `lautowork_n8n` schema per project rather than `_dev`/`_prod` schema suffixes in one project. Migrating existing n8n data out of `lautowork_n8n_dev`/`lautowork_n8n_prod` into the new topology is n8n's own concern and is called out as an open provisioning item, not handled by this migration.

## Decision 3 — n8n's internal tables stay isolated in `lautowork_n8n`; LiNKautowork does not hand-design them

n8n manages its own internal schema automatically: on first boot against a Postgres connection string it runs its own migrations and creates its own tables (workflow definitions, executions, credentials, settings, migration bookkeeping) inside whatever schema it is pointed at (`DB_POSTGRESDB_SCHEMA`, currently `lautowork_n8n_dev` in `deploy/dev/docker-compose.yml`).

**Decision: LiNKautowork points n8n at an isolated schema `lautowork_n8n` with its own dedicated least-privilege Postgres role (e.g. `svc_lautowork_n8n`) that can touch only that schema — and creates neither the schema's tables nor the role as part of this control-schema migration.** Provisioning the empty `lautowork_n8n` schema and its owning role is an operational step (documented here and to be scripted in `ops/`), separate from the `lautowork` control migration, so that n8n owns its schema and the control role never does.

Why the isolation boundary is mandatory (not cosmetic):

1. **Upstream-controlled and version-volatile.** n8n's internal schema is defined and migrated by upstream n8n; it changes across n8n releases. Hand-designing or co-locating those tables would fight n8n's own migrations and break on every version bump.
2. **Least-privilege separation.** The n8n DB role must own/DDL its own schema; LiNKautowork's control role (`svc_lautowork_runtime`) must **not** be able to touch n8n's internals, and n8n's role must **not** be able to touch LiNKautowork's audit/control tables. Two schemas + two roles make that a hard Postgres boundary, not a convention.
3. **Audit integrity vs. n8n release cadence.** LiNKautowork's audit/lifecycle/kill-switch ledger is its governance record of truth; it must not be coupled to, lockable by, or migrate-able alongside n8n's operational churn. Logical isolation keeps `lautowork` control data stable regardless of what n8n does inside `lautowork_n8n`.

This is exactly spec §3's "n8n (LiNKautowork's runtime, logically isolated) → `lautowork_n8n_`" line: LiNKautowork's job is to hand n8n an isolated schema and role, then get out of the way.

## Consequences

- LiNKautowork's control/ledger schema moves to a single spec-compliant `lautowork` schema, keyed to real `platform.organizations` identity with `platform.has_org_access()` RLS, while retaining the JWT tenant-claim fast-path as an OR'd scoping convenience.
- No live LiNKautowork *control* data is at risk (dormant scaffolding, no deployed writer), but because a live n8n runtime already uses the shared Postgres and prior manual application of `001_mvo_schema.sql` could not be verified without a DB connection, the migration ships **`DRAFT_` and non-appliable**.
- **Open item (must close before applying):** a one-time DB-state verification against `linkplatform-stage` then `linkplatform-prod` — does a `lautowork`/`linkautowork_audit`/`linkautowork_control` schema already exist, and does `audit_runs` (or the others) hold any rows? If absent/empty → promote the draft to a real dated `YYYYMMDD_HHMMSS_lautowork_control_core.sql` fresh-create and apply stage-first (the LiNKsites path). If present with data → rework as a data-preserving rename/`ALTER` before applying. This is the same close-out gate LiNKsites resolved in its ADR 0003 (2026-07-15).
- **Open item:** `ops/sql/001_mvo_schema.sql` should be archived (per `docs/DOCUMENTATION_GOVERNANCE.md` §Relevance Policy — archive before delete), and `README.md` §"Supabase Schema Standard" + `IMPLEMENTATION_AGAINST_PRD.md` updated to the `lautowork`/`lautowork_n8n` naming, in the same change that promotes the draft to a real migration. Not done in this change so the draft stays purely additive and reviewable.
- **Open item:** the gateway audit wire field (`tenant_id`) → `org_id` rename is a coordinated change across `gateway/src/integrations/supabase-rpc.ts`, `gateway/src/config/env.ts`, and the RPC signature; deferred, not forced by this migration (RPC keeps accepting `tenant_id` on the wire and writes `org_id`).
- **Open item:** provision the empty `lautowork_n8n` schema + `svc_lautowork_n8n` role and repoint `DB_POSTGRESDB_SCHEMA` off the `_dev`/`_prod` split, as a separate operational step under the two-project topology.
- **`link-n8n`:** documented interim (standalone `development` authoritative), with submodule conversion recorded as the target architecture for a dedicated later pass. No git surgery performed.

## Alternatives considered

- **Ship a real dated migration now (like LiNKsites' final state):** rejected for now — LiNKsites earned that by positively confirming nothing was ever applied to any project; LiNKautowork has a live n8n runtime against the shared Postgres and no way to verify prior manual application without a DB connection, so a real-and-applied migration would be premature. The draft becomes a real migration the moment the verification open item is closed.
- **Introduce a `lautowork.managed_automations` parent table now and put `org_id` only there (full LiNKsites-shape parity):** rejected — no such registry exists in the current schema or is concretely specified; creating one would invent business logic. Flagged as the natural future step instead.
- **Keep the two-schema `linkautowork_audit`/`linkautowork_control` split:** rejected — spec §3 assigns one control schema per Program; the split predates the shared convention and adds no value under a single least-privilege role.
- **Keep `tenant_id` only, layering the org check in the application/gateway instead of RLS:** rejected — RLS is the trust boundary Postgres enforces regardless of application bugs; this is the same reasoning LiNKsites' ADR 0003 used to reject an app-layer-only org check.
- **Delete the embedded `link-n8n` and rely on the standalone, or delete the standalone and keep the embedded:** rejected as an action in this change — resolving the duplication is a deliberate submodule pass, not a delete; both copies are preserved and the authoritative one is documented.
- **Convert `link-n8n` to a submodule now:** rejected for this change — it rewrites refs/remotes and must be a dedicated, verified pass, not a side effect of a schema retrofit.

## Update (2026-07-15) — gateway audit-wire open item closed (internal `tenant` → `org` naming)

The Consequences open item — "the gateway audit wire field (`tenant_id`) → `org_id` rename … deferred, not forced by this migration (RPC keeps accepting `tenant_id` on the wire and writes `org_id`)" — is now closed as a **TypeScript-only clarity change on the gateway side**. No SQL signature was changed and no database connection was made; the change only aligns internal gateway naming with the already-applied migration's data reality (`org_id` column, FK to `platform.organizations`).

### The internal-vs-wire split, verified against the real RPC

`supabase/migrations/20260715_000001_lautowork_control_core.sql` declares the RPC with the SQL parameter literally named `tenant_id uuid`, inserting it into `lautowork.audit_runs.org_id`. PostgREST maps a JSON request body's keys onto the RPC's named parameters, so **the key sent on the wire must remain `tenant_id`** until a separate, coordinated RPC signature change is made (exactly the change this ADR deferred). Therefore:

- **Internal TypeScript concept → `orgId`.** The value the gateway writes is an organization id (it lands in `org_id`), so the internal representation should say so. `AuditRecord.tenant_id` was renamed to `AuditRecord.orgId`.
- **Outbound audit wire → still `tenant_id`.** `SupabaseAuditClient.writeAudit` now maps `orgId` → a `tenant_id` body key at the exact call site, with an inline comment explaining the deliberate mismatch, so a future reader is not misled into "fixing" it and breaking the RPC call.

This confirms the ADR's stated plan (internal names reflect the org reality; wire param name stays for backward compatibility). It matched what the real code needed.

### One deviation from the ADR's literal file list, flagged explicitly

The Consequences item named the coordinated change as spanning `gateway/src/integrations/supabase-rpc.ts`, `gateway/src/config/env.ts`, and the RPC signature. On inspecting the actual code, **the audit-write value does not flow through `env.ts`** — `AuditService.writeRunAudit` sources it from the inbound `mission.tenantId`, not from env config. Two consequences of that finding:

- **`env.ts` identifiers were not renamed.** `ACTIVE_TENANT_UUID` / `ACTIVE_TENANT_SLUG` are **external deployment env-var names** (present in `deploy/{dev,prod}/.env.example`, consumed via docker-compose `env_file`). Renaming them is an ops-coordinated deployment change, not a TypeScript-only cleanup, so they are kept and a clarifying comment was added noting the value is the active organization identity. (`SUPABASE_AUDIT_RPC` likewise unchanged — the RPC name is preserved by design.)
- **The inbound `missionEnvelopeSchema.tenantId` was not renamed.** That is a separate wire contract with the gateway's callers (LiNKaios), which this ADR did not scope and which cannot be changed unilaterally. The gateway maps that inbound value to the org concept at the audit boundary (`orgId: mission.tenantId`).

Net: the only external contract names retained are (1) the RPC wire param `tenant_id`, (2) the inbound mission field `tenantId`, and (3) the `ACTIVE_TENANT_*` env-var names. Everything genuinely internal now says `org`. The pure-internal constants file `gateway/src/constants/tenant.ts` was renamed to `gateway/src/constants/org.ts` with `CANONICAL_INTERNAL_ORG_UUID` / `INTERNAL_ORG_SLUG`; the canonical internal-org UUID **value** `00000000-0000-0000-0000-000000000001` is unchanged (renaming the value would be a behavioral change, not a naming cleanup).

Still deferred (unchanged by this update): the actual RPC signature rename, the inbound mission-contract rename, and the `ACTIVE_TENANT_*` env-var rename — each requires cross-service or ops coordination beyond a gateway-local TypeScript change.
