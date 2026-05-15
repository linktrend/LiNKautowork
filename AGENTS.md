# LiNKtrend Development Standards

This file provides universal guidance for any AI agent or IDE working in this repository.
For full rules, see `.cursor/rules/` (Cursor) or `.agent/` (Antigravity).

## Identity

LiNKtrend is an AI-native venture studio. The Chairman is the sole human operator (non-technical).
All other roles are AI agents. See `.cursor/rules/00-identity.mdc` for full context.

## Git Workflow (SOP v2)

- Branch format: `dev/<machine><ide>` (e.g., `dev/minicodex`)
- Flow: `dev/*` → PR to `staging` → PR to `main`
- No direct pushes to `staging` or `main`
- Conventional commits: `type(scope): summary`
- Forks (`link-*`): modify freely, never push upstream. Upstream sync lands in `staging`.

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

- **Autonomous execution:** Run terminal commands, tests, and linters yourself; deliver work end-to-end. Do not instruct the Chairman to run routine dev commands unless execution is impossible in-session (missing auth, blocked network, policy, or UI-only step). See `.cursor/rules/05-agent-behavior.mdc`.
- Plan before coding (Batch Header: scope, inputs, plan, risks) — then **implement** unless the batch is approval-gated or the user asked for plan-only.
- Small, incremental changes.
- Ask max 3 questions, then proceed with stated assumptions.
- On failure, generate a Briefing Pack (structured 12-section report).
- Communicate in plain English for the non-technical Chairman; “next steps” = what you finished + human-only gaps, not a generic todo list for the operator.

## Other LiNKtrend repositories

The canonical **`05-agent-behavior.mdc`** and this **`AGENTS.md`** template are copied across LiNKtrend repos in the operator’s `Projects` tree so Cursor/Codex/Antigravity behave consistently. **New** repos should copy `.cursor/rules/05-agent-behavior.mdc` and `AGENTS.md` from LiNKaios (or any sibling that already has them) before the first agent session.

## Handoff

- Write handoff docs to `docs/handoffs/` when finishing a session.
- Read latest handoff before starting work on a branch.

## Testing

- Unit (Vitest), Integration (Vitest + mock), E2E (Playwright for web).
- Every feature/fix ships with tests. Regression tests for bugs.

## Skills

This repo includes skills in `.cursor/skills/`, `.agent/skills/`, and `.codex/skills/`.
Skills are loaded automatically based on task context.
