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

The canonical **`05-agent-behavior.mdc`** and this **`AGENTS.md`** template are copied across LiNKtrend repos in the operator’s `Projects` tree so Cursor/Codex/Antigravity behave consistently. **New** repos should copy `.cursor/rules/05-agent-behavior.mdc` and `AGENTS.md` from a current sibling repository before the first agent session.

## Handoff

- Write handoff docs to `docs/handoffs/` when finishing a session.
- Read latest handoff before starting work on a branch.

## Testing

- Unit (Vitest), Integration (Vitest + mock), E2E (Playwright for web).
- Every feature/fix ships with tests. Regression tests for bugs.

## Skills

Canonical skills live under `LiNKdev/skills/` per `LiNKdev/skills/SKILLS_CATALOG.md`. Legacy flat `.cursor/skills/` stubs are not authoritative.

<!-- BEGIN LINKTREND-IDE-MANAGED -->
## LiNKtrend IDE-managed GitOps (do not edit between markers)

This section is maintained by LiNKtrend wire/sync tooling (do not edit between markers).
Consumer-specific guidance may live **outside** these markers.

### Session entrypoints (all platforms)

- **New coding session:** follow agentsetup — create/reuse the GitHub issue and `issue/<n>-<slug>` automatically via `python3 scripts/gitops/create_issue_branch.py`. Never ask humans for issue id/slug.
- **Already-open / wrong branch:** follow agentcomply — migrate dirty work onto the correct `issue/*` branch for this repo.
- Cursor: `/agentsetup` and `/agentcomply` map to `.cursor/commands/agentsetup.md` and `.cursor/commands/agentcomply.md` (skills under `.cursor/skills/`).
- Codex / ChatGPT Work Agents: use this root `AGENTS.md` managed section plus the same scripts; do not require the IDE Development checkout path.

### Lifecycle

- Work on `issue/<n>-<slug>` (or `dev/*`) → push → Packager opens draft PR → Integrator merges to `development`.
- Promote: `development` → `staging` → `main` via temporary `promote/*` PRs only.

### Agent rules

- Ship = checkpoint (commit+push). Packager opens PRs. Max 3 ordinary repairs.
- Completion: `python3 scripts/gitops/completion_gate.py` (checkpoint | review-ready | blocked | status | write-evidence).
- Finished work runs appropriate tests/checks, auto-repairs ordinary failures with at most 3 bounded repair cycles, writes machine-readable evidence with `completion_gate.py write-evidence`, then calls `completion_gate.py review-ready`.
- `review-ready` is the authoritative fail-closed gate. Production publish **and withdraw** of **Linktrend Review Ready** is GitHub App only (trusted `linktrend-review-ready-publisher` workflow with `action=publish` or `action=withdraw` when local privileged credentials are unavailable). Do not publish or withdraw with a user PAT / Carlos restricted identity / `GITHUB_TOKEN` fallback. Do not call `mark-review-ready.sh` as a pre-gate publisher; it is only a compatibility wrapper that requires evidence and delegates to the gate. `clear-review-ready.sh` fails closed without App credentials and prints the App-backed withdraw route.
- Do **not** create or use `.linktrend/review-ready.json` (commit status only — see `core/github/REVIEW-READY.md`).
- If completion cannot pass, call `completion_gate.py blocked`. `.linktrend/completion-blocker.json` is only a **local cache**. The durable cross-machine record is the GitHub repair issue created/updated by the gate (when authenticated repo resolution succeeds). Do not claim durable registration if the command reports `durableRecord=false`.
- Repair tasks: `python3 scripts/gitops/repair_task.py` (upsert | dispatch-attempt | resolve | list).
- No prefer-incoming. No Cursor spawn claims from GitHub Actions.

### Consumer workflow / check configuration

Static `workflow_run.workflows` names are rendered at install time from the committed consumer config:

`.github/linktrend-gitops-consumer.json`

Fields: `ciWorkflowName`, `branchPolicyWorkflowName`, `bugbotCheckName`, and optional `runnerType` (`github-hosted` by default or `linktrend-private-macos-arm64` for trusted managed jobs in approved private repositories).

Repository Actions **variables** still configure required **check/job display names** for gates:

- `LINKTREND_INTEGRATOR_REQUIRED_CHECKS`
- `LINKTREND_STAGING_GATE_CHECKS` / `LINKTREND_RELEASE_GATE_CHECKS`

Do not confuse the two: workflow wake names come from the JSON config; gate check names come from Actions variables.

See `docs/GITOPS-CONSUMER-ROLLOUT.md` when present in the system repo.
<!-- END LINKTREND-IDE-MANAGED -->

