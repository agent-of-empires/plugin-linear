from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

from aoe_linear_plugin import main as worker
from aoe_linear_plugin.main import Runtime


def test_community_plugin_status_uses_host_runtime(tmp_path: Path, monkeypatch) -> None:
    subprocess.run(["git", "init", "-b", "linear-worker-test", str(tmp_path)], check=True, capture_output=True)
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("LINEAR_TOKEN", raising=False)
    output = io.StringIO()
    runtime = Runtime(stdin=io.StringIO(""), stdout=output)

    runtime.handle(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "plugin.community.linear.status",
            "params": {"path": str(tmp_path)},
        }
    )

    response = json.loads(output.getvalue())
    assert response["id"] == 7
    assert response["result"]["branch"] == "linear-worker-test"
    assert response["result"]["error"]["kind"] == "auth"


def test_community_plugin_open_uses_host_runtime_and_browser_action(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def open_issue(path: str, *, selected: str | None = None, open_browser: bool = False) -> dict[str, str]:
        calls.update(path=path, selected=selected, open_browser=open_browser)
        return {"url": "https://linear.app/issue/ENG-1", "kind": "issue", "identifier": selected or ""}

    monkeypatch.setattr(worker, "linear_open", open_issue)
    output = io.StringIO()
    runtime = Runtime(stdin=io.StringIO(""), stdout=output)

    runtime.handle(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "plugin.community.linear.open",
            "params": {"path": "/checkout", "selected": "ENG-1"},
        }
    )

    response = json.loads(output.getvalue())
    assert response["id"] == 8
    assert response["result"]["identifier"] == "ENG-1"
    assert calls == {"path": "/checkout", "selected": "ENG-1", "open_browser": True}


def test_community_plugin_status_rejects_unknown_parameters() -> None:
    output = io.StringIO()
    runtime = Runtime(stdin=io.StringIO(""), stdout=output)

    runtime.handle(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "plugin.community.linear.status",
            "params": {"selectedd": "ENG-1"},
        }
    )

    response = json.loads(output.getvalue())
    assert response["id"] == 9
    assert response["error"]["data"]["kind"] == "invalid_request"
