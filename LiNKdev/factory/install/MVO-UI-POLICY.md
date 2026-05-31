# MVO UI Policy — Operator vs Customer vs Upstream

**Status:** Canonical for MVO UI boundaries (May 2026)  
**Workspace file:** `LiNKtrend-System.code-workspace`  
**Product authority:** `LiNKtrend-System/LiNKdev/product/grounding/UI_AUTHORITY.md`

This document defines **which UI system applies where** in the four-repo workspace. Agents must not apply LiNKaios shell patterns to customer websites or rebuild upstream product UIs inside LiNKaios.

---

## Three UI classes

| Class | Where | Audience | Authority |
|-------|-------|----------|-----------|
| **A — LiNKaios operator UI** | `LiNKtrend-System/LiNKaios/linkaios-web` | Principal, licensee staff, vendor ops | Full shell — see UI_AUTHORITY |
| **B — LinkSites customer UI** | `LiNKsites` templates + published sites | End-customer SMB visitors | Template + vendor model — **not** LiNKaios shell |
| **C — Upstream / kitchen UIs** | Plane, Odoo, n8n, Zulip, Payload admin | Operators via deep links | **Do not rebuild** in LiNKaios |

---

## Class A — LiNKaios operator UI

**Purpose:** Traceability, governance, suite/project visibility, approvals, fleet — not pixel-perfect marketing polish.

**Mandatory patterns:**

- Shell chrome: `ShellMainFrame`, breadcrumbs, `ShellPageHeader`
- Tokens: `LiNKaios/linkaios-web/src/lib/ui-standards.ts`
- Composites: data-table, action-queue, summary-metric-card, forms
- shadcn primitives: `@/components/ui/*`
- Terminology: Suite, Module, Project, Phase, Issue, Assignee, Run, Capability

**Read first:**

- `LiNKdev/product/grounding/UI_AUTHORITY.md`
- `LiNKaios/linkaios-web/docs/ui-system.md`
- `.cursor/rules/08-linkaios-ui-standards.mdc`
- Host skills: `LiNKdev/skills/host/data-table/`, `action-queue/`, `summary-metric-cards/`, `personal-information-forms/`

**MVO dashboard must show:** lead → bot → lease/run → automation → brain event → preview/publish → CRM/Plane status → blockers.

---

## Class B — LinkSites customer UI

**Purpose:** Industry templates (restaurant, clinic, etc.) published to `businessname.linktrend.media`.

**Rules:**

1. **Vendor model, not monorepo import at runtime** — `LiNKsites/packages/ui` holds shared snippets/tokens **copied into templates**; templates do not import the package at runtime per `packages/ui/README.md`.
2. **No LiNKaios shell** — no `ShellMainFrame`, no operator breadcrumbs, no governance tables on customer pages.
3. **Payload CMS admin** is Class C — content editors use Payload; LiNKaios shows publish status and links, not a full CMS rebuild.
4. **Design tokens** may align aesthetically with `@linktrend/ui` primitives vendored into templates; operator chrome stays in Class A only.

**Repo:** `LiNKsites` — `apps/web-master/`, `apps/web-company/`, `apps/cms/`.

---

## Class C — Upstream / kitchen UIs

LiNKaios integrates via **Capabilities** (LinkSkills leases). User-facing LiNKaios copy says **Capability**, not connector.

| Software | UI class | LiNKaios posture |
|----------|----------|------------------|
| **Plane** | Class C | Sync indicator + **Open in Plane** — no full kanban rebuild |
| **Odoo** | Class C | Shadow/mock CRM/accounting — no mirror UI in MVO |
| **n8n (LiNKautowork)** | Class C | Label **Automation** in LiNKaios — not "workflows" in UI |
| **Zulip** | Class C | Stream/topic links — no chat rebuild |
| **Payload admin** | Class C | Publish orchestration visible in LiNKaios; editing in Payload |

---

## Shared package `@linktrend/ui`

| Location | Role |
|----------|------|
| `LiNKtrend-System/packages/ui` | Early shared primitives for LiNKaios-adjacent surfaces; future extraction target |
| `LiNKsites/packages/ui` | Template vendor source — copy into templates |

**Do not** assume one package serves both Class A shell and Class B customer sites without explicit vendoring. See `UI_PACKAGE_EXTRACTION.md` for future `@linktrend/ui` consolidation plan.

---

## LiNKbot-core / OpenClaw UI

OpenClaw gateway, channel plugins, and extension UIs live in **LiNKbot-core**. They are not LiNKaios shell. LiNKaios owns communication profiles, routing, and audit mapping — not a re-skin of Discord/Telegram/etc.

---

## Agent decision tree

```
New UI work?
├─ Operator sees it in LiNKaios Client/Admin → Class A (ui-system + ui-standards)
├─ Public website visitor sees it → Class B (LiNKsites template vendor model)
├─ External product's native UI → Class C (link out; trace in LiNKaios)
└─ Unsure → stop; read UI_AUTHORITY.md before implementing
```

---

## MVO non-goals

- Rebuilding Plane, Odoo, n8n, Zulip, or Payload admin in LiNKaios
- Applying LiNKaios data-table / action-queue patterns to LinkSites marketing pages
- Full design-system polish before functional traceability ships

---

## Workspace settings

See `LiNKtrend-System.code-workspace`. UI policy is documented here and in LiNKtrend-System grounding files — not in workspace JSON.
