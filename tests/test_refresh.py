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


def test_shared_checkout_is_queried_once_for_multiple_sessions(
    monkeypatch, tmp_path: Path, recorded_linear_responses
) -> None:
    _checkout(tmp_path, "recorded/live-1-branch")
    monkeypatch.setattr(refresh, "_state", {"snapshot": {"sessions": []}, "backoff_until": 0.0})
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload["query"])
        recorded = recorded_linear_responses["branch_match"]
        return httpx.Response(recorded["http_status"], json=recorded["body"])

    shared_path = str(tmp_path)
    sessions = [
        {"id": "one", "project_path": shared_path},
        {"id": "two", "project_path": shared_path},
    ]
    snapshot = refresh.build_snapshot(sessions, env={"LINEAR_API_KEY": "token"}, transport=httpx.MockTransport(respond))
    assert len(requests) == 1
    assert [session["issues"][0]["identifier"] for session in snapshot["sessions"]] == ["LIVE-1", "LIVE-1"]


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


def test_http_failure_without_cached_issue_data_does_not_mark_snapshot_stale(monkeypatch, tmp_path: Path) -> None:
    _checkout(tmp_path, "feature/unlinked")
    previous = {
        "sessions": [
            {
                "session_id": "s1",
                "issues": [],
                "repos": [{"path": str(tmp_path), "branch": "feature/unlinked", "issues": []}],
            }
        ]
    }
    monkeypatch.setattr(refresh, "_state", {"snapshot": previous, "backoff_until": 0.0})

    snapshot = refresh.build_snapshot(
        [{"id": "s1", "project_path": str(tmp_path)}],
        env={"LINEAR_API_KEY": "token"},
        transport=httpx.MockTransport(lambda _: httpx.Response(503)),
    )

    session = snapshot["sessions"][0]
    assert session.get("stale") is None
    assert session["repos"][0]["error"]["kind"] == "network"


def test_rate_limit_without_cached_issue_data_does_not_mark_snapshot_stale(monkeypatch, tmp_path: Path) -> None:
    previous = {
        "sessions": [
            {
                "session_id": "s1",
                "issues": [],
                "repos": [{"path": str(tmp_path), "branch": "feature/unlinked", "issues": []}],
            }
        ]
    }
    monkeypatch.setattr(refresh, "_state", {"snapshot": previous, "backoff_until": 9999999999.0})

    snapshot = refresh.build_snapshot([{"id": "s1", "project_path": str(tmp_path)}], env={})

    assert snapshot["sessions"][0].get("stale") is None
    assert snapshot["sessions"][0]["repos"][0]["error"] == {
        "kind": "rate_limited",
        "hint": "Linear rate limit active; refresh will retry later.",
    }
    assert snapshot["rate_limited"] is True


def test_rate_limit_keeps_completed_results_and_stops_remaining_requests(monkeypatch, tmp_path: Path) -> None:
    paths = [tmp_path / name for name in ("a", "b", "c")]
    for index, path in enumerate(paths, start=1):
        _checkout(path, f"ENG-{index}")
    monkeypatch.setattr(refresh, "_state", {"snapshot": {"sessions": []}, "backoff_until": 0.0})
    requested = []

    def respond(request):
        branch = json.loads(request.content)["variables"]["branchName"]
        requested.append(branch)
        if branch == "ENG-1":
            return httpx.Response(200, json={"data": {"issueVcsBranchSearch": {"id": "i1", "identifier": "ENG-1"}}})
        return httpx.Response(429, headers={"Retry-After": "30"})

    sessions = [{"id": str(index), "project_path": str(path)} for index, path in enumerate(paths)]
    snapshot = refresh.build_snapshot(sessions, env={"LINEAR_API_KEY": "key"}, transport=httpx.MockTransport(respond))
    assert requested == ["ENG-1", "ENG-2"]
    assert snapshot["sessions"][0]["issues"] == [{"id": "i1", "identifier": "ENG-1"}]
    assert snapshot["sessions"][0].get("stale") is None
    assert [session["repos"][0]["error"]["kind"] for session in snapshot["sessions"][1:]] == [
        "rate_limited",
        "rate_limited",
    ]
    cached = refresh.build_snapshot(sessions, env={"LINEAR_API_KEY": "key"}, transport=httpx.MockTransport(respond))
    assert requested == ["ENG-1", "ENG-2"]
    assert cached["sessions"][0]["issues"] == snapshot["sessions"][0]["issues"]
    assert cached["sessions"][0]["stale"] is True
