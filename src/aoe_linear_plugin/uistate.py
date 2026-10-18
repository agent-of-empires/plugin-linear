"""Linear issue status, row badges, sorting, and pane payloads."""

from __future__ import annotations

import re
from typing import Any

ROW_BADGE_SLOT = ("row-badge", "linear_issue_badge")
ROW_COLUMN_SLOT = ("row-column", "linear_issue_status")
SORT_KEY_SLOT = ("sort-key", "linear_issue_attention")
PANE_SLOT = ("pane", "linear_issue_pane")
SELECT_METHOD = "linear.select_issue"

SORT_KEY_PAYLOAD = {
    "label": "Linear issue attention",
    "column": ROW_COLUMN_SLOT[1],
    "direction": "asc",
}
_PRIORITY = {1: "Urgent", 2: "High", 3: "Normal", 4: "Low"}


def _state(issue: dict[str, Any]) -> dict[str, Any]:
    state = issue.get("state")
    return state if isinstance(state, dict) else {}


_STATE_VISUAL = {
    "backlog": ("circle-dashed", "neutral"),
    "unstarted": ("circle", "neutral"),
    "started": ("circle-dot", "info"),
    "completed": ("circle-check", "success"),
    "canceled": ("circle-x", "neutral"),
}


def _state_visual(issue: dict[str, Any]) -> tuple[str, str, str | None]:
    state = _state(issue)
    state_type = state.get("type")
    if not isinstance(state_type, str):
        state_type = ""
    icon, tone = _STATE_VISUAL.get(state_type, ("circle", "neutral"))
    color = state.get("color")
    if isinstance(color, str) and re.fullmatch(r"#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?", color):
        return icon, tone, color
    return icon, tone, None


def _rank(issue: dict[str, Any]) -> int:
    state = _state(issue).get("type", "")
    priority = issue.get("priority", 0)
    if state in ("completed", "canceled"):
        return 5
    if priority == 1:
        return 0
    if priority == 2:
        return 1
    return 2 if state == "started" else 3


def _sort_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(issues, key=lambda issue: (_rank(issue), str(issue.get("identifier", ""))))


def _selected(issues: list[dict[str, Any]], identifier: str | None) -> dict[str, Any] | None:
    return next(
        (issue for issue in issues if issue.get("identifier") == identifier),
        issues[0] if issues else None,
    )


def _issue_rows(
    issues: list[dict[str, Any]],
    chosen: dict[str, Any],
    *,
    show_priority: bool,
) -> list[dict[str, Any]]:
    rows = []
    chosen_identifier = chosen.get("identifier")
    for issue in issues:
        identifier = issue.get("identifier")
        if identifier == chosen_identifier:
            continue
        state = _state(issue)
        icon, tone, color = _state_visual(issue)
        issue_key = identifier if isinstance(identifier, str) else ""
        row: dict[str, Any] = {
            "kind": "row",
            "prefix": issue_key,
            "label": issue.get("title", ""),
            "icon": icon,
            "mono": True,
            "method": SELECT_METHOD,
            "params": {"issue": issue_key},
            "href": issue.get("url"),
            "tone": tone,
        }
        state_name = state.get("name")
        if isinstance(state_name, str) and state_name:
            row["sublabel"] = state_name
        if color:
            row["color"] = color
        priority = issue.get("priority")
        if show_priority and isinstance(priority, int) and priority in _PRIORITY:
            row["badges"] = [{"text": f"P{priority}", "tone": "warn" if priority == 1 else "neutral"}]
        rows.append(row)
    return rows


def _error_for(session: dict[str, Any]) -> dict[str, Any] | None:
    if session.get("auth_error"):
        return {"hint": session["auth_error"]}
    return next((repo.get("error") for repo in session.get("repos", []) if repo.get("error")), None)


def _details(issue: dict[str, Any]) -> list[dict[str, Any]]:
    assignee = issue.get("assignee") or {}
    project = issue.get("project") or {}
    cycle = issue.get("cycle") or {}
    team = issue.get("team") or {}
    priority = issue.get("priority")
    labels = issue.get("labels") or {}
    label_nodes = labels.get("nodes", []) if isinstance(labels, dict) else []
    label_names = ", ".join(
        label["name"] for label in label_nodes if isinstance(label, dict) and isinstance(label.get("name"), str)
    )
    values = (
        ("Team", team.get("name")),
        ("Assignee", assignee.get("displayName") or assignee.get("name")),
        ("Project", project.get("name")),
        ("Cycle", cycle.get("name")),
        ("Priority", _PRIORITY.get(priority) if isinstance(priority, int) else None),
        ("Labels", label_names or None),
    )
    return [{"kind": "row", "label": label, "value": str(value)} for label, value in values if value]


def _resource_section(issue: dict[str, Any]) -> dict[str, Any] | None:
    attachments = issue.get("attachments")
    nodes = attachments.get("nodes", []) if isinstance(attachments, dict) else []
    if not isinstance(nodes, list):
        return None
    links = [
        attachment for attachment in nodes if isinstance(attachment, dict) and isinstance(attachment.get("url"), str)
    ]
    if not links:
        return None
    rows = [
        {
            "kind": "row",
            "label": link.get("title") or link["url"],
            "href": link["url"],
            "sublabel": link.get("subtitle", ""),
        }
        for link in links[:20]
    ]
    return {"kind": "section", "title": "Linked resources", "children": rows}


def _comments_section(issue: dict[str, Any]) -> dict[str, Any] | None:
    comments = issue.get("comments")
    nodes = comments.get("nodes", []) if isinstance(comments, dict) else []
    if not isinstance(nodes, list):
        return None
    blocks = []
    for comment in nodes[-10:]:
        if not isinstance(comment, dict):
            continue
        body = comment.get("body")
        if not isinstance(body, str) or not body.strip():
            continue
        user = comment.get("user")
        author = user.get("name") if isinstance(user, dict) else None
        if not isinstance(author, str) or not author.strip():
            author = "Unknown"
        blocks.append(
            {
                "kind": "comment",
                "author": author,
                "body": body[:2000] + ("…" if len(body) > 2000 else ""),
            }
        )
    if not blocks:
        return None
    return {
        "kind": "section",
        "title": "Comments",
        "value": str(len(blocks)),
        "boxed": True,
        "scroll": True,
        "children": blocks,
    }


def _stale_blocks(session: dict[str, Any], *, has_issues: bool) -> list[dict[str, Any]]:
    if not session.get("stale") or not has_issues:
        return []
    blocks: list[dict[str, Any]] = [
        {
            "kind": "note",
            "text": "Showing cached Linear issue data; the latest refresh failed.",
            "tone": "warn",
        }
    ]
    error = _error_for(session)
    if error:
        blocks.append(
            {
                "kind": "callout",
                "title": "Linear refresh failed",
                "detail": error.get("hint", "Request failed"),
                "tone": "warn",
            }
        )
    return blocks


def _pane(session: dict[str, Any], selected: str | None, *, show_priority: bool) -> dict[str, Any]:
    issues = _sort_issues(session.get("issues", []))
    chosen = _selected(issues, selected)
    blocks = _stale_blocks(session, has_issues=bool(issues))
    if chosen is None:
        error = _error_for(session)
        if error:
            blocks.append(
                {
                    "kind": "callout",
                    "title": "Linear unavailable",
                    "detail": error.get("hint", "Request failed"),
                    "tone": "danger",
                }
            )
        else:
            blocks.append(
                {
                    "kind": "note",
                    "text": "No Linear issue is linked to the active checkout branches.",
                    "tone": "neutral",
                }
            )
        return {"title": "Linear", "default_location": "right", "icon": "circle-dot", "blocks": blocks}

    state = _state(chosen)
    icon, tone, color = _state_visual(chosen)
    callout: dict[str, Any] = {
        "kind": "callout",
        "title": f"{chosen.get('identifier', 'Issue')} · {state.get('name', 'Unknown status')}",
        "detail": chosen.get("title", ""),
        "icon": icon,
        "tone": tone,
    }
    if color:
        callout["color"] = color
    blocks.append(callout)
    issue_rows = _issue_rows(issues, chosen, show_priority=show_priority)
    if issue_rows:
        blocks.append(
            {
                "kind": "section",
                "title": "Other linked issues",
                "children": issue_rows,
                "value": str(len(issue_rows)),
                "boxed": True,
            }
        )
    details = _details(chosen)
    if details:
        blocks.append({"kind": "section", "title": "Details", "children": details})
    description = chosen.get("description")
    if isinstance(description, str) and description.strip():
        blocks.append(
            {
                "kind": "section",
                "title": "Description",
                "children": [{"kind": "note", "text": description[:4000]}],
                "collapsible": True,
                "collapsed": True,
            }
        )
    resources = _resource_section(chosen)
    if resources:
        blocks.append(resources)
    comments = _comments_section(chosen)
    if comments:
        blocks.append(comments)
    return {"title": "Linear", "default_location": "right", "icon": "circle-dot", "blocks": blocks}


def _session_ui(
    session: dict[str, Any],
    selected: dict[str, str],
    *,
    show_priority: bool,
) -> list[dict[str, Any]]:
    sid = session.get("session_id")
    if not isinstance(sid, str):
        return []
    issues = _sort_issues(session.get("issues", []))
    current = _selected(issues, selected.get(sid))
    badge_items: list[dict[str, Any]] = []
    column: dict[str, Any] = {}
    if current:
        state = _state(current)
        icon, state_tone, _ = _state_visual(current)
        tone = "success" if state.get("type") == "completed" else "warn" if current.get("priority") == 1 else state_tone
        badge_items.append(
            {
                "text": current.get("identifier", "Linear"),
                "icon": icon,
                "tone": tone,
                "href": current.get("url"),
                "tooltip": current.get("title", ""),
            }
        )
        column = {
            "text": state.get("name", "Open"),
            "tone": tone,
            "tooltip": current.get("title", ""),
            "sort_value": _rank(current),
        }
    else:
        error = _error_for(session)
        if error:
            hint = error.get("hint", "Linear request failed")
            badge_items.append({"text": "Linear error", "tone": "danger", "tooltip": hint})
            column = {"text": "Linear unavailable", "tone": "danger", "tooltip": hint, "sort_value": 98}
    if session.get("stale") and issues:
        badge_items.append({"text": "stale", "tone": "warn", "tooltip": "Showing cached Linear issue data"})
        if column:
            column["tone"] = "warn"
    badge_payload: dict[str, Any] = {"items": badge_items}
    if current and isinstance(current.get("url"), str):
        badge_payload["href"] = current["url"]
    return [
        {
            "slot": ROW_BADGE_SLOT[0],
            "id": ROW_BADGE_SLOT[1],
            "session_id": sid,
            "payload": badge_payload,
        },
        {
            "slot": ROW_COLUMN_SLOT[0],
            "id": ROW_COLUMN_SLOT[1],
            "session_id": sid,
            "payload": column,
        },
        {
            "slot": PANE_SLOT[0],
            "id": PANE_SLOT[1],
            "session_id": sid,
            "payload": _pane(session, selected.get(sid), show_priority=show_priority),
        },
    ]


def session_payloads(
    snapshot: dict[str, Any],
    selected: dict[str, str] | None = None,
    *,
    show_priority: bool = True,
) -> list[dict[str, Any]]:
    """Build per-session badge, status, and pane state plus a global sort key."""
    selected = selected or {}
    result = [{"slot": SORT_KEY_SLOT[0], "id": SORT_KEY_SLOT[1], "payload": dict(SORT_KEY_PAYLOAD)}]
    for session in snapshot.get("sessions", []):
        result.extend(_session_ui(session, selected, show_priority=show_priority))
    return result
