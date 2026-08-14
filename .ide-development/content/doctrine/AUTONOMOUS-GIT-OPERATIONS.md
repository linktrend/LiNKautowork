# Git operations doctrine

**Status:** Active system-source doctrine. This repository is the
IDE Development source and is not a consumer install target.

## Normal flow

Implementers work on short-lived `issue/*` branches, checkpoint with one
focused commit, and stop. Accepted issue commits are integrated serially on a
`phase/*` branch. The Packager opens one Phase PR into `development`; the
Integrator and promotion gates evaluate exact PR heads. No implementer opens,
merges, or promotes a PR.

Checkpoints do not trigger managed CI. The Phase PR runs hosted ARM64 fast
checks. Only an exact final seal may trigger Bugbot and the full suite. A
successful receipt is reused for promotion only when all frozen identity
digests match. Main promotion requires Carlos's explicit approval.

## Stop conditions

Stop on a changed sealed head, missing or stale evidence, failed protection or
source policy, an unresolved conflict, a third infrastructure attempt, or a
third sealed candidate. Preserve the prior evidence and report the reason;
never repair by choosing one side automatically.

## External boundary

This doctrine does not perform GitHub, host, Docker, consumer, release, or
billing operations. W3 operators use the redacted inventory and cleanup plan
under `scripts/external/cleanup_plan.py`, with separate repository and host
scopes. The default is a plan with zero external mutation; live apply is
outside this repository executor's authority.
