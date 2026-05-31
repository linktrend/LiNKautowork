# Workspace MCP strategy

Model Context Protocol (MCP) setup for LiNKtrend **MVO workspace** repos, aligned with LiNKdev wire and host-repo ownership. MCP extends agent tooling — it does not replace LiNKdev roles, LinkSkills capability leases, or governed side effects.

## Principles

1. **Host repo owns MCP config** — each product repo documents its `.cursor/mcp.json` (or IDE equivalent) locally; LiNKdev factory does not ship secrets or repo-specific server URLs in the template.
2. **Secrets stay out of git** — API keys and tokens live in GSM, local env, or IDE secret stores. Use env var references in MCP config where supported.
3. **MCP assists; governance gates side effects** — sending email, publishing sites, CRM writes, and production deploys still require LinkSkills leases, LiNKautowork runs, and LiNKbrain audit per MVO contracts.
4. **Prefer read/discovery tools in planning** — use MCP for docs lookup, component registries, and schema inspection; implement changes in the repo with normal verify/review flow.

## Recommended servers by repo

| Repo | Typical MCP servers | Notes |
|------|---------------------|-------|
| **LiNKtrend-System** | shadcn, Supabase | Operator UI components; schema/migrations via Supabase MCP in dev |
| **LiNKsites** | shadcn | Payload/template UI; Supabase if shared brain schema access is wired |
| **LiNKautowork** | — (minimal) | Workflow JSON and n8n gateway; avoid production n8n MCP unless lease-governed |
| **LiNKbot-core** | — (upstream OpenClaw policy) | Follow OpenClaw host/plugin MCP conventions; no LiNKtrend secrets in fork |

Add Slack or other comms MCP only when an issue explicitly requires governed messaging integration.

## Cursor workspace layout

When all four MVO repos are open in one Cursor workspace:

- Each repo may have its own `.cursor/mcp.json` — Cursor merges enabled servers per workspace rules.
- Enable only servers relevant to the **active issue’s repo** to reduce token noise and accidental cross-repo side effects.
- LiNKdev bootstrap (`.cursor/rules/00-linkdev-bootstrap.mdc`) still routes agents through `LiNKdev/AGENTS.md` and the active issue `read_first` — MCP does not bypass progressive disclosure.

## Wire checklist (per host repo)

During or after LiNKdev wire:

- [ ] Document enabled MCP servers in host grounding or `STACK.md` (names only — no secrets)
- [ ] `.cursor/mcp.json` uses env placeholders for tokens (e.g. `${SUPABASE_ACCESS_TOKEN}`)
- [ ] `.env.example` lists required MCP-related env var **names**
- [ ] Agents on UI issues know shadcn MCP is optional — host `08-*` UI rule and `ui-standards.ts` remain authoritative for operator shell

## shadcn MCP (operator UI repos)

For LiNKaios-style hosts:

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

Use for discovering/installing primitives into the host app. **Do not** bypass host component families (`data-table`, `action-queue`, etc.) documented in `LiNKdev/skills/host/` and the host `08-*` rule.

## Supabase MCP (LiNKtrend-System)

Use for local/linked project schema inspection, migration guidance, and advisors — not as a substitute for committed migrations in the repo. Production changes follow repo migration discipline and Principal approval.

Authenticate via Supabase CLI or plugin auth flow; never commit service role keys to MCP config files.

## Security

- No production credentials in MCP JSON committed to git.
- Rotate tokens if accidentally exposed.
- MCP tools that mutate external systems must align with `LiNKdev/factory/laws/LINKDEV_LAWS.md` and host capability contracts before use in executor work.

## Related docs

- GitHub / branch policy: `LiNKdev/factory/install/WORKSPACE-GITHUB.md`
- UI authority: `LiNKdev/product/grounding/UI_AUTHORITY.template.md`
- Skills: `LiNKdev/skills/host/README.md`, `LiNKdev/factory/install/SKILLS-ALLOWLIST.md`
