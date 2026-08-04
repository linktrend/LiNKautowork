# LiNKautowork Production Work-Pack Index

This index is the execution map for the production roadmap. Each linked packet is self-contained and must be read in full by its implementation agent.

| Wave | Packet | Title | Primary dependency | Parallel lane |
|---|---|---|---|---|
| 1 | [WP-01](./work-packets/WP-01-PRODUCT-CONTRACT.md) | Product contract and Golden Package specification | Approved roadmap | Contract freeze |
| 1 | [WP-02](./work-packets/WP-02-CATALOG-VALIDATOR.md) | Catalogue, publisher, and validator | WP-01 | Catalogue |
| 1 | [WP-03](./work-packets/WP-03-AUTOMATION-ARCHITECT.md) | Automation Architect create/adapt/compose/refine tooling | WP-01 | Authoring |
| 1 | [WP-04](./work-packets/WP-04-CONTROL-DATA-MODEL.md) | Definition, version, instance, binding, and provisioning data model | WP-01 | Data |
| 2 | [WP-05](./work-packets/WP-05-INSTANCE-RUNTIME.md) | Instance lifecycle, n8n provisioner, and linked invocation | Wave 1 | Runtime |
| 2 | [WP-06](./work-packets/WP-06-EVAL-TELEMETRY.md) | Eval runner, execution receipts, and telemetry | Wave 1 | Evidence |
| 2 | [WP-07](./work-packets/WP-07-LIBRARIAN.md) | Institutional Librarian automation mode | WP-05, WP-06 | Curation |
| 2 | [WP-08](./work-packets/WP-08-MONITOR-MAINTAIN.md) | Monitoring, incidents, maintenance, canary, and rollback | WP-05, WP-06 | Operations |
| 3 | [WP-09](./work-packets/WP-09-PRODUCT-API.md) | Organisation-scoped product/operator API and auth boundary | Wave 2 | API |
| 3 | [WP-10](./work-packets/WP-10-OPERATOR-CONSOLE.md) | Internal operator dashboard | WP-09 contracts | Operator UI |
| 3 | [WP-11](./work-packets/WP-11-CLIENT-PRODUCT.md) | Public website, signup, provisioning, and client portal | WP-09, WP-05 | Client UI |
| 3 | [WP-12](./work-packets/WP-12-RELEASE-READINESS.md) | Security, legacy retirement, deployment packaging, and final proof | WP-09–WP-11 | Release |

## Shared execution rules

- Never use live production data or secret values in tests.
- Do not apply migrations to stage or production during pre-VPS waves.
- Every functional change requires automated tests and JSDoc for exports.
- Preserve unrelated work and stop on overlapping ownership.
- Use `org_id`/`orgId` internally; compatibility `tenant*` names must be isolated and documented.
- Every packet produces exact commands, results, changed-file inventory, risks, and rollback notes.
- A packet is not complete because its agent says it is complete. Acceptance evidence and the wave audit decide.
