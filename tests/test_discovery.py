from __future__ import annotations

import subprocess
from pathlib import Path

from aoe_linear_plugin.discovery import discover_checkouts


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
