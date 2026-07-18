# Host skills

Skills for **this repository only**. Virgin LiNKdev template ships this folder **empty** (except this README).

Add skills when this product needs stack- or domain-specific guidance not covered by `../gstack/`.

On conflict with gstack: **host wins** (see `LiNKdev/factory/install/SKILLS-ALLOWLIST.md`).

## Operator UI (wire from reference host)

When the host repo includes **operator shell UI**, copy these skills from a reference host (on `development`) into `LiNKdev/skills/host/` during wire:

| Skill | Purpose |
|-------|---------|
| `data-table/` | Family A — columnar HTML `<table>` surfaces |
| `action-queue/` | Family B — feed-style attention rows |
| `summary-metric-cards/` | Dashboard stat / stream tiles |
| `personal-information-forms/` | Name, address, phone, email field groups and validation |

Also copy supporting skills as needed: `frontend-design`, `web-design-guidelines`, `nextjs-react-expert`, `lint-and-validate`.

Each skill body references **this host repo’s** component paths and token module — not portable factory paths. After copy, grep-replace any stale absolute paths from the source host.

Document filled paths in `LiNKdev/product/grounding/UI_AUTHORITY.md` (from `UI_AUTHORITY.template.md`).

## Customer UI (separate)

Customer-facing surfaces use their own templates and design rules in the customer repo or suite. Do not assume operator UI skills apply to published sites.

## Non-UI hosts

Repos without operator web UI (e.g. pure workflow or bot runtime repos) may leave `host/` empty or add domain skills only (`deployment-procedures`, `api-patterns`, etc.).
