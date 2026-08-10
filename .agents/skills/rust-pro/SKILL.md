---
name: rust-pro
description: Apply practical Rust ownership, error handling, testing, async, and crate organization patterns.
version: 1.0.0
status: active
tags: [rust, systems, testing, cli]
source_adapted_from:
  - link-antigravity-kit/.agent/skills/rust-pro
---

# Rust Pro

Use this skill when writing or reviewing Rust code.

## Rules

- Follow existing crate structure and formatting.
- Prefer clear ownership over premature abstraction.
- Use typed errors where callers need to act.
- Avoid unnecessary cloning in hot paths.
- Keep unsafe code isolated and justified.
- Add tests for behavior and edge cases.

## Checklist

- `cargo fmt` passes
- `cargo test` or focused tests pass
- errors are meaningful
- public APIs are documented when needed
- feature flags and dependencies are intentional

## Proof

Useful evidence includes:

- `cargo test`
- `cargo fmt --check`
- `cargo clippy`
- sample CLI run
- benchmark or profiling result when performance is in scope

## Progressive Disclosure

Read the affected crate, nearby modules, and tests. Do not restructure crates without an explicit architecture issue.
