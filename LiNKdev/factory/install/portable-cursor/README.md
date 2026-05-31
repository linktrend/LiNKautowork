# Portable `.cursor/` shim (copy with LiNKdev)

When you copy `LiNKdev/` into a **new** repository, also install this thin `.cursor/` tree at the repo root.

## Install (wire session)

From repo root:

```bash
cp -R LiNKdev/factory/install/portable-cursor/.cursor ./
```

Then add **product-specific** rules under `.cursor/rules/` as `01-*.mdc` … `08-*.mdc` (this LiNKtrend repo is the reference implementation).

## What this shim contains

| Path | Purpose |
|------|---------|
| `rules/00-linkdev-bootstrap.mdc` | Always-on: read `LiNKdev/` first |
| `skills/README.md` | Points to `LiNKdev/skills/` |
| `agents/README.md` | Points to `LiNKdev/factory/agents/` |
| `commands/*.md` | Wire, UI automations, post-UI, Go — each points to `LiNKdev/factory/install/EXECUTE-*.md` |

## What does NOT live here

- Skill bodies → `LiNKdev/skills/`
- Factory rules → `LiNKdev/factory/rules/`
- Product rules → `.cursor/rules/01`–`08` per product (LiNKtrend only in this repo)

Do not copy `mcp.json` from another repo unless you configure secrets locally.
