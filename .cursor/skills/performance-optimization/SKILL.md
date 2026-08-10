---
name: performance-optimization
description: Diagnose, measure, and improve performance only when there is evidence, a target, or a meaningful risk.
version: 1.0.0
status: active
tags: [performance, profiling, optimization, measurement]
source_adapted_from:
  - addyosmani/agent-skills/skills/performance-optimization
  - link-antigravity-kit/.codex/skills/performance-profiling
---

# Performance Optimization

Use this skill when performance requirements exist or observed behavior is slow, expensive, or resource-heavy.

## Use When

- page load, query, build, or workflow speed matters
- a regression is suspected
- resource usage is excessive
- Core Web Vitals or backend latency are in scope
- a performance-sensitive feature is shipping

## Workflow

1. Define the performance question or target.
2. Measure current behavior.
3. Identify the bottleneck.
4. Make the smallest targeted change.
5. Re-measure.
6. Record before/after evidence.

## Rules

- Do not optimize without a measurement or clear target.
- Do not trade correctness for speed.
- Prefer simple improvements before complex caching or concurrency.
- Avoid speculative abstractions.
- Record performance assumptions separately from verified facts.

## Proof

Useful evidence includes:

- before/after timings
- profiler output
- query plan
- bundle size diff
- lighthouse or browser metric
- load or stress result

## Progressive Disclosure

Read only code and metrics tied to the suspected bottleneck. Broaden investigation only when measurement points elsewhere.
