from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from aoe_linear_plugin.main import _response, main


def test_worker_status_protocol_and_notification_handling(monkeypatch, tmp_path: Path, capsys) -> None:
    subprocess.run(["git", "init", "-b", "linear-worker-test", str(tmp_path)], check=True, capture_output=True)
    requests = [
        {"jsonrpc": "2.0", "method": "session.status.changed", "params": {}},
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


def test_worker_unknown_command_returns_method_not_found() -> None:
    assert _response({"jsonrpc": "2.0", "id": 2, "method": "plugin.community.linear.unknown"}) == {
        "jsonrpc": "2.0",
        "id": 2,
        "error": {"code": -32601, "message": "Unknown method: plugin.community.linear.unknown"},
    }
