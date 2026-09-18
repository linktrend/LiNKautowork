# LiNKsites consumer handoff v1 (LSG0-04)

Source-only consumer-registration prerequisites for LiNKsites. This document does not prove a live health check, organisation-bound receipt, OSS install, or deployment.

## Exact source identity (admitted starting work)

| Field | Value |
| --- | --- |
| Repository | `linktrend/LiNKautowork` |
| Ref | `issue/147-add-linksites-source-only-consumer-registration` |
| Commit | `a13a6467fc9bc2fccdddd1de8d9e258c78e57fdd` |
| Tree | `10e6b59394bfd57703d6f3cee5d7bcda3aa7342f` |

Cached cloud checkout may initially land on another branch. Work proceeds only from this admitted issue-branch identity.

## Required consumer registration data

The fail-closed contract `linksites-consumer-registration.v1` requires every field below. Fixture identifiers in tests are disposable local values, not a live organisation, endpoint, secret, or key.

| Field | Requirement |
| --- | --- |
| `organisation_id` | Explicit UUID. Must match the authenticated Platform organisation and the configured grant. |
| `environment` | One of `development`, `staging`, `production`. Must match the grant. |
| `event_grants` | Named allowlist drawn only from `linkautowork.v1.execution.succeeded`, `linkautowork.v1.execution.failed`, `linkautowork.v1.lifecycle.transition`. |
| `signing_key_ref` | GSM-style name (`LINKTREND_[A-Z0-9_]+`). Reference only; never a key value. |
| `private_endpoint` | HTTPS URL whose sanitized identity is RFC1918 or `*.internal` host plus a bounded path. |

Gateway route: `POST /v1/consumers/linksites/registration`. Unconfigured runtime fails closed (`503`). No grant is wired into `buildDependencies`; production secrets and live endpoints are not invented here.

## Event grants

A registration is admitted only when every requested event is in the grant allowlist. Unknown or ungranted names fail closed. This is a named source grant, not a subscription, delivery, or consumer-outcome proof.

## Organisation and environment grant proof

Admission compares organisation ID and environment against an explicit in-process grant supplied by tests or a future configured runtime. A mismatched organisation, a mismatched Platform claim, or a mismatched environment is denied. This file does not name a real organisation.

## Signing reference

The grant stores a signing-key **reference** such as the fixture name `LINKTREND_SITES_DEV_AUTOWORK_SIGNING_KEY`. Missing references, secret-shaped values, and names that do not match the grant fail closed. No signing secret is present in this repository change.

## Private endpoint identity

Admitted identity is `{ scheme: "https", host, path }` after sanitization. Userinfo, HTTP, public DNS/IP, and non-default ports fail closed. Example fixture host `10.8.0.21` is a disposable RFC1918 address, not a live endpoint.

## Remaining HOLD

| HOLD | Why it remains |
| --- | --- |
| Live health | No network call, probe, or health result is performed or claimed. |
| Organisation-bound receipt | No receipt is issued, persisted, or verified. |
| OSS install / deployment | OSS completeness requires immutable artifact, preservation, provenance, reproducibility, and rollback proof. None of those are supplied here. |

This handoff is source and local evidence only.
