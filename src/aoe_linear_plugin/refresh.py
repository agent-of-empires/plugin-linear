"""Rate-aware aggregate issue refresh with last-good cache fallback."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from aoe_linear_plugin.auth import resolve_token
from aoe_linear_plugin.client import LinearClient
from aoe_linear_plugin.discovery import discover_checkouts
from aoe_linear_plugin.errors import LinearError
from aoe_linear_plugin.resolver import resolve_branch

_lock = threading.Lock()
_state: dict[str, Any] = {
    "snapshot": {"sessions": [], "auth": {"present": False}},
    "backoff_until": 0.0,
}


def _fetch_branch(
    token: str,
    branch: str,
    transport: httpx.BaseTransport | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    try:
        with LinearClient(token, transport=transport) as client:
            return resolve_branch(client, branch), None
    except LinearError as exc:
        error: dict[str, Any] = {"kind": exc.kind, "hint": str(exc)}
        if exc.retry_after is not None:
            error["retry_after"] = exc.retry_after
        return [], error


def build_snapshot(
    sessions: list[dict[str, Any]],
    *,
    env: dict[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
    ignore_submodules: bool = True,
) -> dict[str, Any]:
    """Fetch unique branch keys once and keep last-good issue data on failure."""
    token = resolve_token(os.environ if env is None else env)
    with _lock:
        if time.monotonic() < _state["backoff_until"]:
            return _stale_snapshot(_state["snapshot"], sessions)
        if token is None:
            return {
                "sessions": [
                    _empty_session(session, "Set LINEAR_API_KEY to load Linear issue data.") for session in sessions
                ],
                "auth": {"present": False},
            }
        checkout_map = {
            session.get("id"): discover_checkouts(session, ignore_submodules=ignore_submodules) for session in sessions
        }
        unique = {(item["path"], item["branch"]) for checkouts in checkout_map.values() for item in checkouts}
        current: dict[tuple[str, str], list[dict[str, Any]]] = {}
        errors: dict[tuple[str, str], dict[str, Any]] = {}
        for path, branch in sorted(unique):
            key = (path, branch)
            issues, error = _fetch_branch(token, branch, transport)
            if error:
                errors[key] = error
                previous = _previous_repo(_state["snapshot"], path, branch)
                if previous:
                    issues = previous.get("issues", [])
                if error["kind"] == "rate_limited":
                    _state["backoff_until"] = time.monotonic() + (error.get("retry_after") or 60.0)
                    return _stale_snapshot(_state["snapshot"], sessions)
            current[key] = issues
        output = _assemble_snapshot(sessions, checkout_map, current, errors)
        _state["snapshot"] = output
        return output


def _assemble_snapshot(
    sessions: list[dict[str, Any]],
    checkout_map: dict[Any, list[dict[str, str]]],
    current: dict[tuple[str, str], list[dict[str, Any]]],
    errors: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    output = []
    for session in sessions:
        checkouts = checkout_map.get(session.get("id"), [])
        repos = []
        session_keys = {(checkout["path"], checkout["branch"]) for checkout in checkouts}
        issues_by_id: dict[str, dict[str, Any]] = {}
        for checkout in checkouts:
            key = (checkout["path"], checkout["branch"])
            issues = current.get(key, [])
            for issue in issues:
                if isinstance(issue.get("id"), str):
                    issues_by_id[issue["id"]] = issue
            repos.append(
                {
                    **checkout,
                    "name": Path(checkout["path"]).name,
                    "issues": issues,
                    "error": errors.get(key),
                }
            )
        output.append(
            {
                "session_id": session.get("id"),
                "title": session.get("title", ""),
                "project_path": session.get("project_path"),
                "repos": repos,
                "issues": sorted(issues_by_id.values(), key=lambda issue: issue.get("identifier", "")),
                **({"stale": True} if session_keys & errors.keys() else {}),
            }
        )
    return {"sessions": output, "auth": {"present": True}}


def _previous_repo(snapshot: dict[str, Any], path: str, branch: str) -> dict[str, Any] | None:
    for session in snapshot.get("sessions", []):
        for repo in session.get("repos", []):
            if repo.get("path") == path and repo.get("branch") == branch:
                return repo
    return None


def _empty_session(session: dict[str, Any], message: str, *, kind: str = "auth") -> dict[str, Any]:
    return {
        "session_id": session.get("id"),
        "title": session.get("title", ""),
        "repos": [{"issues": [], "error": {"kind": kind, "hint": message}}],
        "issues": [],
    }


def _stale_snapshot(cached: dict[str, Any], sessions: list[dict[str, Any]]) -> dict[str, Any]:
    old = {item.get("session_id"): item for item in cached.get("sessions", [])}
    results = []
    for session in sessions:
        prior = old.get(session.get("id"))
        stale = (
            {**prior, "stale": True}
            if prior
            else _empty_session(session, "Linear rate limit active; refresh will retry later.", kind="rate_limited")
        )
        results.append(stale)
    return {"sessions": results, "auth": cached.get("auth", {"present": True}), "rate_limited": True}
