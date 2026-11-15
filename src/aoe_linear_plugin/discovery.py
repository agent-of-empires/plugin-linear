"""Safe discovery of all checkouts belonging to host sessions."""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any

GIT_TIMEOUT = 2.0
COMMIT_HINT_LIMIT = 30
GH_TIMEOUT = 5.0
PR_HINT_TTL = 600.0
_DEFAULT_BRANCHES = frozenset({"main", "master"})
# Trunk refs whose history a checkout inherits, in the order most likely to exist first.
_DEFAULT_REFS = ("origin/HEAD", "origin/main", "origin/master", "main", "master")

# ``(path, branch) -> (expires_at, head, hints)``. Pull request text changes rarely, and a poll
# must not re-run ``gh`` for every slug-named branch, so a lookup is reused until the checkout's
# HEAD moves or the TTL lapses. The worker refreshes from one thread, so a plain dict is enough.
_pr_cache: dict[tuple[str, str], tuple[float, str, list[str]]] = {}


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


def _gh(path: str, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["gh", *args],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _pull_request_texts(pull_request: dict[str, Any]) -> list[str]:
    """Title, body, and comment text of one pull request."""
    texts: list[str] = []
    for key in ("title", "body"):
        value = pull_request.get(key)
        if isinstance(value, str) and value.strip():
            texts.append(value)
    comments = pull_request.get("comments")
    if isinstance(comments, list):
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            body = comment.get("body")
            if isinstance(body, str) and body.strip():
                texts.append(body)
    return texts


def _pull_request_text(path: str, branch: str) -> list[str]:
    """Pull request title, body, and comment text for the branch, newest PRs first."""
    output = _gh(
        path,
        "pr",
        "list",
        "--head",
        branch,
        "--state",
        "all",
        "--limit",
        "5",
        "--json",
        "number,title,body,comments",
    )
    if not output:
        return []
    try:
        pull_requests = json.loads(output)
    except json.JSONDecodeError:
        return []
    if not isinstance(pull_requests, list):
        return []
    hints: list[str] = []
    for pull_request in pull_requests:
        if isinstance(pull_request, dict):
            hints.extend(_pull_request_texts(pull_request))
    return hints


def pull_request_hints(path: str, branch: str) -> list[str]:
    """Free text from the branch's pull requests, cached per commit for ``PR_HINT_TTL``.

    A worktree branch can be a slug of the task title while its pull request names the Linear
    issue. ``gh`` is optional: when it is missing, unauthenticated, or the branch has no pull
    request, the empty result is cached too so polling does not keep re-running it.
    """
    head = _git(path, "rev-parse", "HEAD") or ""
    key = (path, branch)
    moment = time.monotonic()
    cached = _pr_cache.get(key)
    if cached and cached[0] > moment and cached[1] == head:
        return list(cached[2])
    hints = _pull_request_text(path, branch)
    _pr_cache[key] = (moment + PR_HINT_TTL, head, hints)
    return list(hints)


def _base_ref(path: str) -> str | None:
    """The ref whose history this checkout inherited rather than authored, if any.

    ``main`` usually has a remote, and its own commits are all inherited from that remote, so
    the base branch itself has to exclude its upstream instead of itself. A feature branch has
    no such inheritance: its upstream is its own publishing remote, and excluding that would
    drop exactly the commits it authored. A branch with no default ref keeps its whole history.
    """
    branch = _git(path, "symbolic-ref", "--quiet", "--short", "HEAD")
    for ref in _DEFAULT_REFS:
        if ref == branch:
            continue
        if _git(path, "rev-parse", "--verify", "--quiet", ref):
            return ref
    if branch not in _DEFAULT_BRANCHES:
        return None
    return _git(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")


def commit_messages(path: str, limit: int = COMMIT_HINT_LIMIT) -> list[str]:
    """Recent commit subjects authored on this branch, newest first, as hints for identifiers.

    ``git log`` alone walks back into the base branch, so a checkout sitting on ``main`` would
    attribute a months-old ``ENG-12`` commit to the current session and show that issue as this
    checkout's work. Commits reachable from the base ref are excluded; a checkout with no known
    base keeps its whole history.
    """
    args = [f"-n{limit}", "--no-color", "--format=%s", "HEAD"]
    base = _base_ref(path)
    if base:
        args.extend(["--not", base])
    output = _git(path, "log", *args)
    return [line.strip() for line in (output or "").splitlines() if line.strip()]


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
