from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def recorded_linear_responses():
    return json.loads((Path(__file__).parent / "fixtures" / "linear_live.json").read_text())["responses"]
