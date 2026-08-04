# WP-12 VPS Deployment Input Register

Every item needs a named owner, value/reference, and explicit authorisation before deployment. `placeholder` is not permission to invent a value.

| Input | Stage | Prod | State | Owner/authority |
| --- | --- | --- | --- | --- |
| VPS provider, host, sizing, OS, region | placeholder | placeholder | requires_authorisation | Principal |
| SSH/Tailscale ownership and operator CIDR | placeholder | placeholder | requires_authorisation | Principal/Operations |
| private/public DNS, Traefik route, TLS resolver | placeholder | placeholder | requires_authorisation | DNS/TLS authority |
| Supabase project | `linkplatform-stage` | `linkplatform-prod` | known names; apply authority missing | Platform data owner |
| GSM project/service identity/IAM | placeholder | placeholder | requires_authorisation | GSM owner |
| Platform auth issuer/audience/JWKS/roles | placeholder | placeholder | requires_authorisation | Platform auth owner |
| payment provider/account/legal pricing | placeholder | placeholder | requires_authorisation | Principal |
| Slack/email alert recipients | placeholder | placeholder | requires_authorisation | Principal/Operations |
| storage/backup target, RPO/RTO approval | placeholder | placeholder | requires_authorisation | Principal |
| retention/deletion policy | placeholder | placeholder | requires_authorisation | Principal/privacy authority |

## GSM migration template (names only)

| Legacy name | New name | Environment | Action |
| --- | --- | --- | --- |
| `<OLD_HMAC_SECRET_NAME>` | `LINKAUTOWORK_LINK_HMAC_SHARED_SECRETS_<ENV>` | `<ENV>` | map only; do not read/copy |
| `<OLD_SERVICE_TOKENS_NAME>` | `LINKAUTOWORK_LINK_SERVICE_TOKENS_<ENV>` | `<ENV>` | map only; do not read/copy |
| `<OLD_DB_PASSWORD_NAME>` | `LINKAUTOWORK_SUPABASE_DB_PASSWORD_<ENV>` | `<ENV>` | map only; do not read/copy |
| `<OLD_N8N_API_KEY_NAME>` | `LINKAUTOWORK_N8N_API_KEY_<ENV>` | `<ENV>` | map only; do not read/copy |
| `<OLD_PLATFORM_KEY_NAME>` | `LINKAUTOWORK_SUPABASE_SERVICE_ROLE_KEY_<ENV>` | `<ENV>` | map only; do not read/copy |

No secret value, target project, or migration action is contained in this repository.
