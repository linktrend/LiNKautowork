# Wave 3 commercial snapshot and webhook correction

## Scope completed

- Added the governed publication read model and immutable order snapshot in migration `20260804_000011_lautowork_governed_commercial_webhooks.sql`.
- Added exact snapshotted terms acceptance and certified release/digest binding through subscription and provisioning.
- Added ordered, signed, allow-listed provider webhook persistence and explicit payment/provisioning lifecycle transitions.
- Updated only the Product API/web signup paths required to carry the durable contract.
- Added disposable PostgREST HTTP webhook proof and evidence `C-W3-10-COMMERCIAL-SNAPSHOT-WEBHOOK.md`.

## Validation

Passing: Product API/web/root typechecks, test-file esbuild syntax checks, shell syntax checks, `git diff --check`, and Docker Compose config parsing. Focused non-listening web tests pass.

Blocked by the CLI sandbox: Product API and web HTTP tests cannot bind loopback listeners (`listen EPERM`), and the durable DB/browser verifier cannot start because Docker access to `/Users/linktrend/.docker/run/docker.sock` is denied. Rerun the evidence command set on a Docker-enabled host.

No provider, payment account, credentials, live service, deployment, commit, or push was used.
