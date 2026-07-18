# Technology stack

Planner copies this file to `LiNKdev/product/grounding/STACK.md` after Principal OK on the finished-product narrative. Gates read it to decide architecture checks and smoke commands.

## Languages

List primary languages/runtime families (used by `architecture_gate`):

- node/typescript
- python
- go
- rust
- shell

Remove lines that do not apply. `architecture_gate` runs only when `node/typescript`, `javascript`, or `typescript` appears below.

## Package managers

| Tool | Version pin | Notes |
|------|-------------|-------|
| npm | | |
| pnpm | | |
| pip | | |
| poetry | | |

## Key paths

| Area | Path |
|------|------|
| Primary app | |
| API / backend | |
| Shared packages | |
| Tests | |

## Verify commands

Commands LiNKdev gates may invoke (non-zero exit fails the gate):

| Gate | Command | Expected |
|------|---------|----------|
| integration_smoke | `npm run test:smoke` | Exit 0 |
| architecture_gate (JS/TS) | `npm run typecheck` | Exit 0 |

Leave blank or use `N/A` when not applicable; `run-gates.sh` skips commands marked `N/A`.

## Integration smoke

Default command for tier B `integration_smoke` (first non-empty row under Verify commands, or override here):

```bash
# npm run test:smoke
```

## Architecture gate (JS/TS only)

When languages include JS/TS, tier B runs the first matching command:

1. `npm run typecheck`
2. `npm run lint`
3. `npx tsc --noEmit -p tsconfig.json`

Document the canonical command for this repo:

```bash
# npm run typecheck
```

## Notes

- Do not store secrets here; reference env var names only.
- Update when the stack changes materially (new language, new primary test command).
