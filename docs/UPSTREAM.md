# Upstream policy: link-n8n

`link-n8n/` is LiNKtrend's fork of [n8n](https://github.com/n8n-io/n8n). It is a **nested fork boundary** inside LiNKautowork, not a separate product repo.

## Rules

1. **Never push** to `n8n-io/n8n` or any upstream remote you do not own.
2. **Sync upstream** into LiNKautowork's **`development`** branch (or a short-lived branch merged via PR into `development`).
3. Resolve conflicts on **`development`** before promotion to `staging` and `main`.
4. LiNKtrend-specific gateway, templates, and ops scripts live **outside** `link-n8n/` unless explicitly vendored with a documented reason.

## Recommended sync flow

```bash
# From a clean LiNKautowork checkout on development
git fetch upstream   # remote pointing at n8n-io/n8n
git merge upstream/<default-branch>   # or cherry-pick tagged releases
# Fix conflicts, run LiNKautowork gates, open PR into development if not already on it
```

Automate upstream pulls only through governed CI or Principal-approved runbooks. Do not bypass `branch-source-policy.yml` when merging into `development`, `staging`, or `main`.

## Related docs

- Repo README — `link-n8n/` layout
- `.github/workflows/branch-source-policy.yml` — allowed branch prefixes into `development`
- `LiNKdev/factory/SPEC.md` §8 — LiNKdev `issue/*` vs `dev/*` branching
