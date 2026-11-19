"""Discover current-user Linear issues that qualify as session suggestions."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit

from aoe_linear_plugin.auth import resolve_token
from aoe_linear_plugin.client import LinearClient
from aoe_linear_plugin.errors import LinearError, LinearGraphQLError

MAX_ITEMS = 500
CRITERION = "assigned_up_next"


def _bounded(value: str, limit: int) -> str:
    return value.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


def _setting_list(value: Any, default: list[str], name: str) -> list[str]:
    if value is None:
        return default
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a comma-separated list.")
    return sorted({part.strip() for part in value.split(",") if part.strip()}) or default


def _scoped(issue: dict[str, Any], teams: set[str], projects: set[str]) -> bool:
    team = issue.get("team") or {}
    project = issue.get("project") or {}
    return (not teams or team.get("key") in teams or team.get("id") in teams) and (
        not projects or project.get("name") in projects or project.get("id") in projects
    )


def _suggestion(issue: dict[str, Any]) -> dict[str, Any] | None:
    issue_id = issue.get("id")
    identifier = issue.get("identifier")
    title = issue.get("title")
    url = issue.get("url")
    if not (
        isinstance(issue_id, str)
        and issue_id.strip()
        and isinstance(identifier, str)
        and identifier.strip()
        and isinstance(title, str)
        and title.strip()
        and isinstance(url, str)
        and url
    ):
        return None
    try:
        parsed_url = urlsplit(url)
        valid_url = (
            url.isascii()
            and not any(char.isspace() or ord(char) < 32 or ord(char) == 127 or char == "\\" for char in url)
            and "://" in url
            and parsed_url.scheme.lower() in {"http", "https"}
            and parsed_url.hostname
            and parsed_url.hostname.isascii()
            and "%" not in parsed_url.hostname
            and parsed_url.username is None
            and parsed_url.password is None
            and len(url.encode("utf-8")) <= 2048
        )
    except ValueError:
        valid_url = False
    if not valid_url or len(issue_id.encode("utf-8")) > 256:
        raise LinearGraphQLError("Linear returned an invalid suggestion identity or URL.")
    project = issue.get("project") or {}
    project_id = project.get("id")
    project_name = project.get("name")
    description = issue.get("description")
    details = (
        description.strip()
        if isinstance(description, str) and description.strip()
        else "No issue description provided."
    )
    team = issue.get("team") or {}
    state_name = (issue.get("state") or {}).get("name") or "Linear"
    priority = issue.get("priority")
    team_name = team.get("name") or "Linear"
    display_title = _bounded(f"{identifier}: {title}", 512)
    mapping_key = project_id if isinstance(project_id, str) and project_id else team.get("id")
    if isinstance(mapping_key, str) and (not mapping_key.strip() or len(mapping_key.encode("utf-8")) > 256):
        raise LinearGraphQLError("Linear returned an invalid suggestion project key.")
    return {
        "id": issue_id,
        "title": display_title,
        "reason": _bounded(f"Assigned to you · {state_name} · {team_name}", 2048),
        "source_url": url,
        "source_ref": _bounded(identifier, 2048),
        "preview": _bounded(details, 16384),
        **({"mapping_key": mapping_key} if isinstance(mapping_key, str) and mapping_key else {}),
        "criterion": CRITERION,
        "variables": {
            "identifier": _bounded(identifier, 2048),
            "title": _bounded(title, 2048),
            "url": _bounded(url, 2048),
            "team": _bounded(str(team_name), 2048),
            "project": _bounded(project_name if isinstance(project_name, str) else "", 2048),
        },
        "draft": {
            "title": display_title,
            "prompt": _bounded(f"Work on this Linear issue: {title} ({identifier}).\n\nSource: {url}", 65536),
        },
        "_priority": (
            priority if isinstance(priority, int) and not isinstance(priority, bool) and 1 <= priority <= 4 else 5
        ),
        "_created": issue.get("createdAt") or "",
    }


def discover_suggestions(
    client: LinearClient,
    *,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Fetch eligible current-user issues and return a complete, qualified snapshot."""
    config = settings or {}
    states = set(_setting_list(config.get("suggestion_up_next_states"), ["Up Next"], "suggestion_up_next_states"))
    teams = set(_setting_list(config.get("suggestion_team_scope"), [], "suggestion_team_scope"))
    projects = set(_setting_list(config.get("suggestion_project_scope"), [], "suggestion_project_scope"))
    viewer = client.execute("query SuggestionViewer { viewer { id } }").get("viewer")
    viewer_id = viewer.get("id") if isinstance(viewer, dict) else None
    if not isinstance(viewer_id, str) or not viewer_id:
        raise LinearGraphQLError("Linear did not return the authenticated user identity.")
    after: str | None = None
    seen_cursors: set[str] = set()
    issues: list[dict[str, Any]] = []
    query = """query AssignedSuggestionIssues($after: String, $filter: IssueFilter!) {
      issues(first: 100, after: $after, filter: $filter) {
        nodes {
          id identifier title url description priority createdAt
          state { name type }
          assignee { id }
          team { id key name }
          project { id name }
        }
        pageInfo { hasNextPage endCursor }
      }
    }"""
    while True:
        result = client.execute(
            query,
            {
                "after": after,
                "filter": {
                    "assignee": {"id": {"eq": viewer_id}},
                    "state": {"name": {"in": sorted(states)}, "type": {"nin": ["completed", "canceled"]}},
                },
            },
        )
        connection = result.get("issues")
        nodes = connection.get("nodes") if isinstance(connection, dict) else None
        page = connection.get("pageInfo") if isinstance(connection, dict) else None
        if not isinstance(nodes, list) or not isinstance(page, dict) or not isinstance(page.get("hasNextPage"), bool):
            raise LinearGraphQLError("Linear returned an incomplete assigned-issues page.")
        issues.extend(issue for issue in nodes if isinstance(issue, dict))
        if not page["hasNextPage"]:
            break
        cursor = page.get("endCursor")
        if not isinstance(cursor, str) or not cursor or cursor in seen_cursors:
            raise LinearGraphQLError("Linear returned an invalid issue pagination cursor.")
        seen_cursors.add(cursor)
        after = cursor
    output = []
    seen_ids: set[str] = set()
    for issue in issues:
        state = issue.get("state") or {}
        assignee = issue.get("assignee") or {}
        if (
            assignee.get("id") != viewer_id
            or state.get("name") not in states
            or state.get("type") in {"completed", "canceled"}
        ):
            continue
        if not _scoped(issue, teams, projects):
            continue
        suggestion = _suggestion(issue)
        if suggestion and suggestion["id"] not in seen_ids:
            seen_ids.add(suggestion["id"])
            output.append(suggestion)
    output.sort(key=lambda item: (item.pop("_priority"), item.pop("_created"), item["id"]))
    return output[:MAX_ITEMS]


def build_suggestions(
    settings: dict[str, Any] | None = None,
    *,
    env: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Use the existing daemon token configuration to build a fresh snapshot."""
    token = resolve_token(os.environ if env is None else env)
    if token is None:
        raise LinearError("Set LINEAR_API_KEY in the AoE daemon's environment and restart the daemon.")
    with LinearClient(token) as client:
        return discover_suggestions(client, settings=settings)
