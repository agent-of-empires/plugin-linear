"""Status and open command behavior."""

from __future__ import annotations

import os
import webbrowser
from typing import Any
from urllib.parse import quote

import httpx

from aoe_linear_plugin.auth import resolve_token
from aoe_linear_plugin.client import LinearClient
from aoe_linear_plugin.discovery import checkout_for_path
from aoe_linear_plugin.errors import LinearError
from aoe_linear_plugin.resolver import branch_is_linear, resolve_branch, selected_issue


def issue_url(issue: dict[str, Any]) -> str:
    """Use Linear's canonical URL, falling back to the standard identifier route."""
    url = issue.get("url")
    if isinstance(url, str) and url.startswith("https://linear.app/"):
        return url
    identifier = issue.get("identifier")
    return f"https://linear.app/issue/{quote(identifier, safe='-')}" if isinstance(identifier, str) else ""


def _summary(issue: dict[str, Any] | None, branch: str) -> str:
    if issue is None:
        return f"Linear: no issue linked to {branch}"
    state = issue.get("state") or {}
    return f"{issue.get('identifier', 'Issue')}: {issue.get('title', '')} ({state.get('name', 'unknown')})"


def linear_status(
    path: str = ".",
    *,
    env: dict[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
    selected: str | None = None,
) -> dict[str, Any]:
    """Return fail-soft issue state for the current branch."""
    result: dict[str, Any] = {
        "summary": "Linear: not a git checkout",
        "branch": None,
        "issues": [],
        "selected": None,
        "linked": False,
        "error": None,
    }
    checkout = checkout_for_path(path)
    if checkout is None:
        return result
    branch = checkout["branch"]
    result["branch"] = branch
    # A checkout whose branch never names a Linear issue is treated as not using Linear, so a
    # missing key or an unreachable API reports a neutral summary instead of an error.
    linked = branch_is_linear(branch)
    result["linked"] = linked
    result["summary"] = f"Linear: no issue linked to {branch}"
    token = resolve_token(os.environ if env is None else env)
    if token is None:
        if linked:
            result["summary"] = "Linear: set LINEAR_API_KEY to show linked issues"
            result["error"] = {"kind": "auth", "hint": "Set LINEAR_API_KEY (or LINEAR_TOKEN) with Linear read access."}
        return result
    try:
        with LinearClient(token, transport=transport) as client:
            issues = resolve_branch(client, branch)
    except LinearError as exc:
        if not linked:
            return result
        result["summary"] = f"Linear: {str(exc).splitlines()[0]}"
        result["error"] = {
            "kind": exc.kind,
            "hint": str(exc),
            **({"retry_after": exc.retry_after} if exc.retry_after is not None else {}),
        }
        return result
    current = selected_issue(issues, selected)
    result["issues"] = issues
    result["linked"] = linked or bool(issues)
    result["selected"] = current.get("identifier") if current else None
    result["summary"] = _summary(current, branch)
    return result


def linear_open(
    path: str = ".",
    *,
    env: dict[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
    selected: str | None = None,
    open_browser: bool = False,
) -> dict[str, str]:
    """Resolve an issue URL and optionally open it in the browser."""
    status = linear_status(path, env=env, transport=transport, selected=selected)
    issue = selected_issue(status["issues"], selected)
    if issue is None:
        error = status["error"]
        if error:
            raise ValueError(error["hint"])
        # Fail soft for a checkout Linear is not part of, like the GitHub plugin's compare fallback.
        return {"url": "", "kind": "none", "identifier": ""}
    url = issue_url(issue)
    if open_browser:
        webbrowser.open(url)
    return {"url": url, "kind": "issue", "identifier": issue.get("identifier", "")}
