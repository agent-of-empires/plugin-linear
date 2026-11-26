from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _no_credentials(monkeypatch, tmp_path_factory):
    """Resolver tests never see the developer's real token, in a file or in the environment.

    Patching the default path keeps ~/.config/linear/api_key out of reach. Deleting
    the environment variables covers the tests that call the resolver with no explicit
    mapping, where an exported key would otherwise win, and an inherited
    LINEAR_API_KEY_FILE would route around the patched default. Token-file behaviour
    has its own coverage.
    """
    for name in ("LINEAR_API_KEY", "LINEAR_TOKEN", "LINEAR_API_KEY_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "aoe_linear_plugin.auth.DEFAULT_KEY_FILE",
        str(tmp_path_factory.getbasetemp() / "no-token-file"),
    )


@pytest.fixture(autouse=True)
def _no_pull_request_lookup(monkeypatch):
    """Unit tests never spawn `gh`; the fallback has dedicated coverage with a stub."""

    def no_hints(*_args, **_kwargs):
        return []

    monkeypatch.setattr("aoe_linear_plugin.handlers.pull_request_hints", no_hints)
    monkeypatch.setattr("aoe_linear_plugin.refresh.pull_request_hints", no_hints)


@pytest.fixture
def recorded_linear_responses():
    return json.loads((Path(__file__).parent / "fixtures" / "linear_live.json").read_text())["responses"]
