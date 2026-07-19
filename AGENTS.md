# LiNKtrend Development Standards

This file provides universal guidance for any AI agent or IDE working in this repository.
For full rules, see `.cursor/rules/` (Cursor) or `.agent/` (Antigravity).

## Identity

LiNKtrend is an AI-native venture studio. The Principal is the sole human operator (non-technical).
All other roles are AI agents. See `.cursor/rules/00-identity.mdc` for full context.

## Git Workflow (LiNKdev-aligned)

Canonical: `.cursor/rules/01-git-branching.mdc`, `LiNKdev/factory/rules/01-git-branching.mdc`, `LiNKdev/factory/SPEC.md` §8, and `.github/workflows/branch-source-policy.yml`. (Former prose summary archived at `docs/archive/BRANCHING_AND_DEPLOYMENT_POLICY.md`.)

- **Integration branch:** `development` — all agent and ad-hoc work lands here via PR
- **Branch prefixes:** `issue/<id>-<slug>` (LiNKdev issues, LAW-05), `dev/<machine><ide>` (optional ad-hoc)
- **Flow:** `issue/*` or `dev/*` → PR to **`development`** → Integrator merges when merge-ready
- **Promotion:** `development` → `staging` → `main` — **Principal only** (after Release OK)
- No direct pushes to `staging` or `main`
- Conventional commits: `type(scope): summary`
- Forks (`link-*`): modify freely, never push upstream. Upstream sync lands in **`development`**, not `staging`.

## Secrets

- All secrets in Google Secret Manager (GSM)
- Naming: `LINKTREND_[SERVICE]_[ENV]_[RESOURCE]_[IDENTIFIER]`
- Never commit secrets. Use `${ENV_VAR}` placeholders.

## Quality

- TypeScript strict mode. ESLint + Prettier mandatory.
- Tailwind CSS for styling. shadcn/ui for primitives.
- Complete, shippable code only — no placeholders or TODOs.
- All exports require JSDoc.

## Agent Behavior

- **Autonomous execution:** Run terminal commands, tests, and linters yourself; deliver work end-to-end. Do not instruct the Principal to run routine dev commands unless execution is impossible in-session (missing auth, blocked network, policy, or UI-only step). See `.cursor/rules/05-agent-behavior.mdc`.
- Plan before coding (Batch Header: scope, inputs, plan, risks) — then **implement** unless the batch is approval-gated or the user asked for plan-only.
- Small, incremental changes.
- Ask max 3 questions, then proceed with stated assumptions.
- On failure, generate a Briefing Pack (structured 12-section report).
- Communicate in plain English for the non-technical Principal; “next steps” = what you finished + human-only gaps, not a generic todo list for the operator.

## Other LiNKtrend repositories

The canonical **`05-agent-behavior.mdc`** and this **`AGENTS.md`** template are copied across LiNKtrend repos in the operator’s `Projects` tree so Cursor/Codex/Antigravity behave consistently. **New** repos should copy `.cursor/rules/05-agent-behavior.mdc` and `AGENTS.md` from LiNKaios (or any sibling that already has them) before the first agent session.

## Handoff

- Write handoff docs to `docs/handoffs/` when finishing a session.
- Read latest handoff before starting work on a branch.

## Testing

- Unit (Vitest), Integration (Vitest + mock), E2E (Playwright for web).
- Every feature/fix ships with tests. Regression tests for bugs.

## Skills

Canonical skills live under `LiNKdev/skills/` per `LiNKdev/skills/SKILLS_CATALOG.md`. Legacy flat `.cursor/skills/` stubs are not authoritative.
