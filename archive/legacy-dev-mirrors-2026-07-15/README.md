# Legacy Dev-System Mirrors (archived 2026-07-15)

Pre-LiNKdeveloper per-repo mirrors: `.agent/`, `.codex/` (skill/agent mirrors
predating the shared `IDE Development` LiNKdeveloper system), and `LiNKdev/`
(the older shared-dev-system install pattern, superseded by the `.cursor`
symlink wiring below).

This repo's `.cursor/` is now a symlink to `/Users/linktrend/Projects/IDE
Development/.cursor` (see `scripts/wire-repo.sh` in that repo), which is the
single source of truth for rules/skills/agents/commands across every wired
repo. These mirrors are redundant with that and were archived, not deleted,
to preserve history.
