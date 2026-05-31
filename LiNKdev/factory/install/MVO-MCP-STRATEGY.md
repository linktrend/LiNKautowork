# MVO MCP Strategy — User Plugins + Per-Repo Config

**Status:** Canonical for MVO agent tooling (May 2026)  
**Workspace file:** `LiNKtrend-System.code-workspace`

Model Context Protocol (MCP) servers extend Cursor agents with browser, Supabase, shadcn, Slack, and other integrations. This doc defines **where** MCP is configured and **how** the four-repo workspace uses it without duplicating secrets.

---

## Two-layer model

| Layer | Location | Scope | Purpose |
|-------|----------|-------|---------|
| **User-level Cursor plugins** | Cursor Settings → MCP / installed plugins | All projects on this machine | Shared servers (Supabase, Slack, browser, shadcn registry) authenticated once |
| **Per-repo `mcp.json`** | `<repo>/.cursor/mcp.json` | That repo when opened alone or in workspace | Repo-specific or team-default MCP entries without user-global pollution |

**Rule:** Prefer user-level plugins for credentials and heavy integrations. Use per-repo `mcp.json` for repo-local defaults (e.g. shadcn MCP on LiNKtrend-System only).

---

## Current state (May 2026)

| Repo | `.cursor/mcp.json` | Notes |
|------|------------------|-------|
| **LiNKtrend-System** | Yes — `shadcn` via `npx shadcn@latest mcp` | LiNKaios UI work |
| **LiNKbot-core** | No | Use OpenClaw docs + user plugins as needed |
| **LiNKautowork** | No | Add when n8n/debug MCP is standardized |
| **LiNKsites** | No | Add when Payload/template MCP helpers exist |

Workspace multi-root opens all four folders; MCP servers from **user plugins** apply globally. Per-repo files merge when that folder is the active context — avoid duplicate server names across layers.

---

## Recommended user-level plugins (MVO)

Install via Cursor MCP / marketplace (not committed to git):

| Server | Use for | MVO posture |
|--------|---------|-------------|
| **Supabase** | Schema, migrations, logs, advisors | Required infrastructure |
| **cursor-ide-browser** | LiNKaios UI verification, publish smoke | Dev/staging only |
| **shadcn** | Component registry for `linkaios-web` | Also in System `mcp.json` |
| **Slack** | Optional — studio comms if enabled | Not blocking MVO |

**Never commit:** API keys, service role keys, bot tokens, or GSM secret values in `mcp.json`. Use env vars or Cursor's secret store.

---

## Per-repo `mcp.json` template

```json
{
  "mcpServers": {
    "shadcn": {
      "command": "npx",
      "args": ["shadcn@latest", "mcp"]
    }
  }
}
```

Add repo-specific servers only when:

1. The tool is scoped to that codebase (e.g. custom LiNKautowork workflow linter)
2. The server id does not conflict with a user-level plugin
3. No secrets appear in the committed file

---

## Agent discipline

1. **Read tool schema** before `CallMcpTool` — descriptors live under Cursor's MCP cache for each server.
2. **Supabase:** use for LiNKbrain/kernel schema work; follow `LiNKdev` + `.cursor/rules/03-secrets-security.mdc`.
3. **Browser MCP:** use for operator UI proof, not as a substitute for governed capability leases on side effects.
4. **Cross-repo work:** MCP does not replace git — changes still land via the branch model in `MVO-GITHUB-STRATEGY.md`.

---

## Future standardization

| Item | Target |
|------|--------|
| LiNKautowork `mcp.json` | n8n workflow inspect / dry-run (mock mode) |
| LiNKsites `mcp.json` | Payload collection schema helper |
| Workspace-level MCP | **Not used** — keep user plugins + per-repo files to avoid secret leakage in `Workspaces/` |

---

## Workspace settings

See `LiNKtrend-System.code-workspace`. MCP is not configured at workspace-file level; this document is the authority for MCP layering across the four MVO repos.
