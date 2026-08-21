# Cursor platform adapters

Physical Cursor discovery surfaces sourced from the installed managed core.

## Materialization

`materialization-manifest.json` maps package-relative sources to consumer destinations under:

- `.cursor/rules/`
- `.cursor/commands/`
- `.cursor/skills/`

Files are physical copies (no checkout-to-checkout symlinks).

## Non-skill loader (ISS-04)

`skills-loader.mjs` plus `skills-lock.json` are the Cursor retrieval surface.
They are not skills. Physical `.cursor/skills/<name>/SKILL.md` copies stay
until dual-app proof authorizes removal.

## Required entrypoints

- Rules: managed bootstrap + branching
- Commands: `agentsetup`, `agentcomply`
- Skills: `agentsetup`, `agentcomply`

Approved remaining skills follow the same destination pattern as Codex (`skills/<name>/SKILL.md` inside the package → `.cursor/skills/<name>/SKILL.md`) per the materialization manifest.
