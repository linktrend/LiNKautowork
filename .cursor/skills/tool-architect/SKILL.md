---
name: tool-architect
description: Design small CLI-first helper tools or scripts that agents can run safely and verify.
version: 1.0.0
status: active
tags: [tools, cli, scripts, automation]
source_adapted_from:
  - LiNKskills/skills/tool-architect
---

# Tool Architect

Use this skill when a repeated or deterministic operation should be made into a small local tool or script.

## Use When

- agents repeatedly perform the same mechanical checks
- a verifier would reduce mistakes
- data transformation should be deterministic
- a workflow needs structured output

## Design Rules

- Prefer CLI-first tools.
- Keep tools small and single-purpose.
- Use structured output when agents must consume results.
- Include `--help` or clear usage instructions.
- Avoid interactive prompts unless explicitly needed.
- Make dry-run mode available for risky operations.
- Tests or sample invocations should prove the tool works.

## Tool Spec

- purpose
- inputs
- outputs
- side effects
- failure modes
- examples
- verification command

## Proof

Useful evidence includes:

- script test
- sample run output
- invalid-input behavior
- docs or usage note

## Progressive Disclosure

Read the workflow and existing scripts before creating a new tool. Do not create tools for one-off work unless the risk justifies it.
