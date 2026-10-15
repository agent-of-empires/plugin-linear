"""Safe discovery of all checkouts belonging to host sessions."""

from __future__ import annotations

import os
import subprocess
from typing import Any

GIT_TIMEOUT = 2.0


def _git(path: str, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", path, *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _candidates(session: dict[str, Any]) -> tuple[list[dict[str, str]], str | None]:
    primary = session.get("project_path")
    candidates = [{"path": primary, "branch": ""}] if isinstance(primary, str) and primary else []
    workspace_repos = session.get("workspace_repos")
    if isinstance(workspace_repos, list):
        candidates.extend(
            {"path": repo["source_path"], "branch": str(repo.get("branch") or "")}
            for repo in workspace_repos
            if isinstance(repo, dict) and isinstance(repo.get("source_path"), str)
        )
    if isinstance(primary, str) and primary and not workspace_repos:
        try:
            with os.scandir(primary) as entries:
                candidates.extend({"path": entry.path, "branch": ""} for entry in entries if entry.is_dir())
        except OSError:
            pass
    return candidates, primary if isinstance(primary, str) else None


def _checkout(
    candidate: dict[str, str],
    primary: str | None,
    *,
    ignore_submodules: bool,
) -> dict[str, str] | None:
    path = candidate["path"]
    top = _git(path, "rev-parse", "--show-toplevel")
    if not top or os.path.realpath(top) != os.path.realpath(path):
        return None
    is_submodule = _git(path, "rev-parse", "--show-superproject-working-tree")
    if ignore_submodules and os.path.realpath(path) != os.path.realpath(primary or "") and is_submodule:
        return None
    branch = candidate["branch"] or _git(path, "symbolic-ref", "--quiet", "--short", "HEAD")
    return {"path": path, "branch": branch} if branch else None


def discover_checkouts(session: dict[str, Any], *, ignore_submodules: bool = True) -> list[dict[str, str]]:
    """Use host workspace metadata and discover immediate child checkouts as fallback."""
    candidates, primary = _candidates(session)
    unique: dict[str, dict[str, str]] = {}
    for candidate in candidates:
        checkout = _checkout(candidate, primary, ignore_submodules=ignore_submodules)
        if checkout:
            unique.setdefault(os.path.realpath(checkout["path"]), checkout)
    return list(unique.values())


def checkout_for_path(path: str) -> dict[str, str] | None:
    """Resolve the checkout root and current branch for a command path."""
    top = _git(path, "rev-parse", "--show-toplevel")
    branch = _git(path, "symbolic-ref", "--quiet", "--short", "HEAD")
    if not top or not branch:
        return None
    return {"path": top, "branch": branch}
