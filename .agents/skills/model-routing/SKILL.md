---
name: model-routing
description: >-
  Select and spawn the correct IDE Development model-routing subagent for a
  task. Ports LiNKdeveloper packages/model-routing router.ts route criteria and
  escalation pairing so the two systems cannot drift.
version: 1.0.0
status: active
tags: [routing, models, subagents, escalation]
source_of_truth: LiNKdeveloper/packages/model-routing/src/router.ts
---

# Model routing (Cursor Desktop)

IDE Development has no persistent Ledger process. Model routing is enforced by
**pinned custom subagents** under `.cursor/agents/route-*.md` plus this skill's
agent-followed doctrine.

## Subagents (one per route)

| Route ID | Subagent file | Model slug |
|---|---|---|
| `default` | `.cursor/agents/route-default.md` | `claude-sonnet-5-thinking-medium` |
| `escalation` | `.cursor/agents/route-escalation.md` | `gpt-5.6-sol-medium` |
| `independent_review` | `.cursor/agents/route-independent-review.md` | `claude-opus-4-8-thinking-medium` |
| `economical` | `.cursor/agents/route-economical.md` | `composer-2.5` |
| `bulk_documents` | `.cursor/agents/route-bulk-documents.md` | `gemini-2.5-flash` |
| `evaluation` | `.cursor/agents/route-evaluation.md` | `grok-4.5-medium` |

Spawn the matching subagent (Task tool / `/route-*`) rather than doing the work
on an unpinned parent model when a route clearly applies.

## Route selection (criteria verbatim from router.ts)

### default — Sonnet 5 Medium

- normal and complex coding
- feature development
- repository analysis
- debugging with a reasonably clear cause
- refactoring
- testing
- documentation
- PRDs and implementation plans
- research, writing and data analysis that are not unusually consequential
- If no special condition below applies, use this route.

### escalation — GPT-5.6 Sol Medium

- new architecture or major architectural decision
- difficult or ambiguous planning
- requirements conflict or important behavior is undocumented
- intermittent or difficult root-cause investigation
- several major systems or repositories interact
- authentication, payments, migrations, infrastructure, deployment, financial logic or trading logic requires analysis
- the default route has failed after one structured correction
- failure could be serious or difficult to detect
- Should normally analyze and plan first; the default route may implement afterward once the resulting plan is clear and bounded.

### independent_review — Opus 4.8 Medium

- security review
- authorization and authentication review
- final review of consequential changes
- migration, payment, infrastructure or trading-risk review
- independent challenge of an architecture or large implementation
- Run as a SEPARATE review task. The reviewer must receive the original request, approved scope, plan, complete diff, tests and known risks.

### economical — Composer 2.5

ALL must hold (unknown ⇒ not eligible → use default):

- one repository
- an existing implementation pattern can be followed
- normally no more than 3-5 expected changed files
- requirements and expected output are explicit
- no architectural decision is required
- no authentication, authorization, payments, database schema, migration, secrets, infrastructure, deployment, production data or live trading logic
- failure will be obvious
- the result can be verified by an automated test, build, type check, lint check, exact output comparison or similarly objective check
- all changes are easy to revert

### bulk_documents — Gemini 2.5 Flash

- large-volume classification or extraction
- very large document collections
- PDF, image or multimodal classification
- repetitive structured synthesis across many files
- Require a representative sample review before processing the full collection. Never move, rename or delete files based solely on unreviewed classification output.

### evaluation — Grok 4.5 Medium (Fast off)

- Grok is being evaluated, not yet adopted as the default.
- May be used instead of the default route for low- or medium-risk work to compare: verified completion, scope discipline, tests passed, corrections required, usage-pool consumption, unrelated changes.
- Do not use for critical work. Keep Fast off.

## Escalation-on-failure protocol (Principal-approved)

When a route's model fails with a **model-quality** signal
(`code_defect`, `quality_gate_failed`, or a **recurring** `timeout_uncertain`):

1. **Log** the attempt: route id, model slug, failure class/reason, timestamp —
   into the active Issue proof artifact or session note (no silent skip).
2. **Retry once** with the paired different-family route:

| Failed route | Retry route |
|---|---|
| `default` | `escalation` |
| `economical` | `default` |
| `evaluation` | `default` |
| `bulk_documents` | `default` |
| `escalation` | *(none — surface to repair)* |
| `independent_review` | *(none — surface to repair)* |

3. Cap at **one hop**. A second failure surfaces to the Principal / repair —
   do not keep trying models until one works.
4. Infrastructure/input failures (not model-quality) use same-model retry rules
   instead of this pairing table.

This protocol is agent-followed doctrine (IDE Development has no Ledger process
to mechanize it). Skipping the log step or the different-family retry is a
routing violation.
