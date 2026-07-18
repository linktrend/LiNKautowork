---
program_id: linkautowork
title: LiNKautowork execution target
status: execution-target
---

# Program: linkautowork (execution target)

This repository is **not** the canonical LiNKdev program host. Do **not** run Planner here or create a local issue tree.

## Canonical program

| Field | Value |
|-------|-------|
| **Program id** | `linktrend-system` |
| **Host repo** | [LiNKtrend-System](https://github.com/linktrend/LiNKtrend-System) |
| **Path** | `LiNKdev/product/programs/linktrend-system/` |

LiNKautowork work is tracked under **linktrend-system** modules, phases, and issues. Principal **Go** and cloud Planner run against LiNKtrend-System only.

## This repo's role

**Execution target** for the LiNKautowork plane:

- Self-hosted n8n runtime boundary — nested `link-n8n/` fork ([docs/UPSTREAM.md](../../../../docs/UPSTREAM.md))
- Policy gateway, GSM-backed deploy stacks, ops scripts
- Canonical workflow templates — `automations/templates/` (source of truth)

**SDK / contracts** for LiNKaios integration live in LiNKtrend-System at `LiNKautowork/` (gateway, template registry, workflow handles).

Product overview: [README.md](../../../../README.md) at repository root.

Grounding: [MVO_ROLE.md](../../grounding/MVO_ROLE.md)
