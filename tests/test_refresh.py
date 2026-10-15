from __future__ import annotations

import json
import subprocess
from pathlib import Path

import httpx

from aoe_linear_plugin import refresh


def _checkout(path: Path, branch: str) -> None:
    subprocess.run(["git", "init", "-b", branch, str(path)], check=True, capture_output=True)


def test_active_rate_limit_serves_last_good_snapshot_without_http(monkeypatch, tmp_path: Path) -> None:
    previous = {
        "sessions": [
            {
                "session_id": "s1",
                "issues": [{"identifier": "ENG-1"}],
                "repos": [{"path": str(tmp_path), "branch": "ENG-1", "issues": [{"identifier": "ENG-1"}]}],
            }
        ],
        "auth": {"present": True},
    }
    monkeypatch.setattr(refresh, "_state", {"snapshot": previous, "backoff_until": 9999999999.0})
    snapshot = refresh.build_snapshot([{"id": "s1", "project_path": str(tmp_path)}], env={})
    assert snapshot["sessions"][0]["issues"] == [{"identifier": "ENG-1"}]
    assert snapshot["sessions"][0]["stale"] is True
    assert snapshot["rate_limited"] is True


def test_shared_checkout_is_queried_once_for_multiple_sessions(monkeypatch, tmp_path: Path) -> None:
    _checkout(tmp_path, "ENG-7-change")
    monkeypatch.setattr(refresh, "_state", {"snapshot": {"sessions": []}, "backoff_until": 0.0})
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload["query"])
        if "IssuesForBranch" in payload["query"]:
            return httpx.Response(200, json={"data": {"issues": {"nodes": [], "pageInfo": {"hasNextPage": False}}}})
        return httpx.Response(200, json={"data": {"issue": {"id": "i7", "identifier": "ENG-7", "title": "Task"}}})

    shared_path = str(tmp_path)
    sessions = [
        {"id": "one", "project_path": shared_path},
        {"id": "two", "project_path": shared_path},
    ]
    snapshot = refresh.build_snapshot(sessions, env={"LINEAR_API_KEY": "token"}, transport=httpx.MockTransport(respond))
    assert len(requests) == 2
    assert [session["issues"][0]["identifier"] for session in snapshot["sessions"]] == ["ENG-7", "ENG-7"]


def test_http_failure_marks_last_good_issue_data_stale(monkeypatch, tmp_path: Path) -> None:
    _checkout(tmp_path, "ENG-1")
    previous = {
        "sessions": [
            {
                "session_id": "s1",
                "issues": [{"id": "i1", "identifier": "ENG-1"}],
                "repos": [
                    {
                        "path": str(tmp_path),
                        "branch": "ENG-1",
                        "issues": [{"id": "i1", "identifier": "ENG-1"}],
                    }
                ],
            }
        ]
    }
    monkeypatch.setattr(refresh, "_state", {"snapshot": previous, "backoff_until": 0.0})

    snapshot = refresh.build_snapshot(
        [{"id": "s1", "project_path": str(tmp_path)}],
        env={"LINEAR_API_KEY": "token"},
        transport=httpx.MockTransport(lambda _: httpx.Response(503)),
    )

    assert [issue["identifier"] for issue in snapshot["sessions"][0]["issues"]] == ["ENG-1"]
    assert snapshot["sessions"][0]["stale"] is True
    assert snapshot["sessions"][0]["repos"][0]["error"]["kind"] == "network"


def test_http_rate_limit_sets_retry_backoff(monkeypatch, tmp_path: Path) -> None:
    _checkout(tmp_path, "ENG-1")
    monkeypatch.setattr(refresh, "_state", {"snapshot": {"sessions": []}, "backoff_until": 0.0})

    def response(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "30"})

    snapshot = refresh.build_snapshot(
        [{"id": "s1", "project_path": str(tmp_path)}],
        env={"LINEAR_API_KEY": "token"},
        transport=httpx.MockTransport(response),
    )
    assert snapshot["rate_limited"] is True
    assert snapshot["sessions"][0]["repos"][0]["error"]["kind"] == "rate_limited"
    assert refresh._state["backoff_until"] > 0
