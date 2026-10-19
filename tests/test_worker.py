from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from aoe_linear_plugin.main import _response, main


def test_worker_status_protocol_and_notification_handling(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("LINEAR_TOKEN", raising=False)
    subprocess.run(["git", "init", "-b", "linear-worker-test", str(tmp_path)], check=True, capture_output=True)
    requests = [
        {"jsonrpc": "2.0", "method": "session.status.changed", "params": {}},
        {"jsonrpc": "2.0", "method": 3, "params": "invalid"},
        {"jsonrpc": "2.0", "id": 7, "method": "plugin.community.linear.status", "params": {"path": str(tmp_path)}},
    ]
    monkeypatch.setattr(sys, "stdin", iter([json.dumps(request) + "\n" for request in requests]))

    main()

    output = capsys.readouterr().out.splitlines()
    assert len(output) == 1
    response = json.loads(output[0])
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 7
    assert response["result"]["branch"] == "linear-worker-test"
    assert response["result"]["error"]["kind"] == "auth"


def test_worker_rejects_unrelated_methods_and_unknown_parameters() -> None:
    for method in ("session.open", "rpc.open", "plugin.community.linear.Open"):
        response = _response({"jsonrpc": "2.0", "id": 3, "method": method})
        assert response is not None
        assert response["error"]["code"] == -32601

    response = _response(
        {"jsonrpc": "2.0", "id": 4, "method": "plugin.community.linear.open", "params": {"selectedd": "ENG-1"}}
    )
    assert response is not None
    assert response["error"]["code"] == -32602


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"jsonrpc": "1.0", "id": 1, "method": "plugin.community.linear.status"},
        {"jsonrpc": "2.0", "id": 1, "method": 1},
        {"jsonrpc": "2.0", "id": True, "method": "plugin.community.linear.status"},
    ],
)
def test_worker_invalid_requests_use_null_id(payload: Any) -> None:
    response = _response(payload)
    assert response is not None
    assert response["error"]["code"] == -32600
    assert response["id"] is None


def test_worker_malformed_json_returns_parse_error(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "stdin", iter(["{invalid}\n"]))

    main()

    response = json.loads(capsys.readouterr().out)
    assert response == {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
