# Principal launch — LiNKdev wire (three messages total)

You only send **one line** per step. Agents read the full prompt from `LiNKdev/factory/install/` and run autonomously.

| Step | Agent | You say (copy exactly) |
|------|--------|-------------------------|
| **A** | Cursor | `Execute the EXECUTE-WIRE-LINKDEV.md prompt in LiNKdev/factory/install/` |
| **B** | Cursor | `Execute the EXECUTE-LINKDEV-DISPATCH-INSTALL.md prompt in LiNKdev/factory/install/` |
| **C** | Cursor (after B) | `Execute the EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md prompt in LiNKdev/factory/install/` |

**Manual (Principal, once per repo):** GitHub → Settings → Secrets → Actions → add **`CURSOR_API_KEY`** (from Cursor Dashboard → API Keys). Agents cannot set this for you.

**Go** (program start) is a separate fourth message later — only when you intend to run the product program. Use the `linkdev-go` Cursor command or say **Go** per SPEC.

Do not walk through the checklist yourself. Do not answer agent questions unless an agent reports a **blocker** it cannot fix.

## Prompt files (for reference)

| File | Owner |
|------|--------|
| [EXECUTE-WIRE-LINKDEV.md](EXECUTE-WIRE-LINKDEV.md) | Cursor — wire §0–3, §6–7, copy workflows |
| [EXECUTE-LINKDEV-DISPATCH-INSTALL.md](EXECUTE-LINKDEV-DISPATCH-INSTALL.md) | Cursor — dispatch secret + workflow verify |
| [EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md](EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md) | Cursor — §9 + wire complete |

## Deprecated (do not use for new wire)

| File | Use instead |
|------|-------------|
| [EXECUTE-LINKDEV-UI-AUTOMATIONS.md](EXECUTE-LINKDEV-UI-AUTOMATIONS.md) | [EXECUTE-LINKDEV-DISPATCH-INSTALL.md](EXECUTE-LINKDEV-DISPATCH-INSTALL.md) |
| [EXECUTE-WIRE-LINKDEV-POST-UI.md](EXECUTE-WIRE-LINKDEV-POST-UI.md) | [EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md](EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md) |

See [../docs/DISPATCH.md](../docs/DISPATCH.md).
