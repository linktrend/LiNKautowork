---
name: mcp-builder
description: Design and review MCP servers and tool interfaces as optional adapters, not replacements for core artifacts.
version: 1.0.0
status: active
tags: [mcp, tools, adapters, integration]
source_adapted_from:
  - anthropics/skills/skills/mcp-builder
  - link-antigravity-kit/.codex/skills/mcp-builder
---

# MCP Builder

Use this skill when building or reviewing an MCP server, tool adapter, or agent-callable interface.

## Use When

- a workflow needs an agent-callable tool
- a repeated manual operation should become a tool
- external services need structured access
- a verifier or helper should be exposed to agents

## Design Rules

- The MCP server is an adapter, not the source of truth.
- Core doctrine and artifacts must remain usable without MCP.
- Tools should have narrow, explicit inputs and outputs.
- Tool names should describe actions clearly.
- Errors should be structured and actionable.
- Do not expose destructive operations without clear gates.
- Avoid hiding business logic in tools when artifacts should express it.

## Tool Contract Checklist

- purpose
- input schema
- output schema
- side effects
- permissions
- failure modes
- validation strategy

## Proof

Useful evidence includes:

- schema validation
- sample call and response
- error-path test
- permission review
- integration note

## Progressive Disclosure

Read the workflow needing the tool, existing tool conventions, and security constraints. Do not build broad generic tools when a narrow helper is enough.
