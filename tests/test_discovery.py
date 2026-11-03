from __future__ import annotations

import json
import subprocess
from pathlib import Path

from aoe_linear_plugin import discovery
from aoe_linear_plugin.discovery import commit_messages, discover_checkouts, pull_request_hints


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _repo(path: Path) -> None:
    path.mkdir(parents=True)
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "config", "user.name", "Test")
    (path / "file.txt").write_text("test")
    _git(path, "add", "file.txt")
    _git(path, "commit", "-m", "initial")


def test_discovery_uses_multi_checkout_host_metadata_and_deduplicates(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    worktree = tmp_path / "worktree"
    _repo(primary)
    _git(primary, "worktree", "add", "-b", "ENG-2-change", str(worktree))
    session = {
        "id": "session-1",
        "project_path": str(primary),
        "workspace_repos": [
            {"source_path": str(worktree), "branch": "ENG-2-change"},
            {"source_path": str(worktree), "branch": "ENG-2-change"},
        ],
    }
    found = discover_checkouts(session)
    assert {(item["path"], item["branch"]) for item in found} == {
        (str(primary), "main"),
        (str(worktree), "ENG-2-change"),
    }


def test_non_checkout_workspace_returns_empty(tmp_path: Path) -> None:
    assert discover_checkouts({"id": "x", "project_path": str(tmp_path)}) == []


def test_pull_request_hints_include_title_body_and_comments(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _repo(repo)
    discovery._pr_cache.clear()
    calls = []
    payload = [
        {
            "number": 31,
            "title": "Status replies",
            "body": "Fixes 0DIN-2361",
            "comments": [{"body": "Linked 0DIN-2361"}, {"body": "thanks"}, {"body": "follow-up"}],
        }
    ]

    def respond(command, **kwargs):
        calls.append(command)
        if command[0] == "gh":
            assert kwargs["cwd"] == str(repo)
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(discovery.subprocess, "run", respond)
    hints = pull_request_hints(str(repo), "status")
    # Every text field is scanned, so a later comment cannot be crowded out by the cap.
    assert hints == ["Status replies", "Fixes 0DIN-2361", "Linked 0DIN-2361", "thanks", "follow-up"]
    assert pull_request_hints(str(repo), "status") == hints
    assert len([call for call in calls if call[0] == "gh"]) == 1


def test_pull_request_hints_cache_invalidates_when_head_moves(monkeypatch, tmp_path: Path) -> None:
    discovery._pr_cache.clear()
    heads = iter(["one", "one", "two"])
    monkeypatch.setattr(discovery, "_git", lambda _path, *_args: next(heads))
    calls = []

    def respond(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps([{"body": f"Fixes ENG-{len(calls)}"}]), stderr=""
        )

    monkeypatch.setattr(discovery.subprocess, "run", respond)
    first = pull_request_hints(str(tmp_path), "status")
    assert pull_request_hints(str(tmp_path), "status") == first
    assert len(calls) == 1
    assert pull_request_hints(str(tmp_path), "status") != first
    assert len(calls) == 2


def test_pull_request_hints_are_empty_when_gh_is_unavailable(monkeypatch, tmp_path: Path) -> None:
    discovery._pr_cache.clear()
    monkeypatch.setattr(discovery, "_git", lambda _path, *_args: "head")

    def missing(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(discovery.subprocess, "run", missing)
    assert pull_request_hints(str(tmp_path), "status") == []


def test_pull_request_hints_are_empty_when_gh_fails(monkeypatch, tmp_path: Path) -> None:
    discovery._pr_cache.clear()
    monkeypatch.setattr(discovery, "_git", lambda _path, *_args: "head")

    def failed(*_args, **_kwargs):
        return subprocess.CompletedProcess([], 1, stdout="", stderr="authentication required")

    monkeypatch.setattr(discovery.subprocess, "run", failed)
    assert pull_request_hints(str(tmp_path), "status") == []

    def timed_out(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(["gh"], 5)

    discovery._pr_cache.clear()
    monkeypatch.setattr(discovery.subprocess, "run", timed_out)
    assert pull_request_hints(str(tmp_path), "status") == []


def test_commit_messages_are_recent_subjects_newest_first(tmp_path: Path) -> None:
    path = tmp_path / "repo"
    _repo(path)
    _git(path, "commit", "--allow-empty", "-m", "ENG-12: add cache")
    assert commit_messages(str(path)) == ["ENG-12: add cache", "initial"]
    assert commit_messages(str(tmp_path)) == []
