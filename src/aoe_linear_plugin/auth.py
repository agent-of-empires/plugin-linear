"""Linear API token resolution."""

from __future__ import annotations

import os
from collections.abc import Mapping


def resolve_token(env: Mapping[str, str] | None = None) -> str | None:
    """Return a personal API key; LINEAR_TOKEN is an alias, not an OAuth token."""
    source = os.environ if env is None else env
    token = source.get("LINEAR_API_KEY") or source.get("LINEAR_TOKEN")
    return token.strip() if token and token.strip() else None
