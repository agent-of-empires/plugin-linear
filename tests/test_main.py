from __future__ import annotations

import io
import itertools
import json
import os
import selectors
import subprocess
import sys
from pathlib import Path

import pytest

from aoe_linear_plugin import main as worker
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
    """Stream against the real worker so startup replies cannot be dropped as an input race."""
    subprocess.run(["git", "init", "-b", "ENG-8-fix", str(tmp_path)], check=True, capture_output=True)
    environment = {key: value for key, value in os.environ.items() if key not in {"LINEAR_API_KEY", "LINEAR_TOKEN"}}
    output = []
    with (
        subprocess.Popen(
            [sys.executable, "-m", "aoe_linear_plugin.main"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            env=environment,
        ) as process,
        selectors.DefaultSelector() as selector,
    ):
        assert process.stdin is not None
        assert process.stdout is not None
        selector.register(process.stdout, selectors.EVENT_READ)
        try:
            for message in (
                {"jsonrpc": "2.0", "id": 41, "method": "linear.refresh"},
                {"jsonrpc": "2.0", "id": 43, "method": "linear.status", "params": {"args": "oops"}},
            ):
                process.stdin.write((json.dumps(message) + "\n").encode())
            process.stdin.flush()
            for _ in range(100):
                assert selector.select(timeout=10), "Worker stopped responding"
                message = json.loads(process.stdout.readline())
                output.append(message)
                method = message.get("method")
                if method == "config.get":
                    key = message["params"]["key"]
                    value = {"ui_refresh_secs": 0, "ignore_submodules": True, "show_priority": True}.get(key, "")
                    result = {"value": value}
                elif method == "sessions.list":
                    result = {"sessions": [{"id": "s1", "project_path": str(tmp_path)}]}
                else:
                    if {41, 42, 43} <= {item.get("id") for item in output} and any(
                        item.get("method") == "ui.state.set" and item["params"]["slot"] == "pane" for item in output
                    ):
                        break
                    continue
                response = {"jsonrpc": "2.0", "id": message["id"], "result": result}
                process.stdin.write((json.dumps(response) + "\n").encode())
                if method == "sessions.list":
                    process.stdin.write(
                        (
                            json.dumps(
                                {
                                    "jsonrpc": "2.0",
                                    "id": 42,
                                    "method": "linear.status",
                                    "params": {"args": {"path": str(tmp_path)}},
                                }
                            )
                            + "\n"
                        ).encode()
                    )
                process.stdin.flush()
            else:
                pytest.fail("Worker did not finish startup and status requests")
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        assert process.returncode == 0
    status = next(message["result"] for message in output if message.get("id") == 42)
    assert status["branch"] == "ENG-8-fix"
    assert status["error"]["kind"] == "auth"
    assert next(message["result"] for message in output if message.get("id") == 41) == {"accepted": True}
    assert next(message["error"] for message in output if message.get("id") == 43)["data"]["kind"] == "internal_error"
    assert any(message.get("method") == "ui.state.set" for message in output)


def test_manual_refresh_repaints_all_active_session_panes(monkeypatch) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("LINEAR_TOKEN", raising=False)
    sessions = [{"id": "s1", "project_path": ""}, {"id": "s2", "project_path": ""}]
    output = io.StringIO()
    runtime = Runtime(stdin=io.StringIO(""), stdout=output)
    monkeypatch.setattr(runtime, "call_host", lambda *_args, **_kwargs: {"sessions": sessions})

    runtime.handle({"jsonrpc": "2.0", "id": 9, "method": "linear.refresh", "params": {"session_id": "s1"}})
    assert runtime.refresh_due is True
    runtime._scheduled_refresh()

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
    assert pane["blocks"][0]["title"] == "ENG-2 · Started"
    selector = next(block for block in pane["blocks"] if block.get("title") == "Other linked issues")
    assert [row["prefix"] for row in selector["children"]] == ["ENG-1"]


def test_unknown_worker_method_returns_json_rpc_error() -> None:
    output = io.StringIO()
    runtime = Runtime(stdin=io.StringIO(""), stdout=output)
    runtime.handle({"jsonrpc": "2.0", "id": 3, "method": "linear.unsupported"})
    message = json.loads(output.getvalue())
    assert message["error"]["data"]["kind"] == "method_not_found"
    assert "linear.unsupported" in message["error"]["message"]


@pytest.mark.parametrize("params", [{"args": "oops"}, "oops", ["oops"]])
def test_malformed_request_returns_error_and_preserves_next_request(params, tmp_path, monkeypatch) -> None:
    subprocess.run(["git", "init", "-b", "ENG-9", str(tmp_path)], check=True, capture_output=True)
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("LINEAR_TOKEN", raising=False)
    output = io.StringIO()
    runtime = Runtime(stdout=output)
    runtime.handle({"id": 1, "method": "linear.status", "params": params})
    runtime.handle({"id": 2, "method": "linear.status", "params": {"cwd": str(tmp_path)}})
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert messages[0]["error"]["data"]["kind"] == "internal_error"
    assert messages[1]["id"] == 2
    assert messages[1]["result"]["error"]["kind"] == "auth"


def test_repaint_exception_does_not_kill_dispatch_or_leak_details(monkeypatch) -> None:
    output = io.StringIO()
    runtime = Runtime(stdout=output)

    def fail():
        raise TypeError("sensitive response data")

    monkeypatch.setattr(runtime, "_push", fail)
    runtime.handle({"id": 1, "method": "linear.select_issue", "params": {"session_id": "s1", "issue": "ENG-1"}})
    runtime.handle({"id": 2, "method": "linear.refresh"})
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert messages[0]["error"]["data"]["kind"] == "internal_error"
    assert "sensitive response data" not in output.getvalue()
    assert messages[1] == {"jsonrpc": "2.0", "id": 2, "result": {"accepted": True}}


def test_refresh_during_host_wait_preserves_outer_reply(monkeypatch) -> None:
    monkeypatch.setattr(worker, "_ids", itertools.count(100))
    output = io.StringIO()
    runtime = Runtime(stdout=output)
    runtime.inbox.put({"id": 9, "method": "linear.refresh"})
    runtime.inbox.put({"id": 100, "result": {"value": 0}})
    assert runtime.call_host("config.get", {"key": "ui_refresh_secs"}) == {"value": 0}
    assert runtime.refresh_due is True
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [message.get("method") for message in messages] == ["config.get", None]
    assert messages[1]["result"] == {"accepted": True}


def test_failed_poll_preserves_command_loop(monkeypatch, capsys) -> None:
    runtime = Runtime(stdout=io.StringIO())

    def fail():
        raise KeyError("sensitive response data")

    monkeypatch.setattr(runtime, "refresh", fail)
    runtime._scheduled_refresh()
    assert runtime.next_refresh > worker.time.monotonic()
    assert "sensitive response data" not in capsys.readouterr().err
    runtime.handle({"id": 2, "method": "linear.refresh"})
    assert runtime.refresh_due is True
