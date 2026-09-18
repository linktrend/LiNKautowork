# Deployment handoff (source 1.0 → separate Server01 agent)

This is a **non-secret receipt**, not a live install grant. The Server01
deployment agent must bind to the **exact tagged main candidate**, not to an
issue branch and not to the stale `v1.0.0` tag.

Machine-readable contract: [`TAGGED-MAIN-CANDIDATE.json`](./TAGGED-MAIN-CANDIDATE.json).

## Do not install these refs

| Ref | Why |
|---|---|
| `v1.0.0` (`88330d2e…` / peeled `7e76a5e77306d42cdcfd4fd59f22473235c7e7fc`, tree `44e85044d16c9a3a6fad5f7e95e607ca0e027358`) | Older object; not the 1.0 engineering line |
| `origin/main` at admission (`2e30109acfb9510cd77e49f759648b2b6a666adc`) | Bootstrap promote; missing AW-01–07 source |
| `origin/staging` at admission (`96267009bfa6dc55921484a2294f74709224940b`) | Not the 1.0 engineering SHA |
| `issue/165-*`, `issue/166-*`, `cursor/*` | Work branches; not protected main |

## Required bind (after packager + controller + Principal promotion)

1. Phase Packager opens the Phase PR; delivery controller merges this line to `development`.
2. Controller/Principal promote `development` → `staging` → `main`.
3. An **annotated tag** is created on that `main` tip (name is a Principal/controller
   choice; suggested `v1.0.1` or a replacement `v1.0.0` **only after** moving or
   deleting the stale tag — this packet does not retag).
4. Server01 agent verifies:

```bash
git fetch origin tag "$TAG"
test "$(git rev-parse "$TAG^{}")" = "$(git rev-parse origin/main)"
# tree must equal git rev-parse origin/main^{tree}
# hosted LiNKautowork CI must be success on that peeled SHA
```

5. The peeled tree must include this handoff directory so the installer has
   the same non-secret procedure. Engineering tests were proven on
   `20f3d4cc03445ca443e31c41f22d34347c866acf` /
   `95bec98a0d65ca30889e595a7bcaa85ddfe52b47`.

Until steps 1–4 exist, exit **HOLD**. Do not substitute `development`.

## Source artifacts to copy onto Server01 (after bind)

- Repository: `https://github.com/linktrend/LiNKautowork`
- Checkout: `/srv/linktrend/deploy/linkautowork/releases/<peeled-commit>`
- Pointers: `current` → that release; keep `previous` until acceptance
- Compose: `deploy/prod/docker-compose.yml` project `linkautowork-prod`
- Names-only env: `deploy/prod/.env.example`
- Runtime env (GSM-rendered, **not in git**): `/srv/linktrend/runtime/linkautowork/*.env.runtime` mode `0600`
- Migration package: `docs/contracts/server01/MIGRATION-PACKAGE.json` (`lautowork.server01.migration-identity/1.0.0`) — **Platform apply**
- Private routes only: `deploy/templates/traefik-dynamic.yml.example`, `deploy/templates/tailscale-boundary.env.example`
- Image/Dockerfile pins: [`IMAGE-CONFIG-MIGRATION-REFERENCES.json`](./IMAGE-CONFIG-MIGRATION-REFERENCES.json)
- Helper (still dry-run until AW-08 authority): `ops/deploy-stack.sh prod --dry-run --print-release-layout`

Engineering CI on the product SHA:
https://github.com/linktrend/LiNKautowork/actions/runs/34955615212

## AW-08 must still do (all HOLD in this packet)

1. Confirm the tag/main/tree bind above; refuse stale `v1.0.0`.
2. Record host image IDs/digests into `deploy/prod/release-identity.json` **on the host evidence path** (do not commit secrets).
3. Render runtime env from GSM to mode-`0600` files outside git (`ops/render-runtime-env-from-gsm.sh`).
4. Platform-apply the ordered SQL package and persist `lautowork.server01_live_fingerprint()`.
5. Create least-privilege DB grants for `svc_lautowork_*` (see `docs/contracts/server01/ROLES-AND-GRANTS.md`).
6. Install an inactive stack; do not publish `4222`, `8222`, `5678`, `8080` on the host.
7. Import the technical fixture inactive; activate one canary only with explicit founder/Platform authority.
8. Run `ops/verify-server01-acceptance.sh --environment prod` on the host.
9. Prove backup/isolated restore (`ops/restore-drill.sh`) and application rollback to `previous`.

## Explicitly not authorised by issue 166

Live Server01, Platform, provider, credential, database, Docker, protected-branch
merge, tagging, or production actions. Public DNS/TLS, Slack/email, payments, and
Program business automations remain later expansion unless separately approved.
Implementers do not open or merge PRs.
