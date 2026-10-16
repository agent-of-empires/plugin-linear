from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

from aoe_linear_plugin.main import Runtime
from aoe_linear_plugin.uistate import PANE_SLOT


def test_worker_status_request_returns_actionable_auth_error(tmp_path: Path, monkeypatch) -> None:
    subprocess.run(["git", "init", "-b", "ENG-9-fix", str(tmp_path)], check=True, capture_output=True)
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("LINEAR_TOKEN", raising=False)
    output = io.StringIO()
    runtime = Runtime(stdin=io.StringIO(""), stdout=output)
    params = {"args": {"path": str(tmp_path)}}
    runtime.handle({"jsonrpc": "2.0", "id": 8, "method": "linear.status", "params": params})
    message = json.loads(output.getvalue())
    assert message["id"] == 8
    assert message["result"]["error"]["kind"] == "auth"
    assert "LINEAR_API_KEY" in message["result"]["error"]["hint"]
    assert message["result"]["branch"] == "ENG-9-fix"


def test_worker_host_smoke_answers_startup_rpcs_and_status(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-b", "ENG-8-fix", str(tmp_path)], check=True, capture_output=True)
    host_messages = [
        {"jsonrpc": "2.0", "id": 1_000_000, "result": {"value": 0}},
        {"jsonrpc": "2.0", "id": 1_000_001, "result": {"value": True}},
        {"jsonrpc": "2.0", "id": 1_000_002, "result": {"value": True}},
        {"jsonrpc": "2.0", "id": 1_000_003, "result": {"sessions": []}},
        {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "linear.status",
            "params": {"args": {"path": str(tmp_path)}},
        },
    ]
    input_data = "\n".join(json.dumps(message) for message in host_messages) + "\n"
    environment = {key: value for key, value in os.environ.items() if key not in {"LINEAR_API_KEY", "LINEAR_TOKEN"}}
    process = subprocess.run(
        [sys.executable, "-m", "aoe_linear_plugin.main"],
        input=input_data,
        text=True,
        capture_output=True,
        env=environment,
        check=True,
        timeout=10,
    )
    output = [json.loads(line) for line in process.stdout.splitlines()]
    status = next(message["result"] for message in output if message.get("id") == 42)
    assert status["branch"] == "ENG-8-fix"
    assert status["error"]["kind"] == "auth"
    assert any(message.get("method") == "ui.state.set" for message in output)


def test_manual_refresh_repaints_all_active_session_panes(monkeypatch) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("LINEAR_TOKEN", raising=False)
    sessions = [{"id": "s1", "project_path": ""}, {"id": "s2", "project_path": ""}]
    output = io.StringIO()
    runtime = Runtime(stdin=io.StringIO(""), stdout=output)
    monkeypatch.setattr(runtime, "call_host", lambda *_args, **_kwargs: {"sessions": sessions})

    runtime.handle({"jsonrpc": "2.0", "id": 9, "method": "linear.refresh", "params": {"session_id": "s1"}})

    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    panes = [
        message["params"]
        for message in messages
        if message.get("method") == "ui.state.set" and message["params"]["slot"] == PANE_SLOT[0]
    ]
    assert {pane["session_id"] for pane in panes} == {"s1", "s2"}


def test_issue_selection_repaints_cached_pane_without_network() -> None:
    output = io.StringIO()
    runtime = Runtime(stdin=io.StringIO(""), stdout=output)
    runtime.snapshot = {
        "sessions": [
            {
                "session_id": "s1",
                "issues": [
                    {"identifier": "ENG-1", "title": "First", "state": {"name": "Todo"}},
                    {"identifier": "ENG-2", "title": "Second", "state": {"name": "Started"}},
                ],
                "repos": [],
            }
        ]
    }
    params = {"session_id": "s1", "issue": "ENG-2"}
    runtime.handle({"method": "linear.select_issue", "params": params})
    assert runtime.selected["s1"] == "ENG-2"
    pushed = [json.loads(line) for line in output.getvalue().splitlines()]
    pane = next(
        message["params"]["payload"]
        for message in pushed
        if message.get("method") == "ui.state.set" and message["params"]["slot"] == PANE_SLOT[0]
    )
    selected = next(row for block in pane["blocks"] for row in block.get("children", []) if row.get("selected"))
    assert selected["prefix"] == "ENG-2"


def test_unknown_worker_method_returns_json_rpc_error() -> None:
    output = io.StringIO()
    runtime = Runtime(stdin=io.StringIO(""), stdout=output)
    runtime.handle({"jsonrpc": "2.0", "id": 3, "method": "linear.unsupported"})
    message = json.loads(output.getvalue())
    assert message["error"]["data"]["kind"] == "method_not_found"
    assert "linear.unsupported" in message["error"]["message"]
