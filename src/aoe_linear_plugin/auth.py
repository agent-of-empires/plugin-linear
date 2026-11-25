"""Linear API token resolution.

A token is found once per refresh, in a fixed order:

1. ``LINEAR_API_KEY`` / ``LINEAR_TOKEN`` in the environment.
2. A token file: ``LINEAR_API_KEY_FILE`` when set, else ``~/.config/linear/api_key``.

The file is not a convenience. AoE fixes the daemon's environment when the
daemon starts and hands that copy to every plugin worker, so a worker inherits
the environment of whatever shell launched AoE, once. When that shell is an SSH
session, a platform credential store that needs interaction cannot be read at
all -- on macOS ``security find-generic-password -w`` fails with
``errSecInteractionNotAllowed`` and prints nothing -- so the daemon starts with
no token and every worker after it inherits the absence, with no way to correct
it short of restarting the daemon. Reading a file the user owns is the same
answer ``gh auth token`` gives from ``~/.config/gh/hosts.yml``, and it is read
on every refresh, so replacing a rejected key needs no restart.

The plugin still never writes, caches, or logs a token: the file is read and the
result is held only for the request that needed it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

TOKEN_ENV_VARS = ("LINEAR_API_KEY", "LINEAR_TOKEN")
KEY_FILE_ENV_VAR = "LINEAR_API_KEY_FILE"
DEFAULT_KEY_FILE = "~/.config/linear/api_key"


def _clean(value: str | None) -> str | None:
    """Return the token without surrounding whitespace, or None when it is empty."""
    if value is None:
        return None
    token = value.strip()
    return token or None


def token_file(source: Mapping[str, str]) -> Path:
    """Return the token file to read, honouring an explicit override."""
    return Path(source.get(KEY_FILE_ENV_VAR) or DEFAULT_KEY_FILE).expanduser()


def _read_token_file(path: Path) -> str | None:
    """Return the file's first line as a token, or None when it is absent or empty."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    lines = text.splitlines()
    return _clean(lines[0] if lines else None)


def resolve_token(env: Mapping[str, str] | None = None) -> str | None:
    """Return a personal API key; LINEAR_TOKEN is an alias, not an OAuth token."""
    source = os.environ if env is None else env
    for key in TOKEN_ENV_VARS:
        token = _clean(source.get(key))
        if token is not None:
            return token
    return _read_token_file(token_file(source))
