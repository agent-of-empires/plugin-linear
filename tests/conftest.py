from __future__ import annotations

import json
from pathlib import Path

import pytest


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
