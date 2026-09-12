# Server01 operations — JetStream observability and recovery

Owner: LiNKtrend Platform
Last updated: 2026-09-11
Status: source rehearsal only. This runbook does **not** authorise a live Server01, NATS/JetStream, n8n, GSM, backup, restore, or deployment action.

## What this runbook covers

LiNKautowork publishes `linkautowork.v1.*` events onto persistent JetStream. AW-06 adds a **snapshot-only** observer so operators can:

1. Derive consumer lag, ack-pending, replica, and connectivity health from a redacted snapshot.
2. Open or recover organisation-bound alerts (`jetstream-unavailable`, `jetstream-lag`, `jetstream-lag-critical`, `jetstream-stale`, `jetstream-replica`).
3. Receive a **non-executing** recovery plan (`observe`, `recreate_consumer`, `replay_from_ack_floor`, `fail_closed`).
4. Rehearse backup artifact hashes and restore archive structure locally.

A healthy gateway HTTP process is not evidence that JetStream consumers are caught up.

## Snapshot contract

Use `deriveJetStreamHealth` / `JetStreamOperations.observe` with an injected snapshot. Required redacted fields:

- cluster: `orgId`, `observedAt`, `connected`
- stream: `name`, `available`, `replicaHealthy`, `lastSeq`, `consumerCount`, `subjects` (names only)
- consumer: `stream`, `consumer`, `lastStreamSeq`, `deliveredStreamSeq`, `numPending`, `numAckPending`, `lastActivityAt`

Lag is `max(0, lastStreamSeq - deliveredStreamSeq)`. Consumer staleness is `observedAt - lastActivityAt`, not the HTTP request clock, so an intentionally older redacted snapshot is not stale merely because observation ran later.

Default thresholds (not production SLO claims):

| Signal | Warning | Critical |
|---|---|---|
| consumer lag | 100 | 1_000 |
| ack pending | 50 | 500 |
| last activity | older than 60s | disconnected / missing stream |

Do not put payloads, credentials, or raw NATS objects into snapshots or incidents.

## Alert routing

Prometheus rules live in `ops/alerts/prometheus-rules.yml` under `linkautowork-jetstream`. They describe **snapshot metric names** (`linkautowork_jetstream_connected`, `linkautowork_jetstream_consumer_lag`, `linkautowork_jetstream_ack_pending`, `linkautowork_jetstream_replica_healthy`, `linkautowork_jetstream_consumer_stale`). Those series are a source contract for a future adapter.

**HOLD — live metrics adapter:** this packet does **not** install Prometheus, Alertmanager, Grafana, a NATS exporter, or any other OSS metrics stack. There is no immutable scrape config, preservation/provenance record, reproducibility pin, or rollback evidence for a live metrics installation. Do not claim those rules are firing in production. Replica and lag remain separate routing keys (`jetstream-replica` vs `jetstream-lag` / `jetstream-lag-critical`).

Until an authorised adapter is wired, prove alerts with the in-process observer tests. Alert adapters are local fakes. Do not select Slack/email recipients here.

## Recovery (plan only)

| Health | Plan kind | Operator meaning | Must not do |
|---|---|---|---|
| healthy / mild lag / ack-pending warning | `observe` | Repeat the snapshot on the maintenance interval; lag alerts stay on the consumer | Recreate consumers |
| replica-only degradation (zero lag) | `observe` | Keep the replica warning on the stream; do not open a lag incident | Treat replica as lag or replay |
| connected empty stream set | `observe` | Classify `unknown`; no lag or replica incidents | Invent missing-stream unavailability |
| stale consumer | `recreate_consumer` | Plan a durable recreate with the same name and ack floor | Reset stream sequence |
| critical lag / ack pending | `replay_from_ack_floor` | Plan a bounded replay from the stored ack floor | Delete the stream |
| disconnected / missing stream | `fail_closed` | Stop publishing; keep the snapshot as evidence | Invent a live restore |

Every plan has `executed: false`. Authorised live replay or restore is a later Principal decision.

## Backup and restore rehearsal

These commands are fail-closed. They refuse `--live` and `LINKTREND_ALLOW_LIVE_OPS=1`.

```text
ops/run-backup.sh --rehearse
ops/restore-drill.sh --rehearse
ops/export-live-from-n8n.sh rehearse
```

- `run-backup.sh` writes mock control, catalogue, and workflow artifacts plus SHA-256 digests under a temp directory. It does not run `pg_dump`.
- `restore-drill.sh` builds or inspects gzip/tar structure (`CREATE` SQL + `automations/templates`). It does not apply SQL to Postgres.
- `export-live-from-n8n.sh` prints a local template export **plan** from `automations/templates/manifest.json`. It does not call n8n or GSM.

Integrity of the three backup kinds is also proven in-process by `rehearseRestore` in `@linktrend/automation-operations`.

## Explicit HOLDs

- No SSH or console session to Server01.
- No NATS URL, JetStream API, or monitoring port contact.
- No live Prometheus/Alertmanager/Grafana/NATS-exporter installation, scrape, or page.
- No n8n Public API, webhook, or workflow activation.
- No GSM / gcloud secret access.
- No production or stage restore, failover, or consumer mutate.
- No implementer PR, merge, or deployment from this packet.

## Proof commands

```text
npm run test:automation-operations
npm run typecheck:automation-operations
npm run restore:rehearse
git diff --check
```

`npm run restore:rehearse` is the repository-level disposable database rehearsal when Docker is available. This packet additionally proves JetStream/backup boundaries with the commands above and does not claim a live Server01 recovery.
