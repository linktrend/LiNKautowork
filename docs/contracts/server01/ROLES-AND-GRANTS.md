# Server01 least-privilege roles and grants

Broad `service_role` is **not** a production runtime identity.

| Role | Login | Purpose | Data grants | Mutating RPCs |
|---|---|---|---|---|
| `svc_lautowork_gateway` | nologin | Gateway admission | insert/update invocation, prepared intent, outbox; insert credential-binding refs | `server01_accept_invocation` |
| `svc_lautowork_product_api` | nologin | Product API / operator reads | SELECT on `server01_*`; audited Product API RPC access, no direct audit/table writes | finite audited Product API commands after file 17 |
| `svc_lautowork_runtime_dispatch` | nologin | n8n callback/receipt bridge | insert receipts/callbacks; update intent/outbox | `server01_admit_callback`, `server01_write_receipt` |
| `svc_lautowork_n8n` | nologin | n8n internal schema only | **no** grants on `lautowork.server01_*` | none |
| `svc_observer` | nologin | Read-only operations | SELECT | none |
| `svc_lautowork_migration_backup` | nologin | Platform backup/restore operator | SELECT on `lautowork` tables | `server01_assert_package_ready` (readiness only) |
| `svc_lautowork_runtime` | nologin | Legacy Autowork runtime (predecessor packet) | existing grants plus execute on Server01 RPCs for disposable continuity | accept/callback/receipt |

Organisation isolation uses forced RLS on org-scoped `server01_*` tables: `org_id` must equal `request.jwt.claim.org_id`. Cross-organisation rows are invisible. n8n cannot read Autowork control or Server01 invocation tables.

AW08 file 17 retires `service_role` and `svc_lautowork_runtime` from the Product
API transport namespace. File 18 adds `svc_lautowork_gateway` execute rights on
v2 resolve/accept/callback, active pause, and an org-filtered kill-switch wrapper.
The production gateway accepts only an org-bound dedicated-role JWT and uses a
separate publishable API key. Legacy runtime grants remain historical and are
not the production gateway credential route.
