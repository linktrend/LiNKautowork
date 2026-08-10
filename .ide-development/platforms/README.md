# Platform adapter sources

This directory holds managed adapter sources for native discovery surfaces.

Wave 1 layout (adapter bodies owned by WP3):

```text
platforms/
  README.md                      # this file (layout contract)
  AGENTS.managed-section.md      # managed AGENTS.md marker block source
  codex/
    README.md
    skills-manifest.json
    skills/<name>/SKILL.md
  cursor/
    README.md
    materialization-manifest.json
    rules/
    commands/
    skills/
```

Hard rules:

- physical destination files only (no absolute/external symlinks)
- Codex discovery must not depend on `.cursor`
- no Claude / `.claude` adapters
- every emitted path must appear in the package manifest with hashes
