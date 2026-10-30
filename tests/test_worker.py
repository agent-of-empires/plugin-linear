from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest

from aoe_linear_plugin import main as worker
from aoe_linear_plugin.main import EOF, Runtime


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
    assert response["result"]["linked"] is False
    assert response["result"]["error"] is None


def test_sort_key_is_removed_once_no_session_has_linear_issues() -> None:
    output = io.StringIO()
    runtime = Runtime(stdin=io.StringIO(""), stdout=output)
    unlinked = {"sessions": [{"session_id": "s1", "issues": [], "linked": False, "repos": []}]}
    linked = {"sessions": [{"session_id": "s1", "issues": [{"identifier": "ENG-1", "title": "Task"}], "repos": []}]}

    runtime.snapshot = unlinked
    runtime._push()
    runtime.snapshot = linked
    runtime._push()
    runtime.snapshot = unlinked
    runtime._push()

    calls = [
        (message["method"], message["params"]["slot"])
        for message in (json.loads(line) for line in output.getvalue().splitlines())
    ]
    sort_key_calls = [call for call in calls if call[1] == "sort-key"]
    assert sort_key_calls == [
        # Startup clears any sort key an earlier worker left behind, then publishes only while
        # some session has Linear issues.
        ("ui.state.remove", "sort-key"),
        ("ui.state.set", "sort-key"),
        ("ui.state.remove", "sort-key"),
    ]


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


def test_community_plugin_refresh_uses_deferred_scheduling() -> None:
    output = io.StringIO()
    runtime = Runtime(stdin=io.StringIO(""), stdout=output)

    runtime.handle(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "plugin.community.linear.refresh",
            "params": {},
        }
    )

    response = json.loads(output.getvalue())
    assert response["id"] == 10
    assert response["result"] == {"accepted": True}
    assert runtime.refresh_due is True


def test_unprefixed_open_alias_is_dispatchable(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def open_issue(path: str, *, selected: str | None = None, open_browser: bool = False) -> dict[str, str]:
        calls.update(path=path, open_browser=open_browser)
        return {"url": "https://linear.app/issue/ENG-1", "kind": "issue", "identifier": selected or "ENG-1"}

    monkeypatch.setattr(worker, "linear_open", open_issue)
    output = io.StringIO()
    runtime = Runtime(stdin=io.StringIO(""), stdout=output)

    runtime.handle({"jsonrpc": "2.0", "id": 11, "method": "linear.open", "params": {}})

    response = json.loads(output.getvalue())
    assert response["id"] == 11
    assert response["result"]["identifier"] == "ENG-1"
    assert calls == {"path": ".", "open_browser": False}


def test_reader_failure_always_signals_eof() -> None:
    class BrokenStream:
        def __iter__(self):
            return self

        def __next__(self):
            raise OSError("read failed")

    runtime = Runtime(stdin=BrokenStream(), stdout=io.StringIO())
    with pytest.raises(OSError, match="read failed"):
        runtime._read()
    assert runtime.inbox.get() is EOF
    assert runtime.inbox.empty()
