# LiNKdev automations — **deprecated (optional legacy)**

**Dispatch v2** replaces Cursor/Codex Automations UI as the control plane. Use:

- [../docs/DISPATCH.md](../docs/DISPATCH.md) — canonical trigger matrix
- `.github/workflows/linkdev-dispatch.yml` — GitHub Actions + Cursor Cloud Agents API
- [../EXECUTE-LINKDEV-DISPATCH-INSTALL.md](../EXECUTE-LINKDEV-DISPATCH-INSTALL.md) — wire Step B

GitHub labels and `STATE.md` are unchanged. Agents do not message each other directly.

## Legacy UI folders (optional)

| Folder | Status |
|--------|--------|
| [cursor/README.md](cursor/README.md) | Deprecated — optional if Automations UI is still used locally |
| [codex/README.md](codex/README.md) | Future Codex dispatch; not wired in v1 |

## Trigger matrix (dispatch v2)

| Role | Labels / event | Runtime |
|------|----------------|---------|
| Orchestrator | Merge to `development` | Cursor (Actions) |
| Reviewer | `linkdev:review-ready` | Cursor (Actions) |
| Integrator | `linkdev:merge-ready` | Cursor (Actions) |
| Executor | `linkdev:ready` + `runtime:cursor` | Cursor (Actions) |
| Executor | `linkdev:ready` + `runtime:codex` | Future |

## Benchmark hook (DS-B11)

```bash
LiNKdev/factory/scripts/replay-merge-verify.sh <program-id>
```

## Proof

See [../EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md](../EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md).
