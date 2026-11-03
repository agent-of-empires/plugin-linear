"""Rate-aware aggregate issue refresh with last-good cache fallback."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from aoe_linear_plugin.auth import resolve_token
from aoe_linear_plugin.client import LinearClient
from aoe_linear_plugin.discovery import commit_messages, discover_checkouts, pull_request_hints
from aoe_linear_plugin.errors import LinearError
from aoe_linear_plugin.resolver import branch_is_linear, identifiers_in_text, resolve_branch

AUTH_HINT = "Set LINEAR_API_KEY to load Linear issue data."
RATE_HINT = "Linear rate limit active; refresh will retry later."

_lock = threading.Lock()
_state: dict[str, Any] = {
    "snapshot": {"sessions": [], "auth": {"present": False}},
    "backoff_until": 0.0,
}


@dataclass
class _Fetched:
    """Per-checkout lookup results and the local hints that produced them."""

    current: dict[tuple[str, str], list[dict[str, Any]]]
    errors: dict[tuple[str, str], dict[str, Any]]
    stale_keys: set[tuple[str, str]]
    hints: dict[tuple[str, str], list[str]]


def _fetch_branch(
    client: LinearClient,
    branch: str,
    hints: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    try:
        return resolve_branch(client, branch, hints=hints), None
    except LinearError as exc:
        error: dict[str, Any] = {"kind": exc.kind, "hint": str(exc)}
        if exc.retry_after is not None:
            error["retry_after"] = exc.retry_after
        return [], error


def _fetch_branches(
    client: LinearClient,
    branches: list[str],
    hints_by_branch: dict[str, list[str]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]], dict[str, Any] | None]:
    issues_by_branch: dict[str, list[dict[str, Any]]] = {}
    errors_by_branch: dict[str, dict[str, Any]] = {}
    stop_error: dict[str, Any] | None = None
    rate_limit: dict[str, Any] | None = None
    for branch in branches:
        issues, error = (
            _fetch_branch(client, branch, hints_by_branch.get(branch, [])) if stop_error is None else ([], stop_error)
        )
        issues_by_branch[branch] = issues
        if error is None:
            continue
        errors_by_branch[branch] = error
        if error["kind"] in {"auth", "rate_limited"}:
            stop_error = error
        if error["kind"] == "rate_limited" and rate_limit is None:
            rate_limit = error
    return issues_by_branch, errors_by_branch, rate_limit


def _checkout_hints(
    sessions: list[dict[str, Any]],
    checkout_map: dict[Any, list[dict[str, str]]],
    *,
    pull_requests: bool = False,
) -> dict[tuple[str, str], list[str]]:
    """Free text per checkout that may name an issue its branch does not.

    AoE worktree branches are often slugs of the task title (``litellm``), so the session title
    and recent commit subjects are the remaining local signals that the work is Linear-tracked.
    When neither names an identifier and ``pull_requests`` is set, the branch's pull request
    text is the last resort; it costs a ``gh`` request, so it never runs for a checkout that
    already names its issue, during backoff, or without credentials.
    """
    titles: dict[tuple[str, str], list[str]] = {}
    for session in sessions:
        title = session.get("title")
        if isinstance(title, str) and title.strip():
            for checkout in checkout_map.get(session.get("id"), []):
                titles.setdefault((checkout["path"], checkout["branch"]), []).append(title)
    commits: dict[str, list[str]] = {}
    hints: dict[tuple[str, str], list[str]] = {}
    for checkouts in checkout_map.values():
        for checkout in checkouts:
            path = checkout["path"]
            if path not in commits:
                commits[path] = commit_messages(path)
            key = (path, checkout["branch"])
            hints[key] = [*titles.get(key, []), *commits[path]]
            if pull_requests and not _hints_name_issue(hints[key]):
                hints[key].extend(pull_request_hints(path, checkout["branch"]))
    return hints


def _hints_name_issue(hints: Iterable[str]) -> bool:
    """Whether local hint text names a Linear issue, without spending a request."""
    return any(identifiers_in_text(hint) for hint in hints)


def build_snapshot(
    sessions: list[dict[str, Any]],
    *,
    env: dict[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
    ignore_submodules: bool = True,
    use_pull_requests: bool = True,
) -> dict[str, Any]:
    """Fetch unique branch keys once and keep last-good issue data on failure."""
    token = resolve_token(os.environ if env is None else env)
    with _lock:
        if time.monotonic() < _state["backoff_until"]:
            return _stale_snapshot(_state["snapshot"], sessions, ignore_submodules=ignore_submodules)
        checkout_map = {
            session.get("id"): discover_checkouts(session, ignore_submodules=ignore_submodules) for session in sessions
        }
        hints = _checkout_hints(sessions, checkout_map, pull_requests=use_pull_requests)
        if token is None:
            return _auth_snapshot(sessions, checkout_map, hints)
        unique = {(item["path"], item["branch"]) for checkouts in checkout_map.values() for item in checkouts}
        branches = sorted({branch for _, branch in unique})
        hints_by_branch: dict[str, list[str]] = {}
        for path, branch in sorted(unique):
            hints_by_branch.setdefault(branch, []).extend(hints.get((path, branch), []))
        with LinearClient(token, transport=transport) as client:
            branch_issues, branch_errors, rate_limit = _fetch_branches(client, branches, hints_by_branch)
        if rate_limit:
            _state["backoff_until"] = time.monotonic() + (rate_limit.get("retry_after") or 60.0)
        current: dict[tuple[str, str], list[dict[str, Any]]] = {}
        errors: dict[tuple[str, str], dict[str, Any]] = {}
        stale_keys: set[tuple[str, str]] = set()
        for path, branch in sorted(unique):
            key = (path, branch)
            issues = branch_issues[branch]
            error = branch_errors.get(branch)
            if error:
                previous = _previous_repo(_state["snapshot"], path, branch)
                cached = (previous or {}).get("issues", [])
                if cached:
                    issues = cached
                    stale_keys.add(key)
            current[key] = issues
            # A checkout with no Linear link stays quiet: an auth or transport failure there
            # says nothing about the user's work, and the GitHub plugin already owns that row.
            if error and _repo_linked(branch, issues, hints.get(key, [])):
                errors[key] = error
        fetched = _Fetched(current=current, errors=errors, stale_keys=stale_keys, hints=hints)
        output = _assemble_snapshot(sessions, checkout_map, fetched)
        if rate_limit:
            output["rate_limited"] = True
        _state["snapshot"] = output
        return output


def _repo_linked(branch: str, issues: list[dict[str, Any]], hints: Iterable[str] = ()) -> bool:
    """Whether this checkout is known or likely to be tracked in Linear."""
    return bool(issues) or branch_is_linear(branch) or _hints_name_issue(hints)


def _session_entry(session: dict[str, Any], repos: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "session_id": session.get("id"),
        "title": session.get("title", ""),
        "project_path": session.get("project_path"),
        "repos": repos,
        "issues": [],
        "linked": any(repo.get("linked") for repo in repos),
    }


def _unavailable_repos(
    checkouts: list[dict[str, str]],
    error: dict[str, Any],
    hints: dict[tuple[str, str], list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Checkouts whose branches were never fetched, flagged only where Linear is likely."""
    hints = hints or {}
    repos: list[dict[str, Any]] = []
    for checkout in checkouts:
        linked = branch_is_linear(checkout["branch"]) or _hints_name_issue(
            hints.get((checkout["path"], checkout["branch"]), [])
        )
        repos.append(
            {
                **checkout,
                "name": Path(checkout["path"]).name,
                "issues": [],
                "linked": linked,
                "error": dict(error) if linked else None,
            }
        )
    return repos


def _auth_snapshot(
    sessions: list[dict[str, Any]],
    checkout_map: dict[Any, list[dict[str, str]]],
    hints: dict[tuple[str, str], list[str]],
) -> dict[str, Any]:
    """Report missing credentials only where a branch or commit actually names a Linear issue."""
    output = []
    for session in sessions:
        checkouts = checkout_map.get(session.get("id"), [])
        output.append(
            _session_entry(
                session,
                _unavailable_repos(checkouts, {"kind": "auth", "hint": AUTH_HINT}, hints),
            )
        )
    return {"sessions": output, "auth": {"present": False}}


def _assemble_snapshot(
    sessions: list[dict[str, Any]],
    checkout_map: dict[Any, list[dict[str, str]]],
    fetched: _Fetched,
) -> dict[str, Any]:
    output = []
    for session in sessions:
        checkouts = checkout_map.get(session.get("id"), [])
        repos = []
        session_keys = {(checkout["path"], checkout["branch"]) for checkout in checkouts}
        issues_by_id: dict[str, dict[str, Any]] = {}
        for checkout in checkouts:
            key = (checkout["path"], checkout["branch"])
            issues = fetched.current.get(key, [])
            for issue in issues:
                if isinstance(issue.get("id"), str):
                    issues_by_id[issue["id"]] = issue
            repos.append(
                {
                    **checkout,
                    "name": Path(checkout["path"]).name,
                    "issues": issues,
                    "linked": _repo_linked(checkout["branch"], issues, fetched.hints.get(key, [])),
                    "error": fetched.errors.get(key),
                }
            )
        entry = _session_entry(session, repos)
        entry["issues"] = sorted(issues_by_id.values(), key=lambda issue: issue.get("identifier", ""))
        if session_keys & fetched.stale_keys:
            entry["stale"] = True
        output.append(entry)
    return {"sessions": output, "auth": {"present": True}}


def _previous_repo(snapshot: dict[str, Any], path: str, branch: str) -> dict[str, Any] | None:
    for session in snapshot.get("sessions", []):
        for repo in session.get("repos", []):
            if repo.get("path") == path and repo.get("branch") == branch:
                return repo
    return None


def _stale_snapshot(
    cached: dict[str, Any],
    sessions: list[dict[str, Any]],
    *,
    ignore_submodules: bool = True,
) -> dict[str, Any]:
    old = {item.get("session_id"): item for item in cached.get("sessions", [])}
    results = []
    for session in sessions:
        prior = old.get(session.get("id"))
        if prior:
            stale = {**prior, "linked": bool(prior.get("linked")) or bool(prior.get("issues"))}
            if prior.get("issues"):
                stale["stale"] = True
            else:
                stale.pop("stale", None)
                if stale.get("repos"):
                    stale["repos"] = [
                        {
                            **repo,
                            "error": (
                                {"kind": "rate_limited", "hint": RATE_HINT}
                                if repo.get("linked") or repo.get("issues")
                                else None
                            ),
                        }
                        for repo in stale["repos"]
                    ]
        else:
            # A session that appeared during backoff still gets its branch inspected, so a Linear
            # branch keeps an actionable rate-limit state instead of looking unlinked.
            checkouts = discover_checkouts(session, ignore_submodules=ignore_submodules)
            hints = _checkout_hints([session], {session.get("id"): checkouts})
            stale = _session_entry(
                session,
                _unavailable_repos(checkouts, {"kind": "rate_limited", "hint": RATE_HINT}, hints),
            )
        results.append(stale)
    return {"sessions": results, "auth": cached.get("auth", {"present": True}), "rate_limited": True}
