# Upstream policy: link-n8n

`link-n8n` is LiNKtrend's **separate** fork of [n8n](https://github.com/n8n-io/n8n) (`https://github.com/linktrend/link-n8n`). LiNKautowork references it as a git submodule for developer access and future custom builds — it does **not** embed n8n product source as its own codebase.

## Runtime decision (2026-07-18)

| Surface | Location |
|---------|----------|
| Gateway, templates, deploy, ops | **This repo** (LiNKautowork) |
| n8n engine fork (customize / upstream sync) | **Separate repo** `link-n8n` (submodule pin) |
| **What Compose runs today** | Pinned stock image `docker.n8n.io/n8nio/n8n:2.30.0` (matches fork sync point) |

**Why stock image for MVO:** industry practice is not to run an unpublished fork image until the fork has required customizations. Pinning a version (never `:latest`) keeps deploys reproducible. When LiNKtrend needs fork-specific changes, build/push an image from `link-n8n` to a private registry and point Compose at that tag — keep the separate-repo model.

## Rules

1. **Never push** to `n8n-io/n8n` or any upstream remote you do not own.
2. Sync upstream **inside the `link-n8n` repo** on its `development` branch.
3. After syncing the fork, bump the Compose pin (or switch to a fork-built image tag) in this repo in the same change.
4. Canonical workflow templates remain in `automations/templates/` — not inside `link-n8n`.

## Related

- [README.md](../README.md)
- `.github/workflows/branch-source-policy.yml`
- `docs/BRANCHING_AND_DEPLOYMENT_POLICY.md`
