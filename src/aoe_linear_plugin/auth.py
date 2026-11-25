"""Linear API token resolution.

A token is found once per refresh, in a fixed order:

1. ``LINEAR_API_KEY`` / ``LINEAR_TOKEN`` in the environment.
2. A token file: ``LINEAR_API_KEY_FILE`` when set, else ``~/.config/linear/api_key``.

The file is not a convenience. AoE fixes the daemon's environment when the
daemon starts and hands that copy to every plugin worker, so a worker inherits
the environment of whatever shell launched AoE, once. When that shell is an SSH
session, a platform credential store that needs interaction cannot be read at
all: on macOS ``security find-generic-password -w`` fails with
``errSecInteractionNotAllowed`` and prints nothing, so the daemon starts with
no token and every worker after it inherits the absence, with no way to correct
it short of restarting the daemon. Reading a file the user owns is the same
answer ``gh auth token`` gives from ``~/.config/gh/hosts.yml``, and it is read
on every refresh, so a rejected file-backed key can be replaced without a
restart. A key taken from the environment cannot be: the daemon fixes its
environment when it starts.

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
# A token is a single short line, so the head of the file is enough to find it
# and a mistake such as a binary blob at that path stays cheap to read.
_MAX_HEAD_BYTES = 4096


def _clean(value: str | None) -> str | None:
    """Return the token without surrounding whitespace, or None when it is empty."""
    if value is None:
        return None
    token = value.strip()
    return token or None


def token_file(source: Mapping[str, str]) -> Path:
    """Return the token file to read.

    ``LINEAR_API_KEY_FILE`` is an override: setting it selects that path and
    suppresses the default rather than being tried ahead of it.

    An override naming an unresolvable home (``~nosuchuser/key``) raises
    ``RuntimeError`` from ``expanduser()``. ``resolve_token()`` turns that into
    an absent token; a caller that must not fail should go through it.
    """
    return Path(source.get(KEY_FILE_ENV_VAR) or DEFAULT_KEY_FILE).expanduser()


def _read_token_file(path: Path) -> str | None:
    """Return the file's first line as a token, or None when it is absent or empty.

    Only the first line is read and decoded, and a decoding failure counts as no
    token. This runs before the callers' Linear error handling, so raising here
    would turn a malformed file into a failed status request and a refresh that
    never publishes a snapshot.

    The head of the file is split with ``splitlines()`` rather than read with
    ``readline()``, so a file saved with bare carriage returns still yields its
    first-line token instead of one value with a stray CR inside it. Decoding
    with ``utf-8-sig`` drops a byte-order mark, which ``strip()`` leaves in place
    and Linear then rejects.
    """
    try:
        with path.open("rb") as handle:
            head = handle.readline(_MAX_HEAD_BYTES)
    except OSError:
        return None
    lines = head.splitlines()
    if not lines:
        return None
    try:
        return _clean(lines[0].decode("utf-8-sig"))
    except UnicodeDecodeError:
        return None


def resolve_token(env: Mapping[str, str] | None = None) -> str | None:
    """Return a personal API key; LINEAR_TOKEN is an alias, not an OAuth token."""
    source = os.environ if env is None else env
    for key in TOKEN_ENV_VARS:
        token = _clean(source.get(key))
        if token is not None:
            return token
    try:
        path = token_file(source)
    except RuntimeError:
        return None
    return _read_token_file(path)
