from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _no_token_file(monkeypatch, tmp_path_factory):
    """Resolver tests never read the developer's real ~/.config/linear/api_key.

    Token-file behaviour has its own coverage; every other test passes an explicit
    `env` mapping and expects that to be the only source.
    """
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
