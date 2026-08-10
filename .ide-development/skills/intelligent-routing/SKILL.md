---
name: intelligent-routing
description: Select trigger, hybrid skill, domain skill, command, artifact path, and agent role for a task.
version: 2.0.0
status: active
tags: [routing, skills, commands, agents, hybrid, triggers]
source_adapted_from:
  - link-antigravity-kit/.codex/skills/intelligent-routing
  - docs/HYBRID-SKILLS-REGISTRY.md
  - docs/archive (historical EXECUTOR_ROUTING_POLICY reference; no absolute host paths)
---

# Intelligent Routing

Use this skill when deciding how the system should handle a request. Carlos uses three triggers only; agents pick routes inside them.

## Routing order

1. **Identify Carlos's plain-language trigger** — new idea, PRD in hand, or existing software / release-sized increment. See `docs/IDE-DEVELOPMENT-OPERATIONS-MANUAL.md`.
2. **For application Programs** — prefer `run-application-pipeline` / `resume-application-pipeline` and the six fixed Modules (`.cursor/execution/APPLICATION-PIPELINE.md`). Do not invent open domain Modules.
3. **Select Module composite skills** under `.cursor/runtime/skills/linktrend/` plus vendored gstack/mattpocock skills. Registry: `docs/HYBRID-SKILLS-REGISTRY.md`.
4. **Select domain skills** — IDE Development core locals from `SKILLS_CATALOG.md` when hybrid does not cover the concern (APIs, UI, etc.).
5. **Atomic maintenance** — one-file bug fixes use issue proof/review/integration without a full six-Module rerun.
6. **Select agent roles** as resources, not as the control structure.
7. **Select a model-routing subagent** when the task matches a route in `.cursor/skills/model-routing/SKILL.md` (ports LiNKdeveloper `router.ts`). Spawn `.cursor/agents/route-*` rather than running unpinned.
8. **Load only required artifacts** — progressive disclosure (Law 19).

## Trigger → pipeline / hybrid routes

### New idea → Module 1 then fixed pipeline

1. Start `run-application-pipeline` (Module 1: interview hard gates → Intent → Technical PRD → your approval).
2. Composite: `linktrend/module1-intake-and-definition` (grill-with-docs + gstack spec + to-spec).
3. **Stop for Carlos approval** — Module 1 gate before Module 2.
4. Continue Modules 2–6 with fail-closed validator calls.

### PRD / draft in hand → Module 1 then fixed pipeline

1. Enter Module 1 with the draft as input; run analysis/prioritization/Intent confirms; author Technical PRD.
2. **Stop for Carlos approval**.
3. Continue Modules 2–6.

### Existing software / release-sized increment

1. Release-sized work: `run-application-pipeline` or `resume-application-pipeline`.
2. Atomic bugfix: issue → proof → review → integration; fold into next Module 4–6 evidence.
3. gstack `/health`, `/ship` remain subordinate to pipeline gates and never authorize deploy from Module 6 alone.

## Hybrid command index

**gstack (macro)** — vendored under `.cursor/runtime/skills/gstack/`:

- Spec — `hybrid-spec` → `.cursor/runtime/skills/gstack/spec/SKILL.md`
- CEO plan review — `hybrid-plan-ceo-review` → `.cursor/runtime/skills/gstack/plan-ceo-review/SKILL.md`
- Health — `hybrid-health` → `.cursor/runtime/skills/gstack/health/SKILL.md`
- Ship — `hybrid-ship` → `.cursor/runtime/skills/gstack/ship/SKILL.md`
- Context save/restore — `hybrid-context-save`, `hybrid-context-restore` → `.cursor/runtime/skills/gstack/context-save/SKILL.md`, `context-restore/SKILL.md`

**mattpocock skills (micro)** — vendored under `.cursor/runtime/skills/mattpocock/`:

- Clarify PRD — `hybrid-grill` → `.cursor/runtime/skills/mattpocock/grill-with-docs/SKILL.md`
- PRD synthesis — `hybrid-to-prd` → `.cursor/runtime/skills/mattpocock/to-spec/SKILL.md`
- Issue slicing — `hybrid-to-issues` → `.cursor/runtime/skills/mattpocock/to-tickets/SKILL.md`
- TDD — `hybrid-tdd` → `.cursor/runtime/skills/mattpocock/tdd/SKILL.md`
- Debugging — `hybrid-diagnosing-bugs` → `.cursor/runtime/skills/mattpocock/diagnosing-bugs/SKILL.md`
- Architecture improve — `hybrid-improve-architecture` → `.cursor/runtime/skills/mattpocock/improve-codebase-architecture/SKILL.md`

## Domain skill shortcuts

After hybrid selection, prefer the smallest domain skill:

- UI → `frontend-ui-engineering`
- API → `api-patterns`
- Data → `database-design`
- Deploy execute → `deployment-procedures` (ship *decision* → gstack `/ship`)
- Browser flows → `webapp-testing`
- Criterion QA → `persistent-qa`
- Scaffold LiNKtrend app → `app-builder`
- Read order → `context-engineering`
- Review a PR / change / patch → `code-review-and-quality` (distinct from gstack `/plan-ceo-review`, which is executive-level plan review, not patch review)
- Bug report ("I found a bug", something broke) → mattpocock `/diagnosing-bugs`; if severity or scope is unclear, treat as Trigger 3 assess first
- Security concern (auth, secrets, input handling, trust boundary) → `security-and-hardening`

## Internal artifact commands (decomposition required)

Use only when the work graph exists or the task fits a bounded gate path:

- ambiguous greenfield after spec: `plan-program`
- module decomposition: `plan-module`
- tiny bounded fix: `small-change`
- ready issue: `execute-issue`
- evidence check: `review-issue`
- accepted work: `integrate-issue`
- recursive module: `complete-module`

## Validation and repair routing (reference)

Failed validation must not silently retry. Per archived Stage 2 reference `EXECUTOR_ROUTING_POLICY.md` (see `docs/ARCHIVE-INDEX.md`) and `VALIDATION-CONTRACT.md`:

- Reject progression when handoff cannot be validated.
- Record ambiguity or failure in artifacts.
- On validation failure during review, return to execution or create a repair issue with `depends_on` the failing proof — see `VALIDATION-CONTRACT.md` Remaining Ambiguity Rule and Stage 2 repair routing (reference only; no LiNKdev runtime dependency).

## Rules

- Do not over-plan trivial work — `small-change` may suffice under Trigger 3.
- Do not skip proof, review, or integration for speed.
- Do not choose multiple overlapping skills when one is enough.
- Do not treat specialist agents as sequence drivers.
- gstack `/ship` and macro QA do not override core integration gates.
- Record blockers when routing cannot proceed.

## Output

- Carlos trigger (1, 2, or 3)
- selected hybrid command(s) if any
- selected domain skill(s) if any
- selected core command if any
- active artifact level
- required reads
- reason for route

## Progressive disclosure

Read `docs/HYBRID-SKILLS-REGISTRY.md` and this catalog's overlap section first. Stop once the correct route is clear.
