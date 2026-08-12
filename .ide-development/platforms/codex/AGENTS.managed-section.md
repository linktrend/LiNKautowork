<!-- BEGIN LINKTREND-IDE-MANAGED -->
## LiNKtrend IDE-managed development system (do not edit between markers)

This section is maintained by LiNKtrend install/sync tooling. Repository-owned guidance may live **outside** these markers.

Installed managed core: **`.ide-development/`** (versioned package; treat as read-only except via the official installer).

### Session entrypoints

- **New coding session:** follow **agentsetup** — create/reuse the GitHub issue and `issue/<n>-<slug>` via `python3 scripts/gitops/create_issue_branch.py`. Never ask humans for issue id/slug.
- **Already-open / wrong branch:** follow **agentcomply** — migrate dirty work onto the correct `issue/*` branch for this repo.
- **Codex / ChatGPT Work Agents:** use this root `AGENTS.md` managed section and physical `.agents/skills/<name>/SKILL.md`. Do **not** require `.cursor` to be loaded.
- **Cursor:** use physical `.cursor/commands/agentsetup.md` / `agentcomply.md` and `.cursor/skills/`.

### Lifecycle

- Work on `issue/<n>-<slug>` (or rare `dev/*`) → push checkpoint → Packager opens draft PR → Integrator merges to `development`.
- Promote: `development` → `staging` → `main` via temporary `promote/*` PRs only.

### Agent rules

- Ship = checkpoint (commit + push). Packager opens PRs. Max 3 ordinary repairs.
- Completion: `python3 scripts/gitops/completion_gate.py` (`checkpoint` | `review-ready` | `blocked` | `status` | `write-evidence`).
- Finished work: run appropriate tests/checks, auto-repair ordinary failures (≤3 cycles), `write-evidence`, then `review-ready`.
- `review-ready` validates evidence then publishes **Linktrend Review Ready** only via the privileged normal-token path (or fails closed with normal-token dispatch diagnostics). Do not call `mark-review-ready.sh` as a pre-gate publisher.
- If completion cannot pass, call `completion_gate.py blocked`.
- Hard stops: no implementer PR, no self-merge, no self-review, no staging/main promotion, no prefer-incoming.

### Deeper doctrine

When needed, open files under `.ide-development/` (and local `docs/` / `scripts/` already installed). Prefer progressive disclosure; do not scan the entire package.
<!-- END LINKTREND-IDE-MANAGED -->
