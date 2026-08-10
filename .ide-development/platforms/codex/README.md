# Codex platform adapters

Physical skill entrypoints for Codex native discovery under `.agents/skills/`,
plus the managed `AGENTS.md` section template.

## Managed AGENTS section

- `AGENTS.managed-section.md` → root `AGENTS.md` marker upsert (`marker_upsert`)
  Lead integrates; preserve consumer text outside markers.

## Required adapters

Always materialize:

- `skills/agentsetup/SKILL.md` → `.agents/skills/agentsetup/SKILL.md`
- `skills/agentcomply/SKILL.md` → `.agents/skills/agentcomply/SKILL.md`

These skills are self-contained for GitOps bootstrap/compliance. They must not depend on `.cursor` being read.

## Remaining approved skills

`skills-manifest.json` lists the approved repository skills. The installer copies each present package skill source into `.agents/skills/<name>/SKILL.md` when packaging includes that skill under the managed-core `skills/` tree.

Claude Code (`.claude`, root `CLAUDE.md`) is out of scope for v2.
