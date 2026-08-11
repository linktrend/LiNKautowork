#!/usr/bin/env python3
"""Carlos user-token credentials for two Packager operations only.

Allowed operations:
  - pr_create: Review Packager feature PR creation into development
  - bugbot_comment: exactly one `@cursor review` + SHA marker comment

Never use this token for merge, promote, repair, status/check writes, cleanup,
or branch pushes. Never print or return token material in logs/outcomes.

Subprocess boundary:
  Child environments must scrub LINKTREND_BUGBOT_USER_TOKEN and BUGBOT_USER_TOKEN
  unless the child is the exact `gh pr create` operation (token passed only as
  GH_TOKEN/GITHUB_TOKEN, not as residual secret env names).
"""

from __future__ import annotations

import os
from typing import Mapping

ALLOWED_OPERATIONS = frozenset({"pr_create", "bugbot_comment"})

# Secret / resolved names that must never leak into unrelated child processes.
CARLOS_TOKEN_ENV_KEYS = (
    "LINKTREND_BUGBOT_USER_TOKEN",
    "BUGBOT_USER_TOKEN",
)

# Env keys that must never silently substitute for the user token.
_FORBIDDEN_EQUALITY_KEYS = (
    "AUTOMATION_TOKEN",
    "LINKTREND_APP_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
)


class BugbotUserCredentialsError(RuntimeError):
    """User token missing or invalid for a permitted Packager operation."""


def resolve_bugbot_user_token() -> tuple[str | None, str, str]:
    """Resolve Carlos user token without logging secret material.

    Source of truth for the secret is ``LINKTREND_BUGBOT_USER_TOKEN``.
    ``BUGBOT_USER_TOKEN`` is accepted only as the post-resolve export from
    ``resolve_bugbot_user_token.sh`` (same value, never an alternate secret).

    Returns:
      (token_or_none, source, status)
    """
    # Prefer resolved export, then the repository secret name only.
    raw = (os.environ.get("BUGBOT_USER_TOKEN") or "").strip()
    if not raw:
        raw = (os.environ.get("LINKTREND_BUGBOT_USER_TOKEN") or "").strip()
    if not raw:
        return None, "none", "missing"

    for key in _FORBIDDEN_EQUALITY_KEYS:
        other = (os.environ.get(key) or "").strip()
        if other and raw == other:
            return None, "invalid", "must_not_equal_automation_or_github_token"

    return raw, "user_secret", "configured"


def require_bugbot_user_token(operation: str) -> str:
    """Fail closed: return user token only for an allowlisted operation."""
    if operation not in ALLOWED_OPERATIONS:
        raise BugbotUserCredentialsError(
            f"operation_not_permitted_for_bugbot_user_token:{operation}"
        )
    token, source, status = resolve_bugbot_user_token()
    if not token or source != "user_secret" or status != "configured":
        raise BugbotUserCredentialsError(
            f"bugbot_user_credentials_blocked:{status}"
        )
    return token


def scrub_carlos_token_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a copy of env with Carlos token names removed."""
    out = dict(os.environ if env is None else env)
    for key in CARLOS_TOKEN_ENV_KEYS:
        out.pop(key, None)
    return out


def subprocess_env_for_token(token: str, *, role: str) -> dict[str, str]:
    """Build a child env for an App or PR-create gh invocation.

    Roles:
      - ``app``: GH_TOKEN=App; Carlos secret names scrubbed
      - ``pr_create``: GH_TOKEN=Carlos token value only; Carlos secret *names*
        still scrubbed so the child does not inherit residual secret env keys
    """
    if role not in {"app", "pr_create"}:
        raise ValueError(f"unsupported subprocess token role: {role}")
    if not token:
        raise BugbotUserCredentialsError("empty_token_for_subprocess")
    env = scrub_carlos_token_env(os.environ)
    env["GH_TOKEN"] = token
    env["GITHUB_TOKEN"] = token
    return env
