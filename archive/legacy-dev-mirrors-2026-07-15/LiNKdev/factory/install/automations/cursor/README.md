# Cursor automations — **deprecated (optional legacy)**

Dispatch v2 uses **GitHub Actions** and the **Cursor Cloud Agents API**, not the Cursor Automations UI.

**Use instead:** [../../docs/DISPATCH.md](../../docs/DISPATCH.md), [../../install/EXECUTE-LINKDEV-DISPATCH-INSTALL.md](../../install/EXECUTE-LINKDEV-DISPATCH-INSTALL.md).

---

## Legacy UI setup (optional)

If you still maintain Cursor Automations manually, role prompts live in `LiNKdev/factory/prompts/*/ROLE.md`. Triggers must match [../../contracts/labels.md](../../contracts/labels.md). UI automations cannot enforce **AND** labels on issues (`linkdev:ready` + `runtime:cursor`) — dispatch workflows can.

Do not store API keys or automation exports with secrets in this folder.
